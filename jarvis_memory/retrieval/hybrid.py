from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from jarvis_memory.config import RetrievalConfig
from jarvis_memory.models import RetrievalResult
from jarvis_memory.retrieval.keyword_retriever import KeywordRetriever
from jarvis_memory.retrieval.reranker import NoopReranker, Reranker
from jarvis_memory.retrieval.vector_retriever import VectorRetriever


@dataclass(slots=True)
class RetrievalFilters:
    source: str | None = None
    doc_type: str | None = None
    date_from: str | None = None
    date_to: str | None = None


class HybridRetriever:
    def __init__(
        self,
        vector_retriever: VectorRetriever,
        keyword_retriever: KeywordRetriever,
        config: RetrievalConfig,
        reranker: Reranker | None = None,
    ) -> None:
        self._vector = vector_retriever
        self._keyword = keyword_retriever
        self._config = config
        self._reranker = reranker or NoopReranker()

    def search(self, query: str, top_k: int | None = None, filters: RetrievalFilters | None = None) -> list[RetrievalResult]:
        f = filters or RetrievalFilters()
        vector_filters = self._build_vector_filters(f)

        vector_res = self._vector.search(
            query=query,
            top_k=self._config.vector_k,
            filters=vector_filters,
        )
        keyword_res = self._keyword.search(
            query=query,
            top_k=self._config.keyword_k,
            source=f.source,
            doc_type=f.doc_type,
            date_from=f.date_from,
            date_to=f.date_to,
        )

        fused = self._rrf_fuse(vector_res, keyword_res, self._config.rrf_k)
        limit = top_k or self._config.top_k

        if self._config.enable_rerank:
            return self._reranker.rerank(query, fused, limit)
        return fused[:limit]

    @staticmethod
    def _build_vector_filters(filters: RetrievalFilters) -> dict[str, Any] | None:
        clauses: list[dict[str, Any]] = []
        if filters.source:
            clauses.append({"source": filters.source})
        if filters.doc_type:
            clauses.append({"doc_type": filters.doc_type})

        if not clauses:
            return None
        if len(clauses) == 1:
            return clauses[0]
        return {"$and": clauses}

    @staticmethod
    def _rrf_fuse(
        vector_results: list[RetrievalResult],
        keyword_results: list[RetrievalResult],
        rrf_k: int,
    ) -> list[RetrievalResult]:
        combined: dict[str, RetrievalResult] = {}
        ranks: dict[str, float] = {}

        for idx, res in enumerate(vector_results, start=1):
            combined.setdefault(res.chunk_id, res)
            ranks[res.chunk_id] = ranks.get(res.chunk_id, 0.0) + 1.0 / (rrf_k + idx)

        for idx, res in enumerate(keyword_results, start=1):
            if res.chunk_id in combined:
                existing = combined[res.chunk_id]
                existing.keyword_rank = idx
            else:
                combined[res.chunk_id] = res
            ranks[res.chunk_id] = ranks.get(res.chunk_id, 0.0) + 1.0 / (rrf_k + idx)

        for chunk_id, score in ranks.items():
            combined[chunk_id].score = score

        return sorted(combined.values(), key=lambda item: item.score, reverse=True)
