"""The run endpoint must refuse a second run while the lock is held (no check-then-act race)."""
import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FTLINK_APP_RUNS", str(tmp_path))
    from ftlink_app.api import app

    return TestClient(app)


def test_second_run_is_refused_while_lock_held(client, monkeypatch):
    from ftlink_app import runner

    assert runner._RUN_LOCK.acquire(blocking=False)
    try:
        r = client.post("/api/runs/baseline")
        assert r.status_code == 409
    finally:
        runner._RUN_LOCK.release()


def test_start_takes_the_lock_in_the_request_thread(tmp_path, monkeypatch):
    from ftlink_app import runner

    monkeypatch.setenv("FTLINK_APP_RUNS", str(tmp_path))
    calls = []
    monkeypatch.setattr(runner, "execute", lambda sid, lock_held=False: calls.append((sid, lock_held)) or runner._RUN_LOCK.release())
    assert runner.start("baseline") is True
    import time
    for _ in range(50):
        if calls:
            break
        time.sleep(0.01)
    assert calls == [("baseline", True)]
    assert not runner._RUN_LOCK.locked()


def test_start_releases_lock_when_thread_cannot_start(tmp_path, monkeypatch):
    from ftlink_app import runner

    monkeypatch.setenv("FTLINK_APP_RUNS", str(tmp_path))

    def fail_start(self):
        raise RuntimeError("thread unavailable")

    monkeypatch.setattr(runner.threading.Thread, "start", fail_start)
    with pytest.raises(RuntimeError, match="thread unavailable"):
        runner.start("baseline")
    assert not runner._RUN_LOCK.locked()


def test_execute_releases_preacquired_lock_when_setup_fails(tmp_path, monkeypatch):
    from ftlink_app import runner

    monkeypatch.setenv("FTLINK_APP_RUNS", str(tmp_path))
    monkeypatch.setattr(runner, "resolve", lambda _sid: (_ for _ in ()).throw(KeyError("gone")))
    assert runner._RUN_LOCK.acquire(blocking=False)
    meta = runner.execute("doc-gone", lock_held=True)
    assert meta["state"] == "error" and "KeyError" in meta["error"]
    assert not runner._RUN_LOCK.locked()


def test_persisted_running_without_live_worker_is_interrupted(tmp_path, monkeypatch):
    from ftlink_app import runner

    monkeypatch.setenv("FTLINK_APP_RUNS", str(tmp_path))
    run_dir = tmp_path / "doc-abandoned"
    run_dir.mkdir()
    (run_dir / "meta.json").write_text(json.dumps({
        "state": "running", "scenario": "doc-abandoned", "started": "2026-09-02T05:17:52"
    }), encoding="utf-8")
    runner._STATUS.pop("doc-abandoned", None)

    value = runner.status("doc-abandoned")
    assert value["state"] == "error"
    assert value["interrupted"] is True
    assert "retry" in value["error"]
