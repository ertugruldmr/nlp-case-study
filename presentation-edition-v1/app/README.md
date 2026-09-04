# ftlink scenario lab

A demo layer over the submitted `ftlink` pipeline (`../deliverable`) that makes
every design alternative a **switchable, runnable, comparable configuration**.
Built as a defense asset: "we did not just pick approach X, here are the others,
live, and here is exactly where they diverge."

The deliverable is consumed strictly as a library. Nothing here writes into the
deliverable tree; every scenario output lands under `app/runs/<scenario>/`.

## What it shows

- **18 scenarios**, each a config diff over the shipped `configs/default.yaml`:
  baseline, strict/lenient acceptance thresholds, lenient-lexical bar, RRF k=60,
  OCR at 400 dpi, OCR psm 6, narrow candidate beam, dense-model swap, cross-encoder
  swap to the Turkish-trained `ytu-ce-cosmos/modernbert-tr-reranker` (revision-pinned),
  percent-rescue ablation, digit-cross-check ablation, value-anchor-channel
  ablation, calibration-controls ablation, footnotes 10, 12 and 13 (config
  generality), and the LLM linker tier (needs an OpenAI-compatible endpoint;
  disabled in the graded submission on purpose).
- **Per-scenario scoreboard**: table/row/cell/relation counts, validation check
  counts, calibration mode, and (where the gold set applies) cell accuracy and
  relation P/R computed by the deliverable's own scorer.
- **A/B comparison**: relations present in both / only A / only B, confidence
  deltas, agreement and low-confidence flag changes, validation-check status
  flips, and cell-level value differences. Identity across runs rides on the
  pipeline's deterministic semantic IDs, i.e. the re-runnability design claim.
- **Live runs**: any scenario re-executes on demand (~1-2 min CPU) next to the
  precomputed results. Every `meta.json` carries a platform stamp (`platform.platform()`,
  tesseract version, warm/cold model cache) and the cards show it next to the wall time, so a
  duration is never quoted without its platform.

## Run it

```bash
cd app
make setup        # uv sync (path dependency on ../deliverable)
make precompute   # one-time: executes the 17 precomputable scenarios (~14 min CPU; the reranker swap downloads a 600 MB model once)
make serve        # http://127.0.0.1:8199
make test         # 63 tests (walkthrough, triage/labels/export, decision matrix, run lock, matrix read cache, platform stamp, sanitization guard, any-document upload/run, reranker-swap registry), no pipeline execution needed
```

Requires `tesseract` + Turkish data on the host, same as the deliverable.

### Docker (authored, not yet smoke-tested: no container runtime on the dev Mac)

```bash
# from the folder that contains app/ and deliverable/ (the build context needs both)
docker compose -f app/compose.yaml up --build
```

## Demo preflight

`./demo_preflight.sh` starts the server if needed, hits every endpoint the defense demo uses
(scenarios, walkthrough, triage at 1/20 and 1/5, footnote-12 walkthrough, matrix, decision
matrix asset, frontend buttons), prints the headline numbers, and exits 1 on any mismatch.
Run it an hour before the call.

## Yapılandırılabilir KAP-tarzı belge (run the sealed pipeline on a compatible PDF)

