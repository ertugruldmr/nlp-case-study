"""Output data model.

Design notes (justified in README):
- Flat, ID-referenced collections (tables / rows / cells / relations / checks), the same
  shape mature document-AI products expose; hierarchy via parent_row_id, never nesting.
- Deterministic semantic IDs (p05.t01, p05.t01.r012, ...) so two runs on the same input
  and config are byte-identical apart from the quarantined `run` block.
- Money is Decimal serialized as string, never float.
- A cell value is a discriminated union on `state`: number | dash | empty. A dash is a
  reported "no movement" marker, an empty cell is absence of any print, zero is a number.
- Every extracted record carries provenance (page, bbox in pixels at the recorded dpi,
  producing stage) and a confidence in [0, 1] that is never a raw model similarity.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Literal, Union

from pydantic import BaseModel, Field


SCHEMA_VERSION = "1.0.0"


class Provenance(BaseModel):
    page: int
    bbox: tuple[float, float, float, float] | None = None  # x0, y0, x1, y1 (pixels @ dpi)
    dpi: int | None = None
    stage: str


class NumberValue(BaseModel):
    state: Literal["number"] = "number"
    raw: str
    value: Decimal
    kind: Literal["int", "decimal", "percent", "percent_range"] = "int"
    value_high: Decimal | None = None  # for percent_range
    repaired: bool = False


class DashValue(BaseModel):
    state: Literal["dash"] = "dash"
    raw: str = "-"


class EmptyValue(BaseModel):
    state: Literal["empty"] = "empty"


CellValue = Union[NumberValue, DashValue, EmptyValue]


class Cell(BaseModel):
    cell_id: str
    row_id: str
    period_id: str
    value: CellValue = Field(discriminator="state")
    confidence: float
    confidence_components: dict[str, float] = {}
    provenance: Provenance


class Row(BaseModel):
    row_id: str
    table_id: str
    label_raw: str
    label_norm: str
    indent_level: int
    role: Literal["group_header", "item", "subitem", "total", "opening", "closing", "closing_equiv", "flow"] = "item"
    parent_row_id: str | None = None
    dipnot_refs: list[int] = []
    asterisk_marks: list[str] = []
    confidence: float = 0.0
    provenance: Provenance


class Period(BaseModel):
    period_id: str
    label: str
    kind: Literal["instant", "duration"] = "instant"


class Table(BaseModel):
    table_id: str
    page: int
    title: str
    statement_hint: str | None = None
    periods: list[Period]
    confidence: float = 0.0
    provenance: Provenance


class RelationApproach(BaseModel):
    name: str  # cross_encoder | value_rules | lexical | llm_select
    raw_score: float
    rank: int | None = None
    accepted: bool


class Relation(BaseModel):
    relation_id: str
    summary_row_id: str
    footnote_row_id: str
    period_scope: str  # period_id or "both"
    relation_type: Literal["balance_reconciliation", "flow_match", "total_reconciliation", "semantic"] = "semantic"
    approaches: list[RelationApproach]
    agreement: Literal["consensus", "a_only", "b_only", "baseline_only", "d_only", "none"]
    confidence: float
    confidence_components: dict[str, float] = {}
    low_confidence: bool = False
    evidence: str = ""


class CheckResult(BaseModel):
    check_id: str
    group: Literal["structural", "format", "financial"]
    scope: str  # table_id / row_id / cell_id / relation_id
    status: Literal["pass", "fail", "not_evaluable"]
    detail: str = ""


class DocumentInfo(BaseModel):
    company: str
    period_end: str
    currency: str
    source_pdf: str
    source_sha256: str | None = None  # fingerprint of the input file, for corpus joins
    page_offset: int | None = None  # printed page + offset = pdf page


class RunInfo(BaseModel):
    # Quarantined: the only block allowed to differ between two identical runs.
    started_at: str
    ftlink_version: str
    tesseract_version: str = ""  # OCR engine build is the cross-machine drift boundary
    # environment degradations that changed what ran (e.g. cross-encoder failed
    # to load and approach A scored nothing): the loud record of a degraded run
    models_loaded: dict[str, bool] = {}
    config_echo: dict


class CaseOutput(BaseModel):
    schema_version: str = SCHEMA_VERSION
    document: DocumentInfo
    run: RunInfo
    tables: list[Table]
    rows: list[Row]
    cells: list[Cell]
    relations: list[Relation]
    checks: list[CheckResult]

    def relations_jsonl(self) -> str:
        """Self-contained one-line-per-relation view for jq/pandas evaluation."""
        rows_by_id = {r.row_id: r for r in self.rows}
        lines = []
        for rel in self.relations:
            s, f = rows_by_id.get(rel.summary_row_id), rows_by_id.get(rel.footnote_row_id)
            lines.append(rel.model_copy(update={}).model_dump_json() [:-1] + (
                f',"summary_label":{_j(s.label_raw if s else "")},"footnote_label":{_j(f.label_raw if f else "")}}}'))
        return "\n".join(lines)


def _j(s: str) -> str:
    import json

    return json.dumps(s, ensure_ascii=False)
