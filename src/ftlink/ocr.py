"""Stage S1: page rendering and OCR word boxes.

tesseract is called through its CLI in TSV mode so we get word-level boxes and
confidences (needed for column geometry and cell-level confidence) without extra
python dependencies. 300 dpi / psm 4 are config defaults locked by measurement on
the target document; 400 dpi measurably degrades digit fidelity there.
"""
from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pymupdf


@dataclass(frozen=True)
class Word:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    conf: float  # tesseract 0..100, -1 for non-word rows (filtered out)
    line_key: tuple[int, int, int]  # block, par, line


@dataclass
class PageOcr:
    page: int  # 1-based pdf page
    width_px: int
    height_px: int
    dpi: int
    words: list[Word]
    rotation: int = 0  # render rotation that won orientation recovery

    def lines(self) -> list[list[Word]]:
        by_line: dict[tuple[int, int, int], list[Word]] = {}
        for w in self.words:
            by_line.setdefault(w.line_key, []).append(w)
        out = [sorted(ws, key=lambda w: w.x0) for ws in by_line.values()]
        out.sort(key=lambda ws: min(w.y0 for w in ws))
        return out

    def text(self) -> str:
        return "\n".join(" ".join(w.text for w in line) for line in self.lines())


def render_page(pdf_path: Path, page: int, dpi: int) -> "pymupdf.Pixmap":
    with pymupdf.open(pdf_path) as doc:
        return doc[page - 1].get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)


def page_count(pdf_path: Path) -> int:
    with pymupdf.open(pdf_path) as doc:
        return doc.page_count


def _run_tesseract(png: Path, psm: int, lang: str) -> list[Word]:
    try:
        proc = subprocess.run(
            ["tesseract", str(png), "stdout", "-l", lang, "--psm", str(psm), "tsv"],
            capture_output=True, text=True, check=True, timeout=120,
        )
    except subprocess.TimeoutExpired:
        # one hung page must not stall the whole run; an empty word list takes the
        # same degraded path as an unreadable page (guarded by STR_SUMMARY_RANGE
        # on configured pages)
        return []
    words: list[Word] = []
    for line in proc.stdout.splitlines()[1:]:
        f = line.split("\t")
        if len(f) < 12 or f[11].strip() == "":
            continue
        conf = float(f[10])
        if conf < 0:
            continue
        left, top, w, h = int(f[6]), int(f[7]), int(f[8]), int(f[9])
        words.append(Word(
            text=f[11], x0=left, y0=top, x1=left + w, y1=top + h, conf=conf,
            line_key=(int(f[2]), int(f[3]), int(f[4])),
        ))
    return words


def ocr_page(pdf_path: Path, page: int, dpi: int = 300, psm: int = 4, lang: str = "tur") -> PageOcr:
    """OCR one page. Some scanned pages carry wide tables printed sideways (page
    /Rotate does not correct the underlying scan), so when the upright pass yields
    almost no words the page is re-rendered at 90/270/180 and the orientation with
    the most recognized words wins. Deterministic: fixed order, strict improvement."""
    zoom = dpi / 72.0

    def quality(words: list[Word]) -> int:
        # sideways text still yields many 1-char low-confidence junk words, so raw
        # word count misleads; count confident multi-char words instead
        return sum(1 for w in words if w.conf >= 60 and len(w.text) >= 3)

    best: tuple[int, list[Word], int, int, int] | None = None  # quality, words, w, h, angle
    with pymupdf.open(pdf_path) as doc, tempfile.TemporaryDirectory() as td:
        for angle in (0, 90, 270, 180):
            mat = pymupdf.Matrix(zoom, zoom).prerotate(angle)
            pix = doc[page - 1].get_pixmap(matrix=mat, colorspace=pymupdf.csGRAY)
            png = Path(td) / f"p{angle}.png"
            pix.save(png)
            words = _run_tesseract(png, psm, lang)
            q = quality(words)
            if best is None or q > best[0]:
                best = (q, words, pix.width, pix.height, angle)
            if best[0] >= 30 and angle == 0:
                break  # upright clearly readable; skip rotation probes
    assert best is not None
    return PageOcr(page=page, width_px=best[2], height_px=best[3], dpi=dpi, words=best[1],
                   rotation=best[4])
