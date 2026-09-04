from __future__ import annotations

import os
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2]

# The sealed pipeline is consumed as a library from a sibling checkout. Two layouts
# are supported without configuration: the repository layout (this app lives in
# <repo>/presentation-edition-v1/app, the pipeline in <repo>/v0) and the flat layout
# (app/ and deliverable/ side by side). FTLINK_APP_DELIVERABLE overrides both.
_PIPELINE_CANDIDATES = (
    APP_ROOT.parent / "deliverable",
    APP_ROOT.parents[1] / "v0",
    APP_ROOT.parents[1] / "deliverable",
)


def deliverable_root() -> Path:
    env = os.environ.get("FTLINK_APP_DELIVERABLE")
    if env:
        root = Path(env).resolve()
        if not (root / "configs/default.yaml").exists():
            raise FileNotFoundError(
                f"FTLINK_APP_DELIVERABLE points at {root}, which has no configs/default.yaml")
        return root
    for candidate in _PIPELINE_CANDIDATES:
        root = candidate.resolve()
        if (root / "configs/default.yaml").exists():
            return root
    tried = ", ".join(str(c) for c in _PIPELINE_CANDIDATES)
    raise FileNotFoundError(
        f"pipeline root not found (tried {tried}); set FTLINK_APP_DELIVERABLE")


def runs_root() -> Path:
    env = os.environ.get("FTLINK_APP_RUNS")
    root = Path(env).resolve() if env else APP_ROOT / "runs"
    root.mkdir(parents=True, exist_ok=True)
    return root


def frontend_root() -> Path:
    return APP_ROOT / "frontend"


def benchmarks_root() -> Path:
    return APP_ROOT / "benchmarks"
