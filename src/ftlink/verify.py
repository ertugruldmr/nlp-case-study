"""Second-engine digit verification (optional stage inside S1/S3).

Every numeric cell's crop is re-read by a second OCR engine (RapidOCR, ONNX, no
Turkish dependency needed because digits are language-neutral). The digit strings of
both engines are compared: agreement corroborates the cell, disagreement caps its
confidence and records the second reading. Values are NEVER silently replaced; the
financial validation stage is the arbiter (flag over fix, by design).

Runs only on upright pages: crop geometry on rotation-recovered pages is not mapped
back to PDF space in v1. Degrades gracefully when the optional dependency is absent.
"""
from __future__ import annotations

import re
import tempfile
from pathlib import Path

import pymupdf

_DIGITS = re.compile(r"\d")


class SecondEngine:
    def __init__(self) -> None:
        self._engine = None
        self.available = False
        try:
            from rapidocr import RapidOCR  # type: ignore

            self._engine = RapidOCR()
            self.available = True
        except Exception:
            self.available = False

    def read_digits(self, png_path: str) -> str | None:
        if not self.available:
            return None
        try:
            res = self._engine(png_path, use_det=False, use_cls=False)
            txt = "".join(res.txts) if getattr(res, "txts", None) else ""
        except Exception:
            return None
        digits = "".join(_DIGITS.findall(txt))
        return digits or None

    def read_text(self, png_path: str) -> tuple[str, float] | None:
        """Full text of a crop plus the engine's mean recognition score."""
        if not self.available:
            return None
        try:
            res = self._engine(png_path, use_det=False, use_cls=False)
            txt = ("".join(res.txts) if getattr(res, "txts", None) else "").strip()
            scores = list(getattr(res, "scores", None) or [])
        except Exception:
            return None
        if not txt:
            return None
        return txt, (sum(scores) / len(scores) if scores else 0.0)


def digits_of(raw: str) -> str:
    return "".join(_DIGITS.findall(raw))


def verify_cells(pdf_path: Path, cells, rotated_pages: set[int], dpi: int) -> dict:
    """Mutates cell confidence/components in place; returns summary counts."""
    engine = SecondEngine()
    stats = {"checked": 0, "agree": 0, "disagree": 0, "unavailable": 0, "skipped_rotated": 0}
    if not engine.available:
        stats["unavailable"] = len(cells)
        return stats
    zoom = dpi / 72.0
    with pymupdf.open(pdf_path) as doc, tempfile.TemporaryDirectory() as td:
        for i, cell in enumerate(cells):
            v = cell.value
            if v.state != "number" or v.kind not in ("int", "decimal"):
                continue
            if cell.provenance.page in rotated_pages:
                stats["skipped_rotated"] += 1
                continue
            bbox = cell.provenance.bbox
            if not bbox:
                continue
            x0, y0, x1, y1 = bbox
            pad = 6
            clip = pymupdf.Rect((x0 - pad) / zoom, (y0 - pad) / zoom,
                                (x1 + pad) / zoom, (y1 + pad) / zoom)
            png = str(Path(td) / f"c{i}.png")
            doc[cell.provenance.page - 1].get_pixmap(
                matrix=pymupdf.Matrix(zoom, zoom), clip=clip).save(png)
            second = engine.read_digits(png)
            if second is None:
                continue
            stats["checked"] += 1
            if second == digits_of(v.raw):
                stats["agree"] += 1
                cell.confidence_components["engine_agreement"] = 1.0
                cell.confidence = round(min(1.0, cell.confidence * 1.05), 4)
            else:
                stats["disagree"] += 1
                cell.confidence_components["engine_agreement"] = 0.0
                cell.confidence = round(min(cell.confidence, 0.4), 4)
                stats.setdefault("disagreements", []).append(
                    f"{cell.cell_id}: tesseract={digits_of(v.raw)} rapidocr={second}")
    return stats
