# ftlink: Finansal Tablo ve Dipnot İlişkilendirme

Linking summary financial-statement rows to the rows of a referenced footnote, at row
level, inside a scanned Turkish KAP audit filing (Özak GYO, 31.12.2012, 95 pages, no text
layer).

This repository holds two things:

| Folder | What it is | Status |
|---|---|---|
| [`v0/`](v0/) | The submitted case artifact. The staged pipeline, its configs, evaluation scripts, unit tests, emitted outputs and the graded README. | Sealed. Content is byte-identical to what was delivered; only its folder name changed when this repository was reorganised. |
| [`presentation-edition-v1/`](presentation-edition-v1/) | The layer built on top of it for a technical walkthrough: a FastAPI scenario lab, a PDF visual debugger that traces every emitted value back to its pixels, an offline presentation cockpit, plus the paper, decks, ADRs and evidence notes. | Additive. It consumes `v0/` as a library and never writes into it. |

The graded contract lives in [`v0/README.md`](v0/README.md). Read that for the full
implementation account. This page is the map, the live-demo guide and the architecture
summary.

### How to read this

| If you have | Do this |
|---|---|
| 5 minutes | Section 1 below, then scroll through the screenshots in section 4. Nothing to install. |
| 20 minutes | Add section 2 (where each case requirement is answered) and section 5 (architecture). Open [`v0/outputs/report.html`](v0/outputs/report.html), which is the pipeline's own report of the shipped run. |
| An hour, hands on | Section 3, two commands, then drive the live demo yourself: click a value in the debugger and watch it resolve to the pixels it came from, then upload a different filing and run the unchanged pipeline on it. |
| Depth | [The paper](presentation-edition-v1/docs/paper/ftlink-paper.pdf) for the protocol and threats to validity, [the decision matrix](presentation-edition-v1/docs/decisions/decision-matrix.md) for what was rejected and why. |

---

## 1. The 90-second version

The source document is a scan. All 95 pages are images, three of the notes pages are
rotated landscape, and there is no text layer to fall back on. That single fact forces
the architecture: everything downstream has to survive OCR being wrong, and the system
is judged on whether it *notices* when it is wrong.

The pipeline is staged, not a single model call. Page detection, table extraction,
Turkish numeric normalization, candidate generation, linking, calibrated confidence and
validation are separate stages with separate failure modes, and each stage's evidence is
carried into the output rather than discarded.

Two real OCR corruptions exist in this document. Both survive into the output as *values*
and are caught as *flags*:

- `Stoklar` 2012 prints `77.543.097` and is read `77.943.097` (a 5 read as a 9, still a
  well-formed number). The second OCR engine disagrees, which caps that cell's confidence
  at 0.40, and the financial check `FIN_PARENT_SUM` localises a 400.000 overshoot.
- `Finansal Yatırımlar` 2012 prints `4.224` and is read `4,224`. Both engines read the
  same digits, so engine agreement cannot see it; only the accounting identity can, and
  it fails.

Neither value is silently corrected. The contract is zero silent errors, not zero errors.

**Results on this filing** (scope stated deliberately: these describe this document, this
hand-authored reference and these document-derived controls, not population performance):

| | |
|---|---|
| Exact reference cells | 199 / 201 (99.0 percent) |
| Reference relations | 7 / 7, precision 1.00, recall 1.00 |
| Validation checks | 103 pass / 4 fail / 6 not evaluable |
| Leave-one-out Brier (33 controls) | 0.0085 |
| Determinism | two runs on the same input are byte-identical outside the run block |
| Tests | 37 pipeline tests, all passing. 79 app tests: 76 pass, 3 skip in a clean clone because they re-derive the benchmark store from research artifacts that are not shipped here |

---

## 2. Where each case requirement is answered

The assignment sets specific requirements. This table is the shortest path from each one to
the code, the output field or the document that answers it.

