"""Stage S9: self-checking validation, three groups.

STRUCTURAL: pages verified against config, period columns present and in the
            document's descending order, footnote references are plausible note
            numbers, located footnote heading verified.
FORMAT:     numeric round-trip re-parse, three-state legality, repaired-value flags.
FINANCIAL:  movement roll-forward per footnote table (opening + flows = closing,
            per column), row-wise category sums (leftmost columns add to a Toplam
            column), block sums in summary tables (a total row equals the sum of
            deeper-indented rows since the previous total), and summary-to-footnote
            reconciliation for accepted relations.

A check that cannot be evaluated reports not_evaluable, never a silent pass, and
never treats a missing operand as zero.
"""
from __future__ import annotations

from decimal import Decimal

from .models import CheckResult


class AssembledRow:
    """Minimal view the validator needs (built by the pipeline)."""

    def __init__(self, row_id: str, label: str, role: str, indent: int,
                 values: dict[str, Decimal | None], states: dict[str, str],
                 repaired: dict[str, bool]) -> None:
        self.row_id = row_id
        self.label = label
        self.role = role
        self.indent = indent
        self.values = values      # period -> Decimal or None (dash/empty)
        self.states = states      # period -> number|dash|empty
        self.repaired = repaired  # period -> bool


def check_structural(table_id: str, periods: list[str], expected_desc: bool,
                     dipnot_refs: list[int], located_verified: bool | None) -> list[CheckResult]:
    out: list[CheckResult] = []
    years = [int(p) for p in periods if p.isdigit()]
    if len(years) >= 2:
        out.append(CheckResult(
            check_id="STR_PERIOD_ORDER", group="structural", scope=table_id,
            status="pass" if years == sorted(years, reverse=True) else "fail",
            detail=f"periods={years}"))
    else:
        out.append(CheckResult(check_id="STR_PERIOD_ORDER", group="structural", scope=table_id,
                               status="not_evaluable", detail=f"periods={periods}"))
    bad_refs = [r for r in dipnot_refs if not (1 <= r <= 99)]
    out.append(CheckResult(check_id="STR_REF_RANGE", group="structural", scope=table_id,
                           status="fail" if bad_refs else "pass", detail=f"bad={bad_refs}"))
    if located_verified is not None:
        out.append(CheckResult(check_id="STR_FOOTNOTE_HEADING", group="structural", scope=table_id,
                               status="pass" if located_verified else "fail"))
    return out


def check_percent_bounds(cells) -> list[CheckResult]:
    """FORMAT: values parsed as percents must lie in [0, 100]; ranges must ascend.
    Catches the measured %-glyph corruption class (%86,6 read as 486,6)."""
    out: list[CheckResult] = []
    for c in cells:
        v = c.value
        if v.state != "number" or v.kind not in ("percent", "percent_range"):
            continue
        ok = 0 <= v.value <= 100
        if v.value_high is not None:
            ok = ok and v.value <= v.value_high <= 100
        out.append(CheckResult(check_id="FMT_PERCENT_BOUNDS", group="format",
                               scope=c.cell_id, status="pass" if ok else "fail",
                               detail=v.raw))
    return out


def check_format(table_id: str, rows: list[AssembledRow]) -> list[CheckResult]:
    out: list[CheckResult] = []
    n_rep = sum(1 for r in rows for p, rep in r.repaired.items() if rep)
    out.append(CheckResult(check_id="FMT_REPAIRED_CELLS", group="format", scope=table_id,
                           status="pass" if n_rep == 0 else "fail",
                           detail=f"{n_rep} repaired numeric cells (flagged, values kept)"))
    bad_state = [r.row_id for r in rows for p, s in r.states.items() if s not in ("number", "dash", "empty")]
    out.append(CheckResult(check_id="FMT_THREE_STATE", group="format", scope=table_id,
                           status="fail" if bad_state else "pass", detail=f"bad={bad_state[:5]}"))
    return out


