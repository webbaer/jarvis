# Synthetic content only, no real personal data.
DOCS = {
    "tutorium.md": "Das Statistik-Tutorium findet donnerstags um 14 Uhr im Seminarraum 3 statt.",
    "kochen.md": "Rezeptidee: Linsencurry mit Kokosmilch, dazu Reis. Vorbereitung dauert zwanzig Minuten.",
    "sport.txt": "Lauftraining am Samstag im Stadtpark, Treffpunkt am Brunnen, Dauer eine Stunde.",
}


def _ingest_all(client) -> dict[str, str]:
    files = [("files", (name, text.encode(), "text/plain")) for name, text in DOCS.items()]
    items = client.post("/ingest", files=files).json()
    return {i["filename"]: i["document_id"] for i in items}


def test_query_returns_separate_lists_and_context(api_client) -> None:
    ids = _ingest_all(api_client)

    response = api_client.post("/query", json={"query": "Wann ist das Statistik Tutorium?", "top_k": 2})
    assert response.status_code == 200
    body = response.json()

    assert body["vector_hits"] and body["keyword_hits"]
    assert len(body["fused_hits"]) == 2
    assert [h["fused_rank"] for h in body["fused_hits"]] == [1, 2]

    top = body["fused_hits"][0]
    assert top["document_id"] == ids["tutorium.md"]
    assert top["vector_score"] is not None and top["keyword_score"] is not None
    assert 0 < top["keyword_score"] < 1
    assert all(h["vector_score"] is not None for h in body["vector_hits"])

    assert body["context"].startswith("[FACTS]")
    assert "[RETRIEVED_CHUNKS]" in body["context"]
    assert "Seminarraum 3" in body["context"]


def test_query_filters_by_doc_type(api_client) -> None:
    _ingest_all(api_client)
    body = api_client.post(
        "/query", json={"query": "Treffpunkt Stadtpark Tutorium", "filters": {"doc_type": "text"}}
    ).json()
    assert body["fused_hits"]
    assert {h["doc_type"] for h in body["fused_hits"]} == {"text"}


def test_query_validates_input(api_client) -> None:
    assert api_client.post("/query", json={"query": ""}).status_code == 422
    assert api_client.post("/query", json={"query": "x", "top_k": 0}).status_code == 422
    assert api_client.post("/query", json={"query": "x", "top_k": 10_000}).status_code == 422


def test_query_on_empty_store(api_client) -> None:
    body = api_client.post("/query", json={"query": "irgendwas"}).json()
    assert body["fused_hits"] == []


def test_locate_reports_rank_outside_top_k(api_client) -> None:
    ids = _ingest_all(api_client)
    response = api_client.post(
        "/query/locate",
        json={"query": "Statistik Tutorium Seminarraum", "document_id": ids["kochen.md"], "top_k": 1},
    )
    assert response.status_code == 200
    locations = response.json()
    assert len(locations) == 1
    loc = locations[0]
    assert loc["in_top_k"] is False
    assert loc["fused_rank"] is None
    # Found by the deeper vector search even though it is not in the top 1.
    assert loc["vector_rank"] is not None and loc["vector_rank"] > 1
    assert loc["deep_fused_rank"] is not None


def test_locate_unknown_document_or_chunk(api_client) -> None:
    ids = _ingest_all(api_client)
    assert api_client.post("/query/locate", json={"query": "x", "document_id": "nope"}).status_code == 404
    response = api_client.post(
        "/query/locate", json={"query": "x", "document_id": ids["sport.txt"], "chunk_id": "nope:0"}
    )
    assert response.status_code == 404
