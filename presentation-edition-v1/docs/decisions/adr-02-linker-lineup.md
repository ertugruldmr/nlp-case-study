---
slug: adr-02-linker-lineup
created: 2026-08-17T06:30:00+03:00
status: accepted
---

# ADR-02: Linker lineup = mmarco CE + value/role rules + lexical baseline (+ optional LLM select)

## Context
≥2 approaches with divergence analysis are graded. Two measured link physics:
reconciliation links (date-role labels, value-driven) vs item-semantic links
(text-driven). No Turkish reranker benchmark exists; in-document gold pairs decide.

## Options considered
[[decision-matrix]] S7: bge-reranker-v2-m3 (568M) vs mmarco-mMiniLM (118M) vs
mxbai (0.5B) — ALL saturate R@5 1.00 with labels+values serialization (E13/E14);
LLM-select local (P=1.00 deterministic, E15); NLI mDeBERTa (pending E17);
jina rerankers excluded (CC-BY-NC).

## Decision
A = mmarco-mMiniLM (parity at 1/5 size, 11ms/pair, Apache-2.0) with labels+values
dot-grouped serialization and rank-aware acceptance; B = value+role rules (roles
11/11 by 5 label rules; period-scoped anchors; hierarchy-aware); C = rapidfuzz
baseline (kept to demonstrate word-level failure); D = LLM-select via
OpenAI-compatible endpoint with committed response cache, DISABLED by default
(grading friction; presented at defense). Divergence recorded per relation
(agreement classes), measured pattern: b_only carries reconciliation links, text
approaches carry semantic links.

## Consequences
CPU-only default path; bge stays one config line away. REVISIT if Colab E13-ext
margins show bge materially more robust on hard negatives, or if the missing NLI
signal (E17) adds independent evidence for the noisy-OR fusion variant.
