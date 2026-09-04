#!/usr/bin/env python3
"""Pre-render the Markdown documents linked from dashboard.html into styled HTML.

Deliberately a build step rather than a runtime fetch: the cockpit is opened over
file://, where browsers block fetch()/XHR to sibling file:// resources, so
client-side Markdown rendering would silently fail offline. Re-run this after
editing any source document under docs/.

    python3 render-docs.py            # rebuild rendered-docs/
    python3 render-docs.py --check    # exit 1 if any rendered page is stale

Requires the `markdown` package (pip install markdown). Writes only into
rendered-docs/; never modifies a source document and never touches ../v0.
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "rendered-docs"

# source markdown (relative to this folder) -> rendered page stem
PAGES: dict[str, str] = {
    "docs/PDF-DEBUGGER-DESIGN-BRIEF.md": "pdf-debugger-design-brief",
    "docs/RESEARCH-PLAYBOOK.md": "research-playbook",
    "docs/SOURCE-PDF-PAGE-GUIDE.md": "source-pdf-page-guide",
    "docs/GROUND-TRUTH-AUTHORING-GUIDE.md": "ground-truth-authoring-guide",
    "docs/decisions/decision-matrix.md": "decision-matrix",
    "docs/decisions/adr-01-extraction-stack.md": "adr-01-extraction-stack",
    "docs/decisions/adr-02-linker-lineup.md": "adr-02-linker-lineup",
    "docs/decisions/adr-03-confidence-decomposition.md": "adr-03-confidence-decomposition",
    "docs/evidence/percent-rescue.md": "percent-rescue",
    "docs/evidence/ocr-bakeoff-run08.md": "ocr-bakeoff-run08",
    "docs/evidence/structure-bakeoff-run06.md": "structure-bakeoff-run06",
    "docs/paper/ftlink-paper.md": "ftlink-paper-source",
    "../v0/README.md": "pipeline-readme",
}

TEMPLATE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>
<style>
:root{{--navy:#071d49;--blue:#0b3b82;--ink:#17233d;--muted:#5b6b8c;--line:#d9e1ef;--bg:#f5f8fc}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.6 Inter,ui-sans-serif,system-ui,sans-serif}}
header{{background:var(--navy);color:#fff;padding:14px 26px;display:flex;align-items:center;gap:14px;flex-wrap:wrap;position:sticky;top:0;z-index:2}}
header .src{{color:#a9c5e9;font-size:12px;word-break:break-all}}
header a{{color:#bfeaf4;text-decoration:none;font-size:12px;margin-left:auto;white-space:nowrap}}
main{{max-width:860px;margin:0 auto;padding:28px 26px 80px;background:#fff;box-shadow:0 0 0 1px var(--line);min-height:100vh}}
h1,h2,h3,h4{{color:var(--navy);line-height:1.25}}
h1{{font-size:26px;border-bottom:2px solid var(--line);padding-bottom:10px}}
h2{{font-size:20px;margin-top:34px;border-bottom:1px solid var(--line);padding-bottom:6px}}
h3{{font-size:16px;margin-top:24px}}
code{{background:#eef3fb;padding:1px 5px;border-radius:4px;font:13px/1.4 ui-monospace,SFMono-Regular,monospace}}
pre{{background:#091a3b;color:#d7e8ff;padding:14px 16px;border-radius:8px;overflow:auto}}
pre code{{background:none;padding:0;color:inherit}}
table{{border-collapse:collapse;width:100%;margin:14px 0;font-size:13.5px}}
th,td{{border:1px solid var(--line);padding:7px 10px;text-align:left;vertical-align:top}}
th{{background:#edf3fb}}
blockquote{{border-left:4px solid var(--blue);margin:14px 0;padding:2px 16px;color:var(--muted);background:#f2f7ff}}
a{{color:var(--blue)}}
img{{max-width:100%}}
</style></head><body>
<header><b>{title}</b><span class="src">{relpath}</span><a href="{raw_href}" target="_blank" rel="noopener">View raw source &#8599;</a></header>
<main>{body}</main>
</body></html>"""


def render(relpath: str, stem: str) -> str:
    import markdown

    src = ROOT / relpath
    if not src.is_file():
        raise FileNotFoundError(f"source document missing: {relpath}")
    text = src.read_text(encoding="utf-8")
    body = markdown.markdown(
        text,
        extensions=["extra", "sane_lists", "toc", "codehilite"],
        extension_configs={"codehilite": {"noclasses": True}},
    )
    match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    title = match.group(1).strip() if match else src.name
    depth = relpath.count("/")
    raw_href = "../" + relpath
    return TEMPLATE.format(title=title, relpath=relpath, raw_href=raw_href, body=body)


def main() -> int:
    check = "--check" in sys.argv
    OUT_DIR.mkdir(exist_ok=True)
    stale: list[str] = []
    manifest: list[str] = []
    for relpath, stem in PAGES.items():
        html = render(relpath, stem)
        out = OUT_DIR / f"{stem}.html"
        if check:
            if not out.is_file() or out.read_text(encoding="utf-8") != html:
                stale.append(str(out.relative_to(ROOT)))
        else:
            out.write_text(html, encoding="utf-8")
            print(f"rendered {relpath} -> rendered-docs/{stem}.html")
        digest = hashlib.sha256((ROOT / relpath).read_bytes()).hexdigest()
        manifest.append(f"{digest}  {relpath}")

    manifest_path = OUT_DIR / "MANIFEST.sha256"
    manifest_text = "\n".join(manifest) + "\n"
    if check:
        if not manifest_path.is_file() or manifest_path.read_text(encoding="utf-8") != manifest_text:
            stale.append("rendered-docs/MANIFEST.sha256")
        if stale:
            print("stale rendered pages:", ", ".join(stale))
            return 1
        print("rendered-docs is up to date")
        return 0

    manifest_path.write_text(manifest_text, encoding="utf-8")
    print(f"wrote {manifest_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
