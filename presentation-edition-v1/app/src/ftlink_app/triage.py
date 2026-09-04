"""Review queue and expected-cost threshold panel over one stored run.

Review order follows the README's own rule: the Venn-ABERS interval width is the honest
statement of how much the calibration can be trusted per relation, so wider intervals and
lower calibrated confidences go first; anything flagged low_confidence (below the operating
point, or fallback calibration) leads the queue. Threshold: review when p < 1 - c_review /
c_miss (rises with the miss cost). Nothing here re-runs the pipeline.
"""
from __future__ import annotations

from typing import Any

from . import labels as labels_mod
from .store import load_result, relations_view

CURVE_STEPS = [round(0.05 * i, 2) for i in range(0, 21)]


def p_star(c_review: float, c_miss: float) -> float:
    if c_miss <= 0 or c_review < 0:
        raise ValueError("c_miss must be > 0 and c_review >= 0")
    return max(0.0, min(1.0, 1.0 - c_review / c_miss))


def relation_queue(scenario_id: str) -> list[dict] | None:
    view = relations_view(scenario_id)
    if view is None:
        return None
    items = []
    for r in view:
        comp = r.get("confidence_components", {})
        p0, p1 = comp.get("venn_abers_p0"), comp.get("venn_abers_p1")
        width = (p1 - p0) if (p0 is not None and p1 is not None) else None
        items.append({**r, "va_width": width})
    items.sort(key=lambda x: (not x.get("low_confidence"), -(x["va_width"] or 0.0), x.get("confidence", 1.0)))
    return items


def cell_queue(result: dict) -> list[dict]:
    rows = {r["row_id"]: r for r in result.get("rows", [])}
    tables = {t["table_id"]: t for t in result.get("tables", [])}
    out = []
    for c in result.get("cells", []):
        v = c.get("value", {})
        if c.get("confidence", 1.0) <= 0.5 or v.get("repaired"):
            r = rows.get(c["row_id"], {})
            t = tables.get(r.get("table_id"), {})
            out.append({"cell_id": c["cell_id"], "row": r.get("label_raw") or "(etiketsiz toplam)", "page": t.get("page"),
                        "period": c.get("period_id"), "state": v.get("state"), "raw": v.get("raw"), "value": v.get("value"),
                        "repaired": bool(v.get("repaired")), "confidence": c.get("confidence"),
                        "components": c.get("confidence_components", {})})
    out.sort(key=lambda x: (x["confidence"] if x["confidence"] is not None else 1.0))
    return out


def threshold_panel(rels: list[dict], c_review: float, c_miss: float, rel_labels: dict) -> dict[str, Any]:
    ps = p_star(c_review, c_miss)
    review, accept = [], []
    for r in rels:
        p = float(r.get("confidence") or 0.0)
        (review if (p < ps or r.get("low_confidence")) else accept).append(r)
    exp_cost = len(review) * c_review + sum((1.0 - float(r.get("confidence") or 0.0)) * c_miss for r in accept)
    review_all = len(rels) * c_review
    review_none = sum((1.0 - float(r.get("confidence") or 0.0)) * c_miss for r in rels)
    curve = [{"threshold": t, "review": sum(1 for r in rels if float(r.get("confidence") or 0.0) < t or r.get("low_confidence"))} for t in CURVE_STEPS]
    lab_stats = None
    if rel_labels:
        acc_lab = [rel_labels.get(r["key"], {}).get("label") for r in accept]
        rev_lab = [rel_labels.get(r["key"], {}).get("label") for r in review]
        n_acc_lab = sum(1 for x in acc_lab if x in ("accept", "reject"))
        lab_stats = {
            "labelled_in_accept_set": n_acc_lab,
            "reviewer_precision_of_accept_set": (sum(1 for x in acc_lab if x == "accept") / n_acc_lab) if n_acc_lab else None,
            "reviewer_rejects_in_accept_set": sum(1 for x in acc_lab if x == "reject"),
            "reviewer_accepts_in_review_set": sum(1 for x in rev_lab if x == "accept"),
        }
    return {"c_review": c_review, "c_miss": c_miss, "p_star": round(ps, 4),
            "review_ids": [r["relation_id"] for r in review], "accept_ids": [r["relation_id"] for r in accept],
            "expected_cost": {"at_p_star": round(exp_cost, 4), "review_all": round(review_all, 4), "review_none": round(review_none, 4)},
            "curve": curve, "labels": lab_stats}


