# Every tunable number the policy uses lives here, exactly once.
#
# The injection hard-block threshold in particular is defined ONLY here. It is
# not duplicated in Python: the gateway computes confidence, this file decides
# what confidence means.
package agentpay.thresholds

# Injection confidence at or above this is a hard block regardless of the
# weighted risk score. Sub-threshold injection still contributes 35% of the
# weighted score and can push a transaction into REQUIRE_APPROVAL.
injection_hard_block := 0.85

# Sub-threshold injection that still warrants a human.
injection_review := 0.5

# Weighted risk score (0-100) at or above which a human must approve.
score_review := 60

# Fraction of the hourly transaction allowance that triggers review.
velocity_review_ratio := 0.8
