"""Compare-engine math on synthetic fixtures (no pipeline run needed)."""
import json

import pytest

from ftlink_app import compare as compare_mod


def _mk_result(relations, cells=None, checks=None):
    return {
        "tables": [{"table_id": "t1", "page": 5, "title": "T", "periods": [],
                    "confidence": 1.0,
                    "provenance": {"page": 5, "stage": "s"}}],
        "rows": [
            {"row_id": "r.sum", "table_id": "t1", "label_raw": "Stoklar",
             "label_norm": "stoklar", "indent_level": 0, "role": "item",
             "dipnot_refs": [11], "asterisk_marks": [], "confidence": 1.0,
             "provenance": {"page": 5, "stage": "s"}},
            {"row_id": "r.fn", "table_id": "t1", "label_raw": "Konut",
             "label_norm": "konut", "indent_level": 0, "role": "item",
             "dipnot_refs": [], "asterisk_marks": [], "confidence": 1.0,
             "provenance": {"page": 53, "stage": "s"}},
        ],
        "cells": cells or [],
        "relations": relations,
        "checks": checks or [],
    }


def _rel(conf, agreement="consensus", low=False):
    return {
        "relation_id": "rel001", "summary_row_id": "r.sum", "footnote_row_id": "r.fn",
        "period_scope": "y2012", "relation_type": "semantic",
        "approaches": [{"name": "cross_encoder", "raw_score": 0.9, "rank": 1,
                        "accepted": True}],
        "agreement": agreement, "confidence": conf, "confidence_components": {},
        "low_confidence": low, "evidence": "",
    }


@pytest.fixture()
def two_runs(tmp_path, monkeypatch):
    monkeypatch.setenv("FTLINK_APP_RUNS", str(tmp_path))
    for sid, result in (
        ("baseline", _mk_result([_rel(0.9)],
                                cells=[{"cell_id": "c1", "row_id": "r.sum",
                                        "period_id": "y2012",
                                        "value": {"state": "number", "raw": "1.000",
                                                  "value": "1000", "kind": "int",
                                                  "repaired": False},
                                        "confidence": 1.0,
                                        "provenance": {"page": 5, "stage": "s"}}],
                                checks=[{"check_id": "FMT_X", "group": "format",
                                         "scope": "c1", "status": "pass",
                                         "detail": ""}])),
        ("strict-linker", _mk_result([],
                                     cells=[{"cell_id": "c1", "row_id": "r.sum",
                                             "period_id": "y2012",
                                             "value": {"state": "dash", "raw": "-"},
                                             "confidence": 1.0,
                                             "provenance": {"page": 5, "stage": "s"}}],
                                     checks=[{"check_id": "FMT_X", "group": "format",
                                              "scope": "c1", "status": "fail",
                                              "detail": "boom"}])),
    ):
        d = tmp_path / sid / "outputs"
        d.mkdir(parents=True)
        (d / "result.json").write_text(json.dumps(result), encoding="utf-8")
    return tmp_path


def test_relation_only_in_a(two_runs):
    diff = compare_mod.compare("baseline", "strict-linker")
    assert len(diff["relations"]["only_a"]) == 1
    assert diff["relations"]["only_a"][0]["summary"]["label"] == "Stoklar"
    assert diff["relations"]["both"] == []
    assert diff["relations"]["only_b"] == []


def test_cell_and_check_diffs(two_runs):
    diff = compare_mod.compare("baseline", "strict-linker")
    assert len(diff["cells"]["changed"]) == 1
    assert diff["cells"]["changed"][0]["a"]["state"] == "number"
    assert diff["cells"]["changed"][0]["b"]["state"] == "dash"
    assert len(diff["checks"]) == 1
    assert diff["checks"][0]["a"] == "pass" and diff["checks"][0]["b"] == "fail"


def test_missing_run_reports_error(two_runs):
    diff = compare_mod.compare("baseline", "footnote-12")
    assert "footnote-12" in diff["error"]


def test_relation_scoped_checks_remap_to_stable_key(two_runs, tmp_path):
    """Relation ids renumber across runs; scopes must diff on the stable key."""
    rel_a = _rel(0.9)
    rel_b = dict(_rel(0.9), relation_id="rel099")  # same link, different id
    res_a = _mk_result([rel_a], checks=[{"check_id": "FIN_RECONCILE",
                                         "group": "financial", "scope": "rel001",
                                         "status": "pass", "detail": "x"}])
    res_b = _mk_result([rel_b], checks=[{"check_id": "FIN_RECONCILE",
                                         "group": "financial", "scope": "rel099",
                                         "status": "pass", "detail": "x"}])
    for sid, res in (("no-anchor-channel", res_a), ("dpi-400", res_b)):
        d = tmp_path / sid / "outputs"
        d.mkdir(parents=True)
        (d / "result.json").write_text(json.dumps(res), encoding="utf-8")
    diff = compare_mod.compare("no-anchor-channel", "dpi-400")
    assert diff["checks"] == []           # not a real difference
    assert diff["check_details_changed"] == []


def test_detail_change_surfaces(two_runs, tmp_path):
    res_a = _mk_result([], checks=[{"check_id": "STR_CALIBRATION_CONTROLS",
                                    "group": "structural", "scope": "document",
                                    "status": "pass", "detail": "positives=11"}])
    res_b = _mk_result([], checks=[{"check_id": "STR_CALIBRATION_CONTROLS",
                                    "group": "structural", "scope": "document",
                                    "status": "pass", "detail": "positives=7"}])
    for sid, res in (("no-anchor-channel", res_a), ("dpi-400", res_b)):
        d = tmp_path / sid / "outputs"
        d.mkdir(parents=True)
        (d / "result.json").write_text(json.dumps(res), encoding="utf-8")
    diff = compare_mod.compare("no-anchor-channel", "dpi-400")
    assert diff["checks"] == []
    assert len(diff["check_details_changed"]) == 1
    assert "positives=7" in diff["check_details_changed"][0]["detail_b"]


def test_confidence_delta(two_runs, tmp_path):
    d = tmp_path / "lenient-linker" / "outputs"
    d.mkdir(parents=True)
    (d / "result.json").write_text(json.dumps(_mk_result([_rel(0.7, low=True)])),
                                   encoding="utf-8")
    diff = compare_mod.compare("baseline", "lenient-linker")
    assert len(diff["relations"]["both"]) == 1
    entry = diff["relations"]["both"][0]
    assert entry["confidence_delta"] == pytest.approx(-0.2)
    assert entry["flag_changed"] is True


def test_matrix_loads_each_result_at_most_twice(two_runs, monkeypatch):
    from collections import Counter

    from ftlink_app import store
    from ftlink_app.registry import SCENARIOS

    counts = Counter()
    real = store.load_result

    def counting(sid):
        counts[sid] += 1
        return real(sid)

    monkeypatch.setattr(store, "load_result", counting)
    monkeypatch.setattr(compare_mod, "load_result", counting)
    rows = compare_mod.matrix()
    assert len(rows) == len(SCENARIOS)
    assert counts["baseline"] == 1 and counts["strict-linker"] == 1
    assert max(counts.values()) <= 2, dict(counts)
    assert any(r.get("vs_baseline") for r in rows)  # the cache did not skip the diff itself
