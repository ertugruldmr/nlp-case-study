"""Build app/benchmarks/*.json from the research artifacts; the sources are only read.

Run: uv run ftlink-benchmarks-sync [--workspace DIR] [--out DIR] [--check]
  workspace = the folder that contains app/, research/ and evidence/ (default: the app's parent)
  out       = the JSON store (default: app/benchmarks)
  --check   = re-derive everything and exit 1 if a committed file differs from its sources
              (writes nothing; this is the drift guard the test suite runs)

One converter per artifact family, each returns a Benchmark. A source that is missing or does not
parse yields a benchmark carrying a "parse_error: ..." note and no invented values. Colab bake-off
results (run-06/07/08) become one converter each, appended to CONVERTERS; nothing else changes.
Files for ids not produced here (hand-dropped benchmarks) are left untouched.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Callable

from pydantic import BaseModel

from . import store
from .benchmarks import PARSE_ERROR_PREFIX, Benchmark, Column, Row
from .evalx import CELLS_RE, CHECKS_RE, RELS_RE
from .paths import APP_ROOT, benchmarks_root

CALIB = "research/assets/experiments/calibration-sensitivity"
TATR = "research/assets/experiments/tatr-local"
RAPIDOCR = "research/assets/experiments/rapidocr-v6-local"
SECOND_DOC = "evidence/second-document-generality.md"
RERANKER = "research/assets/experiments/reranker-swap-local"
RERANKER_NOTE = "evidence/reranker-swap-local.md"
RERANKER_RUN = "reranker-tr-modernbert"
TEXTLAYER = "research/assets/experiments/text-layer-channel"
TEXTLAYER_NOTE = "evidence/text-layer-channel.md"
LOCATOR = "research/assets/experiments/locator-generalization"
LOCATOR_NOTE = "evidence/locator-generalization.md"
CROSSEVAL = "research/assets/experiments/cross-evaluation"
CROSSEVAL_NOTE = "evidence/cross-evaluation.md"
FOLDIN_PLAN = "handoff/RUN0678-FOLDIN-PLAN.md"
BASELINE_META = "app/runs/baseline/meta.json"
BASELINE_RESULT = "app/runs/baseline/outputs/result.json"


class BaselineFacts(BaseModel):
    relations: int
    low_conf: int
    checks_pass: int
    checks_fail: int
    checks_ne: int
    rows: int
    cells: int
    tables_by_page: dict[int, int]
    tables_summary: int
    tables_footnote: int
    footnote_pages: list[int]
    duration_s: float | None
    cells_correct: int | None
    cells_total: int | None
    cells_pct: float | None
    precision: float | None
    recall: float | None

    @property
    def checks_text(self) -> str:
        return f"{self.checks_pass} / {self.checks_fail} / {self.checks_ne}"


def baseline_facts() -> BaselineFacts | None:
    result = store.load_result("baseline")
    if result is None:
        return None
    s = store.summarize_result("baseline", result) or {}
    ev = s.get("eval") or {}
    lo, hi = result["run"]["config_echo"]["document"]["summary_pages"]
    by_page = Counter(t["page"] for t in result.get("tables", []))
    return BaselineFacts(
        relations=s["relations"], low_conf=s["low_conf_relations"],
        checks_pass=s["checks"]["pass"], checks_fail=s["checks"]["fail"], checks_ne=s["checks"]["not_evaluable"],
        rows=s["rows"], cells=s["cells"], tables_by_page=dict(by_page),
        tables_summary=sum(n for p, n in by_page.items() if lo <= p <= hi),
        tables_footnote=sum(n for p, n in by_page.items() if not lo <= p <= hi),
        footnote_pages=sorted(p for p in by_page if not lo <= p <= hi),
        duration_s=s.get("duration_s"),
        cells_correct=(ev.get("cells") or {}).get("correct"), cells_total=(ev.get("cells") or {}).get("total"),
        cells_pct=(ev.get("cells") or {}).get("pct"),
        precision=(ev.get("relations") or {}).get("precision"), recall=(ev.get("relations") or {}).get("recall"))


def _err(what: str) -> str:
    return f"{PARSE_ERROR_PREFIX} {what}"


def _mtime(*paths: Path) -> datetime:
    existing = [p for p in paths if p.exists()]
    if not existing:
        return datetime.now().replace(microsecond=0)
    return datetime.fromtimestamp(max(p.stat().st_mtime for p in existing)).replace(microsecond=0)


def _load_json(p: Path) -> tuple[dict | None, str | None]:
    if not p.exists():
        return None, f"{p.name} missing"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return None, f"{p.name} is not valid JSON ({e.msg} at line {e.lineno})"
    if not isinstance(data, dict):
        return None, f"{p.name} is not a JSON object"
    return data, None


def _rel(p: Path, ws: Path) -> str:
    return str(p.relative_to(ws))


def _fit_columns(loo_label: str) -> list[Column]:
    return [Column(key="a", label_tr="a (eğim)", kind="number"), Column(key="b", label_tr="b (kesişim)", kind="number"),
            Column(key="brier_in", label_tr="Brier (örneklem içi)", kind="number"),
            Column(key="brier_loo", label_tr=loo_label, kind="number"),
            Column(key="jackknife", label_tr="jackknife maks Δp", kind="number")]


def _minmax(xs: object) -> tuple[float | None, float | None]:
    if not isinstance(xs, list) or not xs:
        return None, None
    return min(xs), max(xs)


# --- E48/E49: calibration sensitivity (results.json) -----------------------------------------

def calib_prior_variants(ws: Path, base: BaselineFacts | None) -> Benchmark:
    p = ws / CALIB / "results.json"
    d, err = _load_json(p)
    notes: list[str] = []
    rows: list[Row] = []
    variants = (d or {}).get("A_prior_variants")
    if err:
        notes.append(_err(err))
    elif not isinstance(variants, dict):
        notes.append(_err(f"{p.name}: A_prior_variants missing"))
    else:
        cap = d.get("_capture", {})
        if cap:
            notes.append(f"Yakalama: {cap.get('n_decisions')} bağlantı kararı, {cap.get('n_accepted')} kabul; "
                         f"teslimat ağırlıkları {cap.get('weights_shipped')}. Tüm varyantlar bu yakalama üzerinde çevrimdışı aritmetiktir.")
        for name, v in variants.items():
            if v.get("fit", "x") is None:
                rows.append(Row(id=name, label=name, role="rejected", source=_rel(p, ws), note=v.get("note")))
                continue
            lo, hi = _minmax(v.get("relations"))
            rows.append(Row(id=name, label=name, role="shipped" if name == "shipped" else "measured", source=_rel(p, ws),
                            a=v.get("a"), b=v.get("b"), brier_in=v.get("brier_in_sample"),
                            brier_loo=v.get("brier_loo_refit_same_prior"), jackknife=v.get("jackknife_max_dp"),
                            rel_min=lo, rel_max=hi, flagged=v.get("flagged_at_0.5"), note=None))
    has_shipped = any(r.id == "shipped" for r in rows)
    return Benchmark(
        id="calib-prior-variants", title_tr="Kalibrasyon: Platt öncül varyantları (E48)",
        title_en="Calibration: Platt prior variants on the 33 captured controls (E48)",
        measured_at=_mtime(p), source=_rel(p, ws) if p.exists() else str(Path(CALIB) / "results.json"),
        scope="offline refit", baseline="shipped" if has_shipped else None,
        columns=_fit_columns("Brier (LOO, aynı öncül)") + [
            Column(key="rel_min", label_tr="ilişki güveni min", kind="number"),
            Column(key="rel_max", label_tr="ilişki güveni maks", kind="number"),
            Column(key="flagged", label_tr="bayraklı (0,5)", kind="number"),
            Column(key="note", label_tr="not", kind="text")],
        rows=rows, notes_tr=notes,
        decision_rule=("Öncül kararlılığı değil keskinliği belirler: sonlu her fit tek kontrol çıkarıldığında benzer "
                       "miktarda oynar (jackknife sütunu); düzeltilmemiş MLE ayrık kontrollerde sonlu çözüm bulamaz. "
                       "Teslimat yumuşatılmış Platt (en muhafazakar sonlu harita) kalır; yarım güçte yumuşatma daha keskindir."))


def calib_weight_variants(ws: Path, base: BaselineFacts | None) -> Benchmark:
    p = ws / CALIB / "results.json"
    d, err = _load_json(p)
    notes: list[str] = []
    rows: list[Row] = []
    variants = (d or {}).get("B_weight_variants")
    if err:
        notes.append(_err(err))
    elif not isinstance(variants, dict):
        notes.append(_err(f"{p.name}: B_weight_variants missing"))
    else:
        for name, v in variants.items():
            lo, hi = _minmax(v.get("relations"))
            rows.append(Row(id=name, label=name.replace("_", " "), role="shipped" if name.startswith("shipped") else "measured",
                            source=_rel(p, ws), separated=v.get("separated"), min_pos=v.get("min_pos"), max_neg=v.get("max_neg"),
                            a=v.get("a"), b=v.get("b"), brier_in=v.get("brier_in_sample"),
                            brier_loo=v.get("brier_loo_refit_same_prior"), jackknife=v.get("jackknife_max_dp"),
                            rel_min=lo, rel_max=hi, flagged=v.get("flagged_at_0.5"),
                            spearman=v.get("spearman_vs_shipped"), max_abs_delta=v.get("max_abs_delta_vs_shipped")))
        notes.append("Sütun sırası: CE / değer kuralları / sözcüksel ağırlık; 'separated' = en düşük pozitif kontrol en yüksek negatifin üstünde.")
    shipped = next((r.id for r in rows if r.role == "shipped"), None)
    return Benchmark(
        id="calib-weight-variants", title_tr="Kalibrasyon: füzyon ağırlığı varyantları (E49)",
        title_en="Calibration: fusion-weight variants on the 33 captured controls (E49)",
        measured_at=_mtime(p), source=_rel(p, ws) if p.exists() else str(Path(CALIB) / "results.json"),
        scope="offline refit", baseline=shipped,
        columns=[Column(key="separated", label_tr="kontroller ayrışık", kind="bool"),
                 Column(key="min_pos", label_tr="min pozitif", kind="number"),
                 Column(key="max_neg", label_tr="maks negatif", kind="number")]
                + _fit_columns("Brier (LOO)") + [
                 Column(key="rel_min", label_tr="ilişki güveni min", kind="number"),
                 Column(key="rel_max", label_tr="ilişki güveni maks", kind="number"),
                 Column(key="flagged", label_tr="bayraklı (0,5)", kind="number"),
                 Column(key="spearman", label_tr="Spearman vs teslimat", kind="number"),
                 Column(key="max_abs_delta", label_tr="maks |Δgüven| vs teslimat", kind="number")],
        rows=rows, notes_tr=notes,
        decision_rule=("Karar: kontroller ayrışık kalmalı ve teslimata göre sıralama (Spearman) korunmalı. Değer kanalı "
                       "sıfırlanan varyant ayrışmayı kaybeder ve ilişkiler bayraklanır; CE sıfırlanan varyant ayrışmayı "
                       "korur ama sıralamayı bozar. Teslimat ağırlıkları kalır."))


def calib_text_only_threshold(ws: Path, base: BaselineFacts | None) -> Benchmark:
    p = ws / CALIB / "results.json"
    d, err = _load_json(p)
    notes: list[str] = []
    rows: list[Row] = []
    variants = (d or {}).get("C_text_only_threshold")
    if err:
        notes.append(_err(err))
    elif not isinstance(variants, dict):
        notes.append(_err(f"{p.name}: C_text_only_threshold missing"))
    else:
        for name, v in variants.items():
            lex = name.rsplit("_", 1)[-1]
            rows.append(Row(id=name, label=f"sözcüksel skor {lex}", role="measured", source=_rel(p, ws),
                            lexical=float(lex) if lex.replace(".", "", 1).isdigit() else None,
                            fused_needed=v.get("fused_needed"), cross_encoder_needed=v.get("cross_encoder_needed")))
        notes.append("Değer kuralları kanalı 0 iken (yalnız metin) kabul eşiğine ulaşmak için gereken çapraz-kodlayıcı skoru.")
    return Benchmark(
        id="calib-text-only-threshold", title_tr="Kalibrasyon: yalnız-metin kabul eşiği (E49)",
        title_en="Calibration: cross-encoder score needed for a text-only acceptance (E49)",
        measured_at=_mtime(p), source=_rel(p, ws) if p.exists() else str(Path(CALIB) / "results.json"),
        scope="offline refit", baseline=None,
        columns=[Column(key="lexical", label_tr="sözcüksel skor", kind="number"),
                 Column(key="fused_needed", label_tr="gereken birleşik skor", kind="number"),
                 Column(key="cross_encoder_needed", label_tr="gereken CE skoru", kind="number")],
        rows=rows, notes_tr=notes,
        decision_rule=("Kabul için gereken birleşik skor sabittir; sözcüksel katkı arttıkça yalnız metinle kabul için gereken "
                       "çapraz-kodlayıcı skoru düşer. Tablo, eşiğe değer kanalı olmadan neden zor ulaşıldığını gösterir: "
                       "metin eşleşmesi tek başına tasarım gereği yeterli değildir."))


# --- E56: prior-family refits (prior_family.json) ----------------------------------------------

def calib_prior_family(ws: Path, base: BaselineFacts | None) -> Benchmark:
    p = ws / CALIB / "prior_family.json"
    d, err = _load_json(p)
    notes: list[str] = []
    rows: list[Row] = []
    results = (d or {}).get("results")
    if err:
        notes.append(_err(err))
    elif not isinstance(results, dict):
        notes.append(_err(f"{p.name}: results missing"))
    else:
        if d.get("_note"):
            notes.append(str(d["_note"]))
        for name, v in results.items():
            if v.get("fit", "x") is None:
                rows.append(Row(id=name, label=name, role="rejected", source=_rel(p, ws), note=v.get("note")))
                continue
            lo, hi = _minmax(v.get("relations_p_before_feedback"))
            corp = v.get("corp_loo") or {}
            rows.append(Row(id=name, label=name, role="shipped" if name == "shipped_platt" else "measured", source=_rel(p, ws),
                            a=v.get("a"), b=v.get("b"), brier_in=v.get("brier_in_sample"), brier_loo=v.get("brier_loo_same_prior"),
                            jackknife=v.get("jackknife_max_dp"), p_max_neg=v.get("p_at_max_negative_0.10"),
                            p_min_pos=v.get("p_at_min_positive_0.4737"), p_gap_mid=v.get("p_at_gap_midpoint"),
                            corp_mcb=corp.get("MCB"), corp_dsc=corp.get("DSC"), rel_min=lo, rel_max=hi, note=None))
    has_shipped = any(r.id == "shipped_platt" for r in rows)
    return Benchmark(
        id="calib-prior-family", title_tr="Kalibrasyon: öncül ailesi yeniden fitleri (E56)",
        title_en="Calibration: prior-family refits on the 33 captured controls (E56)",
        measured_at=_mtime(p), source=_rel(p, ws) if p.exists() else str(Path(CALIB) / "prior_family.json"),
        scope="offline refit", baseline="shipped_platt" if has_shipped else None,
        columns=_fit_columns("Brier (LOO, kendi öncülü)") + [
            Column(key="p_max_neg", label_tr="p(en yüksek negatif)", kind="number"),
            Column(key="p_min_pos", label_tr="p(en düşük pozitif)", kind="number"),
            Column(key="p_gap_mid", label_tr="p(boşluk ortası)", kind="number"),
            Column(key="corp_mcb", label_tr="CORP MCB (LOO)", kind="number"),
            Column(key="corp_dsc", label_tr="CORP DSC (LOO)", kind="number"),
            Column(key="rel_min", label_tr="ilişki p min (geri besleme öncesi)", kind="number"),
            Column(key="rel_max", label_tr="ilişki p maks (geri besleme öncesi)", kind="number"),
            Column(key="note", label_tr="not", kind="text")],
        rows=rows, notes_tr=notes,
        decision_rule=("Tüm sonlu iki parametreli haritalar kontrol noktalarında uyuşur ve yalnız skor boşluğunda ayrışır "
                       "(p sütunları); N=33 ayrık kontrolde en muhafazakar sonlu harita yumuşatılmış Platt'tır ve birincil "
                       "kalır. CORP ayrışımında DSC tüm fitlerde aynıdır: fark yalnız kalibrasyon hatasındadır (MCB)."))


# --- E50: TATR detection per page (results-t07.json, results-t03.json) ------------------------

def tatr_detection(ws: Path, base: BaselineFacts | None) -> Benchmark:
    runs: list[tuple[str, float, dict, Path]] = []
    notes: list[str] = []
    rows: list[Row] = []
    pages: set[int] = set()
    for tag, thr, name in (("tatr-t07", 0.7, "results-t07.json"), ("tatr-t03", 0.3, "results-t03.json")):
        p = ws / TATR / name
        d, err = _load_json(p)
        if err or not isinstance((d or {}).get("pages"), list):
            notes.append(_err(err or f"{name}: pages missing"))
            continue
        runs.append((tag, thr, d, p))
        pages.update(pg["page"] for pg in d["pages"])
    page_keys = {pg: f"p{pg:02d}" for pg in sorted(pages)}
    gold_by_page: dict[int, int] = {}
    for _, _, d, _ in runs:
        for pg in d["pages"]:
            gold_by_page[pg["page"]] = len(pg.get("gold_tables", []))
    gold_total = sum(gold_by_page.values())
    if runs and base is not None:
        per = {k: base.tables_by_page.get(pg, 0) for pg, k in page_keys.items()}
        rows.append(Row(id="shipped-xclust", label="Teslimat: x-kümeleme (ftlink 1.0.2, taban çizgisi)", role="shipped",
                        source=BASELINE_RESULT, method="x-clustering (heuristic)", threshold=None, **per,
                        total=sum(per.values()), gold=gold_total, rotated=None, seconds=None))
    elif runs:
        notes.append(_err(f"{BASELINE_RESULT} missing: no shipped row"))
    for tag, thr, d, p in runs:
        per = {page_keys[pg["page"]]: pg.get("tables_detected") for pg in d["pages"]}
        rows.append(Row(id=tag, label=f"TATR dedektör, eşik {thr}", role="measured", source=_rel(p, ws),
                        method="table-transformer-detection + structure v1.1-fin", threshold=thr, **per,
                        total=sum(v or 0 for v in per.values()), gold=gold_total,
                        rotated=sum(pg.get("rotated_detections", 0) for pg in d["pages"]),
                        seconds=round(sum(pg.get("seconds", 0.0) for pg in d["pages"]), 1)))
        for pg in d["pages"]:
            if pg.get("regions"):
                shapes = ", ".join(f"{r.get('rows')}x{r.get('cols')} skor {r.get('score_mean')}" for r in pg["regions"])
                gold = ", ".join(f"{g['id']} {g['rows']}x{g['cols']}" for g in pg.get("gold_tables", []))
                notes.append(f"eşik {thr}, s.{pg['page']}: {len(pg['regions'])} bölge [{shapes}]; gold: {gold}")
        if d.get("_note"):
            notes.append(f"{tag}: {d['_note']}")
    src = [ws / TATR / "results-t07.json", ws / TATR / "results-t03.json"]
    return Benchmark(
        id="tatr-detection", title_tr="Tablo tespiti: TATR dedektörü vs teslimat x-kümeleme, sayfa başına (E50)",
        title_en="Table detection: TATR detector vs shipped x-clustering, per page (E50)",
        measured_at=_mtime(*src), source=f"{TATR}/results-t07.json, {TATR}/results-t03.json",
        scope="this document", baseline="shipped-xclust" if any(r.id == "shipped-xclust" for r in rows) else None,
        columns=[Column(key="method", label_tr="yöntem", kind="text"), Column(key="threshold", label_tr="tespit eşiği", kind="number")]
                + [Column(key=k, label_tr=f"s.{pg} tablo", kind="number") for pg, k in page_keys.items()]
                + [Column(key="total", label_tr="toplam tespit", kind="number"), Column(key="gold", label_tr="gold tablo", kind="number"),
                   Column(key="rotated", label_tr="dönmüş tespit", kind="number"), Column(key="seconds", label_tr="süre (CPU)", kind="seconds")],
        rows=rows, notes_tr=notes,
        decision_rule=("Dedektör düşük eşikte gold tablo sayısına yaklaşır ama çift ve dönmüş tespitler sayıma girer; yapı "
                       "doğruluğu (GriTS) bu tabloda yoktur ve GPU koşusuna aittir. Teslimat x-kümeleme sayfa başına tablo "
                       "sayısını korur; TATR konfigürasyon kapılı yükseltme adayı olarak bekler."))


# --- RapidOCR recognizer variants (score-*.log, run-*.log, diff-*-vs-shipped.log) -------------

START_RE = re.compile(r"^START \d\d:\d\d:\d\d ?(.*)$", re.M)
REC_MODEL_RE = re.compile(r"rapidocr/models/(\S+_rec_\S+?\.onnx)")
DONE_RE = re.compile(r"^done in ([\d.]+)s", re.M)
REAL_RE = re.compile(r"^real ([\d.]+)", re.M)
END_RE = re.compile(r"^END .*exit=(\d+)", re.M)
DIFF_RE = re.compile(r"differing cells: raw/value/state=(\d+) confidence-only=(\d+)")
IDENT_RE = re.compile(r"identical outside run block: (True|False)")


def _variant_order(tag: str) -> tuple[int, str]:
    return ({"default": 0, "default-warm": 1}.get(tag, 2), tag)


def rapidocr_variants(ws: Path, base: BaselineFacts | None) -> Benchmark:
    d = ws / RAPIDOCR
    notes: list[str] = []
    rows: list[Row] = []
    scores = sorted(d.glob("score*.log")) if d.is_dir() else []
    if not scores:
        notes.append(_err(f"{RAPIDOCR}: no score*.log found"))
    if base is not None:
        rows.append(Row(id="shipped", label="Teslimat çalıştırması (taban çizgisi)", role="shipped", source=BASELINE_META,
                        setting="teslim edilen konfigürasyon", recognizer=None,
                        cells_correct=base.cells_correct, cells_total=base.cells_total, cells_pct=base.cells_pct,
                        precision=base.precision, recall=base.recall, checks=base.checks_text,
                        pipeline_s=None, wall_s=base.duration_s, value_diffs=0, conf_only_diffs=0, exit=0))
    elif scores:
        notes.append(_err(f"{BASELINE_META} missing: no shipped row"))
    tags = sorted((s.stem.removeprefix("score").removeprefix("-") or "default" for s in scores), key=_variant_order)
    for tag in tags:
        score = d / ("score.log" if tag == "default" else f"score-{tag}.log")
        run = d / ("run.log" if tag == "default" else f"run-{tag}.log")
        diff = d / f"diff-{tag}-vs-shipped.log"
        st = score.read_text(encoding="utf-8", errors="replace")
        vals: dict[str, object] = {}
        if m := CELLS_RE.search(st):
            vals.update(cells_total=int(m[1]), cells_correct=int(m[2]), cells_pct=float(m[3]))
        else:
            notes.append(_err(f"{score.name}: CELLS line not found"))
        if m := RELS_RE.search(st):
            vals.update(precision=float(m[6]), recall=float(m[7]))
        if m := CHECKS_RE.search(st):
            vals["checks"] = f"{m[1]} / {m[2]} / {m[3]}"
        if run.exists():
            rt = run.read_text(encoding="utf-8", errors="replace")
            m = START_RE.search(rt)
            vals["setting"] = (m[1].strip() if m and m[1].strip() else "kütüphane varsayılanı")
            recs = REC_MODEL_RE.findall(rt)
            vals["recognizer"] = recs[-1] if recs else None
            vals["pipeline_s"] = float(m[1]) if (m := DONE_RE.search(rt)) else None
            vals["wall_s"] = float(m[1]) if (m := REAL_RE.search(rt)) else None
            vals["exit"] = int(m[1]) if (m := END_RE.search(rt)) else None
        else:
            notes.append(_err(f"{run.name} missing: no timing for {tag}"))
        if diff.exists():
            dt = diff.read_text(encoding="utf-8", errors="replace")
            if m := DIFF_RE.search(dt):
                vals.update(value_diffs=int(m[1]), conf_only_diffs=int(m[2]))
            if (m := IDENT_RE.search(dt)) and m[1] == "True":
                notes.append(f"{tag}: result.json run bloğu dışında teslimatla bit bit aynı ({diff.name}).")
        rows.append(Row(id=tag, label=f"RapidOCR {tag}", role="measured", source=_rel(score, ws), **vals))
    if scores:
        notes.append("wall_s = `time` real; pipeline_s = boru hattının kendi 'done in' süresi. Teslimat satırında yalnız meta.json süresi vardır.")
    return Benchmark(
        id="rapidocr-recognizer-variants", title_tr="İkinci OCR motoru: RapidOCR tanıyıcı varyantları",
        title_en="Second OCR engine: RapidOCR recognizer variants on the case document",
        measured_at=_mtime(*scores) if scores else _mtime(), source=f"{RAPIDOCR}/score*.log, run*.log, diff-*-vs-shipped.log",
        scope="this document", baseline="shipped" if any(r.id == "shipped" for r in rows) else None,
        columns=[Column(key="setting", label_tr="ayar", kind="text"), Column(key="recognizer", label_tr="tanıyıcı modeli", kind="text"),
                 Column(key="cells_correct", label_tr="doğru hücre", kind="number"), Column(key="cells_total", label_tr="hücre", kind="number"),
                 Column(key="cells_pct", label_tr="hücre doğruluğu", kind="pct"),
                 Column(key="precision", label_tr="ilişki P", kind="number"), Column(key="recall", label_tr="ilişki R", kind="number"),
                 Column(key="checks", label_tr="kontrol geçti / kaldı / değerlendirilemez", kind="text"),
                 Column(key="pipeline_s", label_tr="boru hattı süresi", kind="seconds"), Column(key="wall_s", label_tr="duvar saati", kind="seconds"),
                 Column(key="value_diffs", label_tr="değer farkı vs teslimat", kind="number"),
                 Column(key="conf_only_diffs", label_tr="yalnız güven farkı vs teslimat", kind="number"),
                 Column(key="exit", label_tr="çıkış kodu", kind="number")],
        rows=rows, notes_tr=notes,
        decision_rule=("Tanıyıcı katmanı veya nesli değiştirildiğinde hücre değeri, ilişki ve kontrol değişmiyorsa fark yalnız "
                       "yüzde hücrelerinin güvenindedir (yalnız güven farkı sütunu); bu durumda kütüphane varsayılanı kalır ve "
                       "sürüm sabitlemesi değişmez."))


# --- Second-document generality (evidence note, "Run outcomes" table) ---------------------------

FIRST_NUM_RE = re.compile(r"([\d]+(?:\.\d+)?)")
PIPELINE_S_RE = re.compile(r"pipeline ([\d.]+) s")
VERIFIED_RE = re.compile(r"^verified:\s*(\S+)", re.M)
OUTCOME_KEYS = ("slug", "exit", "wall", "tables", "rows_cells", "footnote_pages", "relations", "checks")


def _md_table_after(text: str, heading: str) -> list[list[str]] | None:
    idx = text.find(f"\n{heading}")
    if idx < 0:
        return None
    table: list[list[str]] = []
    for line in text[idx + 1:].splitlines()[1:]:
        if line.startswith("|"):
            table.append([c.strip() for c in line.strip().strip("|").split("|")])
        elif table:
            break
    return table or None


def second_document(ws: Path, base: BaselineFacts | None) -> Benchmark:
    p = ws / SECOND_DOC
    notes: list[str] = []
    rows: list[Row] = []
    measured_at = _mtime(p)
    if not p.exists():
        notes.append(_err(f"{SECOND_DOC} missing"))
        table = None
    else:
        text = p.read_text(encoding="utf-8")
        if m := VERIFIED_RE.search(text):
            try:
                measured_at = datetime.fromisoformat(m[1])
            except ValueError:
                notes.append(_err(f"frontmatter verified={m[1]!r} is not ISO"))
        table = _md_table_after(text, "## Run outcomes")
        if table is None:
            notes.append(_err(f"{p.name}: '## Run outcomes' table not found"))
        elif len(table[0]) != len(OUTCOME_KEYS):
            notes.append(_err(f"{p.name}: Run outcomes header has {len(table[0])} columns, expected {len(OUTCOME_KEYS)}: {table[0]}"))
            table = None
    if base is not None and table is not None:
        rows.append(Row(id="case-document-shipped", label="Vaka belgesi, teslimat çalıştırması (taban çizgisi)", role="shipped",
                        source=BASELINE_RESULT, exit=0, wall_s=base.duration_s, pipeline_s=None,
                        tables=f"{base.tables_summary} + {base.tables_footnote}", rows_cells=f"{base.rows} / {base.cells}",
                        footnote_pages=", ".join(str(x) for x in base.footnote_pages),
                        relations=f"{base.relations} ({base.low_conf})", checks=base.checks_text))
    elif table is not None:
        notes.append(_err(f"{BASELINE_RESULT} missing: no shipped row"))
    for cells in (table or [])[2:]:
        if len(cells) != len(OUTCOME_KEYS):
            notes.append(_err(f"row {cells[:1]} has {len(cells)} columns"))
            continue
        r = dict(zip(OUTCOME_KEYS, cells))
        m_exit = FIRST_NUM_RE.search(r["exit"])
        m_wall = FIRST_NUM_RE.search(r["wall"])
        m_pipe = PIPELINE_S_RE.search(r["wall"])
        rows.append(Row(id=r["slug"], label=r["slug"], role="measured", source=f"{SECOND_DOC} (Run outcomes)",
                        exit=int(m_exit[1]) if m_exit else None, wall_s=float(m_wall[1]) if m_wall else None,
                        pipeline_s=float(m_pipe[1]) if m_pipe else None, tables=r["tables"], rows_cells=r["rows_cells"],
                        footnote_pages=r["footnote_pages"], relations=r["relations"], checks=r["checks"]))
    if table is not None:
        notes.append("Bu belgeler için gold küme yoktur; doğruluk ifadeleri kanıt notundaki göz kontrolleridir. "
                     "Teslimat satırında tablo sayısı 'özet + dipnot', ilişki sayısı '(düşük güvenli)' biçimindedir.")
    return Benchmark(
        id="second-document-generality", title_tr="Başka belgelerde genellik: mühürlü boru hattı, yalnız konfigürasyon (E51)",
        title_en="Second-document generality: sealed pipeline on documents it never saw, config only (E51)",
        measured_at=measured_at, source=SECOND_DOC, scope="other documents",
        baseline="case-document-shipped" if any(r.id == "case-document-shipped" for r in rows) else None,
        columns=[Column(key="exit", label_tr="çıkış kodu", kind="number"), Column(key="wall_s", label_tr="duvar saati", kind="seconds"),
                 Column(key="pipeline_s", label_tr="boru hattı süresi", kind="seconds"),
                 Column(key="tables", label_tr="tablo (özet + dipnot)", kind="text"), Column(key="rows_cells", label_tr="satır / hücre", kind="text"),
                 Column(key="footnote_pages", label_tr="bulunan dipnot sayfaları", kind="text"),
                 Column(key="relations", label_tr="ilişki (düşük güvenli)", kind="text"),
                 Column(key="checks", label_tr="kontrol geçti / kaldı / değerlendirilemez", kind="text")],
        rows=rows, notes_tr=notes,
        decision_rule=("Sıfır kod değişikliğiyle başka belgelerde davranış: ilişki üreten satırlar konfigürasyon genelliğini, "
                       "çıkış kodu sıfırdan farklı satır ise S5 dipnot bulma sınırını gösterir (başarısızlık analizi girdisi)."))


def _second_doc_row(ws: Path, slug: str) -> dict[str, str] | None:
    """One row of the second-document evidence note's 'Run outcomes' table, by slug."""
    p = ws / SECOND_DOC
    if not p.exists():
        return None
    table = _md_table_after(p.read_text(encoding="utf-8"), "## Run outcomes")
    for cells in (table or [])[2:]:
        if len(cells) == len(OUTCOME_KEYS) and cells[0] == slug:
            return dict(zip(OUTCOME_KEYS, cells))
    return None