The "Belge yükle" tab uploads a PDF (max 60 MB) with the values the case requires to come from
configuration: summary page range, footnote number, optional extra control pages, display label,
legal company name, reporting period, currency and OCR language. The upload becomes an ad-hoc
scenario `doc-<doc_id>` (doc_id = first 12 hex of the
file's sha256) that runs through the same runner and lock as the registry scenarios. **The
pipeline is unchanged; only the configuration differs** (`document.pdf_path`,
`document.summary_pages`, `document.footnote_no`, document metadata, `ocr.lang`, and
`confidence.extra_control_pages`). Uploads live under `runs/_documents/<doc_id>/` (`source.pdf`
+ `doc.json`), outputs under `runs/doc-<doc_id>/`; Rapor, result.json, Aşama aşama, İnceleme
kuyruğu and Karşılaştır work on `doc-<doc_id>` like on any stored run. The gold-set scorer is not
applied (it covers the shipped document only). Nothing is written into `../deliverable`.
Validation at the boundary: PDF magic bytes (400), page range inside the page count and
`footnote_no >= 1` (422), size cap (413), one run at a time (409).

This is a configurable execution path, not a universality claim. V1's locator, table grammar and
evaluation evidence target Turkish KAP-style financial filings. A different layout may produce a
review-heavy or failed run, and that outcome must remain visible. Full-document visual review is
available for every accepted PDF; canonical extraction must use the document's actual bounded
statement range so the target-note search still has pages to inspect.

```bash
curl -s -F file=@rapor.pdf -F summary_pages_start=5 -F summary_pages_end=7 -F footnote_no=11 \
     -F extra_control_pages=9,10 -F label="Interview challenge" -F company="Şirket A.Ş." \
     -F period_end=2024-12-31 -F currency=TRY -F ocr_lang=tur \
     http://127.0.0.1:8199/api/documents
# -> {"doc_id": "...", "page_count": 95, "run_id": "doc-...", "status": {"state": "absent"}, ...}
curl -s -X POST http://127.0.0.1:8199/api/documents/<doc_id>/run      # 409 while another run is live
curl -s http://127.0.0.1:8199/api/documents/<doc_id>                  # doc.json + run state + meta.json
curl -s http://127.0.0.1:8199/api/runs/doc-<doc_id>/walkthrough       # same views as a scenario
```

A genuine alternate-document smoke is provided in [`ALTERNATE-PDF-DEMO.md`](ALTERNATE-PDF-DEMO.md)
and `demo_alternate_pdf.sh`. It runs the public Özak GYO 2013 filing through this exact
upload/API path and verifies the source hash plus effective configuration. It reports
observed output counts only; no accuracy claim is made because that filing has no
committed gold set.

**Measured smoke (29.08.2026, this flow, the shipped PDF uploaded as a file):** doc_id
`25e4afe4c27b` (95 pages, 2.5 MB), fields 5 / 7 / 11 / `9,10`, label = the company name from
`default.yaml`. Run `doc-25e4afe4c27b`: 29.3 s (macOS-15.4-arm64, tesseract 5.5.3, models warm),
7 tables, 95 rows, 193 cells, **7 relations (0 flagged)**, checks **103 pass / 4 fail / 6
not_evaluable**, calibration `fitted positives=11 negatives=22`. `GET /api/compare?a=baseline&b=doc-25e4afe4c27b`:
7 relations in both, 0 only on either side, max |Δconf| 0.0, 0 cell diffs, 0 check flips: the
upload path reproduces the precomputed baseline byte-for-byte on the semantic keys. A second
`POST .../run` while the first was live returned 409.

## Kıyaslama sekmesi (every comparison measured in this project, from a JSON store)

The "Kıyaslama" tab (button `btnBench`) renders `benchmarks/*.json`: one file per measured
comparison, grouped by scope (`this document`, `other documents`, `offline refit`, `colab`), with
the shipped 1.0.2 row highlighted, role chips (teslimat / ölçüldü / bekliyor / reddedildi), the
notes, the decision rule and every row's source path. Scopes other than `this document` carry the
header "araştırma tarafı; teslimat 1.0.2 değişmedi". Works in "Sunum" mode like the other tabs.
Nothing is recomputed in the app: the numbers are copied from the research artifacts.

- Schema: `benchmarks/SCHEMA.md` (validated by `src/ftlink_app/benchmarks.py` on every read).
- Endpoints: `GET /api/benchmarks` (id, titles, scope, measured_at, row count, baseline, shipped
  rows, parse-error count) and `GET /api/benchmarks/{id}` (the full file; 404 for an unknown id).
- Rebuild the store from the research artifacts (read-only on the sources; the shipped rows come
  from `runs/baseline/`):

```bash
uv run ftlink-benchmarks-sync            # writes benchmarks/<id>.json, one line per benchmark
uv run ftlink-benchmarks-sync --workspace ../ --out benchmarks   # explicit paths
uv run ftlink-benchmarks-sync --check    # writes nothing; exit 1 if a file no longer follows from the sources
```

The sync is idempotent: the same sources produce the same bytes, so re-running it is a no-op.
`--check` re-derives every benchmark, compares it with the committed file, prints the first
differing line of each one that drifted and exits 1. Drift means either a benchmark JSON was
hand-edited or a source artifact moved on without a re-sync; `tests/test_benchmarks.py` runs the
same check, so the store cannot silently fall behind the research artifacts.

Current store (11):

| id | scope | what it compares |
|---|---|---|
| `reranker-swap` | this document | shipped mmarco cross-encoder vs a Turkish-trained reranker, as wired and with the activation contract corrected (3 rows) |
| `tatr-detection` | this document | TATR detector vs shipped x-clustering, per page |
| `rapidocr-recognizer-variants` | this document | second-engine recognizer swaps |
| `cross-evaluation` | this document | 49 headline numbers re-derived by independent code, claimed vs recomputed |
| `second-document-generality` | other documents | sealed pipeline on three other audit reports |
| `text-layer-channel` | other documents | PDF text layer as a third per-cell channel, born-digital vs scanned |
| `locator-generalization` | other documents | footnote locator widened for a second heading convention, before and after |
| `calib-prior-variants`, `calib-weight-variants`, `calib-text-only-threshold`, `calib-prior-family` | offline refit | calibration sensitivity on the 33 captured controls |

A source that cannot be parsed produces a `parse_error:` note instead of invented values (shown in
red in the tab), and every row carries the path its numbers came from.

Colab drop-in: the run-06/07/08 bake-off results become one JSON each (`scope: "colab"`) by adding
a converter function to `src/ftlink_app/benchmarks_sync.py` and listing it in `CONVERTERS`, or by
writing the file by hand to the schema. The tab and the API need no code change.

## API

| Route | What |
|---|---|
| `POST /api/documents` (multipart) | upload a PDF + `summary_pages_start`, `summary_pages_end`, `footnote_no`, optional `extra_control_pages` (comma list), optional `label`; returns doc.json fields + run state |
| `GET /api/documents`, `GET /api/documents/{doc_id}` | uploaded documents with run state; the single view adds the run's meta.json |
| `POST /api/documents/{doc_id}/run` | run the shipped pipeline on that document as scenario `doc-<doc_id>` (same lock: 409 while a run is live) |
| `GET /api/scenarios` | registry + run status + headline metrics |
| `POST /api/runs/{id}` | execute a scenario (409 while another run is live) |
| `GET /api/runs/{id}/result` | full result.json |
| `GET /api/runs/{id}/relations` | relations enriched with row labels |
| `GET /api/runs/{id}/report` | the pipeline's own report.html |
| `GET /api/compare?a=&b=` | structured diff of two stored runs |
| `GET /api/matrix` | one row per scenario: headline metrics + divergence vs baseline (the all-scenarios defense table; UI button "Matris") |
| `GET /api/runs/{id}/triage?c_review=1&c_miss=20` | review queue (relations ordered: flagged, then widest Venn-ABERS interval, then lowest confidence; cells at or below 0.5 or repaired) + expected-cost threshold panel (p* = 1 - c_review/c_miss, review/accept sets, expected cost vs review-all/none, queue-depth curve) + reviewer labels joined; UI button "İnceleme kuyruğu". Toggle "kendi-dışı (leave-self-out)": overlays the leave-self-out Venn-ABERS intervals measured 29.08 on the baseline run (static, caption "29.08 ölçümü, canlı değil"; other scenarios show n/a because the pipeline emits only the in-sample interval) |
| `GET/POST /api/runs/{id}/labels` | reviewer labels (accept/reject/unsure + note) per relation key or cell id, stored at `runs/_labels/<id>.json`; labels never feed the pipeline. In the UI a note needs an existing label (typing a note alone never creates one) |
| `GET /api/runs/{id}/labels/export?format=csv\|jsonl&c_review=1&c_miss=20` | reviewer labels joined with the relation (row labels, pages, period), calibrated confidence, Venn-ABERS bounds, low-confidence flag, p* and the review/accept decision at that p*; cells carry the cell-queue decision. Download as CSV or JSONL |
| `GET /api/runs/{id}/walkthrough` | stage-by-stage cards S2 -> S10 (page detection, tables, normalization, candidates, linking, confidence, validation, output) derived from the stored result.json only; UI button "Aşama aşama" |

## Layout

```
app/
  pyproject.toml        uv project; ftlink consumed via path source
  src/ftlink_app/
    registry.py         the 18 scenarios + their defense stories (TR + EN)
    runner.py           default.yaml + overrides -> Settings -> ftlink run (registry or doc-<id> scenarios)
    documents.py        uploaded PDFs + per-document config -> ad-hoc doc-<id> scenarios
    store.py            read side: summaries, enriched relation views
    compare.py          A/B diff on deterministic IDs
    evalx.py            runs the deliverable's scorer in a symlink sandbox
    api.py              FastAPI + static frontend
    precompute.py       sequential batch runner
  frontend/index.html   single-file UI (TR-first), no CDN, fully offline
  runs/                 scenario outputs (precomputed); runs/_documents/<doc_id>/ uploads; runs/doc-<doc_id>/ their outputs
  tests/                registry validity, compare math, API surface
  Dockerfile, compose.yaml
```

## Positioning

This app is NOT part of the graded zip (the case explicitly grades the AI
pipeline, validation, and README; production completeness is not expected). It
exists for the defense: open the lab, flip a scenario, show the divergence table.

## PDF visual debugger

The app includes the PDF visual debugger as a first-class defense feature. From the
scenario-lab home page, choose **PDF visual debugger**, or open
`http://127.0.0.1:8199/pdf-debugger.html` directly. It renders the known-good 95-page
fixture, overlays the stored table/row/cell/relation provenance bboxes, and binds
selection to the canonical baseline result. Review, page-local Extracted, Debug and
JSON views are available, including the Stoklar digit-substitution and Financial
Investments separator-corruption narratives. JSON can switch between full-run and
current-page views and between wrapped and unwrapped text.

Completed uploaded-document runs can also be inspected. The document table exposes a
**PDF debugger** link, or use `/pdf-debugger.html?run=doc-<doc_id>#review`. The debugger
run selector lists the baseline and completed uploaded runs; PDF rendering, page count,
canonical JSON and annotations remain bound to the selected run. Uploading and executing
the pipeline can now happen in the debugger itself through **Configure / upload / run**.
That workbench exposes the authoritative case contract, an extended statement experiment,
full-document visual review and a bounded custom extraction range. It deliberately does not call
pages 1–end a valid summary-table extraction: doing so would consume the note-search region and
misrepresent covers, narrative pages and heterogeneous tables as one statement family.
It can clone the current PDF under a different configuration without collapsing two
configurations of the same file into one document ID. Long-running status is polled in the
dialog; report, pipeline-stage, triage and baseline-comparison artifacts are also available
without returning to the cockpit.

The Extracted view includes every emitted column and row×period value, plus row role,
hierarchy, references, confidence, relations and validation checks. Every object can focus
its provenance on the PDF. The side panel supports a wider split and a full-screen data
view. Overlay scaling uses the run's per-page OCR coordinate space (2481×3510 at 300 DPI
for portrait pages in the baseline) rather than a hard-coded canvas size.

