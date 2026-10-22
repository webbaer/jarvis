from __future__ import annotations

import sqlite3
from pathlib import Path

from jarvis_memory.models import ChunkInfo, DocumentInfo


class DocumentStore:
    """Read-only views on indexed documents and chunks. Writes go through IngestionPipeline."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def list_documents(self) -> list[DocumentInfo]:
        rows = self._conn.execute(
            """
            SELECT d.*, (SELECT COUNT(*) FROM chunks c WHERE c.document_id = d.id) AS chunk_count
            FROM documents d
            ORDER BY d.indexed_at DESC
            """
        ).fetchall()
        return [self._to_document(r) for r in rows]

    def get_document(self, document_id: str) -> DocumentInfo | None:
        row = self._conn.execute(
            """
            SELECT d.*, (SELECT COUNT(*) FROM chunks c WHERE c.document_id = d.id) AS chunk_count
            FROM documents d
            WHERE d.id = ?
            """,
            (document_id,),
        ).fetchone()
        return self._to_document(row) if row else None

    def get_chunks(self, document_id: str) -> list[ChunkInfo]:
        rows = self._conn.execute(
            "SELECT * FROM chunks WHERE document_id = ? ORDER BY chunk_index ASC",
            (document_id,),
        ).fetchall()
        return [
            ChunkInfo(
                id=str(r["id"]),
                document_id=str(r["document_id"]),
                chunk_index=int(r["chunk_index"]),
                text=str(r["text"]),
                source=str(r["source"]),
                doc_type=str(r["doc_type"]),
                doc_date=r["doc_date"],
                created_at=str(r["created_at"]),
            )
            for r in rows
        ]

    @staticmethod
    def _to_document(row: sqlite3.Row) -> DocumentInfo:
        return DocumentInfo(
            id=str(row["id"]),
            source_path=str(row["source_path"]),
            name=Path(str(row["source_path"])).name,
            doc_type=str(row["doc_type"]),
            doc_date=row["doc_date"],
            content_hash=str(row["content_hash"]),
            indexed_at=str(row["indexed_at"]),
            duplicate_of=row["duplicate_of"],
            chunk_count=int(row["chunk_count"]),
        )
