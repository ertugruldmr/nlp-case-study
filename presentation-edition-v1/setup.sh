#!/usr/bin/env bash
# One-time setup for the live demo. Safe to re-run.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "==> checking prerequisites"
command -v uv >/dev/null || {
  echo "MISSING: uv. Install it with:  curl -LsSf https://astral.sh/uv/install.sh | sh"
  exit 1
}
command -v tesseract >/dev/null || {
  echo "MISSING: tesseract + Turkish language data."
  echo "  macOS:  brew install tesseract tesseract-lang"
  echo "  Debian: sudo apt install tesseract-ocr tesseract-ocr-tur"
  exit 1
}
tesseract --list-langs 2>/dev/null | grep -qx tur || {
  echo "WARNING: the 'tur' tesseract language pack was not found; OCR will fall back to English."
}

echo "==> installing the Python environment (this resolves the sealed pipeline in ../v0)"
cd "$ROOT/app"
uv sync

echo
echo "Setup complete."
echo "  start the demo server : $ROOT/run-pdf-debugger.sh"
echo "  open the cockpit      : $ROOT/run.sh"
echo
echo "Optional, ~14 min CPU, makes every scenario instant instead of on-demand:"
echo "  cd $ROOT/app && uv run ftlink-precompute"
