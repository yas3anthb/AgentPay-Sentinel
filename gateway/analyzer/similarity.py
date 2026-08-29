"""Stage 3c — resemblance to known injection material.

A deterministic, offline second detector beside the regex layer. Where
`rules.py` matches exact phrasings, this catches:

  * near-duplicates of known payloads (an attacker lightly rewording one), via
    character-shingle Jaccard against `CANONICAL_ATTACKS`;
  * novel paraphrases of a known malicious intent — words no rule anticipated —
    via co-occurrence of `INTENT_CLUSTERS` facet groups within a short window.

It emits a confidence in [0, 1] and an optional label. It never decides, and it
is intentionally reachable with the LLM classifier down: "classifier
unavailable" should still mean two detection layers, not zero.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

from gateway.analyzer.attack_corpus import CANONICAL_ATTACKS, INTENT_CLUSTERS
from gateway.analyzer.rules import normalize

_TOKEN = re.compile(r"[a-z0-9']+")
_SHINGLE_N = 4
_INTENT_WINDOW = 16  # tokens; matched facet words must fall within this span
_LABEL_GATE = 0.5    # below this, contributes to confidence but names no label

_CORPUS_SHINGLES: list[set[str]] | None = None


@dataclass(frozen=True, slots=True)
class SimilarityResult:
    confidence: float
    label: str


def _shingles(text: str) -> set[str]:
    squished = re.sub(r"\s+", " ", text).strip()
    if len(squished) < _SHINGLE_N:
        return {squished} if squished else set()
    return {squished[i : i + _SHINGLE_N] for i in range(len(squished) - _SHINGLE_N + 1)}


def _corpus_shingles() -> list[set[str]]:
    global _CORPUS_SHINGLES
    if _CORPUS_SHINGLES is None:
        _CORPUS_SHINGLES = [_shingles(a) for a in CANONICAL_ATTACKS]
    return _CORPUS_SHINGLES


def _best_jaccard(field_shingles: set[str]) -> float:
    if not field_shingles:
        return 0.0
    best = 0.0
    for corpus in _corpus_shingles():
        inter = len(field_shingles & corpus)
        if not inter:
            continue
        best = max(best, inter / len(field_shingles | corpus))
    return best


def _within_window(hit_positions: list[list[int]], window: int) -> bool:
    """True if one representative from every matched facet fits in `window`
    tokens. Sliding window over all marks, O(n log n)."""
    n_facets = len(hit_positions)
    marks = sorted((p, fi) for fi, ps in enumerate(hit_positions) for p in ps)
    counts: dict[int, int] = defaultdict(int)
    distinct = 0
    left = 0
    for right in range(len(marks)):
        _, fr = marks[right]
        if counts[fr] == 0:
            distinct += 1
        counts[fr] += 1
        while marks[right][0] - marks[left][0] > window:
            _, fl = marks[left]
            counts[fl] -= 1
            if counts[fl] == 0:
                distinct -= 1
            left += 1
        if distinct == n_facets:
            return True
    return False


def _intent_score(tokens: list[str]) -> tuple[float, str]:
    if not tokens:
        return 0.0, ""
    positions: dict[str, list[int]] = defaultdict(list)
    for i, tok in enumerate(tokens):
        positions[tok].append(i)

    best_conf, best_label = 0.0, ""
    for label, facets in INTENT_CLUSTERS.items():
        hit_positions = [
            sorted(p for tok in facet for p in positions.get(tok, []))
            for facet in facets
        ]
        hit_positions = [h for h in hit_positions if h]
        if len(hit_positions) < 2:
            continue
        if not _within_window(hit_positions, _INTENT_WINDOW):
            continue
        frac = len(hit_positions) / len(facets)
        # A lone deterministic paraphrase match tops out at "a human should look"
        # (~0.75), not "hard block". Low-trust provenance (the source prior in
        # `combine`) can still push it over the block line; corroboration from
        # the regex or LLM layer escalates it directly.
        conf = min(0.75, 0.30 + 0.45 * frac)
        if conf > best_conf:
            best_conf, best_label = conf, label
    return best_conf, best_label


def scan(fields: dict[str, str]) -> SimilarityResult:
    best_conf, best_label = 0.0, ""
    for raw in fields.values():
        if not raw or not raw.strip():
            continue
        norm = normalize(raw).lower()
        tokens = _TOKEN.findall(norm)

        intent_conf, intent_label = _intent_score(tokens)
        if intent_conf > best_conf:
            best_conf, best_label = intent_conf, intent_label

        jac = _best_jaccard(_shingles(norm))
        jac_conf = jac if jac >= 0.5 else (0.5 if jac >= 0.35 else 0.0)
        if jac_conf > best_conf:
            best_conf, best_label = jac_conf, "resembles_known_injection"

    return SimilarityResult(
        round(best_conf, 3), best_label if best_conf >= _LABEL_GATE else ""
    )
