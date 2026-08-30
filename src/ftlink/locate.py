"""Stage S5: locate the configured footnote's pages automatically.

Primary path: parse the İÇİNDEKİLER (table of contents), resolve the printed-page to
PDF-page offset from page footers, jump to the target. OCR mangles TOC note numbers
("NOT 11" -> "NOT1lI"), so note numbers are recovered with a lookalike-character map
and the result is VERIFIED by re-reading the target page heading. Fallback path: scan
the notes range for a heading that starts with the footnote number. Continuation
pages are followed while the heading repeats with "(devamı)".
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .normalize import tr_lower
from .ocr import PageOcr, ocr_page, page_count

_LOOKALIKE = str.maketrans({"l": "1", "I": "1", "İ": "1", "i": "1", "O": "0", "o": "0", "S": "5", "B": "8"})


def _as_note_no(token: str) -> int | None:
    t = token.strip().rstrip(".,").translate(_LOOKALIKE)
    return int(t) if t.isdigit() and 0 < int(t) < 100 else None


@dataclass
class TocEntry:
    note_no: int
    title: str
    printed_first: int | None


@dataclass
class LocateResult:
    footnote_no: int
    pages: list[int]  # 1-based pdf pages, in order
    title: str
    method: str  # toc | scan
    page_offset: int | None
    verified: bool


def find_toc_page(pdf: Path, dpi: int, psm: int, lang: str, search_upto: int = 8) -> tuple[int, PageOcr] | None:
    for pg in range(1, min(search_upto, page_count(pdf)) + 1):
        ocr = ocr_page(pdf, pg, dpi, psm, lang)
        if "içindekiler" in tr_lower(ocr.text()):
            return pg, ocr
    return None


RE_TOC_LINE = re.compile(r"^NOT\s*([0-9lIİiOoSB.,]{1,4})\s+(.{3,80})$")
RE_TOC_PAGES = re.compile(r"(?:\s|\.)([0-9lIO]{1,3})(?:-[0-9lIO]{1,3})?\s*$")


def parse_toc(ocr: PageOcr) -> list[TocEntry]:
    entries: list[TocEntry] = []
    for line in ocr.text().splitlines():
        line = line.strip()
        m = RE_TOC_LINE.match(line.replace("NOTI", "NOT 1").replace("NOT1", "NOT 1"))
        if not m:
            continue
        no = _as_note_no(m.group(1))  # may be None on OCR damage; sequence renumbering below recovers it
        rest = m.group(2)
        printed = None
        mp = RE_TOC_PAGES.search(rest)
        if mp:
            head = mp.group(1).translate(_LOOKALIKE)
            if head.isdigit():
                printed = int(head)
            rest = rest[: mp.start()]
        title = re.sub(r"[^A-ZÇĞİÖŞÜa-zçğıöşü)\s].*$", "", rest).strip(" .")
        entries.append(TocEntry(note_no=no, title=title, printed_first=printed))
    # OCR damages note numbers ("11" -> "1lI" -> 111). The TOC lists notes in order,
    # so the sequence position is the reliable number: renumber when the parsed
    # sequence is inconsistent, anchoring on the first clean ascending prefix.
    if entries:
        renumbered = [TocEntry(note_no=1 + i, title=e.title, printed_first=e.printed_first)
                      for i, e in enumerate(entries)]
        agreement = sum(1 for a, b in zip(entries, renumbered) if a.note_no == b.note_no)
        # adopt sequence numbering when it agrees with the majority of cleanly parsed
        # numbers (i.e. the list really does start at NOT 1 and is complete)
        parsed = [e for e in entries if e.note_no is not None]
        if parsed and agreement >= len(parsed) * 0.6:
            entries = renumbered
        else:
            entries = parsed
    # printed pages are non-decreasing; a value below the running maximum lost a
    # leading digit to the dot leader and cannot be trusted
    running = 0
    cleaned: list[TocEntry] = []
    for e in entries:
        p = e.printed_first
        if p is not None and p < running:
            p = None
        elif p is not None:
            running = p
        cleaned.append(TocEntry(note_no=e.note_no, title=e.title, printed_first=p))
    return cleaned


def printed_page_number(ocr: PageOcr) -> int | None:
    """The printed folio is the bottom-most short numeric line."""
    lines = ocr.lines()
    for ws in reversed(lines[-4:] if len(lines) >= 4 else lines):
        toks = [w.text.strip() for w in ws]
        if len(toks) == 1 and toks[0].isdigit() and len(toks[0]) <= 3:
            return int(toks[0])
    return None


RE_HEADING = re.compile(r"^\s*([0-9lIİiOo]{1,3})\s*[.\-]?\s*$")


def heading_note_no(ocr: PageOcr) -> int | None:
    """The note number of a footnote page. tesseract usually splits 'NN.' onto its
    own line at the top; the title text may land lines later."""
    for ws in ocr.lines()[:6]:
        txt = " ".join(w.text for w in ws).strip()
        m = RE_HEADING.match(txt)
        if m:
            return _as_note_no(m.group(1))
        m2 = re.match(r"^\s*([0-9lIİiOo]{1,3})\s*[.\-]\s+\S", txt)
        if m2:
            return _as_note_no(m2.group(1))
    return None


def locate_footnote(pdf: Path, footnote_no: int, notes_start_guess: int, dpi: int, psm: int, lang: str,
                    ocr_cache: dict[int, PageOcr] | None = None) -> LocateResult:
    cache = ocr_cache if ocr_cache is not None else {}

    def get(pg: int) -> PageOcr:
        if pg not in cache:
            cache[pg] = ocr_page(pdf, pg, dpi, psm, lang)
        return cache[pg]

    n_pages = page_count(pdf)
    title = ""
    target: int | None = None
    offset: int | None = None
    method = "scan"

    toc = find_toc_page(pdf, dpi, psm, lang)
    if toc is not None:
        toc_pg, toc_ocr = toc
        entries = parse_toc(toc_ocr)
        idx = next((i for i, e in enumerate(entries) if e.note_no == footnote_no), None)
        if idx is not None:
            entry = entries[idx]
            # resolve printed->pdf offset from a nearby probe page footer
            probe = min(toc_pg + 3, n_pages)
            folio = printed_page_number(get(probe))
            if folio is not None:
                offset = probe - folio
                # dot leaders eat leading digits ("... 49-50" -> "... 9-50"), so the
                # printed page is only trusted inside the monotonic neighbor window
                lo = max((e.printed_first for e in entries[:idx] if e.printed_first is not None), default=1)
                hi = min((e.printed_first for e in entries[idx + 1:] if e.printed_first is not None), default=n_pages - offset)
                printed = entry.printed_first
                if printed is not None and lo <= printed <= hi:
                    cand = printed + offset
                    if 1 <= cand <= n_pages and heading_note_no(get(cand)) == footnote_no:
                        target, title, method = cand, entry.title, "toc"
                if target is None and lo <= hi:
                    for cand in range(lo + offset, min(hi + offset, n_pages) + 1):
                        if 1 <= cand and heading_note_no(get(cand)) == footnote_no:
                            target, title, method = cand, entry.title, "toc-bounded-scan"
                            break

    if target is None:
        start = max(1, notes_start_guess)
        for pg in range(start, n_pages + 1):
            if heading_note_no(get(pg)) == footnote_no:
                target, method = pg, "scan"
                break

    if target is None:
        raise RuntimeError(f"footnote {footnote_no} not found (toc and scan both failed)")

    # the footnote's page set is the contiguous run of pages whose heading carries its
    # number; a scan hit may land mid-note, so walk both directions
    first = target
    while first - 1 >= 1 and heading_note_no(get(first - 1)) == footnote_no:
        first -= 1
    pages = [first]
    pg = first + 1
    while pg <= n_pages and heading_note_no(get(pg)) == footnote_no:
        pages.append(pg)
        pg += 1
    target = first

    return LocateResult(footnote_no=footnote_no, pages=pages, title=title, method=method,
                        page_offset=offset, verified=heading_note_no(get(target)) == footnote_no)
