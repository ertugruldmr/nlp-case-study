"""Benchmark store: every committed file validates, the API serves it, the sync rebuilds it from the research
artifacts (never runs the pipeline)."""
import json
import sys

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from ftlink_app import benchmarks, benchmarks_sync
from ftlink_app.paths import APP_ROOT, benchmarks_root

WS = APP_ROOT.parent
SOURCES = (WS / benchmarks_sync.CALIB / "results.json", WS / benchmarks_sync.CALIB / "prior_family.json",
           WS / benchmarks_sync.TATR / "results-t07.json", WS / benchmarks_sync.TATR / "results-t03.json",
           WS / benchmarks_sync.RAPIDOCR / "score.log", WS / benchmarks_sync.SECOND_DOC,
           WS / benchmarks_sync.RERANKER / "results.json", WS / benchmarks_sync.RERANKER / "results-identity-e2e.json",
           WS / benchmarks_sync.TEXTLAYER / "report-ozak-2013.json", WS / benchmarks_sync.TEXTLAYER / "report-case-2012.json",
           WS / benchmarks_sync.LOCATOR / "case-run.log", WS / benchmarks_sync.LOCATOR / "emlak-run.log",
           WS / benchmarks_sync.CROSSEVAL / "recompute.out",
           APP_ROOT / "runs/baseline/meta.json", APP_ROOT / "runs/baseline/outputs/result.json",
           APP_ROOT / f"runs/{benchmarks_sync.RERANKER_RUN}/outputs/result.json")
STORE_SIZE = 11


def test_every_committed_benchmark_validates():
    files = sorted(benchmarks_root().glob("*.json"))
    assert len(files) >= STORE_SIZE
    loaded = benchmarks.load_all()
    assert [b.id for b in sorted(loaded, key=lambda b: b.id)] == [p.stem for p in files]
    for b in loaded:
        assert b.rows, b.id
        assert all(r.source for r in b.rows), b.id
        if b.baseline:
            assert any(r.role == "shipped" for r in b.rows), b.id
        assert not b.parse_errors, (b.id, b.parse_errors)


def test_schema_rejects_inconsistent_files(tmp_path):
    good = {"id": "x", "title_tr": "t", "title_en": "t", "measured_at": "2026-08-29T10:00:00", "source": "s",
            "scope": "colab", "baseline": "a", "columns": [{"key": "v", "label_tr": "v", "kind": "number"}],
            "rows": [{"id": "a", "label": "a", "role": "shipped", "source": "s", "v": 1.5}], "notes_tr": [], "decision_rule": "d"}
    benchmarks.Benchmark.model_validate(good)
    for patch in ({"baseline": "missing"},
                  {"rows": [{**good["rows"][0], "v": "text"}]},
                  {"rows": [{**good["rows"][0], "v": True}]},
                  {"rows": [good["rows"][0], good["rows"][0]]},
                  {"columns": [{"key": "role", "label_tr": "r", "kind": "text"}]},
                  {"scope": "somewhere"},
                  {"rows": [{**good["rows"][0], "role": "maybe"}]}):
        with pytest.raises(ValidationError):
            benchmarks.Benchmark.model_validate({**good, **patch})
    (tmp_path / "other.json").write_text(json.dumps(good), encoding="utf-8")
    with pytest.raises(ValueError, match="file stem"):
        benchmarks.load_all(tmp_path)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FTLINK_APP_RUNS", str(tmp_path))
    from ftlink_app.api import app

    return TestClient(app)


def test_benchmark_endpoints(client):
    r = client.get("/api/benchmarks")
    assert r.status_code == 200
    listing = r.json()
    assert len(listing) >= STORE_SIZE
    for item in listing:
        d = client.get(f"/api/benchmarks/{item['id']}")
        assert d.status_code == 200
        body = d.json()
        assert body["id"] == item["id"] and len(body["rows"]) == item["rows"]
        assert item["shipped_rows"] == sum(1 for r in body["rows"] if r["role"] == "shipped")
        for r in body["rows"]:
            for c in body["columns"]:
                v = r.get(c["key"])
                assert v is None or isinstance(v, {"text": str, "bool": bool}.get(c["kind"], (int, float))), (body["id"], r["id"], c["key"])
    assert client.get("/api/benchmarks/nope").status_code == 404
    assert "btnBench" in client.get("/").text


