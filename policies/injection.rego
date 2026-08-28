# Prompt-injection and classifier-availability rules.
package agentpay.injection

import data.agentpay.thresholds

# Hard block: unambiguous injection in content that reached the agent.
deny contains "PROMPT_INJECTION_HIGH_CONFIDENCE" if {
	input.security.injection_confidence >= thresholds.injection_hard_block
}

# Fail closed. An unavailable classifier is not a clean bill of health.
deny contains "CLASSIFIER_UNAVAILABLE_FAIL_CLOSED" if {
	input.security.classifier_degraded == true
	not input.context.allow_degraded_classifier
}

# Sub-threshold manipulation: a human looks at it.
require_approval contains "PROMPT_INJECTION_SUSPECTED" if {
	input.security.injection_confidence >= thresholds.injection_review
	input.security.injection_confidence < thresholds.injection_hard_block
}
