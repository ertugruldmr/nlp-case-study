"""Re-runnable input-construction ablation for the cross-encoder (approach A).

The README's single most important input decision is that the pair text carries
the row VALUES next to the label. This script reproduces that measurement from
the shipped pipeline output: every summary item that references the configured
footnote is ranked against every footnote row twice, once with labels-only pair
texts and once with the shipped label|values serialization, and the rank of each
reference (gold) link is reported under both.

Run after the pipeline: uv run python eval/ablation.py
"""
import json
import unicodedata
from pathlib import Path

import numpy as np
from rapidfuzz import fuzz

ROOT = Path(__file__).parents[1]
out = json.loads((ROOT / "outputs/result.json").read_text())
gold = json.loads((ROOT / "eval/reference_cells.json").read_text())

TR = str.maketrans("İI", "iı")


def low(s: str) -> str:
    return unicodedata.normalize("NFC", s.translate(TR).lower()).replace("̇", "").strip(" .,:")


tables = {t["table_id"]: t for t in out["tables"]}
rows = {r["row_id"]: r for r in out["rows"]}
cells_by_row: dict[str, list] = {}
for c in out["cells"]:
    cells_by_row.setdefault(c["row_id"], []).append(c)

footnote_no = out["run"]["config_echo"]["document"]["footnote_no"]
summary = [r for r in rows.values()
           if tables[r["table_id"]]["provenance"]["stage"] == "summary_extraction"
           and footnote_no in r["dipnot_refs"]]
footnote = [r for r in rows.values()
            if tables[r["table_id"]]["provenance"]["stage"] == "footnote_extraction"]


def fmt(v: str) -> str:
    d = float(v)
    s = f"{abs(int(d)):,}".replace(",", ".")
    return f"({s})" if d < 0 else s


def pair_text(r: dict, with_values: bool) -> str:
    if not with_values:
        return r["label_raw"]
    vals = " ; ".join(fmt(c["value"]["value"]) for c in cells_by_row.get(r["row_id"], [])
                      if c["value"]["state"] == "number" and c["value"].get("value") is not None)
    return f"{r['label_raw']} | {vals}" if vals else r["label_raw"]


# gold links: map output rows to gold rows by page + label similarity + value overlap
gold_rows = {}
for gt in gold["tables"]:
    for grow in gt["rows"]:
        vals = {abs(float(c["value"])) for c in grow["values"].values()
                if c["state"] == "number" and c.get("value") is not None}
        gold_rows[f"{gt['id']}.{grow['row_id']}"] = (gt["pdf_page"], low(grow["label_raw"]), vals)


def to_gold(r: dict) -> str | None:
    page = tables[r["table_id"]]["page"]
    rvals = {abs(float(c["value"]["value"])) for c in cells_by_row.get(r["row_id"], [])
             if c["value"]["state"] == "number" and c["value"].get("value") is not None}
    best, key = None, (0, -1)
    for gid, (p, lab, gvals) in gold_rows.items():
        if p != page:
            continue
        s = fuzz.ratio(low(r["label_raw"]), lab)
        if r["label_raw"] == "" and lab == "":
            s = 100
        k = (s, len(rvals & gvals))
        if s >= 55 and k > key:
            best, key = gid, k
    return best


gold_links = {(g["summary_table"] + "." + g["summary_row_id"],
               g["footnote_table"] + "." + g["footnote_row_id"]) for g in gold["relations"]}

from sentence_transformers import CrossEncoder  # noqa: E402

cfg = out["run"]["config_echo"]["linking"]
ce = CrossEncoder(cfg["cross_encoder_model"], revision=cfg.get("cross_encoder_revision"))

hit_by: dict[str, dict[str, bool]] = {}
for with_values in (False, True):
    label = "labels+values" if with_values else "labels-only "
    hits = total = 0
    lines = []
    hit_by[label] = {}
    for s in summary:
        s_gold = to_gold(s)
        targets = [f for (gs, gf) in sorted(gold_links) if gs == s_gold
                   for f in [gf]]
        if not targets:
            continue
        scores = ce.predict([(pair_text(s, with_values), pair_text(f, with_values))
                             for f in footnote])
        order = list(np.argsort(-np.asarray(scores), kind="stable"))
        sc = np.asarray(scores, dtype=float)
        margin = float(sc[order[0]] - sc[order[1]]) if len(order) > 1 else float("nan")
        ranked_gold: dict = {}
        for rank, i in enumerate(order, start=1):
            ranked_gold.setdefault(to_gold(footnote[i]), rank)  # best rank wins on twins
        for t in targets:
            total += 1
            rank = ranked_gold.get(t)
            hit = rank is not None and rank <= 5
            hits += 1 if hit else 0
            hit_by[label][f"{s_gold}->{t}"] = hit
            lines.append(f"    {s['label_raw'][:38]:38} -> {t:34} rank {rank}  top1-margin {margin:.4f}")
    print(f"{label}: R@5 = {hits}/{total}")
    for ln in lines:
        print(ln)

# paired comparison on the same reference links (the twin rule above credits the best
# rank across footnote rows that print identical labels, which favours labels-only)
import math  # noqa: E402

lo, hi = hit_by["labels-only "], hit_by["labels+values"]
keys = sorted(set(lo) & set(hi))
b = sum(1 for k in keys if hi[k] and not lo[k])
c = sum(1 for k in keys if lo[k] and not hi[k])
m = b + c
p_two = min(1.0, 2 * sum(math.comb(m, k) for k in range(0, min(b, c) + 1)) / (2 ** m)) if m else 1.0
print(f"PAIRED: n={len(keys)} links; values-only hits {b}, labels-only hits {c}; "
      f"exact McNemar two-sided p = {p_two:.3f} (directional evidence on one document, not a population claim)")
