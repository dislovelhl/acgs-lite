"""
ACGS-2 Enhanced Agent Bus - Feature Flags Coverage Tests
Constitutional Hash: 608508a9bd224290

Covers: enhanced_agent_bus/features.py (36 stmts, 0% -> target 100%)
Tests AgentBusFeatures dataclass, factory methods, environment parsing.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.governance, pytest.mark.constitutional]


class TestAgentBusFeatures:
    def test_default_construction(self) -> None:
        from enhanced_agent_bus.features import AgentBusFeatures

        features = AgentBusFeatures()
        assert features.metrics_enabled is False
        assert features.otel_enabled is False
        assert features.deliberation_available is True
        assert features.config_available is True

    def test_frozen(self) -> None:
        from enhanced_agent_bus.features import AgentBusFeatures

        features = AgentBusFeatures()
        with pytest.raises(AttributeError):
            features.metrics_enabled = True  # type: ignore[misc]

    def test_for_development(self) -> None:
        from enhanced_agent_bus.features import AgentBusFeatures

        features = AgentBusFeatures.for_development()
        assert features.metrics_enabled is True
        assert features.otel_enabled is False
        assert features.deliberation_available is True

    def test_for_production(self) -> None:
        from enhanced_agent_bus.features import AgentBusFeatures

        features = AgentBusFeatures.for_production()
        assert features.metrics_enabled is True
        assert features.otel_enabled is True
        assert features.circuit_breaker_enabled is True
        assert features.policy_client_available is True
        assert features.use_rust is True
        assert features.maci_available is True

    def test_for_testing(self) -> None:
        from enhanced_agent_bus.features import AgentBusFeatures

        features = AgentBusFeatures.for_testing()
        assert features.metrics_enabled is False
        assert features.otel_enabled is False
        assert features.deliberation_available is True
        assert features.maci_available is False

    def test_to_dict(self) -> None:
        from enhanced_agent_bus.features import AgentBusFeatures

        features = AgentBusFeatures.for_testing()
        d = features.to_dict()
        assert isinstance(d, dict)
        assert len(d) == 12
        assert d["metrics_enabled"] is False
        assert d["deliberation_available"] is True

    def test_from_env_defaults(self) -> None:
        from enhanced_agent_bus.features import AgentBusFeatures

        # Clear any AGENTBUS_ env vars
        env = {k: v for k, v in os.environ.items() if not k.startswith("AGENTBUS_")}
        with patch.dict(os.environ, env, clear=True):
            features = AgentBusFeatures.from_env()
            assert features.metrics_enabled is False
            assert features.deliberation_available is True

    def test_from_env_true_values(self) -> None:
        from enhanced_agent_bus.features import AgentBusFeatures

        env_overrides = {
            "AGENTBUS_METRICS_ENABLED": "true",
            "AGENTBUS_OTEL_ENABLED": "1",
            "AGENTBUS_CIRCUIT_BREAKER_ENABLED": "yes",
            "AGENTBUS_USE_RUST": "on",
            "AGENTBUS_MACI_AVAILABLE": "TRUE",
        }
        with patch.dict(os.environ, env_overrides):
            features = AgentBusFeatures.from_env()
            assert features.metrics_enabled is True
            assert features.otel_enabled is True
            assert features.circuit_breaker_enabled is True
            assert features.use_rust is True
            assert features.maci_available is True

    def test_from_env_false_values(self) -> None:
        from enhanced_agent_bus.features import AgentBusFeatures

        env_overrides = {
            "AGENTBUS_DELIBERATION_AVAILABLE": "false",
            "AGENTBUS_CONFIG_AVAILABLE": "0",
        }
        with patch.dict(os.environ, env_overrides):
            features = AgentBusFeatures.from_env()
            assert features.deliberation_available is False
            assert features.config_available is False

    def test_to_dict_all_keys_present(self) -> None:
        from enhanced_agent_bus.features import AgentBusFeatures

        features = AgentBusFeatures.for_production()
        d = features.to_dict()
        expected_keys = {
            "metrics_enabled",
            "otel_enabled",
            "circuit_breaker_enabled",
            "policy_client_available",
            "deliberation_available",
            "crypto_available",
            "config_available",
            "audit_client_available",
            "opa_client_available",
            "use_rust",
            "metering_available",
            "maci_available",
        }
        assert set(d.keys()) == expected_keys
        assert all(isinstance(v, bool) for v in d.values())
