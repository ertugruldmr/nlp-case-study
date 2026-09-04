"""Uploaded documents: the sealed pipeline on a compatible PDF, configured per document.

A document is a PDF plus the values the case requires to come from configuration (summary
page range, footnote number, optional extra control pages). Each upload becomes an ad-hoc
Scenario (id doc-<doc_id>) that runs through the same runner as the registry scenarios, so
every stored-run view works unchanged. Nothing here touches the deliverable tree.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

import pymupdf
from pydantic import BaseModel, Field, field_validator, model_validator

from .paths import runs_root
from .registry import Scenario

MAX_BYTES = 60 * 1024 * 1024
RUN_PREFIX = "doc-"


class UploadFields(BaseModel):
    summary_pages_start: int = Field(ge=1)
    summary_pages_end: int = Field(ge=1)
    footnote_no: int = Field(ge=1)
    extra_control_pages: list[int] = Field(default_factory=list)
    label: str = ""
    company: str = ""
    period_end: str = ""
    currency: str = "TL"
    ocr_lang: str = "tur"
    page_count: int = Field(ge=1)

    @field_validator("extra_control_pages", mode="before")
    @classmethod
    def _parse_pages(cls, v: object) -> object:
        if isinstance(v, str):
            return [int(x) for x in v.replace(";", ",").split(",") if x.strip()]
        return v

    @field_validator("label")
    @classmethod
    def _trim_label(cls, v: str) -> str:
        return v.strip()[:120]

    @field_validator("company")
    @classmethod
    def _trim_company(cls, v: str) -> str:
        return v.strip()[:240]

    @field_validator("period_end")
    @classmethod
    def _validate_period_end(cls, v: str) -> str:
        value = v.strip()
        if value:
            try:
                dt.date.fromisoformat(value)
            except ValueError as exc:
                raise ValueError("period_end must be YYYY-MM-DD") from exc
        return value

    @field_validator("currency")
    @classmethod
    def _normalize_currency(cls, v: str) -> str:
        value = v.strip().upper()
        if not value or len(value) > 8 or not value.replace("_", "").isalnum():
            raise ValueError("currency must be a short code such as TL, TRY or USD")
        return value

    @field_validator("ocr_lang")
    @classmethod
    def _normalize_ocr_lang(cls, v: str) -> str:
        value = v.strip().lower()
        if not value or len(value) > 24 or not all(c.isalnum() or c in "+_-" for c in value):
            raise ValueError("ocr_lang must be a Tesseract language code such as tur or eng")
        return value

    @model_validator(mode="after")
    def _within_document(self) -> "UploadFields":
        if self.summary_pages_start > self.summary_pages_end:
            raise ValueError("summary_pages_start must be <= summary_pages_end")
        if self.summary_pages_end > self.page_count:
            raise ValueError(f"summary_pages_end {self.summary_pages_end} exceeds page count {self.page_count}")
        if self.summary_pages_end == self.page_count:
            raise ValueError(
                "summary_pages_end must leave at least one later page for target-note discovery; "
                "use full-document visual review for pages 1..end"
            )
        bad = [p for p in self.extra_control_pages if p < 1 or p > self.page_count]
        if bad:
            raise ValueError(f"extra_control_pages outside 1..{self.page_count}: {bad}")
        self.extra_control_pages = list(dict.fromkeys(self.extra_control_pages))
        overlap = [p for p in self.extra_control_pages
                   if self.summary_pages_start <= p <= self.summary_pages_end]
        if overlap:
            raise ValueError(f"extra_control_pages must be outside summary range: {overlap}")
        return self


class DocumentMeta(BaseModel):
    doc_id: str
    label: str
    filename: str
    size: int
    sha256: str
    page_count: int
    summary_pages: tuple[int, int]
    footnote_no: int
    extra_control_pages: list[int]
    uploaded_at: str
    profile: dict[str, Any] = Field(default_factory=dict)
    company: str = ""
    period_end: str = ""
    currency: str = "TL"
    ocr_lang: str = "tur"


def documents_root() -> Path:
    return runs_root() / "_documents"


def doc_dir(doc_id: str) -> Path:
    return documents_root() / doc_id


def run_id(doc_id: str) -> str:
    return f"{RUN_PREFIX}{doc_id}"


def is_pdf(data: bytes) -> bool:
    return b"%PDF-" in data[:1024]


def inspect_pdf(data: bytes) -> dict[str, Any]:
    """Return a model-free fingerprint/compatibility profile without persisting bytes."""
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        if doc.needs_pass:
            raise ValueError("password-protected PDFs are not supported")
        native_text_pages: list[int] = []
        image_pages: list[int] = []
        landscape_pages: list[int] = []
        metadata_rotated_pages: list[int] = []
        dimensions: dict[str, int] = {}
        for number, page in enumerate(doc, start=1):
            if page.get_text("text").strip():
                native_text_pages.append(number)
            if page.get_images(full=True):
                image_pages.append(number)
            if page.rect.width > page.rect.height:
                landscape_pages.append(number)
            if page.rotation % 360:
                metadata_rotated_pages.append(number)
            key = f"{round(page.rect.width, 1)}x{round(page.rect.height, 1)}"
            dimensions[key] = dimensions.get(key, 0) + 1
        if len(native_text_pages) == doc.page_count:
            source_kind = "native_text"
        elif native_text_pages:
            source_kind = "mixed"
        else:
            source_kind = "image_only"
        return {
            "sha256": hashlib.sha256(data).hexdigest(),
            "size_bytes": len(data),
            "page_count": doc.page_count,
            "source_kind": source_kind,
            "native_text_page_count": len(native_text_pages),
            "image_page_count": len(image_pages),
            "landscape_pages": landscape_pages,
            "metadata_rotated_pages": metadata_rotated_pages,
            "page_dimensions_points": dimensions,
        }


def page_count(data: bytes) -> int:
    return int(inspect_pdf(data)["page_count"])


def save(data: bytes, filename: str, fields: UploadFields,
         profile: dict[str, Any] | None = None) -> DocumentMeta:
    sha = hashlib.sha256(data).hexdigest()
    base_id = sha[:12]
    config_key = json.dumps({
        "summary_pages": [fields.summary_pages_start, fields.summary_pages_end],
        "footnote_no": fields.footnote_no,
        "extra_control_pages": fields.extra_control_pages,
        "company": fields.company,
        "period_end": fields.period_end,
        "currency": fields.currency,
        "ocr_lang": fields.ocr_lang,
    }, sort_keys=True, separators=(",", ":"))
    doc_id = base_id
    existing = load(base_id)
    if existing is not None and (
        tuple(existing.summary_pages) != (fields.summary_pages_start, fields.summary_pages_end)
        or existing.footnote_no != fields.footnote_no
        or existing.extra_control_pages != fields.extra_control_pages
        or existing.company != fields.company
        or existing.period_end != fields.period_end
        or existing.currency != fields.currency
        or existing.ocr_lang != fields.ocr_lang
    ):
        # The same PDF may be evaluated under several configurations. Preserve the
        # historical SHA-only id for its first configuration and suffix later variants.
        doc_id = f"{base_id}-{hashlib.sha256(config_key.encode()).hexdigest()[:6]}"
    meta = DocumentMeta(
        doc_id=doc_id, label=fields.label, filename=Path(filename).name or "upload.pdf",
        size=len(data), sha256=sha, page_count=fields.page_count,
        summary_pages=(fields.summary_pages_start, fields.summary_pages_end),
        footnote_no=fields.footnote_no, extra_control_pages=fields.extra_control_pages,
        uploaded_at=dt.datetime.now().isoformat(timespec="seconds"),
        profile=profile or inspect_pdf(data), company=fields.company,
        period_end=fields.period_end, currency=fields.currency, ocr_lang=fields.ocr_lang)
    d = doc_dir(meta.doc_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "source.pdf").write_bytes(data)
    (d / "doc.json").write_text(meta.model_dump_json(indent=2), encoding="utf-8")
    return meta


def load(doc_id: str) -> DocumentMeta | None:
    p = doc_dir(doc_id) / "doc.json"
    if not p.exists():
        return None
    return DocumentMeta.model_validate_json(p.read_text(encoding="utf-8"))


def list_all() -> list[DocumentMeta]:
    root = documents_root()
    if not root.exists():
        return []
    docs = [m for p in root.iterdir() if (m := load(p.name)) is not None]
    docs.sort(key=lambda m: m.uploaded_at, reverse=True)
    return docs


def scenario_for(scenario_id: str) -> Scenario | None:
    if not scenario_id.startswith(RUN_PREFIX):
        return None
    meta = load(scenario_id[len(RUN_PREFIX):])
    if meta is None:
        return None
    name = meta.label or meta.filename
    return Scenario(
        id=scenario_id,
        title=f"Uploaded document: {name}",
        title_tr=f"Yüklenen belge: {name}",
        story=("The shipped pipeline on a user-supplied PDF. Only the configuration differs: "
               f"summary pages {meta.summary_pages[0]}-{meta.summary_pages[1]}, footnote "
               f"{meta.footnote_no}, control pages {meta.extra_control_pages or 'none'}."),
        story_tr=("Teslim edilen boru hattı, kullanıcının yüklediği PDF üzerinde. Yalnız "
                  f"konfigürasyon farklıdır: özet sayfaları {meta.summary_pages[0]}-"
                  f"{meta.summary_pages[1]}, dipnot {meta.footnote_no}, kontrol sayfaları "
                  f"{meta.extra_control_pages or 'yok'}."),
        overrides={
            "document": {
                "pdf_path": str((doc_dir(meta.doc_id) / "source.pdf").resolve()),
                "summary_pages": list(meta.summary_pages),
                "footnote_no": meta.footnote_no,
                "company": meta.company,
                "period_end": meta.period_end,
                "currency": meta.currency,
            },
            "ocr": {"lang": meta.ocr_lang},
            "confidence": {"extra_control_pages": meta.extra_control_pages},
        },
        group="document",
        precompute=False,
        eval_applicable=False,
    )
