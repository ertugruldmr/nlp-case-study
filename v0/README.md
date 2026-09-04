# ftlink: Finansal Tablo ve Dipnot İlişkilendirme

**Özet (TR).** Taranmış (metin katmanı olmayan) Özak GYO 2012 KAP denetim raporundan özet
finansal tabloları çıkaran, konfigürasyonda verilen dipnotun sayfasını otomatik olarak bulan,
dipnot tablolarını okuyup özet kalemlerini dipnot satırlarıyla satır seviyesinde
ilişkilendiren aşamalı bir boru hattı. Üç ilişkilendirme yaklaşımı birlikte çalışır ve
karşılaştırılır (çapraz kodlayıcı, değer+rol kuralları, sözcüksel taban çizgisi;
isteğe bağlı dördüncü: LLM seçici). Güven değerleri ham benzerlik değildir: hücre,
satır, tablo ve ilişki seviyesinde, dokümanın kendisinden türetilen kontrol örnekleri
üzerinde kalibre edilir. Doğrulama aşaması yapısal, biçimsel ve finansal kontrol
gruplarını içerir ve bu dokümandaki iki gerçek OCR hatasını (rakam değişimi ve
binlik/ondalık ayırıcı karışması) kendi başına yakalar. Aynı girdiyle iki çalıştırma bayt düzeyinde
aynı çıktıyı üretir. Kurulum ve çalıştırma için Bölüm 1'e bakınız.

A staged pipeline that extracts the summary financial tables from a scanned KAP audit
report (Özak GYO, 31.12.2012), locates a configured footnote automatically, parses its
tables, and links summary items to footnote rows with calibrated confidences and a
self-checking validation stage.

Key facts discovered by measurement and reflected in the design:

- The source PDF is a scan. All 95 pages are images with no text layer, so extraction
  is OCR-based by necessity, and three of the notes pages (55 to 57) are rotated
  landscape pages that need orientation recovery.
- The linking problem has two distinct physics: reconciliation links (a balance sheet
  carrying amount against opening/closing/total rows, whose labels are dates and
  roles, not item names) and item-semantic links (an income statement item against a
  named movement row). No single signal solves both; the pipeline combines them.

## 1. Setup and run

