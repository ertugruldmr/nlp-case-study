"""Pipeline orchestration: S0 config through S10 output.

Stage boundaries are explicit; every stage's product is inspectable on the returned
CaseOutput. Deterministic by construction: fixed model versions, temperature-free
models, stable IDs, sorted collections; the run block is the only varying part.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from decimal import Decimal
from pathlib import Path

from .candidates import CandidateGenerator, SideRow
from .confidence import RelationCalibrator, cell_confidence, row_confidence, table_confidence
from .config import Settings
from .linking import Linker, apply_llm_acceptance
from .locate import LocateResult, locate_footnote
from .models import (CaseOutput, Cell, CheckResult, DocumentInfo, Provenance, Relation,
                     RelationApproach, Row, RunInfo, Table, Period)
from .normalize import clean_label, norm_label, row_role, tr_lower
from .ocr import PageOcr, ocr_page
from .percent import is_rate_table, rescue_rate_table
from .table_structure import RawTable, derive_title, extract_tables, indent_levels
from . import validation as V

FTLINK_VERSION = "1.0.2"


def _tesseract_version() -> str:
    import subprocess

    try:
        out = subprocess.run(["tesseract", "--version"], capture_output=True, text=True)
        return (out.stdout or out.stderr).splitlines()[0].strip()
    except Exception:
        return "unavailable"


def _slug(s: str) -> str:
    s = tr_lower(s)
    s = re.sub(r"[^a-z0-9çğıöşü]+", "_", s).strip("_")
    return s or "col"


class Assembled:
    def __init__(self, table: Table, rows: list[Row], cells: list[Cell],
                 vrows: list[V.AssembledRow], raw: RawTable) -> None:
        self.table = table
        self.rows = rows
        self.cells = cells
        self.vrows = vrows
        self.raw = raw


def assemble_table(raw: RawTable, table_idx: int, stage: str, title: str = "") -> Assembled:
    table_id = f"p{raw.page:02d}.t{table_idx:02d}"
    # column -> period id
    period_ids: dict[int, str] = {}
    year_cols = all(v.strip().isdigit() for v in raw.period_by_col.values()) and raw.period_by_col
    for col in range(len(raw.columns_x)):
        label = raw.period_by_col.get(col, f"col{col}")
        pid = f"y{label.strip()}" if year_cols else _slug(label)
        if pid in period_ids.values():  # twin headers must not collide silently
            pid = f"{pid}_{col}"
        period_ids[col] = pid
    periods = [Period(period_id=period_ids[c], label=raw.period_by_col.get(c, f"col{c}"),
                      kind="duration" if raw.period_kind == "duration" else "instant")
               for c in range(len(raw.columns_x))]

    levels = indent_levels(raw.rows)
    # a table has flow semantics when it is a dated statement (duration) or a
    # movement table (opening/closing rows present); elsewhere ordinary rows are
    # stock items, not flows
    has_flows = raw.period_kind == "duration" or any(
        row_role(clean_label(r.label)[0]) in ("opening", "closing", "closing_equiv")
        for r in raw.rows)
    rows: list[Row] = []
    cells: list[Cell] = []
    vrows: list[V.AssembledRow] = []
    for k, (rr, lvl) in enumerate(zip(raw.rows, levels)):
        row_id = f"{table_id}.r{k:03d}"
        label, marks = clean_label(rr.label)
        role = row_role(label)
        if getattr(rr, "section", False):
            role = "group_header"
        elif role == "flow" and label.upper().startswith("TOPLAM"):
            role = "total"
        if not label and k == len(raw.rows) - 1 and rr.cells:
            role = "total"  # bottom line of a table printed without a label
        if role == "flow" and not has_flows:
            role = "subitem" if lvl > 0 else "item"
        parent = None
        for prev, plvl in zip(reversed(rows), reversed(levels[:k])):
            if plvl < lvl:
                parent = prev.row_id
                break
        cell_confs: list[float] = []
        values: dict[str, Decimal | None] = {}
        states: dict[str, str] = {}
        repaired: dict[str, bool] = {}
        for col, rc in sorted(rr.cells.items()):
            pid = period_ids.get(col, f"col{col}")
            cv = rc.value
            conf = cell_confidence(rc.ocr_conf, rc.parse_conf)
            components = {"ocr": round(rc.ocr_conf, 4), "parse": rc.parse_conf}
            if rc.extra_components:
                components.update(rc.extra_components)
                if rc.extra_components.get("engine_agreement") == 0.0:
                    conf = round(min(conf, 0.4), 4)
            cell_confs.append(conf)
            cells.append(Cell(
                cell_id=f"{row_id}.c{col:02d}", row_id=row_id, period_id=pid,
                value=cv, confidence=conf,
                confidence_components=components,
                provenance=Provenance(page=raw.page, bbox=rc.bbox, stage=rc.stage or stage),
            ))
            if cv.state == "number" and cv.kind in ("int", "decimal"):
                values[pid] = cv.value
                repaired[pid] = cv.repaired
            else:
                values[pid] = None
                repaired[pid] = False
            states[pid] = cv.state
        penalty = 0.15 if not label else 0.0
        rows.append(Row(
            row_id=row_id, table_id=table_id, label_raw=rr.label, label_norm=norm_label(rr.label),
            indent_level=lvl, role=role, parent_row_id=parent,
            dipnot_refs=rr.dipnot_refs, asterisk_marks=marks,
            confidence=row_confidence(cell_confs, penalty),
            provenance=Provenance(page=raw.page, bbox=(0, rr.y0, 0, rr.y1), stage=stage),
        ))
        vrows.append(V.AssembledRow(row_id, label, role, lvl, values, states, repaired))

    table = Table(
        table_id=table_id, page=raw.page, title=title,
        statement_hint=raw.period_kind, periods=periods,
        confidence=table_confidence([r.confidence for r in rows], len(raw.period_by_col),
                                    len(raw.columns_x)),
        provenance=Provenance(page=raw.page, bbox=raw.bbox, stage=stage),
    )
    return Assembled(table, rows, cells, vrows, raw)


def run(settings: Settings) -> CaseOutput:
    cfg = settings
    pdf = cfg.document.pdf_path
    lo, hi = cfg.document.summary_pages
    ocr_cache: dict[int, PageOcr] = {}

    def get_ocr(pg: int) -> PageOcr:
        if pg not in ocr_cache:
            ocr_cache[pg] = ocr_page(pdf, pg, cfg.ocr.dpi, cfg.ocr.psm, cfg.ocr.lang)
        return ocr_cache[pg]

    # S3b: rate rows swap OCR engines (tesseract cannot read % on this scan class)
    rescue_stats = {"rows_added": 0, "cells": 0, "exact": 0, "suffix": 0,
                    "mismatch": 0, "unavailable": 0}

    def maybe_rescue(raw) -> None:
        if not cfg.ocr.percent_rescue or not is_rate_table(raw):
            return
        for k, v in rescue_rate_table(pdf, get_ocr(raw.page), raw, cfg.ocr.lang).items():
            if isinstance(v, list):
                rescue_stats.setdefault(k, []).extend(v)
            else:
                rescue_stats[k] += v

    # S1+S2+S3: summary pages
    summary_asm: list[Assembled] = []
    for pg in range(lo, hi + 1):
        for raw in extract_tables(get_ocr(pg)):
            maybe_rescue(raw)
            summary_asm.append(assemble_table(
                raw, len(summary_asm), "summary_extraction",
                title=derive_title(get_ocr(pg), raw.bbox[1], cfg.document.company)))

    # S5: locate footnote + extract its tables
    loc: LocateResult = locate_footnote(pdf, cfg.document.footnote_no, notes_start_guess=hi + 4,
                                        dpi=cfg.ocr.dpi, psm=cfg.ocr.psm, lang=cfg.ocr.lang,
                                        ocr_cache=ocr_cache)
    footnote_asm: list[Assembled] = []
    for pg in loc.pages:
        for raw in extract_tables(get_ocr(pg)):
            maybe_rescue(raw)
            footnote_asm.append(assemble_table(
                raw, len(summary_asm) + len(footnote_asm), "footnote_extraction",
                title=derive_title(get_ocr(pg), raw.bbox[1], cfg.document.company)))

    # S6 sides
    def side_values(vr: V.AssembledRow) -> dict[str, Decimal]:
        return {p: v for p, v in vr.values.items() if v is not None}

    summary_side: list[SideRow] = []
    summary_is_flow: dict[str, bool] = {}
    row_lookup: dict[str, Row] = {}
    vrow_lookup: dict[str, V.AssembledRow] = {}
    for asm in summary_asm:
        for row, vr in zip(asm.rows, asm.vrows):
            row_lookup[row.row_id] = row
            vrow_lookup[row.row_id] = vr
            if cfg.document.footnote_no in row.dipnot_refs:
                summary_side.append(SideRow(row.row_id, clean_label(row.label_raw)[0],
                                            row.role, side_values(vr)))
                summary_is_flow[row.row_id] = asm.table.statement_hint == "duration"
    footnote_side: list[SideRow] = []
    for asm in footnote_asm:
        for row, vr in zip(asm.rows, asm.vrows):
            row_lookup[row.row_id] = row
            vrow_lookup[row.row_id] = vr
            footnote_side.append(SideRow(row.row_id, clean_label(row.label_raw)[0],
                                         row.role, side_values(vr)))

    gen = CandidateGenerator(rrf_k=cfg.candidates.rrf_k, anchor_weight=cfg.candidates.anchor_weight,
                             top_k=cfg.candidates.top_k,
                             dense_model=cfg.candidates.dense_model,
                             dense_revision=cfg.candidates.dense_model_revision)
    cands = gen.generate(summary_side, footnote_side)

    # S7 linking
    linker = Linker(cfg.linking.cross_encoder_model, cfg.linking.accept_threshold,
                    lexical_threshold=cfg.linking.lexical_threshold,
                    revision=cfg.linking.cross_encoder_revision,
                    rank1_min_score=cfg.linking.rank1_min_score)
    decisions = linker.link(cands, {s.row_id: s for s in summary_side},
                            {f.row_id: f for f in footnote_side}, summary_is_flow)

    # E27 control expansion: extra configured pages (the cash-flow statement also
    # references the footnote) run through the same candidate+linking machinery,
    # but ONLY to enlarge the calibrator's document-derived control set; their
    # rows, cells and relations never enter the output
    control_decisions: list = []
    control_recons: list[str] = []
    if cfg.confidence.extra_control_pages and footnote_side:
        control_side: list[SideRow] = []
        control_is_flow: dict[str, bool] = {}
        control_vrows: dict[str, V.AssembledRow] = {}
        n_ctrl = 0
        for pg in cfg.confidence.extra_control_pages:
            for raw in extract_tables(get_ocr(pg)):
                asm = assemble_table(raw, 50 + n_ctrl, "control_extraction")
                n_ctrl += 1
                for row, vr in zip(asm.rows, asm.vrows):
                    if cfg.document.footnote_no in row.dipnot_refs:
                        control_side.append(SideRow(row.row_id, clean_label(row.label_raw)[0],
                                                    row.role, side_values(vr)))
                        control_is_flow[row.row_id] = asm.table.statement_hint == "duration"
                        control_vrows[row.row_id] = vr
        if control_side:
            cdec = linker.link(gen.generate(control_side, footnote_side),
                               {s.row_id: s for s in control_side},
                               {f.row_id: f for f in footnote_side}, control_is_flow)
            for d in sorted(cdec, key=lambda d: (d.summary_row_id, d.footnote_row_id)):
                rc = V.check_reconciliation("control", control_vrows[d.summary_row_id].values,
                                            vrow_lookup[d.footnote_row_id].values, d.period_scope)
                control_decisions.append(d)
                control_recons.append(rc.status)

    # optional approach D: LLM select with committed response cache
    if cfg.linking.llm.enabled:
        from .llm import LlmLinker

        llm = LlmLinker(cfg.linking.llm.base_url, cfg.linking.llm.model,
                        cfg.linking.llm.cache_path)
        foot_by_id = {f.row_id: f for f in footnote_side}
        for s in summary_side:
            s_cands = [d for d in decisions if d.summary_row_id == s.row_id]
            cand_tuples = []
            for d in s_cands:
                f = foot_by_id[d.footnote_row_id]
                cand_tuples.append((f.row_id, f.role, f.label,
                                    "; ".join(f"{p}={v}" for p, v in f.values.items())))
            picks = llm.select(s.label, "; ".join(f"{p}={v}" for p, v in s.values.items()),
                               cand_tuples)
            for d in s_cands:
                apply_llm_acceptance(d, d.footnote_row_id in picks)

    # S1b second-engine digit verification (optional dependency; flag over fix)
    all_cells_pre = [c for a in summary_asm + footnote_asm for c in a.cells]
    rotated = {pg for pg, o in ocr_cache.items() if o.rotation != 0}
    if cfg.confidence.second_engine:
        from .verify import verify_cells

        vstats = verify_cells(pdf, all_cells_pre, rotated, cfg.ocr.dpi)
    else:
        vstats = {"checked": 0, "disagree": 0, "unavailable": len(all_cells_pre)}

    # S9 validation
    checks: list[CheckResult] = []
    # S2 made checkable: a configured summary page that yields no coherent financial
    # table fails loudly instead of degrading silently to an empty relation set
    for pg in range(lo, hi + 1):
        n_pg = sum(1 for a in summary_asm if a.table.page == pg)
        checks.append(CheckResult(
            check_id="STR_SUMMARY_RANGE", group="structural", scope=f"page_{pg}",
            status="pass" if n_pg else "fail",
            detail=f"{n_pg} coherent financial table(s) on configured page {pg}"))
    checks.append(CheckResult(
        check_id="STR_FOOTNOTE_REFS_PRESENT", group="structural", scope="document",
        status="pass" if summary_side else "fail",
        detail=f"{len(summary_side)} summary row(s) reference footnote {cfg.document.footnote_no}"))
    checks.append(CheckResult(
        check_id="FMT_ENGINE_AGREEMENT", group="format", scope="document",
        status=("not_evaluable" if vstats.get("unavailable") else
                ("fail" if vstats.get("disagree") else "pass")),
        detail=str(vstats)))
    if cfg.ocr.percent_rescue:
        checks.append(CheckResult(
            check_id="FMT_PERCENT_RESCUE", group="format", scope="document",
            status=("not_evaluable" if not rescue_stats["cells"] else
                    ("fail" if rescue_stats["mismatch"] else "pass")),
            detail=str(rescue_stats)))
    for asm in summary_asm + footnote_asm:
        pids = [p.label for p in asm.table.periods]
        refs = [r for row in asm.rows for r in row.dipnot_refs]
        checks += V.check_structural(asm.table.table_id, [p.strip() for p in pids], True, refs,
                                     loc.verified if asm in footnote_asm else None)
        checks += V.check_format(asm.table.table_id, asm.vrows)
        checks += V.check_percent_bounds(asm.cells)
        roles = {vr.role for vr in asm.vrows}
        period_ids = [p.period_id for p in asm.table.periods]
        if "opening" in roles and "closing" in roles:
            checks += V.check_rollforward(asm.table.table_id, asm.vrows, period_ids)
        total_cols = [p for p in period_ids if "toplam" in p]
        if total_cols:
            checks += V.check_rowwise_sum(asm.table.table_id, asm.vrows, period_ids, total_cols[0])
        if asm in summary_asm:
            children: dict[str, list[V.AssembledRow]] = {}
            has_parent: set[str] = set()
            for row, vr in zip(asm.rows, asm.vrows):
                if row.parent_row_id:
                    children.setdefault(row.parent_row_id, []).append(vr)
                    has_parent.add(row.row_id)
            checks += V.check_hierarchy_sums(asm.table.table_id, asm.vrows, period_ids, children)
            checks += V.check_sign_legality(asm.table.table_id, asm.vrows, period_ids)
            if asm.table.statement_hint == "duration":
                checks += V.check_flow_cascade(asm.table.table_id, asm.vrows, period_ids, has_parent)

    # S8 confidence: reconciliation runs FIRST so the calibrator's control set is
    # grounded in document-derived checks (positives: accepted + reconciled;
    # negatives: rejected by all approaches), then relations are scored
    ordered = sorted(decisions, key=lambda d: (d.summary_row_id, d.footnote_row_id))
    recons: list[CheckResult] = []
    for i, d in enumerate(ordered):
        recons.append(V.check_reconciliation(f"rel{i:03d}", vrow_lookup[d.summary_row_id].values,
                                             vrow_lookup[d.footnote_row_id].values, d.period_scope))
    calib = RelationCalibrator()
    calib.fit_with_checks(ordered + control_decisions,
                          [r.status for r in recons] + control_recons)
    loo = calib.loo_stability()
    checks.append(CheckResult(
        check_id="STR_CALIBRATION_CONTROLS", group="structural", scope="document",
        status="pass" if calib.mode == "fitted" else "not_evaluable",
        detail=(f"mode={calib.mode} positives={calib.n_pos} negatives={calib.n_neg} "
                f"control_pages={list(cfg.confidence.extra_control_pages)}"
                f" separated={str(calib.separated).lower()}"
                + (f" loo_max_delta_p={loo['loo_max_delta_p']}" if loo else "")
                + (f" platt_a={calib.params[0]:.4f} platt_b={calib.params[1]:.4f}"
                   if calib.mode == "fitted" and calib.params else ""))))
    relations: list[Relation] = []
    for i, d in enumerate(ordered):
        if not any(d.approach_accepts.values()):
            continue
        recon = recons[i]
        checks.append(recon)
        # a passing value reconciliation is checksum-grade corroboration: it shrinks
        # the remaining doubt (saturation-free); a failing one debits the probability
        rc = calib.confidence(d, recon.status)
        relations.append(Relation(
            relation_id=f"rel{i:03d}",
            summary_row_id=d.summary_row_id, footnote_row_id=d.footnote_row_id,
            period_scope=d.period_scope, relation_type=d.relation_type,
            approaches=[RelationApproach(name=k, raw_score=round(d.approach_scores[k], 4),
                                         rank=d.approach_ranks.get(k),
                                         accepted=d.approach_accepts[k])
                        for k in sorted(d.approach_scores)],
            agreement=d.agreement, confidence=rc.value,
            confidence_components={**rc.components, "calibration_fitted": 1.0 if rc.calibration == "fitted" else 0.0},
            # forced review routes: fallback-mode numbers are ordinal, a d_only
            # relation was accepted outside the calibrated fusion, and a run
            # without the cross-encoder lost an approach from the comparison
            low_confidence=(rc.value < cfg.confidence.low_confidence_flag
                            or rc.calibration != "fitted"
                            or d.agreement == "d_only"
                            or not linker.ce_available),
            evidence=d.evidence,
        ))

    # a summary row that references the configured footnote but produced zero
    # relations is a silent linking loss; it must ship flagged, not invisible
    # (the referencing rows are the pipeline's own coverage contract)
    for s in summary_side:
        n_rel = sum(1 for r in relations if r.summary_row_id == s.row_id)
        checks.append(CheckResult(
            check_id="REL_COVERAGE", group="structural", scope=s.row_id,
            status="pass" if n_rel else "fail",
            detail=f"{n_rel} relation(s) from row referencing footnote "
                   f"{cfg.document.footnote_no}"))

    all_tables = [a.table for a in summary_asm + footnote_asm]
    all_rows = [r for a in summary_asm + footnote_asm for r in a.rows]
    all_cells = [c for a in summary_asm + footnote_asm for c in a.cells]

    return CaseOutput(
        document=DocumentInfo(
            company=cfg.document.company, period_end=cfg.document.period_end,
            currency=cfg.document.currency, source_pdf=str(pdf),
            source_sha256=hashlib.sha256(Path(pdf).read_bytes()).hexdigest(),
            page_offset=loc.page_offset,
        ),
        run=RunInfo(
            started_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            ftlink_version=FTLINK_VERSION,
            tesseract_version=_tesseract_version(),
            models_loaded={"cross_encoder": linker.ce_available},
            config_echo=json.loads(cfg.model_dump_json()),
        ),
        tables=all_tables, rows=all_rows, cells=all_cells,
        relations=relations, checks=checks,
    )


def write_outputs(out: CaseOutput, out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    result = out_dir / "result.json"
    result.write_text(out.model_dump_json(indent=1), encoding="utf-8")
    rel = out_dir / "relations.jsonl"
    rel.write_text(out.relations_jsonl() + "\n", encoding="utf-8")
    return {"result": result, "relations": rel}
