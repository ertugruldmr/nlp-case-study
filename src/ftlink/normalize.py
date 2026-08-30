"""Stage S4: Turkish financial normalization.

- parse_tr_number: a small explicit grammar for this document class. Parentheses mean
  negative, dot groups thousands, comma is the decimal separator, percent tokens and
  percent ranges occur in valuation tables. Dash, empty and zero are three distinct
  states carried as a type, not coerced.
- Repair tier: lost-thousands-dot regrouping is accepted at reduced confidence and
  flagged `repaired`; wrong digits are out of scope by design (the financial
  validation stage owns those).
- tr_lower: Python lower()/casefold() corrupt Turkish dotted/dotless i; the 3-line
  translate recipe below is measured correct on this document's labels.
"""
from __future__ import annotations

import re
import unicodedata
from decimal import Decimal

from .models import CellValue, DashValue, EmptyValue, NumberValue

DASH_TOKENS = {"-", "–", "—", "~"}
_TR = str.maketrans("İI", "iı")

RE_INT = re.compile(r"^\d{1,3}(?:\.\d{3})+$|^\d{1,3}$")
RE_DEC = re.compile(r"^\d{1,3}(?:\.\d{3})*,\d+$")
RE_PCT = re.compile(r"^%(\d+(?:,\d+)?)$")
RE_PCT_RANGE = re.compile(r"^%(\d+(?:,\d+)?)-%(\d+(?:,\d+)?)$")
RE_BROKEN_GROUP = re.compile(r"^\d+(?:\.\d{3})+$")
RE_NUMERIC_TOKEN = re.compile(r"^\(?[%\d][\d.,%()\-]*\)?$")


def tr_lower(s: str) -> str:
    # NFC BEFORE the translate: a decomposed İ (I + U+0307) must not map I -> ı
    s = unicodedata.normalize("NFC", s)
    s = unicodedata.normalize("NFC", s.translate(_TR).lower())
    return s.replace("̇", "")


def parse_tr_number(token: str) -> tuple[CellValue, float] | None:
    """Return (cell value, parse confidence) or None when the token is not numeric."""
    t = token.strip()
    if not t:
        return EmptyValue(), 1.0
    if t in DASH_TOKENS:
        return DashValue(raw=t), 1.0

    neg = t.startswith("(") and t.endswith(")")
    core = t[1:-1].strip() if neg else t

    m = RE_PCT_RANGE.match(core)
    if m:
        lo, hi = (Decimal(x.replace(",", ".")) for x in m.groups())
        return NumberValue(raw=t, value=lo, value_high=hi, kind="percent_range"), 1.0
    m = RE_PCT.match(core)
    if m:
        v = Decimal(m.group(1).replace(",", "."))
        return NumberValue(raw=t, value=-v if neg else v, kind="percent"), 1.0
    if RE_DEC.match(core):
        v = Decimal(core.replace(".", "").replace(",", "."))
        return NumberValue(raw=t, value=-v if neg else v, kind="decimal"), 1.0
    if RE_INT.match(core):
        v = Decimal(core.replace(".", ""))
        return NumberValue(raw=t, value=-v if neg else v, kind="int"), 1.0
    if RE_BROKEN_GROUP.match(core):
        v = Decimal(core.replace(".", ""))
        return NumberValue(raw=t, value=-v if neg else v, kind="int", repaired=True), 0.7
    if core.isdigit() and len(core) > 3:
        v = Decimal(core)
        return NumberValue(raw=t, value=-v if neg else v, kind="int", repaired=True), 0.5
    return None


def is_numeric_token(token: str) -> bool:
    return bool(RE_NUMERIC_TOKEN.match(token.strip()))


STOP_SUFFIX = re.compile(r"\(\*+\)")

# OCR corrupts the printed "(%)" unit marker in rate-row labels into (©)/(90)/(0);
# the token carries no label semantics, so label_norm drops it. label_raw keeps
# the raw read, and multi-char alphabetic parentheticals like "(net)" never match.
OCR_UNIT_JUNK = re.compile(r"\s*\((?:[%©®°0-9o]{1,2})\)\s*$")


def clean_label(label: str) -> tuple[str, list[str]]:
    """Strip footnote asterisks from a row label; keep them as metadata."""
    marks = [m.group(1) for m in re.finditer(r"\((\*+)\)", label)]
    return STOP_SUFFIX.sub("", label).strip(" .:"), marks


def norm_label(label: str) -> str:
    l = tr_lower(clean_label(label)[0])
    l = l.lstrip("-").strip()
    l = OCR_UNIT_JUNK.sub("", l).strip()
    return re.sub(r"\s+", " ", l)


def row_role(label: str) -> str:
    """Deterministic role rules, measured 11/11 on movement-table rows."""
    l = tr_lower(label)
    if "açılış bakiyesi" in l:
        return "opening"
    if "kapanış bakiyesi" in l:
        return "closing"
    if "net defter değeri" in l:
        return "closing_equiv"
    if l.strip() == "toplam" or l.startswith("toplam "):
        return "total"
    return "flow"
