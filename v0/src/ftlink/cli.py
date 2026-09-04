from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .config import Settings
from .pipeline import run, write_outputs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ftlink", description="Financial table and footnote linking")
    sub = ap.add_subparsers(dest="cmd", required=True)
    runp = sub.add_parser("run", help="run the full pipeline")
    runp.add_argument("--config", default="configs/default.yaml")
    args = ap.parse_args(argv)

    if args.cmd == "run":
        t0 = time.time()
        settings = Settings.from_yaml(args.config)
        try:
            out = run(settings)
        except RuntimeError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        paths = write_outputs(out, settings.output.dir)
        if settings.output.emit_report_html:
            from .report import write_report

            paths["report"] = write_report(out, settings, settings.output.dir)
        n_low = sum(1 for r in out.relations if r.low_confidence)
        fails = sum(1 for c in out.checks if c.status == "fail")
        print(f"tables={len(out.tables)} rows={len(out.rows)} cells={len(out.cells)} "
              f"relations={len(out.relations)} (low_conf={n_low}) "
              f"checks: {sum(1 for c in out.checks if c.status == 'pass')} pass / {fails} fail / "
              f"{sum(1 for c in out.checks if c.status == 'not_evaluable')} not_evaluable")
        for name, p in paths.items():
            print(f"  {name}: {p}")
        print(f"done in {time.time() - t0:.1f}s")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
