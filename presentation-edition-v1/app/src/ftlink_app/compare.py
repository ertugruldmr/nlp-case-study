"""Diff two scenario runs: relations, cells, and checks.

Identity across runs rides on the pipeline's deterministic semantic IDs:
relations compare on (summary_row_id, footnote_row_id, period_scope), cells on
cell_id, checks on (check_id, scope). That identity is itself a design claim of
the deliverable (re-runnability), which makes this diff view possible at all.
"""
from __future__ import annotations

from typing import Any

from .store import load_result, relations_of, summarize_result


def _rel_key(rel: dict) -> str:
    return f'{rel["summary_row_id"]}|{rel["footnote_row_id"]}|{rel["period_scope"]}'


def _get(results: dict[str, dict | None], scenario_id: str) -> dict | None:
    if scenario_id not in results:
        results[scenario_id] = load_result(scenario_id)
    return results[scenario_id]


def matrix(baseline_id: str = "baseline") -> list[dict]:
    """One row per registry scenario: headline metrics + divergence vs baseline.

    The all-scenarios defense view: every alternative, its numbers, and how far
    it moved from the shipped configuration, in one table.
    """
    from . import runner
    from .registry import SCENARIOS

    rows: list[dict] = []
    results: dict[str, dict | None] = {}
    base_ok = _get(results, baseline_id) is not None
    for s in SCENARIOS:
        status = runner.status(s.id)
        row: dict[str, Any] = {
            "id": s.id, "title_tr": s.title_tr, "group": s.group,
            "state": status.get("state", "absent"),
            "requires_endpoint": s.requires_endpoint,
        }
        if status.get("state") == "error":
            row["error"] = (status.get("error") or "")[:160]
        summary = summarize_result(s.id, _get(results, s.id))
        if summary:
            ev = summary.get("eval") or {}
            row["summary"] = {
                "cells_pct": (ev.get("cells") or {}).get("pct"),
                "precision": (ev.get("relations") or {}).get("precision"),
                "recall": (ev.get("relations") or {}).get("recall"),
                "relations": summary["relations"],
                "low_conf": summary["low_conf_relations"],
                "checks": summary["checks"],
                "calibration": summary["calibration_mode"],
                "duration_s": summary.get("duration_s"),
                "platform": summary.get("platform"),
            }
            if base_ok and s.id != baseline_id:
                d = compare(baseline_id, s.id, results)
                row["vs_baseline"] = {
                    "rels_only_base": len(d["relations"]["only_a"]),
                    "rels_only_here": len(d["relations"]["only_b"]),
                    "max_abs_dconf": max((abs(e["confidence_delta"])
                                          for e in d["relations"]["both"]), default=0.0),
                    "flags_changed": sum(1 for e in d["relations"]["both"]
                                         if e["flag_changed"]),
                    "cells_changed": len(d["cells"]["changed"]),
                    "check_flips": len(d["checks"]),
                }
        rows.append(row)
    return rows


def compare(a_id: str, b_id: str, results: dict[str, dict | None] | None = None) -> dict[str, Any]:
    results = results if results is not None else {}
    ra, rb = _get(results, a_id), _get(results, b_id)
    if ra is None or rb is None:
        missing = [sid for sid, r in ((a_id, ra), (b_id, rb)) if r is None]
        return {"error": f"no stored run for: {', '.join(missing)}"}

    va = {r["key"]: r for r in relations_of(ra) or []}
    vb = {r["key"]: r for r in relations_of(rb) or []}

    relations = {
        "both": [], "only_a": [], "only_b": [],
    }
    for key in sorted(set(va) | set(vb)):
        in_a, in_b = key in va, key in vb
        if in_a and in_b:
            pa, pb = va[key], vb[key]
            relations["both"].append({
                "key": key, "a": pa, "b": pb,
                "confidence_delta": round(pb["confidence"] - pa["confidence"], 4),
                "agreement_changed": pa["agreement"] != pb["agreement"],
                "flag_changed": pa["low_confidence"] != pb["low_confidence"],
            })
        elif in_a:
            relations["only_a"].append(va[key])
        else:
            relations["only_b"].append(vb[key])

    # cells: same cell_id, different value state or raw text
    ca = {c["cell_id"]: c for c in ra.get("cells", [])}
    cb = {c["cell_id"]: c for c in rb.get("cells", [])}
    cell_diffs = []
    for cid in sorted(set(ca) & set(cb)):
        x, y = ca[cid]["value"], cb[cid]["value"]
        if x.get("state") != y.get("state") or x.get("raw") != y.get("raw"):
            cell_diffs.append({
                "cell_id": cid,
                "a": {"state": x.get("state"), "raw": x.get("raw")},
                "b": {"state": y.get("state"), "raw": y.get("raw")},
                "conf_a": ca[cid].get("confidence"), "conf_b": cb[cid].get("confidence"),
            })
    cells = {
        "changed": cell_diffs,
        "only_a": len(set(ca) - set(cb)),
        "only_b": len(set(cb) - set(ca)),
    }

    # relation ids renumber between runs; remap relation-scoped checks onto the
    # stable (summary_row, footnote_row, period) key so the diff shows real
    # changes, not cosmetic id shifts
    def _scope_map(result: dict) -> dict[str, str]:
        return {rel["relation_id"]: _rel_key(rel) for rel in result.get("relations", [])}

    def _checks(result: dict, rid2key: dict[str, str]) -> dict:
        out = {}
        for c in result.get("checks", []):
            scope = rid2key.get(c["scope"], c["scope"])
            out[(c["check_id"], scope)] = c
        return out

    ka = _checks(ra, _scope_map(ra))
    kb = _checks(rb, _scope_map(rb))
    check_diffs = []
    detail_changed = []
    for key in sorted(set(ka) | set(kb)):
        sa = ka.get(key, {}).get("status", "absent")
        sb = kb.get(key, {}).get("status", "absent")
        entry = {
            "check_id": key[0], "scope": key[1], "a": sa, "b": sb,
            "detail_a": ka.get(key, {}).get("detail", ""),
            "detail_b": kb.get(key, {}).get("detail", ""),
        }
        if sa != sb:
            check_diffs.append(entry)
        elif entry["detail_a"] != entry["detail_b"]:
            detail_changed.append(entry)

    return {
        "a": {"id": a_id, "summary": summarize_result(a_id, ra)},
        "b": {"id": b_id, "summary": summarize_result(b_id, rb)},
        "relations": relations,
        "cells": cells,
        "checks": check_diffs,
        "check_details_changed": detail_changed,
    }
