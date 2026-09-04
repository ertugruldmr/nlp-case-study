"""Score pipeline output against the hand-labeled reference cells.

The reference transcribes every cell of the summary pages and the footnote-11
tables directly from the document; it was cross-verified with 77 arithmetic
identities before use. Run after the pipeline: uv run python eval/score.py
"""
import json, sys, unicodedata
from pathlib import Path

ROOT = Path(__file__).parents[1]
gold = json.loads((ROOT / "eval/reference_cells.json").read_text())
out = json.loads((ROOT / "outputs/result.json").read_text())

TR = str.maketrans("İI", "iı")
def low(s): return unicodedata.normalize("NFC", s.translate(TR).lower()).replace("̇", "").lstrip("-“\" ").strip(" .,:")

# --- cell accuracy: match rows by (page, fuzzy label), periods by year/col order ---
from rapidfuzz import fuzz
ext_rows = {r["row_id"]: r for r in out["rows"]}
ext_tables = {t["table_id"]: t for t in out["tables"]}
cells_by_row = {}
for c in out["cells"]:
    cells_by_row.setdefault(c["row_id"], {})[c["period_id"]] = c

def period_map(gt_table, ext_table):
    """gold period id -> extracted period id"""
    gids = [p["id"] for p in gt_table["periods"]]
    eids = [p["period_id"] for p in ext_table["periods"]]
    m = {}
    for g in gids:
        y = g[1:] if g.startswith("p") else g
        hit = next((e for e in eids if y in e), None)
        if hit: m[g] = hit
    if not m and len(gids) <= len(eids):  # category columns (movement): positional
        for g, e in zip(gids, eids): m[g] = e
    return m

total = correct = wrong_val = wrong_state = missing_row = missing_cell = 0
all_used = set()  # extracted rows matched to a reference row (row ids are table-unique)
wrong_examples = []
missing_examples = []
def tbl_vals(tid):
    vs = set()
    for rid, per in [(r["row_id"], cells_by_row.get(r["row_id"], {})) for r in out["rows"] if r["table_id"] == tid]:
        for c in per.values():
            if c["value"]["state"] == "number" and c["value"].get("value") is not None:
                vs.add(abs(float(c["value"]["value"])))
    return vs

for gt in gold["tables"]:
    page = gt["pdf_page"]
    cand_tables = [t for t in out["tables"] if t["page"] == page]
    if len(cand_tables) > 1:
        gvals = {abs(float(c["value"])) for r in gt["rows"] for c in r["values"].values()
                 if c["state"] == "number" and c.get("value") is not None}
        cand_tables = [max(cand_tables, key=lambda t: len(gvals & tbl_vals(t["table_id"])))]
    used = all_used
    # pass 1: exact normalized-label matches reserve their rows first
    exact_map = {}
    for grow in gt["rows"]:
        gl = low(grow["label_raw"])
        if not gl: continue
        for t in cand_tables:
            for rid, er in ext_rows.items():
                if er["table_id"] != t["table_id"] or rid in used: continue
                if low(er["label_raw"]) == gl:
                    exact_map[grow["row_id"]] = (t, er); used.add(rid); break
            if grow["row_id"] in exact_map: break
    for grow in gt["rows"]:
        if grow["row_id"] in exact_map:
            best, best_s = exact_map[grow["row_id"]], 100
        else:
            best, best_s = None, 0
            for t in cand_tables:
                for rid, er in ext_rows.items():
                    if er["table_id"] != t["table_id"] or rid in used: continue
                    s = fuzz.ratio(low(grow["label_raw"]), low(er["label_raw"]))
                    if s > best_s: best, best_s = (t, er), s
        if grow["label_raw"] == "":  # gold total rows w/o label: match empty-label rows
            # several label-less totals can exist on one page: disambiguate by value overlap
            gvals = {abs(float(c["value"])) for c in grow["values"].values()
                     if c["state"] == "number" and c.get("value") is not None}
            best_overlap = -1
            for t in cand_tables:
                for rid, er in ext_rows.items():
                    if er["table_id"] != t["table_id"] or er["label_raw"] != "" or rid in used:
                        continue
                    evals = {abs(float(c["value"]["value"])) for c in cells_by_row.get(rid, {}).values()
                             if c["value"]["state"] == "number" and c["value"].get("value") is not None}
                    overlap = len(gvals & evals)
                    if overlap > best_overlap:
                        best, best_s, best_overlap = (t, er), 100, overlap
        if best is not None and best_s >= 55:
            used.add(best[1]["row_id"])
        if best is None or best_s < 55:
            n = sum(1 for c in grow["values"].values())
            missing_row += 1; total += n; missing_cell += n
            missing_examples.append(("row", grow["row_id"], grow["label_raw"]))
            continue
        t, er = best
        pm = period_map(gt, ext_tables[t["table_id"]])
        ecells = cells_by_row.get(er["row_id"], {})
        # movement tables in gold: values keyed by column ids (arazi_arsalar...) - map positionally
        gkeys = list(grow["values"].keys())
        if not any(k in pm for k in gkeys):
            eids = [p["period_id"] for p in ext_tables[t["table_id"]]["periods"]]
            pm = {g: e for g, e in zip(gkeys, eids)}
        for gk, gc in grow["values"].items():
            total += 1
            ek = pm.get(gk)
            ec = ecells.get(ek) if ek else None
            if ec is None:
                if gc["state"] == "empty": correct += 1
                else:
                    missing_cell += 1
                    missing_examples.append(("cell", grow["row_id"], gk))
                continue
            ev = ec["value"]
            if gc["state"] != ev["state"]:
                wrong_state += 1; wrong_examples.append((grow["row_id"], gk, gc["state"], ev["state"]))
            elif gc["state"] == "number":
                gval = gc.get("value"); eval_ = ev.get("value")
                if gval is not None and eval_ is not None and float(gval) == float(eval_):
                    correct += 1
                elif str(gc.get("value_raw","")).strip("()") == str(ev.get("raw","")).strip("()"):
                    correct += 1
                else:
                    wrong_val += 1
                    wrong_examples.append((grow["row_id"], gk, gc.get("value_raw"), ev.get("raw")))
            else:
                correct += 1
