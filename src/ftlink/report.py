"""Static self-contained HTML report: tables, relations and check results with
confidence coloring. No server, no external assets; opens by double click."""
from __future__ import annotations

import html
from pathlib import Path

from .config import Settings
from .models import CaseOutput


def _conf_color(c: float) -> str:
    if c >= 0.8:
        return "#2e7d32"
    if c >= 0.5:
        return "#b8860b"
    return "#c62828"


def write_report(out: CaseOutput, settings: Settings, out_dir: Path) -> Path:
    rows_by_id = {r.row_id: r for r in out.rows}
    cells_by_row: dict[str, list] = {}
    for c in out.cells:
        cells_by_row.setdefault(c.row_id, []).append(c)

    parts: list[str] = []
    parts.append(f"<h1>ftlink report</h1><p>{html.escape(out.document.company)} · "
                 f"{out.document.period_end} · footnote {settings.document.footnote_no} · "
                 f"schema {out.schema_version}</p>")

    parts.append("<h2>Relations</h2><table><tr><th>summary row</th><th>footnote row</th>"
                 "<th>type</th><th>scope</th><th>agreement</th><th>confidence</th><th>flag</th></tr>")
    for r in out.relations:
        s = rows_by_id.get(r.summary_row_id)
        f = rows_by_id.get(r.footnote_row_id)
        parts.append(
            f"<tr><td>{html.escape(s.label_raw if s else r.summary_row_id)}</td>"
            f"<td>{html.escape(f.label_raw if f else r.footnote_row_id)}</td>"
            f"<td>{r.relation_type}</td><td>{r.period_scope}</td><td>{r.agreement}</td>"
            f"<td style='color:{_conf_color(r.confidence)}'><b>{r.confidence:.2f}</b></td>"
            f"<td>{'LOW' if r.low_confidence else ''}</td></tr>")
    parts.append("</table>")

    parts.append("<h2>Validation</h2><table><tr><th>check</th><th>group</th><th>scope</th>"
                 "<th>status</th><th>detail</th></tr>")
    for c in out.checks:
        color = {"pass": "#2e7d32", "fail": "#c62828", "not_evaluable": "#666"}[c.status]
        parts.append(f"<tr><td>{c.check_id}</td><td>{c.group}</td><td>{c.scope}</td>"
                     f"<td style='color:{color}'>{c.status}</td><td>{html.escape(c.detail)}</td></tr>")
    parts.append("</table>")

    for t in out.tables:
        parts.append(f"<h2>{t.table_id} · page {t.page} · conf {t.confidence:.2f}</h2>")
        heads = "".join(f"<th>{html.escape(p.label)}</th>" for p in t.periods)
        parts.append(f"<table><tr><th>row</th><th>refs</th>{heads}<th>role</th><th>conf</th></tr>")
        for r in out.rows:
            if r.table_id != t.table_id:
                continue
            cs = {c.period_id: c for c in cells_by_row.get(r.row_id, [])}
            tds = []
            for p in t.periods:
                c = cs.get(p.period_id)
                if c is None:
                    tds.append("<td></td>")
                else:
                    v = c.value
                    txt = v.raw if v.state == "number" else ("-" if v.state == "dash" else "")
                    mark = "*" if getattr(v, "repaired", False) else ""
                    tds.append(f"<td style='text-align:right;color:{_conf_color(c.confidence)}'>"
                               f"{html.escape(txt)}{mark}</td>")
            indent = "&nbsp;" * (2 * r.indent_level)
            parts.append(f"<tr><td>{indent}{html.escape(r.label_raw)}</td>"
                         f"<td>{','.join(map(str, r.dipnot_refs))}</td>{''.join(tds)}"
                         f"<td>{r.role}</td><td>{r.confidence:.2f}</td></tr>")
        parts.append("</table>")

    doc = ("<!doctype html><html><head><meta charset='utf-8'><title>ftlink report</title><style>"
           "body{font-family:system-ui;margin:2rem;max-width:1100px}"
           "table{border-collapse:collapse;margin:1rem 0;width:100%}"
           "td,th{border:1px solid #ccc;padding:3px 8px;font-size:13px;text-align:left}"
           "th{background:#f2efe9}</style></head><body>" + "".join(parts) + "</body></html>")
    p = out_dir / "report.html"
    p.write_text(doc, encoding="utf-8")
    return p