def check_rollforward(table_id: str, rows: list[AssembledRow], columns: list[str]) -> list[CheckResult]:
    out: list[CheckResult] = []
    opening = next((r for r in rows if r.role == "opening"), None)
    closing = next((r for r in rows if r.role == "closing"), None)
    flows = [r for r in rows if r.role == "flow"]
    if opening is None or closing is None or not flows:
        return [CheckResult(check_id="FIN_ROLLFORWARD", group="financial", scope=table_id,
                            status="not_evaluable", detail="missing opening/closing/flow rows")]
    for col in columns:
        o, c = opening.values.get(col), closing.values.get(col)
        if o is None or c is None:
            out.append(CheckResult(check_id="FIN_ROLLFORWARD", group="financial",
                                   scope=f"{table_id}.{col}", status="not_evaluable",
                                   detail="opening or closing not numeric"))
            continue
        fl = Decimal(0)
        evaluable = True
        for r in flows:
            v = r.values.get(col)
            if v is None and r.states.get(col) == "number":
                evaluable = False
                break
            fl += v if v is not None else Decimal(0)  # dash means no movement
        if not evaluable:
            out.append(CheckResult(check_id="FIN_ROLLFORWARD", group="financial",
                                   scope=f"{table_id}.{col}", status="not_evaluable"))
            continue
        out.append(CheckResult(
            check_id="FIN_ROLLFORWARD", group="financial", scope=f"{table_id}.{col}",
            status="pass" if o + fl == c else "fail",
            detail=f"opening={o} flows={fl} closing={c} residual={o + fl - c}"))
    return out


def check_rowwise_sum(table_id: str, rows: list[AssembledRow], columns: list[str],
                      total_col: str) -> list[CheckResult]:
    out: list[CheckResult] = []
    parts = [c for c in columns if c != total_col]
    if not parts:
        return out
    for r in rows:
        t = r.values.get(total_col)
        if t is None:
            continue
        vals = [r.values.get(c) for c in parts]
        if any(v is None and r.states.get(c) == "number" for v, c in zip(vals, parts)):
            out.append(CheckResult(check_id="FIN_ROW_SUM", group="financial",
                                   scope=f"{table_id}.{r.row_id}", status="not_evaluable"))
            continue
        s = sum((v for v in vals if v is not None), Decimal(0))
        out.append(CheckResult(check_id="FIN_ROW_SUM", group="financial",
                               scope=f"{table_id}.{r.row_id}",
                               status="pass" if s == t else "fail",
                               detail=f"sum={s} total={t}"))
    return out


