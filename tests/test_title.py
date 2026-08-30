"""Title derivation: page-heading block above the table bbox (requirement 1)."""
from ftlink.linking import LinkDecision, apply_llm_acceptance
from ftlink.ocr import PageOcr, Word
from ftlink.table_structure import derive_title

COMPANY = "ÖZAK GAYRİMENKUL YATIRIM ORTAKLIĞI A.Ş. VE BAĞLI ORTAKLIKLARI"


def _line(text: str, y: float, line_no: int, x0: float = 100.0, h: float = 30.0) -> list[Word]:
    words, x = [], x0
    for tok in text.split():
        w = Word(text=tok, x0=x, y0=y, x1=x + 20 * len(tok), y1=y + h, conf=90.0,
                 line_key=(1, 1, line_no))
        words.append(w)
        x = w.x1 + 10
    return words


def _page(lines: list[list[Word]]) -> PageOcr:
    return PageOcr(page=5, width_px=2480, height_px=3300, dpi=300,
                   words=[w for line in lines for w in line])


def test_statement_heading_block_joins_and_company_skipped():
    page = _page([
        _line(COMPANY, 100, 1),
        _line("BAĞIMSIZ DENETİMDEN GEÇMİŞ 31 ARALIK 2012 TARİHLİ", 205, 2),
        _line("KONSOLİDE BİLANÇO", 245, 3),
        _line("(Tüm tutarlar Türk Lirası (TL) olarak gösterilmiştir)", 354, 4),
        _line("Cari Dönem Geçmiş Dönem", 636, 5),
    ])
    assert derive_title(page, table_top=800, company=COMPANY) == \
        "BAĞIMSIZ DENETİMDEN GEÇMİŞ 31 ARALIK 2012 TARİHLİ KONSOLİDE BİLANÇO"


def test_footnote_heading_merges_split_number_and_beats_caps_block():
    number = _line("11.", 469, 3, x0=60.0)
    heading = _line("YATIRIM AMAÇLI GAYRİMENKULLER", 465, 2, x0=140.0)
    page = _page([
        _line("KONSOLİDE FİNANSAL TABLOLARA İLİŞKİN AÇIKLAYICI DİPNOTLAR", 286, 1),
        heading, number,
        _line("Arazi ve", 564, 4),
    ])
    assert derive_title(page, table_top=700, company=COMPANY) == \
        "11. YATIRIM AMAÇLI GAYRİMENKULLER"


def test_prose_fragments_never_become_titles():
    page = _page([
        _line("hesabında muhasebeleştirilmiş olup, alım sonrası yapılan harcamalar", 1648, 1),
        _line("gibidir:", 1682, 2),
    ])
    assert derive_title(page, table_top=1900, company=COMPANY) == ""


def test_lines_below_table_top_ignored():
    page = _page([_line("KONSOLİDE KAPSAMLI GELİR TABLOSU", 900, 1)])
    assert derive_title(page, table_top=800, company=COMPANY) == ""


def test_llm_acceptance_creates_d_only_class():
    d = LinkDecision(summary_row_id="r1", footnote_row_id="r2", period_scope="y2012",
                     relation_type="semantic",
                     approach_scores={"cross_encoder": 0.1},
                     approach_accepts={"cross_encoder": False, "value_rules": False,
                                       "lexical": False},
                     agreement="none")
    apply_llm_acceptance(d, True)
    assert d.agreement == "d_only"
    assert d.approach_accepts["llm_select"] is True
    d2 = LinkDecision(summary_row_id="r1", footnote_row_id="r2", period_scope="y2012",
                      relation_type="semantic", approach_accepts={"value_rules": True},
                      agreement="b_only")
    apply_llm_acceptance(d2, True)
    assert d2.agreement == "b_only"  # fused classes are never overwritten
