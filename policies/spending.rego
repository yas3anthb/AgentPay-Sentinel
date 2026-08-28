# Budget enforcement: per-transaction cap, rolling daily cap, currency binding.
#
# Note on money and floats: amounts arrive as JSON numbers, so Rego compares
# them as float64. At payment magnitudes (<= 10 digits, 2dp) that is exact
# enough for these comparisons, and any residual rounding error can only push a
# borderline transaction into a BLOCK, never out of one. Hardening this to
# integer minor units is the right move before real money touches it.
package agentpay.spending

import data.agentpay.thresholds

deny contains "NO_SPENDING_POLICY_BOUND" if {
	not input.context.policy_found
}

deny contains "DELEGATION_POLICY_REVOKED" if {
	input.context.policy_revoked == true
}

deny contains "BUDGET_EXCEEDED" if {
	input.context.policy_found
	input.transaction.amount > input.context.per_transaction_limit
}

deny contains "DAILY_BUDGET_EXCEEDED" if {
	input.context.policy_found
	input.context.spent_today + input.transaction.amount > input.context.daily_limit
}

deny contains "CURRENCY_NOT_PERMITTED" if {
	input.context.policy_found
	input.transaction.currency != input.context.policy_currency
}

deny contains "VELOCITY_LIMIT_EXCEEDED" if {
	input.context.transactions_last_hour >= input.context.max_transactions_per_hour
}

require_approval contains "ABOVE_APPROVAL_THRESHOLD" if {
	input.context.policy_found
	input.transaction.amount >= input.context.approval_threshold
}

require_approval contains "VELOCITY_ELEVATED" if {
	input.context.max_transactions_per_hour > 0
	ratio := input.context.transactions_last_hour / input.context.max_transactions_per_hour
	ratio >= thresholds.velocity_review_ratio
	input.context.transactions_last_hour < input.context.max_transactions_per_hour
}
