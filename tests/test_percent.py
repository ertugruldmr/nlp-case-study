from decimal import Decimal

from ftlink.models import NumberValue
from ftlink.percent import digit_vote
from ftlink.table_structure import RawCell, RawRow, merge_label_rows
from ftlink.validation import check_percent_bounds


def test_digit_vote_exact_and_suffix():
    assert digit_vote("9", "9") == "exact"
    # measured tesseract %-glyph corruptions prepend digits
    assert digit_vote("9", "49") == "suffix"       # %9 -> 49
    assert digit_vote("866", "0866") == "suffix"   # %86,6 -> 086,6
    assert digit_vote("105", "7105") == "suffix"   # %10,5 -> 710,5
    assert digit_vote("9", "3") == "mismatch"
    assert digit_vote("", "3") == "mismatch"


def _row(label, x0, cells=None):
    r = RawRow(label=label, label_x0=x0, y0=0, y1=10)
    if cells:
        r.cells = cells
    return r


def _cell():
    return RawCell(col=0, value=NumberValue(raw="1", value=Decimal(1)),
                   parse_conf=1.0, ocr_conf=0.9, bbox=(0, 0, 1, 1))


def test_wrapped_label_merges_when_next_row_indents():
    frag = _row("Özkaynak Yöntemiyle Değerlenen Yatırımların", 327)
    data = _row("Kar/Zararlarındaki Paylar", 345, {0: _cell()})
    merged = merge_label_rows([frag, data], indent_eps=10)
    assert len(merged) == 1
    assert merged[0].label.startswith("Özkaynak Yöntemiyle")
    assert merged[0].label.endswith("Paylar")


def test_group_header_kept_when_next_row_aligns():
    header = _row("Dönem Karı Dağılımı", 302)
    data = _row("Kontrol Gücü Olmayan Paylar", 301, {0: _cell()})
    merged = merge_label_rows([header, data], indent_eps=10)
    assert len(merged) == 2
    assert merged[0].section is True and merged[0].label == "Dönem Karı Dağılımı"


def test_percent_bounds_flags_glyph_corruption():
    class C:
        def __init__(self, v):
            self.cell_id = "t.r0.c0"
            self.value = v

    ok = C(NumberValue(raw="%86,6", value=Decimal("86.6"), kind="percent"))
    bad = C(NumberValue(raw="486,6", value=Decimal("486.6"), kind="percent"))
    rng = C(NumberValue(raw="%2-%4", value=Decimal(2), value_high=Decimal(4),
                        kind="percent_range"))
    results = check_percent_bounds([ok, bad, rng])
    assert [r.status for r in results] == ["pass", "fail", "pass"]
