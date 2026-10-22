"""Renders the Streamlit app against a live API on a free local port."""
import socket
import threading
import time
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
uvicorn = pytest.importorskip("uvicorn")

from streamlit.testing.v1 import AppTest  # noqa: E402

from api.main import create_app  # noqa: E402

APP_PATH = str(Path(__file__).resolve().parent.parent / "ui" / "app.py")
APP_TIMEOUT_S = 30


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def live_api(memory_config, monkeypatch):
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(create_app(memory_config), host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    url = f"http://127.0.0.1:{port}"
    monkeypatch.setenv("JARVIS_API_URL", url)
    yield url
    server.should_exit = True
    thread.join(timeout=5)


def _all_text(at: AppTest) -> str:
    parts = [e.value for e in (*at.markdown, *at.caption, *at.info, *at.warning, *at.error, *at.success)]
    return "\n".join(str(p) for p in parts)


def test_ui_shows_error_when_api_unreachable(monkeypatch) -> None:
    monkeypatch.setenv("JARVIS_API_URL", f"http://127.0.0.1:{_free_port()}")
    at = AppTest.from_file(APP_PATH, default_timeout=APP_TIMEOUT_S).run()
    assert not at.exception
    assert any("API nicht erreichbar" in e.value for e in at.error)


def test_ui_renders_all_views_with_data(live_api) -> None:
    import httpx

    note = b"Projekt Nordlicht trifft sich jeden Dienstag im Raum B12.\n\nTagesordnung: Statusberichte."
    httpx.post(f"{live_api}/ingest", files=[("files", ("nordlicht.md", note, "text/markdown"))]).raise_for_status()
    httpx.post(
        f"{live_api}/facts",
        json={"subject": "Team", "attribute": "raum", "value": "B12", "source": "test"},
    ).raise_for_status()

    at = AppTest.from_file(APP_PATH, default_timeout=APP_TIMEOUT_S).run()

    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]
    assert any("API erreichbar" in s.value for s in at.success)
    assert len(at.tabs) == 4
    tables = [df.value for df in at.dataframe]
    assert any("nordlicht.md" in str(t.to_dict()) for t in tables)


def _button(at: AppTest, label: str):
    return next(b for b in at.button if b.label == label)


def test_ui_query_inspector_and_eval_interactions(live_api, memory_config) -> None:
    import httpx

    note = b"Projekt Nordlicht trifft sich jeden Dienstag im Raum B12.\n\nTagesordnung: Statusberichte."
    httpx.post(f"{live_api}/ingest", files=[("files", ("nordlicht.md", note, "text/markdown"))]).raise_for_status()
    memory_config.paths.eval_dataset_path.write_text(
        "cases:\n  - id: t1\n    query: Nordlicht Dienstag\n    expected_sources: [nordlicht.md]\n", encoding="utf-8"
    )

    at = AppTest.from_file(APP_PATH, default_timeout=APP_TIMEOUT_S).run()
    at.text_input(key="qi_query").set_value("Wann trifft sich Nordlicht?").run()
    _button(at, "Suchen").click().run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]
    assert any("[RETRIEVED_CHUNKS]" in c.value for c in at.code)

    _button(at, "Rang ermitteln").click().run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]

    _button(at, "Eval-Lauf starten").click().run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]
    assert any(m.label == "Recall@6" for m in at.metric)


def test_ui_does_not_import_memory_module() -> None:
    import re

    pattern = re.compile(r"^\s*(from|import)\s+(jarvis_memory|api)\b", re.MULTILINE)
    ui_dir = Path(APP_PATH).parent
    offenders = [p.name for p in ui_dir.rglob("*.py") if pattern.search(p.read_text(encoding="utf-8"))]
    assert offenders == []
