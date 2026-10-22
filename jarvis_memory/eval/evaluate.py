from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from jarvis_memory.retrieval.hybrid import HybridRetriever


@dataclass(slots=True)
class EvalCase:
    id: str
    query: str
    expected_sources: list[str]


@dataclass(slots=True)
class EvalCaseResult:
    id: str
    query: str
    expected_sources: list[str]
    # 1-based rank of the first expected source within top k, None if missed.
    rank: int | None
    retrieved_sources: list[str]


@dataclass(slots=True)
class EvalMetrics:
    recall_at_k: float
    mrr: float
    cases: int
    per_case: list[EvalCaseResult] = field(default_factory=list)


def load_eval_cases(path: Path) -> list[EvalCase]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    cases: list[EvalCase] = []
    for item in data.get("cases", []):
        cases.append(
            EvalCase(
                id=str(item["id"]),
                query=str(item["query"]),
                expected_sources=[str(s) for s in item.get("expected_sources", [])],
            )
        )
    return cases


def evaluate(retriever: HybridRetriever, cases: list[EvalCase], k: int) -> EvalMetrics:
    hits = 0
    reciprocal_sum = 0.0
    per_case: list[EvalCaseResult] = []

    for case in cases:
        results = retriever.search(case.query, top_k=k)
        found_rank = _first_match_rank(results, case.expected_sources)
        if found_rank is not None:
            hits += 1
            reciprocal_sum += 1.0 / found_rank
        per_case.append(
            EvalCaseResult(
                id=case.id,
                query=case.query,
                expected_sources=case.expected_sources,
                rank=found_rank,
                retrieved_sources=[r.source for r in results],
            )
        )

    n = len(cases)
    if n == 0:
        return EvalMetrics(recall_at_k=0.0, mrr=0.0, cases=0)

    return EvalMetrics(
        recall_at_k=hits / n,
        mrr=reciprocal_sum / n,
        cases=n,
        per_case=per_case,
    )


def _first_match_rank(results, expected_sources: list[str]) -> int | None:
    wanted = [s.strip() for s in expected_sources if s.strip()]
    for idx, row in enumerate(results, start=1):
        if _source_matches(row.source, wanted):
            return idx
    return None


def _source_matches(actual_source: str, expected_sources: list[str]) -> bool:
    normalized_actual = actual_source.replace("\\", "/")
    for expected in expected_sources:
        normalized_expected = expected.replace("\\", "/")
        if normalized_actual == normalized_expected:
            return True
        if normalized_actual.endswith(normalized_expected):
            return True
    return False
