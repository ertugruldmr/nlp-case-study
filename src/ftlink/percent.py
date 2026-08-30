"""Stage S3b: rate-table percent rescue.

The primary OCR engine cannot read the % glyph on this scan class: measured on the
footnote-11 valuation assumptions table, tesseract renders %9 as 49 or 9, %86,6 as
486,6 or 086,6, at every dpi/psm combination tried, while RapidOCR reads all six
rate cells verbatim. So for RATE ROWS ONLY the two engines swap roles: RapidOCR
reads each value-column crop as the primary, tesseract re-reads the same crop
(psm 7, symbol whitelist) as the cross-check vote. Tesseract's % corruption is a
leading-character artifact, so digit agreement is tested exact-or-suffix. Both
readings are recorded in the cell's confidence components; a disagreement caps the
confidence instead of being arbitrated silently (same contract as the money-cell
digit verification).

Two measured side effects of the % misread on the primary pass are also repaired:
- a rate line whose value tokens all failed the money test never became a table row
  (the row is re-collected from OCR lines just below the table), and
- a % glyph fused into a 1-2 digit number can masquerade as a footnote reference
  (phantom refs that sit inside a rescued value window are removed).
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import pymupdf

from .normalize import parse_tr_number, tr_lower
from .ocr import PageOcr
from .table_structure import RawCell, RawRow, RawTable
from .verify import SecondEngine, digits_of

WHITELIST = "0123456789%,.-()"


def is_rate_row(label: str) -> bool:
    return "oran" in tr_lower(label)


def is_rate_table(raw: RawTable) -> bool:
    return sum(1 for r in raw.rows if is_rate_row(r.label)) >= 2


def digit_vote(primary_digits: str, tess_digits: str) -> str:
    """exact / suffix / mismatch. Suffix counts as agreement because tesseract's
    % misread prepends digits (measured: %9 -> 49, %86,6 -> 486,6)."""
    if not tess_digits or not primary_digits:
        return "mismatch"
    if tess_digits == primary_digits:
        return "exact"
    if tess_digits.endswith(primary_digits):
        return "suffix"
    return "mismatch"


def _tesseract_crop(png: str, lang: str) -> str:
    proc = subprocess.run(
        ["tesseract", png, "stdout", "-l", lang, "--psm", "7",
         "-c", f"tessedit_char_whitelist={WHITELIST}"],
        capture_output=True, text=True)
    return proc.stdout.strip().replace("\n", " ")


def _collect_missing_rate_rows(ocr: PageOcr, raw: RawTable) -> int:
    """Rate lines whose values all failed the money test were dropped from the
    segment; re-collect them from the OCR lines around the table's y-band."""
    heights = [r.y1 - r.y0 for r in raw.rows if r.y1 > r.y0] or [40.0]
    pitch = sorted(heights)[len(heights) // 2]
    y_lo, y_hi = raw.bbox[1] - 3 * pitch, raw.bbox[3] + 5 * pitch
    added = 0
    for ws in ocr.lines():
        txt = " ".join(w.text for w in ws).strip()
        y0, y1 = min(w.y0 for w in ws), max(w.y1 for w in ws)
        if not (y_lo <= y0 <= y_hi) or len(ws) > 8 or txt.startswith("("):
            continue
        if not is_rate_row(txt) or min(w.x0 for w in ws) > ocr.width_px * 0.5:
            continue
        if any(y0 < r.y1 and y1 > r.y0 for r in raw.rows):
            continue  # already a row
        value_zone = min(raw.columns_x) - ocr.width_px * 0.105 if raw.columns_x else ocr.width_px
        label_words = [w for w in ws if w.x0 < value_zone]
        raw.rows.append(RawRow(
            label=" ".join(w.text for w in label_words).strip(),
            label_x0=min((w.x0 for w in label_words), default=0.0),
            y0=y0, y1=y1, line_words=list(ws),
        ))
        added += 1
    raw.rows.sort(key=lambda r: r.y0)
    return added


def rescue_rate_table(pdf_path: Path, ocr: PageOcr, raw: RawTable, lang: str) -> dict:
    """Mutates rate rows of `raw` in place; returns summary counts."""
    stats = {"rows_added": 0, "cells": 0, "exact": 0, "suffix": 0,
             "mismatch": 0, "unavailable": 0}
    engine = SecondEngine()
    if not engine.available or ocr.rotation != 0 or not raw.columns_x:
        stats["unavailable"] = 1
        return stats
    stats["rows_added"] = _collect_missing_rate_rows(ocr, raw)

    width = ocr.width_px
    windows: list[tuple[int, float, float]] = []
    for c, colx in enumerate(raw.columns_x):
        cx0 = colx - width * 0.105
        if c > 0:
            cx0 = max(cx0, (raw.columns_x[c - 1] + colx) / 2)
        windows.append((c, cx0, colx + width * 0.016))

    zoom = ocr.dpi / 72.0
    with pymupdf.open(pdf_path) as doc, tempfile.TemporaryDirectory() as td:
        page = doc[ocr.page - 1]
        for row in raw.rows:
            if not is_rate_row(row.label):
                continue
            for c, cx0, cx1 in windows:
                clip = pymupdf.Rect(cx0 / zoom, (row.y0 - 8) / zoom,
                                    cx1 / zoom, (row.y1 + 8) / zoom)
                png = str(Path(td) / f"r{round(row.y0)}c{c}.png")
                page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=clip).save(png)
                read = engine.read_text(png)
                if read is None:
                    continue
                text, score = read
                parsed = parse_tr_number(text)
                if parsed is None or parsed[0].state != "number":
                    continue
                value, parse_conf = parsed
                existing = row.cells.get(c)
                if existing is not None and value.kind not in ("percent", "percent_range"):
                    continue  # only a % reading may override the primary engine
                vote = digit_vote(digits_of(value.raw), digits_of(_tesseract_crop(png, lang)))
                stats["cells"] += 1
                stats[vote] += 1
                agreement = {"exact": 1.0, "suffix": 0.7, "mismatch": 0.0}[vote]
                conf = min(0.95, max(0.5, score))
                if vote == "suffix":
                    conf = round(conf * 0.97, 4)
                elif vote == "mismatch":
                    conf = min(conf, 0.4)
                components = {"percent_rescue": 1.0, "engine_agreement": agreement}
                if existing is not None and existing.value.state == "number":
                    stats.setdefault("overrides", []).append(
                        f"row '{row.label[:30]}' col{c}: primary={existing.value.raw} -> {value.raw}")
                row.cells[c] = RawCell(
                    col=c, value=value, parse_conf=parse_conf, ocr_conf=conf,
                    bbox=(cx0, row.y0, cx1, row.y1), stage="percent_rescue",
                    extra_components=components)
            # a % glyph fused into a small integer can be misread as a footnote ref
            if row.dipnot_refs:
                phantom = set()
                for w in row.line_words:
                    t = w.text.strip()
                    if t.isdigit() and int(t) in row.dipnot_refs:
                        center = (w.x0 + w.x1) / 2
                        if any(cx0 <= center <= cx1 for _, cx0, cx1 in windows):
                            phantom.add(int(t))
                row.dipnot_refs = [r for r in row.dipnot_refs if r not in phantom]
    return stats
