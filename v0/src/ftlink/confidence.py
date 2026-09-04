"""Stage S8: confidence, 0..1, at cell / row / table / relation level.

Never a raw model similarity (task requirement). Composition:
- cell      = OCR word confidence x numeric-parse confidence (repairs debit it),
- row       = mean of its cell confidences, debited when structure is doubtful,
- table     = mean row confidence x header/period completeness factor,
- relation  = weighted fusion of approach signals mapped through a logistic whose
              two parameters are fitted AT RUN TIME on control samples derived from
              the document itself (allowed by the task statement): decisions some
              fused approach accepted AND whose value reconciliation passes act as
              positives (consensus included, never exempted), decisively rejected
              candidates as negatives. With too few control points the fit falls
              back to fixed parameters and says so in the output.

Validation results feed back multiplicatively: a failing check on a participant
debits, a passing reconciliation slightly boosts (capped).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .linking import LinkDecision


@dataclass
class RelationConfidence:
    value: float
    components: dict[str, float]
    calibration: str  # fitted | fallback


FUSION_WEIGHTS = {"cross_encoder": 0.4, "value_rules": 0.4, "lexical": 0.2}


def fused_score(d: LinkDecision) -> float:
    return sum(FUSION_WEIGHTS[k] * d.approach_scores.get(k, 0.0) for k in FUSION_WEIGHTS)


def fit_platt(points: list[tuple[float, int]]) -> tuple[float, float] | None:
    """Tiny 1-D logistic regression by Newton steps; None when degenerate.

    Targets use Platt's (1999) prior smoothing, t+ = (n+ + 1)/(n+ + 2) and
    t- = 1/(n- + 2), which keeps the fit finite under perfectly separated
    controls, the normal situation at this control-set size."""
    pos = sum(1 for _, y in points if y == 1)
    neg = len(points) - pos
    if pos < 3 or neg < 3:
        return None
    t_pos = (pos + 1.0) / (pos + 2.0)
    t_neg = 1.0 / (neg + 2.0)
    a, b = 4.0, -2.0
    xs = [x for x, _ in points]
    ys = [t_pos if y == 1 else t_neg for _, y in points]
    for _ in range(50):
        ga = gb = haa = hab = hbb = 0.0
        for x, y in zip(xs, ys):
            p = 1.0 / (1.0 + math.exp(-(a * x + b)))
            ga += (p - y) * x
            gb += (p - y)
            w = p * (1 - p)
            haa += w * x * x
            hab += w * x
            hbb += w
        det = haa * hbb - hab * hab
        if abs(det) < 1e-9:
            return None
        da = (hbb * ga - hab * gb) / det
        db = (haa * gb - hab * ga) / det
        a, b = a - da, b - db
        if abs(da) + abs(db) < 1e-8:
            break
    if not (math.isfinite(a) and math.isfinite(b)) or a <= 0:
        return None
    return a, b


class RelationCalibrator:
    def __init__(self) -> None:
        self.params: tuple[float, float] | None = None
        self.mode = "fallback"
        self.n_pos = 0
        self.n_neg = 0
        self.control: list[tuple[float, int]] = []

    def fit_with_checks(self, decisions: list[LinkDecision], recon_status: list[str]) -> None:
        """Control samples derived from the document itself: a decision some fused
        approach accepted AND whose value reconciliation passes is a positive; a
        decision no fused approach accepted is a negative. EVERY positive, consensus
        included, requires the reconciliation signature (guarded circularity), and
        the optional LLM tier is decision-level, outside the calibrated fusion, so
        its acceptances neither create positives nor remove negatives here."""
        control: list[tuple[float, int]] = []
        for d, rs in zip(decisions, recon_status):
            accepted = any(v for k, v in d.approach_accepts.items() if k != "llm_select")
            if accepted and rs == "pass":
                control.append((fused_score(d), 1))
            elif not accepted and not d.approach_accepts.get("llm_select", False):
                # a pair only the LLM tier accepted is an emitted d_only relation,
                # not a decisive rejection: it enters NO control pool
                control.append((fused_score(d), 0))
        self.n_pos = sum(1 for _, y in control if y == 1)
        self.n_neg = len(control) - self.n_pos
        self.control = control
        fitted = fit_platt(control)
        if fitted is not None:
            self.params, self.mode = fitted, "fitted"
        else:
            self.params, self.mode = (6.0, -3.0), "fallback"

    @property
    def separated(self) -> bool | None:
        """True when every negative control scores below every positive (perfect
        separation), the regime that degenerates isotonic and unsmoothed fits;
        disclosed in the STR_CALIBRATION_CONTROLS detail. None without both classes."""
        pos = [s for s, y in self.control if y == 1]
        neg = [s for s, y in self.control if y == 0]
        if not pos or not neg:
            return None
        return max(neg) < min(pos)

    def loo_stability(self) -> dict[str, float] | None:
        """Jackknife over the control set: refit with each control point left out
        and report the worst movement of the calibrated curve at the control
        scores. The direct answer to 'how stable is a 2-parameter fit at this N'."""
        if self.mode != "fitted" or self.params is None or len(self.control) < 8:
            return None
        a0, b0 = self.params
        max_dp = 0.0
        degenerate = 0
        for i in range(len(self.control)):
            fit = fit_platt(self.control[:i] + self.control[i + 1:])
            if fit is None:
                degenerate += 1
                continue
            a, b = fit
            for x, _ in self.control:
                p_full = 1.0 / (1.0 + math.exp(-(a0 * x + b0)))
                p_loo = 1.0 / (1.0 + math.exp(-(a * x + b)))
                max_dp = max(max_dp, abs(p_loo - p_full))
        return {"loo_max_delta_p": round(max_dp, 4), "loo_degenerate_refits": degenerate}

    def venn_abers(self, x: float) -> tuple[float, float] | None:
        """Inductive Venn-ABERS interval [p0, p1] for a fused score: two isotonic
        fits over the control set with the test point appended as a negative and
        as a positive (Vovk & Petej 2014). The interval width is the honest
        statement of how much the calibration itself can be trusted at this size."""
        if self.n_pos < 3 or self.n_neg < 3:
            return None
        from sklearn.isotonic import IsotonicRegression

        out = []
        for label in (0, 1):
            xs = [c for c, _ in self.control] + [x]
            ys = [y for _, y in self.control] + [label]
            iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
            iso.fit(xs, ys)
            out.append(float(iso.predict([x])[0]))
        p0, p1 = min(out), max(out)
        return round(p0, 4), round(p1, 4)

    def confidence(self, d: LinkDecision, recon_status: str = "not_evaluable") -> RelationConfidence:
        a, b = self.params if self.params else (6.0, -3.0)
        x = fused_score(d)
        p = 1.0 / (1.0 + math.exp(-(a * x + b)))
        # validation feedback without saturation: a passing reconciliation shrinks
        # the remaining doubt by 15 percent (never reaches 1.0); a failing one
        # debits the probability itself; not-evaluable applies a mild debit
        p_raw = p
        if recon_status == "pass":
            p = 1.0 - 0.85 * (1.0 - p)
        elif recon_status == "fail":
            p = 0.6 * p
        else:
            p = 0.9 * p
        p = max(0.0, min(1.0, p))
        components = {
            **{k: round(d.approach_scores.get(k, 0.0), 4) for k in FUSION_WEIGHTS},
            "fused": round(x, 4),
            "reconciliation": {"pass": 1.0, "fail": 0.0}.get(recon_status, 0.5),
            "validation_factor": round(p / p_raw, 4) if p_raw > 1e-9 else 0.0,
        }
        va = self.venn_abers(x)
        if va is not None:
            components["venn_abers_p0"], components["venn_abers_p1"] = va
        return RelationConfidence(
            value=round(p, 4),
            components=components,
            calibration=self.mode,
        )


def cell_confidence(ocr_conf: float, parse_conf: float) -> float:
    return round(max(0.0, min(1.0, ocr_conf * parse_conf)), 4)


def row_confidence(cell_confs: list[float], structure_penalty: float = 0.0) -> float:
    if not cell_confs:
        return 0.3
    base = sum(cell_confs) / len(cell_confs)
    return round(max(0.0, min(1.0, base * (1.0 - structure_penalty))), 4)


def table_confidence(row_confs: list[float], periods_found: int, periods_expected: int) -> float:
    if not row_confs:
        return 0.2
    base = sum(row_confs) / len(row_confs)
    completeness = periods_found / periods_expected if periods_expected else 1.0
    return round(max(0.0, min(1.0, base * (0.7 + 0.3 * completeness))), 4)
