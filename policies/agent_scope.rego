# Identity and delegated authority.
package agentpay.agent_scope

deny contains "INVALID_IDENTITY" if {
	input.identity.valid == false
}

deny contains code if {
	input.identity.valid == false
	some code in input.identity.reason_codes
}

deny contains "AGENT_NOT_REGISTERED" if {
	input.identity.valid
	not input.context.agent_registered
}

deny contains "AGENT_DEACTIVATED" if {
	input.context.agent_registered
	input.context.agent_active == false
}

deny contains "AGENT_SCOPE_VIOLATION" if {
	not "payments:authorize" in input.transaction.agent_scopes
}

deny contains "AGENT_CATEGORY_NOT_PERMITTED" if {
	count(input.context.agent_allowed_categories) > 0
	not input.context.merchant_category in input.context.agent_allowed_categories
}

deny contains "DELEGATION_USER_MISMATCH" if {
	input.transaction.user_id != input.identity.user_id
}
