from __future__ import annotations

from typing import Protocol

from jarvis_memory.models import RetrievalResult


class Reranker(Protocol):
    def rerank(self, query: str, results: list[RetrievalResult], top_k: int) -> list[RetrievalResult]:
        ...


class NoopReranker:
    def rerank(self, query: str, results: list[RetrievalResult], top_k: int) -> list[RetrievalResult]:
        _ = query
        return sorted(results, key=lambda r: r.score, reverse=True)[:top_k]
