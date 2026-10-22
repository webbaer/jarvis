"""UI settings. The UI talks to the API over HTTP only and never imports jarvis_memory."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

DEFAULT_API_URL = "http://127.0.0.1:8765"


@dataclass(frozen=True, slots=True)
class UiConfig:
    api_url: str = field(default_factory=lambda: os.environ.get("JARVIS_API_URL", DEFAULT_API_URL))
    timeout_s: float = 30.0
    upload_timeout_s: float = 300.0
    eval_timeout_s: float = 300.0
    # Polling for ingest jobs right after an upload.
    poll_interval_s: float = 0.5
    poll_max_s: float = 15.0
    preview_chars: int = 160
    allowed_types: tuple[str, ...] = ("pdf", "md", "txt", "eml")


UI_CONFIG = UiConfig()
