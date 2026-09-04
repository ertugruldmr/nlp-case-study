# Ground-truth authoring and adjudication guide

This is the protocol for producing independent evidence against which the extractor can be evaluated. The current repository contains a useful reference set, but it must not be presented as employer-provided truth. A result copied from the model or corrected while looking at model predictions is an annotation, not independent gold.

## 1. Freeze the annotation unit

Before transcription, record:

- source PDF SHA-256, page count and file name;
- PDF page number and printed page number;
- 300-DPI rendered-image dimensions and any applied rotation;
- configuration contract: summary-page range, target note number and control pages;
- annotation-schema version and annotator/adjudicator IDs.

For the supplied case, the authoritative unit is PDF pages 5–7 plus Note 11 on PDF pages 53–54. Pages 9–10 can be a separately named extension. “All pages” must be a separately versioned dataset because it introduces narrative pages and different table families.

## 2. Annotate six layers independently

### A. Page and table regions

For every in-scope table record `table_id`, title, statement type, page, `[x0,y0,x1,y1]` in the frozen OCR coordinate space, and confidence only if confidence itself is being labelled. A box encloses the complete logical table, not merely numeric columns.

### B. Column/period contract

For every value column record a stable `period_id`, exact visible header, semantic kind, currency/unit and date interpretation. Do not call every `2012` cell the same period: opening balance, closing balance, current-year flow, comparative closing and note-specific columns are different semantic periods.

### C. Rows and hierarchy

Record exact visible label, normalized label, role, indentation level, parent row, note references, asterisk/marker text and row box. Roles should come from a closed set such as `group_header`, `item`, `subitem`, `subtotal`, `total` and `memo`.

Hierarchy decision rules:

1. typography and left indentation are primary evidence;
2. subtotal lines and arithmetic are supporting evidence, not a substitute for layout;
3. repeated labels in different sections receive different row IDs;
4. do not infer a parent solely because the current system predicted one;
5. if hierarchy is genuinely ambiguous, mark `needs_adjudication` instead of silently choosing.

### D. Logical cells

Create the complete row × period grid, including visually empty positions. Each cell must distinguish:

- `number`: a printed numeric value;
- `zero`: an explicit zero;
- `dash`: a printed dash/no-value mark;
- `empty`: no printed value in the logical position;
- `unreadable`: evidence exists but cannot be transcribed reliably.

Store raw text, normalized decimal value, sign/parentheses, repaired flag, cell box and source token IDs. Missing/empty cells are required gold objects; otherwise a system can omit difficult cells without penalty.

### E. Summary-to-footnote relations

Author relations without viewing predicted edges. Each relation contains:

- exact source summary row;
- exact target footnote row;
- `relation_type` such as value match, reconciliation, roll-forward or narrative support;
- exact `period_scope` using the column semantics above;
- evidence values or narrative excerpt location;
- ambiguity/adjudication state.

Value equality alone is not sufficient for a relation when the same amount occurs more than once. Note reference, row meaning, period and roll-forward role must agree. One relation may cover both periods only if the footnote row genuinely supports both.

### F. Validation identities

Record each expected identity separately: operands, signs, scope, tolerance, expected status and reason. Examples are assets = liabilities + equity, subtotals, cash roll-forwards and Note 11 opening + flows = closing. `not_evaluable` is not the same as `fail`.

## 3. Two-pass transcription and adjudication

1. Annotator A transcribes from the rendered PDF with predictions hidden.
2. Annotator B independently transcribes the same pilot pages with predictions hidden.
3. Compare object counts, labels, hierarchy, cell states/values/boxes, period semantics and relations.
4. An adjudicator resolves every disagreement while viewing the source PDF, never by majority vote with a model output.
5. Freeze the adjudicated file; only then run the extractor and scorer.
6. Corrections create a new gold version with a changelog. Never silently edit the frozen benchmark after seeing a score.

For a time-limited case, double-annotate all pages 5–7 and 53–54. For a larger corpus, double-annotate the pilot and a statistically meaningful sample, then require targeted review for low-quality scans, rotated pages and every relation.

