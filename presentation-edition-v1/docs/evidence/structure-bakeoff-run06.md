---
slug: structure-bakeoff-run06
candidate: "E71: run-06 GPU structure engine bake-off (TATR, docling TableFormer, PaddleOCR PP-StructureV3, Qwen2.5-VL-7B) against gold on the same 201 value cells the shipped scorer uses"
created: 2026-08-30T23:35:00+03:00
verified: 2026-08-30T23:35:00+03:00
status: fresh
claim: "Does any off-the-shelf table-structure engine beat the shipped x-clustering (199/201, 99.0%, CPU-only) on the five gold pages?"
verdict: works
sources:
  - research/assets/experiments/colab/run-06-structure-bakeoff/nb6_structure_results.json
  - research/assets/experiments/colab/run-06-structure-bakeoff/nb6_structure_bakeoff_ckpt.ipynb (S2 scorer source, read directly)
  - research/assets/experiments/colab/run-06-structure-bakeoff/README.md
  - deliverable/README.md (section 9, scorer conventions)
  - deliverable/eval/score.py (shipped scorer, read directly)
  - "[[heavy-evidence-run01]] (E47), [[run01-e5-e7-failure-diagnosis]] (E69)"
  - handoff/RUN0678-FOLDIN-PLAN.md
tags: [measured, colab, gpu, structure, tatr, docling, paddleocr, vlm, E71]
---

# E71: run-06 structure bake-off, GPU, landed 30.08 (1044s wall, NVIDIA L4)

## Test setup
`colab-ops/run.sh run-06-structure-bakeoff all`, landed clean (ok, 1044s). Four engines over
the five gold pages (5, 6, 7, 53, 54; seven gold tables): TATR v1.1-fin at detection thresholds
0.3/0.5/0.7 + NMS 0.5 + tesseract; docling TableFormer ACCURATE + `TesseractCliOcrOptions(tur)`;
PaddleOCR PP-StructureV3 in an isolated venv; Qwen2.5-VL-7B-Instruct bf16 prompted to HTML.
Result file: `research/assets/experiments/colab/run-06-structure-bakeoff/nb6_structure_results.json`.

## Scoring methodology, verified directly against the shipped scorer (do not skip this section)
The notebook's own README (this folder) explicitly asks that the 201-cell comparison be checked
before being read as a clean head-to-head, and it is right to ask: **the two scorers are not the
same algorithm**, even though both count "exact cells out of 201."

- **Shipped scorer** (`deliverable/eval/score.py`, read directly): maps predicted rows to gold
  rows by normalized-label matching first (with a fallback for headerless total rows), then per
  value cell checks `state` equality (`empty`/`dash`/`number` are distinct outcomes, "wrong_state"
  is its own bucket) and, for `number` cells, EITHER float equality of the parsed value OR
  raw-string equality after stripping parens. It is a **row-identity + numeric-value scorer**.
- **run-06's `exact_cells()`** (S2 cell, read directly out of the checkpoint notebook): finds
  row/column correspondence by maximizing a GriTS-style structural alignment (`factored_2dmss`
  over `rapidfuzz.distance.Indel.normalized_similarity`), then checks **normalized-string
  equality** of the aligned cell text against gold text (Unicode NFC, dash/İ normalization,
  lowercase, whitespace-stripped; no numeric parsing). It is an **alignment + text-match scorer**.

Practical effect: run-06's check is textually stricter on pure formatting drift (it does not
parse `1.234` and `1234` as the same number the way the shipped scorer's float path does) but
does not need label-matched rows to work, which the shipped scorer requires. On this document the
gold cell texts are already the shipped pipeline's own canonical formatting (dot-grouped,
parenthesized negatives), so the two scorers should agree on any engine that reproduces that
formatting exactly, and the practical gap is small — but it is not zero, and it has not been
measured directly (no side-by-side rerun of both scorers on the same predicted grid exists yet).
**Conclusion: the 199/201 vs 187/151/165/201 comparison below is same-denominator and
same-question, not same-algorithm. Treat the ranking (which engine is closer to gold) as solid;
treat exact percentage-point gaps between rows as approximate, not certified equal.** This is
exactly the caveat the run-06 README itself asked for.

## Observed — headline table (S7:summary `totals`, quoted verbatim from the JSON)
| engine | exact cells | share | note |
|---|---|---|---|
| shipped ftlink x-clustering (deliverable README, not recomputed by this notebook) | 199 / 201 | 99.0% | CPU only |
| Qwen2.5-VL-7B-Instruct to HTML | 187 / 201 | 93.0% | bf16, GPU 23.7 GB, 406.9 s total (73-124 s/page) |
| docling TableFormer ACCURATE + tesseract-tur | 165 / 201 | 82.1% | CPU+tesseract, 25.1 s total, no threshold tuning |
| TATR v1.1-fin best config (det>=0.3, NMS 0.5) | 151 / 201 | 75.1% | page 54 never detected at any threshold |
| PaddleOCR PP-StructureV3 | not run | - | `status: failed`, `"note": "no result from runner"` on all 5 pages — reported as "not run (reason)", not as "worse", per the fold-in plan's rule 4 |

