---
slug: adr-01-extraction-stack
created: 2026-08-17T06:30:00+03:00
status: accepted
---

# ADR-01: Extraction stack = tesseract TSV + deterministic x-clustering (+ RapidOCR digit verify)

## Context
Source is a 95-page image-only scan; tables are borderless with stacked headers;
three notes pages are rotated 270°. Requirements: re-runnable by a bank grader on
CPU, cell-level confidence inputs, page/footnote from config.

## Options considered
[[decision-matrix]] S1/S3 rows: tesseract-TSV+x-cluster (shipped) vs TATR v1.1-fin
(pending Colab E5) vs docling/TableFormer (pending E7) vs VLM tier (API) vs
PP-Structure (rejected: macOS ARM segfaults) vs camelot-class (no text layer) vs
surya/jina (license-gated).

## Decision
Ship tesseract 5 tur TSV (300dpi/psm4, LOCKED by E2 grid: 154/156 values verbatim;
400dpi worse) + orientation recovery + deterministic x-clustering (columns from
numeric right edges, dashes second-pass, label-fragment/section-header handling) +
RapidOCR per-cell digit cross-check (optional extra, flag-over-fix). Measured:
92.5% exact cells, zero silent errors, both real OCR corruptions flagged.

## Consequences
No GPU, no heavyweight deps, fully deterministic. REVISIT when Colab E5/E7 results
land: if TATR GriTS beats x-cluster materially on p53/54, add it as configurable
primary (engine choice already isolated behind extract_tables()).

## Update 17.08 evening (v0.3): residual gaps CLOSED
Percent-table degradation and label-less/group-header rows are fixed and measured
([[percent-rescue]]): S3b swaps engine roles on rate rows (RapidOCR 6/6 vs
tesseract 0/6 on % glyphs, probe-measured before wiring), and an indent rule
separates wrapped-label continuations (+18 px) from group headers (aligned).
Cells 92.5% -> 99.0% exact; the 2 remaining wrongs are the two flagged real
corruptions (the zero-silent-error contract). rapidocr/onnxruntime promoted to
base dependencies: `uv run`'s exact sync uninstalls extras, which would silently
drop the verification stage on the grader's default path.
