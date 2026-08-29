# Budget enforcement: per-transaction cap, rolling daily cap, currency binding.
#
# Money is integer minor units here. The gateway (gateway/money.py) converts
# every amount, limit and threshold to a whole number of paise/cents before it
# reaches OPA, so every comparison below is an integer comparison — no float64,
# no binary rounding on a value that gates a payment.
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
