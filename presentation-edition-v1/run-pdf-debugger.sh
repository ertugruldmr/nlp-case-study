#!/usr/bin/env bash
# Start the live demo server (scenario lab + PDF visual debugger).
# Leave this terminal attached; open the cockpit with ./run.sh in another one.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
PORT="${FTLINK_APP_PORT:-${PDF_DEBUGGER_PORT:-8199}}"

echo "ftlink demo server -> http://127.0.0.1:${PORT}"
echo "  scenario lab   : http://127.0.0.1:${PORT}/"
echo "  visual debugger: http://127.0.0.1:${PORT}/pdf-debugger.html"
echo

if [ -x "$ROOT/app/.venv/bin/python" ]; then
  exec "$ROOT/app/.venv/bin/python" -m uvicorn ftlink_app.api:app \
    --app-dir "$ROOT/app/src" --host 127.0.0.1 --port "$PORT"
fi

if command -v uv >/dev/null; then
  cd "$ROOT/app"
  exec uv run uvicorn ftlink_app.api:app --host 127.0.0.1 --port "$PORT"
fi

echo "No environment found. Run ./setup.sh first (it needs uv and tesseract)." >&2
exit 1
