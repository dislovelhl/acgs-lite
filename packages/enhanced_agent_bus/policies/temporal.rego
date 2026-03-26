package acgs.temporal

import future.keywords.contains
import future.keywords.if
import future.keywords.in

# Temporal Ordering Policy for ACGS-2 Pipeline.
#
# Implements Agent-C-inspired temporal safety properties:
# each rule expresses a prerequisite action that MUST appear in
# input.action_history before the current action is permitted.
#
# Usage:
#   OPAClient.evaluate_with_history(
#       data={"action": "execute_action", "impact_score": 0.9, ...},
#       action_history=["constitutional_hash_verified", "maci_consensus_approved"],
#       policy_path="data.acgs.temporal.allow",
#   )
#
# The `action_history` field is a list of completed action labels from the
# current session, managed by the pipeline and stored in Redis.
#
# Constitutional Hash: 608508a9bd224290
# NIST 800-53 AC-3, AU-9 — Least Privilege, Audit Protection
# P99 eval <1ms: all rules use set membership (O(1) lookups)

default allow := false

# Pre-compute history as a set for O(1) membership checks.
history_set[item] if {
	some item in input.action_history
}

# ---------------------------------------------------------------------------
# Allow: no temporal violations → pass
# ---------------------------------------------------------------------------

# Constitutional hash: prefer data.acgs.constitutional_hash (updatable via OPA
# data API without policy rebuild) with the compile-time literal as fallback,
# so existing deployments without the data key are unaffected.
_expected_hash := data.acgs.constitutional_hash if {
	data.acgs.constitutional_hash != ""
} else := "608508a9bd224290"

allow if {
	count(violations) == 0
	input.constitutional_hash == _expected_hash
}

# ---------------------------------------------------------------------------
# Temporal safety rules
# Each rule fires a violation message when its ordering constraint is broken.
# ---------------------------------------------------------------------------

# 1. Policy modification requires a preceding constitutional validation.
#    Prevents agents from changing governance rules before hash is verified.
violations contains msg if {
	input.action in {"modify_policy", "apply_policy_change", "update_policy"}
	not history_set["constitutional_hash_verified"]
	msg := "temporal:modify_policy requires constitutional_hash_verified to precede it"
}

# 2. High-impact message execution requires MACI consensus to have been reached.
#    Prevents EXECUTOR role from acting before 2-of-3 MACI approval.
violations contains msg if {
	input.action in {"execute_action", "commit_governance_decision"}
	input.impact_score >= 0.8
	not history_set["maci_consensus_approved"]
	msg := "temporal:execute_action (impact>=0.8) requires maci_consensus_approved to precede it"
}

# 3. Any governance decision (approve/reject/deliver) requires hash verification first.
#    Core invariant: no governance outcome without constitutional grounding.
violations contains msg if {
	input.action in {
		"approve_message",
		"reject_message",
		"deliver_message",
		"audit_decision",
	}
	not history_set["constitutional_hash_verified"]
	msg := "temporal:governance_action requires constitutional_hash_verified to precede it"
}

# 4. HITL-gated delivery: messages with impact_score >= 0.8 must pass HITL first.
#    Prevents high-risk messages from bypassing the human-in-the-loop queue.
violations contains msg if {
	input.action == "deliver_message"
	input.impact_score >= 0.8
	not history_set["hitl_approved"]
	msg := "temporal:deliver_message (impact>=0.8) requires hitl_approved to precede it"
}

# 5. Audit writes require the decision to have been reached first.
#    Prevents fabricated audit entries before a real governance decision.
violations contains msg if {
	input.action == "write_audit"
	not history_set["governance_decision_reached"]
	msg := "temporal:write_audit requires governance_decision_reached to precede it"
}

# 6. Policy extraction (LEGISLATIVE role) requires session authentication first.
#    Prevents unauthenticated agents from reading constitutional rule sets.
violations contains msg if {
	input.action == "extract_rules"
	not history_set["session_authenticated"]
	msg := "temporal:extract_rules requires session_authenticated to precede it"
}

# ---------------------------------------------------------------------------
# Diagnostics: expose violation set for structured error logging
# ---------------------------------------------------------------------------

violation_count := count(violations)
