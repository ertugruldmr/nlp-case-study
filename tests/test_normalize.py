from decimal import Decimal

from ftlink.normalize import norm_label, parse_tr_number, row_role, tr_lower


def test_int_grouped():
    v, conf = parse_tr_number("373.992.222")
    assert v.state == "number" and v.value == Decimal("373992222") and conf == 1.0


def test_paren_negative():
    v, _ = parse_tr_number("(72.681.523)")
    assert v.value == Decimal("-72681523")


def test_comma_decimal():
    v, _ = parse_tr_number("0,058")
    assert v.kind == "decimal" and v.value == Decimal("0.058")


def test_percent_and_range():
    v, _ = parse_tr_number("%86,6")
    assert v.kind == "percent" and v.value == Decimal("86.6")
    r, _ = parse_tr_number("%2-%4")
    assert r.kind == "percent_range" and r.value == Decimal("2") and r.value_high == Decimal("4")


def test_three_states_distinct():
    dash, _ = parse_tr_number("-")
    empty, _ = parse_tr_number("")
    zero, _ = parse_tr_number("0")
    assert dash.state == "dash" and empty.state == "empty" and zero.state == "number"
    assert zero.value == 0


def test_repair_lost_dot_low_confidence():
    v, conf = parse_tr_number("196262.178")
    assert v.state == "number" and v.value == Decimal("196262178")
    assert v.repaired and conf < 1.0


def test_tr_lower_dotted_i():
    assert tr_lower("İLİŞKİN") == "ilişkin"
    assert tr_lower("YATIRIM") == "yatırım"


def test_roles():
    assert row_role("1 Ocak 2012 itibari ile açılış bakiyesi") == "opening"
    assert row_role("31 Aralık 2012 itibari ile kapanış bakiyesi") == "closing"
    assert row_role("31 Aralık 2012 itibari ile net defter değeri") == "closing_equiv"
    assert row_role("Toplam") == "total"
    assert row_role("Alımlar") == "flow"


def test_norm_label_strips_ocr_unit_junk():
    # the printed "(%)" unit marker, OCR-corrupted three different ways on p54
    assert norm_label("İskonto oranı (©)") == "iskonto oranı"
    assert norm_label("Doluluk oranı (90)(*)") == "doluluk oranı"
    assert norm_label("Kira artış oranı (0)") == "kira artış oranı"
    # alphabetic parentheticals are content, not unit junk
    assert norm_label("Karşılıklar (net)") == "karşılıklar (net)"
