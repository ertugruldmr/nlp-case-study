"""Read-side access to stored scenario runs."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from .paths import runs_root


def run_dir(scenario_id: str) -> Path:
    return runs_root() / scenario_id


def load_result(scenario_id: str) -> dict | None:
    p = run_dir(scenario_id) / "outputs/result.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def load_meta(scenario_id: str) -> dict | None:
    p = run_dir(scenario_id) / "meta.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def summarize(scenario_id: str) -> dict[str, Any] | None:
    """Headline card for one stored run, derived from the output itself."""
    return summarize_result(scenario_id, load_result(scenario_id))


def summarize_result(scenario_id: str, result: dict | None) -> dict[str, Any] | None:
    if result is None:
        return None
    checks = Counter(c["status"] for c in result.get("checks", []))
    relations = result.get("relations", [])
    agreement = Counter(r["agreement"] for r in relations)
    # calibration mode is recorded in the STR_CALIBRATION_CONTROLS check detail
    calibration_mode = None
    for c in result.get("checks", []):
        if c.get("check_id") == "STR_CALIBRATION_CONTROLS" and "mode=" in c.get("detail", ""):
            calibration_mode = c["detail"].split("mode=")[1].split()[0]
            break
    summary: dict[str, Any] = {
        "tables": len(result.get("tables", [])),
        "rows": len(result.get("rows", [])),
        "cells": len(result.get("cells", [])),
        "relations": len(relations),
        "low_conf_relations": sum(1 for r in relations if r.get("low_confidence")),
        "checks": {"pass": checks.get("pass", 0), "fail": checks.get("fail", 0),
                   "not_evaluable": checks.get("not_evaluable", 0)},
        "agreement": dict(agreement),
        "calibration_mode": calibration_mode,
    }
    meta = load_meta(scenario_id)
    if meta:
        summary["duration_s"] = meta.get("duration_s")
        summary["eval"] = meta.get("eval")
        summary["platform"] = meta.get("platform")
    return summary


def relations_view(scenario_id: str) -> list[dict] | None:
    """Relations enriched with the two row labels, ready for the UI."""
    return relations_of(load_result(scenario_id))


def relations_of(result: dict | None) -> list[dict] | None:
    if result is None:
        return None
    rows = {r["row_id"]: r for r in result.get("rows", [])}
    tables = {t["table_id"]: t for t in result.get("tables", [])}

    def row_info(row_id: str) -> dict:
        r = rows.get(row_id)
        if not r:
            return {"row_id": row_id, "label": "?", "page": None}
        t = tables.get(r["table_id"], {})
        return {"row_id": row_id, "label": r.get("label_raw") or "(etiketsiz toplam)",
                "page": t.get("page"), "table_title": t.get("title", "")}

    view = []
    for rel in result.get("relations", []):
        view.append({
            "relation_id": rel["relation_id"],
            "key": f'{rel["summary_row_id"]}|{rel["footnote_row_id"]}|{rel["period_scope"]}',
            "summary": row_info(rel["summary_row_id"]),
            "footnote": row_info(rel["footnote_row_id"]),
            "period_scope": rel["period_scope"],
            "relation_type": rel["relation_type"],
            "agreement": rel["agreement"],
            "confidence": rel["confidence"],
            "confidence_components": rel.get("confidence_components", {}),
            "low_confidence": rel.get("low_confidence", False),
            "approaches": rel.get("approaches", []),
            "evidence": rel.get("evidence", ""),
        })
    return view
