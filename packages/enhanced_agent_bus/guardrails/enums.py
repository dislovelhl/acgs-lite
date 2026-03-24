"""
Guardrail Enums for Runtime Safety.
Constitutional Hash: cdd01ef066bc6cf2
"""

from enum import Enum


class GuardrailLayer(str, Enum):
    """OWASP-compliant guardrail layers."""

    INPUT_SANITIZER = "input_sanitizer"
    AGENT_ENGINE = "agent_engine"
    TOOL_RUNNER_SANDBOX = "tool_runner_sandbox"
    OUTPUT_VERIFIER = "output_verifier"
    AUDIT_LOG = "audit_log"
    RATE_LIMITER = "rate_limiter"


class SafetyAction(str, Enum):
    """Safety actions the guardrails can take."""

    ALLOW = "allow"
    BLOCK = "block"
    MODIFY = "modify"
    ESCALATE = "escalate"
    SANDBOX = "sandbox"
    AUDIT = "audit"


class ViolationSeverity(str, Enum):
    """Severity levels for violations."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
