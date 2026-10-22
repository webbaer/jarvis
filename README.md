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
- jarvis_memory/eval: Eval-Dataset-Loader und Metriken
- tests/: Unit-Tests
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

## Hinweise

- Keine Cloud-APIs in der Pipeline.
- Das LLM ist bewusst nicht Teil dieses Moduls; Ausgabe ist ein fertiger Kontextblock.
- Warning aus Chroma/OpenTelemetry zu Python 3.14 ist derzeit nur kosmetisch.
