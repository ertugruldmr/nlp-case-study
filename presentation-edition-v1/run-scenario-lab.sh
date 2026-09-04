#!/usr/bin/env bash
# Alias of run-pdf-debugger.sh: one server serves both the scenario lab and the debugger.
set -euo pipefail
exec "$(cd "$(dirname "$0")" && pwd)/run-pdf-debugger.sh" "$@"
