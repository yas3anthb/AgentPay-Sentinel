package agentpay.decision_test

import data.agentpay.decision

# A clean, fully-compliant transaction. Every other case in this file is this
# object with one field changed, so a test failure names the exact cause.
#
# Money is integer minor units (cents), matching gateway/money.py: 4999 == 49.99,
# 20000 == a 200.00 limit. Probabilities, risk scores and counts are NOT money
# and are left as-is.
base := {
	"identity": {"valid": true, "user_id": "user_1", "reason_codes": []},
	"transaction": {
		"user_id": "user_1",
		"agent_id": "agent_1",
		"delegation_id": "del_1",
		"merchant_id": "merch_acme",
		"merchant_verified_claim": true,
		"amount": 4999,
		"currency": "USD",
		"cart_hash": "cart_abc",
		"item_count": 1,
		"agent_scopes": ["payments:authorize"],
	},
	"security": {
		"injection_confidence": 0.02,
		"injection_labels": [],
		"classifier_degraded": false,
		"deterministic_confidence": 0.02,
		"source_trust_score": 0.95,
	},
	"risk": {
		"weighted_score": 12.5,
		"signals": {
			"injection_confidence": 0.02,
			"policy_violation_score": 0.0,
			"budget_anomaly_score": 0.25,
			"merchant_risk_score": 0.1,
			"velocity_risk_score": 0.1,
		},
	},
	"context": {
		"policy_found": true,
		"policy_version": "v1.4.2",
		"policy_revoked": false,
		"per_transaction_limit": 20000,
		"daily_limit": 50000,
		"policy_currency": "USD",
		"spent_today": 2000,
		"allowed_merchants": [],
		"blocked_merchants": [],
		"require_verified_merchant": true,
		"approval_threshold": 15000,
		"max_transactions_per_hour": 10,
		"transactions_last_hour": 1,
		"merchant_known": true,
		"merchant_verified": true,
		"merchant_category": "retail",
		"merchant_registry_risk": 0.1,
		"agent_registered": true,
		"agent_active": true,
		"agent_allowed_categories": [],
		"allow_degraded_classifier": false,
		"degraded_classifier_requires_review": false,
	},
	"approval": {"present": false},
	"duplicate": {"idempotency_conflict": false, "fingerprint_conflict": false},
}

with_txn(patch) := object.union(base, {"transaction": object.union(base.transaction, patch)})

with_ctx(patch) := object.union(base, {"context": object.union(base.context, patch)})

with_sec(patch) := object.union(base, {"security": object.union(base.security, patch)})

# --- happy path ------------------------------------------------------------

test_clean_transaction_allowed if {
	decision.result.decision == "ALLOW" with input as base
	decision.result.reason_codes == ["POLICY_SATISFIED"] with input as base
}

# --- the eight hard blocks -------------------------------------------------

test_injection_at_threshold_is_hard_block if {
	r := decision.result with input as with_sec({"injection_confidence": 0.85})
	r.decision == "BLOCK"
	"PROMPT_INJECTION_HIGH_CONFIDENCE" in r.reason_codes
}

test_injection_hard_block_ignores_low_total_score if {
	# Everything else is pristine and the weighted score is tiny: the hard
	# block must still fire. This is the rule the old design got wrong.
	inp := object.union(
		with_sec({"injection_confidence": 0.99}),
		{"risk": object.union(base.risk, {"weighted_score": 3})},
	)
	r := decision.result with input as inp
	r.decision == "BLOCK"
	"PROMPT_INJECTION_HIGH_CONFIDENCE" in r.reason_codes
}

test_budget_exceeded_blocks if {
	r := decision.result with input as with_txn({"amount": 50000})
	r.decision == "BLOCK"
	"BUDGET_EXCEEDED" in r.reason_codes
}

test_daily_budget_exceeded_blocks if {
	r := decision.result with input as with_ctx({"spent_today": 48000})
	r.decision == "BLOCK"
	"DAILY_BUDGET_EXCEEDED" in r.reason_codes
}