## 4. Minimal JSON shape

```json
{
  "schema_version": "ftlink.gold.v2",
  "document": {
    "sha256": "…",
    "page_count": 95,
    "render_dpi": 300
  },
  "scope": {
    "name": "case-contract",
    "summary_pages": [5, 7],
    "footnote_no": 11,
    "footnote_pages": [53, 54]
  },
  "tables": [
    {
      "table_id": "p05.t01",
      "page": 5,
      "bbox": [0, 0, 0, 0],
      "periods": [
        {"period_id": "closing_2012", "header_raw": "31 Aralık 2012", "kind": "closing"}
      ]
    }
  ],
  "rows": [
    {
      "row_id": "p05.t01.r000",
      "table_id": "p05.t01",
      "label_raw": "…",
      "role": "item",
      "indent_level": 0,
      "parent_row_id": null,
      "note_refs": [11],
      "bbox": [0, 0, 0, 0]
    }
  ],
  "cells": [
    {
      "cell_id": "p05.t01.r000.c00",
      "row_id": "p05.t01.r000",
      "period_id": "closing_2012",
      "state": "number",
      "raw": "1.234",
      "value": 1234,
      "bbox": [0, 0, 0, 0]
    }
  ],
  "relations": [
    {
      "relation_id": "rel.001",
      "summary_row_id": "…",
      "footnote_row_id": "…",
      "relation_type": "roll_forward",
      "period_scope": ["closing_2012"],
      "evidence": {"summary_cell_ids": ["…"], "footnote_cell_ids": ["…"]}
    }
  ],
  "checks": [],
  "adjudication": {"status": "frozen", "version": "2.0.0", "changes": []}
}
```

Coordinates in the example are placeholders and must be replaced by measured boxes. Never use placeholder zero boxes in a frozen file.

## 5. Scoring rules to freeze before evaluation

- Match tables by page and geometry/title evidence, not by copied values.
- Match rows inside an already matched table using label and geometry; values must not decide row alignment.
- Count unmatched predictions as false positives and unmatched gold objects as false negatives.
- Score the full logical cell grid, including `empty`, `dash` and `zero` as distinct states.
- Score hierarchy (`role`, `indent_level`, `parent_row_id`) separately from value accuracy.
- Score relation source, target, type and period scope separately. A correct amount with the wrong period is not a fully correct edge.
- Penalize duplicate predictions rather than allowing multiple attempts to match one gold object.
- Report rotated-page and low-quality-scan slices separately.
- Calibrate confidence against adjudicated correctness. Agreement among OCR engines is an input signal, not proof of accuracy.

Required metrics should include table/row/cell precision-recall-F1, numeric exact/tolerance accuracy, cell-state accuracy, hierarchy accuracy, relation precision-recall-F1, period/type accuracy, validation coverage and calibration error. Always publish counts beside percentages.

## 6. Known audit points for the current reference data

The existing reference set is a starting point, not a final `v2` gold set. Before claiming benchmark quality, re-audit:

- logical empty cells that may not have been emitted;
- hierarchy roles, indentation and parent links;
- period semantics beyond simple `y2012`/`y2011` labels;
- relation period scope and relation type;
- row boxes that were stored with zero horizontal width;
- two previously identified numeric discrepancies and all OCR repairs;
- any score/calibration claim derived from the same predictions being evaluated.

The debugger’s annotations are intentionally stored separately from canonical `result.json`. Export them for adjudication; do not mutate pipeline output in place.

## 7. Fast human annotation checklist

For each page, the reviewer should be able to answer yes/no:

- Is page identity and rotation correct?
- Does every table box enclose the full table?
- Are all visible row labels present exactly once?
- Is each hierarchy decision supported by layout?
- Does every row have every logical period position, including empties?
- Are dash, zero, parentheses and blank states preserved?
- Are note references and asterisks preserved?
- Does every relation point to independently verified source and target rows?
- Are type and period scope correct?
- Can another reviewer reproduce the annotation from the source alone?

If any answer is “no” or “uncertain,” the page stays unfrozen and enters adjudication.

