#!/usr/bin/env bash
# Static verification of the presentation edition. Runs offline, needs no server
# and no Python environment: it checks that the cockpit parses, that every local
# asset it points at exists, that no machine-local path or private material
# leaked into the repository, and that the shell entry points are valid.
#
#   ./presentation-edition-v1/verify.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$ROOT/.." && pwd)"
cd "$ROOT"

fail=0
note() { printf '%-52s %s\n' "$1" "$2"; }

# ---------------------------------------------------------------- 1. the cockpit
if command -v node >/dev/null; then
  node - <<'NODE'
const fs = require('fs'), path = require('path');
const html = fs.readFileSync('dashboard.html', 'utf8');

if (!/<html lang="en">/i.test(html)) throw new Error('dashboard: missing lang=en');
if (!/<title>[^<]+<\/title>/i.test(html)) throw new Error('dashboard: missing <title>');

let inline = 0;
for (const m of html.matchAll(/<script([^>]*)>([\s\S]*?)<\/script>/gi)) {
  if (/\bsrc\s*=/.test(m[1])) continue;
  new Function(m[2]);            // throws on a syntax error
  inline++;
}
console.log(`dashboard: ${inline} inline script(s) parse`);

// every quoted local path the page can navigate to, attributes and JS strings alike
const rx = /["']((?:\.\.\/)?(?:rendered-docs|docs|vendor|app|v0|screenshots)\/[A-Za-z0-9._\/-]+)["']/g;
const targets = new Set([...html.matchAll(rx)].map(m => m[1]));
for (const m of html.matchAll(/(?:href|src|data-preview|data-open)="([^"]+)"/g)) {
  if (!/^(https?:|#|mailto:|javascript:|data:|\$\{)/.test(m[1])) targets.add(m[1].split('#')[0]);
}
const missing = [...targets].filter(t => !fs.existsSync(path.resolve(t)));
if (missing.length) throw new Error('dashboard: missing local targets:\n  ' + missing.join('\n  '));
console.log(`dashboard: ${targets.size} local targets all resolve`);

for (const required of ['Problem & research', 'Decision matrix', 'Open live demo',
                        'V1 · shipped', 'FRONTEND · OFFLINE HTML/JS', 'BACKEND · FASTAPI',
                        'AI CORE · FTLINK 1.0.2']) {
  if (!html.includes(required)) throw new Error(`dashboard: missing required content: ${required}`);
}
console.log('dashboard: required content present');
NODE
  note "cockpit (node)" "PASS"
else
  note "cockpit (node)" "SKIP (node not installed)"
fi

# ------------------------------------------------------- 2. no machine-local paths
if grep -rIqE "(/Users/|/home/)[A-Za-z0-9._-]+/" . --exclude-dir=.venv --exclude-dir=__pycache__ 2>/dev/null; then
  note "no machine-local absolute paths" "FAIL"
  grep -rIlE "(/Users/|/home/)[A-Za-z0-9._-]+/" . --exclude-dir=.venv --exclude-dir=__pycache__ 2>/dev/null | sed 's/^/    /'
  fail=1
else
  note "no machine-local absolute paths" "PASS"
fi

# ------------------------------------------------------- 3. no private material
private_hits=$(grep -rIl -E "interview-prep\.html|INTERVIEWER-LIVE-CHALLENGE" . 2>/dev/null | grep -v "^\./verify\.sh$" || true)
if [ -n "$private_hits" ]; then
  note "no private rehearsal material" "FAIL"
  printf '    %s\n' $private_hits
  fail=1
else
  note "no private rehearsal material" "PASS"
fi

# --------------------------------- 3b. no agent-prompt or presentation-coaching residue
residue=$(grep -rIlniE "you are implementing|copy everything below|fresh (high-effort )?(codex|claude) session|do not say|the correct message is|say aloud" . 2>/dev/null | grep -v "^\./verify\.sh$" || true)
if [ -n "$residue" ]; then
  note "no agent-prompt or coaching residue" "FAIL"
  printf '    %s\n' $residue
  fail=1
else
  note "no agent-prompt or coaching residue" "PASS"
fi

# ------------------------------------------- 3c. no private workspace folder names
ws_names=$(grep -rIl -E "case-info/|002\.processed|career-content" . 2>/dev/null | grep -v "^\./verify\.sh$" || true)
if [ -n "$ws_names" ]; then
  note "no private workspace folder names" "FAIL"
  printf '    %s\n' $ws_names
  fail=1
else
  note "no private workspace folder names" "PASS"
fi

# --------------------------------------- 3d. every relative link in a shipped doc resolves
if command -v python3 >/dev/null; then
  python3 - <<'PYL'
import pathlib, re, sys
bad = []
for pattern, attr in ((("*.md",), r'\]\(([^)]+)\)'), (("rendered-docs/*.html",), r'href="([^"]+)"')):
    for glob in pattern:
        for f in pathlib.Path(".").glob("**/" + glob if not glob.startswith("rendered") else glob):
            if any(part in {".venv", "__pycache__", "node_modules"} for part in f.parts):
                continue
            for n, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                for m in re.finditer(attr, line):
                    t = m.group(1)
                    if t.startswith(("http", "#", "mailto:", "data:", "javascript:")):
                        continue
                    if not (f.parent / t.split("#")[0].replace("%20", " ")).exists():
                        bad.append(f"{f}:{n}: {t}")
if bad:
    print("\n".join("    " + b for b in sorted(set(bad))))
    sys.exit(1)
PYL
  if [ $? -eq 0 ]; then note "shipped documents have no dead links" "PASS"
  else note "shipped documents have no dead links" "FAIL"; fail=1; fi
else
  note "shipped documents have no dead links" "SKIP (python3 not installed)"
fi

# ------------------------------------------------------- 4. the pipeline is reachable
if [ -f "$REPO/v0/configs/default.yaml" ]; then
  note "sealed pipeline present at ../v0" "PASS"
else
  note "sealed pipeline present at ../v0" "FAIL"; fail=1
fi
if grep -q 'path = "../../v0"' app/pyproject.toml; then
  note "app resolves the pipeline from ../../v0" "PASS"
else
  note "app resolves the pipeline from ../../v0" "FAIL"; fail=1
fi

# ------------------------------------------------------- 5. shell entry points
for script in "$ROOT"/*.sh "$ROOT"/app/*.sh; do
  [ -f "$script" ] || continue
  bash -n "$script" || { note "shell syntax: $(basename "$script")" "FAIL"; fail=1; }
done
note "shell entry points parse" "PASS"

# ------------------------------------------------------- 6. rendered docs current
if command -v python3 >/dev/null && python3 -c "import markdown" 2>/dev/null; then
  python3 render-docs.py --check >/dev/null && note "rendered-docs up to date" "PASS" \
    || { note "rendered-docs up to date" "FAIL (run: python3 render-docs.py)"; fail=1; }
else
  note "rendered-docs up to date" "SKIP (pip install markdown)"
fi

echo
if [ "$fail" -eq 0 ]; then echo "verify: PASS"; else echo "verify: FAIL"; exit 1; fi