| Requirement | Where it is answered |
|---|---|
| Summary tables on the configured pages, with title, headers, footnote references, periods, values and main-item / sub-item / total hierarchy | `v0/src/ftlink/table_structure.py` and `normalize.py`; visible per row in the debugger's Extracted view; in the output as `tables[]` (title, page, periods), `rows[]` (`role`, `indent_level`, `parent_row_id`, `dipnot_refs`) and `cells[]` (`period_id`, `value`) |
| Number grammar: parentheses mean negative, dot is the thousands separator, and dash, empty and zero are three distinct states | `v0/src/ftlink/normalize.py`; guarded by `FMT_THREE_STATE` at type level and by `v0/tests/test_normalize.py` |
| Find the items that reference the configured footnote, locate that footnote's page automatically, parse its tables | `v0/src/ftlink/locate.py`: table-of-contents parse, printed-to-PDF folio offset, heading verification, bounded scan fallback. One footnote serving items from several summary tables is the normal case here, not a special one |
| Page range and footnote number must come from configuration, never from code | `v0/configs/default.yaml`. Proven three ways: `configs/alt_footnote.yaml` retargets footnote 12 with no code change, the scenario lab ships `footnote-10`, `footnote-12` and `footnote-13` runs, and the debugger's Configure / upload / run accepts a different PDF with its own page range |
| An NLP or ML component must do inference in the linking stage; exact string matching alone is insufficient by design | S6 dense retrieval with `multilingual-e5-small` and S7 reranking with `mmarco-mMiniLMv2`, both pretrained, both inference only, no training. The lexical baseline is shipped alongside precisely so its insufficiency is measured rather than asserted |
| Whole document into a single LLM call is rejected; the solution must be staged | Eleven named stages, S0 to S10, each with its own failure mode and its own evidence in the output. See the architecture table in section 5. The optional LLM tier is one call per summary item over an already-narrowed candidate set, and it is off by default |
| Confidence between 0 and 1 at table, row, cell and relation level; not constant, not random, and not the raw model score | `v0/src/ftlink/confidence.py`. Composed from OCR, parse, engine agreement, channel and reconciliation signals, then Platt-calibrated at run time on controls derived from the document itself, with a Venn-ABERS interval alongside |
| A validation stage with at least three check groups, and low-confidence records flagged in the output | `v0/src/ftlink/validation.py`: structural, format and financial groups, plus `not_evaluable` as an explicit fourth status. 113 checks on the shipped run (58 financial, 30 format, 23 structural, 2 coverage); every relation carries a `low_confidence` boolean |
| Output as JSON or JSONL with a candidate-designed schema, justified in the README | `v0/outputs/result.json`, `relations.jsonl` and `report.html`; the schema rationale is `v0/README.md` section 10 |
| At least two linking approaches compared, including where they diverge | Three approaches run on every candidate, plus an optional fourth. Every relation records per-approach scores and an agreement class. The divergence is analysed in section 5 below and in `v0/README.md` section 9 |
| At least three low-confidence or failure cases analysed: expected against produced, failing stage, cause, fix | Six cases in `v0/README.md` section 8. Two of them are reproducible in the live demo as one-click shortcuts |
| Re-runnability | `v0/eval/determinism.py`: two runs on the same input are byte-identical outside the run block. Package versions are pinned by the uv lockfile and model weights by explicit Hugging Face snapshot revisions |

---

## 3. Run the live demo

Two commands, two terminals. This is the path used in the walkthrough.

```bash
# once, from the repository root
./presentation-edition-v1/setup.sh          # checks uv + tesseract, then `uv sync`

# terminal 1: start the demo server and leave it attached
./presentation-edition-v1/run-pdf-debugger.sh

# terminal 2: open the offline presentation cockpit
./presentation-edition-v1/run.sh
```

`run-pdf-debugger.sh` serves both surfaces on `http://127.0.0.1:8199`:

- `/` the scenario lab
- `/pdf-debugger.html` the PDF visual debugger

`run.sh` opens `presentation-edition-v1/dashboard.html`, a single self-contained HTML file
with no network dependency. Its **Open live demo** button jumps to the debugger once the
server is up. The cockpit is readable on its own if you would rather not install anything.

