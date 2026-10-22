"""Single entry point for callers outside the pipeline (API, UI, agents).

All operations are serialized with a lock so one instance can be shared across
request and background-job threads.
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from jarvis_memory.app import create_embedder
from jarvis_memory.config import MemoryConfig
from jarvis_memory.eval.evaluate import evaluate, load_eval_cases
from jarvis_memory.eval.run_store import EvalRun, EvalRunStore
from jarvis_memory.ingestion.chunker import detect_overlap
from jarvis_memory.ingestion.pipeline import IngestionPipeline
from jarvis_memory.models import ChunkInfo, DocumentInfo, FactRecord, IngestResult, RetrievalResult
from jarvis_memory.retrieval.context_builder import ContextBuilder
from jarvis_memory.retrieval.hybrid import HybridRetriever, RetrievalFilters
from jarvis_memory.retrieval.keyword_retriever import KeywordRetriever
from jarvis_memory.retrieval.vector_retriever import VectorRetriever
from jarvis_memory.store.db import connect, initialize
from jarvis_memory.store.document_store import DocumentStore
from jarvis_memory.store.fact_store import FactStore
from jarvis_memory.store.vector_store import ChromaVectorStore


@dataclass(slots=True)
class ChunkView:
    chunk: ChunkInfo
    length: int
    # Number of leading characters carried over from the previous chunk.
    overlap_chars: int
    # "short" | "long" | None
    flag: str | None


@dataclass(slots=True)
class ChunkStats:
    count: int
    avg_length: float
    min_length: int
    max_length: int
    short_count: int
    long_count: int
    short_threshold: int
    long_threshold: int


@dataclass(slots=True)
class DocumentChunks:
    document: DocumentInfo
    chunks: list[ChunkView]
    stats: ChunkStats


@dataclass(slots=True)
class QueryResult:
    vector: list[RetrievalResult]
    keyword: list[RetrievalResult]
    fused: list[RetrievalResult]
    context: str


@dataclass(slots=True)
class ChunkLocation:
    chunk_id: str
    document_id: str
    vector_rank: int | None
    vector_score: float | None
    keyword_rank: int | None
    keyword_score: float | None
    # Rank in the real query result (top_k), None if it did not make it.
    fused_rank: int | None
    fused_score: float | None
    # Rank when both candidate lists are extended to `depth`.
    deep_fused_rank: int | None
    in_top_k: bool


class FactNotActiveError(ValueError):
    pass


class MemoryService:
    def __init__(self, config: MemoryConfig, vector_store: ChromaVectorStore | None = None) -> None:
        config.ensure_dirs()
        self._config = config
        self._lock = threading.RLock()
        self._conn = connect(config.paths.sqlite_path, check_same_thread=False)
        initialize(self._conn)
        self._vector_store = vector_store or ChromaVectorStore(str(config.paths.chroma_dir), create_embedder(config))
        self._pipeline = IngestionPipeline(config, self._vector_store, conn=self._conn)
        self._documents = DocumentStore(self._conn)
        self._facts = FactStore(self._conn)
        self._retriever = HybridRetriever(
            VectorRetriever(self._conn, self._vector_store),
            KeywordRetriever(self._conn),
            config.retrieval,
        )
        self._context = ContextBuilder(self._facts, self._retriever, config.context)
        self._eval_runs = EvalRunStore(self._conn)

    @property
    def config(self) -> MemoryConfig:
        return self._config

    @staticmethod
    def new_document_id() -> str:
        return str(uuid.uuid4())

    # --- documents -------------------------------------------------------

    def ingest_file(self, path: Path, document_id: str | None = None, allow_duplicates: bool = False) -> IngestResult:
        with self._lock:
            return self._pipeline.ingest_file(path, document_id=document_id, allow_duplicates=allow_duplicates)

    def ingest_upload(self, path: Path, document_id: str | None = None) -> IngestResult:
        """Ingest a file from the uploads dir; the stored file is removed again if it is
        a duplicate or fails to ingest, so only indexed uploads stay on disk."""
        try:
            result = self.ingest_file(path, document_id=document_id, allow_duplicates=False)
        except Exception:
            self._remove_upload(path)
            raise
        if result.action == "duplicate":
            self._remove_upload(path)
        return result

    def list_documents(self) -> list[DocumentInfo]:
        with self._lock:
            return self._documents.list_documents()

    def get_document(self, document_id: str) -> DocumentInfo | None:
        with self._lock:
            return self._documents.get_document(document_id)

    def get_document_chunks(self, document_id: str) -> DocumentChunks | None:
        with self._lock:
            document = self._documents.get_document(document_id)
            if document is None:
                return None
            chunks = self._documents.get_chunks(document_id)

        chunking = self._config.chunking
        short_threshold = chunking.min_chunk_chars
        long_threshold = int(chunking.max_chars * self._config.inspection.long_chunk_factor)

        views: list[ChunkView] = []
        for idx, chunk in enumerate(chunks):
            overlap = detect_overlap(chunks[idx - 1].text, chunk.text, chunking.overlap_chars) if idx > 0 else 0
            length = len(chunk.text)
            flag = "short" if length < short_threshold else "long" if length > long_threshold else None
            views.append(ChunkView(chunk=chunk, length=length, overlap_chars=overlap, flag=flag))

        lengths = [v.length for v in views]
        stats = ChunkStats(
            count=len(views),
            avg_length=sum(lengths) / len(lengths) if lengths else 0.0,
            min_length=min(lengths, default=0),
            max_length=max(lengths, default=0),
            short_count=sum(1 for v in views if v.flag == "short"),
            long_count=sum(1 for v in views if v.flag == "long"),
            short_threshold=short_threshold,
            long_threshold=long_threshold,
        )
        return DocumentChunks(document=document, chunks=views, stats=stats)

    def delete_document(self, document_id: str) -> bool:
        with self._lock:
            document = self._documents.get_document(document_id)
            if document is None:
                return False
            self._pipeline.delete_document(document_id)
            self._remove_upload(Path(document.source_path))
            return True

    def reindex_document(self, document_id: str) -> IngestResult:
        """Raises LookupError if unknown, FileNotFoundError if the source file is gone."""
        with self._lock:
            return self._pipeline.reindex_document(document_id)

    def _remove_upload(self, path: Path) -> None:
        # Only files we stored ourselves are removed; ingested folders like data/ stay untouched.
        uploads_dir = self._config.paths.uploads_dir.resolve()
        resolved = path.resolve()
        if not resolved.is_relative_to(uploads_dir):
            return
        resolved.unlink(missing_ok=True)
        parent = resolved.parent
        if parent != uploads_dir and parent.is_relative_to(uploads_dir) and not any(parent.iterdir()):
            parent.rmdir()

    # --- retrieval -------------------------------------------------------

    def query(
        self,
        text: str,
        top_k: int | None = None,
        filters: RetrievalFilters | None = None,
        rerank: bool | None = None,
    ) -> QueryResult:
        with self._lock:
            limit = top_k or self._config.context.max_chunks
            inspection = self._retriever.inspect(text, top_k=limit, filters=filters, rerank=rerank)
            context = self._context.format_context(inspection.fused)
        return QueryResult(
            vector=inspection.vector,
            keyword=inspection.keyword,
            fused=inspection.fused,
            context=context,
        )

    def locate(
        self,
        text: str,
        document_id: str,
        chunk_id: str | None = None,
        top_k: int | None = None,
        filters: RetrievalFilters | None = None,
        depth: int | None = None,
    ) -> list[ChunkLocation]:
        """Where do the chunks of a document (or one chunk) rank for this query?"""
        depth = depth or self._config.inspection.locate_depth
        limit = top_k or self._config.context.max_chunks
        with self._lock:
            targets = [c for c in self._documents.get_chunks(document_id) if chunk_id is None or c.id == chunk_id]
            actual = self._retriever.inspect(text, top_k=limit, filters=filters)
            # Fusion of two depth-long lists yields at most 2 * depth entries.
            deep = self._retriever.inspect(text, top_k=2 * depth, filters=filters, rerank=False, candidate_k=depth)

        vector_pos = {r.chunk_id: (i, r) for i, r in enumerate(deep.vector, start=1)}
        keyword_pos = {r.chunk_id: (i, r) for i, r in enumerate(deep.keyword, start=1)}
        fused_pos = {r.chunk_id: (i, r) for i, r in enumerate(actual.fused, start=1)}
        deep_fused_pos = {r.chunk_id: i for i, r in enumerate(deep.fused, start=1)}

        locations: list[ChunkLocation] = []
        for chunk in targets:
            v = vector_pos.get(chunk.id)
            k = keyword_pos.get(chunk.id)
            f = fused_pos.get(chunk.id)
            locations.append(
                ChunkLocation(
                    chunk_id=chunk.id,
                    document_id=chunk.document_id,
                    vector_rank=v[0] if v else None,
                    vector_score=v[1].vector_score if v else None,
                    keyword_rank=k[0] if k else None,
                    keyword_score=k[1].keyword_score if k else None,
                    fused_rank=f[0] if f else None,
                    fused_score=f[1].score if f else None,
                    deep_fused_rank=deep_fused_pos.get(chunk.id),
                    in_top_k=f is not None,
                )
            )
        return locations

    # --- facts -----------------------------------------------------------

    def list_facts(self, include_superseded: bool = False) -> list[FactRecord]:
        with self._lock:
            return self._facts.get_all_facts() if include_superseded else self._facts.get_current_facts()

    def get_fact(self, fact_id: int) -> FactRecord | None:
        with self._lock:
            return self._facts.get_fact(fact_id)

    def add_fact(self, subject: str, attribute: str, value: str, source: str, valid_from: str | None = None) -> FactRecord:
        with self._lock:
            fact_id = self._facts.add_fact(subject, attribute, value, source, valid_from)
            fact = self._facts.get_fact(fact_id)
        assert fact is not None
        return fact

    def update_fact(self, fact_id: int, value: str, source: str, valid_from: str | None = None) -> FactRecord:
        """Supersedes the fact with a new version. Raises LookupError / FactNotActiveError."""
        with self._lock:
            current = self._facts.get_fact(fact_id)
            if current is None:
                raise LookupError(f"Fact not found: {fact_id}")
            if current.status != "active":
                raise FactNotActiveError(f"Fact {fact_id} is {current.status}; only the active version can be changed")
            new_id = self._facts.update_fact(fact_id, value, source, valid_from)
            fact = self._facts.get_fact(new_id)
        assert fact is not None
        return fact

    def fact_history(self, fact_id: int) -> list[FactRecord] | None:
        with self._lock:
            fact = self._facts.get_fact(fact_id)
            if fact is None:
                return None
            return self._facts.get_fact_history(fact.subject, fact.attribute)

    # --- eval ------------------------------------------------------------

    def run_eval(self, k: int | None = None) -> EvalRun:
        k = k or self._config.retrieval.top_k
        dataset = self._config.paths.eval_dataset_path
        cases = load_eval_cases(dataset)
        with self._lock:
            metrics = evaluate(self._retriever, cases, k=k)
            return self._eval_runs.save(metrics, k=k, dataset=str(dataset), config=self._config_snapshot())

    def list_eval_runs(self) -> list[EvalRun]:
        with self._lock:
            return self._eval_runs.list_runs()

    def _config_snapshot(self) -> dict[str, Any]:
        return {
            "embedding": asdict(self._config.embedding),
            "chunking": asdict(self._config.chunking),
            "retrieval": asdict(self._config.retrieval),
            "context": asdict(self._config.context),
        }

    # --- misc ------------------------------------------------------------

    def stats(self) -> dict[str, int]:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT (SELECT COUNT(*) FROM documents) AS documents,
                       (SELECT COUNT(*) FROM chunks) AS chunks,
                       (SELECT COUNT(*) FROM facts WHERE status = 'active') AS facts
                """
            ).fetchone()
        return {"documents": int(row["documents"]), "chunks": int(row["chunks"]), "facts": int(row["facts"])}
