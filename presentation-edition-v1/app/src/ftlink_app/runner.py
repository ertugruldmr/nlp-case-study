"""Execute one scenario: shipped default.yaml + scenario overrides -> ftlink run.

Paths are resolved absolute so the run never depends on the process CWD and never
writes into the deliverable tree. One run at a time (module-level lock): the
pipeline loads models and the demo host is a laptop.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import platform
import subprocess
import threading
import time
import traceback
from pathlib import Path
from typing import Any

import yaml

from . import documents
from .paths import deliverable_root, runs_root
from .registry import BY_ID, Scenario

_RUN_LOCK = threading.Lock()
_STATUS: dict[str, dict[str, Any]] = {}  # scenario_id -> {state, started, error}


def resolve(scenario_id: str) -> Scenario:
    """Registry scenario, or the ad-hoc scenario of an uploaded document (doc-<id>)."""
    scenario = BY_ID.get(scenario_id) or documents.scenario_for(scenario_id)
    if scenario is None:
        raise KeyError(f"unknown scenario: {scenario_id}")
    return scenario


def deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def build_settings_dict(scenario: Scenario) -> dict:
    droot = deliverable_root()
    base = yaml.safe_load((droot / "configs/default.yaml").read_text(encoding="utf-8"))
    merged = deep_merge(base, scenario.overrides)

    run_dir = runs_root() / scenario.id
    merged["document"]["pdf_path"] = str((droot / merged["document"]["pdf_path"]).resolve())
    merged.setdefault("output", {})["dir"] = str(run_dir / "outputs")
    merged["output"]["emit_report_html"] = True
    llm = merged.get("linking", {}).get("llm")
    if llm is not None:
        llm["cache_path"] = str(run_dir / "llm_calls.jsonl")
    return merged


def tesseract_version() -> str:
    try:
        out = subprocess.run(["tesseract", "--version"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    first = (out.stdout or out.stderr).strip().splitlines()[:1]
    parts = first[0].split() if first else []
    return parts[1] if len(parts) >= 2 and parts[0].lower() == "tesseract" else "unknown"


def _model_ids(cfg: dict) -> list[str]:
    ids: list[str] = []
    for k, v in cfg.items():
        if isinstance(v, dict):
            ids.extend(_model_ids(v))
        elif isinstance(v, str) and k.endswith("_model") and "/" in v:
            ids.append(v)
    return ids


def platform_stamp(merged: dict | None = None) -> dict[str, str]:
    """Host facts a wall time must never be quoted without.

    models = warm when every configured HF model already sits in the local hub cache
    before the run starts (no download inside the measured time), cold otherwise;
    omitted when the config names no model."""
    stamp = {"platform": platform.platform(), "tesseract": tesseract_version()}
    ids = _model_ids(merged or {})
    if ids:
        hub = Path(os.environ.get("HF_HUB_CACHE")
                   or Path(os.environ.get("HF_HOME") or Path.home() / ".cache/huggingface") / "hub")
        cached = all((hub / f"models--{m.replace('/', '--')}").is_dir() for m in ids)
        stamp["models"] = "warm" if cached else "cold"
    return stamp


def status(scenario_id: str) -> dict[str, Any]:
    run_dir = runs_root() / scenario_id
    meta_path = run_dir / "meta.json"
    live = _STATUS.get(scenario_id)
    if live and live.get("state") == "running":
        return live
    if meta_path.exists():
        stored = json.loads(meta_path.read_text(encoding="utf-8"))
        if stored.get("state") == "running":
            # A live worker always has an in-memory RUNNING entry. Seeing only a
            # persisted RUNNING record means the process was restarted or killed;
            # do not leave an immortal spinner or imply that work still exists.
            return {**stored, "state": "error", "interrupted": True,
                    "error": "run was interrupted by an application restart; retry explicitly"}
        return stored
    if live:
        return live
    return {"state": "absent"}


def busy() -> bool:
    return _RUN_LOCK.locked()


def start(scenario_id: str) -> bool:
    """Acquire the run lock and spawn the worker; False when another run holds it.

    The lock is taken HERE, in the request thread, so two overlapping POSTs cannot both
    report "started" (the earlier check-then-act on busy() lost that race)."""
    resolve(scenario_id)
    if not _RUN_LOCK.acquire(blocking=False):
        return False
    started = dt.datetime.now().isoformat(timespec="seconds")
    running = {"state": "running", "scenario": scenario_id, "started": started}
    try:
        # Persist RUNNING before the request returns. Besides surviving an app restart,
        # this prevents an older successful meta.json from resurfacing while a rerun is
        # in flight.
        run_dir = runs_root() / scenario_id
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "meta.json").write_text(
            json.dumps(running, ensure_ascii=False, indent=2), encoding="utf-8")
        _STATUS[scenario_id] = running
        threading.Thread(target=execute, args=(scenario_id, True), daemon=True).start()
    except BaseException:
        # Thread creation and pre-worker filesystem failures happen after acquisition;
        # never strand the process-wide run lock on those paths.
        _STATUS[scenario_id] = {"state": "error", "scenario": scenario_id,
                                "error": "run worker could not be started"}
        _RUN_LOCK.release()
        raise
    return True


def execute(scenario_id: str, lock_held: bool = False) -> dict[str, Any]:
    """Blocking scenario run; call from a worker thread in the API (via start())."""
    owns_lock = lock_held
    if not lock_held and not _RUN_LOCK.acquire(blocking=False):
        raise RuntimeError("another scenario run is in progress")
    if not lock_held:
        owns_lock = True
    t0 = time.time()
    run_dir = runs_root() / scenario_id
    try:
        scenario = resolve(scenario_id)
        started = _STATUS.get(scenario_id, {}).get("started") or dt.datetime.now().isoformat(timespec="seconds")
        running = {"state": "running", "scenario": scenario_id, "started": started}
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "meta.json").write_text(
            json.dumps(running, ensure_ascii=False, indent=2), encoding="utf-8")
        _STATUS[scenario_id] = running

        from ftlink.config import Settings
        from ftlink.pipeline import run as ftlink_run, write_outputs
        from ftlink.report import write_report

        merged = build_settings_dict(scenario)
        stamp = platform_stamp(merged)
        settings = Settings(**merged)
        out = ftlink_run(settings)
        out_dir = Path(merged["output"]["dir"])
        write_outputs(out, out_dir)
        write_report(out, settings, out_dir)

        meta = {
            "state": "done",
            "scenario": scenario_id,
            "started": _STATUS[scenario_id]["started"],
            "duration_s": round(time.time() - t0, 1),
            "platform": stamp,
            "overrides": scenario.overrides,
        }
        if scenario.eval_applicable:
            from .evalx import score_run
            meta["eval"] = score_run(out_dir / "result.json")
        (run_dir / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        _STATUS[scenario_id] = meta
        return meta
    except Exception as e:  # surfaced to the UI, never swallowed
        meta = {"state": "error", "scenario": scenario_id,
                "error": f"{type(e).__name__}: {e}",
                "trace": traceback.format_exc()[-2000:],
                "duration_s": round(time.time() - t0, 1),
                "platform": platform_stamp()}
        _STATUS[scenario_id] = meta
        try:
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "meta.json").write_text(
                json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            # The in-memory error remains queryable even if the run directory itself
            # is the failing resource. Lock release in finally is unconditional.
            pass
        return meta
    finally:
        if owns_lock:
            _RUN_LOCK.release()
