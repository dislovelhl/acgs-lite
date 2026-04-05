"""
ACGS-2 Runtime Safety Guardrails (Backward Compatibility Re-exports).

This module re-exports all components from the guardrails package for
backward compatibility. New code should import directly from the guardrails
package submodules.

OWASP-compliant layered security architecture for runtime protection:

1. Input Sanitizer → Cleans and validates incoming requests
2. Agent Engine → Core governance with constitutional validation
3. Tool Runner (Sandbox) → Isolated execution environment
4. Output Verifier → Post-execution content validation
5. Audit Log → Immutable compliance trail

Constitutional Hash: 608508a9bd224290
"""

# Re-export everything from the guardrails package for backward compatibility
from .guardrails import (
    PII_PATTERNS,
    # Agent Engine
    AgentEngine,
    AgentEngineConfig,
    # Audit Log
    AuditLog,
    AuditLogConfig,
    # Base
    GuardrailComponent,
    GuardrailInput,
    # Enums
    GuardrailLayer,
    # Models
    GuardrailResult,
    # Input Sanitizer
    InputSanitizer,
    InputSanitizerConfig,
    # Output Verifier
    OutputVerifier,
    OutputVerifierConfig,
    # Rate Limiter
    RateLimiter,
    RateLimiterConfig,
    # Orchestrator
    RuntimeSafetyGuardrails,
    RuntimeSafetyGuardrailsConfig,
    SafetyAction,
    SandboxConfig,
    # Sandbox
    ToolRunnerSandbox,
    Violation,
    ViolationSeverity,
)
from .guardrails.agent_engine import IMPACT_SCORING_AVAILABLE

__all__ = [
    "IMPACT_SCORING_AVAILABLE",
    "PII_PATTERNS",
    # Agent Engine
    "AgentEngine",
    "AgentEngineConfig",
    # Audit Log
    "AuditLog",
    "AuditLogConfig",
    # Base
    "GuardrailComponent",
    "GuardrailInput",
    # Enums
    "GuardrailLayer",
    # Models
    "GuardrailResult",
    # Input Sanitizer
    "InputSanitizer",
    "InputSanitizerConfig",
    # Output Verifier
    "OutputVerifier",
    "OutputVerifierConfig",
    # Rate Limiter
    "RateLimiter",
    "RateLimiterConfig",
    # Orchestrator
    "RuntimeSafetyGuardrails",
    "RuntimeSafetyGuardrailsConfig",
    "SafetyAction",
    "SandboxConfig",
    # Sandbox
    "ToolRunnerSandbox",
    "Violation",
    "ViolationSeverity",
]
