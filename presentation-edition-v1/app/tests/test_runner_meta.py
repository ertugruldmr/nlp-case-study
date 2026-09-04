"""meta.json carries the platform stamp (fake pipeline modules, no models loaded)."""
import json
import platform
import subprocess
import sys
import types

from ftlink_app import runner


def test_fake_run_writes_platform_stamp(tmp_path, monkeypatch):
    monkeypatch.setenv("FTLINK_APP_RUNS", str(tmp_path))
    fake_pipeline = types.ModuleType("ftlink.pipeline")
    fake_pipeline.run = lambda settings: object()
    fake_pipeline.write_outputs = lambda out, out_dir: None
    fake_report = types.ModuleType("ftlink.report")
    fake_report.write_report = lambda out, settings, out_dir: None
    monkeypatch.setitem(sys.modules, "ftlink.pipeline", fake_pipeline)
    monkeypatch.setitem(sys.modules, "ftlink.report", fake_report)

    meta = runner.execute("footnote-12")  # eval not applicable: no scorer call
    assert meta["state"] == "done"
    stored = json.loads((tmp_path / "footnote-12" / "meta.json").read_text(encoding="utf-8"))
    assert stored["platform"]["platform"] == platform.platform()
    assert stored["platform"]["tesseract"]
    assert stored["platform"].get("models") in ("warm", "cold")
    assert not runner._RUN_LOCK.locked()


def test_tesseract_version_parsing(monkeypatch):
    class Out:
        stdout = "tesseract 5.5.3\n leptonica-1.87.0\n"
        stderr = ""
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: Out())
    assert runner.tesseract_version() == "5.5.3"

    def missing(*a, **k):
        raise FileNotFoundError("tesseract")
    monkeypatch.setattr(subprocess, "run", missing)
    assert runner.tesseract_version() == "unknown"
