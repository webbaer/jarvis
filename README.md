# Jarvis Memory

Lokales, modulares RAG-/Gedaechtnissystem fuer Jarvis (Single-User Assistant).

## Warum ChromaDB?

Ich habe ChromaDB als Vektor-DB gewaehlt, weil sie lokal persistent, einfach in Python integrierbar und fuer kleine bis mittlere persoenliche Wissensbestaende sehr pragmatisch ist. Fuer strukturierte Fakten und Keyword-Suche wird SQLite (inkl. FTS5) verwendet.

## Features

- Ingestion fuer md/txt/pdf/eml ueber Loader-Interface
- Absatzorientiertes Chunking mit konfigurierbarer Chunk-Groesse und Overlap
- Duplikat-Erkennung per Content-Hash
- Re-Indexing nur bei geaenderten Dateien
- Fakten-Gedaechtnis mit Versionierung und Historie
- Hybrides Retrieval (Vektor + FTS5-Keyword) mit RRF-Fusion
- Optionaler Rerank-Hook (abschaltbar)
- Kontext-Builder mit Zeichenbudget
- Evaluation mit Recall@k und MRR
- Pytest-Tests fuer Chunking, Fakten, Retrieval, Eval

## Projektstruktur

- jarvis_memory/ingestion: Loader + Chunker + Ingestion-Pipeline
- jarvis_memory/store: SQLite/FTS, Fakten-Store, Embeddings, Vektor-Store
- jarvis_memory/retrieval: Vektor/Keyword/Hybrid + Context Builder
- jarvis_memory/eval: Eval-Dataset-Loader, Metriken und gespeicherte Eval-Laeufe
- jarvis_memory/service.py: Fassade fuer alle Aufrufer von aussen (API, spaeter Jarvis/Agenten)
- api/: FastAPI-Server (duenne HTTP-Schicht ueber `MemoryService`)
- ui/: Streamlit-Oberflaeche (spricht nur HTTP mit der API, importiert `jarvis_memory` nicht)
- tests/: Unit-, API- und UI-Smoke-Tests
- data/eval_dataset.yaml: Beispiel-Evalset
- data/dummy/: Dummy-Dokumente

## Setup

1. Virtuelle Umgebung:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Installation:

```bash
pip install -e '.[dev]'
```

Optional fuer lokalen Sentence-Transformer-Embedder:

```bash
pip install -e '.[embeddings]'
```

## CLI

Ingestion:

```bash
jarvis-memory ingest data/dummy
```

Fakt hinzufuegen/aktualisieren (automatische Abloesung bei Widerspruch):

```bash
jarvis-memory add-fact --subject Fabian --attribute address --value "Musterweg 2" --source profile.md
```

Faktenhistorie:

```bash
jarvis-memory fact-history --subject Fabian --attribute address
```

Kontext fuer eine Anfrage bauen:

```bash
jarvis-memory query "Wann ist mein Mathe-Tutorium?"
```

Retrieval-Evaluation:

```bash
jarvis-memory eval --k 6
```

## Konfiguration

Zentrale Defaults in jarvis_memory/config.py:

- Embedding-Provider: local_hash (Default), sentence_transformers oder ollama
- Modellnamen / Ollama-Endpoint
- Chunking-Parameter
- Retrieval-Parameter (top_k, vector_k, keyword_k, rrf_k, enable_rerank)
- Kontext-Budget
- Speicherpfade

Hinweis: local_hash ist ein leichter, lokaler Default fuer sofortige Lauffaehigkeit. Fuer semantisch staerkere Embeddings nutze sentence_transformers oder ollama.

## API und Weboberflaeche

Lokale Oberflaeche zum Hochladen von Dokumenten und zum Nachvollziehen von Chunking, Retrieval, Fakten und Eval. Die gesamte Logik liegt in `jarvis_memory`; die API ruft nur `MemoryService` auf, die UI ruft nur die API auf.

### Setup und Start

```bash
make install   # pip install -e '.[dev,api,ui]'
make api       # API auf http://127.0.0.1:8765 (Doku: /docs)
make ui        # UI auf http://127.0.0.1:8501
make run       # beides parallel, Strg+C beendet beide
make test      # alle Tests
```

Ohne make: `python -m api` und `streamlit run ui/app.py`.

API und CLI teilen sich denselben Speicher (`.jarvis_memory/`). Hochgeladene Dateien liegen unter `.jarvis_memory/uploads/<id>/`.

### Ansichten

1. **Dokumente**: Drag & Drop mehrerer Dateien, Status je Datei (wartet, verarbeitet, indexiert, Duplikat, Fehler), Tabelle aller Dokumente, Loeschen und Neu-Indexieren
2. **Chunk-Browser**: Zerlegung eines Dokuments mit Laenge, Metadaten und markiertem Overlap; Kennzahlen und Hervorhebung auffaellig kurzer/langer Chunks
3. **Query-Inspector**: Vektor-, Keyword- und fusionierte Treffer getrennt mit Scores, darunter der Kontext-Block wie er ans LLM geht; Suche nach einem erwarteten Chunk mit Rang auch ausserhalb von top_k
4. **Fakten & Eval**: aktuelle Fakten, Anlegen/Aendern (alte Version bleibt als abgeloest sichtbar), Historie; Eval-Laeufe starten und vergleichen

