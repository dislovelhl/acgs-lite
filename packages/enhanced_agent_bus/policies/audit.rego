package acgs.audit

# Audit Policy - Loggable decisions (ACGS-2 Compliance)
# NIST 800-53 AU-2, OWASP Logging
# Generates audit events for all decisions
# Constitutional Hash: cdd01ef066bc6cf2

default allow := false  # Audit before allow from other policies

audit_event := {
	"timestamp": time.now_ns(),
	"tenant_id": input.tenant_id,
	"user_id": input.user_id,
	"action": input.action,
	"resource": input.resource,
	"decision": decision,
	"constitutional_hash": input.constitutional_hash
}

decision := "allowed" if allow else "denied"

allow {
	input.constitutional_hash == "cdd01ef066bc6cf2"
	input.tenant_id != null
	# Delegate to other policies via input.allow
	input.allow == true
}

# Input validation
valid_input {
	input.action matches "^[a-zA-Z0-9_.-]+$"
}
