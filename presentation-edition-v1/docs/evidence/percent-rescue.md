---
slug: percent-rescue
candidate: "S3b percent rescue (engine swap on rate rows) + intra-segment label/header rule + scorer fairness fixes"
created: 2026-08-17T18:30:00+03:00
verified: 2026-08-17T18:30:00+03:00
status: aging
status_reviewed: 2026-08-29
claim: "The three residual extraction gaps (percent table, dağılım group headers, wrapped label) are closable without touching the money path"
verdict: works
sources:
  - research/assets/experiments/percent_rescue_probe.py (measured probe)
  - deliverable/src/ftlink/percent.py · table_structure.py (merge_label_rows)
  - deliverable/eval/score.py (empty-label + twin-row mapping fixes)
tags: [implementation, measured, G2, G3]
---

# Percent rescue + label/header rule: 92.5% -> 99.0% exact cells (E28)

## Probe (measured, page 54 crops, before any code)
tesseract CANNOT read the % glyph on this scan class in any configuration:
psm7+whitelist 300dpi: `9, 710,5, 086,6, 80,8, 3, 42-4` · 600dpi: `49, 10,5,
086,6, 480,8, 3, 02-4`. RapidOCR reads the SAME crops 6/6 verbatim: `%9, %10,5,
%86,6, %80,8, %3, %2-%4` (both dpi). Design follows the measurement: for rate
rows the engines swap roles (RapidOCR reads, tesseract votes). Tesseract's
corruption is always a digit PREFIX artifact -> vote = exact-or-suffix digit match.

## Shipped (deliverable v0.3)
- `percent.py`: rate-row cell crops re-read by RapidOCR; tesseract psm7 whitelist
  vote; dropped rate lines re-collected below the table bbox; phantom footnote refs
  (%9 -> "49" masqueraded as dipnot ref 49) removed when inside a value window.
  Measured on default run: 6 cells rescued, 2 exact + 4 suffix votes, 0 mismatch,
  1 row re-collected (kira artış). Config: `ocr.percent_rescue` (default true).
- `merge_label_rows` indent rule: intra-segment text-only lines are captured; a
  continuation row indents past its fragment (+18 px measured), a group header's
  followers stay at its left edge. Fixes BOTH the truncated wrapped label
  (Özkaynak ... Paylar) and the two missing Dağılımı group-header rows.
- `FMT_PERCENT_BOUNDS` format check: percents must lie in [0,100], ranges ascend;
  catches the 486,6 corruption class if the rescue ever regresses.
- Scorer fairness fixes (eval/score.py): empty-label gold rows disambiguated by
  value overlap (both label-less totals used to map to the same extracted row);
  twin-table rows with identical labels (2012/2011 movement tables) kept as lists
  and split by value overlap (the dict used to overwrite one twin, converting a
  correct prediction into a phantom fn).

## Measured results (make run + make eval, 17.08 evening)
- Cells: **199/201 = 99.0% exact** (was 92.5). The 2 remaining wrongs are the two
  real OCR corruptions, both flagged (Stoklar digit: engine disagreement cap 0.4 +
  parent-sum +400.000; separator 4,224: parent-sum .224 residue). ZERO silent errors.
- T3 percent table: **6/6 exact** (was 1/6). G3 closed above target (>=5/6).
- Relations: **P=1.00 R=1.00, no ambiguity asterisk** (was R=0.86 nominal).
- Checks: 96 pass / 4 fail / 6 not_evaluable; all 4 fails genuine catches.
  Percent-rescue doc check: pass (0 mismatches).
- Determinism: two runs byte-identical ex-run-block. Tests 21/21 (4 new).
- alt_footnote (12) demo: same profile (8 tables / 251 cells / 1 relation);
  rescue correctly skips rotated pages (unavailable path).

## Fresh-clone bugs found & fixed on the way (G6 input)
1. `make test` failed on a fresh env: pytest lived in an optional extra and
   `uv run`'s exact sync UNINSTALLS extras -> moved to `[dependency-groups]` dev.
2. `make eval` was a silent no-op: target not in .PHONY while an `eval/` directory
   exists -> make judged it "up to date". Added to .PHONY.
3. rapidocr/onnxruntime were an optional extra, but `uv run ftlink` removes extras
   at sync, silently degrading the headline S1b verification -> promoted to base
   dependencies (the default grader path must carry the flag-over-fix stage).

## Defense framing
- "The document told us which engine to trust where": engine choice is per-glyph-
  class and MEASURED (money digits: tesseract wins; % glyphs: RapidOCR 6/6 vs 0/6).
- Flag-over-fix held: the rescue never overrides money cells (only a percent-kind
  reading may replace a primary read); both engine readings live in the components.
- Accuracy ceiling reached: 99.0% is the maximum consistent with zero silent
  substitution; the last 2 cells are deliberately wrong-but-flagged.
