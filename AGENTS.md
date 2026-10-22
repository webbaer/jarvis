# Regeln fuer Coding-Agents

Gilt fuer alle KI-Agents (Claude Code, Codex, Cursor, ...) in diesem Repo. Technische Durchsetzung: [.claude/settings.json](.claude/settings.json) und [.claude/hooks/](.claude/hooks/).

## Projekt in einem Satz

Lokales RAG-/Gedaechtnismodul fuer Jarvis: Ingestion (md/txt/pdf/eml) → SQLite (+FTS5) und ChromaDB → hybrides Retrieval (RRF) → Kontextblock. Kein LLM, keine Cloud-APIs. Details: [README.md](README.md).

## Setup und Checks

```bash
source .venv/bin/activate
make install                 # pip install -e '.[dev,api,ui]'
python -m pytest -q          # muss vor jedem Abschluss gruen sein (make test)
jarvis-memory eval --k 6     # bei Aenderungen an Chunking/Retrieval vorher/nachher vergleichen
```

## Harte Regeln

1. **Lokal bleiben.** Keine Cloud-APIs, keine Telemetrie, keine neuen Netzwerkaufrufe. Einzige erlaubte Ausnahme ist der bestehende Ollama-Endpoint auf localhost.
2. **Keine neuen Abhaengigkeiten ohne Rueckfrage.** Wenn noetig: in `pyproject.toml` eintragen, nie ad-hoc per `pip install <paket>`.
3. **Runtime-State nicht anfassen.** `.jarvis_memory/` (SQLite + Chroma), `.venv/`, `*.egg-info/`, `__pycache__/` nie editieren oder loeschen. Tests benutzen `tmp_path` und eine eigene `MemoryConfig`, nie den echten Store.
4. **Persoenliche Daten.** `data/` enthaelt (Dummy-)Profil-, Gesundheits- und Reisedaten. Keine echten personenbezogenen Daten in Code, Tests, Commits oder Logs. Testdaten sind synthetisch.
5. **Schema-Aenderungen** an `store/db.py` muessen mit bestehenden Datenbanken kompatibel bleiben (`CREATE ... IF NOT EXISTS`, additive Spalten). Breaking Changes nur mit Migrationspfad und nach Rueckfrage.
6. **Fakten-Semantik bewahren.** `FactStore` loescht nie, sondern setzt `status='superseded'` und `valid_to`. Die Historie muss erhalten bleiben.
7. **SQL nur parametrisiert** (`?`-Platzhalter). Keine f-Strings oder String-Konkatenation mit Nutzereingaben.
8. **Git:** Arbeit auf Feature-Branches von `dev`. Kein Push auf `main`, kein Force-Push, kein `reset --hard`/`clean -f`, kein `--no-verify`. Committen und pushen nur auf Aufforderung.

## Schichten

- `jarvis_memory/` enthaelt die gesamte Logik. Neue Faehigkeiten kommen hierher, nach aussen ueber `jarvis_memory/service.py` (`MemoryService`).
- `api/` ist eine duenne HTTP-Schicht: Validierung, Statuscodes, Upload-Pruefung, Job-Tracking. Keine Pipeline-Logik kopieren.
- `ui/` spricht nur HTTP mit der API (`ui/client.py`) und importiert weder `jarvis_memory` noch `api` (Test: `tests/test_ui_smoke.py`).
- Server binden nur an `127.0.0.1`; keine Telemetrie, kein CORS, keine Auth-Attrappen.

## Konventionen

- Python >= 3.11, `from __future__ import annotations` am Dateianfang, Typannotationen ueberall.
- Datenklassen mit `@dataclass(slots=True)`; Konfiguration nur ueber `config.py`, keine Magic Numbers in der Logik.
- Neue Loader: `BaseLoader` implementieren und in `LoaderRegistry` registrieren; Dateiendung auch in `IngestionPipeline._collect_files` ergaenzen.
- Neue Embedder/Reranker: bestehende Interfaces (`Embedder`, `Reranker`-Protocol) nutzen und in `app.py` verdrahten.
- Jede Verhaltensaenderung bekommt einen Test in `tests/`. Externe Abhaengigkeiten (Chroma, Ollama) per Dummy ersetzen, wie in `tests/test_ingestion_mvp.py`.
- Doku (README) ist auf Deutsch ohne Umlaute; Code und Bezeichner auf Englisch.

## Vor dem Abschluss

- [ ] `python -m pytest -q` gruen (wird vom Stop-Hook erzwungen)
- [ ] Bei Retrieval-Aenderungen: `jarvis-memory eval` vorher/nachher genannt
- [ ] README angepasst, falls sich CLI, Config oder Features geaendert haben
- [ ] Keine Dateien aus `.jarvis_memory/`, `__pycache__/` o. ae. im Diff
