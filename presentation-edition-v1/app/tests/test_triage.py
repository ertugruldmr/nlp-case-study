"""Triage queue, threshold panel and labels store (synthetic stored run, no pipeline)."""
import json

import pytest
from fastapi.testclient import TestClient

from ftlink_app import triage


def _rel(rid, key, conf, p0, low=False):
    return {"relation_id": rid, "summary_row_id": key.split("|")[0], "footnote_row_id": key.split("|")[1],
            "period_scope": key.split("|")[2], "relation_type": "balance_reconciliation", "agreement": "b_only",
            "confidence": conf, "low_confidence": low, "approaches": [], "evidence": "",
            "confidence_components": {"venn_abers_p0": p0, "venn_abers_p1": 1.0}}


def _result():
    return {
        "schema_version": "1", "document": {}, "run": {"config_echo": {}},
        "tables": [{"table_id": "p05.t00", "page": 5, "title": "T"}, {"table_id": "p53.t03", "page": 53, "title": "N"}],
        "rows": [{"row_id": "p05.t00.r001", "table_id": "p05.t00", "label_raw": "A"},
                 {"row_id": "p05.t00.r002", "table_id": "p05.t00", "label_raw": "B"},
                 {"row_id": "p53.t03.r000", "table_id": "p53.t03", "label_raw": "K"}],
        "cells": [
            {"cell_id": "c-low", "row_id": "p05.t00.r001", "period_id": "y2012", "confidence": 0.4,
             "value": {"state": "number", "raw": "1", "value": "1", "repaired": False}, "confidence_components": {}},
            {"cell_id": "c-rep", "row_id": "p05.t00.r002", "period_id": "y2012", "confidence": 0.7,
             "value": {"state": "number", "raw": "2", "value": "2", "repaired": True}, "confidence_components": {}},
            {"cell_id": "c-ok", "row_id": "p05.t00.r002", "period_id": "y2011", "confidence": 1.0,
             "value": {"state": "number", "raw": "3", "value": "3", "repaired": False}, "confidence_components": {}},
        ],
        "relations": [
            _rel("rel-hi", "p05.t00.r001|p53.t03.r000|y2012", 0.97, 0.9),
            _rel("rel-wide", "p05.t00.r002|p53.t03.r000|y2012", 0.82, 0.5),
            _rel("rel-flag", "p05.t00.r001|p53.t03.r000|y2011", 0.53, 0.0, low=True),
        ],
        "checks": [],
    }


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FTLINK_APP_RUNS", str(tmp_path))
    out = tmp_path / "baseline" / "outputs"
    out.mkdir(parents=True)
    (out / "result.json").write_text(json.dumps(_result()), encoding="utf-8")
    from ftlink_app.api import app

    return TestClient(app)


def test_p_star_and_validation():
    assert triage.p_star(1, 20) == 0.95
    assert triage.p_star(1, 1) == 0.0
    assert triage.p_star(5, 2) == 0.0  # clamped: reviewing costs more than missing
    with pytest.raises(ValueError):
        triage.p_star(1, 0)


def test_queue_order_and_threshold(client):
    r = client.get("/api/runs/baseline/triage", params={"c_review": 1, "c_miss": 20})
    assert r.status_code == 200
    d = r.json()
    # flagged first, then the widest Venn-ABERS interval, then the rest
    assert [x["relation_id"] for x in d["relations"]] == ["rel-flag", "rel-wide", "rel-hi"]
    assert d["relations"][1]["va_width"] == 0.5
    # cells: the low-confidence and the repaired cell only, lowest confidence first
    assert [c["cell_id"] for c in d["cells"]] == ["c-low", "c-rep"]
    t = d["threshold"]
    assert t["p_star"] == 0.95
    assert set(t["review_ids"]) == {"rel-wide", "rel-flag"} and t["accept_ids"] == ["rel-hi"]
    assert t["expected_cost"]["review_all"] == 3.0
    assert t["expected_cost"]["at_p_star"] == pytest.approx(2 * 1 + (1 - 0.97) * 20)
    assert t["curve"][0] == {"threshold": 0.0, "review": 1}  # only the forced flag at threshold 0
    assert t["curve"][-1]["review"] == 3
    # cheap misses: nothing but the forced flag goes to review
    d2 = client.get("/api/runs/baseline/triage", params={"c_review": 1, "c_miss": 1}).json()
    assert d2["threshold"]["p_star"] == 0.0 and d2["threshold"]["review_ids"] == ["rel-flag"]
    assert client.get("/api/runs/baseline/triage", params={"c_review": 1, "c_miss": 0}).status_code == 400
    assert client.get("/api/runs/footnote-12/triage").status_code == 404


