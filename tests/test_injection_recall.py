"""Detection quality on a held-out set — what each layer actually buys.

`tests/data/injection_holdout.json` has three groups:

  * hard_injections   — blunt phrasings the regex layer is expected to catch
  * novel_injections  — the same malicious intents, reworded so the regexes
                        miss them; the similarity layer's intent-cluster
                        co-occurrence is what should still fire
  * clean_commercial  — realistic merchant copy + buyer intent that must NOT
                        be flagged

The tests below pin the recall the second layer adds and the precision on the
clean set, and print a confusion matrix per layer configuration so the
trade-off is visible rather than asserted. A false positive here is not a
decline: it routes to REQUIRE_APPROVAL, i.e. one human review.
"""
from __future__ import annotations

import json
import pathlib

from gateway.analyzer import combine, rules, similarity
from gateway.schemas import SourceType

DATA = json.loads((pathlib.Path(__file__).parent / "data" / "injection_holdout.json").read_text())
HARD: list[str] = DATA["hard_injections"]
NOVEL: list[str] = DATA["novel_injections"]
CLEAN: list[str] = DATA["clean_commercial"]

REVIEW = 0.5  # policies/thresholds.rego: injection_review — at/above this a human looks


def _rule_only(text: str) -> float:
    return rules.scan({"merchant_content": text}).confidence


def _rules_plus_similarity(text: str) -> float:
    """Worst realistic case for a reworded attack: classifier degraded
    (llm_confidence = 0) and scraped-page provenance."""
    fields = {"merchant_content": text}
    return combine(
        _rule_only(text),
        0.0,
        SourceType.SCRAPED_PAGE,
        similarity_confidence=similarity.scan(fields).confidence,
    )


def _confusion(score) -> dict:
    inj = HARD + NOVEL
    tp = sum(1 for t in inj if score(t) >= REVIEW)
    fn = len(inj) - tp
    fp = sum(1 for t in CLEAN if score(t) >= REVIEW)
    tn = len(CLEAN) - fp
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    return {"tp": tp, "fn": fn, "fp": fp, "tn": tn, "precision": precision, "recall": recall}


def test_print_confusion_matrix_per_layer_config(capsys):
    """Not a pass/fail gate on its own — it makes the numbers visible. The
    asserts in the other tests are the gate."""
    configs = {
        "rules only": _rule_only,
        "rules + similarity (LLM off)": _rules_plus_similarity,
    }
    with capsys.disabled():
        print(f"\n  held-out set: {len(HARD)} hard + {len(NOVEL)} novel injections, "
              f"{len(CLEAN)} clean")
        print(f"  {'config':<30} {'TP':>3} {'FN':>3} {'FP':>3} {'TN':>3}  "
              f"{'precision':>9} {'recall':>7}")
        for name, fn in configs.items():
            m = _confusion(fn)
            print(f"  {name:<30} {m['tp']:>3} {m['fn']:>3} {m['fp']:>3} {m['tn']:>3}  "
                  f"{m['precision']:>9.2f} {m['recall']:>7.2f}")
        print("  (a false positive routes to REQUIRE_APPROVAL — one human review, not a decline)")


def test_regex_layer_alone_misses_most_novel_phrasings():
    caught = sum(1 for t in NOVEL if _rule_only(t) >= REVIEW)
    # If this climbs, the held-out set has drifted into phrasings the regexes
    # already handle and is no longer measuring the second layer.
    assert caught <= 5, f"regex alone caught {caught}/{len(NOVEL)} novel; refresh the set"


def test_regex_layer_still_catches_the_blunt_phrasings():
    caught = sum(1 for t in HARD if _rule_only(t) >= REVIEW)
    assert caught >= len(HARD) - 1, f"regex caught only {caught}/{len(HARD)} hard injections"


def test_similarity_layer_recovers_most_novel_phrasings():
    with_second = sum(1 for t in NOVEL if _rules_plus_similarity(t) >= REVIEW)
    assert with_second >= 0.70 * len(NOVEL), (
        f"rules+similarity caught only {with_second}/{len(NOVEL)} novel with the classifier off"
    )


def test_overall_recall_with_two_deterministic_layers():
    """Measured, not aspirational: ~0.8 recall at 1.0 precision with the LLM
    OFF. The remaining ~20% is what the LLM classifier is for — the point of
    this test is that "classifier down" is a real, bounded degradation, not a
    blind spot. Do NOT raise this by tuning the corpus against this file."""
    m = _confusion(_rules_plus_similarity)
    assert m["recall"] >= 0.80, m


def test_precision_on_clean_commercial_copy_is_high():
    """The number that matters for false-decline cost. Two deterministic layers
    on realistic merchant copy must keep false positives near zero — and a
    false positive is a human review, not a declined purchase."""
    m = _confusion(_rules_plus_similarity)
    assert m["fp"] <= 1, f"{m['fp']} false positives on {len(CLEAN)} clean texts"
    assert m["precision"] >= 0.95, m


def test_clean_controls_name_no_similarity_label():
    for text in CLEAN:
        assert similarity.scan({"merchant_content": text}).label == "", text


def test_second_layer_is_a_strict_improvement_on_the_novel_set():
    rule_only = sum(1 for t in NOVEL if _rule_only(t) >= REVIEW)
    with_second = sum(1 for t in NOVEL if _rules_plus_similarity(t) >= REVIEW)
    assert with_second > rule_only