# --- E51b: reranker swap (lab run + fixed-control replay) ---------------------------------------

CALIB_DETAIL_RE = re.compile(r"mode=(\w+) positives=(\d+) negatives=(\d+)")


class RunFacts(BaseModel):
    relations: int
    flagged: int
    checks_text: str
    calibration: str | None
    duration_s: float | None
    cells_pct: float | None
    precision: float | None
    recall: float | None


def _run_facts(scenario_id: str) -> RunFacts | None:
    result = store.load_result(scenario_id)
    if result is None:
        return None
    s = store.summarize_result(scenario_id, result) or {}
    ev = s.get("eval") or {}
    detail = next((c.get("detail", "") for c in result.get("checks", [])
                   if c.get("check_id") == "STR_CALIBRATION_CONTROLS"), "")
    m = CALIB_DETAIL_RE.search(detail)
    return RunFacts(
        relations=s["relations"], flagged=s["low_conf_relations"],
        checks_text=f"{s['checks']['pass']} / {s['checks']['fail']} / {s['checks']['not_evaluable']}",
        calibration=f"{m[1]}, {m[2]} poz / {m[3]} neg" if m else None,
        duration_s=s.get("duration_s"), cells_pct=(ev.get("cells") or {}).get("pct"),
        precision=(ev.get("relations") or {}).get("precision"), recall=(ev.get("relations") or {}).get("recall"))


