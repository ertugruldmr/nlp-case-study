# Benchmark store schema

> Every `source` field in this store is a path into the author's private research tree
> (`research/...`, `evidence/...`). Those artifacts are not shipped with this repository.
> The paths are kept rather than stripped so each number stays attributable to the run that
> produced it; the notes that carry an argument rather than just a number are included under
> `presentation-edition-v1/docs/evidence/`.

One JSON file per measured comparison, file name `<id>.json`, `id` equal to the file stem.
Every file is validated by `ftlink_app.benchmarks.Benchmark` (pydantic) when the API reads it;
a file that fails validation breaks `GET /api/benchmarks`, so run `make test` after adding one.
Files are produced by `uv run ftlink-benchmarks-sync` from the research artifacts, or dropped
in by hand (Colab bake-off results). The API never writes here. `ftlink-benchmarks-sync --check`
re-derives every generated file and exits 1 if a committed one differs, so drift is detectable;
hand-dropped ids are not produced by a converter and are left alone by both modes.

```json
{
  "id": "kebab-case, equals the file stem",
  "title_tr": "Turkish title shown in the tab",
  "title_en": "English title (subtitle)",
  "measured_at": "ISO 8601 datetime, when the measurement was taken (source mtime or the note's verified stamp)",
  "source": "path of the evidence note or artifact, relative to the workspace root",
  "scope": "this document | other documents | offline refit | colab",
  "baseline": "row id the other rows are compared against, or null when no shipped row exists",
  "columns": [
    {"key": "snake_case, unique, not one of id/label/role/source", "label_tr": "column header", "kind": "text | number | pct | seconds | bool"}
  ],
  "rows": [
    {"id": "unique within the file", "label": "row header", "role": "shipped | measured | pending | rejected",
     "source": "where this row's numbers come from (path, relative to the workspace root)",
     "<column key>": "value typed by the column kind; null = not measured / not applicable"}
  ],
  "notes_tr": ["free-text notes shown under the table", "parse_error: <what could not be read>"],
  "decision_rule": "the sentence that says what the table decides and why the shipped option stays"
}
```

Rules
- `kind` typing per cell: `number`, `pct`, `seconds` are JSON numbers (pct as 0-100, seconds as float);
  `bool` is a JSON boolean; `text` is a string. `null` is allowed everywhere and renders as "-".
- `role`: `shipped` = the sealed 1.0.2 configuration (highlighted in the tab); `measured` = an
  alternative that was run; `pending` = planned, no numbers yet; `rejected` = did not run or has no
  finite result (state the reason in a text column or a note).
- Every row carries its own `source`, so a table can mix rows from different artifacts (for example
  the shipped row from `app/runs/baseline/` next to research-side rows).
- A note starting with `parse_error:` means the sync could not read a source; the table is then
  incomplete on purpose (no invented values). The tab shows these notes in red.
- Scopes other than `this document` are research-side measurements: the tab prints
  "araştırma tarafı; teslimat 1.0.2 değişmedi" above them.
- Sanitization applies: no employer, tenant, personal or absolute local paths in any string
  (`tests/test_sanitization.py` scans this folder).

Colab drop-in: convert a run-06/07/08 result into this shape (one file per bake-off, `scope: "colab"`,
`measured_at` = the Colab run's timestamp, `source` = the notebook or result path) either by hand
or by adding a converter function to `src/ftlink_app/benchmarks_sync.py` and listing it in
`CONVERTERS`. The tab needs no code change.
