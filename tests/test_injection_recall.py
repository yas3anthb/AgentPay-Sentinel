"""What the second detection layer actually buys.

The regex layer (`gateway/analyzer/rules.py`) is high-precision: it matches
known phrasings and requires specific word adjacency. `tests/data/
injection_holdout.json` holds novel paraphrases of the same malicious intents,
chosen so the regexes miss them. This test pins two things:

  * the regexes really do miss most of the held-out set (otherwise the number
    below is measuring nothing);
  * rules + similarity together recover most of it, with the LLM classifier
    switched off — so "classifier unavailable" is still two layers, not zero.

It also checks the clean controls stay near zero on both layers.
"""
from __future__ import annotations

import json
import pathlib

from gateway.analyzer import combine, rules, similarity
from gateway.schemas import SourceType

DATA = json.loads((pathlib.Path(__file__).parent / "data" / "injection_holdout.json").read_text())
NOVEL: list[str] = DATA["novel_injections"]
CLEAN: list[str] = DATA["clean_controls"]

REVIEW = 0.5  # policies/thresholds.rego: injection_review


def _rule_only(text: str) -> float:
    return rules.scan({"merchant_content": text}).confidence


def _rules_plus_similarity(text: str) -> float:
    """Classifier degraded (llm_confidence = 0), scraped-page provenance —
    the worst realistic case for these phrasings."""
    fields = {"merchant_content": text}
    return combine(
        _rule_only(text),
        0.0,
        SourceType.SCRAPED_PAGE,
        similarity_confidence=similarity.scan(fields).confidence,
    )


def test_regex_layer_alone_misses_most_novel_phrasings():
    caught = sum(1 for t in NOVEL if _rule_only(t) >= REVIEW)
    # If this ever gets high, the held-out set has drifted into phrasings the
    # regexes already handle and is no longer measuring the second layer.
    assert caught <= 3, f"regex alone caught {caught}/{len(NOVEL)}; refresh the held-out set"


def test_similarity_layer_recovers_most_novel_phrasings():
    with_second = sum(1 for t in NOVEL if _rules_plus_similarity(t) >= REVIEW)
    assert with_second >= 8, (
        f"rules+similarity caught only {with_second}/{len(NOVEL)} with the classifier off"
    )


def test_second_layer_is_a_strict_improvement_on_the_held_out_set():
    rule_only = sum(1 for t in NOVEL if _rule_only(t) >= REVIEW)
    with_second = sum(1 for t in NOVEL if _rules_plus_similarity(t) >= REVIEW)
    assert with_second > rule_only


def test_clean_controls_stay_low_on_both_layers():
    for text in CLEAN:
        assert _rule_only(text) < REVIEW, text
        assert _rules_plus_similarity(text) < REVIEW, text
        assert similarity.scan({"merchant_content": text}).label == "", text
