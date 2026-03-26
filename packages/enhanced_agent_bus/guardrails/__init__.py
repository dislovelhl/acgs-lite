"""
ACGS-2 Runtime Safety Guardrails Package.

OWASP-compliant layered security architecture for runtime protection:

1. Rate Limiter → DoS protection and abuse prevention
2. Input Sanitizer → Cleans and validates incoming requests
3. Agent Engine → Core governance with constitutional validation
4. Tool Runner (Sandbox) → Isolated execution environment
5. Output Verifier → Post-execution content validation
6. Audit Log → Immutable compliance trail

Constitutional Hash: 608508a9bd224290
"""

# Enums
# Agent Engine (Layer 2)
from .agent_engine import AgentEngine, AgentEngineConfig

# Audit Log (Layer 5)
from .audit_log import AuditLog, AuditLogConfig

# Base classes and constants
from .base import PII_PATTERNS, GuardrailComponent, GuardrailInput
from .enums import GuardrailLayer, SafetyAction, ViolationSeverity

# Input Sanitizer (Layer 1)
from .input_sanitizer import InputSanitizer, InputSanitizerConfig

# Models
from .models import GuardrailResult, Violation

# Orchestrator
from .orchestrator import RuntimeSafetyGuardrails, RuntimeSafetyGuardrailsConfig

# Output Verifier (Layer 4)
from .output_verifier import OutputVerifier, OutputVerifierConfig

# Rate Limiter (Layer 0)
from .rate_limiter import RateLimiter, RateLimiterConfig

# Sandbox (Layer 3)
from .sandbox import SandboxConfig, ToolRunnerSandbox
from .sandbox_providers import (
    DockerSandboxProvider,
    FirecrackerSandboxProvider,
    MockSandboxProvider,
    SandboxExecutionRequest,
    SandboxExecutionResult,
    SandboxProvider,
    SandboxProviderFactory,
    SandboxProviderType,
    SandboxResourceLimits,
    SandboxSecurityConfig,
    get_default_provider,
)

# SIEM Providers
from .siem_providers import (
    ElasticsearchProvider,
    SIEMProvider,
    SIEMProviderConfig,
    SIEMProviderType,
    SplunkHECProvider,
    create_siem_provider,
)

__all__ = [
    "PII_PATTERNS",
    # Agent Engine
    "AgentEngine",
    "AgentEngineConfig",
    # Audit Log
    "AuditLog",
    "AuditLogConfig",
    "DockerSandboxProvider",
    "ElasticsearchProvider",
    "FirecrackerSandboxProvider",
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
    "MockSandboxProvider",
    # Output Verifier
    "OutputVerifier",
    "OutputVerifierConfig",
    # Rate Limiter
    "RateLimiter",
    "RateLimiterConfig",
    # Orchestrator
    "RuntimeSafetyGuardrails",
    "RuntimeSafetyGuardrailsConfig",
    "SIEMProvider",
    "SIEMProviderConfig",
    # SIEM Providers
    "SIEMProviderType",
    "SafetyAction",
    "SandboxConfig",
    "SandboxExecutionRequest",
    "SandboxExecutionResult",
    "SandboxProvider",
    "SandboxProviderFactory",
    "SandboxProviderType",
    "SandboxResourceLimits",
    "SandboxSecurityConfig",
    "SplunkHECProvider",
    # Sandbox
    "ToolRunnerSandbox",
    "Violation",
    "ViolationSeverity",
    "create_siem_provider",
    "get_default_provider",
]
