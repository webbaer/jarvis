from pathlib import Path

from jarvis_memory.store.db import connect, initialize
from jarvis_memory.store.fact_store import FactStore


def _make_store(tmp_path: Path) -> FactStore:
    conn = connect(tmp_path / "memory.sqlite3")
    initialize(conn)
    return FactStore(conn)


def test_add_fact_supersedes_old_value(tmp_path: Path) -> None:
    store = _make_store(tmp_path)

    store.add_fact("Fabian", "address", "Musterweg 1", "mail")
    store.add_fact("Fabian", "address", "Musterweg 2", "bank")

    current = store.get_current_facts("Fabian")
    history = store.get_fact_history("Fabian", "address")

    assert len(current) == 1
    assert current[0].value == "Musterweg 2"
    assert len(history) == 2
    assert history[0].status == "superseded"
    assert history[0].valid_to is not None
    assert history[1].status == "active"


def test_update_fact_creates_new_active_version(tmp_path: Path) -> None:
    store = _make_store(tmp_path)

    fact_id = store.add_fact("Fabian", "city", "Berlin", "note")
    new_id = store.update_fact(fact_id, "Hamburg", "calendar")

    assert new_id != fact_id
    current = store.get_current_facts("Fabian")
    assert len(current) == 1
    assert current[0].value == "Hamburg"
