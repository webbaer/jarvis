from __future__ import annotations

import re
import sqlite3

from jarvis_memory.models import RetrievalResult


class KeywordRetriever:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def search(
        self,
        query: str,
        top_k: int,
        source: str | None = None,
        doc_type: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[RetrievalResult]:
        fts_query = _to_fts_query(query)
        if not fts_query:
            return []

        sql = """
        SELECT c.id AS chunk_id, c.document_id, c.text, c.source, c.doc_type, c.doc_date,
               bm25(chunks_fts) AS rank_score
        FROM chunks_fts
        JOIN chunks c ON c.id = chunks_fts.chunk_id
        WHERE chunks_fts MATCH ?
        """
        params: list[object] = [fts_query]

        if source:
            sql += " AND c.source = ?"
            params.append(source)
        if doc_type:
            sql += " AND c.doc_type = ?"
            params.append(doc_type)
        if date_from:
            sql += " AND (c.doc_date IS NULL OR c.doc_date >= ?)"
            params.append(date_from)
        if date_to:
            sql += " AND (c.doc_date IS NULL OR c.doc_date <= ?)"
            params.append(date_to)

        sql += " ORDER BY rank_score ASC LIMIT ?"
        params.append(top_k)

        rows = self._conn.execute(sql, params).fetchall()
        results: list[RetrievalResult] = []
        for idx, row in enumerate(rows, start=1):
            # FTS5 bm25() is negative, more negative = better. Map relevance to [0, 1), higher = better.
            relevance = max(0.0, -float(row["rank_score"]))
            score = relevance / (1.0 + relevance)
            results.append(
                RetrievalResult(
                    chunk_id=str(row["chunk_id"]),
                    text=str(row["text"]),
                    source=str(row["source"]),
                    doc_type=str(row["doc_type"]),
                    doc_date=row["doc_date"],
                    score=score,
                    keyword_rank=idx,
                    keyword_score=score,
                    document_id=str(row["document_id"]),
                )
            )
        return results


def _to_fts_query(query: str) -> str:
    tokens = re.findall(r"[A-Za-z0-9_]+", query.lower())
    if not tokens:
        return ""
    return " OR ".join(tokens)
