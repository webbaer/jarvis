from __future__ import annotations

import hashlib
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from jarvis_memory.config import MemoryConfig
from jarvis_memory.ingestion.chunker import ChunkingParams, split_into_chunks
from jarvis_memory.ingestion.loaders import LoaderRegistry
from jarvis_memory.models import IngestResult
from jarvis_memory.store.db import connect, initialize
from jarvis_memory.store.vector_store import ChromaVectorStore


class IngestionPipeline:
    def __init__(
        self,
        config: MemoryConfig,
        vector_store: ChromaVectorStore,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        self._config = config
        self._vector_store = vector_store
        self._loaders = LoaderRegistry()
        self._conn = conn or connect(config.paths.sqlite_path)
        initialize(self._conn)

    def ingest_path(self, path: Path) -> dict[str, int]:
        files = self._collect_files(path)
        stats = {"processed": 0, "skipped": 0, "updated": 0}
        for file_path in files:
            result = self._ingest_file(file_path)
            stats[result.action] += 1
        self._conn.commit()
        return stats

    def ingest_file(
        self,
        path: Path,
        document_id: str | None = None,
        allow_duplicates: bool = True,
        force: bool = False,
    ) -> IngestResult:
        """Ingest a single file and commit.

        allow_duplicates=False: content already indexed under another document is
        reported as action "duplicate" and nothing is written.
        force=True: re-chunk even if the content hash is unchanged.
        """
        try:
            result = self._ingest_file(path, document_id, allow_duplicates, force)
            self._conn.commit()
            return result
        except Exception:
            self._conn.rollback()
            raise

    def reindex_document(self, document_id: str) -> IngestResult:
        row = self._conn.execute(
            "SELECT source_path FROM documents WHERE id = ?",
            (document_id,),
        ).fetchone()
        if row is None:
            raise LookupError(f"Document not found: {document_id}")
        return self.ingest_file(Path(row["source_path"]), force=True)

    def delete_document(self, document_id: str) -> bool:
        row = self._conn.execute("SELECT id FROM documents WHERE id = ?", (document_id,)).fetchone()
        if row is None:
            return False

        dependents = self._conn.execute(
            "SELECT source_path FROM documents WHERE duplicate_of = ?",
            (document_id,),
        ).fetchall()
        try:
            self._delete_document_chunks(document_id)
            self._conn.execute("UPDATE documents SET duplicate_of = NULL WHERE duplicate_of = ?", (document_id,))
            self._conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

        # Former duplicates had no chunks of their own; index them so the content stays searchable.
        for dep in dependents:
            dep_path = Path(dep["source_path"])
            if dep_path.exists():
                self.ingest_file(dep_path, force=True)
        return True

    def _collect_files(self, path: Path) -> list[Path]:
        if path.is_file():
            return [path]
        candidates: list[Path] = []
        for ext in ("*.txt", "*.md", "*.pdf", "*.eml"):
            candidates.extend(path.rglob(ext))
        return sorted({p.resolve() for p in candidates})

    def _ingest_file(
        self,
        path: Path,
        document_id: str | None = None,
        allow_duplicates: bool = True,
        force: bool = False,
    ) -> IngestResult:
        loaded = self._loaders.load_path(path)
        content_hash = hashlib.sha256(loaded.content.encode("utf-8")).hexdigest()
        existing = self._conn.execute(
            "SELECT id, content_hash FROM documents WHERE source_path = ?",
            (str(path),),
        ).fetchone()

        # Only an indexed original (not another duplicate) counts as the canonical copy.
        same_hash_row = self._conn.execute(
            """
            SELECT d.id FROM documents d
            WHERE d.content_hash = ? AND d.source_path != ? AND d.duplicate_of IS NULL
              AND EXISTS (SELECT 1 FROM chunks c WHERE c.document_id = d.id)
            LIMIT 1
            """,
            (content_hash, str(path)),
        ).fetchone()

        now = datetime.now(timezone.utc).isoformat()
        if existing and existing["content_hash"] == content_hash and not force:
            return IngestResult(
                document_id=existing["id"],
                source=str(path),
                action="skipped",
                chunk_count=self._chunk_count(existing["id"]),
            )

        duplicate_of = same_hash_row["id"] if same_hash_row else None
        if duplicate_of and not allow_duplicates and not existing:
            return IngestResult(document_id=None, source=str(path), action="duplicate", duplicate_of=duplicate_of)

        document_id = existing["id"] if existing else (document_id or str(uuid.uuid4()))

        if existing:
            self._delete_document_chunks(document_id)
            action = "updated"
        else:
            action = "processed"

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
            return IngestResult(document_id=document_id, source=str(path), action=action, duplicate_of=duplicate_of)

        params = ChunkingParams(
            max_chars=self._config.chunking.max_chars,
            overlap_chars=self._config.chunking.overlap_chars,
            min_chunk_chars=self._config.chunking.min_chunk_chars,
        )
        chunk_texts = split_into_chunks(loaded.content, params)
        if not chunk_texts:
            return IngestResult(document_id=document_id, source=str(path), action=action)

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
        return IngestResult(document_id=document_id, source=str(path), action=action, chunk_count=len(chunk_texts))

    def _chunk_count(self, document_id: str) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS n FROM chunks WHERE document_id = ?", (document_id,)).fetchone()
        return int(row["n"])

    def _delete_document_chunks(self, document_id: str) -> None:
        self._vector_store.delete_by_document(document_id)
        self._conn.execute("DELETE FROM chunks_fts WHERE chunk_id IN (SELECT id FROM chunks WHERE document_id = ?)", (document_id,))
        self._conn.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))
