package acgs.multitenant

# Multi-tenant isolation policy - Mandatory tenant_id (ACGS-2 Standard)
# NIST SP 800-207, OWASP Multi-Tenancy Top 10
# Enforces tenant isolation: deny if tenant_id missing/null/empty
# Constitutional Hash: cdd01ef066bc6cf2

default allow := false

# Allow if tenant_id is present, non-null, non-empty, and valid format (UUID-like)
allow {
	input.tenant_id != null
	input.tenant_id != ""
	is_valid_tenant_id(input.tenant_id)
	input.constitutional_hash == "cdd01ef066bc6cf2"
}

# Deny cross-tenant access
deny_cross_tenant {
	input.tenant_id != input.context.target_tenant_id
}

# Input validation: tenant_id format (UUID v4 regex safe)
is_valid_tenant_id(id) {
	id matches "^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
}

# Metrics: tenant isolation violations
violation[name] := msg {
	not allow
	msg := sprintf("Multi-tenant violation: missing/invalid tenant_id '%v'", [input.tenant_id])
}
