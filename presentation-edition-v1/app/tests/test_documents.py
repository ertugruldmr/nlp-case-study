"""Upload a configured PDF through the same lock path (fake pipeline, no models)."""
import json
import time

import pymupdf
import pytest
from fastapi.testclient import TestClient

from ftlink_app import documents, runner

FIELDS = {
    "summary_pages_start": "1",
    "summary_pages_end": "2",
    "footnote_no": "11",
    "extra_control_pages": "3",
    "label": "Interview fixture",
    "company": "Test A.Ş.",
    "period_end": "2024-12-31",
    "currency": "TRY",
    "ocr_lang": "tur",
}


def _pdf(pages: int = 3) -> bytes:
    doc = pymupdf.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"Sayfa {i + 1}: Yatırım Amaçlı Gayrimenkuller (Dipnot 11)")
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FTLINK_APP_RUNS", str(tmp_path))
    from ftlink_app.api import app

    return TestClient(app)


def _upload(client, data=None, **overrides):
    fields = {**FIELDS, **overrides}
    return client.post("/api/documents", files={"file": ("rapor.pdf", data or _pdf(), "application/pdf")}, data=fields)


def test_upload_writes_doc_json_and_source(client, tmp_path):
    import hashlib

    data = _pdf()
    r = _upload(client, data)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["doc_id"] == hashlib.sha256(data).hexdigest()[:12]
    assert d["page_count"] == 3 and d["size"] == len(data)
    assert d["summary_pages"] == [1, 2] and d["footnote_no"] == 11 and d["extra_control_pages"] == [3]
    assert d["label"] == "Interview fixture" and d["filename"] == "rapor.pdf"
    assert d["company"] == "Test A.Ş." and d["period_end"] == "2024-12-31"
    assert d["currency"] == "TRY" and d["ocr_lang"] == "tur"
    assert d["profile"]["sha256"] == d["sha256"]
    assert d["profile"]["source_kind"] == "native_text"
    assert d["profile"]["native_text_page_count"] == 3
    assert d["run_id"] == f"doc-{d['doc_id']}" and d["status"]["state"] == "absent" and d["summary"] is None
    folder = tmp_path / "_documents" / d["doc_id"]
    assert (folder / "source.pdf").read_bytes() == data
    stored = json.loads((folder / "doc.json").read_text(encoding="utf-8"))
    assert stored["sha256"] == d["sha256"] and stored["uploaded_at"]
    listed = client.get("/api/documents").json()
    assert [x["doc_id"] for x in listed] == [d["doc_id"]]
    assert client.get(f"/api/documents/{d['doc_id']}").json()["meta"] is None
    assert client.get("/api/documents/nope").status_code == 404


def test_same_pdf_can_keep_multiple_configurations(client):
    data = _pdf()
    first = _upload(client, data).json()
    second = _upload(client, data, summary_pages_start="2", summary_pages_end="2",
                     extra_control_pages="3", label="Alternate bounded experiment").json()
    assert first["doc_id"] != second["doc_id"]
    assert second["doc_id"].startswith(first["doc_id"] + "-")
    assert first["summary_pages"] == [1, 2]
    assert second["summary_pages"] == [2, 2]
    assert len(client.get("/api/documents").json()) == 2


def test_non_pdf_rejected_by_magic_bytes(client):
    r = client.post("/api/documents", files={"file": ("x.pdf", b"hello, not a pdf", "application/pdf")}, data=FIELDS)
    assert r.status_code == 400


def test_read_only_pdf_inspection_does_not_persist(client, tmp_path):
    response = client.post("/api/debugger/inspect-pdf",
                           files={"file": ("new.pdf", _pdf(4), "application/pdf")})
    assert response.status_code == 200
    profile = response.json()
    assert profile["page_count"] == 4
    assert profile["source_kind"] == "native_text"
    assert profile["native_text_page_count"] == 4
    assert len(profile["sha256"]) == 64
    assert not (tmp_path / "_documents").exists()
    r = client.post("/api/documents", files={"file": ("x.pdf", b"%PDF-1.4 garbage", "application/pdf")}, data=FIELDS)
    assert r.status_code == 400


def test_out_of_range_fields_422(client):
    assert _upload(client, summary_pages_end="9").status_code == 422
    assert _upload(client, summary_pages_end="3", extra_control_pages="").status_code == 422
    assert _upload(client, summary_pages_start="2", summary_pages_end="1").status_code == 422
    assert _upload(client, footnote_no="0").status_code == 422
    assert _upload(client, extra_control_pages="1,7").status_code == 422
    assert _upload(client, extra_control_pages="1").status_code == 422
    assert _upload(client, extra_control_pages="1,x").status_code == 422
    assert _upload(client, extra_control_pages="", label="").status_code == 200
    assert _upload(client, period_end="31-12-2024").status_code == 422
    assert _upload(client, currency="Turkish lira").status_code == 422
    assert _upload(client, ocr_lang="tur;rm").status_code == 422


def test_duplicate_control_pages_are_normalized(client):
    result = _upload(client, extra_control_pages="3,3,3").json()
    assert result["extra_control_pages"] == [3]


