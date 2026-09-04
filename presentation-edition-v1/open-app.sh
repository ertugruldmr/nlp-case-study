#!/usr/bin/env bash
set -euo pipefail
URL="http://127.0.0.1:${FTLINK_APP_PORT:-8199}"
if command -v open >/dev/null; then open "$URL"; elif command -v xdg-open >/dev/null; then xdg-open "$URL"; else echo "$URL"; fi
