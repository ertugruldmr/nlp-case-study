"""The decision-matrix asset the frontend renders: well-formed and served."""
import json

import pytest
from fastapi.testclient import TestClient

from ftlink_app.paths import frontend_root

ROLES = {"shipped", "verifier", "fallback", "comparison", "pending", "rejected", "excluded"}


def test_decision_matrix_asset_is_well_formed():
    dm = json.loads((frontend_root() / "decision_matrix.json").read_text(encoding="utf-8"))
    assert dm["version"].startswith("ftlink 1.0")
    assert len(dm["stages"]) == 8
    # S7 gained the measured modernbert-tr-reranker row on 29.08 (39 -> 40); S1/S3 gained GPU
    # bake-off comparison rows on 30.08 (run-06/07/08 fold-in, 40 -> 43); demo_preflight step 8
    # pins the same totals
    assert sum(len(st["options"]) for st in dm["stages"]) == 43
    for st in dm["stages"]:
        assert st["id"] and st["title_tr"] and st["options"]
        assert any(o["role"] == "shipped" for o in st["options"]), st["id"]
        for o in st["options"]:
            assert o["name"] and o["role"] in ROLES and o["measure"]
            assert isinstance(o["evidence"], list)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FTLINK_APP_RUNS", str(tmp_path))
    from ftlink_app.api import app

    return TestClient(app)


def test_decision_matrix_served(client):
    r = client.get("/decision_matrix.json")
    assert r.status_code == 200
    assert len(r.json()["stages"]) >= 7
    html = client.get("/").text
    assert "btnMatrixDM" in html and "btnPresent" in html
