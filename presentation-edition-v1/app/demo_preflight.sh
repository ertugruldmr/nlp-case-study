#!/usr/bin/env bash
# demo_preflight.sh: run T-60 min before the defense. Starts the lab, hits every endpoint the
# demo uses, prints the headline numbers, stops the server. Exit 1 on any mismatch.
# Usage: cd app && ./demo_preflight.sh          (about 20 seconds; needs `uv sync` done once)
set -uo pipefail
export PATH="$HOME/.local/bin:$PATH"
cd "$(dirname "$0")"
PORT=8199; BASE="http://127.0.0.1:$PORT"
fail=0; ok() { echo "  OK   $1"; }; bad() { echo "  FAIL $1"; fail=1; }
if curl -s -o /dev/null "$BASE/api/meta"; then echo "server already running on $PORT"; STARTED=0; else
  uv run uvicorn ftlink_app.api:app --host 127.0.0.1 --port $PORT >/tmp/ftlink_demo_preflight.log 2>&1 &
  STARTED=1; for i in $(seq 1 60); do curl -s -o /dev/null "$BASE/api/meta" && break; sleep 0.5; done
fi
echo "== 1. meta"; curl -s "$BASE/api/meta" | python3 -c "import json,sys;d=json.load(sys.stdin);print('  ',d['pipeline'])" || bad meta
echo "== 2. scenarios (expect 18, baseline done)"
curl -s "$BASE/api/scenarios" | python3 -c "
import json,sys;d=json.load(sys.stdin);n=len(d);b=[s for s in d if s['id']=='baseline'][0]
print('   scenarios',n,'| baseline',b['status']['state'],'| cells',b['summary']['cells'],'| relations',b['summary']['relations'],'| checks',b['summary']['checks'])
sys.exit(0 if n==18 and b['status']['state']=='done' and b['summary']['relations']==7 else 1)" && ok scenarios || bad scenarios
echo "== 3. walkthrough baseline (expect S2..S10, 4 low cells, 7 relations, 4 fails)"
curl -s "$BASE/api/runs/baseline/walkthrough" | python3 -c "
import json,sys;w=json.load(sys.stdin);by={s['id']:s for s in w['stages']}
print('   stages',[s['id'] for s in w['stages']],'| cells<=0.5',by['S4']['facts']['cells_at_or_below_0_5'],'| repaired',by['S4']['facts']['repaired_cells'],'| agreement',by['S7']['facts']['agreement'],'| fails',[c['check_id'] for c in by['S9']['items']])
sys.exit(0 if by['S4']['facts']['cells_at_or_below_0_5']==4 and by['S7']['facts']['relations']==7 and len(by['S9']['items'])==4 else 1)" && ok walkthrough || bad walkthrough
echo "== 4. triage 1/20 (expect p* 0.95, 6 of 7 to review, cost 6.43 / 7.0 / 15.79)"
curl -s "$BASE/api/runs/baseline/triage?c_review=1&c_miss=20" | python3 -c "
import json,sys;t=json.load(sys.stdin)['threshold']
print('   p*',t['p_star'],'| review',len(t['review_ids']),'| accept',t['accept_ids'],'| cost',t['expected_cost'])
sys.exit(0 if t['p_star']==0.95 and len(t['review_ids'])==6 and t['accept_ids']==['rel008'] else 1)" && ok triage-1-20 || bad triage-1-20
echo "== 5. triage 1/5 (expect p* 0.8, empty queue)"
curl -s "$BASE/api/runs/baseline/triage?c_review=1&c_miss=5" | python3 -c "
import json,sys;t=json.load(sys.stdin)['threshold'];print('   p*',t['p_star'],'| review',t['review_ids']);sys.exit(0 if t['p_star']==0.8 and t['review_ids']==[] else 1)" && ok triage-1-5 || bad triage-1-5
echo "== 6. footnote-12 walkthrough (expect 8 tables, 1 relation, calibration fitted 3/13 in the LAB variant)"
curl -s "$BASE/api/runs/footnote-12/walkthrough" | python3 -c "
import json,sys;w=json.load(sys.stdin);by={s['id']:s for s in w['stages']}
print('   tables',by['S3']['facts']['tables'],'| relations',by['S7']['facts']['relations'],'| calib',by['S8']['facts']['calibration_check']['detail'][:48])
sys.exit(0 if by['S3']['facts']['tables']==8 and by['S7']['facts']['relations']==1 else 1)" && ok fn12 || bad fn12
echo "== 7. matrix (expect 18 rows; dpi-400 recall 0.14; lenient P 0.70)"
curl -s "$BASE/api/matrix" | python3 -c "
import json,sys;r=json.load(sys.stdin);m={x['id']:x for x in r}
print('   rows',len(r),'| dpi-400 recall',m['dpi-400']['summary']['recall'],'| lenient P',m['lenient-lexical']['summary']['precision'],'| psm-6',m['psm-6']['state'])
sys.exit(0 if len(r)==18 and m['dpi-400']['summary']['recall']==0.14 else 1)" && ok matrix || bad matrix
echo "== 8. decision matrix asset (expect 8 stages, 43 options)"
curl -s "$BASE/decision_matrix.json" | python3 -c "
import json,sys;d=json.load(sys.stdin);n=sum(len(s['options']) for s in d['stages']);print('   stages',len(d['stages']),'| options',n,'|',d['version']);sys.exit(0 if len(d['stages'])==8 and n==43 else 1)" && ok decision-matrix || bad decision-matrix
echo "== 9. frontend buttons"
curl -s "$BASE/" | python3 -c "
import sys;h=sys.stdin.read();need=['btnWalk','btnTriage','btnMatrixDM','btnPresent','btnMatrix','btnDocs'];miss=[b for b in need if b not in h];print('   buttons present:',[b for b in need if b in h]);sys.exit(1 if miss else 0)" && ok frontend || bad frontend
echo "== 10. documents endpoint (any-PDF flow; expect a JSON list)"
curl -s "$BASE/api/documents" | python3 -c "
import json,sys;d=json.load(sys.stdin);print('   uploaded documents',len(d),'|',[(x['doc_id'],x['status']['state']) for x in d][:5]);sys.exit(0 if isinstance(d,list) else 1)" && ok documents || bad documents
echo "== 11. benchmarks store (expect >= 11 benchmarks, every file valid, no parse errors, shipped row where a baseline exists, btnBench)"
curl -s "$BASE/api/benchmarks" | python3 -c "
import json,sys,urllib.request;d=json.load(sys.stdin);ok=isinstance(d,list) and len(d)>=11
for b in d:
    x=json.load(urllib.request.urlopen('$BASE/api/benchmarks/'+b['id']));ok=ok and x['id']==b['id'] and len(x['rows'])==b['rows'] and b['parse_errors']==0 and (b['baseline'] is None or b['shipped_rows']>=1)
