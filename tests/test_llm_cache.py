import json
from pathlib import Path

from ftlink.llm import LlmLinker, PROMPT


def test_cache_replay_offline(tmp_path):
    cache = tmp_path / "llm.jsonl"
    probe = LlmLinker("http://invalid.local/v1", "m", cache)
    cands = [("t1.r1", "flow", "Alımlar", "p2012=5")]
    prompt = PROMPT.format(label="X", values="p2012=5",
                           candidates="- id=t1.r1 | tablo: flow | satır: Alımlar | değerler: p2012=5")
    key = probe._key(prompt)
    cache.write_text(json.dumps({"key": key, "model": "m",
                                 "response": json.dumps({"links": [{"candidate_id": "t1.r1",
                                                                    "period": "p2012", "why": "eş"}]})}) + "\n")
    linker = LlmLinker("http://invalid.local/v1", "m", cache)  # no network possible
    assert linker.select("X", "p2012=5", cands) == {"t1.r1"}


def test_graceful_on_unreachable(tmp_path):
    linker = LlmLinker("http://127.0.0.1:9/v1", "m", tmp_path / "c.jsonl", timeout=1)
    assert linker.select("X", "p2012=5", [("a", "b", "c", "d")]) == set()
