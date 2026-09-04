---
slug: decision-matrix
created: 2026-08-16T00:00:00+03:00
verified: 2026-08-29T01:30:00+03:00
status: fresh
sources:
  - "[[01-master-plan]] and all sweep-#1 notes"
  - evidence/tesseract-ocr.md
---

# Decision matrix — YKT case solutions

> Presentation asset for the defense (refreshed 29.08.2026 to ftlink 1.0.2; the demo app renders it live under "Karar matrisi" from `app/frontend/decision_matrix.json`). Legend: ✅ = measured on THIS document (evidence/ note),
> ◐ = sourced claim (sweep note, URL), ? = pending [E#] test. Populate ?-cells only from
> evidence notes — never from README claims.

## Axes
| Axis | Meaning / how measured |
|---|---|
| accuracy | vs gold set (cell_acc / GriTS-Content / gold-pair rank) — evidence/ only |
| cost | $ per document run |
| open-source | license (bank-viability gate: Apache-2.0/MIT ship; NC/OpenRAIL excluded) |
| on-device | CPU-only laptop, offline |
| frontier-API | hosted model needed? |
| latency | wall-clock per doc |
| ops burden | install weight, re-runnability risk |
| diverges where | which cases this option wins/loses (req. 10) |


**S0 configuration, measured 30.08 (E68).** The page range is the binding constraint on recall, not the
linking: `summary_pages [5, 7] -> [5, 10]`, one line and no code, gives 11 relations instead of 7 (four new
cash-flow links at 0.9252 to 0.9994, three by consensus, none flagged), preserves all 7 originals, and grows
the calibration control set from 11/22 to 15/34 with the jackknife improving to 0.0338. Inside the shipped
range the reference set is provably complete (9 value coincidences, exactly 7 row pairs, all emitted).
Evidence: [[scope-widening]].

## Stage: OCR (S1)
| Solution | accuracy | cost | license | on-device | latency | ops | diverges where | evidence |
|---|---|---|---|---|---|---|---|---|
| tesseract 5 tur TSV (PRIMARY) — **config LOCKED 300dpi/psm4 (E2)** | ✅ 154/156 values verbatim @300dpi (400dpi WORSE: 149; lab scenario dpi-400: 79.6% cells, recall 0.14, E33); **% glyph 0/6 at every dpi/psm (E28)**; **GPU bake-off confirmed 30.08 (run-08, E54): no alternative of 15 tested engines beats the shipped 199/201 (best single alternative 185-190/201: docTR, RapidOCR variants, EasyOCR, all trading percent recall for worse digit/label fidelity); 2 GPU 7B VLMs (Qwen2.5-VL, olmOCR-2) underperform even at loose page-level recall; PaddleOCR failed to install (env, not measured)** | 0 | Apache-2.0 | yes | 0.6–0.7s/p ✅ | brew/apt trivial | fails: %-glyphs, reading-order splits, TOC numbers | [[tesseract-ocr]] [[percent-rescue]] [[ocr-bakeoff-run08]] |
| RapidOCR digit cross-check (VERIFIER) | ✅ E3/E4 shipped (v0 measurement: 176 checked, 2 disagreements); **1.0.2 run: FMT_ENGINE_AGREEMENT counts 176 crops checked, 175 agree, 1 disagree (Stoklar, the real corruption, capped at 0.4); separately 5 cells carry engine_agreement < 1.0, that one plus the four p54 percent cells the S3b swap re-read. Both numbers are correct and measure different things (check-level disagreements vs cells whose confidence the agreement signal touched)**| Apache-2.0 | yes (onnx) | ~0.1s/cell ✅ | pip-only (now base dep) | digit disagreement flags; separator-class passes BY NATURE (parent-sum catches) | [[deliverable-v0]] |
| **RapidOCR percent PRIMARY on rate rows (S3b, SHIPPED)** | ✅ 6/6 rate cells verbatim vs tesseract 0/6; T3 1/6→6/6 exact | 0 | Apache-2.0 | yes (onnx) | ~0.2s/cell ✅ | none (base dep) | engines swap per glyph class; tesseract demoted to suffix-vote verifier | [[percent-rescue]] |
| PaddleOCR full (REJECTED primary) | ◐ no TR diacritics (maintainer, #16482) | 0 | Apache-2.0 | yes | ? | macOS ARM risk | labels corrupt; digits OK | [[10-ocr-engines]] |
| Apple Vision (REJECTED) | ✅ no `tr` in supported langs on this machine | 0 | — | mac-only | — | breaks re-run | — | [[10-ocr-engines]] |
| surya (REJECTED) | ◐ | 0 | OpenRAIL-M rev-cap — bank-hostile | heavy | — | vllm dep | — | [[10-ocr-engines]] |

## Stage: table structure (S3)
| Solution | accuracy | cost | license | on-device | latency | ops | diverges where | evidence |
|---|---|---|---|---|---|---|---|---|
| TATR v1.1-fin + word boxes (upgrade candidate; planned config-gated behind extract_tables(), no engine key yet) | **ADR-01 RESOLVED 30.08 against TATR (run-06, GPU, supersedes the local-only E69 finding)**: scored on the same 201 gold value cells the shipped scorer uses (methodology caveat: run-06's scorer is a GriTS-alignment + normalized-string-match scorer, not identical to `eval/score.py`'s row-label + numeric-value scorer — same question, different algorithm, see [[structure-bakeoff-run06]]), TATR's best config (det>=0.3+NMS) reaches **151/201 (75.1%)**, page 54 never detected at any threshold. Where it detects at all, structure quality sits at or near the printed-table ceiling (page 5: 0.8308 vs ceiling 0.831; 86-94% of ceiling elsewhere) — **the weakness is detection configuration, not structural quality once detected.** Threshold cliff confirmed sharply: page 7 goes 0.7611 (det>=0.3) to 0.0 (det>=0.5); page 53 goes 0.7948/0.3947/0.0 across 0.3/0.5/0.7 — a single hyperparameter moves it between usable and nothing. At TATR's own canonical 1600px setup, run-06 detects only 1 of 5 pages at threshold 0.7 (page 6), agreeing with [[tatr-local-structure]] E50; a native-resolution local check found 3 of 5, confirming the detector is scale-sensitive (native resolution is the outlier figure, not the reference). Out of domain regardless: trained on **FinTabNet.c** (error-corrected FinTabNet, arXiv:2303.00716), born-digital, vs a 300dpi Turkish scan. **Verdict: shipped x-clustering (99.0%) is KEPT over TATR (75.1%), no code change.** | 0 | MIT | yes, 28.8M | ? | torch-cpu | trained on **FinTabNet.c** (error-corrected FinTabNet, arXiv:2303.00716) = this distribution | resolved (GPU head-to-head, vs x-clustering), [[structure-bakeoff-run06]] |
| **x-clustering on numeric-token right edges (SHIPPED PRIMARY)** | ✅ 99.0% exact cells (199/201), 7/7 real titles via derive_title, indent rule for wrapped labels vs group headers | 0 | own code | yes | fast | none; deterministic | right-aligned cols: cluster x1 not x0; header text has no check (p53.t04 junk header, README 8) | [[deliverable-v0]] [[percent-rescue]] [[mock03-hardening]] |
| docling TableFormer (BASELINE) | **Measured 30.08 (run-06, GPU/CPU): 165/201 exact cells (82.1%), untuned** (same 201-cell comparison as TATR above, same methodology caveat applies), 25.1s total over 5 pages via `TesseractCliOcrOptions(tur)`. Genuinely strong, not failing: reaches the gold ceiling class on pages 5 (35/36) and stays close on 6/7, weakest page 54 still 62.5% (10/16). Falls short of shipped x-clustering (99.0%) but is the best CPU-viable challenger measured. Run-01's earlier E7 crash (missing `tesserocr` Python bindings, fix verified E69) is now moot — docling ran clean in run-06 via the same `TesseractCliOcrOptions` swap. **Verdict: shipped x-clustering (99.0%) is KEPT over docling (82.1%), no code change.** | 0 | MIT | yes | 5.1s/page L4 measured (run-06); 400 ms/table L4, 1.74 s x86 per AAAI'25 card, research/105; pin v1, v2 regressions #3158/#3553 | one pip install | scan robustness now measured, not unknown: 82.1% on this scan class | resolved (GPU head-to-head, vs x-clustering), [[structure-bakeoff-run06]] |
| Qwen2.5-VL-7B-Instruct to HTML (NEW ROW, run-06) | **Measured 30.08: 187/201 exact cells (93.0%), best off-the-shelf challenger measured**, bf16, 23.7 GB GPU peak, 406.9s total (73-124s/page). Genuinely strong: clean sweeps on pages 53 (33/33) and 54 (16/16), 52/58 on page 7, 56/58 on page 6, 30/36 on page 5. Falls 12 cells short of shipped x-clustering while needing a 7B-parameter GPU model at ~2 min/page — a real accuracy/cost tradeoff, not a failure. **Verdict: shipped x-clustering (99.0%, CPU) is KEPT over the VLM (93.0%, GPU), no code change.** | 0 | Apache-2.0 (Qwen2.5) | yes, 7B | 73-124 s/page L4, bf16 (4-bit nf4 on <20GB GPUs) | prompt to HTML + grid parser | strongest challenger, still short and far more expensive | resolved (GPU head-to-head, vs x-clustering), [[structure-bakeoff-run06]] |
| PaddleOCR PP-StructureV3 | **Not run (run-06): `status: failed`, "no result from runner" on all 5 pages, no traceback captured.** Reported as "not run (reason)" per the fold-in plan's rule, never as "worse." | 0 | Apache-2.0 | yes | unknown, never executed | isolated venv install | runner-script failure, cause not diagnosed | not run, [[structure-bakeoff-run06]] |
| VLM per-page, cached (API TIER) | ? E8 | <$0.01/p ◐ | — | no | ? | cache→offline replay | ~95–99% run-identity w/o cache ◐ | pending |
| camelot/pdfplumber/tabula/gmft (NEGATIVE) | ✅ no text layer to read | — | — | — | — | — | resurrect only via ocrmypdf layer | [[05-document-recon]] |
| PP-StructureV3 (REJECTED) | — | 0 | Apache-2.0 | ◐ segfaults macOS ARM (official tracker) | — | high | — | [[15-table-structure]] |
| RapidTable unitable / slanet_plus (onnx CPU; consumes our word boxes) | ? E52 (Colab run-06 structure bake-off) | 0 | Apache-2.0 | yes | ms-s/table | one pip | trained on EN/ZH; wireless 78.4 TEDS (v1.0); research/105 | pending |
| VLM table-to-HTML, LOCAL open weights (dots.ocr MIT 3B; Qwen3-VL / olmOCR-2 Apache) | ? E52 (run-06 Qwen2.5-VL row) | 0 (GPU) | MIT / Apache | GPU 16-24 GB | s/page | heavy | no dash/empty/zero, no footnote-ref column, no indent depth: still needs the post-rules layer; OmniDocBench v1.6 TEDS 87-95 (research/105); Nanonets = Qwen research licence (NC), Marker weights OpenRAIL-M | pending |

## Stage: candidate generation (S6) — E10/E10b MEASURED 16.08
Two measured link TYPES: (a) reconciliation (bilanço↔opening/closing/total rows — labels are
dates/roles, no item semantics) and (b) item-semantic (gelir↔named movement rows).
| Solution | accuracy (vs gold, N=19) | cost | license | on-device | latency | ops | diverges where | evidence |
|---|---|---|---|---|---|---|---|---|
| **value-anchor channel** | ✅ R@5 **1.00 / 1.00** (both types — load-bearing) | 0 | own | yes | ms | stop-value guard needed | false-anchors on collisions (423.580.000 ×3 rows, seen) | [[candidate-channels]] |
| char_wb 2-4 TF-IDF | ✅ type-(b) 1.00; type-(a) 0.00 | 0 | BSD | yes | ms | sklearn only | "değer" n-grams carry the near-zero-word-overlap pair | [[candidate-channels]] |
| multilingual-e5-small qq | ✅ type-(b) 1.00; type-(a) **below random** [14–19] | 0 | MIT | yes ~118M | 0.27s/21 enc ✅ | ST | semantic channel ONLY; never alone | [[candidate-channels]] |
| Qwen3-Embedding-0.6B (challenger to e5-small) | ? E53 (run-07 bi-encoder row) | 0 | Apache-2.0 | yes 1.2 GB fp16 | ms GPU | sentence-transformers | only challenger row worth a matrix line (research/107); bge-m3 and gte stay fallbacks | pending |
| global assignment (Hungarian / optimal transport) over the candidate matrix | ✅ FALSIFIED 29.08 (research/113, verified): the 7 reference relations come from only 2 distinct summary rows (5 and 2), so a one-to-one assignment caps recall at 2 of 7 = 0.29; a many-to-one cap adds nothing the RRF ranking does not already give | 0 | scipy (already locked) | yes | ms | small | measured against this document's own link structure | research/113 |
| arithmetic-implied values as anchor keys (research/113 item 1) | ✅ REFUTED 30.08 (E62): the arithmetic holds (five components sum to 77.543.097) but the exact anchor ALREADY emits that pair (rel006, confidence 0.6694, flagged); implied keys add 0 true and 1 false pair over 49 in-scope pairs, and at the two cheapest levels they cannot even compute the implied total because the total row was mis-roled by the same OCR failure they target | 0 | own code | yes | ms | small | measured, not argued | [[f5-and-arithmetic-anchors]] |
| document-level numeric equality sweep (candidate channel C, research/109) | ? E65 | 0 | own code | yes | ms | small | Pang et al. auditor-report cross-checker pattern; overlaps the value-anchor channel, adds cross-page reach | pending |
| rapidfuzz token_set | ✅ (a) 0.60 / (b) 1.00 @R@5 | 0 | MIT | yes | ms | tiny | best bare-label generalist, still misses (a) tails | [[candidate-channels]] |
| bm25s lucene+stem (DIVERGENCE BASELINE) | ✅ (a) 0.40 / (b) 0.50 | 0 | MIT | yes | ms | tiny | stem "değerle"≠"değer" miss measured. **CONFOUND flagged 29.08 (research/113) and then MEASURED (E61, 30.08): at constant candidate generation and constant scorer, snowball TIES the shipped tokenisation at 0 of 7, so "stemming loses" was never the finding; the specific over-stemming miss is real, the general conclusion was an artefact of comparing two different scoring functions.** F5 truncation does lift type (b) R@5 from 0.00 to 1.00 with zero regressions, but it is REDUNDANT: the shipped char_wb(2,4) channel already reaches type (b) R@5 1.00 at rank 2 on the same pairs. Cut point is load-bearing (5 works, 6 does not). Keep F5 as a config-gated normaliser for a word-level BM25 channel on OTHER documents, not for accuracy here | [[f5-and-arithmetic-anchors]], research/113 |
| weighted RRF (tfidf+e5+anchor) | ✅ best k=5–10, anchor_w=3: bilanço [1,3,4,7,8], gelir [1,2] | 0 | own | yes | ms | none | = YKT published taste (SAFİR RRF) | [[candidate-channels]] |
| title/context serialization (REJECTED for within-footnote) | ✅ FALSIFIED — title constant across candidates; degrades (b) [1,2]→[9,10] | — | — | — | — | — | keep label-centric after S5 | [[candidate-channels]] |
| jina-embeddings-v3 (EXCLUDED) | — | — | CC-BY-NC — bank-hostile | — | — | trust_remote_code | evaluated-and-excluded story | [[30-candidate-generation]] |

## Stage: normalization (S4) — E9 MEASURED 16.08
| Solution | accuracy | cost | license | on-device | latency | ops | diverges where | evidence |
|---|---|---|---|---|---|---|---|---|
| custom ~90-line Decimal grammar | ✅ 182/182 gold cells exact; 19/19 states; 175/176 OCR values recovered | 0 | stdlib | yes | ms | none | wrong-digit OCR out of scope BY DESIGN (validation's job) | [[tr-number-parser]] |
| repair tier (lost-dot regroup) | ✅ precision 1.00, recall 0.53 | 0 | stdlib | yes | ms | none | last-dot drops unparsed → surface as low-conf flags | [[tr-number-parser]] |
| zeyrek / Zemberek (REJECTED) | ✅ offline-crash / JVM measured | — | — | — | — | re-run traps | rejection reason partly stale (research/113): a pure-Python `zemberek-python` exists, so "JVM dependency" no longer holds; the offline-crash observation for zeyrek stands. Not revisited before the send | [[20-normalization]], research/113 |

## Stage: linking (S7) — the ≥2-approach comparison
| Solution | accuracy | cost | license | on-device | latency | ops | diverges where | evidence |
|---|---|---|---|---|---|---|---|---|
| C1/C2 rapidfuzz baseline | C1 fails zero-overlap pair BY CONSTRUCTION ✅(gold) | 0 | MIT | yes | ms | none | C2 breaks on value collisions | gold; E-pending demo |
| A: bge-reranker-v2-m3 | ✅ R@5 **1.00/1.00** (labels+values); 0.20/1.00 labels-only. **E47 (run-01, GPU): top1_margin 0.506 bilanço / 0.098 gelir — 7x / 5x SMALLER than shipped mmarco, despite tied r@5.** **E72 (run-07, GPU, on the 33 controls): labels-only AUC 0.7438 vs mmarco 0.4504 (+0.2934, clears the pre-registered +0.05 swap bar); fused-map LOO Brier 0.0054 vs mmarco 0.0071 vs shipped-file 0.0085 (lower/better on both). Rule technically fires for a swap on these two candidates, but run-07 only completed 2 of 13 planned candidates (a third crashed with a CUDA device-side assert, the remaining 10 never ran) — NOT treated as a resolved recommendation, filed as a re-run item (DECISIONS).** | 0 | Apache-2.0 | yes 568M CPU | ✅ 11–31ms/pair | ST CrossEncoder | input-construction A/B 0.20→1.00 = README exhibit; partial-coverage swap signal, re-run needed | [[bge-reranker]], [[heavy-evidence-run01]], [[reranker-bakeoff-run07]] |
| A-small: mmarco-mMiniLM (SHIPPED DEFAULT, revision-pinned) | ✅ R@5 1.00/1.00 — PARITY at 1/5 size; **input-construction ablation SHIPPED re-runnable (eval/ablation.py): labels-only 1/7 vs labels+values 7/7, exact McNemar p = 0.031; Turkish absent from mMARCO (zero-shot via XLM-R backbone)**. **E47 (run-01, GPU): top1_margin 3.502 bilanço / 0.482 gelir — matches local CPU reproduction (3.3974/0.4824); LARGEST margin of the 3 rerankers tested, i.e. best separation, not just parity** | 0 | Apache-2.0 | yes ~118M | ✅ 3 ms batched / 8 ms single (README re-timing; first measurement 11 ms) | tiny | rank-saturated on r@5; margins now measured (E47), confirm shipped default; **E72 (run-07): labels-only AUC 0.4504, weakest of the 2 candidates that completed — see bge row above for the partial-coverage caveat before reading this as a loss** | [[small-rerankers]] [[mock-hardening]] [[heavy-evidence-run01]], [[reranker-bakeoff-run07]] |
| A-alt: mxbai-rerank-base-v2 | ✅ R@5 1.00/1.00. **E47 (run-01, GPU): top1_margin 0.016 bilanço / 0.012 gelir — weakest separation of the 3 tested despite tied r@5** | 0 | Apache-2.0 | yes 0.5B | ✅ 54ms/pair | trust_remote_code | margin weakest despite r@5 parity | [[small-rerankers]], [[heavy-evidence-run01]] |
| A-alt2: Qwen3-Reranker-0.6B (Apache-2.0, 596M) | ? E53 (run-07): MMTEB-R 66.36 vs bge-v2-m3 58.36 at equal size (Qwen3 report Table 4, research/107) | 0 | Apache-2.0 | yes 1.2 GB fp16 | s/pair CPU, ms GPU | CrossEncoder path via tomaarsen seq-cls port | base LLM pretraining lists Turkish; reranker fine-tuning data coverage not stated | pending |
| A-alt3: ytu-ce-cosmos/modernbert-tr-reranker (Turkish-trained, 149M) | E57 local: config-only swap 17 relations (10 fp, all flagged, double sigmoid); identity-forced: 8 relations (7 gold + 1 flagged fp), labels-only AUC 0.7149 vs mmarco 0.4504, fused LOO Brier 0.0076 vs 0.0085; E53 (run-07) pending | 0 | Apache-2.0 | yes, CPU-viable | fast | CrossEncoder path | listwise-KL distilled from Qwen3-Reranker-8B on msmarco-tr etc. (card, 30.06.2026); no competitor rows published; 512 max_seq may truncate long label+values pairs | pending |
| jina-reranker-v3 / v3.5 (MEASURE ONLY) | ? E53 | — | CC-BY-NC-4.0 | — | — | — | licence gate for a bank deliverable; own card shows Qwen3-Reranker-4B ahead on MIRACL/RTEB | pending |
| B-local: LLM-select (LM Studio qwen3.6-35b measured; deliverable: Ollama/Llama-3.1-8B per Cetvel) | ✅ P=1.00 both; R=1.00 gelir / 0.20 bilanço (relation-definition, prompt-fixable) | 0 | — | yes | 2–5s/call ✅ | runaway-generation risk (E15b timeout) → max_tokens cap | precision-selector vs CE recall-ranker — measured divergence | [[llm-select-linker]] |
| D tier as SHIPPED: OpenAI-compatible endpoint + committed response cache, `linking.llm.enabled: false` | ✅ cache-replay and unreachable-endpoint paths unit-tested; d_only relations always flagged; never feeds the calibrator | 0 (off) | — | replay offline | s/call when on | grading friction avoided by default-off (DECISIONS 4) | decision-level, outside the fused calibration | README 5 D; [[llm-select-linker]] |
| NLI mDeBERTa (3rd signal) | ❌ E17 (run-01, GPU): target_ranks [4,5,7,11,13] bilanço (2/5 in top5), [16,19] gelir (0/2 in top5) — NOT competitive, easy query fails outright | 0 | MIT | yes 279M | fast | HF | entailment framing does not transfer here | NOT ADOPTED, [[heavy-evidence-run01]] |
| jina-reranker-v2 (EXCLUDED) | — | — | CC-BY-NC | — | — | — | license gate exhibit | [[40-linking-models]] |

## Stage: confidence calibration (S8)
| Solution | accuracy | cost | license | on-device | latency | ops | diverges where | evidence |
|---|---|---|---|---|---|---|---|---|
| hand-weighted fusion → Platt (PRIMARY, SHIPPED) | ✅ mode=**fitted** w/ E27 controls (11 pos / 22 neg); Platt target smoothing required (unsmoothed fit diverges on separated controls — v0.2 silently ran fallback); **jackknife loo_max_delta_p=0.0372 shipped in output; weight-zeroing test: accept set + ordering identical, max Δ 0.0196** | 0 | own (20-line Newton) | yes | ms | 2 params, defensible N ◐ICML05 | saturation-free recon feedback (gap-shrink, never reaches 1.0) | [[e27-controls-venn-abers]] [[mock-hardening]] |
| noisy-OR 3-channel (COMPARISON) | not shipped as primary (ADR-03: independence not claimable, value channel double-counts) | 0 | own | yes | ms | needs independence argument | diverges on zero-overlap pair | [[adr-03]] |
| Venn-ABERS interval (HONESTY LAYER, SHIPPED) | ✅ IVAP on runtime controls: weakest link [0.50,1.00], consensus [0.90,1.00] — ordering matches reviewer priority. **In-sample caveat measured 29.08 (E45):** computed with the relation's own control label present; leave-self-out widens weakest to [0.00,1.00], consensus to [0.89,1.00]; disclosed in README 6 | 0 | sklearn isotonic (~20 lines, no extra dep) | yes | ms | finite-sample valid | [p0,p1] width = calibration uncertainty; p1=1.0 expected at N=33 (say it first) | [[e27-controls-venn-abers]] |
| E27 extra control pages (SHIPPED, config) | ✅ `confidence.extra_control_pages: [9,10]` → +4 positives (sign-flipped cash-flow links, abs-compare) | 0 | own | yes | +6s (2 pages OCR) | config-driven (req 4) | controls only, never output | [[e27-controls-venn-abers]] |
| **LOO Brier report (SHIPPED, eval/calibration_loo.py)** | ✅ leave-one-out Brier 0.0085 on the 33 controls vs base rate 0.2222 vs raw fused 0.0579; LOO quartiles 0/8, 0/8, 2/8, 9/9 | 0 | own | yes | 40 s | one script | coherent on its own controls; not a transfer claim | [[v010-battery-foldin]] |
| GPU study: e5-large + bge-reranker-v2-m3 fused, LOO Platt (COMPARISON, Colab run-03) | ✅ Brier 0.145 [0.080, 0.226] vs raw CE 0.235; positives flatten at 0.19-0.20 with 7 positives + default L2; base-rate Brier 0.150 | 0 | Apache/MIT | GPU | min | Colab | N is the bottleneck, not model size; W2 closed (no figure swap) | [[gpu-calibration-study]] |
| isotonic cell-level on checksum cells | ? E18 (needs >200 certified cells) | 0 | sklearn | yes | ms | only if harvest succeeds | cell/row/table confidences stay ordinal compositions (README 6) | pending |
| split conformal (GARNISH) | α floor 1/(n+1) ◐ | 0 | MAPIE | yes | ms | small-N caveats | flag-for-review guarantee only | optional |
| cell confidence AS A TRIAGE SIGNAL (measured, E67) | ✅ both scorer errors at ranks 4 and 17 of 193; 17 cells (8.8%) for full recall, lift 11.35x, rank-order AUC 0.9529 on n=2 (noisy, stated); validation layer alone localises both inside 28 cells (14.5%) | 0 | shipped | yes | ms | none | limit: 98 cells sit at exactly 1.0, so the ranking works by pushing errors down, not correct cells up; the dropped-leading-digit mode defeats it and only the arithmetic catches that | [[confidence-review-budget]] |
| Jeffreys/Firth MAP (finite under separation) | E56: a 14.6406, p 0.886 at lowest positive, jackknife 0.029, LOO Brier 0.0019 (sharper, by construction) | 0 | own code | yes | ms | 20 lines | agrees with Platt at every control, crosses at gap midpoint 0.335; bolder inside the gap | [[prior-family-refits]] |
| Cauchy MAP, Gelman 2008 default prior | E56: a 17.6862, p 0.932 at lowest positive, jackknife 0.023, LOO Brier 0.0006 | 0 | own code | yes | ms | 30 lines | same crossing; boldest finite map; equally defensible, less conservative | [[prior-family-refits]] |
| conformal / SGR risk bound at n = 33 (research/108) | interval width 0.03-0.09 on the risk statement; zero errors on 33 -> 8.7% risk at 95% confidence | 0 | MAPIE / own | yes | ms | small | adds a guarantee sentence, not information | [[108-small-n-calibration-frontier-2026]] |
| format-agreement confidence feature (research/109) | ? E66 | 0 | own code | yes | ms | small | candidate feature below the shipped calibrator until measured | pending |
| raw similarity as confidence (REJECTED BY SPEC) | — | — | — | — | — | — | the thing req. 7 forbids | — |

## Cross-cutting: run modes (EARLY PLANNING 16.08, SUPERSEDED: the shipped lineup is tesseract + RapidOCR + x-clustering + e5-small + mmarco-mMiniLM, CPU-only, LLM tier disabled; kept as the record of the alternatives considered)
| Mode | precision story | cost | offline | when to present |
|---|---|---|---|---|
| Full-local (tesseract+TATR+e5+bge-reranker+Qwen3) | highest control, zero API | 0 | yes | bank/BDDK default |
| Local+API-linker (cache-replayed) | LLM judgment on hard pairs | ~$0.05 | replay yes | quality headroom |
| VLM-extraction tier | rescues bad scans | ~$0.30 | replay yes | robustness fallback story |

## Stage: evaluation and re-runnability (added 29.08, ftlink 1.0.0)
| Solution | accuracy | cost | license | on-device | latency | ops | diverges where | evidence |
|---|---|---|---|---|---|---|---|---|
| hand-transcribed reference (201 cells, 7 links) + 77 identities + blind second pass | ✅ 30/30 sampled, 6/6 dash/empty, fn11 markers exact, 53/53 identities, 201/201 secondary | 0 | — | — | hours (human) | audit JSON kept | one filing, same renders as the pipeline | [[gold-audit]] |
| scorer with intervals (eval/score.py) | ✅ CI [0.9645, 0.9988]; lower bounds 0.652; unmatched extracted rows 0 | 0 | own | yes | s | one script | no FP term in the cell metric (disclosed, count printed) | [[v010-battery-foldin]] |
| ablation with paired test (eval/ablation.py) | ✅ 1/7 vs 7/7; McNemar p = 0.031; margins 3.3974 / 0.4824 vs 0.2106 / 0.0402 | 0 | own | yes | 40 s | needs the CE | twin-label rule favours labels-only (disclosed) | [[v010-battery-foldin]] |
| determinism as exit code (eval/determinism.py) | ✅ True on macOS; Linux double run True (run-04); **the demo app's own precompute on a second Linux VM reproduces the sealed 199/201 + same 2 flagged cells (run-05, E74, 30.08)** — re-runnability now demonstrated on three independent axes (same-machine byte-identical, second-OS core pipeline, second-OS app) | 0 | own | yes | 60 s | one script | byte-identity scoped to the OCR build | [[linux-grader-drill]] [[app-linux-drill-run05]] |
| mutation harness (eval/mutations.py) | ✅ 3/3 named catchers; E21 dev harness 0 FA | 0 | own | yes | 3 min | one script | 3 hand-designed mutants, not an operator set | [[e35-shipped-validation-mutations]] |
| GriTS structure metric | not computed (stated honestly in README 9 / card 100) | — | — | — | — | — | would score header/hierarchy errors the cell metric ignores | [[100-eval-standards-card]] |

