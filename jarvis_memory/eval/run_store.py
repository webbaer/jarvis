from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from jarvis_memory.eval.evaluate import EvalCaseResult, EvalMetrics


@dataclass(slots=True)
class EvalRun:
    id: int
    created_at: str
    k: int
    cases: int
    recall_at_k: float
    mrr: float
    dataset: str
    config: dict[str, Any]
    per_case: list[EvalCaseResult]


class EvalRunStore:
    """Persists eval runs so results can be compared over time."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def save(self, metrics: EvalMetrics, k: int, dataset: str, config: dict[str, Any]) -> EvalRun:
        now = datetime.now(timezone.utc).isoformat()
        cur = self._conn.execute(
            """
            INSERT INTO eval_runs (created_at, k, cases, recall_at_k, mrr, dataset, config_json, per_case_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now,
                k,
                metrics.cases,
                metrics.recall_at_k,
                metrics.mrr,
                dataset,
                json.dumps(config, default=str),
                json.dumps([asdict(c) for c in metrics.per_case]),
            ),
        )
        self._conn.commit()
        run = self.get_run(int(cur.lastrowid))
        assert run is not None
        return run

    def get_run(self, run_id: int) -> EvalRun | None:
        row = self._conn.execute("SELECT * FROM eval_runs WHERE id = ?", (run_id,)).fetchone()
        return self._to_run(row) if row else None

    def list_runs(self) -> list[EvalRun]:
        rows = self._conn.execute("SELECT * FROM eval_runs ORDER BY created_at DESC, id DESC").fetchall()
        return [self._to_run(r) for r in rows]

    @staticmethod
    def _to_run(row: sqlite3.Row) -> EvalRun:
        return EvalRun(
            id=int(row["id"]),
            created_at=str(row["created_at"]),
            k=int(row["k"]),
            cases=int(row["cases"]),
            recall_at_k=float(row["recall_at_k"]),
            mrr=float(row["mrr"]),
            dataset=str(row["dataset"]),
            config=json.loads(row["config_json"]),
            per_case=[EvalCaseResult(**c) for c in json.loads(row["per_case_json"])],
        )
