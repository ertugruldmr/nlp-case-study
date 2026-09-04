"""ftlink-precompute argument handling (no pipeline execution)."""
import sys

import pytest

from ftlink_app import precompute, runner


def test_unknown_ids_exit_2_with_message(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["ftlink-precompute", "nope", "baseline"])
    monkeypatch.setattr(runner, "execute", lambda sid: pytest.fail("must not run anything"))
    assert precompute.main() == 2
    err = capsys.readouterr().err
    assert "nope" in err and "baseline" in err


def test_known_id_runs_and_exits_0(tmp_path, monkeypatch):
    monkeypatch.setenv("FTLINK_APP_RUNS", str(tmp_path))
    monkeypatch.setattr(sys, "argv", ["ftlink-precompute", "baseline"])
    calls = []
    monkeypatch.setattr(runner, "execute", lambda sid: calls.append(sid) or {"state": "error", "error": "fake"})
    assert precompute.main() == 0
    assert calls == ["baseline"]
