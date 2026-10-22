from __future__ import annotations

import sqlite3
from typing import Any

from jarvis_memory.models import RetrievalResult
from jarvis_memory.store.vector_store import ChromaVectorStore


class VectorRetriever:
    def __init__(self, conn: sqlite3.Connection, vector_store: ChromaVectorStore) -> None:
        self._conn = conn
        self._vector_store = vector_store

    def search(
        self,
        query: str,
        top_k: int,
        filters: dict[str, Any] | None = None,
    ) -> list[RetrievalResult]:
        raw = self._vector_store.query(query=query, top_k=top_k, filters=filters)
        results: list[RetrievalResult] = []
        for item in raw:
            meta = item["metadata"]
            distance = float(item["distance"])
            score = 1.0 / (1.0 + distance)
            results.append(
                RetrievalResult(
                    chunk_id=item["chunk_id"],
                    text=item["text"],
                    source=meta["source"],
                    doc_type=meta["doc_type"],
                    doc_date=meta.get("doc_date"),
                    score=score,
                    vector_rank=item["rank"],
                )
            )
        return results
