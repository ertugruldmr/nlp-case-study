"""FastAPI service: scenario registry, stored runs, live runs, comparisons, uploaded documents."""
from __future__ import annotations

import csv
import io
import json

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Request
from pydantic import BaseModel, Field, ValidationError
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from . import benchmarks, pdf_debugger
from . import compare as compare_mod
from . import documents
from . import labels as labels_mod
from . import runner, store, triage, walkthrough
from .paths import frontend_root
from .registry import SCENARIOS

app = FastAPI(title="ftlink scenario lab", version="1.0.1")


def _validation_detail(error: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(x) for x in item['loc']) or 'fields'}: {item['msg']}"
        for item in error.errors()
    )


async def _read_and_inspect_pdf(file: UploadFile) -> tuple[bytes, dict]:
    data = await file.read(documents.MAX_BYTES + 1)
    if len(data) > documents.MAX_BYTES:
        raise HTTPException(413, f"PDF larger than {documents.MAX_BYTES // (1024 * 1024)} MB")
    if not documents.is_pdf(data):
        raise HTTPException(400, "not a PDF (magic bytes)")
    try:
        return data, documents.inspect_pdf(data)
    except (OSError, RuntimeError, ValueError) as exc:
        raise HTTPException(400, f"PDF could not be inspected: {exc}")


@app.get("/api/debugger/runs")
def debugger_runs() -> list[dict]:
    return pdf_debugger.available_runs()


@app.post("/api/debugger/inspect-pdf")
async def debugger_inspect_pdf(file: UploadFile = File(...)) -> dict:
    """Read-only preflight: fingerprint a user-supplied PDF without saving it."""
    _, profile = await _read_and_inspect_pdf(file)
    return profile


