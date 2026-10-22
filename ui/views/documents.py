from __future__ import annotations

import time

import streamlit as st

from ui.client import ApiClient, ApiError
from ui.config import UI_CONFIG
from ui.views.common import STATUS_LABELS, TERMINAL_STATUSES, call


def render(client: ApiClient) -> None:
    st.subheader("Upload")
    _upload_section(client)

    st.subheader("Dokumente")
    docs = call(client.documents, "Dokumente laden")
    if docs is None:
        return
    if not docs:
        st.info("Noch keine Dokumente indexiert.")
        return
    _documents_table(docs)
    _document_actions(client, docs)


def _upload_section(client: ApiClient) -> None:
    uploader_key = f"uploader_{st.session_state.get('uploader_gen', 0)}"
    files = st.file_uploader(
        "Dateien hierher ziehen (PDF, Markdown, Text, E-Mail)",
        type=list(UI_CONFIG.allowed_types),
        accept_multiple_files=True,
        key=uploader_key,
    )
    if st.button("Hochladen und indexieren", disabled=not files, type="primary"):
        items = call(lambda: client.upload([(f.name, f.getvalue()) for f in files]), "Upload")
        if items is not None:
            st.session_state["upload_items"] = items
            _poll_jobs(client)
            # A fresh key clears the file uploader.
            st.session_state["uploader_gen"] = st.session_state.get("uploader_gen", 0) + 1
            st.rerun()

    items = st.session_state.get("upload_items")
    if not items:
        return

    docs_by_id = {d["id"]: d for d in (call(client.documents, "Dokumente laden") or [])}
    rows = []
    for item in items:
        status = item.get("job_status", item["status"])
        note = item.get("error") or ""
        if status == "duplicate":
            original = docs_by_id.get(item.get("duplicate_of") or "")
            note = f"Inhalt schon vorhanden als '{original['name'] if original else item.get('duplicate_of')}', nicht erneut indexiert"
        elif status == "indexed":
            note = f"{item.get('chunk_count', 0)} Chunks"
        rows.append({"Datei": item["filename"], "Status": STATUS_LABELS.get(status, status), "Hinweis": note})
    st.dataframe(rows, hide_index=True, width="stretch")

    if any(r["Status"] == STATUS_LABELS["duplicate"] for r in rows):
        st.warning("Mindestens eine Datei war ein Duplikat und wurde nicht erneut indexiert.")
    if any(r["Status"] in (STATUS_LABELS["rejected"], STATUS_LABELS["failed"]) for r in rows):
        st.error("Mindestens eine Datei wurde abgelehnt oder konnte nicht verarbeitet werden, siehe Hinweis.")

    pending = any(item.get("job_status", item["status"]) not in TERMINAL_STATUSES for item in items)
    col_refresh, col_clear = st.columns([1, 1])
    if pending and col_refresh.button("Status aktualisieren"):
        _poll_jobs(client, max_s=0)
        st.rerun()
    if col_clear.button("Upload-Liste leeren"):
        st.session_state.pop("upload_items", None)
        st.rerun()


def _poll_jobs(client: ApiClient, max_s: float = UI_CONFIG.poll_max_s) -> None:
    """Refresh job states, waiting up to max_s for running jobs to finish."""
    items: list[dict] = st.session_state.get("upload_items", [])
    deadline = time.monotonic() + max_s
    with st.spinner("Verarbeite Dateien ..."):
        while True:
            for item in items:
                if not item.get("job_id") or item.get("job_status") in TERMINAL_STATUSES:
                    continue
                job = call(lambda: client.job(item["job_id"]), "Job-Status")
                if job is None:
                    return
                item.update(
                    job_status=job["status"],
                    error=job["error"],
                    duplicate_of=job["duplicate_of"],
                    chunk_count=job["chunk_count"],
                )
            pending = [i for i in items if i.get("job_id") and i.get("job_status") not in TERMINAL_STATUSES]
            if not pending or time.monotonic() >= deadline:
                return
            time.sleep(UI_CONFIG.poll_interval_s)


def _documents_table(docs: list[dict]) -> None:
    names = {d["id"]: d["name"] for d in docs}
    rows = [
        {
            "Name": d["name"],
            "Typ": d["doc_type"],
            "Datum": d["doc_date"] or "",
            "Chunks": int(d["chunk_count"]),
            "Indexiert am": d["indexed_at"][:19].replace("T", " "),
            "Hash": d["content_hash"][:12],
            "Duplikat von": names.get(d["duplicate_of"], d["duplicate_of"] or ""),
            "Pfad": d["source_path"],
        }
        for d in docs
    ]
    st.dataframe(rows, hide_index=True, width="stretch")


def _document_actions(client: ApiClient, docs: list[dict]) -> None:
    st.markdown("**Aktionen**")
    for doc in docs:
        col_name, col_reindex, col_delete = st.columns([6, 1.5, 1.5])
        col_name.write(f"{doc['name']}  \n`{doc['id']}`")
        if col_reindex.button("Neu indexieren", key=f"reindex_{doc['id']}"):
            result = call(lambda: client.reindex_document(doc["id"]), "Neu-Indexieren")
            if result is not None:
                st.toast(f"{doc['name']}: {result['chunk_count']} Chunks neu indexiert")
                st.rerun()

        confirm_key = f"confirm_delete_{doc['id']}"
        if not st.session_state.get(confirm_key):
            if col_delete.button("Loeschen", key=f"delete_{doc['id']}"):
                st.session_state[confirm_key] = True
                st.rerun()
        else:
            st.warning(f"'{doc['name']}' wirklich loeschen? Chunks werden aus Vektor- und Keyword-Index entfernt.")
            col_yes, col_no, _ = st.columns([1, 1, 6])
            if col_yes.button("Ja, loeschen", key=f"delete_yes_{doc['id']}", type="primary"):
                st.session_state.pop(confirm_key, None)
                try:
                    client.delete_document(doc["id"])
                except ApiError as exc:
                    st.error(f"Loeschen fehlgeschlagen. {exc.message}")
                    return
                st.toast(f"{doc['name']} geloescht")
                st.rerun()
            if col_no.button("Abbrechen", key=f"delete_no_{doc['id']}"):
                st.session_state.pop(confirm_key, None)
                st.rerun()
