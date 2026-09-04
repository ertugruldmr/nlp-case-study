#!/usr/bin/env bash
# Genuine alternate-document smoke through the public upload/run API.
#
# This proves that bytes from a different PDF and its requested configuration reach
# the sealed ftlink pipeline. It deliberately does NOT claim extraction accuracy:
# the alternate filing has source provenance and a prior manual spot-check, but no
# committed cell/relation gold set.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BASE_URL="${FTLINK_DEMO_BASE_URL:-http://127.0.0.1:8199}"
PACKAGED_PDF="$SCRIPT_DIR/fixtures/ozak_gyo_2013.pdf"
RESEARCH_PDF="$WORKSPACE_DIR/research/assets/second-doc/ozak-gyo-2013/source.pdf"
PDF_PATH="${FTLINK_ALTERNATE_PDF:-$([ -f "$PACKAGED_PDF" ] && printf '%s' "$PACKAGED_PDF" || printf '%s' "$RESEARCH_PDF")}" 
EXPECTED_SHA256="7bed2e05c84a467e2c797767f59a1087594526aead2362bd810f5d5e123a36bd"
BASELINE_SHA256="25e4afe4c27bd2b3bb17a943a323e265520e68981c349f300d9248b3f3bfd7e0"
TIMEOUT_SECONDS="${FTLINK_DEMO_TIMEOUT_SECONDS:-600}"

if [ ! -f "$PDF_PATH" ]; then
  echo "alternate PDF not found: $PDF_PATH" >&2
  exit 2
fi

actual_sha="$(shasum -a 256 "$PDF_PATH" | awk '{print $1}')"
if [ "$actual_sha" != "$EXPECTED_SHA256" ]; then
  echo "alternate PDF hash mismatch: expected $EXPECTED_SHA256, got $actual_sha" >&2
  echo "This recipe is evidence-bound; inspect a replacement PDF before changing the hash." >&2
  exit 2
fi
if [ "$actual_sha" = "$BASELINE_SHA256" ]; then
  echo "alternate PDF unexpectedly equals the baseline" >&2
  exit 2
fi

tmp_dir="$(mktemp -d "${TMPDIR:-/tmp}/ftlink-alt-demo.XXXXXX")"
trap 'rm -rf "$tmp_dir"' EXIT
upload_json="$tmp_dir/upload.json"
run_json="$tmp_dir/run.json"
status_json="$tmp_dir/status.json"
result_json="$tmp_dir/result.json"

curl -fsS "$BASE_URL/api/meta" >/dev/null || {
  echo "ftlink app is not reachable at $BASE_URL; start it with: cd app && make serve" >&2
  exit 2
}

echo "Uploading verified alternate PDF (Özak GYO 2013, sha256 ${actual_sha:0:12}…)"
curl -fsS \
  -F "file=@$PDF_PATH;type=application/pdf" \
  -F summary_pages_start=6 \
  -F summary_pages_end=8 \
  -F footnote_no=12 \
  -F extra_control_pages=10,11 \
  -F 'label=Özak GYO 2013 alternate-document smoke' \
  -F 'company=ÖZAK GAYRİMENKUL YATIRIM ORTAKLIĞI A.Ş. VE BAĞLI ORTAKLIKLARI' \
  -F period_end=2013-12-31 \
  -F currency=TL \
  -F ocr_lang=tur \
  "$BASE_URL/api/documents" >"$upload_json"

doc_id="$(python3 - "$upload_json" <<'PY'
import json, sys
value = json.load(open(sys.argv[1], encoding="utf-8"))
assert value["sha256"] == "7bed2e05c84a467e2c797767f59a1087594526aead2362bd810f5d5e123a36bd"
assert value["page_count"] == 91
assert value["summary_pages"] == [6, 8]
assert value["footnote_no"] == 12
assert value["extra_control_pages"] == [10, 11]
assert value["company"] == "ÖZAK GAYRİMENKUL YATIRIM ORTAKLIĞI A.Ş. VE BAĞLI ORTAKLIKLARI"
assert value["period_end"] == "2013-12-31"
assert value["currency"] == "TL" and value["ocr_lang"] == "tur"
print(value["doc_id"])
PY
)"
run_id="doc-$doc_id"

