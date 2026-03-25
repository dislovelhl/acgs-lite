package acgs.rbac

import future.keywords.contains
import future.keywords.if
import future.keywords.in

# RBAC Policy - Stricter least-privilege, tenant-scoped (ACGS-2 Enhanced)
# NIST 800-53 AC-6, OWASP A01:2021 Broken Access Control
# Constitutional Hash: 608508a9bd224290
# P99 eval <1ms: O(1) object lookups instead of array iteration
# OPA Performance: Using indexed set lookups for sub-millisecond evaluation

default allow := false

# OPTIMIZATION: Pre-compute role set as object for O(1) lookup
# Converts ["admin", "user"] -> {"admin": true, "user": true}
user_roles_set[role] := true if {
	some role in input.user.roles
}

# Allow if user has required role in tenant context
# Uses O(1) set membership instead of O(n) array iteration
allow if {
	user_roles_set[input.required_role]
	input.user.tenant_id == input.tenant_id
	input.constitutional_hash == "608508a9bd224290"
	not privilege_escalation_attempt
}

# Deny privilege escalation (stricter)
# Uses O(1) set lookup for role check
privilege_escalation_attempt if {
	input.required_role == "admin"
	not user_roles_set["admin"]
}

privilege_escalation_attempt if {
	input.action == "delete"
	not user_roles_set["admin"]
	not user_roles_set["owner"]
}

# Input validation: roles array non-empty, strings only (OWASP Injection prev)
valid_roles if {
	is_array(input.user.roles)
	count(input.user.roles) > 0
	every role in input.user.roles {
		regex.match("^[a-zA-Z0-9_-]+$", role)
	}
}

# Metrics: RBAC denials
violation contains msg if {
	not allow
	msg := sprintf("RBAC denial: role '%v' insufficient for '%v' in tenant '%v'", [input.required_role, input.action, input.tenant_id])
}
