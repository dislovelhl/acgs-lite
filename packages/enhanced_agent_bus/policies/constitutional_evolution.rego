package acgs.constitutional_evolution

import future.keywords.contains
import future.keywords.if
import future.keywords.in

# Constitutional Evolution Policy - Manage hash transitions and amendments
# ACGS-2 Constitutional Evolution System
# Supports grace periods, amendment validation, and MACI enforcement
# Constitutional Hash: 608508a9bd224290

# Grace period configuration (5 minutes = 300 seconds)
grace_period_seconds := 300

# Default values
default is_in_grace_period := false
default allow_amendment := false

# Grace period: Check if current time is within transition grace period
is_in_grace_period if {
	data.constitutional.transition.start_time
	current_time := time.now_ns() / 1000000000  # Convert to seconds
	start_time := data.constitutional.transition.start_time
	elapsed := current_time - start_time
	elapsed < grace_period_seconds
}

# Valid hashes during transition: old hash + new hash
valid_hashes_during_transition contains hash if {
	# Include previous hash during grace period
	hash := data.constitutional.transition.previous_hash
	is_in_grace_period
}

valid_hashes_during_transition contains hash if {
	# Include new hash during grace period
	hash := data.constitutional.transition.new_hash
	is_in_grace_period
}

valid_hashes_during_transition contains hash if {
	# Always include active hash
	hash := data.constitutional.active_hash.hash
}

# Amendment proposal validation
allow_amendment if {
	# Validate amendment proposal structure
	is_valid_amendment_proposal
	# Check MACI permissions
	has_amendment_permission
	# Validate against current constitution
	validates_against_current_constitution
}

# Validate amendment proposal structure
is_valid_amendment_proposal if {
	# Must have proposal_id
	input.amendment.proposal_id
	# Must have proposed_changes
	input.amendment.proposed_changes
	# Must have justification (min 10 chars)
	count(input.amendment.justification) >= 10
	# Must have target_version
	input.amendment.target_version
	# Must have proposer_agent_id
	input.amendment.proposer_agent_id
}

# Check MACI permissions for amendments
has_amendment_permission if {
	# Amendment proposals require LEGISLATIVE role
	input.agent_role == "legislative"
	input.action == "propose_amendment"
}

# OPTIMIZATION: Judicial actions as object for O(1) lookup
judicial_actions := {"approve_amendment": true, "reject_amendment": true}

has_amendment_permission if {
	# Amendment approvals require JUDICIAL role
	input.agent_role == "judicial"
	judicial_actions[input.action]
}

has_amendment_permission if {
	# Manual rollback requires JUDICIAL role
	input.agent_role == "judicial"
	input.action == "rollback_amendment"
}

# Validate amendment against current constitution
validates_against_current_constitution if {
	# Amendment target version must match active version
	input.amendment.target_version == data.constitutional.active_hash.version
}

validates_against_current_constitution if {
	# Or target a specific version in history
	data.constitutional.versions[input.amendment.target_version]
}

# Amendment impact validation
is_high_impact_amendment if {
	# High impact if impact_score >= 0.8
	input.amendment.impact_score >= 0.8
}

is_medium_impact_amendment if {
	# Medium impact if 0.5 <= impact_score < 0.8
	input.amendment.impact_score >= 0.5
	input.amendment.impact_score < 0.8
}

is_low_impact_amendment if {
	# Low impact if impact_score < 0.5
	input.amendment.impact_score < 0.5
}

# Approval requirements based on impact
requires_multi_approver if {
	is_high_impact_amendment
}

requires_single_approver if {
	is_low_impact_amendment
}

requires_two_approvers if {
	is_medium_impact_amendment
}

# OPTIMIZATION: Critical fields as object for O(1) lookup instead of array iteration
critical_fields_set := {
	"constitutional_hash": true,
	"maci_enforcement": true,
	"audit_required": true,
	"tenant_isolation": true
}

# Critical field protection - these fields cannot be modified via amendments
# Uses O(1) object key lookup instead of O(n) array search
is_critical_field(field) if {
	critical_fields_set[field]
}

# Validate amendment doesn't modify critical fields
no_critical_field_changes if {
	# Check that no critical fields are being modified
	not amendment_modifies_critical_fields
}

amendment_modifies_critical_fields if {
	# Check if any proposed change targets a critical field
	some field
	input.amendment.proposed_changes[field]
	is_critical_field(field)
}

# Transition state helpers
is_transition_active if {
	data.constitutional.transition.start_time
	is_in_grace_period
}

transition_progress_percent := progress if {
	is_transition_active
	current_time := time.now_ns() / 1000000000
	start_time := data.constitutional.transition.start_time
	elapsed := current_time - start_time
	progress := (elapsed / grace_period_seconds) * 100
} else := 0

# Audit event for amendment operations
amendment_audit_event := {
	"timestamp": time.now_ns(),
	"action": input.action,
	"agent_id": input.agent_id,
	"agent_role": input.agent_role,
	"amendment_id": input.amendment.proposal_id,
	"target_version": input.amendment.target_version,
	"impact_score": input.amendment.impact_score,
	"is_high_impact": is_high_impact_amendment,
	"requires_multi_approver": requires_multi_approver,
	"has_permission": has_amendment_permission,
	"modifies_critical_fields": amendment_modifies_critical_fields,
	"decision": amendment_decision,
	"constitutional_hash": data.constitutional.active_hash.hash
}

amendment_decision := "allowed" if allow_amendment else "denied"

# Violation messages for amendments
amendment_violation contains msg if {
	not has_amendment_permission
	msg := sprintf(
		"MACI violation: Agent role '%v' not authorized for action '%v'",
		[input.agent_role, input.action]
	)
}

amendment_violation contains msg if {
	amendment_modifies_critical_fields
	msg := "Amendment attempts to modify critical protected fields"
}

amendment_violation contains msg if {
	not validates_against_current_constitution
	msg := sprintf(
		"Amendment target version '%v' does not match active version '%v'",
		[input.amendment.target_version, data.constitutional.active_hash.version]
	)
}

amendment_violation contains msg if {
	not is_valid_amendment_proposal
	msg := "Invalid amendment proposal structure or missing required fields"
}

# Transition metrics
transition_metrics := {
	"is_active": is_transition_active,
	"progress_percent": transition_progress_percent,
	"grace_period_seconds": grace_period_seconds,
	"valid_hashes": valid_hashes_during_transition,
	"previous_hash": data.constitutional.transition.previous_hash,
	"new_hash": data.constitutional.transition.new_hash,
	"start_time": data.constitutional.transition.start_time
}

# Helper: Get transition remaining time in seconds
transition_remaining_seconds := remaining if {
	is_transition_active
	current_time := time.now_ns() / 1000000000
	start_time := data.constitutional.transition.start_time
	elapsed := current_time - start_time
	remaining := grace_period_seconds - elapsed
} else := 0
