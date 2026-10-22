from jarvis_memory.config import RetrievalConfig
from jarvis_memory.models import RetrievalResult
from jarvis_memory.retrieval.hybrid import HybridRetriever


class DummyVector:
    def search(self, query: str, top_k: int, filters=None):
        _ = (query, top_k, filters)
        return [
            RetrievalResult("a", "A", "s1", "text", None, 0.8, vector_rank=1),
            RetrievalResult("b", "B", "s1", "text", None, 0.7, vector_rank=2),
        ]


class DummyKeyword:
    def search(self, query: str, top_k: int, source=None, doc_type=None, date_from=None, date_to=None):
        _ = (query, top_k, source, doc_type, date_from, date_to)
        return [
            RetrievalResult("b", "B", "s1", "text", None, 0.9, keyword_rank=1),
            RetrievalResult("c", "C", "s2", "text", None, 0.6, keyword_rank=2),
        ]


def test_rrf_merges_and_ranks_results() -> None:
    cfg = RetrievalConfig(top_k=3, vector_k=3, keyword_k=3, rrf_k=60, enable_rerank=False)
    retriever = HybridRetriever(DummyVector(), DummyKeyword(), cfg)

    results = retriever.search("test")

    ids = [r.chunk_id for r in results]
    assert set(ids) == {"a", "b", "c"}
    assert ids[0] == "b"
