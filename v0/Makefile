# Every target wraps a plain `uv run` command; the commands are also printed
# verbatim in README.md for environments without make.

.PHONY: setup run run-alt test clean eval determinism calibration

setup:
	uv sync --frozen
	@which tesseract >/dev/null || echo "MISSING: install tesseract + Turkish data (brew install tesseract tesseract-lang | apt install tesseract-ocr tesseract-ocr-tur)"

run:
	uv run ftlink run --config configs/default.yaml

run-alt:
	uv run ftlink run --config configs/alt_footnote.yaml

test:
	uv run pytest -q

clean:
	rm -rf outputs outputs_footnote12
eval:
	uv run python eval/score.py

determinism:
	uv run python eval/determinism.py

calibration:
	uv run python eval/calibration_loo.py
