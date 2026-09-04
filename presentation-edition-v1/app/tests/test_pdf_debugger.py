import hashlib
import json
import shutil

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FTLINK_APP_RUNS", str(tmp_path))
    from ftlink_app import pdf_debugger
    monkeypatch.setattr(pdf_debugger, "ANNOTATION_PATH", tmp_path / "_debugger" / "annotations.jsonl")
    from ftlink_app.api import app
    return TestClient(app)


def _annotation():
    return {"schema_version": "debugger.annotation.v1", "decision": "unsure", "issue_family": "OCR digit", "note": "Check this digit", "severity": "needs review", "object_ids": ["p05.t00.r007.c00"], "document_sha256": "a" * 64, "run_id": "baseline", "timestamp": "2026-08-31T00:00:00+03:00"}


def test_debugger_run_and_canonical_are_read_only(client, tmp_path):
    from ftlink_app import pdf_debugger
    strict = tmp_path / "strict-linker" / "outputs"
    strict.mkdir(parents=True)
    shutil.copy2(pdf_debugger.result_path(), strict / "result.json")
    (strict.parent / "meta.json").write_text(json.dumps({"state": "done"}), encoding="utf-8")
    run = client.get("/api/debugger/run")
    assert run.status_code == 200 and run.json()["status"] == "completed"
    canonical = client.get("/api/debugger/canonical")
    assert canonical.status_code == 200
    assert canonical.content == pdf_debugger.result_path().read_bytes()
    home = client.get("/").text
    debugger = client.get("/pdf-debugger.html")
    assert 'id="btnPdfDebugger"' in home
    assert debugger.status_code == 200 and "pdf-debugger-enhancements.js" in debugger.text
    enhancements = client.get("/pdf-debugger-enhancements.js")
    assert enhancements.status_code == 200
    assert all(label in enhancements.text for label in (
        "Configure / upload / run", "Bounded extraction",
        "Bound row × column values", "Full-screen data", "coordinate_spaces",
        "Case guide", "What this solution is required to prove", "Rotate 90°",
        "Baseline-only ground truth", "No ground truth attached to this run",
        "No relation was emitted for this run", "Run-specific scope",
        "Case-compatible configuration", "No relations emitted",
    ))
    assert "Experimental all-page extraction" not in enhancements.text
    assert "state.run.result.relations[0].relation_id" not in enhancements.text
    assert run.json()["coordinate_spaces"]["7"] == {
        "width": 2481, "height": 3510, "dpi": 300, "rotation": 0
    }
    proof = client.get("/api/debugger/proof").json()
    assert proof["schema_version"] == "debugger.run-proof.v1"
    assert proof["input"]["sha256_match"] is True
    assert proof["configuration"]["echo"]["document"]["summary_pages"] == [5, 7]
    assert proof["output"]["counts"]["relations"] == 7
    assert len(proof["execution"]["pipeline_code_sha256"]) == 64
    runs = client.get("/api/debugger/runs").json()
    assert runs[0]["run_id"] == "baseline"
    assert any(x["run_id"] == "strict-linker" for x in runs)


def test_completed_registered_experiment_opens_in_debugger(client, tmp_path):
    from ftlink_app import pdf_debugger
    strict = tmp_path / "strict-linker" / "outputs"
    strict.mkdir(parents=True)
    shutil.copy2(pdf_debugger.result_path(), strict / "result.json")
    (strict.parent / "meta.json").write_text(json.dumps({"state": "done"}), encoding="utf-8")
    response = client.get("/api/debugger/run", params={"run_id": "strict-linker"})
    assert response.status_code == 200
    assert response.json()["run_id"] == "strict-linker"
    assert response.json()["page_count"] == 95
    assert client.get("/api/debugger/page/7", params={"run_id": "strict-linker"}).status_code == 200


def test_debugger_page_is_bounded_and_rendered(client):
    page = client.get("/api/debugger/page/5")
    assert page.status_code == 200 and page.headers["content-type"].startswith("image/png") and page.content.startswith(b"\x89PNG")
    rotated = client.get("/api/debugger/page/5", params={"view_rotation": 90})
    assert rotated.status_code == 200 and rotated.content.startswith(b"\x89PNG")
    assert client.get("/api/debugger/page/5", params={"view_rotation": 45}).status_code == 400
    assert client.get("/api/debugger/page/0").status_code == 400
    assert client.get("/api/debugger/page/../../etc/passwd").status_code in (400, 404)


