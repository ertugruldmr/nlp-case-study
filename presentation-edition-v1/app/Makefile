.PHONY: setup precompute serve test clean

setup:
	uv sync
	@which tesseract >/dev/null || echo "MISSING: install tesseract + Turkish data (brew install tesseract tesseract-lang | apt install tesseract-ocr tesseract-ocr-tur)"

precompute:
	uv run ftlink-precompute

serve:
	uv run uvicorn ftlink_app.api:app --host 127.0.0.1 --port 8199

test:
	uv run pytest -q

clean:
	rm -rf runs/*/outputs runs/*/meta.json
