# Human-approval handling.
#
# The critical rule: an approval is bound to the exact transaction a human saw.
# If amount, merchant, or currency moved after the approval was granted, the
# approval is void — this is the "approve $12 of coffee, execute $1,200 of gift
# cards" attack.
#
# bound_amount and transaction.amount are both integer minor units (see
# gateway/money.py), so the `!=` below is an exact integer comparison — not a
# float-equality check that could miss a sub-cent drift.
package agentpay.approvals

import data.agentpay.thresholds

deny contains "APPROVAL_BINDING_MISMATCH" if {
	input.approval.present
	input.approval.bound_amount != input.transaction.amount
}

deny contains "APPROVAL_BINDING_MISMATCH" if {
	input.approval.present
	input.approval.bound_merchant_id != input.transaction.merchant_id
}

deny contains "APPROVAL_BINDING_MISMATCH" if {
	input.approval.present
	input.approval.bound_currency != input.transaction.currency
}

deny contains "APPROVAL_BINDING_MISMATCH" if {
	input.approval.present
	input.approval.bound_cart_hash != input.transaction.cart_hash
}

deny contains "APPROVAL_EXPIRED" if {
	input.approval.present
	input.approval.expired == true
}

deny contains "APPROVAL_INVALID" if {
	input.approval.present
	input.approval.valid == false
}

# A high weighted score with no single hard failure is exactly the case a human
# is good at and a rule is not.
require_approval contains "COMPOSITE_RISK_ELEVATED" if {
	input.risk.weighted_score >= thresholds.score_review
}
