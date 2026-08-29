"""Stage 3 — Intent & Content Security Analyzer.

Combines the deterministic rule layer, the LLM classifier, and source-trust
scoring into one evidence object. Like the risk engine, it emits no decision.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from gateway.analyzer import llm, rules, similarity, trust
from gateway.canonical import CanonicalTransaction
from gateway.schemas import SourceType


@dataclass(slots=True)
class AnalysisResult:
    injection_confidence: float
    injection_labels: list[str] = field(default_factory=list)
    rule_confidence: float = 0.0
    llm_confidence: float = 0.0
    similarity_confidence: float = 0.0
    similarity_label: str = ""
    classifier_degraded: bool = False
    classifier_degraded_reason: str = ""
    source_trust_score: float = 1.0
    evidence: list[dict] = field(default_factory=list)
    classifier_model: str = ""
    classifier_latency_ms: int = 0

    def to_dict(self) -> dict:
        return {
            "injection_confidence": self.injection_confidence,
            "injection_labels": self.injection_labels,
            "rule_confidence": self.rule_confidence,
            "llm_confidence": self.llm_confidence,
            "similarity_confidence": self.similarity_confidence,
            "similarity_label": self.similarity_label,
            "classifier_degraded": self.classifier_degraded,
            "classifier_degraded_reason": self.classifier_degraded_reason,
            "source_trust_score": self.source_trust_score,
            "classifier_model": self.classifier_model,
            "classifier_latency_ms": self.classifier_latency_ms,
            "evidence": self.evidence[:12],
        }


def combine(
    rule_confidence: float,
    llm_confidence: float,
    source: SourceType,
    similarity_confidence: float = 0.0,
) -> float:
    """Take the strongest of the deterministic rule layer, the LLM classifier,
    and the similarity layer, then amplify by how untrusted the provenance is.

    Deliberately not an average: averaging lets a confident detector get diluted
    by a hedging one, which is the wrong failure direction for a control that
    gates money. Because it is a `max`, the rule and similarity layers set a
    floor under the confidence even when the classifier is degraded — that is
    what keeps "classifier down" from meaning "no detection"."""
    base = max(rule_confidence, llm_confidence, similarity_confidence)
    if sum(1 for c in (rule_confidence, llm_confidence, similarity_confidence) if c > 0) >= 2:
        # Independent corroboration between any two layers is worth something.
        base = min(1.0, base + 0.05)
    return round(min(1.0, base * trust.injection_prior(source)), 3)


async def analyze(txn: CanonicalTransaction) -> AnalysisResult:
    fields = txn.untrusted.fields()
    source = txn.untrusted.merchant_source_type

    rule_result = rules.scan(fields)
    llm_result = await llm.classify(fields)
    sim_result = similarity.scan(fields)

    labels = set(rule_result.labels)
    labels.update(s for s in llm_result.signals if not s.startswith("classifier_unavailable"))
    if sim_result.label:
        labels.add(f"similar:{sim_result.label}")

    evidence = [
        {
            "layer": "rules",
            "label": f.label,
            "field": f.field,
            "excerpt": f.excerpt,
            "why": f.description,
        }
        for f in rule_result.findings
    ]
    if llm_result.signals and not llm_result.degraded:
        evidence.append(
            {
                "layer": "llm",
                "label": ",".join(llm_result.signals[:5]),
                "field": "data_block",
                "excerpt": "",
                "why": f"{llm_result.model} confidence {llm_result.confidence}",
            }
        )
    if sim_result.confidence > 0:
        evidence.append(
            {
                "layer": "similarity",
                "label": sim_result.label or "sub-threshold",
                "field": "untrusted_fields",
                "excerpt": "",
                "why": f"resemblance to known injection patterns ({sim_result.confidence})",
            }
        )

    return AnalysisResult(
        injection_confidence=combine(
            rule_result.confidence,
            llm_result.confidence,
            source,
            similarity_confidence=sim_result.confidence,
        ),
        injection_labels=sorted(labels),
        rule_confidence=rule_result.confidence,
        llm_confidence=llm_result.confidence,
        similarity_confidence=sim_result.confidence,
        similarity_label=sim_result.label,
        classifier_degraded=llm_result.degraded,
        classifier_degraded_reason=llm_result.degraded_reason,
        source_trust_score=trust.trust_score(source),
        evidence=evidence,
        classifier_model=llm_result.model,
        classifier_latency_ms=llm_result.latency_ms,
    )
