"""
ACGS-2 LLM Failover - Configuration Module
Constitutional Hash: 608508a9bd224290

LLM-specific circuit breaker configurations and provider type definitions.
"""

from __future__ import annotations

from enum import Enum

from enhanced_agent_bus.circuit_breaker import (
    CONSTITUTIONAL_HASH,
    FallbackStrategy,
    ServiceCircuitConfig,
    ServiceSeverity,
)


class LLMProviderType(str, Enum):
    """LLM provider types for configuration."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    AZURE = "azure"
    BEDROCK = "bedrock"
    COHERE = "cohere"
    MISTRAL = "mistral"
    KIMI = "kimi"
    LOCAL = "local"


# LLM-specific circuit breaker configurations
LLM_CIRCUIT_CONFIGS: dict[str, ServiceCircuitConfig] = {
    # OpenAI - High reliability, moderate timeouts
    "llm:openai": ServiceCircuitConfig(
        name="llm:openai",
        failure_threshold=5,
        timeout_seconds=30.0,
        half_open_requests=3,
        fallback_strategy=FallbackStrategy.CACHED_VALUE,
        fallback_ttl_seconds=60,
        severity=ServiceSeverity.HIGH,
        description="OpenAI LLM Provider - uses cached responses on failure",
    ),
    # Anthropic - High reliability, longer timeouts for complex reasoning
    "llm:anthropic": ServiceCircuitConfig(
        name="llm:anthropic",
        failure_threshold=5,
        timeout_seconds=45.0,
        half_open_requests=3,
        fallback_strategy=FallbackStrategy.CACHED_VALUE,
        fallback_ttl_seconds=60,
        severity=ServiceSeverity.HIGH,
        description="Anthropic LLM Provider - uses cached responses on failure",
    ),
    # Google - Variable latency, higher threshold
    "llm:google": ServiceCircuitConfig(
        name="llm:google",
        failure_threshold=7,
        timeout_seconds=60.0,
        half_open_requests=5,
        fallback_strategy=FallbackStrategy.CACHED_VALUE,
        fallback_ttl_seconds=120,
        severity=ServiceSeverity.MEDIUM,
        description="Google LLM Provider - higher tolerance for variable latency",
    ),
    # Azure OpenAI - Enterprise-grade, moderate settings
    "llm:azure": ServiceCircuitConfig(
        name="llm:azure",
        failure_threshold=5,
        timeout_seconds=30.0,
        half_open_requests=3,
        fallback_strategy=FallbackStrategy.CACHED_VALUE,
        fallback_ttl_seconds=60,
        severity=ServiceSeverity.HIGH,
        description="Azure OpenAI Provider - enterprise reliability",
    ),
    # AWS Bedrock - Enterprise-grade, moderate settings
    "llm:bedrock": ServiceCircuitConfig(
        name="llm:bedrock",
        failure_threshold=5,
        timeout_seconds=30.0,
        half_open_requests=3,
        fallback_strategy=FallbackStrategy.CACHED_VALUE,
        fallback_ttl_seconds=60,
        severity=ServiceSeverity.HIGH,
        description="AWS Bedrock Provider - enterprise reliability",
    ),
    # Kimi (Moonshot AI) - Free tier with moderate limits
    "llm:kimi": ServiceCircuitConfig(
        name="llm:kimi",
        failure_threshold=5,
        timeout_seconds=30.0,
        half_open_requests=3,
        fallback_strategy=FallbackStrategy.CACHED_VALUE,
        fallback_ttl_seconds=60,
        severity=ServiceSeverity.MEDIUM,
        description="Kimi LLM Provider - Moonshot AI with free tier",
    ),
    # Local models - Higher tolerance, faster recovery
    "llm:local": ServiceCircuitConfig(
        name="llm:local",
        failure_threshold=3,
        timeout_seconds=10.0,
        half_open_requests=5,
        fallback_strategy=FallbackStrategy.BYPASS,
        severity=ServiceSeverity.LOW,
        description="Local LLM Provider - fast recovery expected",
    ),
}


def get_llm_circuit_config(provider_type: str) -> ServiceCircuitConfig:
    """Get LLM-specific circuit breaker configuration."""
    key = f"llm:{provider_type.lower()}"
    if key in LLM_CIRCUIT_CONFIGS:
        return LLM_CIRCUIT_CONFIGS[key]

    # Default LLM config
    return ServiceCircuitConfig(
        name=key,
        failure_threshold=5,
        timeout_seconds=30.0,
        half_open_requests=3,
        fallback_strategy=FallbackStrategy.CACHED_VALUE,
        fallback_ttl_seconds=60,
        severity=ServiceSeverity.MEDIUM,
        description=f"Auto-configured LLM circuit breaker for {provider_type}",
    )


__all__ = [
    "CONSTITUTIONAL_HASH",
    "LLM_CIRCUIT_CONFIGS",
    "LLMProviderType",
    "get_llm_circuit_config",
]
