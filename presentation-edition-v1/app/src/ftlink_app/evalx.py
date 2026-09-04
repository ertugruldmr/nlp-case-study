"""Score a scenario run with the deliverable's own scorer, without touching it.

The shipped scorer hardcodes ROOT-relative paths (eval/reference_cells.json and
outputs/result.json under the deliverable root). Copying its 150 lines here would
drift; overwriting deliverable/outputs would violate the seal. Instead the scorer
runs inside a throwaway sandbox of symlinks that reproduces the layout it expects,
and its stdout (a stable format printed for exactly this purpose) is parsed.
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

from .paths import deliverable_root

CELLS_RE = re.compile(
    r"CELLS: total=(\d+) correct=(\d+) \(([\d.]+)%\) wrong_val=(\d+) wrong_state=(\d+) "
    r"missing_cell=(\d+) missing_row=(\d+)")
RELS_RE = re.compile(
    r"RELATIONS: gold=(\d+) predicted=(\d+) tp=(\d+) fp=(\d+) fn=(\d+) P=([\d.]+) R=([\d.]+)")
CHECKS_RE = re.compile(r"CHECKS: (\d+) pass / (\d+) fail / (\d+) not_evaluable")


def score_run(result_json: Path, reference: Path | None = None) -> dict:
    """Score with the deliverable's scorer; `reference` swaps the gold file
    (research-side reference sets, e.g. footnote-10), default = the shipped one."""
    droot = deliverable_root()
    ref = (reference or (droot / "eval/reference_cells.json")).resolve()
    with tempfile.TemporaryDirectory() as td:
        sandbox = Path(td)
        (sandbox / "eval").mkdir()
        (sandbox / "outputs").mkdir()
        (sandbox / "eval/score.py").symlink_to(droot / "eval/score.py")
        (sandbox / "eval/reference_cells.json").symlink_to(ref)
        (sandbox / "outputs/result.json").symlink_to(result_json.resolve())
        proc = subprocess.run([sys.executable, str(sandbox / "eval/score.py")],
                              capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        return {"error": (proc.stderr or proc.stdout)[-800:]}
    out = proc.stdout
    res: dict = {"raw": out.strip()}
    if m := CELLS_RE.search(out):
        res["cells"] = {"total": int(m[1]), "correct": int(m[2]), "pct": float(m[3]),
                        "wrong_val": int(m[4]), "wrong_state": int(m[5]),
                        "missing_cell": int(m[6]), "missing_row": int(m[7])}
    if m := RELS_RE.search(out):
        res["relations"] = {"gold": int(m[1]), "predicted": int(m[2]), "tp": int(m[3]),
                            "fp": int(m[4]), "fn": int(m[5]),
                            "precision": float(m[6]), "recall": float(m[7])}
    if m := CHECKS_RE.search(out):
        res["checks"] = {"pass": int(m[1]), "fail": int(m[2]), "not_evaluable": int(m[3])}
    return res
