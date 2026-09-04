"""Benchmark store: one JSON file per measured comparison under app/benchmarks/, validated on read.

Schema: app/benchmarks/SCHEMA.md. Files are produced by `ftlink-benchmarks-sync` (benchmarks_sync.py)
or dropped in by hand (Colab bake-off results); the API never writes here.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from .paths import benchmarks_root

Scope = Literal["this document", "other documents", "offline refit", "colab"]
Kind = Literal["text", "number", "pct", "seconds", "bool"]
Role = Literal["shipped", "measured", "pending", "rejected"]

SCOPE_ORDER: tuple[str, ...] = ("this document", "other documents", "offline refit", "colab")
RESERVED_ROW_KEYS = frozenset({"id", "label", "role", "source"})
PARSE_ERROR_PREFIX = "parse_error:"


class Column(BaseModel):
    key: str
    label_tr: str
    kind: Kind


class Row(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    label: str
    role: Role
    source: str

    def value(self, key: str) -> object:
        return (self.model_extra or {}).get(key)


class Benchmark(BaseModel):
    id: str
    title_tr: str
    title_en: str
    measured_at: datetime
    source: str
    scope: Scope
    baseline: str | None
    columns: list[Column]
    rows: list[Row]
    notes_tr: list[str] = []
    decision_rule: str

    @model_validator(mode="after")
    def _consistent(self) -> "Benchmark":
        keys = [c.key for c in self.columns]
        if len(set(keys)) != len(keys):
            raise ValueError("duplicate column key")
        clash = RESERVED_ROW_KEYS & set(keys)
        if clash:
            raise ValueError(f"column key(s) clash with row fields: {sorted(clash)}")
        ids = [r.id for r in self.rows]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate row id")
        if self.baseline is not None and self.baseline not in ids:
            raise ValueError(f"baseline {self.baseline!r} is not a row id")
        for r in self.rows:
            for c in self.columns:
                _check_kind(r.id, c, r.value(c.key))
        return self

    @property
    def parse_errors(self) -> list[str]:
        return [n for n in self.notes_tr if n.startswith(PARSE_ERROR_PREFIX)]


def _check_kind(row_id: str, col: Column, v: object) -> None:
    if v is None:
        return
    if col.kind == "bool":
        ok = isinstance(v, bool)
    elif col.kind == "text":
        ok = isinstance(v, str)
    else:
        ok = isinstance(v, (int, float)) and not isinstance(v, bool)
    if not ok:
        raise ValueError(f"row {row_id!r} column {col.key!r}: {v!r} is not {col.kind}")


def load_all(root: Path | None = None) -> list[Benchmark]:
    root = root or benchmarks_root()
    out: list[Benchmark] = []
    for p in sorted(root.glob("*.json")):
        b = Benchmark.model_validate_json(p.read_text(encoding="utf-8"))
        if b.id != p.stem:
            raise ValueError(f"{p.name}: id {b.id!r} must equal the file stem")
        out.append(b)
    out.sort(key=lambda b: (SCOPE_ORDER.index(b.scope), b.id))
    return out


def load(benchmark_id: str, root: Path | None = None) -> Benchmark | None:
    return next((b for b in load_all(root) if b.id == benchmark_id), None)


def listing(root: Path | None = None) -> list[dict]:
    return [{
        "id": b.id, "title_tr": b.title_tr, "title_en": b.title_en, "scope": b.scope,
        "measured_at": b.measured_at.isoformat(), "rows": len(b.rows), "baseline": b.baseline,
        "shipped_rows": sum(1 for r in b.rows if r.role == "shipped"),
        "parse_errors": len(b.parse_errors),
    } for b in load_all(root)]
