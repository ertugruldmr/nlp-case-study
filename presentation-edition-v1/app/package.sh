#!/bin/sh
# Build the offline review bundle: the scenario lab plus the sealed pipeline it
# depends on, with no virtual environments, caches, uploads or reviewer labels.
set -eu
APP=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
ROOT=$(CDPATH= cd -- "$APP/../.." && pwd)
OUT="$APP/dist/ftlink-scenario-lab-v1.zip"
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT INT TERM
mkdir -p "$STAGE/ftlink-scenario-lab-v1/app" "$STAGE/ftlink-scenario-lab-v1/v0"

# Explicit allowlist: no virtual environments, caches, uploads, labels or git data.
cp -R "$APP/benchmarks" "$APP/fixtures" "$APP/frontend" "$APP/src" "$APP/tests" "$APP/runs" "$STAGE/ftlink-scenario-lab-v1/app/"
cp "$APP/pyproject.toml" "$APP/uv.lock" "$APP/Makefile" "$APP/README.md" "$APP/Dockerfile" "$APP/compose.yaml" "$APP/demo_preflight.sh" "$APP/demo_alternate_pdf.sh" "$APP/ALTERNATE-PDF-DEMO.md" "$STAGE/ftlink-scenario-lab-v1/app/"
cp -R "$ROOT/v0/configs" "$ROOT/v0/data" "$ROOT/v0/eval" "$ROOT/v0/src" "$ROOT/v0/tests" "$ROOT/v0/outputs" "$STAGE/ftlink-scenario-lab-v1/v0/"
cp "$ROOT/v0/pyproject.toml" "$ROOT/v0/uv.lock" "$ROOT/v0/Makefile" "$ROOT/v0/README.md" "$STAGE/ftlink-scenario-lab-v1/v0/"
cp "$APP/PACKAGE-MANIFEST.md" "$STAGE/ftlink-scenario-lab-v1/"
find "$STAGE" -type d \( -name '__pycache__' -o -name '.pytest_cache' -o -name '.venv' -o -name '_documents' -o -name '_labels' -o -name '_debugger' \) -exec rm -rf {} +
find "$STAGE/ftlink-scenario-lab-v1/app/runs" -mindepth 1 -maxdepth 1 -type d -name 'doc-*' -exec rm -rf {} +
find "$STAGE" -type f \( -name '*.pyc' -o -name '*.log' \) -delete
mkdir -p "$APP/dist"
(test -f "$OUT" && rm -f "$OUT") || true
(cd "$STAGE" && zip -qr "$OUT" ftlink-scenario-lab-v1)
printf '%s\n' "$OUT"