def _replay_cells(variant: dict) -> dict[str, object]:
    lv = variant.get("label_values") or {}
    return {"model": variant.get("model"), "activation": variant.get("activation_fn"),
            "params": variant.get("num_params"), "auc_labels": (variant.get("labels_only") or {}).get("auc"),
            "auc_label_values": lv.get("auc"), "controls_ge_05": lv.get("n_ge_0_5"),
            "brier_loo": (lv.get("replay") or {}).get("brier_loo")}


def reranker_swap(ws: Path, base: BaselineFacts | None) -> Benchmark:
    p = ws / RERANKER / "results.json"
    q = ws / RERANKER / "results-identity-e2e.json"
    d, err = _load_json(p)
    e2e, err_e2e = _load_json(q)
    notes: list[str] = []
    rows: list[Row] = []
    variants = (d or {}).get("variants")
    if err:
        notes.append(_err(err))
    elif not isinstance(variants, dict):
        notes.append(_err(f"{p.name}: variants missing"))
    else:
        shipped = _run_facts("baseline")
        if shipped is None:
            notes.append(_err(f"{BASELINE_RESULT} missing: no shipped row"))
        else:
            rows.append(Row(id="mmarco-shipped", label="Teslimat: mmarco-mMiniLMv2 çapraz-kodlayıcı (ftlink 1.0.2)",
                            role="shipped", source=f"{BASELINE_META}, {RERANKER}/results.json",
                            **_replay_cells(variants.get("mmarco-shipped") or {}),
                            relations=shipped.relations, precision=shipped.precision, recall=shipped.recall,
                            flagged=shipped.flagged, checks=shipped.checks_text, cells_pct=shipped.cells_pct,
                            calibration=shipped.calibration, wall_s=shipped.duration_s))
        wired = _run_facts(RERANKER_RUN)
        if wired is None:
            notes.append(_err(f"app/runs/{RERANKER_RUN}/outputs/result.json missing: no as-wired row"))
        else:
            rows.append(Row(id="modernbert-tr-as-wired", label="modernbert-tr yeniden sıralayıcı, bağlandığı gibi (çift sigmoid)",
                            role="measured", source=f"app/runs/{RERANKER_RUN}/meta.json, {RERANKER}/results.json",
                            **_replay_cells(variants.get("modernbert-tr-as-wired") or {}),
                            relations=wired.relations, precision=wired.precision, recall=wired.recall,
                            flagged=wired.flagged, checks=wired.checks_text, cells_pct=wired.cells_pct,
                            calibration=wired.calibration, wall_s=wired.duration_s))
        if err_e2e:
            notes.append(_err(err_e2e))
        else:
            ev = (e2e or {}).get("eval_relations") or {}
            ch = (e2e or {}).get("checks") or {}
            m = CALIB_DETAIL_RE.search(str((e2e or {}).get("calibration_detail", "")))
            rows.append(Row(id="modernbert-tr-identity", label="modernbert-tr yeniden sıralayıcı, Identity aktivasyonu zorlanmış",
                            role="measured", source=f"{RERANKER}/results-identity-e2e.json, {RERANKER}/results.json",
                            **_replay_cells(variants.get("modernbert-tr-identity") or {}),
                            relations=(e2e or {}).get("relations"), precision=ev.get("precision"), recall=ev.get("recall"),
                            flagged=(e2e or {}).get("flagged"),
                            checks=f"{ch['pass']} / {ch['fail']} / {ch['not_evaluable']}" if ch else None,
                            cells_pct=(e2e or {}).get("eval_cells_pct"),
                            calibration=f"{m[1]}, {m[2]} poz / {m[3]} neg" if m else None,
                            wall_s=(e2e or {}).get("wall_s_models_warm")))
        c = d.get("controls") or {}
        chk = d.get("shipped_run_check") or {}
        notes.append(f"Tekrar oynatma sabit {c.get('n')} kontrol kararı üzerindedir ({c.get('positives')} pozitif / "
                     f"{c.get('negatives')} negatif, {c.get('emitted_relations')} yayımlanan ilişki); etiketler her aday "
                     f"için aynıdır, yalnız çapraz-kodlayıcı değişir.")
        mm = variants.get("mmarco-shipped") or {}
        notes.append(f"Geçerlilik kapısı: mmarco satırı yakalanan skorları maks mutlak fark "
                     f"{mm.get('reproduces_captured_ce_scores_max_abs_diff')} ile yeniden üretir ve teslimat koşusunun "
                     f"a={chk.get('platt_a')}, b={chk.get('platt_b')}, mod={chk.get('mode')} haritasına oturur.")
        notes.append("'kontrol >= 0,5' sütunu aktivasyon sözleşmesini gösterir: modelin konfigürasyonunda "
                     "sbert_ce_default_activation_function yoktur, sentence-transformers tek etiketli çapraz-kodlayıcıyı "
                     "Sigmoid'e düşürür ve boru hattı ikinci bir sigmoid uygular, böylece 33 kontrolün 33'ü kabul barını aşar.")
        notes.append(f"Ön kayıtlı karar kuralı: {FOLDIN_PLAN} (run-07, sonuçlar üretilmeden önce yazıldı).")
    return Benchmark(
        id="reranker-swap", title_tr="Yeniden sıralayıcı takası: Türkçe eğitilmiş çapraz-kodlayıcı (E51b)",
        title_en="Reranker swap: a Turkish-trained cross-encoder against the shipped mmarco model (E51b)",
        measured_at=_mtime(p, q), source=RERANKER_NOTE, scope="this document",
        baseline="mmarco-shipped" if any(r.id == "mmarco-shipped" for r in rows) else None,
        columns=[Column(key="model", label_tr="model", kind="text"),
                 Column(key="activation", label_tr="aktivasyon", kind="text"),
                 Column(key="params", label_tr="parametre", kind="number"),
                 Column(key="auc_labels", label_tr="AUC (yalnız etiket, 33 kontrol)", kind="number"),
                 Column(key="auc_label_values", label_tr="AUC (etiket + değer)", kind="number"),
                 Column(key="controls_ge_05", label_tr="kontrol >= 0,5 (33 içinde)", kind="number"),
                 Column(key="brier_loo", label_tr="birleşik harita LOO Brier", kind="number"),
                 Column(key="relations", label_tr="ilişki", kind="number"),
                 Column(key="precision", label_tr="ilişki P", kind="number"),
                 Column(key="recall", label_tr="ilişki R", kind="number"),
                 Column(key="flagged", label_tr="bayraklı ilişki", kind="number"),
                 Column(key="checks", label_tr="kontrol geçti / kaldı / değerlendirilemez", kind="text"),
                 Column(key="cells_pct", label_tr="hücre doğruluğu", kind="pct"),
                 Column(key="calibration", label_tr="kalibrasyon", kind="text"),
                 Column(key="wall_s", label_tr="duvar saati", kind="seconds")],
        rows=rows, notes_tr=notes,
        decision_rule=("Ön kayıtlı run-07 kuralı: bir yeniden sıralayıcı ancak yalnız-etiket AUC en az 0,05 artarsa VE "
                       "birleşik haritanın LOO Brier'i kötüleşmezse VE model 1 GB altındaysa önerilen takas olur. Üç koşul da "
                       "sağlanıyor, ama tablo takasın 1.0.2'de yalnız konfigürasyonla yapılamayacağını gösteriyor: kabul eşiği "
                       "modelin aktivasyon ölçeğine bağlıdır, bağlandığı gibi her kontrol barı aşar, kalibrasyon geri düşer ve "
                       "P 1,00'den 0,41'e iner. Ölçek düzeltildiğinde bile çalışma noktası P 0,88 verir; teslimat mmarco kalır, "
                       "aktivasyon sözleşmesini okumak bir 1.0.3 işidir."))


