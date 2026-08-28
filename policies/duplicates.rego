# Replay and duplicate protection. The gateway performs the stateful checks
# (Redis lock, stored idempotency record, fingerprint window) and reports the
# finding here so the decision still comes out of exactly one place.
package agentpay.duplicates

deny contains "DUPLICATE_IDEMPOTENCY_KEY" if {
	input.duplicate.idempotency_conflict == true
}

deny contains "DUPLICATE_TRANSACTION_FINGERPRINT" if {
	input.duplicate.fingerprint_conflict == true
}
