from jarvis_memory.config import MemoryConfig

# Synthetic content only, no real personal data.
FACT = {"subject": "Testperson", "attribute": "lieblingsfarbe", "value": "blau", "source": "notiz.md"}


def test_fact_versioning_keeps_history(api_client) -> None:
    created = api_client.post("/facts", json=FACT)
    assert created.status_code == 201
    first = created.json()
    assert first["status"] == "active"

    updated = api_client.put(f"/facts/{first['id']}", json={"value": "gruen", "source": "kalender"})
    assert updated.status_code == 200
    second = updated.json()
    assert second["id"] != first["id"]
    assert second["value"] == "gruen"
    assert second["status"] == "active"

    current = api_client.get("/facts").json()
    assert [f["value"] for f in current] == ["gruen"]

    all_facts = api_client.get("/facts", params={"include_superseded": True}).json()
    assert {(f["value"], f["status"]) for f in all_facts} == {("blau", "superseded"), ("gruen", "active")}

    history = api_client.get(f"/facts/{first['id']}/history").json()
    assert [f["value"] for f in history] == ["blau", "gruen"]
    assert history[0]["status"] == "superseded"
    assert history[0]["valid_to"] is not None


def test_posting_same_subject_attribute_supersedes(api_client) -> None:
    api_client.post("/facts", json=FACT)
    api_client.post("/facts", json={**FACT, "value": "rot"})
    current = api_client.get("/facts").json()
    assert [f["value"] for f in current] == ["rot"]


def test_update_superseded_fact_is_conflict(api_client) -> None:
    first = api_client.post("/facts", json=FACT).json()
    api_client.put(f"/facts/{first['id']}", json={"value": "gruen", "source": "x"})
    response = api_client.put(f"/facts/{first['id']}", json={"value": "gelb", "source": "x"})
    assert response.status_code == 409


def test_fact_errors(api_client) -> None:
    assert api_client.put("/facts/999", json={"value": "x", "source": "y"}).status_code == 404
    assert api_client.get("/facts/999/history").status_code == 404
    assert api_client.post("/facts", json={**FACT, "value": ""}).status_code == 422


def test_facts_appear_in_query_context(api_client) -> None:
    api_client.post("/facts", json=FACT)
    context = api_client.post("/query", json={"query": "Farbe"}).json()["context"]
    assert "Testperson.lieblingsfarbe: blau" in context


def test_eval_run_is_stored_with_config(api_client, memory_config: MemoryConfig) -> None:
    memory_config.paths.eval_dataset_path.write_text(
        "cases:\n"
        "  - id: t1\n"
        "    query: Statistik Tutorium\n"
        "    expected_sources: [tutorium.md]\n"
        "  - id: t2\n"
        "    query: Linsencurry\n"
        "    expected_sources: [gibt-es-nicht.md]\n",
        encoding="utf-8",
    )
    files = [("files", ("tutorium.md", b"Das Statistik-Tutorium ist donnerstags.", "text/markdown"))]
    api_client.post("/ingest", files=files)

    response = api_client.post("/eval/run", json={"k": 3})
    assert response.status_code == 200
    run = response.json()
    assert run["k"] == 3
    assert run["cases"] == 2
    assert run["recall_at_k"] == 0.5
    assert run["mrr"] == 0.5
    assert run["config"]["retrieval"]["rrf_k"] == memory_config.retrieval.rrf_k
    assert [c["rank"] for c in run["per_case"]] == [1, None]

    api_client.post("/eval/run", json={"k": 1})
    results = api_client.get("/eval/results").json()
    assert [r["k"] for r in results] == [1, 3]
    assert all(r["created_at"] for r in results)


def test_eval_without_dataset_is_conflict(api_client) -> None:
    response = api_client.post("/eval/run", json={})
    assert response.status_code == 409
    assert "nicht gefunden" in response.json()["detail"]