def test_size_cap_413(client, monkeypatch):
    monkeypatch.setattr(documents, "MAX_BYTES", 500)
    assert _upload(client).status_code == 413


def test_doc_scenario_builds_valid_settings_outside_deliverable(client, tmp_path):
    from ftlink.config import Settings

    from ftlink_app.paths import deliverable_root

    doc_id = _upload(client).json()["doc_id"]
    scenario = runner.resolve(f"doc-{doc_id}")
    assert scenario.group == "document" and scenario.eval_applicable is False
    merged = runner.build_settings_dict(scenario)
    settings = Settings(**merged)
    assert settings.document.pdf_path == (tmp_path / "_documents" / doc_id / "source.pdf").resolve()
    assert settings.document.summary_pages == (1, 2) and settings.document.footnote_no == 11
    assert settings.confidence.extra_control_pages == [3] and settings.document.company == "Test A.Ş."
    assert str(settings.document.period_end) == "2024-12-31" and settings.document.currency == "TRY"
    assert settings.ocr.lang == "tur"
    assert not str(merged["output"]["dir"]).startswith(str(deliverable_root()))
    assert str(merged["output"]["dir"]).startswith(str(tmp_path))
    with pytest.raises(KeyError):
        runner.resolve("doc-000000000000")


def _fake_execute(sid: str, lock_held: bool = False) -> dict:
    from ftlink_app.paths import runs_root

    out = runs_root() / sid / "outputs"
    out.mkdir(parents=True, exist_ok=True)
    result = {"schema_version": "1", "document": {}, "run": {"config_echo": {"document": {"summary_pages": [1, 2], "footnote_no": 11}}},
              "tables": [{"table_id": "p01.t00", "page": 1, "title": "T", "periods": [], "confidence": 1.0, "provenance": {"stage": "summary_extraction"}}],
              "rows": [{"row_id": "p01.t00.r000", "table_id": "p01.t00", "label_raw": "A", "role": "item", "dipnot_refs": [11]}],
              "cells": [], "relations": [],
              "checks": [{"check_id": "STR_CALIBRATION_CONTROLS", "group": "structural", "scope": "document", "status": "pass", "detail": "mode=fallback"}]}
    (out / "result.json").write_text(json.dumps(result), encoding="utf-8")
    (out / "report.html").write_text("<html>fake</html>", encoding="utf-8")
    meta = {"state": "done", "scenario": sid, "duration_s": 0.1, "platform": {"platform": "fake", "tesseract": "0"}}
    (out.parent / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    runner._STATUS[sid] = meta
    runner._RUN_LOCK.release()
    return meta


def test_run_through_the_shared_lock_and_views_resolve(client, monkeypatch):
    monkeypatch.setattr(runner, "execute", _fake_execute)
    doc_id = _upload(client).json()["doc_id"]
    rid = f"doc-{doc_id}"
    assert client.post("/api/documents/nope/run").status_code == 404
    r = client.post(f"/api/documents/{doc_id}/run")
    assert r.status_code == 200 and r.json() == {"state": "started", "scenario": rid, "doc_id": doc_id}
    for _ in range(200):
        if client.get(f"/api/documents/{doc_id}").json()["status"]["state"] == "done":
            break
        time.sleep(0.01)
    d = client.get(f"/api/documents/{doc_id}").json()
    assert d["status"]["state"] == "done" and d["meta"]["scenario"] == rid
    assert d["summary"]["tables"] == 1 and d["summary"]["calibration_mode"] == "fallback"
    assert not runner._RUN_LOCK.locked()
    assert client.get(f"/api/runs/{rid}/result").json()["tables"][0]["table_id"] == "p01.t00"
    assert [s["id"] for s in client.get(f"/api/runs/{rid}/walkthrough").json()["stages"]][0] == "S2"
    assert client.get(f"/api/runs/{rid}/triage").json()["scenario"] == rid
    assert client.get(f"/api/runs/{rid}/report").status_code == 200
    assert client.post(f"/api/runs/{rid}/labels", json={"kind": "cell", "key": "c1", "label": "accept"}).status_code == 200
    assert client.get("/api/compare", params={"a": rid, "b": "baseline"}).status_code == 200
    assert client.post(f"/api/runs/{rid}").status_code == 200  # the generic run route resolves doc runs too
    for _ in range(200):
        if not runner._RUN_LOCK.locked():
            break
        time.sleep(0.01)
    from ftlink_app.registry import SCENARIOS

    assert {s["id"] for s in client.get("/api/scenarios").json()} == {s.id for s in SCENARIOS}  # doc runs never enter the registry


def test_second_run_refused_while_lock_held(client, monkeypatch):
    monkeypatch.setattr(runner, "execute", _fake_execute)
    doc_id = _upload(client).json()["doc_id"]
    assert runner._RUN_LOCK.acquire(blocking=False)
    try:
        assert client.post(f"/api/documents/{doc_id}/run").status_code == 409
        assert client.post(f"/api/runs/doc-{doc_id}").status_code == 409
    finally:
        runner._RUN_LOCK.release()
