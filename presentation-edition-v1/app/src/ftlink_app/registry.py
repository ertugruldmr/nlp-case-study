"""Scenario registry: every alternative is a CONFIG diff over the shipped default.

The point this app demonstrates at the defense: the pipeline's alternatives are
not slideware, they are switchable configurations of the submitted system. Each
scenario carries the defense story it exists to tell.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class Scenario(BaseModel):
    id: str
    title: str
    title_tr: str
    story: str
    story_tr: str
    overrides: dict[str, Any]
    group: str  # baseline | linking | extraction | confidence | generality | llm
    precompute: bool = True
    requires_endpoint: bool = False
    eval_applicable: bool = True  # gold covers summary pages + footnote 11 only


SCENARIOS: list[Scenario] = [
    Scenario(
        id="baseline",
        title="Shipped configuration",
        title_tr="Teslim edilen konfigürasyon",
        story=("The submitted system exactly as graded: footnote 11, all channels, "
               "engine swap on rate rows, fitted calibration. Every other scenario "
               "is a config diff against this one."),
        story_tr=("Teslim edilen sistem: dipnot 11, tüm kanallar, oran satırlarında "
                  "motor değişimi, fitted kalibrasyon. Diğer tüm senaryolar bu "
                  "konfigürasyonun üzerine birer fark olarak tanımlıdır."),
        overrides={},
        group="baseline",
    ),
    Scenario(
        id="strict-linker",
        title="Strict acceptance (threshold 0.8)",
        title_tr="Sıkı kabul eşiği (0.8)",
        story=("Expected-cost framing: when a missed link is cheap and review is "
               "expensive, raise the bar. Shows which relations survive a 0.8 "
               "threshold and how recall pays for precision."),
        story_tr=("Beklenen maliyet çerçevesi: kaçırılan ilişki ucuz, inceleme "
                  "pahalıysa eşik yükselir. 0.8 eşiğinde hangi ilişkilerin ayakta "
                  "kaldığını ve geri çağırmanın bedelini gösterir."),
        overrides={"linking": {"accept_threshold": 0.8}},
        group="linking",
    ),
    Scenario(
        id="lenient-linker",
        title="Lenient acceptance (threshold 0.2)",
        title_tr="Gevşek kabul eşiği (0.2)",
        story=("The opposite regime: accept early, let validation and calibration "
               "flag the doubtful. Measures whether precision actually degrades on "
               "this document or the guards hold."),
        story_tr=("Ters rejim: erken kabul et, şüpheliyi doğrulama ve kalibrasyon "
                  "işaretlesin. Bu dokümanda kesinliğin gerçekten düşüp düşmediğini "
                  "ölçer."),
        overrides={"linking": {"accept_threshold": 0.2}},
        group="linking",
    ),
    Scenario(
        id="no-percent-rescue",
        title="Percent rescue OFF (single-engine OCR)",
        title_tr="Yüzde kurtarma KAPALI (tek motor OCR)",
        story=("Ablation of the engine swap: tesseract reads % glyphs 0/6 on this "
               "scan class while RapidOCR reads 6/6. Turning the rescue off shows "
               "exactly what the second engine buys on the rate table."),
        story_tr=("Motor değişimi ablasyonu: bu tarama sınıfında tesseract % "
                  "glifini 0/6, RapidOCR 6/6 okur. Kurtarmayı kapatmak ikinci "
                  "motorun oran tablosunda tam olarak ne kazandırdığını gösterir."),
        overrides={"ocr": {"percent_rescue": False}},
        group="extraction",
    ),
    Scenario(
        id="psm-6",
        title="OCR segmentation psm 6",
        title_tr="OCR bölütleme psm 6",
        story=("Tesseract page-segmentation ablation, measured result: psm 6 "
               "(uniform block) corrupts the TOC and heading reads badly enough "
               "that footnote location fails BOTH paths and the run aborts "
               "loudly (RuntimeError) instead of shipping garbage. The locked "
               "psm 4 is not a preference, it is load-bearing."),
        story_tr=("Tesseract sayfa bölütleme ablasyonu, ölçülen sonuç: psm 6 "
                  "(tek blok) İçindekiler ve başlık okumalarını o kadar bozar ki "
                  "dipnot konumlama İKİ yoldan da başarısız olur ve çalıştırma "
                  "çöp üretmek yerine gürültülü biçimde durur (RuntimeError). "
                  "Kilitlenen psm 4 bir tercih değil, taşıyıcı bir seçimdir."),
        overrides={"ocr": {"psm": 6}},
        group="extraction",
    ),
    Scenario(
        id="dense-swap",
        title="Dense channel swapped (paraphrase-MiniLM)",
        title_tr="Yoğun kanal değişimi (paraphrase-MiniLM)",
        story=("Model-choice evidence for the dense candidate channel: e5-small "
               "replaced by paraphrase-multilingual-MiniLM-L12-v2 (same 118M "
               "class) via config alone. Measures whether the linking outcome "
               "depends on the specific embedder or on the channel design."),
        story_tr=("Yoğun aday kanalı için model seçimi kanıtı: e5-small, yalnız "
                  "konfigürasyonla paraphrase-multilingual-MiniLM-L12-v2 (aynı "
                  "118M sınıfı) ile değiştirilir. Bağlama sonucunun belirli "
                  "gömücüye mi yoksa kanal tasarımına mı bağlı olduğunu ölçer."),
        overrides={"candidates": {
            "dense_model": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
            "dense_model_revision": "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"}},
        group="linking",
    ),
    Scenario(
        id="reranker-tr-modernbert",
        title="Cross-encoder swapped (ModernBERT-TR reranker)",
        title_tr="Çapraz kodlayıcı değişimi (ModernBERT-TR reranker)",
        story=("Model-choice evidence for approach A: the multilingual "
               "mmarco-mMiniLMv2 (118M, no Turkish in mMARCO) replaced by "
               "ytu-ce-cosmos/modernbert-tr-reranker (149M, Apache-2.0; its card "
               "states distillation from Qwen3-Reranker-8B on Turkish retrieval "
               "data) via the two config keys, revision pinned. Measured result: "
               "cells unchanged (99.0%), all 7 gold links kept (R 1.00) but 10 "
               "semantic false positives appear (P 0.41), every one flagged, and "
               "calibration falls back (negatives 22 to 0). The cause is the score "
               "scale, not the model: this model's config carries no "
               "sentence-transformers activation key, so CrossEncoder applies "
               "Sigmoid and the linker's own sigmoid compresses every pair into "
               "0.51 to 0.73, above the 0.5 accept bar (mmarco's config declares "
               "Identity). On the fixed 33 controls the Turkish reranker separates "
               "labels-only pairs far better (AUC 0.71 vs 0.45; label+values 0.99 "
               "vs 0.95) with no LOO Brier loss on the replayed fused map (0.0076 "
               "vs 0.0085); with the activation pinned to Identity it links 8 (7 "
               "gold + 1 flagged) at P 0.88. Swap-by-config is real, but the accept "
               "threshold's sigmoid scale is a per-model contract."),
        story_tr=("A yaklaşımı için model seçimi kanıtı: çok dilli mmarco-mMiniLMv2 "
                  "(118M, mMARCO'da Türkçe yok), iki konfigürasyon anahtarıyla ve "
                  "sabit revizyonla ytu-ce-cosmos/modernbert-tr-reranker (149M, "
                  "Apache-2.0; kartı Türkçe erişim verisi üzerinde "
                  "Qwen3-Reranker-8B'den damıtıldığını yazar) ile değiştirilir. "
                  "Ölçülen sonuç: hücreler aynı (%99.0), 7 altın bağın hepsi "
                  "korunur (R 1.00) ama 10 anlamsal yanlış pozitif çıkar (P 0.41), "
                  "hepsi bayraklı, kalibrasyon fallback'e düşer (negatifler 22'den "
                  "0'a). Neden model değil ölçek: bu modelin config'inde "
                  "sentence-transformers aktivasyon anahtarı yok, CrossEncoder "
                  "Sigmoid uygular ve bağlayıcının kendi sigmoidi her çifti "
                  "0.51-0.73 aralığına, yani 0.5 kabul eşiğinin üstüne sıkıştırır "
                  "(mmarco'nun config'i Identity bildirir). Sabit 33 kontrolde "
                  "Türkçe yeniden sıralayıcı yalnız-etiket çiftlerini çok daha iyi "
                  "ayırır (AUC 0.71'e karşı 0.45; etiket+değer 0.99'a karşı 0.95) "
                  "ve tekrar oynatılan füzyon haritasında LOO Brier kaybı yoktur "
                  "(0.0076'ya karşı 0.0085); aktivasyon Identity'ye sabitlenince 8 "
                  "bağ (7 altın + 1 bayraklı) P 0.88 ile kurulur. Konfigürasyonla "
                  "değişim gerçektir, ama kabul eşiğinin sigmoid ölçeği model "
                  "başına bir sözleşmedir."),
        overrides={"linking": {
            "cross_encoder_model": "ytu-ce-cosmos/modernbert-tr-reranker",
            "cross_encoder_revision": "d6aabbe061f1bf6cb796e317ecb6d9b8f7b96c54"}},
        group="linking",
    ),
    Scenario(
        id="lenient-lexical",
        title="Lexical baseline bar lowered (0.4)",
        title_tr="Sözlüksel taban çizgisi eşiği 0.4",
        story=("The insufficiency claim stress-tested: approach C accepts "
               "nothing at 0.75 on this document. Lowering the bar to 0.4 "
               "measures whether word-level matching starts contributing links "
               "or starts admitting garbage."),
        story_tr=("Yetersizlik iddiasının stres testi: C yaklaşımı bu dokümanda "
                  "0.75'te hiçbir şey kabul etmez. Eşiği 0.4'e indirmek, kelime "
                  "düzeyi eşleştirmenin bağlantı üretmeye mi yoksa çöp kabul "
                  "etmeye mi başladığını ölçer."),
        overrides={"linking": {"lexical_threshold": 0.4}},
        group="linking",
    ),
    Scenario(
        id="footnote-10",
        title="Footnote 10 (second generality proof)",
        title_tr="Dipnot 10 (ikinci genellik kanıtı)",
        story=("Third footnote target, zero code changes, measured honestly: "
               "locate finds note 10, tables extract, REL_COVERAGE passes, but "
               "the Stoklar linking physics is harder (no exact value anchor), "
               "so both produced links ship FLAGGED under fallback calibration. "
               "Generality of the machinery, with the degradation visible."),
        story_tr=("Üçüncü dipnot hedefi, sıfır kod değişikliği, dürüst ölçüm: "
                  "konumlama not 10'u bulur, tablolar çıkar, REL_COVERAGE geçer; "
                  "ancak Stoklar bağlama fiziği daha zordur (tam değer çapası "
                  "yok), bu yüzden üretilen iki bağlantı da fallback kalibrasyon "
                  "altında BAYRAKLI çıkar. Mekanizmanın genelliği, bozulma "
                  "görünür halde."),
        overrides={"document": {"footnote_no": 10}},
        group="generality",
        eval_applicable=False,
    ),
    Scenario(
        id="dpi-400",
        title="OCR at 400 dpi",
        title_tr="OCR 400 dpi",
        story=("The counter-intuitive resolution result: on this scan class 400 "
               "dpi DEGRADES digit fidelity versus the locked 300 dpi (measured "
               "in the OCR grid before the seal). Re-runnable proof that the dpi "
               "choice is evidence, not habit."),
        story_tr=("Sezgiye aykırı çözünürlük sonucu: bu tarama sınıfında 400 dpi, "
                  "kilitlenen 300 dpi'a göre rakam sadakatini DÜŞÜRÜR (mühürden "
                  "önce OCR ızgarasında ölçüldü). Dpi seçiminin alışkanlık değil "
                  "kanıt olduğunun tekrar çalıştırılabilir ispatı."),
        overrides={"ocr": {"dpi": 400}},
        group="extraction",
    ),
    Scenario(
        id="narrow-candidates",
        title="Narrow candidate beam (top_k 2)",
        title_tr="Dar aday havuzu (top_k 2)",
        story=("Beam stress test with a measured surprise: the accept set "
               "survives top_k 2 unchanged (anchor-union + rank-1 carry), but "
               "the narrow beam starves the calibrator's NEGATIVE pool (22 to "
               "2), so calibration falls back and every relation ships flagged. "
               "Beam width is a calibration resource, not just a recall knob."),
        story_tr=("Işın stres testi ve ölçülen sürpriz: kabul kümesi top_k 2'de "
                  "aynen ayakta kalır (çapa-birleşim + ilk sıra kabulü), ama dar "
                  "ışın kalibratörün NEGATİF havuzunu kurutur (22'den 2'ye); "
                  "kalibrasyon fallback'e düşer ve her ilişki bayraklı çıkar. "
                  "Işın genişliği yalnız geri çağırma değil, bir kalibrasyon "
                  "kaynağıdır."),
        overrides={"candidates": {"top_k": 2}},
        group="linking",
    ),
    Scenario(
        id="rrf-k60",
        title="RRF k=60 (literature default)",
        title_tr="RRF k=60 (literatür varsayılanı)",
        story=("The RRF paper's k=60 versus our k=10: at 19 candidates per item "
               "the rank tail is meaningless, so k should not matter. This run "
               "makes that a measurement instead of an argument."),
        story_tr=("RRF makalesinin k=60 değeri bizim k=10'a karşı: kalem başına "
                  "19 adayda sıralama kuyruğu anlamsızdır, k fark etmemeli. Bu "
                  "çalıştırma bunu argüman olmaktan çıkarıp ölçüm yapar."),
        overrides={"candidates": {"rrf_k": 60}},
        group="linking",
    ),
    Scenario(
        id="no-second-engine",
        title="Digit cross-check OFF",
        title_tr="Rakam çapraz kontrolü KAPALI",
        story=("Ablation of the dual-engine digit verification: the 77.543.097 "
               "corruption loses one of its two independent catchers; the "
               "financial checks remain as the second line of defense."),
        story_tr=("Çift motorlu rakam doğrulama ablasyonu: 77.543.097 bozulması "
                  "iki bağımsız yakalayıcısından birini kaybeder; finansal "
                  "kontroller ikinci savunma hattı olarak kalır."),
        overrides={"confidence": {"second_engine": False}},
        group="confidence",
    ),
    Scenario(
        id="no-anchor-channel",
        title="Value-anchor channel OFF",
        title_tr="Değer çapası kanalı KAPALI",
        story=("Candidate-generation ablation: zeroing the value-anchor weight "
               "tests whether reconciliation links survive on text channels alone. "
               "Weight-sensitivity was measured stable at the seal; this makes the "
               "claim reproducible live."),
        story_tr=("Aday üretimi ablasyonu: değer çapası ağırlığını sıfırlamak, "
                  "mutabakat ilişkilerinin yalnız metin kanallarıyla yaşayıp "
                  "yaşamadığını test eder. Ağırlık duyarlılığı mühürde stabil "
                  "ölçülmüştü; bu senaryo iddiayı canlı tekrarlanabilir yapar."),
        overrides={"candidates": {"anchor_weight": 0.0}},
        group="linking",
    ),
    Scenario(
        id="fallback-calibration",
        title="Calibration controls removed",
        title_tr="Kalibrasyon kontrolleri kaldırıldı",
        story=("Removes the cash-flow control pages: positives drop 11 to 7. "
               "Measured result: the smoothed fit still holds (an unsmoothed "
               "earlier build fell back entirely at this N), but every "
               "confidence moves by up to 0.02 and the stability disclosures "
               "lose backing. Shows WHY the extra controls were added."),
        story_tr=("Nakit akış kontrol sayfalarını kaldırır: pozitifler 11'den "
                  "7'ye düşer. Ölçülen sonuç: yumuşatılmış uyum hâlâ ayakta "
                  "(yumuşatmasız eski sürüm bu N'de tamamen fallback'e düşerdi), "
                  "ama her güven 0.02'ye kadar oynar ve stabilite beyanları "
                  "dayanağını kaybeder. Ek kontrollerin NEDEN eklendiğini "
                  "gösterir."),
        overrides={"confidence": {"extra_control_pages": []}},
        group="confidence",
    ),
    Scenario(
        id="footnote-12",
        title="Footnote 12 (config generality)",
        title_tr="Dipnot 12 (konfigürasyon genelliği)",
        story=("Same pipeline, different target footnote, zero code changes: "
               "locates rotated landscape pages, extracts rougher tables, and "
               "flags its own degradation. Requirement 4 demonstrated live."),
        story_tr=("Aynı boru hattı, farklı hedef dipnot, sıfır kod değişikliği: "
                  "döndürülmüş yatay sayfaları bulur, daha kaba tabloları çıkarır "
                  "ve kendi bozulmasını bayraklar. Gereksinim 4'ün canlı gösterimi."),
        overrides={"document": {"footnote_no": 12}},
        group="generality",
        eval_applicable=False,
    ),
    Scenario(
        id="footnote-13",
        title="Footnote 13 (fourth generality proof)",
        title_tr="Dipnot 13 (dördüncü genellik kanıtı)",
        story=("Fourth footnote family, zero code changes, and the mirror image "
               "of footnote 10: here the value anchor CAN fire. The summary row "
               "Maddi Olmayan Duran Varlıklar links to the note's closing net "
               "book value row on an exact 14.526.075 match with reconciliation "
               "1.0, while the cross-encoder scores it 0.135 (zero lexical "
               "overlap): rules carry what the text model cannot see. The "
               "note starts mid-page 57 under note 12's tables and page-level "
               "scoping keys on the page's top heading, so page 57 goes to note "
               "12 and the note is located from page 58: the 2012 side is absent "
               "by that scoping limit (README 8), note 14's table on page 58 "
               "enters the pool, and the produced link ships FLAGGED under "
               "fallback calibration."),
        story_tr=("Dördüncü dipnot ailesi, sıfır kod değişikliği ve dipnot 10'un "
                  "ayna görüntüsü: burada değer çapası ATEŞLENEBİLİYOR. Özet "
                  "satırı Maddi Olmayan Duran Varlıklar, notun kapanış net defter "
                  "değeri satırına tam 14.526.075 eşleşmesi ve 1.0 mutabakatla "
                  "bağlanırken çapraz kodlayıcı 0.135 veriyor (sözcük kesişimi "
                  "sıfır): kurallar metin modelinin göremediğini taşır. Not 13, "
                  "sayfa 57'de not 12'nin tablolarının altında başlar; sayfa "
                  "düzeyi kapsam sayfanın üst başlığına bakar, bu yüzden sayfa 57 "
                  "not 12'ye gider ve not 58'den itibaren bulunur: 2012 tarafı bu "
                  "kapsam sınırı yüzünden yok (README 8), not 14'ün tablosu havuza "
                  "girer ve üretilen bağ fallback kalibrasyonla BAYRAKLI sevk edilir."),
        overrides={"document": {"footnote_no": 13}},
        group="generality",
        eval_applicable=False,
    ),
    Scenario(
        id="llm-tier",
        title="LLM linker tier (approach D)",
        title_tr="LLM bağlayıcı katmanı (yaklaşım D)",
        story=("The configured fourth approach: select-formulation LLM linking "
               "against an OpenAI-compatible endpoint with a committed response "
               "cache for offline byte-identical replay. Needs a running endpoint; "
               "disabled in the graded submission to keep the grader's setup "
               "friction-free."),
        story_tr=("Konfigüre edilmiş dördüncü yaklaşım: OpenAI uyumlu bir uca "
                  "karşı select formülasyonlu LLM bağlama, çevrimdışı bayt-özdeş "
                  "tekrar için kayıtlı yanıt önbelleğiyle. Çalışan bir uç ister; "
                  "notlandırma sürtünmesini sıfırlamak için teslimde kapalıdır."),
        overrides={"linking": {"llm": {"enabled": True}}},
        group="llm",
        precompute=False,
        requires_endpoint=True,
    ),
]

BY_ID: dict[str, Scenario] = {s.id: s for s in SCENARIOS}


def get(scenario_id: str) -> Scenario:
    if scenario_id not in BY_ID:
        raise KeyError(f"unknown scenario: {scenario_id}")
    return BY_ID[scenario_id]
