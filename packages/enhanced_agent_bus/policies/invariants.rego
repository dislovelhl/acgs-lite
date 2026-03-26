package acgs.invariants

import future.keywords.contains
import future.keywords.if
import future.keywords.in

# Constitutional Invariant Policy - Runtime enforcement of HARD invariants (Pillar 6)
# ACGS-2 Standard: 608508a9bd224290 (baseline)
# Six default HARD invariants enforced at OPA layer
# Constitutional Hash: 608508a9bd224290
# P99 eval <1ms: O(1) set membership, early exit patterns

default allow_amendment := false

# ---------------------------------------------------------------------------
# Invariant 1: MACI Separation of Powers
# Proposer must not be the same as validator or executor.
# ---------------------------------------------------------------------------
invariant_maci_separation if {
	# Role separation: all three roles must be distinct
	input.proposer_role != input.validator_role
	input.proposer_role != input.executor_role
	input.validator_role != input.executor_role
	# Agent ID separation: same agent must not fill multiple roles
	input.proposer_id != input.validator_id
	input.proposer_id != input.executor_id
	input.validator_id != input.executor_id
}

violation_maci contains msg if {
	not invariant_maci_separation
	msg := "INVARIANT VIOLATION [HARD]: MACI separation of powers - proposer, validator, and executor must be distinct roles AND distinct agents"
}

# ---------------------------------------------------------------------------
# Invariant 2: Fail-Closed Governance
# All governance checks must produce a definitive result (not null/error).
# ---------------------------------------------------------------------------
invariant_fail_closed if {
	input.governance_result != null
	input.governance_result != "error"
	input.governance_result != ""
}

violation_fail_closed contains msg if {
	not invariant_fail_closed
	msg := "INVARIANT VIOLATION [HARD]: Fail-closed governance - governance check must produce definitive result"
}

# ---------------------------------------------------------------------------
# Invariant 3: Append-Only Audit
# Audit operations must be append-only (no delete, no update, no truncate).
# OPTIMIZATION: O(1) set membership check for forbidden operations.
# ---------------------------------------------------------------------------
forbidden_audit_ops := {"delete", "update", "truncate", "drop"}

invariant_append_only_audit if {
	not input.audit_operation in forbidden_audit_ops
}

violation_append_only contains msg if {
	not invariant_append_only_audit
	msg := sprintf(
		"INVARIANT VIOLATION [HARD]: Append-only audit trail - operation '%s' is forbidden",
		[input.audit_operation],
	)
}

# ---------------------------------------------------------------------------
# Invariant 4: Constitutional Hash Required
# Every governance decision must carry a non-empty constitutional hash.
# ---------------------------------------------------------------------------
invariant_hash_required if {
	input.constitutional_hash != null
	input.constitutional_hash != ""
	count(input.constitutional_hash) > 0
}

violation_hash contains msg if {
	not invariant_hash_required
	msg := "INVARIANT VIOLATION [META]: Constitutional hash required on all governance paths"
}

# ---------------------------------------------------------------------------
# Invariant 5: Tenant Isolation
# Tenant ID must be present and requests must not cross tenant boundaries.
# OPTIMIZATION: Early exit on missing tenant_id before boundary check.
# ---------------------------------------------------------------------------
invariant_tenant_isolation if {
	input.tenant_id != null
	input.tenant_id != ""
	not _tenant_cross_boundary
}

_tenant_cross_boundary if {
	input.target_tenant_id
	input.target_tenant_id != input.tenant_id
}

violation_tenant contains msg if {
	not invariant_tenant_isolation
	msg := "INVARIANT VIOLATION [HARD]: Tenant isolation - cross-tenant access forbidden"
}

# ---------------------------------------------------------------------------
# Invariant 6: Human Approval for Constitutional Activation
# Constitutional changes require explicit human_approved flag.
# ---------------------------------------------------------------------------
invariant_human_approval if {
	input.change_type != "constitutional"
}

invariant_human_approval if {
	input.change_type == "constitutional"
	input.human_approved == true
}

violation_human_approval contains msg if {
	not invariant_human_approval
	msg := "INVARIANT VIOLATION [META]: Constitutional activation requires human approval"
}

# ---------------------------------------------------------------------------
# Aggregate: amendment is allowed only if ALL invariants pass
# ---------------------------------------------------------------------------
allow_amendment if {
	invariant_maci_separation
	invariant_fail_closed
	invariant_append_only_audit
	invariant_hash_required
	invariant_tenant_isolation
	invariant_human_approval
}

# Collect all violations into a single set
all_violations := violation_maci | violation_fail_closed | violation_append_only | violation_hash | violation_tenant | violation_human_approval

# Invariant manifest for tracking and versioning
invariant_manifest := {
	"version": "1.0.0",
	"invariant_count": 6,
	"constitutional_hash": "608508a9bd224290",
}