def check_hierarchy_sums(table_id: str, rows: list[AssembledRow], periods: list[str],
                         children: dict[str, list[AssembledRow]]) -> list[CheckResult]:
    """Two complementary sum identities, evaluated conservatively:

    1. parent sum: a row with children equals the sum of its direct children.
    2. grand total: a TOPLAM row is checked against candidate member sets (preceding
       same-indent rows; with and without childless rows). Voting semantics: pass if
       ANY candidate set reproduces the total, fail only when all evaluable sets
       disagree, not_evaluable otherwise. Never assumes a missing value is zero.
    """
    out: list[CheckResult] = []

    for r in rows:
        kids = children.get(r.row_id, [])
        if len(kids) < 2:
            continue
        for p in periods:
            t = r.values.get(p)
            vals = [k.values.get(p) for k in kids]
            if t is None or any(v is None and k.states.get(p) == "number" for v, k in zip(vals, kids)):
                continue
            if any(k.repaired.get(p) for k in kids) or r.repaired.get(p):
                status = "not_evaluable"
                detail = "repaired operand"
            else:
                s = sum((v for v in vals if v is not None), Decimal(0))
                status = "pass" if s == t else "fail"
                detail = f"children_sum={sum((v for v in vals if v is not None), Decimal(0))} parent={t}"
            out.append(CheckResult(check_id="FIN_PARENT_SUM", group="financial",
                                   scope=f"{table_id}.{r.row_id}.{p}", status=status, detail=detail))

    for i, r in enumerate(rows):
        if not r.label.upper().startswith("TOPLAM") and r.role != "total":
            continue
        same = [x for x in rows[:i] if x.indent == r.indent
                and not x.label.upper().startswith("TOPLAM") and x.role != "total"]
        if not same:
            continue
        with_kids = [x for x in same if len(children.get(x.row_id, [])) >= 1]

        def drop_aggregated(members: list[AssembledRow], p: str) -> list[AssembledRow]:
            """A member equal to the sum of a contiguous run of following members is
            an aggregate header; keep it, drop its parts (avoids double counting)."""
            out_m: list[AssembledRow] = []
            skip_until = -1
            for i, x in enumerate(members):
                if i <= skip_until:
                    continue
                v = x.values.get(p)
                if v is not None:
                    run = Decimal(0)
                    for j in range(i + 1, len(members)):
                        nv = members[j].values.get(p)
                        if nv is None:
                            break
                        run += nv
                        if run == v:
                            skip_until = j
                            break
                out_m.append(x)
            return out_m

        def sets_for(p: str) -> list[list[AssembledRow]]:
            seen: set[tuple[str, ...]] = set()
            sets: list[list[AssembledRow]] = []
            for s in (same, with_kids, drop_aggregated(same, p)):
                key = tuple(x.row_id for x in s)
                if s and key not in seen:
                    seen.add(key)
                    sets.append(s)
            return sets
        for p in periods:
            t = r.values.get(p)
            if t is None:
                continue
            verdicts = []
            skipped_missing = skipped_mixed = 0
            for s in sets_for(p):
                vals = [x.values.get(p) for x in s]
                if any(v is None and x.states.get(p) == "number" for v, x in zip(vals, s)):
                    skipped_missing += 1
                    continue
                if any(isinstance(v, Decimal) and v != v.to_integral_value() for v in vals if v is not None):
                    skipped_mixed += 1  # per-share figures never sum with totals
                    continue
                verdicts.append(sum((v for v in vals if v is not None), Decimal(0)) == t)
            if not verdicts:
                out.append(CheckResult(check_id="FIN_GRAND_TOTAL", group="financial",
                                       scope=f"{table_id}.{r.row_id}.{p}", status="not_evaluable",
                                       detail=(f"{skipped_missing + skipped_mixed} hypotheses enumerated, "
                                               f"none evaluable ({skipped_missing} with missing member "
                                               f"cells, {skipped_mixed} with mixed per-share units)")))
            elif any(verdicts):
                out.append(CheckResult(check_id="FIN_GRAND_TOTAL", group="financial",
                                       scope=f"{table_id}.{r.row_id}.{p}", status="pass",
                                       detail=f"{sum(verdicts)}/{len(verdicts)} member-set hypotheses match"))
            else:
                out.append(CheckResult(check_id="FIN_GRAND_TOTAL", group="financial",
                                       scope=f"{table_id}.{r.row_id}.{p}", status="fail",
                                       detail="no member-set hypothesis reproduces the total"))
    return out


def _is_milestone(r: AssembledRow) -> bool:
    alpha = [ch for ch in r.label if ch.isalpha()]
    if not alpha or r.indent != 0:
        return False
    upper = sum(1 for ch in alpha if ch.isupper())
    return upper / len(alpha) >= 0.6 and any(v is not None for v in r.values.values())


def _dedupe_segment(vals: list[Decimal], base: Decimal) -> list[Decimal]:
    """Remove re-expressions from a cascade segment, purely by value (layout-free):
    - a row equal to the previous milestone is its repeated total,
    - a contiguous run summing to the previous milestone is its breakdown,
    - a contiguous run summing to a PRECEDING row re-expresses that aggregate
      (e.g. a tax total followed by its two components)."""
    # runs summing to base (breakdown re-listing) and singletons equal to base
    keep = [True] * len(vals)
    i = 0
    while i < len(vals):
        if not keep[i]:
            i += 1
            continue
        if vals[i] == base:
            keep[i] = False
            i += 1
            continue
        run = Decimal(0)
        for j in range(i, len(vals)):
            if not keep[j]:
                break
            run += vals[j]
            if run == base and j > i:
                for k in range(i, j + 1):
                    keep[k] = False
                break
        i += 1
    vals2 = [v for v, k in zip(vals, keep) if k]
    # aggregate followed by its components
    out: list[Decimal] = []
    i = 0
    while i < len(vals2):
        out.append(vals2[i])
        run = Decimal(0)
        consumed = 0
        for j in range(i + 1, len(vals2)):
            run += vals2[j]
            if run == vals2[i]:
                consumed = j - i
                break
        i += 1 + consumed
    return out


