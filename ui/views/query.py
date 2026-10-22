from __future__ import annotations

import streamlit as st

from ui.client import ApiClient
from ui.views.common import call, document_label, preview

DEFAULT_TOP_K = 6
MAX_TOP_K = 50
DEFAULT_DEPTH = 100
MAX_DEPTH = 500
ALL = "(alle)"


def _short_source(source: str) -> str:
    return source.replace("\\", "/").rsplit("/", 1)[-1]


def _fmt(score: float | None) -> str:
    return "" if score is None else f"{score:.4f}"


def _rank(rank: int | None, missing: str = "") -> str:
    # Text column: mixing ints and placeholders breaks Arrow serialization.
    return missing if rank is None else str(rank)


def render(client: ApiClient) -> None:
    docs = call(client.documents, "Dokumente laden") or []

    query = st.text_input("Frage", key="qi_query", placeholder="z. B. Wann ist das Tutorium?")
    col_k, col_rerank = st.columns([1, 1])
    top_k = col_k.number_input("top_k", min_value=1, max_value=MAX_TOP_K, value=DEFAULT_TOP_K, key="qi_top_k")
    rerank = col_rerank.toggle("Reranking", value=False, key="qi_rerank", help="Nutzt den konfigurierten Reranker (derzeit Noop).")
    filters = _filters(docs)

    if st.button("Suchen", type="primary", disabled=not query.strip()):
        result = call(lambda: client.query(query, int(top_k), filters, rerank), "Suche")
        if result is not None:
            st.session_state["qi_result"] = {"query": query, "top_k": int(top_k), "filters": filters, "result": result}

    state = st.session_state.get("qi_result")
    if not state:
        return
    result = state["result"]
    st.caption(f"Ergebnis fuer: \"{state['query']}\" (top_k={state['top_k']})")

    col_vec, col_kw, col_fused = st.columns(3)
    with col_vec:
        st.markdown("**Vektor-Treffer**")
        _hits_table(result["vector_hits"], "vector")
    with col_kw:
        st.markdown("**Keyword-Treffer (BM25)**")
        _hits_table(result["keyword_hits"], "keyword")
    with col_fused:
        st.markdown("**Fusioniert (RRF)**")
        _hits_table(result["fused_hits"], "fused")

    with st.expander("Volltext der fusionierten Treffer"):
        for hit in result["fused_hits"]:
            st.markdown(f"**#{hit['fused_rank']}** `{_short_source(hit['source'])}` · `{hit['chunk_id']}`")
            st.text(hit["text"])

    st.markdown("**Kontext-Block (so geht er ans LLM)**")
    st.code(result["context"], language=None, wrap_lines=True)

    _locate_section(client, docs, state)


def _filters(docs: list[dict]) -> dict | None:
    with st.expander("Filter"):
        types = sorted({d["doc_type"] for d in docs})
        sources = sorted({d["source_path"] for d in docs})
        col_type, col_source = st.columns(2)
        doc_type = col_type.selectbox("Dokumenttyp", [ALL, *types], key="qi_type")
        source = col_source.selectbox("Quelle", [ALL, *sources], key="qi_source", format_func=lambda s: s if s == ALL else _short_source(s))
        col_from, col_to = st.columns(2)
        date_from = col_from.text_input("Datum ab (wie im Dokument gespeichert)", key="qi_from")
        date_to = col_to.text_input("Datum bis", key="qi_to")

    filters = {
        "doc_type": None if doc_type == ALL else doc_type,
        "source": None if source == ALL else source,
        "date_from": date_from or None,
        "date_to": date_to or None,
    }
    return filters if any(filters.values()) else None


def _hits_table(hits: list[dict], kind: str) -> None:
    if not hits:
        st.caption("keine Treffer")
        return
    rows = []
    for idx, hit in enumerate(hits, start=1):
        row = {"Rang": hit.get("fused_rank", idx)}
        if kind == "vector":
            row["Score"] = _fmt(hit["vector_score"])
        elif kind == "keyword":
            row["Score"] = _fmt(hit["keyword_score"])
        else:
            row.update(
                {
                    "RRF": _fmt(hit["score"]),
                    "V-Rang": _rank(hit["vector_rank"]),
                    "K-Rang": _rank(hit["keyword_rank"]),
                }
            )
        row.update({"Quelle": _short_source(hit["source"]), "Text": preview(hit["text"])})
        rows.append(row)
    st.dataframe(rows, hide_index=True, width="stretch")


def _locate_section(client: ApiClient, docs: list[dict], state: dict) -> None:
    with st.expander("Erwarteten Chunk suchen (fehlt er im Ergebnis?)"):
        if not docs:
            st.caption("Keine Dokumente vorhanden.")
            return
        doc = st.selectbox("Dokument", docs, format_func=document_label, key="qi_loc_doc")
        chunks = (call(lambda: client.chunks(doc["id"]), "Chunks laden") or {}).get("chunks", [])
        options = [None, *chunks]
        chunk = st.selectbox(
            "Chunk",
            options,
            format_func=lambda c: "alle Chunks des Dokuments" if c is None else f"#{c['chunk_index']}: {preview(c['text'], 80)}",
            key="qi_loc_chunk",
        )
        depth = st.slider("Suchtiefe je Retriever", min_value=10, max_value=MAX_DEPTH, value=DEFAULT_DEPTH, step=10, key="qi_loc_depth")

        if st.button("Rang ermitteln", key="qi_loc_btn"):
            locations = call(
                lambda: client.locate(
                    state["query"], doc["id"], chunk["id"] if chunk else None, state["top_k"], state["filters"], depth
                ),
                "Chunk-Suche",
            )
            if locations is None:
                return
            rows = [
                {
                    "Chunk": loc["chunk_id"].rsplit(":", 1)[-1],
                    "Im Ergebnis": "ja" if loc["in_top_k"] else "nein",
                    "Rang im Ergebnis": _rank(loc["fused_rank"], "-"),
                    "Rang (Tiefensuche)": _rank(loc["deep_fused_rank"], f"> {depth}"),
                    "Vektor-Rang": _rank(loc["vector_rank"], f"> {depth}"),
                    "Vektor-Score": _fmt(loc["vector_score"]),
                    "Keyword-Rang": _rank(loc["keyword_rank"], "kein Treffer"),
                    "Keyword-Score": _fmt(loc["keyword_score"]),
                }
                for loc in locations
            ]
            st.dataframe(rows, hide_index=True, width="stretch")
            if not any(loc["in_top_k"] for loc in locations):
                st.warning(f"Kein Chunk dieses Dokuments ist in den Top {state['top_k']}.")
