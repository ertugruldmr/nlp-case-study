"""The cross-encoder-unavailable path: degrade loudly, never crash the run."""
import builtins

from ftlink.linking import Linker


def test_ce_load_failure_scores_zero_and_records_unavailability(monkeypatch):
    real_import = builtins.__import__

    def failing(name, *args, **kwargs):
        if name == "sentence_transformers":
            raise ImportError("simulated offline first run")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", failing)
    lk = Linker("cross-encoder/mmarco-mMiniLMv2-L12-H384-v1")
    assert lk.ce_available is True
    scores = lk._ce_scores([("a", "b"), ("c", "d")])
    assert scores == [0.0, 0.0]
    assert lk.ce_available is False
    # subsequent calls stay on the degraded path without re-importing
    assert lk._ce_scores([("e", "f")]) == [0.0]