The shipped baseline row is copied into the JSON from the deliverable README, not independently
recomputed by this notebook (the JSON's own `baseline.source` field says so) — it is not a fifth
engine run through the same code path, it is the number this bake-off is measured against.

## Observed — docling and the VLM are genuinely strong, not failing
Per-page docling: reaches the gold ceiling class on pages 5 (35/36) and stays close on 6 (52/58)
and 7 (41/58); its weakest page is 54 (10/16), still 62.5%. Per-page Qwen2.5-VL: recovers every
value cell on pages 7 (52/58 — wait, verified below), 53 (33/33) and 54 (16/16) exactly, and 56/58
on page 6. Correction on page 7: the JSON's per-page row shows Qwen2.5-VL at 52/58 on page 7, not
a clean sweep there; pages 53 and 54 are the two clean sweeps (33/33 and 16/16). Both engines are
correctly described as strong, off-the-shelf, GPU-requiring challengers that fall short of the
shipped CPU-only pipeline on this specific document — not as failures.

## Observed — TATR: detection-configuration weakness, not structural weakness, and a real threshold cliff
Per-page GriTS-top against its own printed-table ceiling (`grits_top_ceiling` in S2:gold), only
where TATR detects at all (det>=0.3):
| page | grits_top | ceiling | ratio |
|---|---|---|---|
| 5 | 0.8308 | 0.831 | 1.00 (at ceiling) |
| 6 | 0.7945 | 0.841 | 0.94 |
| 7 | 0.7611 | 0.841 | 0.90 |
| 53 (dipnot11_t1 only, t2 unmatched) | 0.7948 | 0.923 | 0.86 |
| 54 | 0.0 (never detected) | 0.857 / 0.909 | - |

Where TATR detects, its structure quality sits close to or at the printed-table ceiling (exactly
at ceiling on page 5, 86-94% of ceiling elsewhere) — the deficit is concentrated in *whether it
fires at all*, not in row/column recognition once it does. **The correct framing is "TATR's
weakness is detection configuration, not structural quality" (page 54 confirms this: 0 detections
at every threshold, so 0 structure to evaluate there at all).**

The threshold cliff is stark and reproduces exactly (quoted from S7:summary rows): page 7 gives
grits_top 0.7611 at det>=0.3 and 0.0 at det>=0.5 and det>=0.7; page 53 gives 0.7948 / 0.3947 / 0.0
across 0.3 / 0.5 / 0.7. A single hyperparameter moves TATR between usable and nothing on this
document — a real argument for a deterministic geometry method's re-runnability over a tuned
detector, independent of the accuracy gap.

**Does not replicate E50 cell-for-cell, and the gap is itself a finding.** [[tatr-local-structure]]
(E50) pre-downscaled to 1600px and detected 1 of 5 pages at threshold 0.7; this run's own local
CPU pre-check (logged separately by a peer session against native 2481px renders) found 3 of 5;
run-06 itself, at 1600px (its own canonical setup, per its README), agrees with E50: **1 of 5
pages at threshold 0.7 (page 6 only)**. TATR's detector is scale-sensitive at a fixed threshold —
now confirmed twice at 1600px (E50 and run-06) against once at native resolution (the local
peer check), so 1600px / 1-of-5 is the reference figure, not the native-resolution 3-of-5.

TATR is out of domain here regardless of threshold: trained on PubTables-1M / FinTabNet
(error-corrected, arXiv:2303.00716), both born-digital, against a 300dpi scanned Turkish audit
report. Worth stating unprompted at the defense — the honest claim is "TATR off the shelf
underperforms on this document," not "TATR is a bad model" or "TATR is bad at structure."

## ADR-01 final resolution
Per `RUN0678-FOLDIN-PLAN.md`'s pre-registered rule ("a structure engine becomes a recommended
config-gated upgrade only if it implies at least 199/201 exact cells AND detects all 7 gold
tables AND runs on CPU or states its GPU need honestly"): **no challenger clears the bar.** Best
challenger (Qwen2.5-VL-7B, 187/201, 93.0%) needs a GPU and still falls 12 cells short; docling
(165/201) needs no GPU tuning but falls further short; TATR (151/201) additionally misses tables
outright; PaddleOCR did not run at all. **Verdict: shipped x-clustering is KEPT, no code change
before the send.** This supersedes the local-only, detection-count-based finding this note's
predecessor ([[run01-e5-e7-failure-diagnosis]], E69) recorded — the reasoning is now a clean
201-cell head-to-head (with the scorer-methodology caveat above) rather than a proxy on detection
counts alone, and the verdict direction is unchanged (x-clustering wins) but for a stronger and
more specific reason.

## Failure notes
PaddleOCR PP-StructureV3 failed on all 5 pages with only `"no result from runner"` recorded — no
traceback captured for this candidate (the isolated `pp-venv` runner script's own error handling
did not propagate one). This is itself worth a line in `ISSUES-AND-STUCK-POINTS.md`: a fourth
candidate for the ≥3 failure-case analysis, distinct from run-01's silent-key class because here
the failure IS recorded (`status: failed`), just without a diagnosable cause. Not pursued further
since PaddleOCR was never going to beat the 199/201 bar even at its best plausible number, and the
plan's rule 4 ("not run (reason)", never "worse") already covers how to report it.

## Decision-matrix impact
`decisions/decision-matrix.md`: TATR row superseded from the local-only E69 finding to this GPU
head-to-head (75.1%, detection-configuration framing, threshold cliff); docling row updated from
"untried" to measured (82.1%, no tuning, genuinely strong); PaddleOCR row (if any) updated to "not
run, no runner output"; Qwen2.5-VL added as a new row (93.0%, best challenger, GPU-requiring).
`research/94.fact-ledger.md` S3/S6 structure rows updated. `research/95.defense-qa.md`: new
addition with the scorer-methodology caveat, the detection-vs-structure framing, and the
threshold-cliff slide material. `ISSUES-AND-STUCK-POINTS.md` W1 closed (ADR-01 fully resolved).
No deliverable change. Deck/PPTX "bekliyor" cell regeneration for run-06 deferred to the
post-campaign batch (shared cells with run-07/08), per the same batching decision already applied
to run-01's fold-in.
