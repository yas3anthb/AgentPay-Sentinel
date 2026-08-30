# Prompt-injection and classifier-availability rules.
package agentpay.injection

import data.agentpay.thresholds

# Hard block: unambiguous injection in content that reached the agent.
deny contains "PROMPT_INJECTION_HIGH_CONFIDENCE" if {
	input.security.injection_confidence >= thresholds.injection_hard_block
}

# --- what to do when the LLM classifier could not answer -------------------
#
# The original rule was: no classifier verdict -> BLOCK, always. That is the
# safe default and it is still the default here. But measurement changed the
# picture: `docs/latency.md` shows a small but real fraction of live requests
# where the OpenAI call exceeds its timeout. Under an unconditional block,
# every one of those is a DECLINED PAYMENT for a customer who did nothing
# wrong, and during a provider outage that is *every* payment.
#
# The distinction that matters is between two very different situations:
#
#   1. classifier down AND the deterministic layers already saw something
#      -> we have positive evidence of an attack. Deny. (Note the hard-block
#         rule above usually fires here on its own.)
#   2. classifier down AND the deterministic layers found nothing
#      -> we have a GAP IN EVIDENCE, not evidence of an attack.
#
# Case 2 is exactly what the three-way decision exists for. Escalating to a
# human is not a weakening of fail-closed: nothing is allowed without a
# verdict, it is just that the verdict comes from a person instead of a model.
# A false positive then costs one human review rather than a lost sale.
#
# This is opt-in via `context.degraded_classifier_requires_review`. With the
# flag off the behaviour is byte-for-byte the original unconditional deny.

deny contains "CLASSIFIER_UNAVAILABLE_FAIL_CLOSED" if {
	input.security.classifier_degraded == true
	not input.context.allow_degraded_classifier
	not escalate_degraded_to_human
}

escalate_degraded_to_human if {
	input.security.classifier_degraded == true
	input.context.degraded_classifier_requires_review == true
	not input.context.allow_degraded_classifier

	# Only when the layers that DID run found nothing. If they flagged
	# anything at all, this is case 1 and the deny above stands.
	input.security.deterministic_confidence < thresholds.injection_review
}

require_approval contains "CLASSIFIER_UNAVAILABLE_HUMAN_REVIEW" if {
	escalate_degraded_to_human
}

# Sub-threshold manipulation: a human looks at it.
require_approval contains "PROMPT_INJECTION_SUSPECTED" if {
	input.security.injection_confidence >= thresholds.injection_review
	input.security.injection_confidence < thresholds.injection_hard_block
}
