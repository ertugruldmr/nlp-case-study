"""Re-runnability check: run the default configuration twice into scratch directories
and compare result.json outside the quarantined run block.

Exit code 0 when the two outputs are identical (the README claim), 1 otherwise, so a
CI job can guard the property. About one minute (two pipeline runs).
Run after setup: uv run python eval/determinism.py   (or: make determinism)
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]


def run_once() -> tuple[dict, dict]:
    import ftlink.pipeline as P
    from ftlink.config import Settings

    merged = yaml.safe_load((ROOT / "configs/default.yaml").read_text(encoding="utf-8"))
    merged["document"]["pdf_path"] = str(ROOT / merged["document"]["pdf_path"])
    out_dir = Path(tempfile.mkdtemp(prefix="ftlink_det_"))
    merged["output"]["dir"] = str(out_dir)
    merged["output"]["emit_report_html"] = False
    out = P.run(Settings(**merged))
    P.write_outputs(out, out_dir)
    d = json.loads((out_dir / "result.json").read_text(encoding="utf-8"))
    run = d.pop("run")
    return d, run


def main() -> int:
    a, ra = run_once()
    b, rb = run_once()
    canon = lambda d: json.dumps(d, sort_keys=True, ensure_ascii=False)  # noqa: E731
    same = canon(a) == canon(b)
    print(f"DETERMINISM: byte-identical outside the run block: {same}")
    if not same:
        print("  differing top-level keys:", [k for k in a if canon(a[k]) != canon(b.get(k))])
    print(f"  run.started_at: {ra.get('started_at')} vs {rb.get('started_at')} (the only block allowed to differ)")
    return 0 if same else 1


if __name__ == "__main__":
    sys.exit(main())