print('   benchmarks',len(d),'|',[(b['id'],b['rows'],b['scope']) for b in d])
h=urllib.request.urlopen('$BASE/').read().decode();print('   btnBench present:','btnBench' in h);sys.exit(0 if ok and 'btnBench' in h else 1)" && ok benchmarks || bad benchmarks
echo "== 12. PDF visual debugger (baseline, page render, proof, annotation schema, launcher)"
curl -s "$BASE/api/debugger/run?run_id=baseline" | python3 -c "import json,sys;d=json.load(sys.stdin);r=d['result'];print('   status',d['status'],'| relations',len(r['relations']));sys.exit(0 if d['status']=='completed' and len(r['relations'])==7 else 1)" && ok debugger-run || bad debugger-run
curl -s "$BASE/api/debugger/proof?run_id=baseline" | python3 -c "import json,sys;d=json.load(sys.stdin);print('   input match',d['input']['sha256_match'],'| config hash',d['configuration']['sha256'][:12],'| result hash',d['output']['result_sha256'][:12]);sys.exit(0 if d['input']['sha256_match'] and d['output']['counts']['relations']==7 else 1)" && ok debugger-proof || bad debugger-proof
curl -s -o /tmp/ftlink_debugger_page.png -w '%{http_code}' "$BASE/api/debugger/page/5" | grep -qx 200 && file /tmp/ftlink_debugger_page.png | grep -qi png && ok debugger-page || bad debugger-page
curl -s "$BASE/" | python3 -c "import sys;h=sys.stdin.read();sys.exit(0 if 'btnPdfDebugger' in h else 1)" && ok debugger-launcher || bad debugger-launcher
(curl -s "$BASE/pdf-debugger.html"; curl -s "$BASE/pdf-debugger-enhancements.js") | python3 -c "import sys;h=sys.stdin.read();need=['/api/debugger/run','/api/debugger/proof','pdf-debugger-enhancements.js','Report issue'];miss=[x for x in need if x not in h];print('   debugger assets missing:',miss);sys.exit(1 if miss else 0)" && ok debugger-ui || bad debugger-ui
if [ "$STARTED" = 1 ]; then pkill -f "uvicorn ftlink_app.api:app" >/dev/null 2>&1 || true; echo "server stopped (start it again for the demo: make serve)"; fi
[ $fail = 0 ] && echo "DEMO PREFLIGHT GREEN: numbers above are what you say" || { echo "DEMO PREFLIGHT FAILED: fix before the call (see /tmp/ftlink_demo_preflight.log)"; exit 1; }
