"""Stage 3a — deterministic injection rules.

Cheap, explainable, and runs before the model call so an obvious attack never
depends on an LLM being available. Each pattern carries a label and a weight;
labels flow into the audit log so a blocked transaction can be explained
without re-running anything.

This layer is deliberately high-precision rather than high-recall: it catches
known phrasings. The classifier layer is what generalises.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Rule:
    label: str
    pattern: re.Pattern[str]
    weight: float
    description: str


def _c(p: str) -> re.Pattern[str]:
    return re.compile(p, re.IGNORECASE)


RULES: tuple[Rule, ...] = (
    Rule(
        "instruction_override_phrase",
        _c(r"\b(ignore|disregard|forget|override)\s+(all\s+|any\s+|the\s+)?"
           r"(previous|prior|earlier|above|preceding|system)\s+"
           r"(instruction|instructions|prompt|prompts|rule|rules|message|messages)\b"),
        0.9,
        "classic prompt-override phrasing",
    ),
    Rule(
        "role_reassignment",
        _c(r"\b(you\s+are\s+now|from\s+now\s+on\s+you|act\s+as|pretend\s+to\s+be|"
           r"new\s+(system\s+)?(prompt|instructions?|role))\b"),
        0.7,
        "attempts to reassign the model's role",
    ),
    Rule(
        "verification_bypass_request",
        _c(r"\b(disable|skip|bypass|turn\s+off|suppress|omit)\s+"
           r"(the\s+)?(verification|validation|security|safety|check|checks|"
           r"2fa|mfa|confirmation|approval|review)\b"),
        0.95,
        "asks for a control to be switched off",
    ),
    Rule(
        "approval_suppression",
        _c(r"\b(do\s+not|don'?t|never|no\s+need\s+to)\s+"
           r"(ask|request|require|prompt|wait)\s+"
           r"(for\s+)?(the\s+)?(user\s+)?(confirmation|approval|permission|consent|authorization)\b"),
        0.95,
        "asks the agent to pay without human confirmation",
    ),
    Rule(
        "budget_bypass_request",
        _c(r"\b(ignore|exceed|raise|increase|remove|lift|bypass|override)\s+"
           r"(the\s+|your\s+|any\s+)?(spending\s+)?(budget|limit|limits|cap|caps|threshold|ceiling)\b"),
        0.9,
        "asks for the spending policy to be relaxed",
    ),
    Rule(
        "alternate_endpoint",
        _c(r"\b(use|send|post|redirect|route|forward)\s+(the\s+)?"
           r"(payment|funds|money|transaction|request|checkout)?\s*"
           r"(to\s+)?(this\s+|an?\s+|our\s+)?(alternate|alternative|different|new|backup|updated)\s+"
           r"(endpoint|url|address|api|gateway|link|account|wallet)\b"),
        0.95,
        "attempts to redirect funds or traffic",
    ),
    Rule(
        "credential_exfiltration",
        _c(r"\b(reveal|show|print|output|send|share|leak|repeat)\s+"
           r"(me\s+|us\s+)?(your\s+|the\s+|all\s+)?"
           r"(system\s+prompt|api[_\s-]?key|secret|secrets|token|tokens|credential|credentials|password)\b"),
        0.9,
        "asks for secrets or the system prompt",
    ),
    Rule(
        "urgency_pressure",
        _c(r"\b(urgent|immediately|right\s+now|without\s+delay|before\s+it'?s\s+too\s+late)\b"
           r"[^.]{0,60}\b(pay|purchase|buy|transfer|checkout|complete\s+the\s+order)\b"),
        0.45,
        "social-engineering urgency paired with a payment verb",
    ),
    Rule(
        "hidden_instruction_markers",
        _c(r"(<\s*!--|\[\s*system\s*\]|\{\{\s*system|###\s*system|<\|im_start\|>|"
           r"\bBEGIN\s+SYSTEM\b|\bEND\s+SYSTEM\b)"),
        0.75,
        "smuggled instruction delimiters or hidden markup",
    ),
    Rule(
        "amount_mutation_request",
        _c(r"\b(change|update|set|adjust|modify|correct)\s+(the\s+)?"
           r"(amount|total|price|quantity|currency|recipient|merchant)\s+"
           r"(to|into)\b"),
        0.8,
        "asks for the money-moving fields to be rewritten",
    ),
    Rule(
        "tool_invocation_injection",
        _c(r"\b(call|invoke|execute|run|trigger)\s+(the\s+)?"
           r"(tool|function|api|endpoint|command)\b[^.]{0,40}\b"
           r"(pay|transfer|checkout|authorize|purchase)\b"),
        0.85,
        "tries to drive tool use from inside content",
    ),
)

# Characters used to hide payloads from humans while leaving them visible to
# the model: zero-width joiners, bidi overrides, soft hyphens.
_INVISIBLE = re.compile(r"[​-‏‪-‮⁠-⁤﻿­]")


def normalize(text: str) -> str:
    """Undo the cheap obfuscations before matching: unicode confusables, hidden
    control characters, and runs of whitespace used to break up keywords."""
    text = unicodedata.normalize("NFKC", text)
    text = _INVISIBLE.sub("", text)
    return re.sub(r"[ \t ]+", " ", text)


@dataclass(frozen=True, slots=True)
class RuleFinding:
    label: str
    field: str
    weight: float
    excerpt: str
    description: str


@dataclass(frozen=True, slots=True)
class RuleScanResult:
    findings: tuple[RuleFinding, ...]
    confidence: float
    had_invisible_characters: bool

    @property
    def labels(self) -> list[str]:
        return sorted({f.label for f in self.findings})


def scan(fields: dict[str, str]) -> RuleScanResult:
    """Scan every untrusted field. Returns findings plus a confidence in
    [0, 1] taken from the strongest match, nudged up when several independent
    rules fire (one phrase can be a coincidence; three is a payload)."""
    findings: list[RuleFinding] = []
    saw_invisible = False

    for field_name, raw in fields.items():
        if not raw:
            continue
        if _INVISIBLE.search(raw):
            saw_invisible = True
        text = normalize(raw)
        for rule in RULES:
            m = rule.pattern.search(text)
            if m:
                start = max(0, m.start() - 30)
                findings.append(
                    RuleFinding(
                        label=rule.label,
                        field=field_name,
                        weight=rule.weight,
                        excerpt=text[start : m.end() + 30].strip()[:160],
                        description=rule.description,
                    )
                )

    if not findings:
        confidence = 0.08 if saw_invisible else 0.0
        return RuleScanResult((), confidence, saw_invisible)

    top = max(f.weight for f in findings)
    distinct = len({f.label for f in findings})
    confidence = min(1.0, top + 0.05 * (distinct - 1) + (0.05 if saw_invisible else 0.0))
    return RuleScanResult(tuple(findings), round(confidence, 3), saw_invisible)
