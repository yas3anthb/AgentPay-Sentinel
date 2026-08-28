# Merchant trust. The registry is the authority — never the caller's own
# `merchant_verified` claim, which is attacker-controlled input.
package agentpay.merchant

deny contains "MERCHANT_BLOCKED" if {
	input.transaction.merchant_id in input.context.blocked_merchants
}

deny contains "MERCHANT_NOT_IN_ALLOWLIST" if {
	count(input.context.allowed_merchants) > 0
	not input.transaction.merchant_id in input.context.allowed_merchants
}

deny contains "UNVERIFIED_MERCHANT" if {
	input.context.require_verified_merchant == true
	not input.context.merchant_verified
}

deny contains "MERCHANT_VERIFICATION_SPOOFED" if {
	input.transaction.merchant_verified_claim == true
	input.context.merchant_known
	not input.context.merchant_verified
}

require_approval contains "UNKNOWN_MERCHANT" if {
	not input.context.merchant_known
	not input.context.require_verified_merchant
}

require_approval contains "ELEVATED_MERCHANT_RISK" if {
	input.risk.signals.merchant_risk_score >= 0.6
	input.context.merchant_known
	input.context.merchant_verified
}
