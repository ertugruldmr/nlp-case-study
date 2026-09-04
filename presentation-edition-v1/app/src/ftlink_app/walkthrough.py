"""Stage-by-stage walkthrough of one stored run, derived from result.json alone.

The demo tab this feeds exists to make the pipeline's decomposition visible at the
defense: every stage card below is computed from fields the deliverable already emits
(tables, rows, cells, relations, checks, run.config_echo). No pipeline internals are
re-run and nothing is inferred that the output does not carry.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any


def _rows_index(result: dict) -> dict[str, dict]:
    return {r["row_id"]: r for r in result.get("rows", [])}


def _tables_index(result: dict) -> dict[str, dict]:
    return {t["table_id"]: t for t in result.get("tables", [])}


def _row_label(rows: dict[str, dict], row_id: str) -> str:
    r = rows.get(row_id)
    return r.get("label_raw") or r.get("label_norm") or row_id if r else row_id


def _row_page(rows: dict[str, dict], tables: dict[str, dict], row_id: str) -> int | None:
    r = rows.get(row_id)
    if not r:
        return None
    t = tables.get(r["table_id"])
    return t["page"] if t else None


def build(result: dict) -> dict[str, Any]:
    cfg = result.get("run", {}).get("config_echo", {})
    doc_cfg = cfg.get("document", {})
    tables = result.get("tables", [])
    rows = result.get("rows", [])
    cells = result.get("cells", [])
    relations = result.get("relations", [])
    checks = result.get("checks", [])
    rows_by_id = _rows_index(result)
    tables_by_id = _tables_index(result)
    cells_by_row: dict[str, list[dict]] = defaultdict(list)
    for c in cells:
        cells_by_row[c["row_id"]].append(c)
    rows_by_table: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        rows_by_table[r["table_id"]].append(r)

    summary_pages = doc_cfg.get("summary_pages")
    stage_of = {t["table_id"]: (t.get("provenance") or {}).get("stage", "") for t in tables}
    summary_tables = [t for t in tables if stage_of[t["table_id"]].startswith("summary")]
    footnote_tables = [t for t in tables if not stage_of[t["table_id"]].startswith("summary")]

    # S2: page detection + footnote location
    page_checks = [c for c in checks if c["group"] == "structural" and str(c.get("scope", "")).startswith("page_")]
    s2 = {
        "id": "S2", "title": "Page detection and footnote location", "title_tr": "Sayfa tespiti ve dipnot konumu",
        "facts": {
            "configured_summary_pages": summary_pages,
            "configured_footnote_no": doc_cfg.get("footnote_no"),
            "page_offset": result.get("document", {}).get("page_offset"),
            "summary_pages_found": sorted({t["page"] for t in summary_tables}),
            "footnote_pages_found": sorted({t["page"] for t in footnote_tables}),
        },
        "items": [{"check_id": c["check_id"], "scope": c["scope"], "status": c["status"], "detail": c["detail"]} for c in page_checks],
    }

    # S3: table extraction
    s3_items = []
    for t in tables:
        trows = rows_by_table.get(t["table_id"], [])
        n_cells = sum(len(cells_by_row.get(r["row_id"], [])) for r in trows)
        s3_items.append({
            "table_id": t["table_id"], "page": t["page"], "title": t.get("title", ""),
            "stage": stage_of[t["table_id"]], "statement_hint": t.get("statement_hint"),
            "periods": [p.get("label", p.get("period_id")) for p in t.get("periods", [])],
            "rows": len(trows), "cells": n_cells, "confidence": t.get("confidence"),
        })
    roles = Counter(r.get("role") for r in rows)
    s3 = {
        "id": "S3", "title": "Table extraction (structure, headers, hierarchy)", "title_tr": "Tablo çıkarımı (yapı, başlıklar, hiyerarşi)",
        "facts": {"tables": len(tables), "rows": len(rows), "cells": len(cells), "roles": dict(roles),
                  "rows_with_footnote_refs": sum(1 for r in rows if r.get("dipnot_refs"))},
        "items": s3_items,
    }

    # S4: normalization
    states = Counter(c["value"]["state"] for c in cells)
    repaired = [c for c in cells if c["value"].get("repaired")]
    disagreements = [c for c in cells if (c.get("confidence_components") or {}).get("engine_agreement", 1.0) < 1.0]
    low_cells = sorted((c for c in cells if c.get("confidence", 1.0) <= 0.5), key=lambda c: c["confidence"])

    def cell_item(c: dict) -> dict:
        return {"cell_id": c["cell_id"], "row": _row_label(rows_by_id, c["row_id"]),
                "page": _row_page(rows_by_id, tables_by_id, c["row_id"]), "period": c.get("period_id"),
                "state": c["value"]["state"], "raw": c["value"].get("raw"), "value": c["value"].get("value"),
                "repaired": bool(c["value"].get("repaired")), "confidence": c.get("confidence"),
                "components": c.get("confidence_components")}
    s4 = {
        "id": "S4", "title": "Number normalization (parentheses, separators, dash / empty / zero)", "title_tr": "Sayı normalizasyonu (parantez, ayraç, tire / boş / sıfır)",
        "facts": {"states": dict(states), "repaired_cells": len(repaired), "engine_disagreements": len(disagreements),
                  "cells_at_or_below_0_5": len(low_cells), "ocr": cfg.get("ocr")},
        "items": [cell_item(c) for c in low_cells] + [cell_item(c) for c in repaired if c["confidence"] > 0.5],
    }

    # S6: candidate generation (config + what the relations reveal about ranks)
    ranks = [a.get("rank") for r in relations for a in r.get("approaches", []) if a.get("name") == "cross_encoder" and a.get("rank")]
    s6 = {
        "id": "S6", "title": "Candidate generation (hybrid lexical + dense + value anchor, RRF)", "title_tr": "Aday üretimi (sözcüksel + yoğun + değer çapası, RRF)",
        "facts": {"config": cfg.get("candidates"), "cross_encoder_rank_of_accepted_links": ranks,
                  "referencing_rows": [{"row": r.get("label_raw"), "page": _row_page(rows_by_id, tables_by_id, r["row_id"]), "refs": r.get("dipnot_refs")}
                                       for r in rows if doc_cfg.get("footnote_no") in (r.get("dipnot_refs") or [])]},
        "items": [],
    }

    # S7: linking
    def rel_item(r: dict) -> dict:
        return {"relation_id": r["relation_id"],
                "summary": {"label": _row_label(rows_by_id, r["summary_row_id"]), "page": _row_page(rows_by_id, tables_by_id, r["summary_row_id"])},
                "footnote": {"label": _row_label(rows_by_id, r["footnote_row_id"]), "page": _row_page(rows_by_id, tables_by_id, r["footnote_row_id"])},
                "period_scope": r.get("period_scope"), "relation_type": r.get("relation_type"),
                "approaches": r.get("approaches", []), "agreement": r.get("agreement"), "evidence": r.get("evidence"),
                "confidence": r.get("confidence"), "low_confidence": r.get("low_confidence"),
                "components": r.get("confidence_components", {})}
    agreement = Counter(r.get("agreement") for r in relations)
    s7 = {
        "id": "S7", "title": "Linking (three approaches, where they diverge)", "title_tr": "İlişkilendirme (üç yaklaşım, nerede ayrışıyorlar)",
        "facts": {"config": cfg.get("linking"), "relations": len(relations), "agreement": dict(agreement)},
        "items": [rel_item(r) for r in relations],
    }

    # S8: confidence
    calib = next((c for c in checks if c["check_id"] == "STR_CALIBRATION_CONTROLS"), None)
    s8 = {
        "id": "S8", "title": "Confidence (four levels, calibrated at run time on document controls)", "title_tr": "Güven (dört seviye, doküman kontrolleriyle çalışma anında kalibre)",
        "facts": {"config": cfg.get("confidence"), "calibration_check": calib,
                  "low_confidence_relations": sum(1 for r in relations if r.get("low_confidence")),
                  "table_confidence": [{"table_id": t["table_id"], "confidence": t.get("confidence")} for t in tables]},
        "items": [{"relation_id": r["relation_id"], "confidence": r.get("confidence"), "low_confidence": r.get("low_confidence"),
                   **{k: v for k, v in (r.get("confidence_components") or {}).items()}} for r in relations],
    }

    # S9: validation
    by_group = defaultdict(Counter)
    for c in checks:
        by_group[c["group"]][c["status"]] += 1
    fails = [c for c in checks if c["status"] == "fail"]
    s9 = {
        "id": "S9", "title": "Validation (structural, format, financial + not_evaluable)", "title_tr": "Doğrulama (yapısal, biçimsel, finansal + değerlendirilemez)",
        "facts": {"by_group": {g: dict(cnt) for g, cnt in by_group.items()},
                  "totals": dict(Counter(c["status"] for c in checks))},
        "items": [{"check_id": c["check_id"], "group": c["group"], "scope": c["scope"], "status": c["status"], "detail": c["detail"]} for c in fails],
    }

    # S10: output
    run = result.get("run", {})
    s10 = {
        "id": "S10", "title": "Output (JSON, JSONL, report; quarantined run block)", "title_tr": "Çıktı (JSON, JSONL, rapor; karantinalı run bloğu)",
        "facts": {"schema_version": result.get("schema_version"), "counts": {"tables": len(tables), "rows": len(rows), "cells": len(cells), "relations": len(relations), "checks": len(checks)},
                  "run": {k: run.get(k) for k in ("ftlink_version", "tesseract_version", "models_loaded", "started_at")},
                  "document": result.get("document")},
        "items": [],
    }
    return {"stages": [s2, s3, s4, s6, s7, s8, s9, s10]}
