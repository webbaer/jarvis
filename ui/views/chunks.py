from __future__ import annotations

import html

import streamlit as st

from ui.client import ApiClient
from ui.views.common import call, document_label

FLAG_LABELS = {"short": "auffaellig kurz", "long": "auffaellig lang"}
_TEXT_STYLE = "white-space: pre-wrap; font-family: ui-monospace, monospace; font-size: 0.85rem;"
_OVERLAP_STYLE = "background: rgba(255, 200, 0, 0.35); border-radius: 2px;"


def render(client: ApiClient) -> None:
    docs = call(client.documents, "Dokumente laden")
    if docs is None:
        return
    if not docs:
        st.info("Noch keine Dokumente indexiert.")
        return

    doc = st.selectbox("Dokument", docs, format_func=document_label, key="cb_doc")
    data = call(lambda: client.chunks(doc["id"]), "Chunks laden")
    if data is None:
        return

    stats = data["stats"]
    if doc["duplicate_of"]:
        st.info("Dieses Dokument ist ein Duplikat und hat keine eigenen Chunks.")
    cols = st.columns(6)
    cols[0].metric("Chunks", stats["count"])
    cols[1].metric("Durchschnitt", f"{stats['avg_length']:.0f} Z.")
    cols[2].metric("Kuerzester", f"{stats['min_length']} Z.")
    cols[3].metric("Laengster", f"{stats['max_length']} Z.")
    cols[4].metric("Zu kurz", stats["short_count"])
    cols[5].metric("Zu lang", stats["long_count"])
    st.caption(
        f"Auffaellig: kuerzer als {stats['short_threshold']} oder laenger als {stats['long_threshold']} Zeichen. "
        "Gelb markiert = Overlap aus dem vorherigen Chunk."
    )

    only_flagged = st.checkbox("Nur auffaellige Chunks zeigen", key="cb_only_flagged")
    chunks = [c for c in data["chunks"] if c["flag"] or not only_flagged]
    if not chunks:
        st.caption("Keine Chunks zum Anzeigen.")
        return

    st.dataframe(
        [
            {
                "#": c["chunk_index"],
                "Laenge": c["length"],
                "Overlap": c["overlap_chars"],
                "Auffaelligkeit": FLAG_LABELS.get(c["flag"], ""),
            }
            for c in chunks
        ],
        hide_index=True,
        width="stretch",
    )

    for chunk in chunks:
        with st.container(border=True):
            flag = f" · **{FLAG_LABELS[chunk['flag']]}**" if chunk["flag"] else ""
            st.markdown(f"**Chunk {chunk['chunk_index']}** · {chunk['length']} Zeichen · Overlap {chunk['overlap_chars']}{flag}")
            st.markdown(_highlight(chunk["text"], chunk["overlap_chars"]), unsafe_allow_html=True)
            st.caption(
                f"id={chunk['id']} · typ={chunk['doc_type']} · datum={chunk['doc_date'] or '-'} · erstellt={chunk['created_at'][:19]}"
            )


def _highlight(text: str, overlap: int) -> str:
    head = html.escape(text[:overlap])
    tail = html.escape(text[overlap:])
    marked = f'<span style="{_OVERLAP_STYLE}">{head}</span>' if head else ""
    return f'<div style="{_TEXT_STYLE}">{marked}{tail}</div>'