**Prerequisites**: Python 3.11+, [uv](https://docs.astral.sh/uv/), and tesseract with the
Turkish language pack.

```bash
# macOS
brew install tesseract tesseract-lang
# Debian / Ubuntu
sudo apt install tesseract-ocr tesseract-ocr-tur
```

The first `uv sync` resolves the pipeline from `v0/` through a path dependency, and the
first pipeline run downloads two small Hugging Face models (about 950 MB, fp32). After
that, set `HF_HUB_OFFLINE=1` and the loaders refuse network access entirely and serve the
revision-pinned local snapshots.

Optional, about 14 minutes of CPU, makes every scenario open instantly instead of
computing on demand:

```bash
cd presentation-edition-v1/app && uv run ftlink-precompute
```

Sixteen completed scenarios are already committed, plus the stored abort record of the
`psm-6` scenario, so the demo works without this step.

**Container path** (authored, not smoke-tested locally: no container runtime on the
development machine):

```bash
docker compose -f presentation-edition-v1/app/compose.yaml up --build
```

**No-install path**: open [`v0/outputs/report.html`](v0/outputs/report.html) in a browser.
It is the pipeline's own self-contained visual report of the shipped run.

**Static verification**, offline, no server and no Python environment needed:

```bash
./presentation-edition-v1/verify.sh
```

---

## 4. What the demo shows

### 4.1 The presentation cockpit

Seven views over the same evidence: the thesis, the research contract, the system, the
proof, the product, the roadmap and a chronological walkthrough. Every number on it is
scoped to what actually measured it.

![Presentation cockpit, overview](presentation-edition-v1/screenshots/01-cockpit-overview.png)

The System view renders the S0 to S10 pipeline as a phase-grouped diagram. Clicking a
stage exposes its purpose, the measured signal it produces, its tech and models, its
compute cost, the config keys that drive it and its failure behaviour. The two stages
that carry an ML model expand further into that model's own architecture.

![Pipeline S0 to S10 with per-stage detail](presentation-edition-v1/screenshots/03-cockpit-pipeline-s0-s10.png)

![Stage detail panel](presentation-edition-v1/screenshots/04-cockpit-stage-detail.png)

The Proof view separates what was measured from what is claimed, and names the boundary
between the two.

![Proof view](presentation-edition-v1/screenshots/05-cockpit-proof.png)

Other views: [problem and research](presentation-edition-v1/screenshots/02-cockpit-problem-and-research.png),
[product](presentation-edition-v1/screenshots/06-cockpit-product.png),
[roadmap](presentation-edition-v1/screenshots/07-cockpit-live-flow.png),
[resource hub](presentation-edition-v1/screenshots/08-cockpit-resources.png).

### 4.2 The PDF visual debugger

The part worth spending time on. A two-panel document-analysis desk: the rendered PDF page
on the left with provenance overlays, the extracted result on the right, bound in both
directions. Click a value, the page scrolls to the pixels it came from. Click a region,
the result panel selects the object that region produced.

![Review desk with provenance overlays](presentation-edition-v1/screenshots/20-debugger-review-desk.png)

Selecting the `Stoklar` cell shows the defect in full: the raw OCR reading, the parsed
value, the confidence capped at 0.40 by second-engine disagreement, and every relation
that touches the row. The system does not hide the error and does not invent a
correction.

![Known OCR defect, digit substitution](presentation-edition-v1/screenshots/21-debugger-known-ocr-defect.png)

The Extracted view is the full row by column table for the current page: every emitted
value with its row role, hierarchy, footnote references, per-cell confidence, relations
and validation checks. Every object can focus its own provenance on the page image.

![Extracted table view](presentation-edition-v1/screenshots/23-debugger-extracted-view.png)

Run proof answers the obvious question about any demo, which is whether it is static. The
input PDF bytes, the persisted configuration, the pipeline source and the stored result
each carry a SHA-256 computed at view time from the actual files, not typed into the UI.

![Run proof](presentation-edition-v1/screenshots/25-debugger-run-proof.png)

Debug mode shows the evidence trace behind a decision: which candidate channels fired,
what each approach scored, how the confidence decomposed and which checks touched the
row.

![Evidence trace](presentation-edition-v1/screenshots/24-debugger-evidence-trace.png)

Configure / upload / run takes a different PDF, with the page range, footnote number,
extra control pages and document metadata all supplied as configuration. It runs the
unchanged sealed pipeline on it. This is the case requirement that page range and
footnote number must never be hard-coded, made operable.

![Configure, upload and run a new document](presentation-edition-v1/screenshots/27-debugger-configure-upload-run.png)

Also available: [JSON view](presentation-edition-v1/screenshots/26-debugger-json-view.png),
[separator-corruption case](presentation-edition-v1/screenshots/22-debugger-separator-defect.png),
[case guide](presentation-edition-v1/screenshots/28-debugger-case-guide.png).

### 4.3 The scenario lab

Eighteen scenarios, each a configuration diff over the shipped `configs/default.yaml`. No
code changes anywhere. The point is that the alternatives are not described, they are
runnable.

![Scenario lab home](presentation-edition-v1/screenshots/10-scenario-lab-home.png)

The divergence matrix puts every scenario in one table with its headline metrics and how
far it moved from the baseline.

![Scenario divergence matrix](presentation-edition-v1/screenshots/11-scenario-divergence-matrix.png)

A/B comparison diffs two stored runs on the pipeline's deterministic semantic identifiers:
relations present in both or only one, confidence deltas, agreement-class changes,
validation-check flips and cell-level value differences.

![A/B comparison](presentation-edition-v1/screenshots/14-ab-comparison.png)

The review queue orders relations by review priority (flagged first, then widest
Venn-ABERS interval, then lowest confidence) and prices the threshold: given a cost of
review and a cost of a miss, `p* = 1 - c_review / c_miss` decides what to review, and the
panel shows expected cost against review-everything and review-nothing.

![Review queue and expected-cost thresholds](presentation-edition-v1/screenshots/13-review-queue-and-thresholds.png)

The stage walkthrough reconstructs S2 to S10 from the stored `result.json` alone, so what
it shows is what was actually emitted.

![Stage walkthrough](presentation-edition-v1/screenshots/12-stage-walkthrough.png)

The benchmark store is every comparison measured in the project, one JSON file each,
grouped by scope, with the shipped row highlighted and each row carrying the path its
numbers came from. Nothing is recomputed in the app.

![Benchmark store](presentation-edition-v1/screenshots/15-benchmark-store.png)

The decision matrix records what was selected, what was measured and rejected, and what is
still queued, per stage.

![Decision matrix](presentation-edition-v1/screenshots/16-decision-matrix.png)

---

## 5. Architecture

Single-call whole-document conversion is rejected by design and by the task. The stages,
with the technology that implements each:

| Stage | What it does | Implementation | Failure behaviour |
|---|---|---|---|
| S0 config | Freezes scope as data: PDF path, summary page range, footnote number, control pages, metadata | YAML plus Pydantic validation | Invalid scope fails at the boundary |
| S1 render + OCR | 300 dpi grayscale render, word boxes with confidences, orientation recovery for rotated pages | PyMuPDF, tesseract 5.x `tur`, TSV output | Page-level abort with an explicit reason |
| S1b verify | Every numeric cell crop re-read by a second engine; digit disagreement caps the cell confidence | RapidOCR (PP-OCRv6-small, ONNX) | Flag over fix: values are never silently replaced |
| S2 page checks | The configured range is verified, not trusted: a page with no coherent financial table fails `STR_SUMMARY_RANGE` | Deterministic checks | Misconfiguration fails loudly, with named pages |
| S3 structure | Column and row reconstruction without ruling lines | Deterministic x-clustering over word boxes. No ML, no GPU | Degenerate clusters surface as failing structural checks |
| S3b percent rescue | Rate rows re-read per cell with the engines swapped, because tesseract cannot read the percent glyph on this scan class (measured 0 of 6) while RapidOCR reads all six | Engine role swap | `FMT_PERCENT_BOUNDS` guards the class |
| S4 grammar | Turkish numeric grammar, three-state cells (dash, empty, zero as distinct states), label cleanup, row roles | Deterministic parser | Unparseable cells become explicit, never zero |
| S5 locate | Finds the configured footnote: table-of-contents parse, printed-to-PDF folio offset, heading verification, bounded scan fallback | Deterministic, with OCR-damage countermeasures | A footnote that cannot be located aborts with exit code 2 |
| S6 candidates | Four channels fused by weighted Reciprocal Rank Fusion, `rrf_k = 10`, `top_k = 8` | char_wb 2-4 TF-IDF cosine; rapidfuzz token-set ratio; `intfloat/multilingual-e5-small` bi-encoder (118M, 12 layers, hidden 384) with `query:` prefix; a period-scoped value anchor at `anchor_weight = 3.0` | An empty candidate pool for a referencing row fails `REL_COVERAGE` |
| S7 link | Three approaches run on every candidate and are compared, plus an optional fourth | A: `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` (118M), `accept_threshold = 0.5`, `rank1_min_score = 0.2`. B: value plus role rules, five deterministic label rules, no ML. C: lexical baseline at 0.75, the deliberately insufficient control. D: optional LLM selector, off by default | Every relation records per-approach scores and an agreement class |
| S8 confidence | Cell, row, table and relation confidence, calibrated on controls derived from the document itself | Platt scaling with target smoothing, plus Venn-ABERS interval; fitted on 33 controls (11 positive, 22 negative) | Fallback calibration is declared in the output when controls are too few |
| S9 validate | Structural, format and financial check groups, with `not_evaluable` as an explicit fourth status | Named checks, each pointing at the rows it inspected | A check that cannot be evaluated never silently passes |
| S10 emit | `result.json`, `relations.jsonl`, `report.html`, deterministic semantic identifiers | Stable IDs derived from page, table, row and column | Two runs on the same input are byte-identical outside the run block |

Model pinning uses two independent layers, because they pin different things: the uv
lockfile pins package versions, and model weights are pinned to explicit Hugging Face
snapshot revisions in the config and passed to every loader, so a re-published model card
cannot change what a fresh machine downloads.

- dense: `intfloat/multilingual-e5-small` at revision `614241f622f53c4eeff9890bdc4f31cfecc418b3`
- cross-encoder: `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` at revision `1427fd652930e4ba29e8149678df786c240d8825`

Inference is CPU, fp32, no sampling anywhere. Both are deterministic forward passes.
Cross-encoder cost is single-digit milliseconds per pair on CPU. A full run is about 27 to
32 seconds warm on Apple Silicon; a duration is never quoted without its platform, and
every run's `meta.json` records `platform.platform()`, the tesseract version and whether
the model cache was warm.

### Why two link mechanisms

The linking problem has two distinct physics in this document.

*Reconciliation links* bind a balance-sheet carrying amount to an opening, closing or
total row whose printed label is a date and a role, not an item name. Text similarity
under-accepts these, and value plus role rules carry them.

*Item-semantic links* bind an income-statement item to a named movement row whose wording
differs substantially. The hardest pair in this filing, `Yatırım Amaçlı Gayrimenkul
Değerleme Farkları` against `Makul değer değişikliğinden kaynaklanan kazanç`, scores a
token-set ratio of about 0.40 against a 0.75 lexical bar while both other approaches link
it confidently. That pair is the reason a semantic component is required at all.

No single signal solves both. The divergence between approaches is therefore systematic
and explainable, not noise: five relations are `b_only` and cluster exactly on the
reconciliation physics, two are `consensus`, and the lexical baseline accepts nothing.
Lowering the lexical bar to 0.4 admits three false links, precision drops to 0.70, and all
three arrive with calibrated confidences between 0.044 and 0.048 and the low-confidence
flag. Word matching does not merely underperform here; it injects garbage the moment it is
loosened, and the calibration layer prices that garbage correctly.

### Confidence is not a model score

Confidence is composed, then calibrated, and it is a review-priority signal rather than a
population probability guarantee.

- Cell confidence starts from OCR word confidence times parse confidence, is boosted by
  1.05 (capped at 1.0) on second-engine agreement, capped at 0.40 on disagreement, and
  set to 0.7 or 0.5 when repaired.
- Row confidence is the mean cell confidence with a minimum-driven penalty.
- Relation confidence fuses the per-approach signals and the value reconciliation, then
  passes through Platt scaling with target smoothing, fitted at run time on control
  samples derived from the document itself. The cash-flow statement also references the
  configured footnote, so its rows serve as additional calibration controls and are never
  emitted as relations.
- A Venn-ABERS interval accompanies the point estimate, so the width of the uncertainty is
  visible and not just its centre.

Platt was chosen over isotonic on evidence, not taste: the literature crossover for small
N is reproduced on the 33 controls here. Leave-one-out Brier is 0.0085.

---

## 6. Documents

Everything below is in the repository, no external links required.

| Document | Where |
|---|---|
| The graded implementation README | [`v0/README.md`](v0/README.md) |
| Research paper: protocol, experiments, threats to validity, reproducibility | [`presentation-edition-v1/docs/paper/ftlink-paper.pdf`](presentation-edition-v1/docs/paper/ftlink-paper.pdf) ([HTML](presentation-edition-v1/docs/paper/ftlink-paper.html), [Markdown](presentation-edition-v1/docs/paper/ftlink-paper.md)) |
| Walkthrough deck | [`presentation-edition-v1/docs/deck/deck.pdf`](presentation-edition-v1/docs/deck/deck.pdf) ([HTML](presentation-edition-v1/docs/deck/deck.html)) |
| Two-page handout | [`presentation-edition-v1/docs/deck/handout.pdf`](presentation-edition-v1/docs/deck/handout.pdf) |
| Methods inventory: shipped, measured, rejected, queued | [`presentation-edition-v1/docs/methods/methods.pdf`](presentation-edition-v1/docs/methods/methods.pdf) ([HTML](presentation-edition-v1/docs/methods/methods.html)) |
| Decision matrix: options per stage with evidence state | [`presentation-edition-v1/docs/decisions/decision-matrix.md`](presentation-edition-v1/docs/decisions/decision-matrix.md) |
| ADR 01: extraction stack | [`presentation-edition-v1/docs/decisions/adr-01-extraction-stack.md`](presentation-edition-v1/docs/decisions/adr-01-extraction-stack.md) |
| ADR 02: linker line-up | [`presentation-edition-v1/docs/decisions/adr-02-linker-lineup.md`](presentation-edition-v1/docs/decisions/adr-02-linker-lineup.md) |
| ADR 03: confidence decomposition | [`presentation-edition-v1/docs/decisions/adr-03-confidence-decomposition.md`](presentation-edition-v1/docs/decisions/adr-03-confidence-decomposition.md) |
| Evidence: OCR engine bake-off | [`presentation-edition-v1/docs/evidence/ocr-bakeoff-run08.md`](presentation-edition-v1/docs/evidence/ocr-bakeoff-run08.md) |
| Evidence: table-structure bake-off | [`presentation-edition-v1/docs/evidence/structure-bakeoff-run06.md`](presentation-edition-v1/docs/evidence/structure-bakeoff-run06.md) |
| Evidence: the percent-rescue measurement | [`presentation-edition-v1/docs/evidence/percent-rescue.md`](presentation-edition-v1/docs/evidence/percent-rescue.md) |
| Research playbook: the trade-off cards | [`presentation-edition-v1/docs/RESEARCH-PLAYBOOK.md`](presentation-edition-v1/docs/RESEARCH-PLAYBOOK.md) |
| PDF debugger design brief, written before the implementation | [`presentation-edition-v1/docs/PDF-DEBUGGER-DESIGN-BRIEF.md`](presentation-edition-v1/docs/PDF-DEBUGGER-DESIGN-BRIEF.md) |
| Source PDF page map, all 95 pages | [`presentation-edition-v1/docs/SOURCE-PDF-PAGE-GUIDE.md`](presentation-edition-v1/docs/SOURCE-PDF-PAGE-GUIDE.md) |
| How the hand-authored reference was built and audited | [`presentation-edition-v1/docs/GROUND-TRUTH-AUTHORING-GUIDE.md`](presentation-edition-v1/docs/GROUND-TRUTH-AUTHORING-GUIDE.md) |
| Scenario lab API and internals | [`presentation-edition-v1/app/README.md`](presentation-edition-v1/app/README.md) |

`presentation-edition-v1/rendered-docs/` holds pre-rendered HTML of the Markdown documents
so the offline cockpit can preview them over `file://`, where browsers block fetch to
sibling files. Regenerate with `python3 presentation-edition-v1/render-docs.py`.

---

## 7. Repository map

```
.
├── v0/                                  the submitted artifact, sealed
│   ├── README.md                        the graded implementation account
│   ├── configs/default.yaml             page range, footnote number, thresholds, model revisions
│   ├── configs/alt_footnote.yaml        the same pipeline aimed at footnote 12
│   ├── data/ozak_gyo_2012.pdf           the source filing
│   ├── src/ftlink/                      the pipeline: ocr, table_structure, normalize,
│   │                                    percent, locate, candidates, linking, confidence,
│   │                                    validation, verify, report, pipeline, cli
│   ├── eval/                            scorer, ablation, mutation harness, determinism,
│   │                                    leave-one-out calibration, reference cells
│   ├── tests/                           37 unit tests
│   ├── outputs/                         the shipped run: result.json, relations.jsonl, report.html
│   └── outputs_footnote12/              the config-only footnote 12 run
│
└── presentation-edition-v1/
    ├── dashboard.html                   the offline presentation cockpit
    ├── setup.sh run-pdf-debugger.sh run.sh verify.sh
    ├── app/                             the scenario lab and PDF debugger
    │   ├── src/ftlink_app/              FastAPI, registry, runner, documents, compare,
    │   │                                triage, walkthrough, benchmarks, pdf_debugger
    │   ├── frontend/                    single-file UI, no CDN, fully offline
    │   ├── runs/                        16 precomputed scenarios + 1 stored abort record
    │   ├── benchmarks/                  every measured comparison, one JSON each
    │   ├── fixtures/                    the source filing and a second public filing
    │   ├── tests/                       79 tests (76 pass, 3 skip without the research artifacts)
    │   └── Dockerfile compose.yaml
    ├── docs/                            paper, decks, ADRs, evidence notes, guides
    ├── rendered-docs/                   pre-rendered HTML for offline preview
    ├── screenshots/                     the images used on this page
    └── verification/                    real-browser click-through scripts (CDP)
```

---

## 8. Reproducing the numbers

```bash
cd v0
uv sync --frozen
uv run ftlink run --config configs/default.yaml      # the shipped run
uv run pytest -q                                     # 37 tests
uv run python eval/score.py                          # 199/201 cells, P=R=1.00
uv run python eval/determinism.py                    # two runs, byte-diff outside the run block
uv run python eval/calibration_loo.py                # leave-one-out Brier and Venn-ABERS
uv run python eval/ablation.py                       # paired ablation with an exact McNemar test
uv run python eval/mutations.py                      # named injected failures and their catchers
uv run ftlink run --config configs/alt_footnote.yaml # footnote 12, rotated pages, config only
```

```bash
cd presentation-edition-v1/app
uv run pytest -q                                     # 79 tests: 76 pass, 3 skip (see below)
./demo_preflight.sh                                  # hits every endpoint the demo uses, exits 1 on a mismatch
```

The three skipped app tests are `test_benchmarks.py`'s sync checks. They rebuild the
benchmark store from the raw research artifacts that produced it, and those artifacts are
not shipped in this repository, so the tests skip rather than pretend to pass. Every
committed benchmark file is still validated by the tests that do run.

Config generality was exercised on footnotes 10, 12 and 13 of the same filing with zero
code changes, and the sealed pipeline was run unchanged on three other public audit
reports with only the configuration changed. The results of that second-document work,
including one loud failure on a different auditor's heading convention (`DİPNOT n` instead
of `NOT n`, exit code 2), are in the benchmark store and the paper.

