package acgs.constitutional

import future.keywords.contains
import future.keywords.if
import future.keywords.in

# Constitutional AI Policy - Enforce hash integrity (Pillar 1)
# ACGS-2 Standard: 608508a9bd224290 (baseline)
# OWASP API Sec Top 10: Broken Auth, NIST AI RMF 1.2 Integrity
# Supports dynamic hash evolution and versioning
# Constitutional Hash: 608508a9bd224290
# P99 eval <1ms: O(1) object lookups, early exit patterns

default allow := false

# Import evolution policy for transition management
import data.acgs.constitutional_evolution as evolution

# OPTIMIZATION: Pre-compute feature set for O(1) deprecated feature lookup
# Converts ["eval", "other"] -> {"eval": true, "other": true}
feature_set[feat] := true if {
	some feat in input.features
}

# OPTIMIZATION: Static set of deprecated features for O(1) lookup
deprecated_feature_names := {"eval", "legacy_sync"}

# Main allow rule with evolution support
allow if {
	is_valid_constitutional_hash
	not deprecated_features_used
	input.tenant_id != null  # Cross-policy tenant enforcement
}

# Hash validation: Check against active hash or valid transition hashes
# OPTIMIZATION: Direct equality checks are indexed by OPA
is_valid_constitutional_hash if {
	# Primary validation: exact match with active hash
	input.constitutional_hash == data.constitutional.active_hash.hash
}

is_valid_constitutional_hash if {
	# Fallback: exact match with baseline hash (for backward compatibility)
	input.constitutional_hash == "608508a9bd224290"
	not data.constitutional.active_hash.hash  # Only if no active hash set
}

is_valid_constitutional_hash if {
	# Grace period validation: hash is in valid transition set
	evolution.is_in_grace_period
	input.constitutional_hash in evolution.valid_hashes_during_transition
}

# OPTIMIZATION: O(1) intersection check instead of O(n) iteration
# Check if any feature is in the deprecated set using set intersection
deprecated_features_used if {
	some feat in deprecated_feature_names
	feature_set[feat]
}

# Metrics: constitutional violations (P99 eval <1ms)
violation contains msg if {
	not allow
	msg := sprintf(
		"Constitutional hash mismatch or deprecated features detected. Expected: %v, Got: %v",
		[expected_hash, input.constitutional_hash]
	)
}

# Expected hash for violation reporting
expected_hash := data.constitutional.active_hash.hash if {
	data.constitutional.active_hash.hash
} else := "608508a9bd224290"

# Audit event for constitutional policy evaluation
audit_event := {
	"timestamp": time.now_ns(),
	"tenant_id": input.tenant_id,
	"action": input.action,
	"resource": input.resource,
	"constitutional_hash": input.constitutional_hash,
	"active_hash": data.constitutional.active_hash.hash,
	"decision": decision,
	"in_grace_period": evolution.is_in_grace_period,
	"version": data.constitutional.active_hash.version
}

decision := "allowed" if allow else "denied"

# Helper: Check if current version is active
is_active_version(version_id) if {
	data.constitutional.active_hash.version == version_id
}

# Helper: Get active constitutional version
active_version := data.constitutional.active_hash.version if {
	data.constitutional.active_hash.version
} else := "1.0.0"

# Helper: Get active constitutional hash
active_hash := data.constitutional.active_hash.hash if {
	data.constitutional.active_hash.hash
} else := "608508a9bd224290"
