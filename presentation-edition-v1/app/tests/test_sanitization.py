"""Sanitization guard: the app may be shown to a bank.

Deny-list (fails): employer name, tenant counts, workspace paths, third-party names, e-mail addresses,
phone numbers, absolute home paths. Warn-list (printed, never fails): workspace-voice words. Forbidden
strings are assembled from parts so this file never carries them itself.
"""
import json
import re
import warnings
from pathlib import Path

from ftlink_app.paths import APP_ROOT

FILES = ("README.md", "src/ftlink_app/registry.py", "src/ftlink_app/documents.py", "src/ftlink_app/api.py",
         "src/ftlink_app/pdf_debugger.py", "frontend/pdf-debugger.html", "frontend/pdf-debugger-enhancements.js",
         "src/ftlink_app/benchmarks.py", "src/ftlink_app/benchmarks_sync.py", "benchmarks/SCHEMA.md",
         "frontend/index.html", "frontend/decision_matrix.json",
         *sorted(str(p.relative_to(APP_ROOT)) for p in (APP_ROOT / "benchmarks").glob("*.json")))


def _j(*parts: str) -> str:
    return "".join(parts)


def _load_deny_literals() -> dict[str, list[str]]:
    """Forbidden literals are read from an untracked local file, never committed.

    The strings this guard exists to catch are themselves the material that must not
    ship, so committing them would publish exactly what the guard protects. Supply them
    at tests/denylist.local.json (git-ignored, an object of category -> list of lowercase
    literals). Without that file the literal half of the guard is inert and only the
    shipped regex patterns below run, which is the correct behaviour for a clone.
    """
    p = Path(__file__).parent / "denylist.local.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


DENY_LITERALS: dict[str, list[str]] = _load_deny_literals()
DENY_PATTERNS: dict[str, re.Pattern[str]] = {
    "tenant count": re.compile(r"(?<![\d.,])(?:1[.,]?)?400\s*\+"),
    "absolute home path": re.compile(r"(?:/Users/|/home/|[A-Za-z]:\\Users\\)[\w.-]+"),
    "e-mail address": re.compile(r"[\w.%+-]+@[\w-]+(?:\.[\w-]+)*\.[a-z]{2,}", re.I),
    "phone number": re.compile(r"(?:\+90|\b0)[\s-]?\(?5\d{2}\)?[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}\b"),
}
WARN_WORDS = ("defense", "grader", "colab", "decisions/", "evidence/")


def _hits(text: str) -> list[tuple[int, str, str]]:
    out: list[tuple[int, str, str]] = []
    for n, line in enumerate(text.splitlines(), 1):
        low = line.lower()
        for kind, needles in DENY_LITERALS.items():
            out.extend((n, kind, x) for x in needles if x in low)
        for kind, rx in DENY_PATTERNS.items():
            out.extend((n, kind, m.group(0)) for m in rx.finditer(line))
    return out


def test_deny_list_catches_the_shapes():
    samples = ["x" + "@" + "example" + ".com", "/Users/" + "someone" + "/x", "/home/" + "someone",
               "400" + "+", "1.400" + "+", "1,400 " + "+", "+90 " + "532 " + "000 00 00"]
    for sample in samples:
        assert _hits(sample), sample
    for kind, needles in DENY_LITERALS.items():
        for needle in needles:
            assert _hits(needle), f"{kind}: {needle}"
    for clean in ["400 dpi", "+400.000 fark", "R@5 0,40", "0,531", "cross-encoder/mmarco"]:
        assert not _hits(clean), clean


def test_app_files_carry_no_denied_strings():
    problems = []
    for rel in FILES:
        text = (APP_ROOT / rel).read_text(encoding="utf-8")
        problems.extend(f"{rel}:{n}: {kind}: {found!r}" for n, kind, found in _hits(text))
    assert not problems, "\n".join(problems)


def test_workspace_voice_words_are_reported_not_failed():
    found = []
    for rel in FILES:
        for n, line in enumerate((APP_ROOT / rel).read_text(encoding="utf-8").splitlines(), 1):
            low = line.lower()
            found.extend(f"{rel}:{n}: {w}" for w in WARN_WORDS if w in low)
    for f in found:
        print("WARN workspace-voice:", f)
    if found:
        warnings.warn(f"{len(found)} workspace-voice hit(s) in app files (see -s output)", UserWarning)