Screenshots: _Platzhalter_ (`docs/screenshots/dokumente.png`, `chunk-browser.png`, `query-inspector.png`, `fakten-eval.png`)

### Endpoints

| Methode | Pfad | Zweck |
|---|---|---|
| GET | `/health` | Status und Zaehler |
| POST | `/ingest` | Upload (multipart, Feld `files`, mehrere Dateien); je Datei `job_id`, `document_id`, Status |
| GET | `/ingest`, `/ingest/{job_id}` | Job-Status: `queued`, `processing`, `indexed`, `duplicate`, `failed` |
| GET | `/documents`, `/documents/{id}` | Dokumente mit Name, Typ, Datum, Chunk-Anzahl, Content-Hash |
| GET | `/documents/{id}/chunks` | Chunks mit Laenge, Overlap, Auffaelligkeit und Kennzahlen |
| DELETE | `/documents/{id}` | entfernt Dokument aus Vektor-DB und Keyword-Index (und die hochgeladene Datei) |
| POST | `/documents/{id}/reindex` | neu indexieren |
| POST | `/query` | Frage, `top_k`, `filters`, `rerank`; Vektor-, Keyword- und fusionierte Treffer plus Kontext-Block |
| POST | `/query/locate` | Rang/Score der Chunks eines Dokuments fuer eine Frage, auch jenseits von top_k |
| GET/POST | `/facts` | aktuelle Fakten (`?include_superseded=true` fuer alle) / anlegen |
| PUT | `/facts/{id}` | neue Version; die alte wird abgeloest, nicht geloescht |
| GET | `/facts/{id}/history` | Versionshistorie |
| POST | `/eval/run` | Eval mit `data/eval_dataset.yaml` starten (Body: `{"k": 6}`) |
| GET | `/eval/results` | alle Laeufe mit Recall@k, MRR, Zeitstempel und verwendeter Config |

Uploads werden als Hintergrund-Job verarbeitet. Der Job-Status liegt nur im Speicher und geht bei einem Neustart der API verloren; die Dokumente selbst bleiben erhalten.

### Upload-Pruefung

- Erlaubt: `.pdf`, `.md`, `.txt`, `.eml`. Geprueft werden Endung **und** Inhalt (PDF-Signatur, UTF-8-Text ohne Binaerdaten, E-Mail-Header).
- Groessenlimit je Datei (Default 25 MB), maximal 20 Dateien je Upload.
- Dateinamen werden bereinigt (kein Pfadanteil, nur `A-Za-z0-9._-`), jede Datei liegt in einem eigenen Unterordner und wird nie ausgefuehrt.
- Duplikate werden per Content-Hash erkannt, gemeldet und nicht erneut indexiert; die doppelte Datei wird wieder entfernt.

### Konfiguration

Defaults in `jarvis_memory/config.py` (`UploadConfig`, `InspectionConfig`, `ServerConfig`). Ueberschreibbar per Umgebungsvariable:

| Variable | Default | Wirkung |
|---|---|---|
| `JARVIS_DATA_DIR` | `.jarvis_memory` | Speicherort fuer SQLite, Chroma und Uploads |
| `JARVIS_MAX_UPLOAD_MB` | `25` | Groessenlimit je Datei (zusaetzlich `maxUploadSize` in `.streamlit/config.toml` anpassen) |
| `JARVIS_API_HOST` / `JARVIS_API_PORT` | `127.0.0.1` / `8765` | Bind-Adresse der API |
| `JARVIS_API_URL` | `http://127.0.0.1:8765` | API-Adresse fuer die UI |

UI-Einstellungen (Timeouts, Polling) stehen in `ui/config.py`, Streamlit-Server-Einstellungen in `.streamlit/config.toml` (nur localhost, keine Usage-Statistiken).

### Sicherheit: vor einem Deployment noetig

Die aktuelle Stufe hat **keine Authentifizierung** und ist nur fuer den Betrieb auf dem eigenen Rechner gedacht. Server binden deshalb nur an `127.0.0.1`. Bevor API oder UI im Netz erreichbar werden:

- **Login/Auth**: API-Zugriff nur mit Token oder Session (z. B. OAuth2/OIDC ueber die Uni), UI hinter Login; Rollen, wer loeschen und Fakten aendern darf.
- **HTTPS**: TLS ueber einen Reverse Proxy (z. B. Caddy oder nginx); API nicht direkt exponieren.
- **Upload-Schutz**: Rate Limits, Limit der Request-Groesse am Proxy (Starlette puffert den Body vor der Pruefung), Virenscan, Quotas pro Person; PDFs ggf. in einer Sandbox parsen.
- **Daten**: Uploads und Datenbank enthalten persoenliche Daten. Verschluesselung at rest, Backups, Loeschkonzept und Zugriffsprotokoll; der Kontext-Block enthaelt lokale Dateipfade.
- **CORS** bleibt aus (die UI ruft die API serverseitig auf); bei einem Browser-Client nur die eigene Origin zulassen.

## Hinweise

- Keine Cloud-APIs in der Pipeline. Chroma-Telemetrie und Streamlit-Usage-Statistiken sind abgeschaltet.
- Das LLM ist bewusst nicht Teil dieses Moduls; Ausgabe ist ein fertiger Kontextblock.
- Warning aus Chroma/OpenTelemetry zu Python 3.14 ist derzeit nur kosmetisch.
