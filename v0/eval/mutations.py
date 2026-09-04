"""Mutation-test the validation stage on the live pipeline.

Three corruptions are injected between table assembly and everything downstream
(linking, calibration, validation); each must be caught by the matching check
group, and the clean reference run must show no new failures. This makes the
"the checks actually catch things" claim re-runnable rather than asserted.
Run after setup (about 3 minutes, 4 pipeline runs):
    uv run python eval/mutations.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]

# (id, page, row-label substring, period substring or None=all periods, delta,
#  expected catcher check_ids: at least one NEW failure must come from this set)
MUTATIONS = [
    ("member_digit", 5, "ticari alacaklar", "2011", Decimal(1000000),
     {"FIN_PARENT_SUM"}),
    ("grand_total", 5, "toplam varlıklar", "2012", Decimal(-500000),
     {"FIN_GRAND_TOTAL"}),
    ("link_row_values", 5, "yatırım amaçlı gayrimenkuller", None, Decimal(7),
     {"REL_COVERAGE"}),
]


def run_pipeline(mutation=None):
    import ftlink.pipeline as P
    from ftlink.config import Settings
    from ftlink.normalize import tr_lower

    merged = yaml.safe_load((ROOT / "configs/default.yaml").read_text(encoding="utf-8"))
    merged["document"]["pdf_path"] = str(ROOT / merged["document"]["pdf_path"])
    tmp = tempfile.mkdtemp(prefix="ftlink_mut_")
    merged["output"]["dir"] = tmp
    merged["output"]["emit_report_html"] = False

    orig = P.assemble_table
    if mutation is not None:
        mid, page, label_sub, period_sub, delta, _expected = mutation

        def wrapper(raw, table_idx, stage, title=""):
            asm = orig(raw, table_idx, stage, title)
            if raw.page != page:
                return asm
            for row, vr in zip(asm.rows, asm.vrows):
                if label_sub not in tr_lower(row.label_raw):
                    continue
                for cell in asm.cells:
                    if cell.row_id != row.row_id or cell.value.state != "number":
                        continue
                    if period_sub and period_sub not in cell.period_id:
                        continue
                    new = cell.value.value + delta
                    cell.value.value = new
                    cell.value.raw = f"{new:,}".replace(",", ".")
                    vr.values[cell.period_id] = new
            return asm

        P.assemble_table = wrapper
    try:
        out = P.run(Settings(**merged))
    finally:
        P.assemble_table = orig
    fails = sorted((c.check_id, c.scope) for c in out.checks if c.status == "fail")
    return fails, len(out.relations)


def main() -> int:
    clean_fails, clean_rels = run_pipeline()
    print(f"clean: {len(clean_fails)} failing checks (the known document defects), "
          f"{clean_rels} relations")
    ok = True
    for m in MUTATIONS:
        fails, n_rels = run_pipeline(m)
        new = [f for f in fails if f not in clean_fails]
        # not merely "something failed": the NAMED check group must be the catcher
        expected = m[5]
        caught = any(f[0] in expected for f in new)
        ok &= caught
        print(f"{m[0]}: NEW failing checks {new or 'NONE'} | relations {n_rels}"
              f" | expected {sorted(expected)} | "
              f"{'CAUGHT by expected check' if caught else 'MISSED'}")
    print("MUTATIONS:", "all caught" if ok else "MISSED SOME", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