# --- E58: PDF text layer as a third per-cell channel ---------------------------------------------

TEXTLAYER_DOCS: tuple[tuple[str, str, str], ...] = (
    ("ozak-gyo-2013", "Özak GYO 31.12.2013 (born-digital)", "report-ozak-2013.json"),
    ("case-document-2012", "Vaka belgesi 31.12.2012 (taranmış)", "report-case-2012.json"),
)


def text_layer_channel(ws: Path, base: BaselineFacts | None) -> Benchmark:
    notes: list[str] = []
    rows: list[Row] = []
    paths: list[Path] = []
    for row_id, label, name in TEXTLAYER_DOCS:
        p = ws / TEXTLAYER / name
        paths.append(p)
        d, err = _load_json(p)
        if err:
            notes.append(_err(err))
            continue
        words = d.get("text_layer_words_per_page") or {}
        differ_records = d.get("differ_records") or []
        cells = d.get("numeric_cells")
        agree = d.get("agree")
        rows.append(Row(id=row_id, label=label, role="measured", source=_rel(p, ws),
                        pages=", ".join(str(x) for x in d.get("pages_used") or []),
                        words=sum(words.values()) if words else None,
                        numeric_cells=cells, agree=agree,
                        agree_pct=round(100.0 * agree / cells, 1) if cells and agree is not None else None,
                        differ=d.get("differ"), text_missing=d.get("text_missing"),
                        text_nonnumeric=d.get("text_nonnumeric"),
                        dropped_leading_1=sum(1 for r in differ_records if r.get("dropped_leading_1")),
                        recovered=d.get("dropped_leading_1_recovered")))
    if rows:
        notes.append(f"Kanal boru hattının içinde değildir: {TEXTLAYER}/textlayer_check.py mühürlü çıktının hücre "
                     f"kutularını PDF metin katmanına yansıtır ve sayıyı boru hattının kendi dilbilgisiyle ayrıştırır; "
                     f"ftlink içe aktarılmaz, 1.0.2 çalıştırılmaz.")
        notes.append("Bir hücre kutusuna en az yüzde 50 alanla düşen kelimeler okunur; karşılaştırma ayrıştırılmış sayı "
                     "üzerindedir, ham dize üzerinde değil.")
    return Benchmark(
        id="text-layer-channel", title_tr="Metin katmanı üçüncü kanal olarak: OCR hücrelerinin çapraz kontrolü (E58)",
        title_en="PDF text layer as a third per-cell channel, cross-checking the sealed OCR read (E58)",
        measured_at=_mtime(*paths), source=TEXTLAYER_NOTE, scope="other documents", baseline=None,
        columns=[Column(key="pages", label_tr="kullanılan sayfalar", kind="text"),
                 Column(key="words", label_tr="metin katmanı kelimesi", kind="number"),
                 Column(key="numeric_cells", label_tr="sayısal hücre", kind="number"),
                 Column(key="agree", label_tr="uyuşan", kind="number"),
                 Column(key="agree_pct", label_tr="uyuşma oranı", kind="pct"),
                 Column(key="differ", label_tr="ayrışan", kind="number"),
                 Column(key="text_missing", label_tr="metin yok", kind="number"),
                 Column(key="text_nonnumeric", label_tr="metin sayı değil", kind="number"),
                 Column(key="dropped_leading_1", label_tr="baştaki 1 düşmüş", kind="number"),
                 Column(key="recovered", label_tr="kurtarılan", kind="number")],
        rows=rows, notes_tr=notes,
        decision_rule=("Metin katmanı yalnız born-digital dosyada bir kanaldır: orada 201 sayısal hücrenin 12'sinde OCR'dan "
                       "ayrışır ve baştaki 1'i düşen 11 hücrenin 11'ini de kurtarır; taranmış vaka belgesinde 182 hücrenin "
                       "182'sinde hiç kelime yoktur, yani kanal atıldır ve teslimatın ölçülen doğruluğunu değiştirmez. "
                       "Bu yüzden konfigürasyon kapılı bir dördüncü doğrulama adayıdır, 1.0.2'de varsayılan değildir."))


