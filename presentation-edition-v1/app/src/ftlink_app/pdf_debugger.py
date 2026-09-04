"""PDF visual debugger adapter for the scenario lab.

The baseline and completed app runs are exposed read-only. Review annotations are
separate app state and never flow into the ftlink pipeline.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import json
import re
from pathlib import Path
from typing import Any

import pymupdf

from . import documents, store
from .paths import APP_ROOT, deliverable_root, runs_root
from .registry import BY_ID, SCENARIOS

ANNOTATION_SCHEMA = "debugger.annotation.v1"
ANNOTATION_PATH = runs_root() / "_debugger" / "annotations.jsonl"
FIXTURE_PDF = APP_ROOT / "fixtures" / "ozak_gyo_2012.pdf"


def _safe_run_id(run_id: str) -> str:
    if run_id in BY_ID:
        return run_id
    if not run_id.startswith("doc-") or not re.fullmatch(r"[A-Za-z0-9-]+", run_id[4:]):
        raise ValueError("unsupported debugger run")
    return run_id


def result_path(run_id: str = "baseline") -> Path:
    run_id = _safe_run_id(run_id)
    if run_id != "baseline":
        # An older result.json may still exist while the same scenario is being rerun
        # or after that rerun fails. meta/status is authoritative for whether the
        # current attempt is safe to present as completed.
        from . import runner
        state = runner.status(run_id).get("state")
        if state != "done":
            raise ValueError(f"debugger run is not completed (state={state or 'unknown'})")
    path = (deliverable_root() / "outputs" / "result.json") if run_id == "baseline" else (
        runs_root() / run_id / "outputs" / "result.json")
    if not path.is_file():
        raise ValueError("debugger run is not completed")
    return path


def load_result(run_id: str = "baseline") -> dict[str, Any]:
    return json.loads(result_path(run_id).read_text(encoding="utf-8"))


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _pipeline_fingerprint() -> str:
    root = deliverable_root()
    paths = sorted((root / "src/ftlink").glob("*.py")) + [root / "configs/default.yaml"]
    digest = hashlib.sha256()
    for path in paths:
        digest.update(str(path.relative_to(root)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def run_proof(run_id: str = "baseline") -> dict[str, Any]:
    """Evidence that a result is bound to concrete input bytes, config and pipeline code."""
    run_id = _safe_run_id(run_id)
    result = load_result(run_id)
    source = pdf_path(run_id)
    output = result_path(run_id)
    actual_source_sha = _file_sha256(source)
    claimed_source_sha = result.get("document", {}).get("source_sha256")
    config = result.get("run", {}).get("config_echo", {})
    config_json = json.dumps(config, sort_keys=True, separators=(",", ":"), default=str)
    meta = store.load_meta(run_id) or {}
    uploaded = None
    if run_id.startswith("doc-"):
        doc = documents.load(run_id[4:])
        if doc:
            uploaded = {
                "doc_id": doc.doc_id, "filename": doc.filename, "label": doc.label,
                "uploaded_at": doc.uploaded_at, "profile": doc.profile,
            }
    counts = {key: len(result.get(key, []))
              for key in ("tables", "rows", "cells", "relations", "checks")}
    return {
        "schema_version": "debugger.run-proof.v1",
        "run_id": run_id,
        "input": {
            "filename": source.name,
            "size_bytes": source.stat().st_size,
            "actual_sha256": actual_source_sha,
            "result_claimed_sha256": claimed_source_sha,
            "sha256_match": actual_source_sha == claimed_source_sha,
        },
        "configuration": {
            "sha256": hashlib.sha256(config_json.encode()).hexdigest(),
            "echo": config,
        },
        "execution": {
            "result_started_at": result.get("run", {}).get("started_at"),
            "state": meta.get("state", "stored"),
            "duration_s": meta.get("duration_s"),
            "platform": meta.get("platform"),
            "models_loaded": result.get("run", {}).get("models_loaded", {}),
            "pipeline_code_sha256": _pipeline_fingerprint(),
        },
        "output": {
            "result_sha256": _file_sha256(output),
            "size_bytes": output.stat().st_size,
            "counts": counts,
            "non_pass_checks": sum(1 for c in result.get("checks", [])
                                   if c.get("status") != "pass"),
        },
        "uploaded_document": uploaded,
    }


def pdf_path(run_id: str = "baseline") -> Path:
    run_id = _safe_run_id(run_id)
    if run_id.startswith("doc-"):
        meta = documents.load(run_id[4:])
        if meta is None:
            raise ValueError("uploaded document is unavailable")
        path = documents.doc_dir(meta.doc_id) / "source.pdf"
        if not path.is_file():
            raise ValueError("uploaded PDF is unavailable")
        return path
    source = APP_ROOT.parent / "case-info" / "Özak GYO 31122012 Bağımsız Denetim Raporu.pdf"
    return source if source.exists() else FIXTURE_PDF


def page_count(run_id: str = "baseline") -> int:
    with pymupdf.open(pdf_path(run_id)) as doc:
        return doc.page_count


def coordinate_spaces(run_id: str = "baseline") -> dict[str, dict[str, int]]:
    result = load_result(run_id)
    dpi = int(result.get("run", {}).get("config_echo", {}).get("ocr", {}).get("dpi") or 300)
    objects = [*result.get("tables", []), *result.get("rows", []), *result.get("cells", [])]
    max_bbox: dict[int, tuple[float, float]] = {}
    for obj in objects:
        prov = obj.get("provenance") or {}
        bbox = prov.get("bbox")
        page = prov.get("page") or obj.get("page")
        if page and isinstance(bbox, list) and len(bbox) == 4:
            old = max_bbox.get(int(page), (0.0, 0.0))
            max_bbox[int(page)] = (max(old[0], float(bbox[2])), max(old[1], float(bbox[3])))
    spaces: dict[str, dict[str, int]] = {}
    with pymupdf.open(pdf_path(run_id)) as doc:
        for index, page in enumerate(doc):
            width = round(page.rect.width * dpi / 72)
            height = round(page.rect.height * dpi / 72)
            mx, my = max_bbox.get(index + 1, (0.0, 0.0))
            rotation = 90 if mx > width * 1.01 and mx <= height * 1.01 and my <= width * 1.01 else 0
            if rotation:
                width, height = height, width
            spaces[str(index + 1)] = {"width": width, "height": height,
                                      "dpi": dpi, "rotation": rotation}
    return spaces


def page_png(page: int, run_id: str = "baseline", view_rotation: int = 0) -> bytes:
    run_id = _safe_run_id(run_id)
    if view_rotation not in {0, 90, 180, 270}:
        raise ValueError("view_rotation must be 0, 90, 180 or 270")
    count = page_count(run_id)
    if page < 1 or page > count:
        raise ValueError(f"page must be between 1 and {count}")
    space = coordinate_spaces(run_id)[str(page)]
    rotation = (space["rotation"] + view_rotation) % 360
    cache = runs_root() / "_debugger" / "pages" / run_id / f"page-{page}-r{rotation}.png"
    cache.parent.mkdir(parents=True, exist_ok=True)
    if not cache.exists():
        doc = pymupdf.open(pdf_path(run_id))
        try:
            matrix = pymupdf.Matrix(1.5, 1.5).prerotate(rotation)
            pix = doc[page - 1].get_pixmap(matrix=matrix, colorspace=pymupdf.csRGB, alpha=False)
            pix.save(cache)
        finally:
            doc.close()
    return cache.read_bytes()


def available_runs() -> list[dict[str, Any]]:
    runs = [{"run_id": "baseline", "label": "Baseline (submitted run)",
             "page_count": page_count("baseline")}]
    for scenario in SCENARIOS:
        if scenario.id == "baseline":
            continue
        try:
            result_path(scenario.id)
        except ValueError:
            continue
        runs.append({"run_id": scenario.id, "label": scenario.title,
                     "page_count": page_count(scenario.id), "group": scenario.group})
    for meta in documents.list_all():
        run_id = documents.run_id(meta.doc_id)
        try:
            result_path(run_id)
        except ValueError:
            continue
        runs.append({"run_id": run_id, "label": meta.label or meta.filename,
                     "page_count": meta.page_count, "group": "document"})
    return runs


def _validate(value: object) -> dict[str, Any]:
    if not isinstance(value, dict): raise ValueError("annotation must be an object")
    required = {"schema_version", "decision", "issue_family", "note", "severity", "object_ids", "document_sha256", "run_id", "timestamp"}
    missing = required - set(value)
    if missing: raise ValueError("missing fields: " + ", ".join(sorted(missing)))
    if value["schema_version"] != ANNOTATION_SCHEMA: raise ValueError("unsupported annotation schema")
    if value["decision"] not in {"accept", "reject", "unsure"}: raise ValueError("invalid decision")
    if not isinstance(value["note"], str) or len(value["note"]) > 4000: raise ValueError("invalid note")
    if not isinstance(value["object_ids"], list) or not all(isinstance(x, str) for x in value["object_ids"]): raise ValueError("invalid object_ids")
    if len(value["document_sha256"]) != 64: raise ValueError("invalid run binding")
    run_id = _safe_run_id(value["run_id"])
    if run_id != "baseline":
        result = load_result(run_id)
        if result.get("document", {}).get("source_sha256") != value["document_sha256"]:
            raise ValueError("annotation document does not match run")
    return value


def annotations() -> list[dict[str, Any]]:
    if not ANNOTATION_PATH.exists(): return []
    return [_validate(json.loads(line)) for line in ANNOTATION_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]


def add_annotation(value: dict[str, Any]) -> int:
    _validate(value)
    ANNOTATION_PATH.parent.mkdir(parents=True, exist_ok=True)
    with ANNOTATION_PATH.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")
    return len(annotations())


def export_annotations(fmt: str) -> tuple[str, str, str]:
    rows = annotations()
    if fmt == "jsonl": return ("application/x-ndjson", "annotations.jsonl", "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in rows))
    if fmt != "csv": raise ValueError("format must be jsonl or csv")
    fields = ["schema_version", "decision", "issue_family", "note", "severity", "object_ids", "document_sha256", "run_id", "timestamp"]
    out = io.StringIO(); writer = csv.DictWriter(out, fieldnames=fields, lineterminator="\n"); writer.writeheader()
    for row in rows: writer.writerow({**row, "object_ids": ";".join(row["object_ids"])})
    return ("text/csv; charset=utf-8", "annotations.csv", out.getvalue())
