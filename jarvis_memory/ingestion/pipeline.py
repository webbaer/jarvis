from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path

from jarvis_memory.config import MemoryConfig
from jarvis_memory.ingestion.chunker import ChunkingParams, split_into_chunks
from jarvis_memory.ingestion.loaders import LoaderRegistry
from jarvis_memory.store.db import connect, initialize
from jarvis_memory.store.vector_store import ChromaVectorStore


class IngestionPipeline:
    def __init__(self, config: MemoryConfig, vector_store: ChromaVectorStore) -> None:
        self._config = config
        self._vector_store = vector_store
        self._loaders = LoaderRegistry()
        self._conn = connect(config.paths.sqlite_path)
        initialize(self._conn)

    def ingest_path(self, path: Path) -> dict[str, int]:
        files = self._collect_files(path)
        stats = {"processed": 0, "skipped": 0, "updated": 0}
        for file_path in files:
            action = self._ingest_file(file_path)
            stats[action] += 1
        self._conn.commit()
        return stats

    def _collect_files(self, path: Path) -> list[Path]:
        if path.is_file():
            return [path]
        candidates: list[Path] = []
        for ext in ("*.txt", "*.md", "*.pdf", "*.eml"):
            candidates.extend(path.rglob(ext))
        return sorted({p.resolve() for p in candidates})

    def _ingest_file(self, path: Path) -> str:
        loaded = self._loaders.load_path(path)
        content_hash = hashlib.sha256(loaded.content.encode("utf-8")).hexdigest()
        existing = self._conn.execute(
            "SELECT id, content_hash FROM documents WHERE source_path = ?",
            (str(path),),
        ).fetchone()

        same_hash_row = self._conn.execute(
            "SELECT id FROM documents WHERE content_hash = ? LIMIT 1",
            (content_hash,),
        ).fetchone()

        now = datetime.now(timezone.utc).isoformat()
        if existing and existing["content_hash"] == content_hash:
            return "skipped"

        document_id = existing["id"] if existing else str(uuid.uuid4())

        if existing:
            self._delete_document_chunks(document_id)
            action = "updated"
        else:
            action = "processed"

        duplicate_of = None
        if same_hash_row and same_hash_row["id"] != document_id:
            duplicate_of = same_hash_row["id"]

        self._conn.execute(
            """
            INSERT INTO documents (id, source_path, content_hash, doc_type, doc_date, indexed_at, duplicate_of)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              source_path=excluded.source_path,
              content_hash=excluded.content_hash,
              doc_type=excluded.doc_type,
              doc_date=excluded.doc_date,
              indexed_at=excluded.indexed_at,
              duplicate_of=excluded.duplicate_of
            """,
            (
                document_id,
                str(path),
                content_hash,
                loaded.doc_type,
                loaded.doc_date,
                now,
                duplicate_of,
            ),
        )

        if duplicate_of:
            return action

        params = ChunkingParams(
            max_chars=self._config.chunking.max_chars,
            overlap_chars=self._config.chunking.overlap_chars,
            min_chunk_chars=self._config.chunking.min_chunk_chars,
        )
        chunk_texts = split_into_chunks(loaded.content, params)
        if not chunk_texts:
            return action

        ids: list[str] = []
        metadatas: list[dict[str, str | int | None]] = []
        for idx, text in enumerate(chunk_texts):
            chunk_id = f"{document_id}:{idx}"
            ids.append(chunk_id)
            metadata = {
                "document_id": document_id,
                "source": str(path),
                "doc_type": loaded.doc_type,
                "doc_date": loaded.doc_date,
                "chunk_index": idx,
            }
            metadatas.append(metadata)
            self._conn.execute(
                """
                INSERT INTO chunks (id, document_id, chunk_index, text, source, doc_type, doc_date, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (chunk_id, document_id, idx, text, str(path), loaded.doc_type, loaded.doc_date, now),
            )
            self._conn.execute(
                """
                INSERT INTO chunks_fts (chunk_id, text, source, doc_type, doc_date)
                VALUES (?, ?, ?, ?, ?)
                """,
                (chunk_id, text, str(path), loaded.doc_type, loaded.doc_date),
            )

        self._vector_store.upsert_chunks(ids=ids, texts=chunk_texts, metadatas=metadatas)
        return action

    def _delete_document_chunks(self, document_id: str) -> None:
        self._vector_store.delete_by_document(document_id)
        self._conn.execute("DELETE FROM chunks_fts WHERE chunk_id IN (SELECT id FROM chunks WHERE document_id = ?)", (document_id,))
        self._conn.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))