def test_labels_roundtrip_and_reviewer_stats(client):
    key = "p05.t00.r001|p53.t03.r000|y2012"
    r = client.post("/api/runs/baseline/labels", json={"kind": "relation", "key": key, "label": "accept", "note": "ok"})
    assert r.status_code == 200 and r.json()["summary"]["relation"]["accept"] == 1
    r = client.post("/api/runs/baseline/labels", json={"kind": "cell", "key": "c-low", "label": "reject"})
    assert r.json()["summary"]["cell"]["reject"] == 1
    assert client.post("/api/runs/baseline/labels", json={"kind": "relation", "key": key, "label": "maybe"}).status_code == 400
    assert client.post("/api/runs/nope/labels", json={"kind": "relation", "key": key, "label": "accept"}).status_code == 404
    got = client.get("/api/runs/baseline/labels").json()
    assert got["labels"]["relation"][key]["label"] == "accept" and got["labels"]["relation"][key]["note"] == "ok"
    d = client.get("/api/runs/baseline/triage").json()
    assert d["relations"][2]["label"]["label"] == "accept"  # rel-hi carries its label
    assert d["cells"][0]["label"]["label"] == "reject"
    assert d["threshold"]["labels"] == {"labelled_in_accept_set": 1, "reviewer_precision_of_accept_set": 1.0,
                                        "reviewer_rejects_in_accept_set": 0, "reviewer_accepts_in_review_set": 0}
    # clearing a label removes it
    client.post("/api/runs/baseline/labels", json={"kind": "relation", "key": key, "label": None})
    assert client.get("/api/runs/baseline/labels").json()["summary"]["relation"]["labelled"] == 0


def test_labels_export_csv_and_jsonl(client):
    import csv
    import io

    k_hi = "p05.t00.r001|p53.t03.r000|y2012"    # rel-hi: accepted at p* 0.95
    k_flag = "p05.t00.r001|p53.t03.r000|y2011"  # rel-flag: forced review
    client.post("/api/runs/baseline/labels", json={"kind": "relation", "key": k_hi, "label": "accept", "note": "ok"})
    client.post("/api/runs/baseline/labels", json={"kind": "relation", "key": k_flag, "label": "reject"})

    r = client.get("/api/runs/baseline/labels/export", params={"format": "csv"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    lines = r.text.strip().split("\n")
    assert lines[0] == ",".join(triage.EXPORT_COLUMNS)
    assert len(lines) == 3
    by = {x["key"]: x for x in csv.DictReader(io.StringIO(r.text))}
    hi, flag = by[k_hi], by[k_flag]
    assert hi["label"] == "accept" and hi["note"] == "ok" and hi["decision"] == "accept"
    assert hi["summary_label"] == "A" and hi["summary_page"] == "5" and hi["footnote_label"] == "K" and hi["footnote_page"] == "53"
    assert hi["confidence"] == "0.97" and hi["p_star"] == "0.95" and hi["venn_abers_p0"] == "0.9"
    assert flag["label"] == "reject" and flag["decision"] == "review" and flag["low_confidence"] == "True"

    j = client.get("/api/runs/baseline/labels/export", params={"format": "jsonl"})
    assert j.status_code == 200
    recs = [json.loads(line) for line in j.text.splitlines()]
    assert len(recs) == 2 and {x["key"] for x in recs} == {k_hi, k_flag}
    assert client.get("/api/runs/baseline/labels/export", params={"format": "xml"}).status_code == 400
    assert client.get("/api/runs/footnote-12/labels/export").status_code == 404
