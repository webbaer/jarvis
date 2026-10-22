from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from jarvis_memory.models import FactRecord


class FactStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def add_fact(
        self,
        subject: str,
        attribute: str,
        value: str,
        source: str,
        valid_from: str | None = None,
    ) -> int:
        now = datetime.now(timezone.utc).isoformat()
        start = valid_from or now

        current = self._conn.execute(
            """
            SELECT id, value FROM facts
            WHERE subject = ? AND attribute = ? AND status = 'active' AND valid_to IS NULL
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (subject, attribute),
        ).fetchone()

        if current and current["value"] == value:
            return int(current["id"])

        if current:
            self._conn.execute(
                """
                UPDATE facts
                SET valid_to = ?, status = 'superseded'
                WHERE id = ?
                """,
                (start, int(current["id"])),
            )

        cur = self._conn.execute(
            """
            INSERT INTO facts (subject, attribute, value, source, valid_from, valid_to, status, created_at)
            VALUES (?, ?, ?, ?, ?, NULL, 'active', ?)
            """,
            (subject, attribute, value, source, start, now),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def update_fact(
        self,
        fact_id: int,
        new_value: str,
        source: str,
        valid_from: str | None = None,
    ) -> int:
        row = self._conn.execute(
            "SELECT subject, attribute FROM facts WHERE id = ?",
            (fact_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Fact id not found: {fact_id}")
        return self.add_fact(
            subject=row["subject"],
            attribute=row["attribute"],
            value=new_value,
            source=source,
            valid_from=valid_from,
        )

    def get_current_facts(self, subject: str | None = None) -> list[FactRecord]:
        if subject:
            rows = self._conn.execute(
                """
                SELECT * FROM facts
                WHERE status = 'active' AND valid_to IS NULL AND subject = ?
                ORDER BY subject, attribute
                """,
                (subject,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT * FROM facts
                WHERE status = 'active' AND valid_to IS NULL
                ORDER BY subject, attribute
                """
            ).fetchall()
        return [self._to_fact_record(r) for r in rows]

    def get_fact(self, fact_id: int) -> FactRecord | None:
        row = self._conn.execute("SELECT * FROM facts WHERE id = ?", (fact_id,)).fetchone()
        return self._to_fact_record(row) if row else None

    def get_all_facts(self) -> list[FactRecord]:
        rows = self._conn.execute(
            "SELECT * FROM facts ORDER BY subject, attribute, valid_from ASC, created_at ASC"
        ).fetchall()
        return [self._to_fact_record(r) for r in rows]

    def get_fact_history(self, subject: str, attribute: str) -> list[FactRecord]:
        rows = self._conn.execute(
            """
            SELECT * FROM facts
            WHERE subject = ? AND attribute = ?
            ORDER BY valid_from ASC, created_at ASC
            """,
            (subject, attribute),
        ).fetchall()
        return [self._to_fact_record(r) for r in rows]

    @staticmethod
    def _to_fact_record(row: sqlite3.Row) -> FactRecord:
        return FactRecord(
            id=int(row["id"]),
            subject=str(row["subject"]),
            attribute=str(row["attribute"]),
            value=str(row["value"]),
            source=str(row["source"]),
            valid_from=str(row["valid_from"]),
            valid_to=row["valid_to"],
            status=str(row["status"]),
            created_at=str(row["created_at"]),
        )