Prerequisites: Python 3.11+, [uv](https://docs.astral.sh/uv/), and tesseract with
Turkish data:

```bash
# macOS                          # Debian/Ubuntu
brew install tesseract tesseract-lang
                                 sudo apt install tesseract-ocr tesseract-ocr-tur
```

Place the source document at `data/ozak_gyo_2012.pdf` (KAP download:
`https://kap.org.tr/tr/api/file/download/33E83438337C023CE0530A4A622B5826`), then:

```bash
uv sync --frozen          # or: make setup
uv run ftlink run --config configs/default.yaml    # or: make run
uv run pytest -q          # unit tests
uv run python eval/score.py                        # score against reference cells
uv run ftlink run --config configs/alt_footnote.yaml   # footnote 12 demo (rotated pages)
uv run python eval/determinism.py   # or: make determinism (two runs, diff outside the run block, exit 1 on drift)
uv run python eval/calibration_loo.py   # or: make calibration (leave-one-out Brier, Venn-ABERS with and without own label)
```

Outputs land in `outputs/`: `result.json` (canonical, full schema), `relations.jsonl`
(one line per link, jq/pandas friendly), `report.html` (self-contained visual review,
opens by double click). First run downloads two small Hugging Face models
(about 950 MB on disk, fp32 safetensors plus tokenizers); subsequent runs are
offline. For an ASSERTABLE offline
property (air-gapped or regulated segments), set `HF_HUB_OFFLINE=1` after the
first run: the loaders then refuse any network access and serve the pinned
snapshots from the local cache.

Re-run check on a second platform: the same commands were executed from the
submission zip on a fresh x86_64 Ubuntu 22.04 machine (Python 3.13 through uv,
tesseract 4.1.1 from apt, empty caches): 37/37 tests, the same evaluation numbers
as on the macOS development machine (99.0 percent of reference cells, relation
precision and recall 1.00, 103 checks pass / 4 fail / 6 not evaluable, the same two
flagged corruption cells), and a byte-identical `result.json` (excluding the `run`
block) across two consecutive runs. The first `make run` took 165 seconds cold,
model downloads included.

## 2. Pipeline stages

Single-call whole-document conversion is rejected by design (and by the task). Stages:

```
S0 config          summary page range and footnote number come from YAML, never code
S1 render + OCR    PyMuPDF 300 dpi grayscale -> tesseract TSV (word boxes + confidences)
                   with automatic orientation recovery for rotated pages
S1b verification   every numeric cell crop is re-read by a second OCR engine
                   (RapidOCR, ONNX); digit disagreement caps the cell confidence.
                   Flag over fix: values are never silently replaced, the financial
                   checks arbitrate
S2 page detection  configured range verified by check: a configured page yielding
                   no coherent financial table fails STR_SUMMARY_RANGE, and
                   STR_FOOTNOTE_REFS_PRESENT fails when no summary row references
                   the configured footnote (misconfiguration fails loudly)
S3 table structure deterministic x-clustering over word boxes (details below)
S3b percent rescue rate rows (percent cells) are re-read per cell with the engines
                   swapped, because tesseract cannot read the % glyph on this scan
                   class (measured 0/6) while RapidOCR reads all six rate cells
                   verbatim; tesseract becomes the cross-check vote
S4 normalization   Turkish numeric grammar, three-state cells, label cleanup, row roles
S5 footnote locate TOC parse -> printed-to-PDF offset -> verify; bounded scan fallback
S6 candidates      char n-gram TF-IDF + dense embeddings + value anchor, fused with RRF
S7 linking         three approaches (cross-encoder, value+role rules, lexical baseline)
S8 confidence      multi-signal fusion calibrated on document-derived control samples
S9 validation      structural, format and financial check groups; flags into output
S10 output         result.json + relations.jsonl + report.html, deterministic IDs
```

### Table structure without ruling lines (S3)

The tables are borderless, so structure comes from geometry: money tokens are
right-aligned, so value columns are clustered on the right edge of numeric tokens;
dash marks are short and would create phantom columns, so they are assigned in a
second pass by column-center proximity; the footnote-reference column is a cluster of
small integers left of the values; the row label is what remains; indentation depth of
the label x-origin encodes the item hierarchy; stacked header lines above the first
data row provide period columns (year tokens) or category columns (Arazi ve Arsalar /
Binalar / Toplam). Prose paragraphs with inline numbers are rejected by a table
coherence test (repeated column structure), with an explicit exception for rate
tables, which are kept and flagged rather than dropped.

Table titles are not in the table: on this document class the real titles print as
page-level headings above the table bbox, while the in-table header lines carry only
the stacked period columns. So the title comes from the heading block above the
table: on any page, the nearest note-number-prefixed line above the table (a
note number followed by its heading text; OCR sometimes splits them into two
same-height lines that are re-joined) wins; when no such line exists, as on the
summary pages, the topmost multi-word uppercase block that is not the configured
company name (the statement heading) is used. A page with no qualifying heading
yields an empty title: honest absence beats a prose fragment in a required field.
Titles are deliberately never consumed by the matching stages (Section 3), so this
derivation cannot move any link or confidence.

Text-only lines inside a table body are resolved by an indent rule measured on this
scan: a wrapped long label prints its continuation row indented under the fragment
(about 18 px), while a group header (Dönem Karı Dağılımı) is followed by rows at the
same left edge. So a cell-less labeled line merges into the next row only when that
row indents past it; otherwise it becomes a value-less group-header row that keeps
the hierarchy intact.

### Rate rows: the engines swap roles (S3b)

The valuation-assumptions table (İskonto oranı, Doluluk oranı, Kira artış oranı)
defeats the primary engine in a specific, measured way: tesseract renders the %
glyph as a digit or drops it (%9 becomes 49, %86,6 becomes 486,6) at every dpi and
psm combination tried, while the second engine reads all six rate cells verbatim
from the same crops. So for rate rows only, RapidOCR becomes the reader and
tesseract the verifier: each value-column crop is re-read by RapidOCR, then
tesseract re-reads it (psm 7, symbol whitelist) as a cross-check vote. Tesseract's
corruption is a leading-character artifact, so digit agreement is tested
exact-or-suffix, both readings land in the cell's confidence components, and a
disagreement caps confidence instead of being silently arbitrated. Rate lines whose
value tokens all failed the money test (and therefore never became rows) are
re-collected from the OCR lines below the table, and a % glyph that fused into a
small integer and masqueraded as a footnote reference is removed. A dedicated
format check (FMT_PERCENT_BOUNDS) then requires percent values to lie in [0, 100],
which is exactly the class the corruption produces (486,6).

The same corruption also hits the LABEL side: the printed "(%)" unit marker in
these row labels is read as (©), (90) or (0). `label_norm` strips that trailing
junk token (it carries no label semantics; alphabetic parentheticals such as
"(net)" are never touched), while `label_raw` preserves the raw read, so the
output keeps both the clean and the honest version of every rate-row label.

### Footnote location (S5)

Primary path: find the İÇİNDEKİLER page, parse note entries, resolve the printed-page
to PDF-page offset from a page footer folio, jump, and verify the heading on the
target page. OCR damages the TOC in measured ways, and each has a countermeasure:

- note numbers mangle ("NOT 11" reads as "NOT1lI"), so entries are renumbered by their
  sequence position, which is immune to glyph damage;
- dot leaders eat leading page digits ("49-50" reads as "9-50"), so a printed page
  that violates the non-decreasing page order is distrusted and replaced by a bounded
  scan over the window implied by its neighbors;
- the final answer is always verified by re-reading the target page heading, and the
  footnote's full page set is the contiguous run of pages carrying its heading.

Fallback path when the TOC is unusable: scan the notes range for the heading. On this
document, footnote 11 resolves to PDF pages 53 and 54 (bounded scan, about 14 s) and
footnote 12 to pages 55 to 57 (direct TOC hit, about 17 s, all three pages rotated).

## 3. Models: what, why, settings

| Stage | Model | Why |
|---|---|---|
| S6 dense channel | `intfloat/multilingual-e5-small` (118M, MIT) | Strongest small multilingual embedder on the Turkish portions of the MTEB family per parameter at selection time (a leaderboard reading, not re-verifiable from this repository; the binding evaluation is in-document: the dense channel carries the paraphrase pairs the lexical channels miss). Measured to be non-load-bearing: swapping in `paraphrase-multilingual-MiniLM-L12-v2` (same size class) via the two config keys leaves the accepted relation set identical and moves confidences by at most 0.0009, so the channel design, not the specific embedder, carries the result. `query:` prefix on both sides, the documented convention for symmetric matching. Encoding about 40 short labels costs well under a second on CPU. |
| S7 approach A | `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` (118M, Apache-2.0) | Ranks all reference links into the top 5 with the serialization below, at single-digit milliseconds per pair on CPU (re-timed on the dev machine: 3 ms batched, 8 ms single-pair; machine-dependent). Turkish is not among mMARCO's 14 languages (English plus 13 machine-translated targets), so the Turkish behavior is zero-shot transfer through the multilingual MiniLMv2 backbone distilled from XLM-R; that is one more reason the ranking claim is measured on this document instead of read off a model card. Larger rerankers (bge-reranker-v2-m3, 568M) were evaluated and matched but not beaten at rank level, so the small model ships and the large one remains a config swap. |

Inference settings: CPU, fp32, no sampling anywhere (cross-encoders and embedders are
deterministic forward passes). Two pinning layers, because they pin different
things: the uv lockfile pins PACKAGE versions, and the model WEIGHTS are pinned to
explicit Hugging Face snapshot revision hashes in the config, passed to every model
loader, so a re-published model card cannot change what a fresh machine downloads.
Models with
non-commercial licenses (jina rerankers and embeddings) were evaluated on paper and
excluded: a bank cannot ship CC-BY-NC.

### Input construction (measured, not assumed)

The cross-encoder pair text is `label | value ; value` for both sides, with amounts
formatted with Turkish dot grouping exactly as printed. This is the single most
important input decision: movement-table rows are labeled by dates and roles
("31 Aralık 2012 itibari ile kapanış bakiyesi"), so with labels alone the correct
targets rank near the bottom; with values in the pair text they rank 1 to 5 out of
19. The measurement is re-runnable from the shipped output:
`uv run python eval/ablation.py` ranks every reference link under both
serializations and reports R@5 = 1/7 labels-only (gold targets at ranks 9 to 19)
against 7/7 with values (ranks 1 to 5), prints the top-1 margin of every query, and
adds the paired view: on the 7 reference links, 6 are discordant (hit with values,
miss without) and none the other way, exact McNemar two-sided p = 0.031, which is
directional evidence on one document, not a population claim. One convention favours
the labels-only condition: when two footnote rows print identical labels (the 2012
and 2011 movement tables), the best rank across the twins is credited, a tie that
labels-only could not break on its own.
Within one footnote the table title is deliberately NOT added to candidate texts: it
is constant across all candidates, adds no discrimination, and measurably degrades
the easy pairs.

### Chunking of long documents and large tables

The document is processed page by page (render, OCR, structure), so document length
only affects the locate stage, which reads the TOC instead of scanning when it can.
Tables are chunked naturally by the line/row structure; no table in scope approaches
model context limits because every model input is a single row pair, never a whole
table. Rotated wide tables (footnote 12) are handled by orientation recovery, not by
special-casing.

## 4. Candidate generation and ranking (S6)

Four channels, fused with weighted Reciprocal Rank Fusion (k = 10):

- char_wb 2-4 TF-IDF cosine over normalized labels: robust to Turkish agglutination
  and residual OCR noise, and it carries the morpheme overlap ("değerleme" against
  "değer değişikliği") that word-level matching misses;
- token-set fuzzy ratio (rapidfuzz): a second, word-level lexical voter. Candidate
  generation is recall-oriented, so a partially redundant voter is harmless here;
  this is a different job from approach C, which uses the same similarity as an
  ACCEPTANCE baseline in the linking stage;
- multilingual-e5-small cosine: semantic channel for paraphrased items;
- value anchor (weight 3): equal absolute amounts between the item's period values and
  a candidate row's values. High amount multiplicity is usually a legitimate
  reconciliation chain, not noise, so anchors are period-scoped and later gated by row
  roles instead of being stop-listed.

The candidate set per summary item is the RRF top 8 plus every anchor hit. Candidate
recall on the reference links is 7 of 7. The stage's constants are
sensitivity-checked by config re-runs on this document, not argued: `top_k` 8 to 2,
`anchor_weight` 3 to 0, and `rrf_k` 10 to 60 (the RRF paper's default) each leave
the accepted relation set identical, because the anchor-union rule and rank-1
admission carry the links. One honest side effect is part of the result: at
`top_k` 2 the calibrator's negative pool starves (22 to 2), so calibration drops
to fallback mode and every relation ships force-flagged; beam width is also a
calibration resource, and the system discloses the change instead of hiding it.
Every re-run is one config edit away for the grader.

## 5. Linking approaches and thresholds (S7)

- A, cross-encoder: accepts when the sigmoid score clears `linking.accept_threshold`
  (0.5), or when the pair is the top-ranked candidate for its summary item and clears
  the coarse rank-1 floor `linking.rank1_min_score` (0.2). Rank-aware acceptance is
  deliberate: absolute sigmoid scales vary across rerankers, rank ordering is the
  validated signal, and the floor only guards rank-1 admission against noise-level
  scores; both numbers are config, and threshold re-runs at 0.2 and 0.8 leave the
  accepted set unchanged on this document.
- B, value + role rules: accepts when a period-scoped value match exists AND the
  footnote row role is consistent (stock values bind to opening/closing/net book
  value/total rows; flow values bind to movement rows). Roles come from five
  deterministic label rules. Fully explainable, no ML.
- C, lexical baseline: rapidfuzz token-set ratio over Turkish-lowercased labels
  (the OCR-junk strip of `label_norm` applies to the TF-IDF channel only; C and the
  fuzzy candidate channel see the raw label after Turkish lowercasing), threshold
  `linking.lexical_threshold` (0.75). Kept as the deliberately insufficient
  baseline. On this document it accepts nothing, and the insufficiency is
  measured in BOTH directions by a config re-run: at a lowered bar of 0.4 it
  admits three false links (precision drops to 0.70), all three of which arrive
  with calibrated confidences of 0.044 to 0.048 and the low-confidence flag.
  Word-level matching does not merely underperform here; it injects garbage the
  moment it is loosened, and the calibration layer prices that garbage correctly.

- D, LLM select (optional, `linking.llm.enabled`, off by default): one call per
  summary item to any OpenAI-compatible endpoint; the model sees all candidates and
  selects related rows under a strict JSON schema. The prompt is Turkish: the summary
  item's label and per-period values, then one line per candidate (`id | table hint |
  row label | values`), with the instruction to select, per period, every row carrying
  the same amount (opening, closing, net book value and total rows included) and to
  leave out anything uncertain; the reply is JSON with the selected candidate ids.
  When the tier is enabled, every
  response is written to `cache/llm_calls.jsonl` keyed by a prompt hash, and later
  runs replay the cache offline and byte-identically, so determinism never depends
  on provider seed behavior. The repository ships with the tier disabled and
  therefore without a cache file; enabling it creates the cache on first run (the
  cache-replay and unreachable-endpoint paths are covered by unit tests). Local
  measurement (35B-class local model, temperature 0): precision 1.00 on both
  items, identical picks across repeated runs; the default `linking.llm.model`
  value is an endpoint-name placeholder and carries no measurement. D is
  decision-level and stays OUTSIDE the calibrated fusion: a pair accepted by D
  alone ships with agreement `d_only`, its confidence still comes from the fused
  channels (low by construction), so it always arrives flagged for review, and
  D's acceptances never feed the calibrator's control set.

Fallback chain: if the cross-encoder model cannot load (offline first run, wrong
platform), approach A scores zero and accepts nothing, the run continues on
approaches B and C, the run block records `models_loaded.cross_encoder: false`,
and every relation ships force-flagged because the approach comparison is
degraded (the path is unit-tested);
if OCR yields no words for a page, orientation recovery retries three rotations, and
a page that stays empty contributes no words, which on a configured summary page
fails STR_SUMMARY_RANGE loudly (each tesseract call is also bounded by a timeout, so
one hung page cannot stall the run); if the LLM endpoint is unreachable, approach D
degrades to no-op without failing the run.

## 6. Confidence (S8)

Confidence is never a raw model similarity. Levels:

- cell: OCR word confidence times numeric-parse confidence, times 1.05 (capped at 1.0)
  when the second engine reads the same digits and capped at 0.4 when it disagrees. A
  repaired number is flagged `repaired` and capped at 0.7 (one lost thousands separator
  regrouped) or 0.5 (the heavier regroup).
- row: mean of cell confidences, with a penalty for structural doubts (missing label).
- table: mean row confidence, discounted by header/period completeness.

Cell, row and table confidences are ordinal compositions (OCR word confidence, parse
confidence, engine agreement, structural penalties), not calibrated probabilities; only
the relation level is calibrated. On this document the two wrong cells rank 4th and
17th lowest of 193 by cell confidence: the digit substitution is caught by the cell
layer itself (engine disagreement, 0.40), the separator corruption is not (both engines
agree on the digits, 0.85) and is caught only by the parent-sum residue, which is why
the financial check group exists. The other three cells at or below 0.5 on this run are
correct values with low OCR confidence (a group total, a repaired footnote cell, a
per-share figure): cell-level flags are recall-oriented, and precision comes from the
check groups, not from the cell score.
- relation: a weighted fusion of the three approach scores (0.4 cross-encoder, 0.4
  value rules, 0.2 lexical) mapped through a logistic function whose two parameters
  are fitted at run time on control samples derived from the document itself, as the
  task statement permits: positives are decisions that some approach accepted and
  whose value reconciliation check passes; negatives are candidates all approaches
  rejected. Decisions that some approach accepted but that do NOT reconcile enter
  neither pool: they are the hard region, and the calibrator must not learn it from
  its own acceptances. The fit uses Platt's original target smoothing (t+ = (n+ + 1)/(n+ + 2)),
  which keeps it finite under perfectly separated controls, the normal situation at
  this control-set size. The family choice is not taste: on perfectly separated
  controls (which STR_CALIBRATION_CONTROLS discloses) an isotonic fit provably
  collapses to a two-plateau step function whose accepted-side value is exactly
  1.0, and an unsmoothed logistic saturates the same way, so of the standard
  small-N families only the smoothed Platt map stays graded. The Platt map's own
  leave-one-out stability SHIPS in the output (loo_max_delta_p in the
  STR_CALIBRATION_CONTROLS detail), and so do the fitted parameters (`platt_a`,
  `platt_b`), which makes the map itself monitorable across documents without labels; the isotonic side of the comparison was a
  development measurement on the same 33 controls, where isotonic also moved
  more under leave-one-out. A leave-one-out Brier score is one command away
  (`make calibration`, eval/calibration_loo.py): on the 33 controls the smoothed
  Platt map scores 0.009 against 0.222 for the constant base rate and 0.058 for the
  raw fused score, and the leave-one-out reliability quartiles hold 0 positives in
  the two lowest quartiles (mean prediction about 0.05), 2 of 8 in the third (mean
  0.24) and 9 of 9 in the top (mean 0.92). These are the calibrator's own controls,
  so the number says the map is coherent on this document, not that it transfers.
  If the control set still degenerates (fewer than three positives or three
  negatives, or a non-finite fit) the mapping falls back to fixed parameters a = 6,
  b = -3 (a steep map through 0.5 at a fused score of 0.5, ordinal only, never read as
  a probability) and says so in `confidence_components.calibration_fitted`
  (1.0 = fitted, 0.0 = fallback; kept numeric because every component in that
  dict is a float, and the authoritative mode string ships in the
  STR_CALIBRATION_CONTROLS check detail).

The control set is enlarged beyond the summary tables by `confidence.
extra_control_pages` (default: the cash-flow statement, pages 9 and 10), whose rows
also reference the configured footnote with sign-flipped amounts. Those rows run
through the same candidate and linking machinery but only feed the calibrator; they
never appear in the output. On this document that yields 11 positives and 22
negatives, a fitted (not fallback) calibration, and the STR_CALIBRATION_CONTROLS
check reports the counts.

Validation feedback is saturation-free by construction: a passing value
reconciliation shrinks the remaining doubt by 15 percent (1 - 0.85 x (1 - p), so a
calibrated probability never reaches 1.0); a failing one debits the probability to
60 percent; not-evaluable applies a mild debit (a factor of 0.9).

Three properties of this construction are measured, not asserted:

- Stability: the STR_CALIBRATION_CONTROLS check reports a jackknife over the
  control set (refit with each control point left out); on this document the worst
  movement of any calibrated confidence is 0.037 (`loo_max_delta_p`).
- Weight sensitivity: rerunning with the lexical channel zeroed (weights
  0.5/0.5/0.0 instead of 0.4/0.4/0.2) leaves the accepted relation set and the
  confidence ORDERING identical and moves confidences by at most 0.02: the
  runtime-refit mapping absorbs the hand weights, so no fragile information hides
  in them.
- Guarded circularity: the controls are label-free but not model-free, so the
  positive rule deliberately requires a second signature the models cannot
  produce: an arithmetic value reconciliation of the document itself. EVERY
  positive, consensus included, requires that signature (enforced in code, not
  just described), and the optional LLM tier's acceptances never enter the
  control set. Negatives need no arithmetic at all (rejected by every approach). The
  reconciliation signature itself is period-agnostic by design (a balance-sheet
  amount legitimately reconciles to the other year's movement table: opening equals
  prior closing), so period discipline lives in the anchor channel and in the
  relation's `period_scope`, not in the signature. Coincidental value collisions are
  bounded by period-scoping and role gates on the anchor channel. One consequence is
  stated plainly: approach B's acceptance test and the reconciliation signature are the
  same arithmetic (a period-scoped value match), so every B acceptance is a positive
  control and the perfect separation of the controls is partly structural, not evidence
  of model skill. The fitted map therefore certifies value-anchored links. A link with
  no value match cannot reconcile, takes the 0.9 not-evaluable factor, and on this
  document's map needs a cross-encoder score above roughly 0.73 (with a typical lexical
  score of 0.4) to clear the 0.5 operating point: the design is conservative on
  text-only links by construction, which is the intended behavior for a reviewer queue.

The low-confidence flag at 0.5 is a demonstration operating point, not a claim
about costs: the calibrated scale is the deliverable, and a consumer derives their
own threshold from costs without refitting anything. The derivation: reviewing a
relation costs c_review; accepting it unreviewed costs (1 - p) x c_miss in
expectation, so review whenever (1 - p) x c_miss exceeds c_review, that is,
whenever p < 1 - c_review / c_miss. Worked example: review cost 1, miss cost 20
gives a threshold of 0.95, so almost everything gets reviewed, which is the sane
behavior when misses are twenty times as expensive. The threshold RISES with the
miss cost. That portability is the practical difference between shipping
calibration and shipping one tuned threshold.

Two flag semantics are deliberate: a relation is flagged when its calibrated
probability sits below the threshold OR when the calibration mode is fallback,
because a fallback-mode number is ordinal, not probabilistic, and must always
reach a reviewer regardless of where it lands on the scale. The footnote-12 demo
shows this firing: its single cross-note relation scores 0.53 under fallback
calibration and ships flagged.

Each relation also reports, whenever the control set holds at least three positives
and three negatives (below that the interval is omitted and the fallback rule flags
the relation anyway), a Venn-ABERS interval `[venn_abers_p0, venn_abers_p1]`
in its components: two isotonic fits over the control set with the test point
appended as a negative and as a positive (Vovk and Petej 2014). The interval width
is the honest statement of how much the calibration itself can be trusted at this
control-set size; on this document the weakest reconciliation link reports
[0.50, 1.00] while the consensus fair-values link reports [0.90, 1.00], which is
exactly the ordering a reviewer should act on. One caveat is stated rather than
hidden: the controls are the emitted decisions themselves, so each interval is
computed with the relation's own control label present. The same script reports a
leave-self-out variant (own label removed before the two isotonic fits): the weakest
link widens from [0.50, 1.00] to [0.00, 1.00] and the consensus link moves from
[0.90, 1.00] to [0.89, 1.00]. The weakest link's lower bound rests on its own label,
which is why the interval is presented as a review-ordering device and a disclosure
of control-set thinness, not as a coverage guarantee.

Every relation carries its components, so a reviewer can see exactly what produced
each number. Relations below 0.5 are flagged `low_confidence: true` in the output.

## 7. Validation (S9) and results on this document

Three groups, with an explicit fourth status: a check that cannot be evaluated
reports `not_evaluable` and never silently passes or treats a missing operand as
zero.

Structural: period columns present and in the document's descending year order;
footnote references within plausible note-number range; located footnote heading
verified against the configured number (the binding of a reference to its row is
verified indirectly: REL_COVERAGE plus FIN_RECONCILE require every row carrying the
configured reference to produce a value-reconciled link; there is no separate
reference-on-the-right-row check); and per-item link coverage (REL_COVERAGE):
every summary row that references the configured footnote must produce at least
one relation, so a silent linking loss on a referencing item (for example a
unit-scale mismatch killing the value anchor while the text channels score near
zero) ships as a failing check, never invisibly.

Two failure styles are deliberate. A configured footnote that cannot be located
aborts the run with a clean error and exit code 2 (there is no meaningful partial
output without the target note), whereas a misconfigured summary page range ships
with failing structural checks, because a partially wrong page set still yields
inspectable tables and the checks say exactly which pages are wrong.

Format: repaired-cell flagging (FMT_REPAIRED_CELLS); the dash / empty / zero three-state
legality (FMT_THREE_STATE), which is a type-level guarantee of the output model surfaced as
a check, so it passes by construction and exists for visibility, not detection;

Format also includes sign legality (a row labeled "(-)" must not carry a positive
value) and the document-level second-engine agreement summary. The sign check keys on
the printed "(-)" marker; on this document one such marker is OCR-read as "(<9)"
(Pazarlama, Satış ve Dağıtım Giderleri), so that row is not checked (its values are
negative anyway). A stricter version would treat any corrupted trailing parenthesised
token as a candidate marker and report not_evaluable.

Financial: movement roll-forward (opening + flows = closing, per column); row-wise
category sums (Arazi + Binalar = Toplam); parent sums over the extracted hierarchy;
grand totals checked against member-set hypotheses with an exact, pre-enumerated
rule (the hypotheses are structural and fixed in advance: same-indent members,
members-with-children, and same-indent with aggregate rows dropped when a running
sum of subsequent members reproduces them; a hypothesis is evaluable only when
none of its member cells is missing and no fractional per-share row is mixed in;
the check passes when at least one evaluable hypothesis reproduces the total, the
detail names how many did, it fails when none does, and it reports not_evaluable
when no hypothesis is evaluable, so ambiguity never converts into a silent pass);
an income-statement flow cascade (each
uppercase milestone equals the previous one plus the intervening signed rows, with
value-based deduplication of breakdown re-listings and aggregate/component double
counts, because scanned layouts are too flat for indentation to be trusted); and
value reconciliation per accepted relation.

Results on the default run (113 check instances; the count includes per-scope
repeats of one check id and the type-level FMT_THREE_STATE, so the informative signal is
in the fail and not_evaluable lines): 103 checks pass, 6 report not_evaluable (four
FIN_GRAND_TOTAL instances on two income-statement milestone rows, where a fractional
per-share row leaves no evaluable member hypothesis, and two STR_PERIOD_ORDER on the
single-period movement tables, where order has nothing to compare), and all 4
failures are genuine document/OCR defects the pipeline caught on its own: the
second-engine disagreement summary and two parent-sum contradictions are analyzed
as cases 1 and 2 in Section 8, and the fourth (FMT_REPAIRED_CELLS) flags three
footnote-table cells whose lost thousands separators were regrouped by the repair
tier, values kept and capped at confidence 0.7, which is the repair tier's
precision-first contract making itself visible rather than a defect of its own.
The Stoklar digit corruption is additionally pinpointed BEFORE any financial
check runs by the second-engine disagreement, which caps that cell at confidence
0.4; the separator corruption passes the digit comparison by nature (both engines
read the same digits) and is caught by the parent-sum residue instead, a measured
division of labor between the check groups.

The check suite itself is testable, and the test ships: `uv run python
eval/mutations.py` injects three corruptions into the live pipeline (a summed
member digit, a grand total, and the reference row's values, which kills the
value anchor and with it the links) and asserts each is caught by NEW failing
checks against the clean reference run: the member digit by parent sums at two
hierarchy levels, the total by the grand-total hypothesis vote, and the induced
linking loss by REL_COVERAGE. A validation stage that has never watched itself
miss or catch an injected error is an assertion; this one is a measurement.

Operational signals: run this nightly over a filing stream and the per-document
output already carries the monitoring surface: check pass/fail/not_evaluable rates
per group (the financial-group failure rate is the data-quality alarm), the
second-engine disagreement rate (scanner or layout drift shows up here first), the
calibration mode with its control counts (a fitted-to-fallback shift is the canary
that a document class stopped yielding controls), and the low-confidence relation
rate plus the Venn-ABERS width distribution (the review-queue depth). Page on
fallback-mode or financial-failure spikes; route low-confidence relations to human
review, which is what the flag exists for.

## 8. Error analysis (low-confidence and failure cases)

Six cases, all measured on this document, summarized first and analyzed below:

| # | Case | Expected | Produced | Failing stage | Root cause | Fix / catch |
|---|---|---|---|---|---|---|
| 1 | Silent digit substitution | Stoklar 2012 = 77.543.097 | 77.943.097 | OCR recognition | 5 misread as 9; number stays well-formed | flagged twice: second-engine disagreement caps cell at 0.4; FIN_PARENT_SUM localizes +400.000 |
| 2 | Separator read as decimal | Finansal Yatırımlar 2012 = 4.224 | 4,224 (=four) | OCR glyph + grammar | dot misread as comma; token is a valid decimal | digits identical so the engine check passes BY NATURE; FIN_PARENT_SUM catches the impossible .224 residue |
| 3 | Percent glyph destruction | %9, %10,5, %86,6, %80,8, %3, %2-%4 | 49, 710,5, 486,6, dropped, dropped row | OCR recognition | tesseract has no reliable % class on this scan | S3b engine swap: RapidOCR reads 6/6, tesseract votes by digit suffix; FMT_PERCENT_BOUNDS guards the [0,100] range |
| 4 | TOC dot leaders eat digits | NOT 11 at printed 49-50 | "9-50" | OCR on contents page | dot leader touches the page number | monotonicity rule distrusts 9 after 48; bounded scan finds page 53; heading verified |
| 5 | Wrapped label vs group header | one row "Özkaynak ... Paylar"; header rows kept | fragment dropped, label truncated | structure segmentation | text-only lines inside a table body were discarded | indent rule: continuation rows indent under their fragment, group headers align with what follows |
| 6 | Rotated landscape pages | footnote 12 tables (pages 55-57) readable | near-zero words upright | render orientation | scan printed sideways; PDF /Rotate does not correct it | orientation recovery re-renders at 90/270/180 and keeps the confident-word maximum; extraction stays demo-grade and its check failures are reported honestly |

1. Silent digit substitution. The format stage cannot see it because the corrupted
   number is perfectly well-formed. Caught twice, independently: the second-engine
   cross-check disagrees (RapidOCR reads the correct 77.543.097) and caps the cell
   at confidence 0.4, and FIN_PARENT_SUM localizes it (the Dönen Varlıklar children
   sum overshoots the printed group total by exactly 400.000). This double catch is
   the flag-over-fix design working as intended: the pipeline does not silently
   substitute the second reading, it makes the disagreement and the arithmetic
   contradiction visible.

2. Thousands separator read as decimal comma. The digit cross-check does NOT catch
   this one (both engines read the same digits 4224; the corruption is in the
   separator, not the digits), which is exactly why the financial group exists:
   FIN_PARENT_SUM exposes the fractional residue (.224) that a money column cannot
   have. Division of labor between check groups, demonstrated on a real cell.
   Improvement: column-type inference (a column whose other values are all integers
   makes a decimal member suspect).

3. Percent glyph destruction. The primary engine's failure is total on this class
   (0/6 rate cells) and produces PLAUSIBLE numbers: 486,6 is a well-formed decimal,
   and a %-digit fusion ("%9" as "49") even masqueraded as a footnote reference.
   The fix inverts the engine roles for rate rows only (Section 2, S3b) and its
   output is auditable: every rescued cell records both engine readings and the
   vote class in its confidence components, and FMT_PERCENT_BOUNDS would flag the
   corruption class again if the rescue ever regressed.

4. TOC dot leaders eat page digits. Caught by the monotonicity rule (9 cannot
   follow 48) and repaired by the bounded scan, which found page 53 and verified
   the heading. This is why the locate stage never trusts a single signal.

5. Wrapped label vs group header. Both print as text-only lines inside the table
   body, so dropping them (the original behavior) truncated the wrapped
   "Özkaynak Yöntemiyle Değerlenen Yatırımların Kar/Zararlarındaki Paylar" label and
   lost the Dağılımı group headers. The two cases are separated by a measured
   geometric signal, not semantics: a continuation row indents past its fragment
   (about 18 px on this scan), a group header's following rows stay at its left
   edge. Header/body boundaries need content tests, not just position tests.

6. Rotated landscape pages (footnote 12 demo, `configs/alt_footnote.yaml`). The
   upright OCR pass yields almost no words, and raw word count is a misleading
   recovery signal because sideways text still produces junk words; the recovery
   keeps the rotation with the most CONFIDENT multi-char words. Extraction quality
   on these pages is honestly lower and the run reports it as failing roll-forward
   checks instead of hiding it; the point of the demo is that the footnote number
   and page set come from config and the pipeline degrades visibly, not silently. Two
   page-level scoping limits show in this demo and are stated as such: footnote pages are
   assigned by the heading at the top of the page, so a page shared by two notes goes to
   the note whose heading is on top and the neighbor's table enters the footnote table
   set (here page 57 also carries note 13's first table, `p57.t07`, visible in the output
   title), and a note that starts mid-page loses that page (footnote 13 starts under
   note 12's tables on page 57 and is located from page 58). Sub-page segmentation by
   heading position is the fix; the titles in the output make both cases auditable.

Minor defects also visible in the output and worth naming: the 2011 movement table's
first column header carries OCR junk ("harcamalar Arazi ve Arsalar"); columns still map
positionally and every value under it scores correct, but header text has no check of
its own.

## 9. Approach comparison: where they diverge, not just scores

All three approaches run on every candidate; each relation records per-approach
scores, accept decisions, and an agreement class (`consensus`, `a_only`, `b_only`,
`baseline_only`, plus `d_only` when the optional LLM tier is enabled and admits a
pair every fused approach rejected; such relations keep the fused channels'
conservative confidence and always arrive flagged). On this document:

- consensus: the income-statement fair-value link for 2011 and the fair-values-table
  total. Both semantics and value+role agree; these carry the highest confidences.
- b_only (value + role rules): five relations. Four are the balance-sheet
  reconciliation links against the movement tables: their labels are pure
  date/role text, so the text model under-accepts them and the value+role
  approach carries them. This is the reconciliation-link physics described at the
  top, visible in the output as a systematic divergence pattern, not a random
  disagreement. The fifth is subtler and worth naming: the income-statement
  fair-value item links to BOTH movement tables (2011 and 2012 twins), and the
  cross-encoder's rank-aware acceptance admits at most one below-threshold
  candidate per summary item, so the 2011 twin lands consensus (rank 1) while the
  2012 twin (rank 2, score 0.18) is carried by the value+role approach alone.
  Twin-table links therefore systematically split consensus/b_only; that is a
  property of rank-1 admission, not an inconsistency.
- a_only (cross-encoder): not present in the shipped run. It occurred during
  development on the fair-values total row (label empty in print) before the
  role-inference fix; in the shipped output that link lands consensus. The class
  stays reachable by design: under the approach-B fallback (role inference
  degraded), the cross-encoder still carries value-bearing rows alone.
- The lexical baseline accepts nothing, and on the hardest pair (Yatırım Amaçlı
  Gayrimenkul Değerleme Farkları against Makul değer değişikliğinden kaynaklanan
  kazanç) word-level similarity stays far below the acceptance bar (token-set
  ratio about 0.40 against the 0.75 threshold) while both other approaches link
  it confidently. That pair is the reason a semantic component is required at all.
- Comparison fairness: C sees labels only by design (it is the word-matching baseline
  the task calls insufficient), while A sees `label | values` pair texts; the
  divergence map therefore measures what values add, not two equally informed models.

Scoring against the hand-labeled reference (`eval/score.py`): link precision 1.00
and recall 1.00 on the reference relation set (the two movement tables print
identical row labels, so the scorer disambiguates twin rows by value overlap), and
99.0 percent exact cell accuracy over all 201 reference cells. The two remaining
wrong cells are exactly the two real OCR corruptions analyzed in Section 8, and
both are flagged by a failing check plus a confidence cap rather than passing
silently: the pipeline's contract is zero silent errors, not zero errors.

Scorer conventions, stated so the numbers can be audited against `eval/score.py`: a
reference cell whose state is empty counts as correct when the extractor emits no cell
at that position (there is nothing to extract, and an emitted number there would count
as a wrong state); and a predicted relation whose rows cannot be mapped to any
reference row is left out of the precision count instead of being counted as a false
positive. In the shipped run every predicted relation maps (predicted 7, reference 7),
so the second convention is inert here; on a document with links outside the reference
set it would understate false positives, which is why the number of mapped relations
is printed next to the precision. The cell metric walks the reference rows, so an
extracted row that matches no reference row would fall outside it; the scorer prints
that count and it is 0 on the shipped run.

Uncertainty on these numbers, printed by the scorer: the cell accuracy carries a
Clopper-Pearson 95 percent interval of 0.965 to 0.999 (n = 201 cells of one
document), and 7 of 7 relations gives an exact one-sided 95 percent lower bound of
0.65 on both precision and recall. Seven links can show that the approach works on
this filing; they cannot estimate its error rate across filings.

Provenance of the reference: one person transcribed all 201 cells from the page
renders and accepted a value only after 77 arithmetic identities held; a second,
blind re-transcription pass over a seeded 30-cell sample, every dash and empty
state, and the whole footnote-reference column agreed on every item.

## 10. Output schema (why it looks the way it does)

`result.json` holds flat, ID-referenced collections (tables, rows, cells, relations,
checks), the shape mature document-AI products expose; hierarchy is `parent_row_id`
references, not nesting, so consumers can walk it either way. IDs are deterministic
and semantic (`p05.t00.r003.c01`), so two runs on the same input and config are
byte-identical apart from the quarantined `run` block; that is re-runnability made
verifiable with a diff, and `eval/determinism.py` (make determinism) turns that diff
into an exit code. `document.source_sha256` fingerprints the input file so outputs
can be joined to their source across a corpus. The claim is scoped honestly: package versions are pinned
by the lockfile and model weights by snapshot hashes, but the OCR engine itself is
a system dependency, so cross-machine identity holds given the same tesseract
build. The run block records `tesseract --version` for exactly this reason, and a
drifted OCR build announces itself through the second-engine disagreement rate
before anything else. `document` echoes the configured company, period and currency (they are not extracted
from the scan) next to the input fingerprint. Money is Decimal serialized as string (0,058
cannot live in a float). A cell value is a discriminated union on `state` (`number`, `dash`, `empty`),
because the dash and the empty cell are semantically different absences and zero is a
number (this document prints no empty cells: every absence is a dash, so the `empty`
state is exercised by the tests, not by this run). Every relation carries per-approach evidence and its confidence components.
`relations.jsonl` is a derived, self-contained view (one line per link with labels
inlined) for quick grading with jq or pandas.

## 11. Deliberately not built

CI/CD (a lockfile plus `make test` gives the same signal here), containers as the
primary path (Python plus tesseract is a lighter ask; a Dockerfile would add a
daemon dependency for the grader), Kubernetes/IaC (one process, one document), a
database (JSON artifacts are the contract), authentication (nothing is served), and
model training (the task forbids it). Each omission trades no correctness for less
friction.

Also not built, stated so they are not mistaken for oversights: leading-minus
negatives (this filing prints every negative in parentheses; a `-1.234` token is not
parsed as a number today), a text-layer fast path (every page is OCRed; a born-digital
filing would work, slower than necessary), automatic detection of the summary-statement
pages (the range is configured and verified by STR_SUMMARY_RANGE), traversal of
cross-references between footnotes ("bkz. Not X"), cross-statement identities as
shipped checks (assets equal liabilities plus equity, the net-profit tie between
balance sheet and income statement, prior-year closing equals current-year opening),
and role rules beyond the five Turkish phrases this filing uses (a filing writing
dönem başı / dönem sonu would need them added to the lexicon).
