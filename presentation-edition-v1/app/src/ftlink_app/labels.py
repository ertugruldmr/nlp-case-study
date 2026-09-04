"""Reviewer labels for triage: a JSON store per scenario under the runs root.

Labels never flow back into the pipeline (the deliverable is sealed and its calibration
uses document arithmetic, not human labels). They exist so a reviewer's decisions on the
flagged records can be recorded, exported, and compared with the calibrated confidences.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from .paths import runs_root

LABELS = ("accept", "reject", "unsure")
KINDS = ("relation", "cell")


def _path(scenario_id: str) -> Path:
    d = runs_root() / "_labels"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{scenario_id}.json"


def load(scenario_id: str) -> dict[str, dict[str, dict[str, Any]]]:
    p = _path(scenario_id)
    if not p.exists():
        return {"relation": {}, "cell": {}}
    data = json.loads(p.read_text(encoding="utf-8"))
    return {"relation": data.get("relation", {}), "cell": data.get("cell", {})}


def set_label(scenario_id: str, kind: str, key: str, label: str | None, note: str = "") -> dict:
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    if label is not None and label not in LABELS:
        raise ValueError(f"label must be one of {LABELS} or null to clear")
    data = load(scenario_id)
    if label is None:
        data[kind].pop(key, None)
    else:
        data[kind][key] = {"label": label, "note": note or "", "ts": dt.datetime.now().isoformat(timespec="seconds")}
    _path(scenario_id).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data


def summary(data: dict) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for kind in KINDS:
        items = data.get(kind, {})
        counts = {lab: sum(1 for v in items.values() if v.get("label") == lab) for lab in LABELS}
        out[kind] = {"labelled": len(items), **counts}
    return out