def check_flow_cascade(table_id: str, rows: list[AssembledRow], periods: list[str],
                       has_parent: set[str]) -> list[CheckResult]:
    """Income-statement style derived chain: each uppercase milestone equals the
    previous milestone plus the intervening signed flow rows. Breakdown re-listings
    and aggregate/component double counts are removed by value-based deduplication
    (the printed layout is too flat on scans to rely on indentation). Unit-mixed
    rows (per-share decimals) are excluded; a missing operand makes the segment
    not_evaluable, never zero."""
    out: list[CheckResult] = []
    milestones = [i for i, r in enumerate(rows) if _is_milestone(r)]
    if len(milestones) < 2:
        return out
    for p in periods:
        prev_idx: int | None = None
        for mi in milestones:
            target = rows[mi].values.get(p)
            if target is None:
                prev_idx = mi
                continue
            start = 0 if prev_idx is None else prev_idx + 1
            base = Decimal(0) if prev_idx is None else (rows[prev_idx].values.get(p) or Decimal(0))
            if prev_idx is not None and rows[prev_idx].values.get(p) is None:
                prev_idx = mi
                continue
            raw_vals: list[Decimal] = []
            evaluable = True
            for r in rows[start:mi]:
                v = r.values.get(p)
                if r.row_id in has_parent:
                    continue
                if v is None:
                    if r.states.get(p) == "number":
                        evaluable = False
                        break
                    continue
                if v != v.to_integral_value():
                    continue  # per-share style unit-mixed row
                raw_vals.append(v)
            seg = sum(_dedupe_segment(raw_vals, base), Decimal(0)) if evaluable else Decimal(0)
            if not evaluable:
                out.append(CheckResult(check_id="FIN_FLOW_CASCADE", group="financial",
                                       scope=f"{table_id}.{rows[mi].row_id}.{p}",
                                       status="not_evaluable"))
            else:
                ok = base + seg == target
                out.append(CheckResult(check_id="FIN_FLOW_CASCADE", group="financial",
                                       scope=f"{table_id}.{rows[mi].row_id}.{p}",
                                       status="pass" if ok else "fail",
                                       detail=f"prev={base} segment={seg} milestone={target}"))
            prev_idx = mi
    return out


def check_sign_legality(table_id: str, rows: list[AssembledRow], periods: list[str]) -> list[CheckResult]:
    """A row label ending in (-) declares an expense; its numeric values must not be
    positive."""
    out: list[CheckResult] = []
    for r in rows:
        if not r.label.rstrip().endswith("(-)"):
            continue
        for p in periods:
            v = r.values.get(p)
            if v is None:
                continue
            out.append(CheckResult(check_id="FMT_SIGN_LEGALITY", group="format",
                                   scope=f"{table_id}.{r.row_id}.{p}",
                                   status="pass" if v <= 0 else "fail",
                                   detail=f"value={v} for a (-) labeled row"))
    return out


def check_reconciliation(relation_id: str, s_vals: dict[str, Decimal | None],
                         f_vals: dict[str, Decimal | None], period_scope: str) -> CheckResult:
    pairs = []
    for sp, sv in s_vals.items():
        if sv is None:
            continue
        for fp, fv in f_vals.items():
            if fv is not None and abs(sv) == abs(fv):
                pairs.append((sp, fp))
    if period_scope != "unscoped" and pairs:
        return CheckResult(check_id="FIN_RECONCILE", group="financial", scope=relation_id,
                           status="pass", detail=f"matched {pairs}")
    if not any(v is not None for v in s_vals.values()):
        return CheckResult(check_id="FIN_RECONCILE", group="financial", scope=relation_id,
                           status="not_evaluable")
    return CheckResult(check_id="FIN_RECONCILE", group="financial", scope=relation_id,
                       status="fail" if not pairs else "pass",
                       detail="no value agreement" if not pairs else f"matched {pairs}")
