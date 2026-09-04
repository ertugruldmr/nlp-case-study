---
slug: ocr-bakeoff-run08
candidate: "E54: 16 OCR engine variants (tesseract x6, RapidOCR x3, EasyOCR, docTR x2, PaddleOCR, Qwen2.5-VL-7B x2, olmOCR-2) bake-off on the deliverable's 201 gold cells, GPU"
created: 2026-08-30T23:05:00+03:00
verified: 2026-08-30T23:05:00+03:00
status: fresh
verdict: partial
claim: "Does any alternative OCR engine beat the shipped tesseract+RapidOCR two-engine pipeline on this scan class?"
sources:
  - research/assets/experiments/colab/run-08-ocr-bakeoff/nb8_ocr_results.json
  - research/assets/experiments/colab/run-08-ocr-bakeoff/README.md
  - handoff/RUN0678-FOLDIN-PLAN.md
tags: [measured, colab, gpu, ocr, E54]
---

# E54: OCR bake-off, run-08 (GPU, L4), shipped pipeline stays ahead

## Test setup
Colab L4, `colab-ops/run.sh run-08-ocr-bakeoff all`, 1265s notebook-internal elapsed (1336s wall
at the campaign level). 16 of 16 planned engine variants attempted (per the notebook's own try/
except contract, predating this session's harness hardening): 15 completed `ok`, 1 recorded
`failed` with a traceback (PaddleOCR — its isolated venv could not install pip inside itself,
both GPU and CPU wheel paths; this is an environment failure, not a modelling result). No
silent gaps: every planned key is present in the result file with an explicit status.

Two scoring levels, not directly comparable to each other or naively to the shipped number:
level (a) = does the engine's full-page text contain the gold value string at all (denominator
182 numeric cells); level (b) = cell-exact match using row/column geometry derived from the
tesseract TSV (denominator 201, mixing number/dash/empty states). The notebook's own comparison
line is explicit about this: "Level (a) recall is looser ... and is not comparable to the
199/201 figure."

## Observed — level (b), cell-exact (the comparable number)
| engine | cell exact /201 | percent /6 | label CER (folded) | s/page | GPU MB |
|---|---|---|---|---|---|
| **shipped (tesseract TSV + RapidOCR swap, README)** | **199** | 6/6 | — | — | 0 (CPU) |
| tesseract apt psm4 1x | 193 | 0/6 | 0.0498 | 1.66 | 0 |
| tesseract apt psm6 1x | 193 | 0/6 | 0.0524 | 1.41 | 0 |
| rapidocr_onnxruntime 1x | 190 | 6/6 | 0.0604 | 3.40 | 0 |
| rapidocr>=2.0, 1x | 190 | 6/6 | 0.0422 | 2.23 | 0 |
| doctr db_resnet50+crnn_vgg16_bn | 190 | 6/6 | 0.0566 | 0.38 | 568 |
| doctr db_resnet50+parseq | 190 | 6/6 | 0.0570 | 0.72 | 580 |
| easyocr tr | 185 | 6/6 | 0.0511 | 3.43 | 3580 |
| tesseract apt psm4 2x (upscale) | 183 | 0/6 | 0.0494 | 2.92 | 0 |
| tesseract apt psm6 2x (upscale) | 181 | 0/6 | 0.0528 | 2.57 | 0 |
| tesseract tessdata_best psm4/psm6 1x | 8 | 0/6 | 1.0 | 2.5-2.7 | 0 |
| PaddleOCR PP-OCRv5 | FAILED (venv pip install broken, both GPU and CPU wheel) | — | — | — | — |

Qwen2.5-VL-7B and olmOCR-2 are page-transcription VLMs scored only at level (a)/(a-row), not
directly in this table (see below).

**No single engine beats the shipped two-engine pipeline's 199/201.** The best single-engine
result at level (b) is the shipped primary itself (tesseract apt psm6, 193/201) before RapidOCR's
percent-row rescue is applied; every alternative engine that DOES read percent glyphs correctly
(RapidOCR variants, docTR, EasyOCR) trades that gain for worse digit/label fidelity elsewhere,
landing at 185-190/201, all below the shipped combination.

## Anomaly: tessdata_best returns literally empty strings, not bad recognition
Both `tessdata_best` variants (psm4 and psm6) score 8/201 exact — but inspecting the raw records
shows every non-empty gold cell was read as `''` (empty string), not a garbled digit. This is a
total output failure, not a language-model-quality finding: `settings.tessdata_dir` is recorded
as `/content/tessdata_best`, and level_a/level_b mismatch lists confirm `read=''` uniformly. The
engine's own `status` field says `ok` because tesseract exited 0 and produced a (empty) file —
this is exactly the class of failure that looks like a result but isn't, one level short of the
notebook's own try/except contract (which catches exceptions, not empty-but-successful output).
Root cause not chased further here (out of scope for this fold-in); flagged so nobody reads
"tessdata_best is unusably poor at Turkish digits" from this number — the correct reading is "this
notebook's tessdata_best invocation produced no output," a configuration bug, not a model result.

## Observed — level (a), page-level recall, and the VLM tier
| engine | recall /182 | percent /6 (a) | notes |
|---|---|---|---|
| rapidocr_onnxruntime 1x / rapidocr>=2.0 1x | 182/182 | 6/6 | full recall at page level |
| doctr (both variants) | 182/182 | 6/6 | full recall at page level |
| easyocr tr | 177/182 | 6/6 | |
| olmocr2 (allenai/olmOCR-2-7B-1025) | 174/182 | 6/6 (a) | HTML tables stripped to tokens; (a-row) only 21/193, structure not usable as-is |
| qwen2.5-vl-7b pages | 169/182 | 6/6 (a) | (a-row) approximate row-exact 167/193; percent crops 5/6 (one miss) |
| tesseract apt (both psm) | 175/182 | 0/6 | matches the local CPU smoke exactly (175/182, 0/6) |

The best two-engine union at level (a) is `rapidocr_onnxruntime:2x` + any tesseract variant at
182/182 (full recall), which is the same combination logic the shipped pipeline already uses
(RapidOCR for percent, tesseract for the rest) — this is a confirmation of the shipped
architecture's shape, not a new finding.

Qwen2.5-VL-7B and olmOCR-2 (both 7B GPU VLMs, 71-107 s/page, 16+ GB peak) underperform the
free CPU engines on this document even at the loose level-(a) metric. Neither is a viable OCR
replacement here.

## Decision-matrix impact
`decisions/decision-matrix.md` S1 OCR stage: no row changes to the shipped choice (tesseract TSV
primary + RapidOCR percent rescue stays the best-measured combination); added a comparison line
citing this run so the "why not PaddleOCR/EasyOCR/a VLM" question at the defense now has GPU
numbers on this exact document instead of README claims alone. `research/94.fact-ledger.md` S1
row gets this run's citation.

## What is still open
PaddleOCR PP-OCRv5 never actually ran (venv/pip environment failure) — this run answers "how does
PaddleOCR compare" with "not measured, not by design," same honesty standard as run-07's partial
coverage. Re-running just the PaddleOCR cell in an isolated environment would close this, but is
not blocking since PaddleOCR was already a REJECTED candidate on an independent basis (no TR
diacritics, per `research/10.ocr-engines.md` candidate 3 / decision-matrix S1).
