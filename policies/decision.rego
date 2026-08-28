# The Policy Decision Point.
#
# This is the ONLY place in AgentPay Sentinel that emits ALLOW,
# REQUIRE_APPROVAL, or BLOCK. Every other component contributes evidence.
# The gateway reads `result` and does what it says.
#
# Order of authority:
#   1. any deny  -> BLOCK          (deny-by-default; a single failure is fatal)
#   2. any require_approval -> REQUIRE_APPROVAL
#   3. otherwise -> ALLOW
package agentpay.decision

import data.agentpay.agent_scope
import data.agentpay.approvals
import data.agentpay.duplicates
import data.agentpay.injection
import data.agentpay.merchant
import data.agentpay.spending

# --- aggregate the rule packages -------------------------------------------

deny_reasons := union({
	injection.deny,
	spending.deny,
	merchant.deny,
	agent_scope.deny,
	approvals.deny,
	duplicates.deny,
})

approval_reasons := union({
	injection.require_approval,
	spending.require_approval,
	merchant.require_approval,
	approvals.require_approval,
})

# --- a granted, correctly-bound approval satisfies the review requirement ---

approval_satisfied if {
	input.approval.present
	input.approval.valid == true
	input.approval.expired == false
	input.approval.bound_amount == input.transaction.amount
	input.approval.bound_merchant_id == input.transaction.merchant_id
	input.approval.bound_currency == input.transaction.currency
	input.approval.bound_cart_hash == input.transaction.cart_hash
}

# --- the decision ----------------------------------------------------------

default decision := "BLOCK" # deny-by-default: no matching rule means no money moves

decision := "BLOCK" if {
	count(deny_reasons) > 0
}

decision := "REQUIRE_APPROVAL" if {
	count(deny_reasons) == 0
	count(approval_reasons) > 0
	not approval_satisfied
}

decision := "ALLOW" if {
	count(deny_reasons) == 0
	count(approval_reasons) == 0
}

decision := "ALLOW" if {
	count(deny_reasons) == 0
	count(approval_reasons) > 0
	approval_satisfied
}

# --- reason codes ----------------------------------------------------------

reason_codes := sort([r | some r in deny_reasons]) if {
	count(deny_reasons) > 0
}

reason_codes := sort([r | some r in approval_reasons]) if {
	count(deny_reasons) == 0
	count(approval_reasons) > 0
	not approval_satisfied
}

reason_codes := ["APPROVAL_SATISFIED"] if {
	count(deny_reasons) == 0
	count(approval_reasons) > 0
	approval_satisfied
}

reason_codes := ["POLICY_SATISFIED"] if {
	count(deny_reasons) == 0
	count(approval_reasons) == 0
}

# --- the object the gateway consumes ---------------------------------------

result := {
	"decision": decision,
	"reason_codes": reason_codes,
	"deny_reasons": sort([r | some r in deny_reasons]),
	"approval_reasons": sort([r | some r in approval_reasons]),
	"policy_version": input.context.policy_version,
	"weighted_score": input.risk.weighted_score,
}
