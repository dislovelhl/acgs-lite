package acgs.ratelimit

import future.keywords.contains
import future.keywords.if

# Rate Limiting Policy - P99 <5ms compliance (ACGS-2 Perf Target)
# OWASP API Rate Limit, NIST SP 800-218 RL.1-3
# Stateless threshold check; external state (Redis) assumed for prod
# Constitutional Hash: cdd01ef066bc6cf2

default allow := false

# Allow if rate below threshold (e.g. 100 qps burst 200 for P99<5ms)
allow if {
	input.request_rate_qps < 100
	input.burst_count < 200
	input.tenant_id != null
	input.constitutional_hash == "cdd01ef066bc6cf2"
}

# Input validation: numeric rates (no string injection)
is_valid_rate(rate) if {
	rate >= 0
	rate <= 1000  # Cap for perf
}

# Metrics: rate limit hits (prometheus export)
violation contains msg if {
	not allow
	msg := sprintf("Rate limit exceeded: qps=%v burst=%v tenant=%v", [input.request_rate_qps, input.burst_count, input.tenant_id])
}