@app.get("/api/debugger/run")
def debugger_run(run_id: str = "baseline") -> dict:
    try:
        result = pdf_debugger.load_result(run_id)
        count = pdf_debugger.page_count(run_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    return {"run_id": run_id, "status": "completed", "page_count": count,
            "coordinate_spaces": pdf_debugger.coordinate_spaces(run_id),
            "document": result["document"], "run": result["run"], "result": result}


@app.get("/api/debugger/proof")
def debugger_proof(run_id: str = "baseline") -> dict:
    try:
        return pdf_debugger.run_proof(run_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


class DebuggerConfiguration(BaseModel):
    source_run_id: str = "baseline"
    summary_pages_start: int
    summary_pages_end: int
    footnote_no: int
    extra_control_pages: list[int] = Field(default_factory=list)
    label: str = ""
    company: str | None = None
    period_end: str | None = None
    currency: str | None = None
    ocr_lang: str | None = None


@app.post("/api/debugger/configured-run")
def debugger_configured_run(value: DebuggerConfiguration) -> dict:
    try:
        source = pdf_debugger.pdf_path(value.source_run_id)
        count = pdf_debugger.page_count(value.source_run_id)
        source_result = pdf_debugger.load_result(value.source_run_id)
        source_document = source_result.get("document", {})
        source_config = source_result.get("run", {}).get("config_echo", {})
        fields = documents.UploadFields(
            summary_pages_start=value.summary_pages_start,
            summary_pages_end=value.summary_pages_end,
            footnote_no=value.footnote_no,
            extra_control_pages=value.extra_control_pages,
            label=value.label,
            company=value.company if value.company is not None else source_document.get("company", ""),
            period_end=value.period_end if value.period_end is not None else source_document.get("period_end", ""),
            currency=value.currency if value.currency is not None else source_document.get("currency", "TL"),
            ocr_lang=value.ocr_lang if value.ocr_lang is not None else source_config.get("ocr", {}).get("lang", "tur"),
            page_count=count,
        )
    except ValidationError as exc:
        raise HTTPException(422, _validation_detail(exc))
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    meta = documents.save(source.read_bytes(), source.name, fields)
    rid = documents.run_id(meta.doc_id)
    if not runner.start(rid):
        raise HTTPException(409, "another scenario run is in progress")
    return {**_doc_view(meta), "state": "started", "run_id": rid}


@app.get("/api/debugger/page/{page}")
def debugger_page(page: int, run_id: str = "baseline", view_rotation: int = 0) -> Response:
    try: body = pdf_debugger.page_png(page, run_id, view_rotation)
    except ValueError as exc: raise HTTPException(400, str(exc))
    except (OSError, RuntimeError) as exc: raise HTTPException(503, f"page render unavailable: {type(exc).__name__}")
    return Response(body, media_type="image/png", headers={"Cache-Control": "public, max-age=3600"})


@app.get("/api/debugger/canonical")
def debugger_canonical(run_id: str = "baseline") -> Response:
    try: body = pdf_debugger.result_path(run_id).read_bytes()
    except ValueError as exc: raise HTTPException(404, str(exc))
    return Response(body, media_type="application/json", headers={"Content-Disposition": f"attachment; filename={run_id}-result.json"})


@app.get("/api/debugger/annotations")
def debugger_annotations() -> dict:
    return {"schema_version": pdf_debugger.ANNOTATION_SCHEMA, "annotations": pdf_debugger.annotations()}


@app.post("/api/debugger/annotations")
async def debugger_add_annotation(request: Request) -> dict:
    try: value = await request.json(); count = pdf_debugger.add_annotation(value)
    except (ValueError, json.JSONDecodeError) as exc: raise HTTPException(400, str(exc))
    return {"ok": True, "count": count}


@app.get("/api/debugger/annotations/export")
def debugger_export_annotations(format: str = "jsonl") -> Response:
    try: media, filename, body = pdf_debugger.export_annotations(format)
    except ValueError as exc: raise HTTPException(400, str(exc))
    return Response(body, media_type=media, headers={"Content-Disposition": f"attachment; filename={filename}"})


def _require_run_id(scenario_id: str) -> None:
    try:
        runner.resolve(scenario_id)
    except KeyError:
        raise HTTPException(404, f"unknown scenario {scenario_id}")


@app.get("/api/meta")
def meta() -> dict:
    return {
        "case": "Finansal Tablo ve Dipnot İlişkilendirme",
        "document": "Özak GYO 31.12.2012 bağımsız denetim raporu (taranmış, 95 sayfa)",
        "pipeline": "ftlink 1.0.2 (deliverable, consumed as a library)",
        "note": ("Her senaryo, teslim edilen konfigürasyonun üzerine bir config "
                 "farkıdır; kod değişikliği yoktur."),
    }


@app.get("/api/scenarios")
def scenarios() -> list[dict]:
    out = []
    for s in SCENARIOS:
        d = s.model_dump()
        d["status"] = runner.status(s.id)
        # A rerun may leave a recoverable previous artifact on disk. It is not
        # presentable until the current authoritative attempt is DONE.
        d["summary"] = store.summarize(s.id) if d["status"].get("state") == "done" else None
        out.append(d)
    return out


@app.get("/api/runs/{scenario_id}/result")
def run_result(scenario_id: str) -> dict:
    result = store.load_result(scenario_id)
    if result is None:
        raise HTTPException(404, f"no stored run for {scenario_id}")
    return result


@app.get("/api/runs/{scenario_id}/relations")
def run_relations(scenario_id: str) -> list[dict]:
    rels = store.relations_view(scenario_id)
    if rels is None:
        raise HTTPException(404, f"no stored run for {scenario_id}")
    return rels


@app.get("/api/runs/{scenario_id}/walkthrough")
def run_walkthrough(scenario_id: str) -> dict:
    result = store.load_result(scenario_id)
    if result is None:
        raise HTTPException(404, f"no stored run for {scenario_id}")
    return walkthrough.build(result)


@app.get("/api/runs/{scenario_id}/triage")
def run_triage(scenario_id: str, c_review: float = 1.0, c_miss: float = 20.0) -> dict:
    try:
        data = triage.build(scenario_id, c_review, c_miss)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if data is None:
        raise HTTPException(404, f"no stored run for {scenario_id}")
    return data


class LabelIn(BaseModel):
    kind: str
    key: str
    label: str | None
    note: str = ""


@app.get("/api/runs/{scenario_id}/labels")
def get_labels(scenario_id: str) -> dict:
    data = labels_mod.load(scenario_id)
    return {"labels": data, "summary": labels_mod.summary(data)}


@app.post("/api/runs/{scenario_id}/labels")
def post_label(scenario_id: str, body: LabelIn) -> dict:
    _require_run_id(scenario_id)
    try:
        data = labels_mod.set_label(scenario_id, body.kind, body.key, body.label, body.note)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"labels": data, "summary": labels_mod.summary(data)}


@app.get("/api/runs/{scenario_id}/labels/export")
def export_labels(scenario_id: str, format: str = "csv", c_review: float = 1.0, c_miss: float = 20.0) -> Response:
    if format not in ("csv", "jsonl"):
        raise HTTPException(400, "format must be csv or jsonl")
    try:
        rows = triage.export_rows(scenario_id, c_review, c_miss)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if rows is None:
        raise HTTPException(404, f"no stored run for {scenario_id}")
    if format == "jsonl":
        body = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
        media = "application/x-ndjson"
    else:
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=list(triage.EXPORT_COLUMNS), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
        body, media = buf.getvalue(), "text/csv; charset=utf-8"
    return Response(body, media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="{scenario_id}-labels.{format}"'})


@app.get("/api/runs/{scenario_id}/report", response_class=HTMLResponse)
def run_report(scenario_id: str) -> FileResponse:
    p = store.run_dir(scenario_id) / "outputs/report.html"
    if not p.exists():
        raise HTTPException(404, f"no report for {scenario_id}")
    return FileResponse(p)


@app.post("/api/runs/{scenario_id}")
def run_scenario(scenario_id: str) -> dict:
    _require_run_id(scenario_id)
    if not runner.start(scenario_id):
        raise HTTPException(409, "another scenario run is in progress")
    return {"state": "started", "scenario": scenario_id}


@app.get("/api/compare")
def compare(a: str, b: str) -> dict:
    for sid in (a, b):
        _require_run_id(sid)
    return compare_mod.compare(a, b)


@app.get("/api/matrix")
def matrix() -> list[dict]:
    return compare_mod.matrix()


@app.get("/api/benchmarks")
def list_benchmarks() -> list[dict]:
    return benchmarks.listing()


@app.get("/api/benchmarks/{benchmark_id}")
def get_benchmark(benchmark_id: str) -> dict:
    b = benchmarks.load(benchmark_id)
    if b is None:
        raise HTTPException(404, f"unknown benchmark {benchmark_id}")
    return b.model_dump(mode="json")


def _doc_view(meta: documents.DocumentMeta) -> dict:
    rid = documents.run_id(meta.doc_id)
    status = runner.status(rid)
    # Do not put metrics from an older result beside a running/failed rerun. The
    # previous files may remain recoverable on disk, but only DONE is presentable.
    summary = store.summarize(rid) if status.get("state") == "done" else None
    return {**meta.model_dump(), "run_id": rid, "status": status, "summary": summary}


@app.post("/api/documents")
async def upload_document(
    file: UploadFile = File(...),
    summary_pages_start: int = Form(...),
    summary_pages_end: int = Form(...),
    footnote_no: int = Form(...),
    extra_control_pages: str = Form(""),
    label: str = Form(""),
    company: str = Form(""),
    period_end: str = Form(""),
    currency: str = Form("TL"),
    ocr_lang: str = Form("tur"),
) -> dict:
    data, profile = await _read_and_inspect_pdf(file)
    pages = int(profile["page_count"])
    try:
        fields = documents.UploadFields(
            summary_pages_start=summary_pages_start, summary_pages_end=summary_pages_end,
            footnote_no=footnote_no, extra_control_pages=extra_control_pages, label=label,
            company=company, period_end=period_end, currency=currency, ocr_lang=ocr_lang,
            page_count=pages)
    except ValidationError as e:
        raise HTTPException(422, _validation_detail(e))
    return _doc_view(documents.save(data, file.filename or "upload.pdf", fields, profile))


@app.get("/api/documents")
def list_documents() -> list[dict]:
    return [_doc_view(m) for m in documents.list_all()]


@app.get("/api/documents/{doc_id}")
def get_document(doc_id: str) -> dict:
    meta = documents.load(doc_id)
    if meta is None:
        raise HTTPException(404, f"unknown document {doc_id}")
    return {**_doc_view(meta), "meta": store.load_meta(documents.run_id(doc_id))}


@app.post("/api/documents/{doc_id}/run")
def run_document(doc_id: str) -> dict:
    if documents.load(doc_id) is None:
        raise HTTPException(404, f"unknown document {doc_id}")
    rid = documents.run_id(doc_id)
    if not runner.start(rid):
        raise HTTPException(409, "another scenario run is in progress")
    return {"state": "started", "scenario": rid, "doc_id": doc_id}


app.mount("/", StaticFiles(directory=frontend_root(), html=True), name="frontend")


def serve() -> None:
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8199)
