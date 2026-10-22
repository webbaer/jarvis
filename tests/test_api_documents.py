from pathlib import Path

from jarvis_memory.config import MemoryConfig

# Synthetic content only, no real personal data.
NOTE = (
    "Projekt Nordlicht trifft sich jeden Dienstag im Raum B12.\n\n"
    "Die Tagesordnung umfasst Statusberichte und offene Punkte zum Prototyp.\n\n"
    "Protokoll fuehrt abwechselnd ein Teammitglied, Ablage im Projektordner."
)


def _upload(client, *files: tuple[str, bytes]):
    payload = [("files", (name, data, "application/octet-stream")) for name, data in files]
    return client.post("/ingest", files=payload)


def _upload_ok(client, name: str = "nordlicht.md", data: bytes = NOTE.encode()) -> dict:
    response = _upload(client, (name, data))
    assert response.status_code == 202
    item = response.json()[0]
    assert item["status"] == "queued", item
    return item


def test_health(api_client) -> None:
    response = api_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "documents": 0, "chunks": 0, "facts": 0}


def test_upload_indexes_document(api_client) -> None:
    item = _upload_ok(api_client)

    job = api_client.get(f"/ingest/{item['job_id']}").json()
    assert job["status"] == "indexed"
    assert job["chunk_count"] > 0

    docs = api_client.get("/documents").json()
    assert len(docs) == 1
    assert docs[0]["id"] == item["document_id"]
    assert docs[0]["name"] == "nordlicht.md"
    assert docs[0]["doc_type"] == "markdown"
    assert docs[0]["chunk_count"] == job["chunk_count"]
    assert len(docs[0]["content_hash"]) == 64


def test_duplicate_upload_is_reported_not_indexed(api_client, memory_config: MemoryConfig) -> None:
    first = _upload_ok(api_client)
    second = _upload_ok(api_client, name="kopie.md")

    job = api_client.get(f"/ingest/{second['job_id']}").json()
    assert job["status"] == "duplicate"
    assert job["duplicate_of"] == first["document_id"]

    assert len(api_client.get("/documents").json()) == 1
    stored = [p.name for p in memory_config.paths.uploads_dir.rglob("*") if p.is_file()]
    assert stored == ["nordlicht.md"]


def test_rejects_bad_uploads(api_client, memory_config: MemoryConfig) -> None:
    memory_config.upload.max_file_bytes = 1024
    response = _upload(
        api_client,
        ("tool.exe", b"MZ\x90\x00"),
        ("fake.pdf", b"kein pdf"),
        ("binary.txt", b"abc\x00def"),
        ("latin1.txt", "Grüße".encode("latin-1")),
        ("mail.eml", b"nur text ohne header"),
        ("gross.txt", b"x" * 2048),
        ("leer.md", b""),
    )
    assert response.status_code == 202
    items = response.json()
    assert [i["status"] for i in items] == ["rejected"] * 7
    assert all(i["error"] for i in items)
    assert not any(p.is_file() for p in memory_config.paths.uploads_dir.rglob("*"))


def test_filename_is_sanitized(api_client, memory_config: MemoryConfig) -> None:
    item = _upload_ok(api_client, name="../../etc/Über Notiz!.md")
    assert item["filename"] == "Uber_Notiz_.md"
    stored = [p for p in memory_config.paths.uploads_dir.rglob("*") if p.is_file()]
    assert len(stored) == 1
    assert stored[0].resolve().is_relative_to(memory_config.paths.uploads_dir.resolve())


def test_accepts_eml_and_pdf_signature(api_client) -> None:
    eml = b"Subject: Testtermin\nFrom: team@example.com\n\nTreffen am Freitag um 10 Uhr."
    response = _upload(api_client, ("termin.eml", eml))
    assert response.json()[0]["status"] == "queued"


def test_chunks_endpoint_reports_overlap_and_stats(api_client) -> None:
    item = _upload_ok(api_client)
    body = api_client.get(f"/documents/{item['document_id']}/chunks").json()

    chunks = body["chunks"]
    assert body["stats"]["count"] == len(chunks) >= 2
    assert [c["chunk_index"] for c in chunks] == list(range(len(chunks)))
    assert chunks[0]["overlap_chars"] == 0
    assert any(c["overlap_chars"] > 0 for c in chunks[1:])
    assert all(c["length"] == len(c["text"]) for c in chunks)


def test_delete_removes_document_chunks_and_file(api_client, memory_config: MemoryConfig) -> None:
    item = _upload_ok(api_client)
    doc_id = item["document_id"]

    assert api_client.delete(f"/documents/{doc_id}").status_code == 204
    assert api_client.get("/documents").json() == []
    assert api_client.get(f"/documents/{doc_id}/chunks").status_code == 404
    assert api_client.get("/health").json()["chunks"] == 0
    assert not any(p.is_file() for p in memory_config.paths.uploads_dir.rglob("*"))
    assert api_client.delete(f"/documents/{doc_id}").status_code == 404


def test_reindex_keeps_document_id(api_client) -> None:
    item = _upload_ok(api_client)
    response = api_client.post(f"/documents/{item['document_id']}/reindex")
    assert response.status_code == 200
    body = response.json()
    assert body["document_id"] == item["document_id"]
    assert body["action"] == "updated"
    assert body["chunk_count"] > 0
    assert api_client.post("/documents/unbekannt/reindex").status_code == 404


def test_reindex_missing_source_is_conflict(api_client, memory_config: MemoryConfig) -> None:
    item = _upload_ok(api_client)
    for path in memory_config.paths.uploads_dir.rglob("*.md"):
        Path(path).unlink()
    assert api_client.post(f"/documents/{item['document_id']}/reindex").status_code == 409


def test_unknown_job_is_404(api_client) -> None:
    assert api_client.get("/ingest/does-not-exist").status_code == 404