test_unverified_merchant_on_protected_policy_blocks if {
	r := decision.result with input as with_ctx({"merchant_verified": false})
	r.decision == "BLOCK"
	"UNVERIFIED_MERCHANT" in r.reason_codes
}

test_spoofed_verification_claim_blocks if {
	r := decision.result with input as with_ctx({
		"merchant_verified": false,
		"require_verified_merchant": false,
	})
	r.decision == "BLOCK"
	"MERCHANT_VERIFICATION_SPOOFED" in r.reason_codes
}

test_invalid_identity_blocks_with_underlying_code if {
	inp := object.union(base, {"identity": {
		"valid": false,
		"user_id": "user_1",
		"reason_codes": ["DELEGATION_REVOKED"],
	}})
	r := decision.result with input as inp
	r.decision == "BLOCK"
	"INVALID_IDENTITY" in r.reason_codes
	"DELEGATION_REVOKED" in r.reason_codes
}

test_duplicate_payment_blocks if {
	inp := object.union(base, {"duplicate": {
		"idempotency_conflict": true,
		"fingerprint_conflict": false,
	}})
	r := decision.result with input as inp
	r.decision == "BLOCK"
	"DUPLICATE_IDEMPOTENCY_KEY" in r.reason_codes
}

test_fingerprint_conflict_blocks if {
	inp := object.union(base, {"duplicate": {
		"idempotency_conflict": false,
		"fingerprint_conflict": true,
	}})
	r := decision.result with input as inp
	"DUPLICATE_TRANSACTION_FINGERPRINT" in r.reason_codes
}

test_amount_changed_after_approval_blocks if {
	inp := object.union(base, {"approval": {
		"present": true,
		"valid": true,
		"expired": false,
		"bound_amount": 1200,
		"bound_merchant_id": "merch_acme",
		"bound_currency": "USD",
		"bound_cart_hash": "cart_abc",
	}})
	r := decision.result with input as inp
	r.decision == "BLOCK"
	"APPROVAL_BINDING_MISMATCH" in r.reason_codes
}

test_merchant_swapped_after_approval_blocks if {
	inp := object.union(base, {"approval": {
		"present": true,
		"valid": true,
		"expired": false,
		"bound_amount": 4999,
		"bound_merchant_id": "merch_original",
		"bound_currency": "USD",
		"bound_cart_hash": "cart_abc",
	}})
	"APPROVAL_BINDING_MISMATCH" in decision.result.reason_codes with input as inp
}

# --- fail-closed on a degraded classifier ----------------------------------

test_degraded_classifier_fails_closed if {
	r := decision.result with input as with_sec({"classifier_degraded": true})
	r.decision == "BLOCK"
	"CLASSIFIER_UNAVAILABLE_FAIL_CLOSED" in r.reason_codes
}

test_degraded_classifier_tolerated_when_policy_says_so if {
	inp := object.union(
		with_sec({"classifier_degraded": true}),
		{"context": object.union(base.context, {"allow_degraded_classifier": true})},
	)
	decision.result.decision == "ALLOW" with input as inp
}

# --- graceful degradation: classifier down + deterministic layers clean ----

test_degraded_classifier_with_no_other_evidence_routes_to_human if {
	inp := object.union(
		with_sec({"classifier_degraded": true, "deterministic_confidence": 0.0}),
		{"context": object.union(base.context, {"degraded_classifier_requires_review": true})},
	)
	r := decision.result with input as inp
	r.decision == "REQUIRE_APPROVAL"
	"CLASSIFIER_UNAVAILABLE_HUMAN_REVIEW" in r.reason_codes
	not "CLASSIFIER_UNAVAILABLE_FAIL_CLOSED" in r.reason_codes
}

test_degraded_classifier_with_deterministic_hit_still_blocks if {
	# The rules/similarity layers flagged it. A gap in the LLM verdict does
	# not soften that — this is evidence of an attack, not absence of one.
	inp := object.union(
		with_sec({
			"classifier_degraded": true,
			"deterministic_confidence": 0.7,
			"injection_confidence": 0.7,
		}),
		{"context": object.union(base.context, {"degraded_classifier_requires_review": true})},
	)
	r := decision.result with input as inp
	r.decision == "BLOCK"
}

