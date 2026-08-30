"""Optional approach D: LLM-as-linker in the SELECT formulation.

One call per summary item: the model sees the item and every candidate footnote row
(id, table hint, label, values) and selects the related rows with a period and a
one-line justification, constrained by a JSON schema. Disabled by default.

Re-runnability: every response is committed to a JSONL cache keyed by a hash of
(model, prompt). A cache hit never touches the network, so a grader replays the
committed cache offline and byte-identically; determinism does not depend on any
provider's seed behavior. Some local servers (reasoning models) return the
constrained JSON in `reasoning_content` instead of `content`; both are read.
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from pathlib import Path

SCHEMA = {
    "type": "object", "required": ["links"],
    "properties": {"links": {"type": "array", "items": {
        "type": "object", "required": ["candidate_id", "period", "why"],
        "properties": {"candidate_id": {"type": "string"},
                       "period": {"type": "string"},
                       "why": {"type": "string", "maxLength": 200}}}}},
}

PROMPT = """Bir bağımsız denetim raporunda özet finansal tablo kalemi ile dipnot \
tablolarındaki satırlar arasında satır seviyesinde ilişki kuruyorsun.

ÖZET TABLO KALEMİ: "{label}" | dönem değerleri: {values}

DİPNOT SATIR ADAYLARI:
{candidates}

HER dönem değeri için AYRI AYRI, bu kaleme karşılık gelen TÜM satırları seç \
(açılış/kapanış bakiyeleri, net defter değeri ve toplam satırları dahil; aynı tutarı \
taşıyan her uygun satır bir ilişkidir). Değer eşitliği ve muhasebe anlamını birlikte \
kullan; emin olmadıklarını dahil etme."""


class LlmLinker:
    def __init__(self, base_url: str, model: str, cache_path: Path,
                 api_key_env: str = "FTLINK_LLM_API_KEY", timeout: int = 120) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.cache_path = cache_path
        self.timeout = timeout
        self.api_key = os.environ.get(api_key_env, "")
        self._cache: dict[str, str] = {}
        if cache_path.exists():
            for line in cache_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rec = json.loads(line)
                    self._cache[rec["key"]] = rec["response"]

    def _key(self, prompt: str) -> str:
        return hashlib.sha256(f"{self.model}\n{prompt}".encode()).hexdigest()

    def _call(self, prompt: str) -> str:
        key = self._key(prompt)
        if key in self._cache:
            return self._cache[key]
        body = json.dumps({
            "model": self.model, "temperature": 0, "max_tokens": 2000,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_schema", "json_schema": {
                "name": "links", "strict": True, "schema": SCHEMA}},
        }).encode()
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(f"{self.base_url}/chat/completions", body, headers)
        with urllib.request.urlopen(req, timeout=self.timeout) as f:
            resp = json.load(f)
        msg = resp["choices"][0]["message"]
        content = msg.get("content") or msg.get("reasoning_content") or "{}"
        # only VALID JSON enters the committed cache: a malformed response must be
        # retried on the next run, not replayed forever
        json.loads(content)
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        with self.cache_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"key": key, "model": self.model, "response": content},
                                ensure_ascii=False) + "\n")
        self._cache[key] = content
        return content

    def select(self, label: str, values_txt: str,
               candidates: list[tuple[str, str, str, str]]) -> set[str]:
        """candidates: (candidate_id, table_hint, label, values_txt) -> picked ids."""
        cand_lines = "\n".join(f"- id={cid} | tablo: {hint} | satır: {lab} | değerler: {vals}"
                               for cid, hint, lab, vals in candidates)
        prompt = PROMPT.format(label=label, values=values_txt, candidates=cand_lines)
        try:
            out = json.loads(self._call(prompt))
            return {l["candidate_id"] for l in out.get("links", [])}
        except Exception:
            return set()
