"""Stage S3: table structure from OCR word boxes (deterministic x-clustering).

Borderless financial tables give no ruling lines to detect. Structure is recovered
from geometry instead:
- value columns cluster on the RIGHT edge of numeric tokens (money is right-aligned),
- the footnote-reference column is a cluster of small integers left of the values,
- the row label is everything left of that,
- indentation (label x0) encodes the item hierarchy,
- stacked header lines above the first data row carry the period columns; a period is
  matched to a value column by x overlap of its year token.

Tables on a page are split on prose gaps (text-dense lines without money tokens).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .models import DashValue, EmptyValue, NumberValue
from .normalize import DASH_TOKENS, is_numeric_token, parse_tr_number, tr_lower
from .ocr import PageOcr, Word

YEAR_MIN, YEAR_MAX = 1900, 2100


@dataclass
class RawCell:
    col: int
    value: object  # CellValue
    parse_conf: float
    ocr_conf: float
    bbox: tuple[float, float, float, float]
    stage: str | None = None  # overrides the table-level provenance stage
    extra_components: dict[str, float] | None = None


@dataclass
class RawRow:
    label: str
    label_x0: float
    y0: float
    y1: float
    dipnot_refs: list[int] = field(default_factory=list)
    cells: dict[int, RawCell] = field(default_factory=dict)
    line_words: list[Word] = field(default_factory=list)
    section: bool = False


@dataclass
class RawTable:
    page: int
    header_lines: list[str]
    columns_x: list[float]  # right edge per value column, left to right
    period_by_col: dict[int, str]  # col index -> "2012" style year or raw header
    period_kind: str  # instant | duration
    rows: list[RawRow] = field(default_factory=list)
    bbox: tuple[float, float, float, float] = (0, 0, 0, 0)


def _is_money(word: Word) -> bool:
    t = word.text.strip()
    if t in DASH_TOKENS:
        return True
    if not is_numeric_token(t):
        return False
    parsed = parse_tr_number(t)
    if parsed is None or parsed[0].state != "number":
        return False
    v = parsed[0]
    if v.kind in ("percent", "percent_range", "decimal"):
        return True
    iv = int(v.value)
    if "." not in t and YEAR_MIN <= iv <= YEAR_MAX and not t.startswith("("):
        return False  # bare year token belongs to headers, not values
    return "." in t or "(" in t or abs(iv) >= 1000 or t == "0"


def _is_small_ref(word: Word) -> bool:
    t = word.text.strip()
    return t.isdigit() and 1 <= len(t) <= 2


def _cluster_1d(values: list[float], gap: float) -> list[float]:
    """Sort and split on gaps; return cluster centers."""
    if not values:
        return []
    vs = sorted(values)
    groups: list[list[float]] = [[vs[0]]]
    for v in vs[1:]:
        if v - groups[-1][-1] > gap:
            groups.append([v])
        else:
            groups[-1].append(v)
    return [sum(g) / len(g) for g in groups]


def merge_label_rows(rows: list[RawRow], indent_eps: float) -> list[RawRow]:
    """Resolve cell-less labeled lines: wrapped label continuation vs group header.

    Measured on this scan: when a long label wraps, its continuation row prints
    INDENTED under the fragment (~18 px); a group header (Dönem Karı Dağılımı) is
    followed by rows at the SAME left edge. So a cell-less, ref-less labeled line
    merges into the next row only when that row indents past it; otherwise it stays
    as a value-less group-header row. Trailing fragments with no following row are
    dropped (matches the previous behavior).
    """
    merged: list[RawRow] = []
    pending: list[RawRow] = []
    for r in rows:
        if r.section:
            merged.append(r)
            continue
        if not r.cells and not r.dipnot_refs and r.label:
            pending.append(r)
            continue
        while pending:
            frag = pending.pop()  # nearest fragment binds first
            if r.label and r.label_x0 > frag.label_x0 + indent_eps:
                r.label = (frag.label + " " + r.label).strip()
                r.label_x0 = frag.label_x0
            else:
                frag.section = True
                merged.append(frag)
        merged.append(r)
    return merged


def extract_tables(ocr: PageOcr, col_gap_px: float | None = None) -> list[RawTable]:
    lines = ocr.lines()
    gap = col_gap_px if col_gap_px is not None else ocr.width_px * 0.02

    # classify lines
    kinds: list[str] = []
    for ws in lines:
        money = [w for w in ws if _is_money(w)]
        right_money = [w for w in money if w.x1 > ocr.width_px * 0.5]
        text_words = [w for w in ws if not _is_money(w) and not _is_small_ref(w)]
        if right_money and len(text_words) <= 9:
            kinds.append("data")
        elif len(text_words) >= 10:
            kinds.append("prose")
        else:
            kinds.append("other")

    # segment: contiguous data blocks (allowing short "other" gaps of 1-2 lines)
    segments: list[tuple[int, int]] = []
    i = 0
    while i < len(lines):
        if kinds[i] != "data":
            i += 1
            continue
        j, hole = i, 0
        last_data = i
        while j + 1 < len(lines) and hole <= 2:
            j += 1
            if kinds[j] == "data":
                last_data, hole = j, 0
            elif kinds[j] == "prose":
                break
            else:
                hole += 1
        segments.append((i, last_data))
        i = last_data + 1

    tables: list[RawTable] = []
    for seg_start, seg_end in segments:
        data_lines = [lines[k] for k in range(seg_start, seg_end + 1) if kinds[k] == "data"]
        if len(data_lines) < 2:
            continue

        # text-only lines inside the segment are either wrapped row labels or group
        # headers (Dönem Karı Dağılımı); both are kept as cell-less rows and resolved
        # after row construction by the indent rule in merge_label_rows
        text_lines = []
        for k in range(seg_start, seg_end + 1):
            if kinds[k] != "other":
                continue
            ws = lines[k]
            txt = " ".join(w.text for w in ws).strip()
            alpha_words = [w for w in ws if any(ch.isalpha() for ch in w.text)]
            if (len(alpha_words) >= 2 and len(ws) <= 8
                    and not any(_is_money(w) for w in ws)
                    and min(w.x0 for w in ws) < ocr.width_px * 0.5
                    and not txt.startswith("(")):
                text_lines.append(ws)

        # value columns from right edges of NUMERIC money tokens; dash marks are short
        # and would form phantom columns, so they are assigned in a second pass
        rights = [w.x1 for ws in data_lines for w in ws if _is_money(w) and w.text.strip() not in DASH_TOKENS]
        columns_x = _cluster_1d(rights, gap)
        if not columns_x:
            continue

        # header zone: up to 4 non-data lines directly above the segment
        header_top = seg_start
        while header_top - 1 >= 0 and kinds[header_top - 1] == "other" and seg_start - header_top < 4:
            header_top -= 1
        header_lines = [lines[k] for k in range(header_top, seg_start)]

        # a header line that is really a wrapped first-row label: many words, not
        # aligned to value columns, no year token close to a column
        label_fragment = ""
        if header_lines:
            last = header_lines[-1]
            aligned = [w for w in last if min((abs(w.x1 - c) for c in columns_x), default=1e9) < gap]
            if len(last) >= 4 and not aligned and max(w.x1 for w in last) < ocr.width_px * 0.6:
                label_fragment = " ".join(w.text for w in last)
                header_lines = header_lines[:-1]

        # periods: year tokens in header zone mapped to columns by x-overlap
        period_by_col: dict[int, str] = {}
        duration = False
        for ws in header_lines:
            for w in ws:
                t = w.text.strip().rstrip(".")
                if t.isdigit() and YEAR_MIN <= int(t) <= YEAR_MAX and min((abs(w.x1 - c) for c in columns_x), default=1e9) < gap * 2:
                    col = min(range(len(columns_x)), key=lambda c: abs(w.x1 - columns_x[c]))
                    period_by_col.setdefault(col, t)
            joined = tr_lower(" ".join(w.text for w in ws))
            if "1 ocak" in joined and len(ws) <= 7:
                duration = True

        # year headers must explain at least half the columns, else these are
        # category columns (e.g. Arazi ve Arsalar | Binalar | Toplam)
        if len(period_by_col) * 2 < len(columns_x):
            period_by_col = {}
            for ws in header_lines:
                for w in ws:
                    if _is_money(w) or w.conf < 30 or w.x0 < ocr.width_px * 0.4:
                        continue
                    col = min(range(len(columns_x)), key=lambda c: abs(w.x1 - columns_x[c]))
                    if abs(w.x1 - columns_x[col]) < gap * 2:
                        period_by_col[col] = (period_by_col.get(col, "") + " " + w.text).strip()

        table = RawTable(
            page=ocr.page,
            header_lines=[" ".join(w.text for w in ws) for ws in header_lines],
            columns_x=columns_x,
            period_by_col=period_by_col,
            period_kind="duration" if duration else "instant",
        )

        # a short all-caps line at the bottom of the header zone is a section header
        # (VARLIKLAR, KAYNAKLAR): keep it as a value-less group row for hierarchy
        for ws in header_lines[-2:]:
            txt = " ".join(w.text for w in ws).strip()
            alpha = [ch for ch in txt if ch.isalpha()]
            if (1 <= len(ws) <= 2 and alpha and len(txt) <= 24
                    and sum(1 for ch in alpha if ch.isupper()) / len(alpha) >= 0.9
                    and not any(t.text.strip().isdigit() for t in ws)):
                table.rows.append(RawRow(
                    label=txt, label_x0=min(w.x0 for w in ws),
                    y0=min(w.y0 for w in ws), y1=max(w.y1 for w in ws),
                    line_words=list(ws), section=True,
                ))

        for ws in data_lines:
            money = [w for w in ws if _is_money(w)]
            refs = [w for w in ws if _is_small_ref(w) and (not money or w.x1 < min(m.x0 for m in money)) and w.x0 > ocr.width_px * 0.35]
            label_words = [w for w in ws if w not in money and w not in refs]
            label_words = [w for w in label_words if not money or w.x0 < min(m.x0 for m in money)]
            row = RawRow(
                label=" ".join(w.text for w in label_words).strip(),
                label_x0=min((w.x0 for w in label_words), default=0.0),
                y0=min(w.y0 for w in ws),
                y1=max(w.y1 for w in ws),
                dipnot_refs=[int(w.text) for w in refs],
                line_words=ws,
            )
            dashes = [w for w in money if w.text.strip() in DASH_TOKENS]
            numbers = [w for w in money if w.text.strip() not in DASH_TOKENS]
            for w in numbers:
                parsed = parse_tr_number(w.text.strip())
                if parsed is None:
                    continue
                val, pconf = parsed
                col = min(range(len(columns_x)), key=lambda c: abs(w.x1 - columns_x[c]))
                if abs(w.x1 - columns_x[col]) > gap * 2:
                    continue
                cell = RawCell(
                    col=col, value=val, parse_conf=pconf, ocr_conf=w.conf / 100.0,
                    bbox=(w.x0, w.y0, w.x1, w.y1),
                )
                prev = row.cells.get(col)
                if prev is not None:
                    # ghost duplicate: same digits with/without grouping dots; keep the
                    # well-formed higher-confidence token
                    def digits(c: RawCell) -> str:
                        v = c.value
                        return str(v.value) if v.state == "number" else v.state
                    if digits(prev) == digits(cell):
                        if (cell.parse_conf, cell.ocr_conf) <= (prev.parse_conf, prev.ocr_conf):
                            continue
                    elif prev.ocr_conf >= cell.ocr_conf:
                        continue
                row.cells[col] = cell
            # second pass: dash marks by nearest column CENTER (their right edge is
            # not informative), only into still-empty columns
            for w in dashes:
                center = (w.x0 + w.x1) / 2
                free = [c for c in range(len(columns_x)) if c not in row.cells]
                if not free:
                    continue
                col = min(free, key=lambda c: abs(center - (columns_x[c] - gap)))
                if abs(center - (columns_x[col] - gap)) > gap * 3:
                    continue
                row.cells[col] = RawCell(
                    col=col, value=DashValue(raw=w.text.strip()), parse_conf=1.0,
                    ocr_conf=w.conf / 100.0, bbox=(w.x0, w.y0, w.x1, w.y1),
                )
            table.rows.append(row)

        for ws in text_lines:
            table.rows.append(RawRow(
                label=" ".join(w.text for w in ws).strip(),
                label_x0=min(w.x0 for w in ws),
                y0=min(w.y0 for w in ws), y1=max(w.y1 for w in ws),
                line_words=list(ws),
            ))
        table.rows.sort(key=lambda r: r.y0)
        table.rows = merge_label_rows(table.rows, indent_eps=ocr.width_px * 0.004)
        if label_fragment:
            # attach to the first DATA row: rows[0] can be a section header
            first = next((r for r in table.rows if not r.section), None)
            if first is not None:
                first.label = (label_fragment + " " + first.label).strip()

        # coherence filter: a real table has repeated column structure; prose with
        # inline numbers does not. Rate/assumption tables (percent rows) are kept even
        # when OCR shreds the % glyphs, at reduced confidence downstream.
        rate_rows = sum(1 for r in table.rows if "oran" in tr_lower(r.label))
        multi_cell_rows = sum(1 for r in table.rows if len(r.cells) >= 2)
        if rate_rows < 2:
            if multi_cell_rows < 2 and len(table.rows) < 3:
                continue
            if multi_cell_rows == 0:
                col_use: dict[int, int] = {}
                for r in table.rows:
                    for c in r.cells:
                        col_use[c] = col_use.get(c, 0) + 1
                if not col_use or max(col_use.values()) < 3:
                    continue

        xs = [w.x0 for ws in data_lines for w in ws]
        ys = [w.y0 for ws in data_lines for w in ws]
        xe = [w.x1 for ws in data_lines for w in ws]
        ye = [w.y1 for ws in data_lines for w in ws]
        table.bbox = (min(xs), min(ys), max(xe), max(ye))
        tables.append(table)

    return tables


def indent_levels(rows: list[RawRow], quant_px: float = 18.0) -> list[int]:
    """Quantize label x0 into indent levels (0 = leftmost)."""
    if not rows:
        return []
    xs = sorted({r.label_x0 for r in rows if r.label})
    centers = _cluster_1d(xs, quant_px)
    return [min(range(len(centers)), key=lambda i: abs(r.label_x0 - centers[i])) if r.label else 0 for r in rows]


def derive_title(ocr: PageOcr, table_top: float, company: str = "") -> str:
    """Table title from the page-heading block ABOVE the table bbox.

    header_lines cannot carry the title: segmentation starts at the stacked period
    lines inside the table bbox, while real titles print as page-level headings.
    Two heading shapes exist in this document class (KAP audit reports) and both
    are domain conventions, not document specifics:
    - footnote headings: a note number and an uppercase heading ("11. YATIRIM
      AMAÇLI GAYRİMENKULLER"), sometimes split by OCR into two same-height lines;
    - statement headings: an uppercase block under the company name ("BAĞIMSIZ
      DENETİMDEN GEÇMİŞ ... KONSOLİDE BİLANÇO").
    The nearest footnote heading above the table wins (footnote tables belong to
    their note); otherwise the topmost multi-word uppercase block that is not the
    company name. No qualifying line yields an EMPTY title: honest absence beats
    prose fragments in a required field.
    """
    import re

    from rapidfuzz import fuzz

    # merge OCR lines sharing one visual baseline (a note number and its heading
    # print at the same height but come back as two tesseract lines); stacked
    # heading lines must NOT merge, so the tops have to nearly coincide
    merged: list[tuple[float, float, list[Word]]] = []
    for line in ocr.lines():
        y0 = min(w.y0 for w in line)
        y1 = max(w.y1 for w in line)
        if merged:
            p0, p1, ws = merged[-1]
            if abs(y0 - p0) < 0.5 * max(p1 - p0, y1 - y0):
                merged[-1] = (min(p0, y0), max(p1, y1), ws + line)
                continue
        merged.append((y0, y1, list(line)))

    note_heading: str | None = None
    caps_blocks: list[tuple[float, float, str]] = []  # y0, y1, text
    for y0, y1, ws in merged:
        if y1 > table_top + 2:
            continue
        text = " ".join(w.text for w in sorted(ws, key=lambda w: w.x0)).strip()
        if not text:
            continue
        if text.startswith("(") and text.endswith(")"):
            continue  # unit/disclaimer parenthetical
        if company and fuzz.partial_ratio(tr_lower(text), tr_lower(company)) >= 85:
            continue  # page header repeats the company name
        if re.match(r"^\d{1,2}\s*[.)]\s*\S", text):
            note_heading = text  # keep updating: nearest above the table wins
            continue
        letters = [c for c in text if c.isalpha()]
        if len(letters) >= 8 and len(text.split()) >= 2:
            if sum(1 for c in letters if c.isupper()) / len(letters) >= 0.75:
                # join contiguous uppercase lines into one heading block
                if caps_blocks and y0 - caps_blocks[-1][1] < 1.6 * (y1 - y0):
                    b0, b1, btxt = caps_blocks[-1]
                    caps_blocks[-1] = (b0, max(b1, y1), f"{btxt} {text}")
                else:
                    caps_blocks.append((y0, y1, text))

    if note_heading:
        return note_heading
    if caps_blocks:
        return caps_blocks[0][2]
    return ""
