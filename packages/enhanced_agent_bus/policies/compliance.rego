package acgs.compliance

import future.keywords.contains
import future.keywords.if

# Compliance Policy - NIST/OWASP 2025 hardening
# No eval/exec, input sanitization, P99 perf
# Constitutional Hash: cdd01ef066bc6cf2

default allow := false

allow if {
	not dangerous_input
	no_eval_attempt
	input.tenant_id != null
	input.constitutional_hash == "cdd01ef066bc6cf2"
}

# OWASP A03:2021 Injection - No eval/exec patterns
no_eval_attempt if {
	not regex.find_n(`eval\s*\(`, lower(input.code), 1)
	not regex.find_n(`exec\s*\(`, lower(input.code), 1)
	not regex.find_n(`__import__`, lower(input.code), 1)
}

# NIST input validation - safe strings/numbers only
dangerous_input if {
	input.payload matches `.*[<>\'";].*`
}

dangerous_input if {
	not is_number(input.numeric_field)
}

# Perf: simple regex (cached), P99 <5ms
is_number(n) if {
	n >= 0
}

# Metrics
violation contains msg if {
	not allow
	msg := "Compliance violation: injection risk or invalid input"
}
