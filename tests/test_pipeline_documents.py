from pathlib import Path

from jarvis_memory.config import MemoryConfig
from jarvis_memory.ingestion.chunker import ChunkingParams, detect_overlap, split_into_chunks
from jarvis_memory.ingestion.pipeline import IngestionPipeline
from jarvis_memory.retrieval.keyword_retriever import KeywordRetriever
from jarvis_memory.store.db import connect, initialize
from jarvis_memory.store.document_store import DocumentStore


class DummyVectorStore:
    def __init__(self) -> None:
        self.rows: dict[str, dict] = {}

    def upsert_chunks(self, ids, texts, metadatas) -> None:
        for chunk_id, text, meta in zip(ids, texts, metadatas):
            self.rows[chunk_id] = {"text": text, "metadata": meta}

    def delete_by_document(self, document_id: str) -> None:
        self.rows = {k: v for k, v in self.rows.items() if v["metadata"]["document_id"] != document_id}


def _setup(tmp_path: Path, memory_config: MemoryConfig):
    memory_config.ensure_dirs()
    conn = connect(memory_config.paths.sqlite_path)
    initialize(conn)
    store = DummyVectorStore()
    return IngestionPipeline(memory_config, store, conn=conn), DocumentStore(conn), store, conn


def test_upload_duplicate_is_not_written(tmp_path: Path, memory_config: MemoryConfig) -> None:
    pipeline, docs, _, _ = _setup(tmp_path, memory_config)
    a = tmp_path / "a.md"
    b = tmp_path / "b.md"
    a.write_text("Gleicher Inhalt fuer beide Dateien.", encoding="utf-8")
    b.write_text("Gleicher Inhalt fuer beide Dateien.", encoding="utf-8")

    first = pipeline.ingest_file(a)
    second = pipeline.ingest_file(b, allow_duplicates=False)

    assert second.action == "duplicate"
    assert second.duplicate_of == first.document_id
    assert [d.name for d in docs.list_documents()] == ["a.md"]


def test_deleting_original_promotes_duplicate(tmp_path: Path, memory_config: MemoryConfig) -> None:
    pipeline, docs, store, _ = _setup(tmp_path, memory_config)
    for name in ("a.md", "b.md", "c.md"):
        (tmp_path / name).write_text("Gleicher Inhalt fuer alle Dateien.", encoding="utf-8")
    pipeline.ingest_path(tmp_path)

    original = next(d for d in docs.list_documents() if d.duplicate_of is None)
    assert pipeline.delete_document(original.id)

    remaining = docs.list_documents()
    assert len(remaining) == 2
    indexed = [d for d in remaining if d.chunk_count > 0]
    assert len(indexed) == 1
    assert [d.duplicate_of for d in remaining if d.chunk_count == 0] == [indexed[0].id]
    assert {r["metadata"]["document_id"] for r in store.rows.values()} == {indexed[0].id}


def test_keyword_scores_reflect_relevance(tmp_path: Path, memory_config: MemoryConfig) -> None:
    pipeline, _, _, conn = _setup(tmp_path, memory_config)
    (tmp_path / "a.md").write_text("Tutorium Tutorium Tutorium Statistik", encoding="utf-8")
    (tmp_path / "b.md").write_text("Ein langer Text, der nur einmal nebenbei das Wort Tutorium nennt und sonst ueber andere Dinge spricht.", encoding="utf-8")
    pipeline.ingest_path(tmp_path)

    results = KeywordRetriever(conn).search("Tutorium Statistik", top_k=5)
    scores = [r.keyword_score for r in results]
    assert len(scores) == 2
    assert all(0 < s < 1 for s in scores)
    assert scores[0] > scores[1]
    assert results[0].document_id is not None


def test_detect_overlap_matches_chunker() -> None:
    text = "\n\n".join([f"Absatz {i} " + ("x" * 120) for i in range(6)])
    params = ChunkingParams(max_chars=320, overlap_chars=50, min_chunk_chars=80)
    chunks = split_into_chunks(text, params)

    overlaps = [detect_overlap(chunks[i - 1], chunks[i], params.overlap_chars) for i in range(1, len(chunks))]
    assert overlaps and all(o == params.overlap_chars for o in overlaps)
    assert detect_overlap("abc", "xyz", 2) == 0
