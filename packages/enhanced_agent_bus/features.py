"""
ACGS-2 Enhanced Agent Bus - Feature Flags (compatibility module)
Constitutional Hash: 608508a9bd224290

This module is kept for backward compatibility with callers importing
``AgentBusFeatures`` from ``enhanced_agent_bus.features``.
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AgentBusFeatures:
    """Feature flags for the Enhanced Agent Bus."""

    metrics_enabled: bool = False
    otel_enabled: bool = False
    circuit_breaker_enabled: bool = False
    policy_client_available: bool = False
    deliberation_available: bool = True
    crypto_available: bool = False
    config_available: bool = True
    audit_client_available: bool = False
    opa_client_available: bool = False
    use_rust: bool = False
    metering_available: bool = False
    maci_available: bool = False

    @classmethod
    def from_env(cls) -> "AgentBusFeatures":
        """Build feature flags from ``AGENTBUS_*`` environment variables."""

        def _bool(name: str, default: bool) -> bool:
            value = os.environ.get(f"AGENTBUS_{name}")
            if value is None:
                return default
            return value.lower() in {"true", "1", "yes", "on"}

        return cls(
            metrics_enabled=_bool("METRICS_ENABLED", False),
            otel_enabled=_bool("OTEL_ENABLED", False),
            circuit_breaker_enabled=_bool("CIRCUIT_BREAKER_ENABLED", False),
            policy_client_available=_bool("POLICY_CLIENT_AVAILABLE", False),
            deliberation_available=_bool("DELIBERATION_AVAILABLE", True),
            crypto_available=_bool("CRYPTO_AVAILABLE", False),
            config_available=_bool("CONFIG_AVAILABLE", True),
            audit_client_available=_bool("AUDIT_CLIENT_AVAILABLE", False),
            opa_client_available=_bool("OPA_CLIENT_AVAILABLE", False),
            use_rust=_bool("USE_RUST", False),
            metering_available=_bool("METERING_AVAILABLE", False),
            maci_available=_bool("MACI_AVAILABLE", False),
        )

    @classmethod
    def for_development(cls) -> "AgentBusFeatures":
        return cls(
            metrics_enabled=True,
            otel_enabled=False,
            circuit_breaker_enabled=False,
            policy_client_available=False,
            deliberation_available=True,
            crypto_available=False,
            config_available=True,
            audit_client_available=False,
            opa_client_available=False,
            use_rust=False,
            metering_available=False,
            maci_available=False,
        )

    @classmethod
    def for_production(cls) -> "AgentBusFeatures":
        return cls(
            metrics_enabled=True,
            otel_enabled=True,
            circuit_breaker_enabled=True,
            policy_client_available=True,
            deliberation_available=True,
            crypto_available=True,
            config_available=True,
            audit_client_available=True,
            opa_client_available=True,
            use_rust=True,
            metering_available=True,
            maci_available=True,
        )

    @classmethod
    def for_testing(cls) -> "AgentBusFeatures":
        return cls(
            metrics_enabled=False,
            otel_enabled=False,
            circuit_breaker_enabled=False,
            policy_client_available=False,
            deliberation_available=True,
            crypto_available=False,
            config_available=True,
            audit_client_available=False,
            opa_client_available=False,
            use_rust=False,
            metering_available=False,
            maci_available=False,
        )

    def to_dict(self) -> dict[str, bool]:
        return {
            "metrics_enabled": self.metrics_enabled,
            "otel_enabled": self.otel_enabled,
            "circuit_breaker_enabled": self.circuit_breaker_enabled,
            "policy_client_available": self.policy_client_available,
            "deliberation_available": self.deliberation_available,
            "crypto_available": self.crypto_available,
            "config_available": self.config_available,
            "audit_client_available": self.audit_client_available,
            "opa_client_available": self.opa_client_available,
            "use_rust": self.use_rust,
            "metering_available": self.metering_available,
            "maci_available": self.maci_available,
        }


__all__ = ["AgentBusFeatures"]