test_graceful_degradation_is_opt_in if {
	# Flag off (the base default) -> unchanged hard block, byte for byte.
	r := decision.result with input as with_sec({
		"classifier_degraded": true,
		"deterministic_confidence": 0.0,
	})
	r.decision == "BLOCK"
	"CLASSIFIER_UNAVAILABLE_FAIL_CLOSED" in r.reason_codes
}

# --- approval routing ------------------------------------------------------

test_above_threshold_requires_approval if {
	r := decision.result with input as with_txn({"amount": 17500})
	r.decision == "REQUIRE_APPROVAL"
	"ABOVE_APPROVAL_THRESHOLD" in r.reason_codes
}

test_sub_threshold_injection_requires_approval if {
	r := decision.result with input as with_sec({"injection_confidence": 0.6})
	r.decision == "REQUIRE_APPROVAL"
	"PROMPT_INJECTION_SUSPECTED" in r.reason_codes
}

test_high_composite_score_requires_approval if {
	inp := object.union(base, {"risk": object.union(base.risk, {"weighted_score": 72})})
	r := decision.result with input as inp
	r.decision == "REQUIRE_APPROVAL"
	"COMPOSITE_RISK_ELEVATED" in r.reason_codes
}

test_correctly_bound_approval_allows if {
	inp := object.union(with_txn({"amount": 17500}), {"approval": {
		"present": true,
		"valid": true,
		"expired": false,
		"bound_amount": 17500,
		"bound_merchant_id": "merch_acme",
		"bound_currency": "USD",
		"bound_cart_hash": "cart_abc",
	}})
	r := decision.result with input as inp
	r.decision == "ALLOW"
	r.reason_codes == ["APPROVAL_SATISFIED"]
}

# --- scope, velocity, allowlist -------------------------------------------

test_missing_scope_blocks if {
	r := decision.result with input as with_txn({"agent_scopes": ["catalog:read"]})
	r.decision == "BLOCK"
	"AGENT_SCOPE_VIOLATION" in r.reason_codes
}

test_blocked_merchant_blocks if {
	r := decision.result with input as with_ctx({"blocked_merchants": ["merch_acme"]})
	"MERCHANT_BLOCKED" in r.reason_codes
}

test_allowlist_excludes_other_merchants if {
	r := decision.result with input as with_ctx({"allowed_merchants": ["merch_other"]})
	"MERCHANT_NOT_IN_ALLOWLIST" in r.reason_codes
}

test_velocity_limit_blocks if {
	r := decision.result with input as with_ctx({"transactions_last_hour": 10})
	r.decision == "BLOCK"
	"VELOCITY_LIMIT_EXCEEDED" in r.reason_codes
}

test_velocity_elevated_requires_approval if {
	r := decision.result with input as with_ctx({"transactions_last_hour": 8})
	r.decision == "REQUIRE_APPROVAL"
	"VELOCITY_ELEVATED" in r.reason_codes
}

test_unbound_delegation_blocks if {
	r := decision.result with input as with_ctx({"policy_found": false})
	r.decision == "BLOCK"
	"NO_SPENDING_POLICY_BOUND" in r.reason_codes
}

test_revoked_policy_blocks if {
	r := decision.result with input as with_ctx({"policy_revoked": true})
	"DELEGATION_POLICY_REVOKED" in r.reason_codes
}

test_currency_mismatch_blocks if {
	r := decision.result with input as with_txn({"currency": "EUR"})
	"CURRENCY_NOT_PERMITTED" in r.reason_codes
}

test_deactivated_agent_blocks if {
	r := decision.result with input as with_ctx({"agent_active": false})
	"AGENT_DEACTIVATED" in r.reason_codes
}

test_user_mismatch_blocks if {
	r := decision.result with input as with_txn({"user_id": "user_someone_else"})
	"DELEGATION_USER_MISMATCH" in r.reason_codes
}

# --- deny-by-default -------------------------------------------------------

test_empty_input_is_blocked if {
	decision.decision == "BLOCK" with input as {}
}
