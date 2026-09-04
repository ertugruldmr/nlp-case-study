# ftlink scenario lab V1 package

This bundle contains the scenario-lab app, its precomputed scenario fixtures, the PDF visual debugger, the debugger's 2.4 MB known-good PDF fixture, and the sealed pipeline source/output needed by the app's path dependency. It is an additive presentation/demo bundle, not a replacement for the submitted pipeline artifact.

Included:

- `app/frontend/index.html` with the `PDF visual debugger` launcher.
- `app/frontend/pdf-debugger.html` and `pdf-debugger-enhancements.js`.
- `app/src/ftlink_app/pdf_debugger.py` and debugger API routes.
- `app/fixtures/ozak_gyo_2012.pdf`.
- `app/fixtures/ozak_gyo_2013.pdf`, `app/demo_alternate_pdf.sh` and
  `app/ALTERNATE-PDF-DEMO.md` for a genuinely different-PDF binding smoke.
- Existing scenario runs, benchmark store, app tests and launch configuration.
- `v0/` source, configuration, tests and canonical outputs as the app dependency.

Excluded deliberately:

- `.venv/`, caches (including rendered debugger pages), `__pycache__`, `.git/`, workspace research/private notes, email drafts, temporary files, uploaded ad-hoc documents, `doc-*` run outputs, and reviewer annotation/label state.

From the extracted bundle root:

```bash
cd app
uv sync --frozen
uv run pytest -q
uv run uvicorn ftlink_app.api:app --host 127.0.0.1 --port 8199
```

Open `http://127.0.0.1:8199/`, then choose `PDF visual debugger`. The debugger reads the bundled sibling `v0/outputs/result.json` and renders its bundled fixture PDF. Uploaded-document runs remain opt-in and write only under `app/runs/`; the alternate smoke uses the bundled 2013 fixture when present.
