package acgs.resources

import future.keywords.contains
import future.keywords.if

# Resource Limits Policy - P99 <5ms enforcement (ACGS-2 Perf)
# NIST SP 800-53 SC-7, OWASP Resource Exhaustion
# Bounds CPU/Mem requests for low latency
# Constitutional Hash: cdd01ef066bc6cf2

default allow := false

allow if {
	input.resources.cpu_requests <= 250m
	input.resources.cpu_limits <= 500m
	input.resources.mem_requests <= 512Mi
	input.resources.mem_limits <= 1Gi
	input.tenant_id != null
	input.constitutional_hash == "cdd01ef066bc6cf2"
}

# Input validation: resource strings parsed safely (no eval)
parse_cpu(value) := num if {
	contains(value, "m")
	num := to_number(trim_suffix(value, "m"))
	num >= 0
	num <= 500
}

# Metrics: resource violations
violation contains msg if {
	not allow
	msg := sprintf("Resource limit exceeded: cpu=%v mem=%v", [input.resources.cpu_limits, input.resources.mem_limits])
}
