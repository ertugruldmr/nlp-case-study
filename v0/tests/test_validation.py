from decimal import Decimal

from ftlink.validation import AssembledRow, check_hierarchy_sums, check_rollforward, check_rowwise_sum


def _row(rid, label, role, indent, vals, states=None, repaired=None):
    states = states or {p: ("number" if v is not None else "dash") for p, v in vals.items()}
    repaired = repaired or {p: False for p in vals}
    return AssembledRow(rid, label, role, indent, vals, states, repaired)


def test_rollforward_pass_and_fail():
    rows = [
        _row("o", "1 Ocak açılış bakiyesi", "opening", 0, {"c": Decimal(100)}),
        _row("f", "Alımlar", "flow", 0, {"c": Decimal(20)}),
        _row("c", "31 Aralık kapanış bakiyesi", "closing", 0, {"c": Decimal(120)}),
    ]
    res = check_rollforward("t", rows, ["c"])
    assert res[0].status == "pass"
    rows[2].values["c"] = Decimal(121)
    assert check_rollforward("t", rows, ["c"])[0].status == "fail"


def test_rollforward_dash_is_no_movement_but_missing_is_not_zero():
    rows = [
        _row("o", "açılış bakiyesi", "opening", 0, {"c": Decimal(100)}),
        _row("f", "Alımlar", "flow", 0, {"c": None}, states={"c": "dash"}),
        _row("c", "kapanış bakiyesi", "closing", 0, {"c": Decimal(100)}),
    ]
    assert check_rollforward("t", rows, ["c"])[0].status == "pass"
    # a numeric flow whose value failed to parse must NOT be treated as zero
    rows[1].states["c"] = "number"
    assert check_rollforward("t", rows, ["c"])[0].status == "not_evaluable"


def test_rowwise_sum():
    rows = [_row("r", "x", "flow", 0,
                 {"a": Decimal(3), "b": Decimal(4), "toplam": Decimal(7)})]
    assert check_rowwise_sum("t", rows, ["a", "b", "toplam"], "toplam")[0].status == "pass"


def test_grand_total_aggregate_hypothesis():
    # C aggregates A+B; the naive same-indent sum double counts, the
    # aggregate-dropping hypothesis must still find the match
    rows = [
        _row("g1", "Kısa", "flow", 0, {"p": Decimal(10)}),
        _row("agg", "Özkaynaklar", "flow", 0, {"p": Decimal(30)}),
        _row("a", "Ana", "flow", 0, {"p": Decimal(20)}),
        _row("b", "Kontrol", "flow", 0, {"p": Decimal(10)}),
        _row("t", "TOPLAM KAYNAKLAR", "total", 0, {"p": Decimal(40)}),
    ]
    res = check_hierarchy_sums("t", rows, ["p"], {})
    grand = [c for c in res if c.check_id == "FIN_GRAND_TOTAL"]
    assert grand and grand[0].status == "pass"


def test_parent_sum_catches_digit_error():
    kids = [_row("k1", "x", "item", 1, {"p": Decimal(60)}),
            _row("k2", "y", "item", 1, {"p": Decimal(41)})]  # true 40, corrupted
    parent = _row("g", "Grup", "item", 0, {"p": Decimal(100)})
    res = check_hierarchy_sums("t", [parent] + kids, ["p"], {"g": kids})
    assert res[0].check_id == "FIN_PARENT_SUM" and res[0].status == "fail"


def test_flow_cascade_catches_sign_flip():
    rows = [
        _row("s", "Satış Gelirleri", "item", 0, {"p": Decimal(100)}),
        _row("m", "Maliyet (-)", "item", 0, {"p": Decimal(-40)}),
        _row("bk", "BRÜT KAR", "item", 0, {"p": Decimal(60)}),
        _row("g", "Gider (-)", "item", 0, {"p": Decimal(-10)}),
        _row("fk", "FAALİYET KARI", "item", 0, {"p": Decimal(50)}),
    ]
    from ftlink.validation import check_flow_cascade, check_sign_legality
    res = check_flow_cascade("t", rows, ["p"], set())
    assert all(c.status == "pass" for c in res) and len(res) == 2
    rows[1].values["p"] = Decimal(40)  # sign flip
    res2 = check_flow_cascade("t", rows, ["p"], set())
    assert any(c.status == "fail" for c in res2)
    sign = check_sign_legality("t", rows, ["p"])
    assert any(c.status == "fail" for c in sign)  # the flipped (-) row is positive


def test_flow_cascade_skips_breakdown_and_pershare():
    rows = [
        _row("dk", "DÖNEM KARI", "item", 0, {"p": Decimal(100)}),
        _row("d1", "Azınlık", "item", 0, {"p": Decimal(30)}),
        _row("d2", "Ana Ortaklık", "item", 0, {"p": Decimal(70)}),
        _row("rt", "", "item", 0, {"p": Decimal(100)}),
        _row("hb", "Hisse başına kazanç", "item", 0, {"p": Decimal("0.058")}),
        _row("ok", "Diğer Kapsamlı Gelir", "item", 0, {"p": Decimal(-20)}),
        _row("tk", "TOPLAM KAPSAMLI GELİR", "item", 0, {"p": Decimal(80)}),
    ]
    from ftlink.validation import check_flow_cascade
    res = check_flow_cascade("t", rows, ["p"], set())
    tk = [c for c in res if "tk" in c.scope]
    assert tk and tk[0].status == "pass"