# --- E59: locator generalization to the "DIPNOT n" heading convention ---------------------------

LOG_SUMMARY_RE = re.compile(
    r"^tables=(\d+) rows=(\d+) cells=(\d+) relations=(\d+) \(low_conf=(\d+)\) "
    r"checks: (\d+) pass / (\d+) fail / (\d+) not_evaluable", re.M)
LOG_EXIT_RE = re.compile(r"^# \S+ run exit=(\d+) wall=(\d+)s", re.M)


def _log_facts(p: Path) -> tuple[dict[str, object] | None, str | None]:
    if not p.exists():
        return None, f"{p.name} missing"
    t = p.read_text(encoding="utf-8", errors="replace")
    m = LOG_SUMMARY_RE.search(t)
    if not m:
        return None, f"{p.name}: no 'tables=... checks: ...' summary line"
    x = LOG_EXIT_RE.search(t)
    return {"exit": int(x[1]) if x else None, "wall_s": float(x[2]) if x else None,
            "pipeline_s": float(y[1]) if (y := DONE_RE.search(t)) else None,
            "tables": int(m[1]), "rows": int(m[2]), "cells": int(m[3]), "relations": int(m[4]),
            "flagged": int(m[5]), "checks": f"{m[6]} / {m[7]} / {m[8]}"}, None