---

## 9. What this does not claim

Stating the boundary is part of the work.

- Every headline accuracy or calibration number above describes **this filing**, **this
  hand-authored reference**, or **these document-derived controls**. None of them is a
  population performance estimate. One strong filing is case evidence, not a benchmark.
- The reference set is independently authored and audited here, not supplied with the
  case. How it was built and checked is documented in the ground-truth authoring guide.
- Confidence is a review-priority signal. It orders what a human should look at first. It
  is not a guarantee of correctness probability on an unseen document.
- The locator, the table grammar and the evaluation evidence target Turkish KAP-style
  financial filings. A different layout may produce a review-heavy or failed run, and that
  outcome is meant to stay visible rather than be smoothed over.
- The container image is authored but has not been built and smoke-tested locally.
- The scenario lab is a walkthrough asset, not a production service. Reviewer labels
  captured in its UI are stored separately and never feed or retrain the pipeline.
- The optional LLM linking tier is off by default and was not used to produce any shipped
  number.

---

## 10. How this was built

The pipeline, the app and the documents in this repository were produced with heavy use of
AI coding assistants, under review, with the measurements run and checked rather than
asserted. Every number on this page and in the paper is traceable to a stored artifact:
`v0/outputs/result.json`, a scenario `meta.json`, an evaluation script's output or a
benchmark JSON that names the file its numbers came from. Where something was measured
once, on one machine, with one document, the text says so.
