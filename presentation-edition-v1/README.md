# Presentation edition v1

The walkthrough layer over the sealed case pipeline in [`../v0`](../v0). It adds a live
demo, a visual debugger, an offline presentation cockpit and the written record (paper,
decks, ADRs, evidence notes). It consumes `../v0` strictly as a library and never writes
into it.

Start at the [repository README](../README.md) for the architecture summary and the
annotated screenshots. This page is the operating manual.

## Run it

```bash
# once
./setup.sh                    # checks uv + tesseract, then `uv sync` inside app/

# terminal 1, stays attached
./run-pdf-debugger.sh         # http://127.0.0.1:8199

# terminal 2
./run.sh                      # opens dashboard.html
```

One server serves both surfaces:

| URL | Surface |
|---|---|
| `http://127.0.0.1:8199/` | scenario lab: 18 switchable configurations, matrix, A/B, triage, benchmarks |
| `http://127.0.0.1:8199/pdf-debugger.html` | PDF visual debugger: provenance overlays, extracted view, run proof, upload and run |

Helpers: `open-app.sh`, `open-pdf-debugger.sh`, `run-scenario-lab.sh` (an alias of
`run-pdf-debugger.sh`). A non-default port works if you set the same value on both sides:

```bash
FTLINK_APP_PORT=8299 ./run-pdf-debugger.sh
FTLINK_APP_PORT=8299 ./open-app.sh
```

`dashboard.html` needs no server and no network. Opening it directly is a valid way to
read the case; only its **Open live demo** button requires the server.

Run `app/demo_preflight.sh` before presenting. It starts the server if needed, hits every
endpoint the walkthrough touches, prints the numbers, and exits non-zero on any mismatch.

## The cockpit

`dashboard.html` is a single self-contained page with seven views:

1. **Overview** the thesis, the verified snapshot, and the three observations that forced
   the architecture.
2. **Problem and research** the contract, the six subproblems, the hypothesis ledger and
   the applied-research lifecycle.
3. **System** the S0 to S10 pipeline as a clickable diagram, the data / evidence / trust
   bindings, and an interactive decision matrix. Stages carrying an ML model expand into
   that model's own architecture.
4. **Proof** the two real OCR defects, the evaluation methodology, and the claim
   boundaries.
5. **Product** the frontend, the FastAPI backend, the sealed AI core, the API routes and
   the live-demo handoff.
6. **Evolution** V1 shipped against V2 and V3 proposed, and the human-correction loop.
7. **Live flow** an interruption-safe chronological walkthrough with expandable technical
   probes.

Hash routes reopen a view directly: `dashboard.html#system`, `dashboard.html#proof`.

The **Resources** button previews the emitted report, the deck, the handout, the methods
deck, the paper and the rendered design documents inside the page.

## Scope and evidence rules

These hold everywhere in this folder and are worth restating because they are easy to
overstate in a live conversation.

- `199/201`, `7/7`, `103/4/6` and the calibration figures are scoped to this filing, this
  hand-authored reference, or these document-derived controls. They are not population
  performance.
- Confidence is a review-priority signal, not a probability guarantee on unseen documents.
- The two known OCR defects stay visible and are never silently corrected.
- V1 is shipped. V2 and V3 are proposed, not shipped.
- The scenario lab is a measured walkthrough asset, not a production service.
- Reviewer labels captured in the UI are stored separately and never feed or retrain the
  pipeline.

## Layout

```
presentation-edition-v1/
├── dashboard.html            offline presentation cockpit, no network dependency
├── setup.sh                  prerequisite check plus `uv sync`
├── run-pdf-debugger.sh       start the demo server (also: run-scenario-lab.sh)
├── run.sh                    open the cockpit
├── open-app.sh open-pdf-debugger.sh
├── verify.sh                 static checks: cockpit parses, links resolve, no leaked paths
├── render-docs.py            rebuild rendered-docs/ from docs/  (`--check` to detect drift)
├── app/                      the scenario lab and the debugger (see app/README.md)
├── docs/                     paper, decks, ADRs, evidence notes, guides
├── rendered-docs/            pre-rendered HTML of docs/, for file:// preview
├── screenshots/              the images used in the repository README
├── vendor/mermaid.min.js     vendored, so the diagrams work offline
└── verification/             real-browser click-through scripts driven over CDP
```

## Verification

```bash
./verify.sh
```

Offline, no server, no Python environment required. It checks that the cockpit's inline
script parses, that every local asset it can navigate to exists, that no machine-local
absolute path or private rehearsal material leaked into the repository, that the app
resolves the pipeline from `../../v0`, that every shell entry point parses, and that
`rendered-docs/` is not stale.

Deeper, with a real browser: `verification/browser-clickthrough-baseline.mjs` and
`verification/browser-clickthrough-upload.mjs` drive an already-running Chrome over the
DevTools protocol (default `http://127.0.0.1:9223`) against a running demo server, exercise
the debugger end to end and write screenshots.

```bash
# Chrome must already be running with --remote-debugging-port=9223
node verification/browser-clickthrough-baseline.mjs
```

## Notes

- `app/runs/` ships 16 precomputed scenarios so the demo opens instantly. The `psm-6`
  scenario is stored in its `error` state on purpose: it is the honest record of a
  configuration that aborts loudly rather than emitting noise.
- The precomputed `result.json` files carry relative paths in their configuration echo, to
  match the sealed artifact and to keep no machine's directory layout in the repository. A
  run you execute locally will legitimately write your own absolute paths back into
  `config_echo`. That is the pipeline echoing what it was given.
- `runs/_documents/`, `runs/_debugger/` and `runs/_labels/` are runtime caches for uploaded
  PDFs, rendered page images and reviewer labels. They are not committed and regenerate on
  demand.
