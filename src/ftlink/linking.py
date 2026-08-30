"""Stage S7: linking. Three approaches, always all run, compared in the output.

A  cross_encoder : multilingual cross-encoder over "label | values" pair texts.
                   Including the values in the pair text is a measured design choice:
                   movement-table rows are labeled by dates and roles, not by the
                   item name, and only value context lets a text model rank them.
B  value_rules   : deterministic value+role reasoning. A summary item's period value
                   matching a footnote row is accepted when the row's ROLE is
                   consistent: stock values bind to opening/closing/total rows,
                   flow values bind to flow rows. No ML, fully explainable.
C  lexical       : rapidfuzz label matching after Turkish normalization; C is the
                   deliberately insufficient baseline the task statement predicts,
                   kept to show WHERE it fails (word-level zero-overlap pairs).

Agreement classes over accepted sets feed the comparison and the confidence stage.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from rapidfuzz import fuzz

from .candidates import Candidate, SideRow
from .normalize import tr_lower


@dataclass
class LinkDecision:
    summary_row_id: str
    footnote_row_id: str
    period_scope: str
    relation_type: str
    approach_scores: dict[str, float] = field(default_factory=dict)
    approach_accepts: dict[str, bool] = field(default_factory=dict)
    approach_ranks: dict[str, int] = field(default_factory=dict)
    agreement: str = "none"
    evidence: str = ""


STOCK_ROLES = {"opening", "closing", "closing_equiv", "total"}


def apply_llm_acceptance(d: LinkDecision, hit: bool) -> None:
    """Fold an approach-D (LLM select) verdict into a decision. D is decision-level:
    it can admit a pair every fused approach rejected, and that class must be
    visible in the output taxonomy as d_only rather than leaking out as none."""
    d.approach_scores["llm_select"] = 1.0 if hit else 0.0
    d.approach_accepts["llm_select"] = hit
    if hit and d.agreement == "none":
        d.agreement = "d_only"


def _relation_type(role: str) -> str:
    if role in ("opening", "closing", "closing_equiv"):
        return "balance_reconciliation"
    if role == "total":
        return "total_reconciliation"
    return "flow_match"


class Linker:
    def __init__(self, cross_encoder_model: str, accept_threshold: float = 0.5,
                 lexical_threshold: float = 0.75, revision: str | None = None,
                 rank1_min_score: float = 0.2) -> None:
        self.ce_name = cross_encoder_model
        self.ce_revision = revision
        self.accept_threshold = accept_threshold
        self.lexical_threshold = lexical_threshold
        self.rank1_min_score = rank1_min_score
        self._ce = None
        self.ce_available = True

    def _ce_scores(self, pairs: list[tuple[str, str]]) -> list[float]:
        if self._ce is None:
            try:
                from sentence_transformers import CrossEncoder

                # weights pinned to a snapshot hash: lockfile pins packages only
                self._ce = CrossEncoder(self.ce_name, revision=self.ce_revision)
            except Exception:
                # cannot load (offline first run, wrong platform): approach A
                # scores zero and accepts nothing; approach B still links, the
                # run block records the missing model and every relation ships
                # force-flagged (degrade loudly, never crash the whole run)
                self._ce = False
                self.ce_available = False
        if self._ce is False:
            return [0.0] * len(pairs)
        import numpy as np

        raw = self._ce.predict(pairs, batch_size=16)
        return [float(1 / (1 + np.exp(-s))) for s in raw]

    def link(self, candidates: list[Candidate], summary: dict[str, SideRow],
             footnote: dict[str, SideRow], summary_is_flow: dict[str, bool]) -> list[LinkDecision]:
        if not candidates:
            return []

        def fmt(v) -> str:
            # Turkish grouping, matching how amounts print in the document; the
            # cross-encoder was validated with dot-grouped pair texts
            whole = f"{abs(int(v)):,}".replace(",", ".")
            frac = abs(v) - abs(int(v))
            if frac:
                whole += "," + f"{frac}".split(".")[-1]
            return f"({whole})" if v < 0 else whole

        def pair_text(r: SideRow) -> str:
            vals = " ; ".join(fmt(v) for v in r.values.values())
            return f"{r.label} | {vals}" if vals else r.label

        ce_scores = self._ce_scores([
            (pair_text(summary[c.summary_row_id]), pair_text(footnote[c.footnote_row_id]))
            for c in candidates
        ])

        # per-summary-row CE ranks: absolute sigmoid thresholds vary by model, the
        # rank ordering is the validated signal, so rank 1 with a clear margin also
        # counts as acceptance
        by_summary: dict[str, list[tuple[int, float]]] = {}
        for i, (c, ce) in enumerate(zip(candidates, ce_scores)):
            by_summary.setdefault(c.summary_row_id, []).append((i, ce))
        ce_rank: dict[int, int] = {}
        for sid, lst in by_summary.items():
            for rank, (i, _) in enumerate(sorted(lst, key=lambda t: -t[1]), start=1):
                ce_rank[i] = rank

        decisions: list[LinkDecision] = []
        for idx, (c, ce) in enumerate(zip(candidates, ce_scores)):
            s, f = summary[c.summary_row_id], footnote[c.footnote_row_id]

            # B: value+role rules
            role_ok = (f.role in STOCK_ROLES) if not summary_is_flow.get(s.row_id, False) else (f.role == "flow")
            b_accept = bool(c.anchor_periods) and role_ok
            b_score = 1.0 if b_accept else (0.5 if c.anchor_periods else 0.0)

            # C: lexical baseline
            c_score = fuzz.token_set_ratio(tr_lower(s.label), tr_lower(f.label)) / 100.0
            c_accept = c_score >= self.lexical_threshold

            a_accept = ce >= self.accept_threshold or (
                ce_rank.get(idx, 99) == 1 and ce >= self.rank1_min_score)

            accepts = {"cross_encoder": a_accept, "value_rules": b_accept, "lexical": c_accept}
            n = sum(accepts.values())
            if n == 0:
                agreement = "none"
            elif accepts["cross_encoder"] and accepts["value_rules"]:
                agreement = "consensus"
            elif accepts["cross_encoder"]:
                agreement = "a_only"
            elif accepts["value_rules"]:
                agreement = "b_only"
            else:
                agreement = "baseline_only"

            period_scope = "both" if len({p for p, _ in c.anchor_periods}) > 1 else (
                c.anchor_periods[0][0] if c.anchor_periods else "unscoped")

            decisions.append(LinkDecision(
                summary_row_id=s.row_id, footnote_row_id=f.row_id,
                period_scope=period_scope,
                relation_type=_relation_type(f.role) if c.anchor_periods else "semantic",
                approach_scores={"cross_encoder": ce, "value_rules": b_score, "lexical": c_score},
                approach_accepts=accepts,
                approach_ranks={"cross_encoder": ce_rank.get(idx, 0)},
                agreement=agreement,
                evidence=(f"value match {c.anchor_periods}" if c.anchor_periods else "semantic only")
                + f"; footnote row role={f.role}",
            ))
        return decisions
