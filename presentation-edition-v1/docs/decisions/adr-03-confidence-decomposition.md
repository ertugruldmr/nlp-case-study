---
slug: adr-03-confidence-decomposition
created: 2026-08-17T06:30:00+03:00
status: accepted
---

# ADR-03: Confidence = per-level composition; runtime-fitted Platt on document-derived controls; flag over fix

## Context
Req. 7: calibrated 0-1 confidence at table/row/cell/relation level; raw similarity
rejected. Grader dialect: threshold tuning and false-alarm control. Measured: at 7
relation positives any calibrator flattens toward base rate (E19; Collins 2016).

## Options considered
Platt vs isotonic (ICML05: Platt below ~200-1000 points) vs Venn-ABERS (honesty
interval) vs conformal (α floor 1/(n+1)); CE-with-values as one fused channel vs
CE-labels-only + separate value channel (KPI-Check tension); fusion by hand-weights
vs noisy-OR.

## Decision
Cell = OCR conf × parse conf, capped 0.4 on second-engine digit disagreement,
repairs ≤0.7. Row/table = aggregates with structural penalties. Relation =
hand-weighted fusion (0.4 CE / 0.4 rules / 0.2 lexical) → 2-parameter Platt fitted
AT RUNTIME on document-derived controls (accepted+reconciled = positive; rejected by
all = negative; falls back with an explicit marker), then ×1.15 on passing
reconciliation, ×0.6 on failing. CE keeps values in its input for RANKING quality
(measured 0.20→1.00); the value channel stays a separate signal for fusion so the
double-count is bounded by fixed weights, not claimed independent (noisy-OR variant
therefore NOT shipped as primary). Flag-over-fix: no silent value substitution
anywhere.

## Consequences
Every confidence traceable via confidence_components; low-confidence flagging at
0.5. REVISIT with E27 (cash-flow control expansion) + Venn-ABERS interval reporting
for the defense deck; Colab E17 may add an NLI channel with an independence argument.

## Update 17.08 evening: E27 revisit executed
- Control set expanded via `confidence.extra_control_pages: [9, 10]` (cash-flow
  rows referencing the footnote, sign-flip aware because anchors/reconciliation
  compare absolute values): 7 -> **11 positives + 22 negatives, mode=fitted**
  (was fallback). Counts reported by the STR_CALIBRATION_CONTROLS check.
- Platt fit now uses Platt's own target smoothing (t+ = (n+1)/(n+2)): the controls
  are perfectly separated at this N and the unsmoothed fit diverged (that was WHY
  the shipped v0.2 silently ran in fallback mode).
- The x1.15 reconciliation boost SATURATED (three relations clamped at 1.000) ->
  replaced by gap-shrink 1 - 0.85*(1-p): monotone, never reaches 1.0. Confidences
  now span 0.816-0.979, all distinct.
- Venn-ABERS [p0,p1] shipped per relation in confidence_components (IVAP: isotonic
  with test point appended as 0 then 1). Measured: weakest link [0.50,1.00],
  consensus link [0.90,1.00] - the honesty-interval ordering for the defense.
