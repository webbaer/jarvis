"""Jarvis Memory UI. Start with `make ui` (or `streamlit run ui/app.py`)."""
from __future__ import annotations

import sys
from pathlib import Path

# Streamlit puts only this file's directory on sys.path; make `ui.*` importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402

from ui.client import ApiError  # noqa: E402
from ui.views import chunks, documents, facts_eval, query  # noqa: E402
from ui.views.common import get_client  # noqa: E402

st.set_page_config(page_title="Jarvis Memory", layout="wide")
client = get_client()

with st.sidebar:
    st.title("Jarvis Memory")
    st.caption(f"API: {client.base_url}")
    try:
        health = client.health()
    except ApiError as exc:
        st.error(exc.message)
        st.stop()
    st.success("API erreichbar")
    st.metric("Dokumente", health["documents"])
    st.metric("Chunks", health["chunks"])
    st.metric("Aktive Fakten", health["facts"])

tab_docs, tab_chunks, tab_query, tab_facts = st.tabs(["Dokumente", "Chunk-Browser", "Query-Inspector", "Fakten & Eval"])
with tab_docs:
    documents.render(client)
with tab_chunks:
    chunks.render(client)
with tab_query:
    query.render(client)
with tab_facts:
    facts_eval.render(client)