print(f"CELLS: total={total} correct={correct} ({correct/total*100:.1f}%) wrong_val={wrong_val} wrong_state={wrong_state} missing_cell={missing_cell} missing_row={missing_row}")
for w in wrong_examples[:12]: print("   ", w)
for m in missing_examples[:16]: print("    missing:", m)
from scipy.stats import beta  # available through scikit-learn's dependency set
ci_lo = beta.ppf(0.025, correct, total - correct + 1) if correct > 0 else 0.0
ci_hi = beta.ppf(0.975, correct + 1, total - correct) if correct < total else 1.0
print(f"CELLS 95% CI (Clopper-Pearson, n={total}, one document): [{ci_lo:.4f}, {ci_hi:.4f}]")
gold_pages = {gt["pdf_page"] for gt in gold["tables"]}
unmatched = [r for r in out["rows"] if ext_tables[r["table_id"]]["page"] in gold_pages and r["row_id"] not in all_used]
print(f"EXTRACTED rows on reference pages not matched to any reference row: {len(unmatched)} "
      f"(their {sum(len(cells_by_row.get(r['row_id'], {})) for r in unmatched)} cells are outside the cell metric)")
for r in unmatched[:8]: print("    unmatched:", r["row_id"], r["label_raw"])

# --- relation P/R vs gold ---
grels = set()
rowid2gold = {}  # (page, normalized label) -> [gold row ids]; twin movement tables
for gt in gold["tables"]:  # (2012/2011) print identical row labels, so keep lists
    for grow in gt["rows"]:
        rowid2gold.setdefault((gt["pdf_page"], low(grow["label_raw"])), []).append(
            f'{gt["id"]}.{grow["row_id"]}')
def ext2goldrow(rid):
    er = ext_rows[rid]; page = ext_tables[er["table_id"]]["page"]
    ervals = {float(c["value"]["value"]) for c in cells_by_row.get(rid, {}).values()
              if c["value"]["state"] == "number" and c["value"].get("value") is not None}
    if er["label_raw"] == "":
        best, bo = None, -1
        for (p, lab), gids in rowid2gold.items():
            if p != page or lab != "": continue
            for g in gids:
                o = len(ervals & gold_vals_by_row.get(g, set()))
                if o > bo: best, bo = g, o
        return best
    # label similarity first; identical labels (twin tables) split by value overlap
    best, bs, bo = None, 0, -1
    for (p, lab), gids in rowid2gold.items():
        if p != page: continue
        s = fuzz.ratio(low(er["label_raw"]), lab)
        if s < 55: continue
        for g in gids:
            o = len(ervals & gold_vals_by_row.get(g, set()))
            if (s, o) > (bs, bo): best, bs, bo = g, s, o
    return best
gold_vals_by_row = {}
for gt in gold["tables"]:
    for grow in gt["rows"]:
        gold_vals_by_row[f'{gt["id"]}.{grow["row_id"]}'] = {float(c["value"]) for c in grow["values"].values() if c.get("value") is not None and c["state"]=="number"}
for rel in gold["relations"]:
    grels.add((f'{rel["summary_table"]}.{rel["summary_row_id"]}', f'{rel["footnote_table"]}.{rel["footnote_row_id"]}'))
erels = set()
for rel in out["relations"]:
    s = ext2goldrow(rel["summary_row_id"]); f = ext2goldrow(rel["footnote_row_id"])
    if s and f: erels.add((s, f))
tp = len(erels & grels); fp = len(erels - grels); fn = len(grels - erels)
print(f"RELATIONS: gold={len(grels)} predicted={len(erels)} tp={tp} fp={fp} fn={fn} P={tp/max(1,tp+fp):.2f} R={tp/max(1,tp+fn):.2f}")
print("  fp:", sorted(erels - grels)); print("  fn:", sorted(grels - erels))
p_lo = beta.ppf(0.05, tp, fp + 1) if tp > 0 else 0.0
r_lo = beta.ppf(0.05, tp, fn + 1) if tp > 0 else 0.0
print(f"RELATIONS exact one-sided 95% lower bounds (n={len(grels)}): precision >= {p_lo:.3f}, recall >= {r_lo:.3f}")

# --- check counts, so README figures can be verified against the output at a glance ---
from collections import Counter
cc = Counter(c["status"] for c in out["checks"])
print(f"CHECKS: {cc.get('pass', 0)} pass / {cc.get('fail', 0)} fail / {cc.get('not_evaluable', 0)} not_evaluable")