curl -fsS -X POST "$BASE_URL/api/documents/$doc_id/run" >"$run_json"
python3 - "$run_json" "$run_id" <<'PY'
import json, sys
value = json.load(open(sys.argv[1], encoding="utf-8"))
assert value["state"] == "started"
assert value["scenario"] == sys.argv[2]
PY

echo "Started $run_id; waiting for the real OCR/model pipeline"
started_at="$(date +%s)"
while :; do
  curl -fsS "$BASE_URL/api/documents/$doc_id" >"$status_json"
  state="$(python3 - "$status_json" <<'PY'
import json, sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["status"]["state"])
PY
)"
  if [ "$state" = "done" ]; then
    break
  fi
  if [ "$state" = "error" ]; then
    python3 - "$status_json" <<'PY'
import json, sys
value = json.load(open(sys.argv[1], encoding="utf-8"))
raise SystemExit("alternate run failed: " + value["status"].get("error", "unknown error"))
PY
  fi
  now="$(date +%s)"
  if [ $((now - started_at)) -ge "$TIMEOUT_SECONDS" ]; then
    echo "timed out after ${TIMEOUT_SECONDS}s; the server-side run may still be active" >&2
    exit 1
  fi
  sleep 2
done

curl -fsS "$BASE_URL/api/runs/$run_id/result" >"$result_json"
python3 - "$result_json" "$status_json" "$run_id" <<'PY'
import collections
import json
import sys

result = json.load(open(sys.argv[1], encoding="utf-8"))
status = json.load(open(sys.argv[2], encoding="utf-8"))
run_id = sys.argv[3]
expected_sha = "7bed2e05c84a467e2c797767f59a1087594526aead2362bd810f5d5e123a36bd"
baseline_sha = "25e4afe4c27bd2b3bb17a943a323e265520e68981c349f300d9248b3f3bfd7e0"
doc = result["document"]
cfg = result["run"]["config_echo"]

# Binding assertions are the claim this smoke is allowed to make.
assert status["status"]["state"] == "done"
assert status["status"]["scenario"] == run_id
assert doc["source_sha256"] == expected_sha and doc["source_sha256"] != baseline_sha
assert cfg["document"]["summary_pages"] == [6, 8]
assert cfg["document"]["footnote_no"] == 12
assert cfg["document"]["company"] == "ÖZAK GAYRİMENKUL YATIRIM ORTAKLIĞI A.Ş. VE BAĞLI ORTAKLIKLARI"
assert cfg["document"]["period_end"] == "2013-12-31"
assert cfg["document"]["currency"] == "TL"
assert cfg["ocr"]["lang"] == "tur"
assert cfg["confidence"]["extra_control_pages"] == [10, 11]
assert all(1 <= int(t["page"]) <= 91 for t in result.get("tables", []))

checks = collections.Counter(x["status"] for x in result.get("checks", []))
print("ALTERNATE PDF BINDING: PASS")
print(f"  run: {run_id}")
print(f"  source sha256: {doc['source_sha256']}")
print(f"  effective config: summary 6-8, footnote 12, period 2013-12-31, TL/tur, controls 10,11")
print(f"  observed only (not gold-scored): tables={len(result.get('tables', []))} "
      f"rows={len(result.get('rows', []))} cells={len(result.get('cells', []))} "
      f"relations={len(result.get('relations', []))} "
      f"checks={checks.get('pass', 0)}/{checks.get('fail', 0)}/{checks.get('not_evaluable', 0)}")
print("  accuracy claim: NONE; inspect the report/debugger or create independent gold labels")
PY

echo "Debugger: $BASE_URL/pdf-debugger.html?run=$run_id#review"
echo "Result:   $BASE_URL/api/runs/$run_id/result"
