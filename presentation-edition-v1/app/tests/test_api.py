"""API surface on an empty runs store (fast, no pipeline)."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FTLINK_APP_RUNS", str(tmp_path))
    from ftlink_app.api import app

    return TestClient(app)


def test_scenarios_lists_registry(client):
    r = client.get("/api/scenarios")
    assert r.status_code == 200
    data = r.json()
    ids = {s["id"] for s in data}
    assert {"baseline", "footnote-12", "llm-tier"} <= ids
    for s in data:
        assert s["status"]["state"] in ("absent", "done", "error", "running")


def test_unknown_scenario_404(client):
    assert client.get("/api/runs/nope/result").status_code == 404
    assert client.post("/api/runs/nope").status_code == 404
    assert client.get("/api/compare", params={"a": "baseline", "b": "nope"}).status_code == 404


def test_result_absent_404(client):
    assert client.get("/api/runs/baseline/result").status_code == 404


def test_frontend_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "ftlink" in r.text.lower()


def test_matrix_lists_every_scenario_even_on_empty_store(client):
    from ftlink_app.registry import SCENARIOS

    r = client.get("/api/matrix")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == len(SCENARIOS)
    assert all(row["state"] == "absent" for row in rows)
    assert all("summary" not in row for row in rows)
