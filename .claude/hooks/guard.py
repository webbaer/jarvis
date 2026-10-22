#!/usr/bin/env python3
"""PreToolUse guard for coding agents working in this repo.

Reads the hook payload from stdin. Exit 0 = allow, exit 2 = block
(stderr is shown to the agent as the reason).
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

PROJECT_DIR = Path(os.environ.get("CLAUDE_PROJECT_DIR", Path.cwd())).resolve()
# Scratch space outside the repo that agents may still write to.
TEMP_DIRS = [Path(tempfile.gettempdir()).resolve(), Path("/tmp").resolve()]

# Generated or runtime state: never edited by hand.
PROTECTED_PATH_PARTS = {
    ".jarvis_memory": "Runtime-Store (SQLite/Chroma). Neu erzeugen mit `jarvis-memory ingest`, nicht editieren.",
    ".venv": "Virtuelle Umgebung. Abhaengigkeiten ueber pyproject.toml aendern.",
    ".git": "Git-Interna nicht direkt editieren.",
    "__pycache__": "Generierter Bytecode.",
    ".pytest_cache": "Generierter Cache.",
}
PROTECTED_SUFFIXES = {
    ".egg-info": "Generierte Paket-Metadaten (pip install -e).",
    ".sqlite3": "Datenbankdatei, nur ueber den Code aendern.",
    ".pyc": "Generierter Bytecode.",
}

# (pattern, reason) for Bash commands that are blocked outright.
BLOCKED_COMMANDS = [
    (r"\brm\s+(-[a-zA-Z]*[rf][a-zA-Z]*\s+)+(/|~|\.|\*|\$HOME)(\s|$)",
     "Rekursives Loeschen von Root/Home/Repo-Wurzel ist verboten."),
    (r"\brm\s+(?!.*--cached).*(\.jarvis_memory|data/)",
     "Loeschen von .jarvis_memory/ oder data/ ist verboten. Den Store ggf. ueber eine Config mit tmp-Pfad testen."),
    (r"\bgit\s+push\b.*(--force\b|-f\b|--force-with-lease)",
     "Force-Push ist verboten."),
    (r"\bgit\s+push\b.*\b(main|master)\b",
     "Direkter Push auf main ist verboten. Ueber Feature-Branch + PR gehen."),
    (r"\bgit\s+reset\s+--hard\b",
     "git reset --hard verwirft Arbeit. Erst mit dem User absprechen."),
    (r"\bgit\s+clean\s+-[a-zA-Z]*f",
     "git clean -f loescht ungetrackte Dateien. Erst mit dem User absprechen."),
    (r"\bgit\s+(checkout|restore)\s+(--\s+)?\.(\s|$)",
     "Verwirft alle lokalen Aenderungen. Erst mit dem User absprechen."),
    (r"\bgit\s+commit\b.*--no-verify",
     "--no-verify umgeht Checks."),
    (r"\bgit\s+branch\s+-D\b",
     "Erzwungenes Loeschen von Branches ist verboten."),
    (r"\bsqlite3\b.*\.jarvis_memory.*\b(DELETE|DROP|UPDATE|INSERT)\b",
     "Schreibzugriffe direkt auf den Memory-Store sind verboten. Ueber FactStore/IngestionPipeline gehen."),
    (r"\bpip3?\s+install\b(?!.*-e\s+['\"]?\.)",
     "Keine ad-hoc Paketinstallation. Abhaengigkeit in pyproject.toml eintragen und `pip install -e '.[dev]'` nutzen."),
    (r"\b(curl|wget)\b.*\|\s*(ba|z)?sh\b",
     "Remote-Skripte nicht direkt ausfuehren."),
]


def _block(reason: str) -> None:
    print(f"[guardrail] Blockiert: {reason}", file=sys.stderr)
    sys.exit(2)


def check_path(raw_path: str) -> None:
    path = Path(raw_path)
    if not path.is_absolute():
        path = PROJECT_DIR / path
    path = path.resolve()

    try:
        rel = path.relative_to(PROJECT_DIR)
    except ValueError:
        if not any(path.is_relative_to(t) for t in TEMP_DIRS):
            _block(f"{raw_path} liegt ausserhalb des Repos.")
        return

    for part in rel.parts:
        if part in PROTECTED_PATH_PARTS:
            _block(f"{rel}: {PROTECTED_PATH_PARTS[part]}")
        for suffix, reason in PROTECTED_SUFFIXES.items():
            if part.endswith(suffix):
                _block(f"{rel}: {reason}")


def check_command(command: str) -> None:
    for pattern, reason in BLOCKED_COMMANDS:
        if re.search(pattern, command, flags=re.IGNORECASE):
            _block(reason)


def main() -> None:
    payload = json.load(sys.stdin)
    tool = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {}) or {}

    if tool in {"Edit", "Write", "NotebookEdit"}:
        target = tool_input.get("file_path") or tool_input.get("notebook_path")
        if target:
            check_path(target)
    elif tool == "Bash":
        check_command(tool_input.get("command", ""))


if __name__ == "__main__":
    main()