The run selector also exposes completed registered experiments, not only the baseline and
uploaded PDFs. **Case guide** explains the assignment flow, configuration boundaries,
relation navigation and document-scoped ground-truth limitations. **Rotate 90°** is a
review-only per-page transformation with corresponding overlay coordinates; it never edits
canonical provenance. Invalid ranges, malformed/overlapping calibration pages, render
failures and long-running pipeline errors are shown explicitly.

Debugger API routes are `/api/debugger/runs`, `/api/debugger/run?run_id=...`,
`POST /api/debugger/configured-run`,
`/api/debugger/page/{page}?run_id=...`, `/api/debugger/canonical?run_id=...`,
`/api/debugger/annotations`, and
`/api/debugger/annotations/export?format=jsonl|csv`. The app fixture and debugger
annotations are separate from the sealed pipeline output. Upload/run continues to
use the existing document workflow and shared runner lock; reviewer labels never
retrain or alter the pipeline output.

Build the reviewable bundle with `./package.sh`. It writes
`app/dist/ftlink-scenario-lab-v1.zip`, includes sanitized precomputed runs and the
paired `deliverable/` dependency, and excludes virtual environments, caches,
uploaded documents, reviewer labels and private workspace material.

## Maintenance note: evidence slug display labels

`frontend/index.html`'s `EVIDENCE_LABELS` map (near the decision-matrix render code) translates
internal evidence-note slugs (e.g. `linux-grader-drill`) into neutral Turkish display labels for
the chips shown in the Kıyaslama/decision-matrix view, since raw slugs are workspace-internal
vocabulary that should not appear in front of a reader. Unmapped slugs fall through to a
`humanize()` prettifier, which is a safety net, not a translation: it title-cases and de-hyphenates
whatever it is given, so a new slug like `alt-probe-round` would render as "Alt Probe Round"
rather than something a reader should see. If you add a new evidence note whose slug
might appear in `decision_matrix.json`'s `evidence` arrays, add a label for it here too.
