"""Calibration report on the run-time control set: leave-one-out Brier and the
Venn-ABERS interval with and without the relation's own control label.

The pipeline fits its relation calibrator on controls derived from the document
itself (README section 6). This script re-runs the default configuration, captures
that control set, and reports what the README deliberately does not headline:

- Brier scores (constant base rate, raw fused score, in-sample smoothed Platt,
  leave-one-out smoothed Platt), with a quartile reliability table of the LOO map;
- for every emitted relation, the Venn-ABERS interval as shipped (computed with the
  relation's own control label present, because the controls ARE the emitted
  decisions) next to a leave-self-out interval (that label removed).

Development measurement, not a shipped number: at 33 controls these values move
with every control point, which is exactly what the jackknife in the output says.
Run after setup (about 40 seconds, one pipeline run): uv run python eval/calibration_loo.py
"""
from __future__ import annotations

import math
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]


def brier(ps: list[float], ys: list[int]) -> float:
    return sum((p - y) ** 2 for p, y in zip(ps, ys)) / len(ys)


def main() -> int:
    import ftlink.confidence as C
    import ftlink.pipeline as P
    from ftlink.config import Settings

    captured: dict = {}
    orig = C.RelationCalibrator.fit_with_checks

    def spy(self, decisions, recon_status):
        orig(self, decisions, recon_status)
        captured["calib"] = self

    C.RelationCalibrator.fit_with_checks = spy
    merged = yaml.safe_load((ROOT / "configs/default.yaml").read_text(encoding="utf-8"))
    merged["document"]["pdf_path"] = str(ROOT / merged["document"]["pdf_path"])
    merged["output"]["dir"] = tempfile.mkdtemp(prefix="ftlink_cal_")
    merged["output"]["emit_report_html"] = False
    try:
        out = P.run(Settings(**merged))
    finally:
        C.RelationCalibrator.fit_with_checks = orig
    calib = captured["calib"]
    control = list(calib.control)
    xs = [x for x, _ in control]
    ys = [y for _, y in control]
    n, npos = len(ys), sum(ys)
    if calib.mode != "fitted" or calib.params is None:
        print(f"CONTROLS: n={n} positives={npos} negatives={n - npos} mode={calib.mode}: no fitted map to evaluate")
        return 0
    a, b = calib.params
    print(f"CONTROLS: n={n} positives={npos} negatives={n - npos} mode={calib.mode} "
          f"platt_a={a:.4f} platt_b={b:.4f} separated={str(calib.separated).lower()}")
    base = npos / n
    print(f"BRIER constant base rate ({base:.3f}): {base * (1 - base):.4f}")
    print(f"BRIER raw fused score read as a probability: {brier(xs, ys):.4f}")
    ins = [1.0 / (1.0 + math.exp(-(a * x + b))) for x in xs]
    print(f"BRIER in-sample smoothed Platt: {brier(ins, ys):.4f}")
    loo: list[float] = []
    degenerate = 0
    for i in range(n):
        fit = C.fit_platt(control[:i] + control[i + 1:])
        if fit is None:
            degenerate += 1
            loo.append(ins[i])
            continue
        aa, bb = fit
        loo.append(1.0 / (1.0 + math.exp(-(aa * xs[i] + bb))))
    print(f"BRIER leave-one-out smoothed Platt: {brier(loo, ys):.4f} (degenerate refits: {degenerate})")
    order = sorted(range(n), key=lambda i: loo[i])
    for j in range(4):
        idx = order[j * n // 4:(j + 1) * n // 4]
        if idx:
            print(f"  LOO quartile {j + 1}: mean_pred={sum(loo[i] for i in idx) / len(idx):.3f} "
                  f"frac_pos={sum(ys[i] for i in idx) / len(idx):.3f} n={len(idx)}")
    print("VENN-ABERS per emitted relation: as shipped (own control label present) vs leave-self-out")
    for r in out.relations:
        x = r.confidence_components.get("fused")
        if x is None:
            continue
        # components round the fused score to 4 decimals; the interval must be evaluated
        # at the EXACT control score, otherwise the tie with the relation's own label breaks
        own = next((k for k, (cx, cy) in enumerate(control) if cy == 1 and abs(cx - x) < 1e-4), None)
        if own is not None:
            x = control[own][0]
        va_in = calib.venn_abers(x)
        if own is None:
            va_out, tag = va_in, "not a control point"
        else:
            c2 = C.RelationCalibrator()
            c2.control = control[:own] + control[own + 1:]
            c2.n_pos, c2.n_neg = npos - 1, n - npos
            va_out, tag = c2.venn_abers(x), "own label removed"
        print(f"  {r.relation_id} fused={x:.4f} confidence={r.confidence:.4f} "
              f"shipped={va_in} leave_self_out={va_out} ({tag})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
