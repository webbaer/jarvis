#!/usr/bin/env bash
# Stop hook: before the agent finishes, run pytest if Python files changed.
# Exit 2 sends the failure back to the agent so it fixes it before stopping.
set -u

payload="$(cat)"
# Avoid loops: if we already blocked once in this stop cycle, let it stop.
if printf '%s' "$payload" | grep -q '"stop_hook_active"[[:space:]]*:[[:space:]]*true'; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0

# Only run when tracked or new .py files differ from HEAD.
changed="$( { git diff --name-only HEAD; git ls-files --others --exclude-standard; } 2>/dev/null | grep -E '\.py$' )"
[ -z "$changed" ] && exit 0

python=".venv/bin/python"
[ -x "$python" ] || python="python3"

if ! output="$("$python" -m pytest -q -x 2>&1)"; then
  {
    echo "[guardrail] pytest schlaegt fehl. Bitte vor dem Abschluss beheben:"
    printf '%s\n' "$output" | tail -40
  } >&2
  exit 2
fi
exit 0
