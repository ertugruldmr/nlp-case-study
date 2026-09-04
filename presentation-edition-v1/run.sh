#!/usr/bin/env bash
# Open the offline presentation cockpit. Works with or without the demo server;
# the "Open live demo" button needs ./run-pdf-debugger.sh running.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
TARGET="$ROOT/dashboard.html"
if command -v open >/dev/null; then open "$TARGET"
elif command -v xdg-open >/dev/null; then xdg-open "$TARGET"
else echo "Open this file in a browser: $TARGET"; fi
