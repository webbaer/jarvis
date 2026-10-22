from jarvis_memory.eval.evaluate import EvalCase, evaluate
from jarvis_memory.models import RetrievalResult


class DummyRetriever:
    def __init__(self, rows_by_query: dict[str, list[RetrievalResult]]) -> None:
        self._rows_by_query = rows_by_query

    def search(self, query: str, top_k: int, filters=None):
        _ = (top_k, filters)
        return self._rows_by_query.get(query, [])


def test_eval_metrics_recall_and_mrr() -> None:
    retriever = DummyRetriever(
        {
            "q1": [RetrievalResult("a", "", "s1", "text", None, 0.9)],
            "q2": [
                RetrievalResult("b", "", "x", "text", None, 0.8),
                RetrievalResult("c", "", "s2", "text", None, 0.7),
            ],
            "q3": [RetrievalResult("d", "", "x", "text", None, 0.6)],
        }
    )

    cases = [
        EvalCase(id="1", query="q1", expected_sources=["s1"]),
        EvalCase(id="2", query="q2", expected_sources=["s2"]),
        EvalCase(id="3", query="q3", expected_sources=["s3"]),
    ]

    metrics = evaluate(retriever, cases, k=3)

    assert metrics.cases == 3
    assert metrics.recall_at_k == 2 / 3
    assert metrics.mrr == (1.0 + 0.5 + 0.0) / 3
