from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

import streamlit as st

from ui.client import ApiClient, ApiError
from ui.config import UI_CONFIG, UiConfig

T = TypeVar("T")

STATUS_LABELS = {
    "queued": "wartet",
    "processing": "verarbeitet",
    "indexed": "indexiert",
    "duplicate": "Duplikat",
    "failed": "Fehler",
    "rejected": "abgelehnt",
}
TERMINAL_STATUSES = {"indexed", "duplicate", "failed", "rejected"}


def get_client() -> ApiClient:
    return ApiClient(
        UiConfig().api_url,
        timeout_s=UI_CONFIG.timeout_s,
        upload_timeout_s=UI_CONFIG.upload_timeout_s,
        eval_timeout_s=UI_CONFIG.eval_timeout_s,
    )


def call(fn: Callable[[], T], what: str) -> T | None:
    """Run an API call and show a readable error instead of a traceback."""
    try:
        return fn()
    except ApiError as exc:
        st.error(f"{what} fehlgeschlagen. {exc.message}")
        return None


def preview(text: str, limit: int = UI_CONFIG.preview_chars) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def document_label(doc: dict) -> str:
    return f"{doc['name']} ({doc['doc_type']}, {doc['chunk_count']} Chunks)"
