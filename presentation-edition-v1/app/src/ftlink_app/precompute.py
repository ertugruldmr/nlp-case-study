"""Precompute every precompute-eligible scenario sequentially.

Run once after setup: uv run ftlink-precompute [scenario ...]
Existing runs are skipped unless --force.
"""
from __future__ import annotations

import sys

from . import runner, store
from .registry import BY_ID, SCENARIOS


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    force = "--force" in sys.argv
    unknown = [a for a in args if a not in BY_ID]
    if unknown:
        print(f"unknown scenario id(s): {', '.join(unknown)}. Known: {', '.join(BY_ID)}", file=sys.stderr)
        return 2
    targets = [s for s in SCENARIOS if (s.id in args if args else s.precompute)]
    for s in targets:
        if not force and store.load_result(s.id) is not None:
            print(f"[skip] {s.id}: stored run exists")
            continue
        print(f"[run ] {s.id} ...", flush=True)
        meta = runner.execute(s.id)
        if meta["state"] == "done":
            ev = meta.get("eval") or {}
            cells = ev.get("cells", {})
            rels = ev.get("relations", {})
            print(f"[done] {s.id} in {meta['duration_s']}s"
                  + (f" | cells {cells.get('pct')}% P={rels.get('precision')} "
                     f"R={rels.get('recall')}" if ev else ""))
        else:
            # a failing scenario IS a stored result (meta.json state=error, shown
            # honestly in the UI); the batch continues
            print(f"[FAIL] {s.id}: {meta.get('error')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