def test_completed_uploaded_run_can_be_opened_in_debugger(client):
    from ftlink_app import documents, pdf_debugger
    data = pdf_debugger.pdf_path().read_bytes()
    fields = documents.UploadFields(summary_pages_start=5, summary_pages_end=7,
                                    footnote_no=11, extra_control_pages="9,10",
                                    label="Uploaded baseline", page_count=95)
    meta = documents.save(data, "uploaded.pdf", fields)
    run_id = documents.run_id(meta.doc_id)
    out = documents.documents_root().parent / run_id / "outputs"
    out.mkdir(parents=True)
    shutil.copy2(pdf_debugger.result_path(), out / "result.json")
    (out.parent / "meta.json").write_text(json.dumps({"state": "done"}), encoding="utf-8")

    runs = client.get("/api/debugger/runs").json()
    assert any(x["run_id"] == run_id for x in runs)
    loaded = client.get("/api/debugger/run", params={"run_id": run_id})
    assert loaded.status_code == 200 and loaded.json()["page_count"] == 95
    page = client.get("/api/debugger/page/5", params={"run_id": run_id})
    assert page.status_code == 200 and page.content.startswith(b"\x89PNG")
    assert client.get("/api/debugger/canonical", params={"run_id": run_id}).content == (out / "result.json").read_bytes()

    annotation = {**_annotation(), "run_id": run_id,
                  "document_sha256": hashlib.sha256(data).hexdigest()}
    assert client.post("/api/debugger/annotations", json=annotation).status_code == 200


def test_failed_rerun_never_exposes_stale_completed_debugger_output(client):
    from ftlink_app import documents, pdf_debugger, runner

    data = pdf_debugger.pdf_path().read_bytes()
    fields = documents.UploadFields(summary_pages_start=5, summary_pages_end=7,
                                    footnote_no=11, extra_control_pages="9,10",
                                    label="Stale output guard", page_count=95)
    meta = documents.save(data, "uploaded.pdf", fields)
    run_id = documents.run_id(meta.doc_id)
    out = documents.documents_root().parent / run_id / "outputs"
    out.mkdir(parents=True)
    shutil.copy2(pdf_debugger.result_path(), out / "result.json")
    (out.parent / "meta.json").write_text(json.dumps({"state": "done"}), encoding="utf-8")
    assert client.get("/api/debugger/run", params={"run_id": run_id}).status_code == 200

    failed = {"state": "error", "scenario": run_id, "error": "RuntimeError: forced"}
    (out.parent / "meta.json").write_text(json.dumps(failed), encoding="utf-8")
    runner._STATUS[run_id] = failed

    assert client.get("/api/debugger/run", params={"run_id": run_id}).status_code == 404
    assert client.get("/api/debugger/canonical", params={"run_id": run_id}).status_code == 404
    assert all(x["run_id"] != run_id for x in client.get("/api/debugger/runs").json())
    doc = client.get(f"/api/documents/{meta.doc_id}").json()
    assert doc["status"]["state"] == "error" and doc["summary"] is None


def test_debugger_can_clone_current_pdf_with_a_new_configuration(client, monkeypatch):
    from ftlink_app import runner
    started = []
    monkeypatch.setattr(runner, "start", lambda run_id: started.append(run_id) or True)
    response = client.post("/api/debugger/configured-run", json={
        "source_run_id": "baseline",
        "summary_pages_start": 5,
        "summary_pages_end": 10,
        "footnote_no": 11,
        "extra_control_pages": [],
        "label": "Extended statements",
    })
    assert response.status_code == 200, response.text
    value = response.json()
    assert value["state"] == "started" and value["run_id"] == started[0]
    assert value["summary_pages"] == [5, 10]


def test_debugger_configuration_rejects_bad_scope(client):
    response = client.post("/api/debugger/configured-run", json={
        "source_run_id": "baseline", "summary_pages_start": 10,
        "summary_pages_end": 5, "footnote_no": 11,
    })
    assert response.status_code == 422
    overlap = client.post("/api/debugger/configured-run", json={
        "source_run_id": "baseline", "summary_pages_start": 5,
        "summary_pages_end": 7, "footnote_no": 11,
        "extra_control_pages": [6],
    })
    assert overlap.status_code == 422
    assert "must be outside summary range" in overlap.json()["detail"]
    assert "pydantic.dev" not in overlap.json()["detail"]


def test_debugger_annotation_round_trip_and_exports(client, tmp_path):
    value = _annotation()
    posted = client.post("/api/debugger/annotations", json=value)
    assert posted.status_code == 200 and posted.json()["count"] == 1
    assert client.get("/api/debugger/annotations").json()["annotations"] == [value]
    assert "debugger.annotation.v1" in client.get("/api/debugger/annotations/export?format=jsonl").text
    csv = client.get("/api/debugger/annotations/export?format=csv")
    assert csv.status_code == 200 and "object_ids" in csv.text
    bad = {**value, "run_id": "deliverable"}
    assert client.post("/api/debugger/annotations", json=bad).status_code == 400