def build(scenario_id: str, c_review: float = 1.0, c_miss: float = 20.0) -> dict[str, Any] | None:
    result = load_result(scenario_id)
    if result is None:
        return None
    rels = relation_queue(scenario_id) or []
    labs = labels_mod.load(scenario_id)
    for r in rels:
        r["label"] = labs["relation"].get(r["key"])
    cells = cell_queue(result)
    for c in cells:
        c["label"] = labs["cell"].get(c["cell_id"])
    return {"scenario": scenario_id, "relations": rels, "cells": cells,
            "threshold": threshold_panel(rels, c_review, c_miss, labs["relation"]),
            "labels_summary": labels_mod.summary(labs)}


EXPORT_COLUMNS = ("scenario", "kind", "key", "label", "note", "ts", "summary_label", "summary_page",
                  "footnote_label", "footnote_page", "period", "confidence", "venn_abers_p0", "venn_abers_p1",
                  "low_confidence", "p_star", "decision")


def export_rows(scenario_id: str, c_review: float = 1.0, c_miss: float = 20.0) -> list[dict[str, Any]] | None:
    """Reviewer labels joined with what they were judged against.

    decision: relations follow the p* rule of the threshold panel (review / accept); cells
    follow the cell-queue rule (review when confidence <= 0.5 or repaired, else accept)."""
    data = build(scenario_id, c_review, c_miss)
    if data is None:
        return None
    ps = data["threshold"]["p_star"]
    review = set(data["threshold"]["review_ids"])
    queued = {c["cell_id"] for c in data["cells"]}
    rows: list[dict[str, Any]] = []
    for r in data["relations"]:
        lab = r.get("label")
        if not lab:
            continue
        comp = r.get("confidence_components", {})
        rows.append({"scenario": scenario_id, "kind": "relation", "key": r["key"], "label": lab["label"],
                     "note": lab.get("note", ""), "ts": lab.get("ts", ""),
                     "summary_label": r["summary"]["label"], "summary_page": r["summary"]["page"],
                     "footnote_label": r["footnote"]["label"], "footnote_page": r["footnote"]["page"],
                     "period": r["period_scope"], "confidence": r["confidence"],
                     "venn_abers_p0": comp.get("venn_abers_p0"), "venn_abers_p1": comp.get("venn_abers_p1"),
                     "low_confidence": bool(r.get("low_confidence")), "p_star": ps,
                     "decision": "review" if r["relation_id"] in review else "accept"})
    labs = labels_mod.load(scenario_id)["cell"]
    result = load_result(scenario_id) or {}
    rows_by_id = {r["row_id"]: r for r in result.get("rows", [])}
    tables = {t["table_id"]: t for t in result.get("tables", [])}
    for c in result.get("cells", []):
        lab = labs.get(c["cell_id"])
        if not lab:
            continue
        r = rows_by_id.get(c["row_id"], {})
        rows.append({"scenario": scenario_id, "kind": "cell", "key": c["cell_id"], "label": lab["label"],
                     "note": lab.get("note", ""), "ts": lab.get("ts", ""),
                     "summary_label": r.get("label_raw") or "(etiketsiz toplam)",
                     "summary_page": tables.get(r.get("table_id"), {}).get("page"),
                     "footnote_label": None, "footnote_page": None, "period": c.get("period_id"),
                     "confidence": c.get("confidence"), "venn_abers_p0": None, "venn_abers_p1": None,
                     "low_confidence": c["cell_id"] in queued, "p_star": ps,
                     "decision": "review" if c["cell_id"] in queued else "accept"})
    return rows
