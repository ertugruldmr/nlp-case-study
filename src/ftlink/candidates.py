"""Stage S6: candidate generation between summary items and footnote rows.

Four channels fused with weighted Reciprocal Rank Fusion:
- char n-gram TF-IDF cosine: morphology- and OCR-noise-robust lexical signal,
- token-set fuzzy ratio: a second, word-level lexical voter (recall-oriented here;
  the linking stage separately uses the same similarity as an acceptance baseline),
- dense embeddings (multilingual-e5-small, "query:" prefix on both sides, the
  documented convention for symmetric matching),
- value anchor: equal absolute amounts between the item's period values and the
  candidate row's values, period-scoped. High-multiplicity amounts are usually
  LEGITIMATE reconciliation chains, so the guard is role/hierarchy awareness in the
  linking stage, not a stop list.

Serialization stays label-centric: within one footnote the table title is constant
across candidates and adds no discriminative signal (measured).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

import numpy as np
from rapidfuzz import fuzz
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .normalize import norm_label, tr_lower


@dataclass
class SideRow:
    """A row prepared for matching (either side)."""
    row_id: str
    label: str
    role: str
    values: dict[str, Decimal] = field(default_factory=dict)  # period_id -> abs value

    @property
    def abs_values(self) -> set[Decimal]:
        return {abs(v) for v in self.values.values()}


@dataclass
class Candidate:
    summary_row_id: str
    footnote_row_id: str
    scores: dict[str, float]
    fused: float
    anchor_periods: list[tuple[str, str]] = field(default_factory=list)  # (summary_period, footnote_period)


def _ranks(scores: np.ndarray) -> np.ndarray:
    order = np.argsort(-scores, kind="stable")
    rk = np.empty_like(order)
    rk[order] = np.arange(1, len(order) + 1)
    return rk


class CandidateGenerator:
    def __init__(self, rrf_k: float = 10.0, anchor_weight: float = 3.0, top_k: int = 8,
                 use_dense: bool = True, dense_model: str = "intfloat/multilingual-e5-small",
                 dense_revision: str | None = None) -> None:
        self.rrf_k = rrf_k
        self.anchor_weight = anchor_weight
        self.top_k = top_k
        self.use_dense = use_dense
        self.dense_model_name = dense_model
        self.dense_revision = dense_revision
        self._dense = None

    def _dense_scores(self, queries: list[str], corpus: list[str]) -> np.ndarray:
        if self._dense is None:
            from sentence_transformers import SentenceTransformer

            # weights pinned to a snapshot hash: the lockfile pins packages only
            self._dense = SentenceTransformer(self.dense_model_name,
                                              revision=self.dense_revision)
        eq = self._dense.encode([f"query: {q}" for q in queries], normalize_embeddings=True)
        ec = self._dense.encode([f"query: {c}" for c in corpus], normalize_embeddings=True)
        return eq @ ec.T

    def generate(self, summary: list[SideRow], footnote: list[SideRow]) -> list[Candidate]:
        if not summary or not footnote:
            return []
        q_texts = [norm_label(s.label) for s in summary]
        c_texts = [norm_label(f.label) for f in footnote]

        vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))
        X = vec.fit_transform(c_texts + q_texts)
        tfidf = cosine_similarity(X[len(c_texts):], X[: len(c_texts)])

        fuzzy = np.array([[fuzz.token_set_ratio(tr_lower(s.label), tr_lower(f.label)) / 100.0
                           for f in footnote] for s in summary])

        anchor = np.zeros((len(summary), len(footnote)))
        anchor_periods: dict[tuple[int, int], list[tuple[str, str]]] = {}
        for si, s in enumerate(summary):
            for fi, f in enumerate(footnote):
                hits = [(sp, fp) for sp, sv in s.values.items() for fp, fv in f.values.items()
                        if abs(sv) == abs(fv) and abs(sv) != 0]
                if hits:
                    anchor[si, fi] = 1.0
                    anchor_periods[(si, fi)] = hits

        channels: list[tuple[np.ndarray, float]] = [(tfidf, 1.0), (fuzzy, 1.0), (anchor, self.anchor_weight)]
        if self.use_dense:
            channels.insert(1, (self._dense_scores(q_texts, c_texts), 1.0))

        out: list[Candidate] = []
        for si, s in enumerate(summary):
            fused = np.zeros(len(footnote))
            for mat, w in channels:
                fused += w / (self.rrf_k + _ranks(mat[si]))
            order = np.argsort(-fused, kind="stable")
            keep = set(order[: self.top_k].tolist()) | {fi for fi in range(len(footnote)) if anchor[si, fi] > 0}
            for fi in sorted(keep, key=lambda i: -fused[i]):
                f = footnote[fi]
                out.append(Candidate(
                    summary_row_id=s.row_id, footnote_row_id=f.row_id,
                    scores={
                        "tfidf": float(tfidf[si, fi]),
                        "fuzzy": float(fuzzy[si, fi]),
                        "anchor": float(anchor[si, fi]),
                        **({"dense": float(channels[1][0][si, fi])} if self.use_dense else {}),
                    },
                    fused=float(fused[fi]),
                    anchor_periods=anchor_periods.get((si, fi), []),
                ))
        return out