def _footnote_split(result: dict) -> tuple[str, str]:
    lo, hi = result["run"]["config_echo"]["document"]["summary_pages"]
    by_page = Counter(t["page"] for t in result.get("tables", []))
    summary = sum(n for pg, n in by_page.items() if lo <= pg <= hi)
    return (f"{summary} + {sum(by_page.values()) - summary}",
            ", ".join(str(pg) for pg in sorted(by_page) if not lo <= pg <= hi))


def _identical_outside_run(a: Path, b: Path) -> bool | None:
    if not (a.exists() and b.exists()):
        return None
    try:
        da, db = json.loads(a.read_text(encoding="utf-8")), json.loads(b.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    da.pop("run", None)
    db.pop("run", None)
    return da == db


def locator_generalization(ws: Path, base: BaselineFacts | None) -> Benchmark:
    case_log = ws / LOCATOR / "case-run.log"
    emlak_log = ws / LOCATOR / "emlak-run.log"
    diff = ws / LOCATOR / "locate.diff"
    work_result = ws / LOCATOR / "work/outputs/result.json"
    emlak_result = ws / LOCATOR / "emlak-outputs/result.json"
    notes: list[str] = []
    rows: list[Row] = []
    case, case_err = _log_facts(case_log)
    if case_err:
        notes.append(_err(case_err))
    else:
        d, err = _load_json(work_result)
        split, fn_pages = _footnote_split(d) if d else (None, None)
        if err:
            notes.append(_err(err))
        rows.append(Row(id="case-under-patch", label="Vaka belgesi, yamalı bulucuyla", role="measured",
                        source=f"{LOCATOR}/case-run.log, {LOCATOR}/work/outputs/result.json",
                        **case, tables_split=split, footnote_pages=fn_pages,
                        identical=_identical_outside_run(work_result, ws / "deliverable/outputs/result.json"),
                        note="mühürlü çıktıyla karşılaştırıldı"))
    before = _second_doc_row(ws, "emlak-konut-gyo-2012")
    if before is None:
        notes.append(_err(f"{SECOND_DOC}: no 'emlak-konut-gyo-2012' row in the Run outcomes table"))
    else:
        m_exit = FIRST_NUM_RE.search(before["exit"])
        m_wall = FIRST_NUM_RE.search(before["wall"])
        rows.append(Row(id="emlak-before", label="Emlak Konut GYO 31.12.2012, yamadan önce", role="rejected",
                        source=f"{SECOND_DOC} (Run outcomes)",
                        exit=int(m_exit[1]) if m_exit else None, wall_s=float(m_wall[1]) if m_wall else None,
                        pipeline_s=None, tables=None, tables_split=None, rows=None, cells=None, relations=None,
                        flagged=None, checks=None, footnote_pages=before["footnote_pages"], identical=None,
                        note="S5'te durdu, hiç çıktı yok"))
    emlak, emlak_err = _log_facts(emlak_log)
    if emlak_err:
        notes.append(_err(emlak_err))
    else:
        d, err = _load_json(emlak_result)
        split, fn_pages = _footnote_split(d) if d else (None, None)
        if err:
            notes.append(_err(err))
        rows.append(Row(id="emlak-after", label="Emlak Konut GYO 31.12.2012, yamadan sonra", role="measured",
                        source=f"{LOCATOR}/emlak-run.log, {LOCATOR}/emlak-outputs/result.json",
                        **emlak, tables_split=split, footnote_pages=fn_pages, identical=None,
                        note="dipnot 9 bulundu, gold küme yok"))
    if rows and diff.exists():
        added = sum(1 for line in diff.read_text(encoding="utf-8").splitlines()
                    if line.startswith("+") and not line.startswith("+++"))
        notes.append(f"Yama yalnız S5 kapsamındadır: {LOCATOR}/locate.diff {added} düzenli ifadeyi genişletir "
                     f"(içindekiler satırı ve iki başlık kalıbı). Önek grubu isteğe bağlı olduğundan önceden eşleşen her "
                     f"dize aynı yakalama grubuyla eşleşmeye devam eder.")
    elif rows:
        notes.append(_err(f"{LOCATOR}/locate.diff missing: patch size not stated"))
    if rows:
        notes.append("'aynı' sütunu, yamalı çalışma kopyasının result.json'u ile mühürlü çıktının run bloğu çıkarılmış "
                     "hâllerinin eşitliğidir; bu senkronizasyonda yeniden hesaplanır, not edilmiş bir iddia değildir.")
        notes.append("Bu belgeler için gold küme yoktur; Emlak Konut satırında 98 kontrolün 25'i kalıyor ve iki ilişkinin "
                     "ikisi de bayraklı, yani boru hattının kendi doğrulaması çıkarımı güvenilmez ilan ediyor.")
    return Benchmark(
        id="locator-generalization", title_tr="Dipnot bulucunun genellenmesi: 'DIPNOT n' başlık düzeni (E59)",
        title_en="Locator generalization: widening S5 for the DIPNOT-n heading convention (E59)",
        measured_at=_mtime(case_log, emlak_log, diff), source=LOCATOR_NOTE, scope="other documents", baseline=None,
        columns=[Column(key="exit", label_tr="çıkış kodu", kind="number"),
                 Column(key="wall_s", label_tr="duvar saati", kind="seconds"),
                 Column(key="pipeline_s", label_tr="boru hattı süresi", kind="seconds"),
                 Column(key="tables", label_tr="tablo", kind="number"),
                 Column(key="tables_split", label_tr="tablo (özet + dipnot)", kind="text"),
                 Column(key="rows", label_tr="satır", kind="number"),
                 Column(key="cells", label_tr="hücre", kind="number"),
                 Column(key="relations", label_tr="ilişki", kind="number"),
                 Column(key="flagged", label_tr="bayraklı ilişki", kind="number"),
                 Column(key="checks", label_tr="kontrol geçti / kaldı / değerlendirilemez", kind="text"),
                 Column(key="footnote_pages", label_tr="bulunan dipnot sayfaları", kind="text"),
                 Column(key="identical", label_tr="vaka çıktısı aynı (run bloğu dışında)", kind="bool"),
                 Column(key="note", label_tr="not", kind="text")],
        rows=rows, notes_tr=notes,
        decision_rule=("Genişletme graded belgede atıldır (aynı tablolar, hücreler, ilişkiler ve kontroller) ve daha önce "
                       "çıkış kodu 2 ile duran dosyayı 45 saniyede tamamlar; ama ürettiği iki ilişkinin ikisi de bayraklı ve "
                       "kontrollerin dörtte biri kalıyor. Yani genelleme S5'i açar, çıkarımı doğrulamaz: teslimat 1.0.2 "
                       "değişmedi, benimseme ayrı bir sürüm kararıdır."))


# --- E60: cross-evaluation, recomputing every headline number from raw artifacts -----------------

XEVAL_SECTION_RE = re.compile(r"^== \d+\. (.+) ==$")
XEVAL_METRIC_RE = re.compile(r"^\s*\[(AGREE|DISAGREE)\] (.+?): claimed (.*?) \| recomputed (.*)$")
XEVAL_SUMMARY_RE = re.compile(r"^== SUMMARY: (\d+) checks, (\d+) agree, (\d+) disagree ==$", re.M)


def _split_note(recomputed: str) -> tuple[str, str | None]:
    if recomputed.endswith(")") and "  (" in recomputed:
        head, _, tail = recomputed.rpartition("  (")
        return head.strip(), tail[:-1].strip() or None
    return recomputed.strip(), None


def cross_evaluation(ws: Path, base: BaselineFacts | None) -> Benchmark:
    p = ws / CROSSEVAL / "recompute.out"
    notes: list[str] = []
    rows: list[Row] = []
    if not p.exists():
        notes.append(_err(f"{CROSSEVAL}/recompute.out missing"))
    else:
        text = p.read_text(encoding="utf-8", errors="replace")
        group = ""
        for line in text.splitlines():
            if s := XEVAL_SECTION_RE.match(line):
                group = s[1]
                continue
            if m := XEVAL_METRIC_RE.match(line):
                recomputed, note = _split_note(m[4])
                rows.append(Row(id=f"m{len(rows) + 1:02d}", label=m[2], role="measured", source=_rel(p, ws),
                                group=group, claimed=m[3].strip(), recomputed=recomputed,
                                agree=m[1] == "AGREE", note=note))
        if not rows:
            notes.append(_err(f"{p.name}: no '[AGREE]' / '[DISAGREE]' metric lines"))
        elif s := XEVAL_SUMMARY_RE.search(text):
            notes.append(f"Özet satırı: {s[1]} nicelik yeniden hesaplandı, {s[2]} uyuştu, {s[3]} uyuşmadı "
                         f"({CROSSEVAL}/recompute.py, bağımsız kod; ftlink içe aktarılmadı, boru hattı yeniden çalıştırılmadı, "
                         f"skorlama betikleri çağrılmadı).")
        else:
            notes.append(_err(f"{p.name}: SUMMARY line not found"))
    if rows:
        notes.append("Belgeleme bulgusu 1: LOO Brier'in gerçek değeri 0,008459'dur. Her yerde geçen 4 basamaklı 0,0085 "
                     "doğrudur, ama README bölüm 6 bunu 3 basamakta 0,009 diye yazıyor; bu çift yuvarlamadır, doğru 3 "
                     "basamaklı değer 0,008'dir. Denetimde yayımlanmış bir rakamın veriden çıkmadığı tek yer budur.")
        notes.append("Belgeleme bulgusu 2: skorlayıcının açıklanmayan üçüncü kuralı tam olarak bir hücre taşıyor. "
                     "Ayrıştırılmış değerler farklı olduğunda parantezler atıldıktan sonra ham dizeler eşleşiyorsa hücre "
                     "doğru sayılıyor; bu yüzde aralığı hücresini kurtarıyor. Çıkarım esasen doğrudur, ama bu geri düşüş "
                     "olmasaydı aynı koşu 199/201 yerine 198/201 puan alırdı ve kural listesi bunu da saymalıdır.")
    return Benchmark(
        id="cross-evaluation", title_tr="Çapraz değerlendirme: her başlık sayısının bağımsız yeniden türetilmesi (E60)",
        title_en="Cross-evaluation: every headline number re-derived from raw artifacts by independent code (E60)",
        measured_at=_mtime(p), source=CROSSEVAL_NOTE, scope="this document", baseline=None,
        columns=[Column(key="group", label_tr="küme", kind="text"),
                 Column(key="claimed", label_tr="iddia edilen", kind="text"),
                 Column(key="recomputed", label_tr="yeniden hesaplanan", kind="text"),
                 Column(key="agree", label_tr="uyuşuyor", kind="bool"),
                 Column(key="note", label_tr="not", kind="text")],
        rows=rows, notes_tr=notes,
        decision_rule=("Denetim, yayımlanan hiçbir başlık sayısının boru hattının kendi değerlendirme betiklerine bağlı "
                       "olmadığını gösteriyor: bağımsız eşleştirici, kendi Newton'u, kendi PAV'ı ve kendi tam binom "
                       "toplamıyla her nicelik yeniden türetildi ve tümü uyuştu. Geriye kalan iki iş hesaplama değil "
                       "belgelemedir; ikisi de aşağıdaki notlarda ve savunmada açıkça söylenir."))


CONVERTERS: tuple[Callable[[Path, BaselineFacts | None], Benchmark], ...] = (
    calib_prior_variants, calib_weight_variants, calib_text_only_threshold, calib_prior_family,
    tatr_detection, rapidocr_variants, second_document, reranker_swap, text_layer_channel,
    locator_generalization, cross_evaluation,
)


def _serialize(b: Benchmark) -> str:
    return json.dumps(b.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"


def build(workspace: Path) -> list[Benchmark]:
    """Derive every benchmark from the sources. Same inputs give the same bytes, so this is re-runnable."""
    workspace = workspace.resolve()
    base = baseline_facts()
    return [conv(workspace, base) for conv in CONVERTERS]


def sync(workspace: Path, out: Path) -> list[Benchmark]:
    built = build(workspace)
    out.mkdir(parents=True, exist_ok=True)
    for b in built:
        (out / f"{b.id}.json").write_text(_serialize(b), encoding="utf-8")
    return built


def _first_diff(have: str, want: str) -> str:
    for n, (a, b) in enumerate(zip(have.splitlines(), want.splitlines()), 1):
        if a != b:
            return f"line {n}: committed {a.strip()!r} vs derived {b.strip()!r}"
    return f"committed {len(have.splitlines())} line(s), derived {len(want.splitlines())}"


def check(workspace: Path, out: Path) -> list[str]:
    """Re-derive every benchmark and report the committed files that no longer follow from the sources."""
    drift: list[str] = []
    for b in build(workspace):
        p = out / f"{b.id}.json"
        if not p.exists():
            drift.append(f"{b.id}: {p.name} is not in the store")
            continue
        want, have = _serialize(b), p.read_text(encoding="utf-8")
        if want != have:
            drift.append(f"{b.id}: differs from the sources ({_first_diff(have, want)})")
    return drift


def main() -> int:
    args = sys.argv[1:]
    ws = Path(args[args.index("--workspace") + 1]) if "--workspace" in args else APP_ROOT.parent
    out = Path(args[args.index("--out") + 1]) if "--out" in args else benchmarks_root()
    if "--check" in args:
        drift = check(ws, out)
        for d in drift:
            print(f"[drift] {d}")
        print(f"checked {len(CONVERTERS)} benchmark(s) in {out}: " +
              ("in sync with the sources" if not drift else f"{len(drift)} out of date"))
        return 1 if drift else 0
    for b in sync(ws, out):
        errs = b.parse_errors
        tag = "warn" if errs else "ok  "
        print(f"[{tag}] {b.id}: {len(b.rows)} rows, scope '{b.scope}'" + (f", {len(errs)} parse error(s)" if errs else ""))
        for e in errs:
            print(f"       {e}")
    print(f"wrote {len(CONVERTERS)} benchmark(s) to {out}")
    return 0