@pytest.mark.skipif(not all(p.exists() for p in SOURCES), reason="research artifacts or the baseline run are not present")
def test_sync_rebuilds_from_the_research_artifacts(tmp_path):
    built = benchmarks_sync.sync(WS, tmp_path)
    assert len(built) == STORE_SIZE == len(benchmarks_sync.CONVERTERS)
    loaded = benchmarks.load_all(tmp_path)
    assert {b.id for b in loaded} == {b.id for b in built}
    with_baseline = [b for b in loaded if b.baseline]
    assert len(with_baseline) >= 5
    for b in with_baseline:
        assert sum(1 for r in b.rows if r.role == "shipped") >= 1, b.id
    for b in loaded:
        assert not b.parse_errors, (b.id, b.parse_errors)
        assert all(r.source for r in b.rows), b.id
    by_id = {b.id: b for b in loaded}
    rapid = by_id["rapidocr-recognizer-variants"]
    assert {r.id for r in rapid.rows} >= {"shipped", "default", "default-warm"}
    assert rapid.rows[0].role == "shipped" and rapid.rows[0].value("cells_total") == 201
    second = by_id["second-document-generality"]
    assert {r.id for r in second.rows} >= {"case-document-shipped", "ozak-gyo-2013", "ozak-gyo-2011"}
    tatr = by_id["tatr-detection"]
    assert tatr.rows[0].value("total") == 7 and tatr.rows[0].value("gold") == 7
    rerank = by_id["reranker-swap"]
    assert [r.id for r in rerank.rows] == ["mmarco-shipped", "modernbert-tr-as-wired", "modernbert-tr-identity"]
    assert [r.value("auc_labels") for r in rerank.rows] == [0.4504, 0.7149, 0.7149]
    assert [r.value("controls_ge_05") for r in rerank.rows] == [3, 33, 11]
    assert [r.value("brier_loo") for r in rerank.rows] == [0.0085, 0.0051, 0.0076]
    assert [r.value("relations") for r in rerank.rows] == [7, 17, 8]
    text_layer = by_id["text-layer-channel"]
    assert [(r.value("numeric_cells"), r.value("agree"), r.value("differ"), r.value("text_missing"))
            for r in text_layer.rows] == [(201, 189, 12, 0), (182, 0, 0, 182)]
    assert text_layer.rows[0].value("dropped_leading_1") == text_layer.rows[0].value("recovered") == 11
    locator = by_id["locator-generalization"]
    assert [r.id for r in locator.rows] == ["case-under-patch", "emlak-before", "emlak-after"]
    assert locator.rows[0].value("identical") is True and locator.rows[0].value("relations") == 7
    assert locator.rows[1].role == "rejected" and locator.rows[1].value("exit") == 2
    assert locator.rows[2].value("tables") == 8 and locator.rows[2].value("checks") == "66 / 25 / 7"
    xeval = by_id["cross-evaluation"]
    assert len(xeval.rows) == 49 and all(r.value("agree") is True for r in xeval.rows)
    assert all(r.value("claimed") and r.value("recomputed") and r.value("group") for r in xeval.rows)


@pytest.mark.skipif(not all(p.exists() for p in SOURCES), reason="research artifacts or the baseline run are not present")
def test_the_committed_store_still_follows_from_the_sources():
    """--check as a test: a benchmark JSON edited by hand, or a source that moved on, fails here."""
    assert benchmarks_sync.check(WS, benchmarks_root()) == []


@pytest.mark.skipif(not all(p.exists() for p in SOURCES), reason="research artifacts or the baseline run are not present")
def test_sync_is_idempotent_and_check_reports_drift(tmp_path, monkeypatch):
    built = benchmarks_sync.sync(WS, tmp_path)
    first = {p.name: p.read_text(encoding="utf-8") for p in tmp_path.glob("*.json")}
    benchmarks_sync.sync(WS, tmp_path)
    assert {p.name: p.read_text(encoding="utf-8") for p in tmp_path.glob("*.json")} == first
    assert benchmarks_sync.check(WS, tmp_path) == []
    edited = tmp_path / f"{built[0].id}.json"
    body = json.loads(edited.read_text(encoding="utf-8"))
    body["rows"][0]["label"] = "hand-edited"
    edited.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (tmp_path / f"{built[1].id}.json").unlink()
    drift = benchmarks_sync.check(WS, tmp_path)
    assert len(drift) == 2
    assert drift[0].startswith(f"{built[0].id}: differs from the sources") and "hand-edited" in drift[0]
    assert drift[1] == f"{built[1].id}: {built[1].id}.json is not in the store"
    monkeypatch.setattr(sys, "argv", ["ftlink-benchmarks-sync", "--out", str(tmp_path), "--check"])
    assert benchmarks_sync.main() == 1
    benchmarks_sync.sync(WS, tmp_path)
    assert benchmarks_sync.main() == 0


def test_sync_reports_parse_errors_instead_of_inventing_values(tmp_path, monkeypatch):
    monkeypatch.setenv("FTLINK_APP_RUNS", str(tmp_path / "runs"))
    built = benchmarks_sync.sync(tmp_path / "empty-workspace", tmp_path / "out")
    assert len(built) == len(benchmarks_sync.CONVERTERS)
    for b in built:
        assert b.parse_errors, b.id
        assert not b.rows and b.baseline is None, b.id
    assert len(benchmarks.load_all(tmp_path / "out")) == len(built)
