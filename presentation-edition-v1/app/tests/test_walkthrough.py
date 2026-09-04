"""Stage walkthrough derived from a stored result.json (synthetic, no pipeline)."""
import json

import pytest
from fastapi.testclient import TestClient

from ftlink_app import walkthrough


def _result() -> dict:
    return {
        "schema_version": "1",
        "document": {"company": "X", "period_end": "2012-12-31", "currency": "TL", "page_offset": 4},
        "run": {"ftlink_version": "0.1.0", "tesseract_version": "5.5.3", "models_loaded": {"cross_encoder": True},
                "config_echo": {"document": {"summary_pages": [5, 7], "footnote_no": 11},
                                "ocr": {"dpi": 300}, "candidates": {"top_k": 8}, "linking": {"accept_threshold": 0.5},
                                "confidence": {"low_confidence_flag": 0.5}}},
        "tables": [
            {"table_id": "p05.t00", "page": 5, "title": "BILANCO", "statement_hint": "instant",
             "periods": [{"period_id": "y2012", "label": "2012"}], "confidence": 0.9,
             "provenance": {"stage": "summary_extraction"}},
            {"table_id": "p53.t03", "page": 53, "title": "11. NOTE", "statement_hint": "flow",
             "periods": [{"period_id": "y2012", "label": "2012"}], "confidence": 0.8,
             "provenance": {"stage": "footnote_extraction"}},
        ],
        "rows": [
            {"row_id": "p05.t00.r001", "table_id": "p05.t00", "label_raw": "Yatirim", "role": "item", "dipnot_refs": [11]},
            {"row_id": "p53.t03.r000", "table_id": "p53.t03", "label_raw": "Kapanis", "role": "closing", "dipnot_refs": []},
        ],
        "cells": [
            {"cell_id": "p05.t00.r001.c00", "row_id": "p05.t00.r001", "period_id": "y2012",
             "value": {"state": "number", "raw": "1.000", "value": "1000", "repaired": False},
             "confidence": 0.4, "confidence_components": {"ocr": 0.9, "parse": 1.0, "engine_agreement": 0.0}},
            {"cell_id": "p53.t03.r000.c00", "row_id": "p53.t03.r000", "period_id": "y2012",
             "value": {"state": "dash", "raw": "-", "value": None, "repaired": False},
             "confidence": 1.0, "confidence_components": {"ocr": 1.0, "parse": 1.0, "engine_agreement": 1.0}},
        ],
        "relations": [
            {"relation_id": "rel000", "summary_row_id": "p05.t00.r001", "footnote_row_id": "p53.t03.r000",
             "period_scope": "y2012", "relation_type": "balance_reconciliation",
             "approaches": [{"name": "cross_encoder", "raw_score": 0.1, "rank": 2, "accepted": False},
                            {"name": "value_rules", "raw_score": 1.0, "rank": None, "accepted": True}],
             "agreement": "b_only", "confidence": 0.87, "low_confidence": False,
             "confidence_components": {"fused": 0.5, "venn_abers_p0": 0.8, "venn_abers_p1": 1.0}, "evidence": "value match"},
        ],
        "checks": [
            {"check_id": "STR_SUMMARY_RANGE", "group": "structural", "scope": "page_5", "status": "pass", "detail": "ok"},
            {"check_id": "STR_CALIBRATION_CONTROLS", "group": "structural", "scope": "document", "status": "pass", "detail": "mode=fitted"},
            {"check_id": "FIN_PARENT_SUM", "group": "financial", "scope": "p05.t00.r001", "status": "fail", "detail": "off by 400000"},
        ],
    }


def test_build_stage_order_and_counts():
    w = walkthrough.build(_result())
    ids = [s["id"] for s in w["stages"]]
    assert ids == ["S2", "S3", "S4", "S6", "S7", "S8", "S9", "S10"]
    by = {s["id"]: s for s in w["stages"]}
    assert by["S2"]["facts"]["configured_footnote_no"] == 11
    assert by["S2"]["facts"]["summary_pages_found"] == [5] and by["S2"]["facts"]["footnote_pages_found"] == [53]
    assert by["S3"]["facts"]["tables"] == 2 and by["S3"]["items"][0]["rows"] == 1
    assert by["S4"]["facts"]["states"] == {"number": 1, "dash": 1}
    assert by["S4"]["facts"]["engine_disagreements"] == 1 and by["S4"]["items"][0]["cell_id"] == "p05.t00.r001.c00"
    assert by["S6"]["facts"]["referencing_rows"][0]["row"] == "Yatirim"
    assert by["S7"]["items"][0]["summary"]["label"] == "Yatirim" and by["S7"]["items"][0]["footnote"]["page"] == 53
    assert by["S8"]["facts"]["calibration_check"]["detail"] == "mode=fitted"
    assert by["S9"]["facts"]["totals"] == {"pass": 2, "fail": 1} and by["S9"]["items"][0]["check_id"] == "FIN_PARENT_SUM"
    assert by["S10"]["facts"]["counts"]["relations"] == 1


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FTLINK_APP_RUNS", str(tmp_path))
    out = tmp_path / "baseline" / "outputs"
    out.mkdir(parents=True)
    (out / "result.json").write_text(json.dumps(_result()), encoding="utf-8")
    from ftlink_app.api import app

    return TestClient(app)


def test_walkthrough_endpoint(client):
    r = client.get("/api/runs/baseline/walkthrough")
    assert r.status_code == 200
    assert [s["id"] for s in r.json()["stages"]] == ["S2", "S3", "S4", "S6", "S7", "S8", "S9", "S10"]
    assert client.get("/api/runs/footnote-12/walkthrough").status_code == 404
