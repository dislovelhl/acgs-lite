"""
Security Defaults Regression Tests
Constitutional Hash: 608508a9bd224290

CRITICAL: These tests prevent regression on security-critical defaults.
All security-sensitive components MUST default to fail-closed behavior.

Security Audit Reference: VULN-001, VULN-002 (2025-12)
"""

import os
from unittest.mock import MagicMock

import pytest

# Import patterns matching existing test conventions
try:
    from config import BusConfiguration
    from models import CONSTITUTIONAL_HASH, AgentMessage
    from policy_client import PolicyRegistryClient, get_policy_client
    from validation_strategies import RustValidationStrategy
except ImportError:
    from enhanced_agent_bus.models import CONSTITUTIONAL_HASH, AgentMessage

    from ..config import BusConfiguration
    from ..policy_client import PolicyRegistryClient, get_policy_client
    from ..validation_strategies import RustValidationStrategy


class TestPolicyClientSecurityDefaults:
    """
    Test that PolicyRegistryClient defaults to fail-closed behavior.

    Security Rationale:
    - Fail-closed ensures that validation failures result in DENY
    - Prevents bypass attacks when policy registry is unavailable
    - Constitutional compliance requires explicit validation success
    """

    def test_policy_client_default_fail_closed(self):
        """PolicyClient MUST default to fail_closed=True."""
        client = PolicyRegistryClient()
        assert client.fail_closed is True, (
            "SECURITY VIOLATION: PolicyRegistryClient must default to fail_closed=True. "
            "Fail-open behavior allows bypass attacks when registry is unavailable."
        )

    def test_policy_client_explicit_fail_open_allowed(self):
        """Explicit fail_closed=False should be allowed for testing."""
        client = PolicyRegistryClient(fail_closed=False)
        assert client.fail_closed is False

    def test_policy_client_explicit_fail_closed(self):
        """Explicit fail_closed=True should work."""
        client = PolicyRegistryClient(fail_closed=True)
        assert client.fail_closed is True

    def test_get_policy_client_default_fail_closed(self):
        """get_policy_client() MUST return client with fail_closed=True by default."""
        # Import the module to access global client state
        import sys

        policy_client_module = sys.modules.get("policy_client") or sys.modules.get(
            "enhanced_agent_bus.policy_client"
        )
        if policy_client_module is None:
            # Module imported via try/except at top - access via direct path
            for name, mod in sys.modules.items():
                if name.endswith("policy_client") and hasattr(mod, "_policy_client"):
                    policy_client_module = mod
                    break

        if policy_client_module is None:
            pytest.skip("Could not locate policy_client module in sys.modules")

        original_client = policy_client_module._policy_client
        policy_client_module._policy_client = None

        try:
            client = get_policy_client()
            assert client.fail_closed is True, (
                "SECURITY VIOLATION: get_policy_client() must return fail_closed=True client. "
                "Global policy client must enforce fail-closed behavior."
            )
        finally:
            # Restore original client state
            policy_client_module._policy_client = original_client


class TestBusConfigurationSecurityDefaults:
    """
    Test that BusConfiguration defaults to secure settings.

    Security Rationale:
    - Configuration objects set system-wide security behavior
    - Insecure defaults can propagate throughout the system
    - Production deployments must be secure by default
    """

    def test_bus_config_default_policy_fail_closed(self):
        """BusConfiguration MUST default policy_fail_closed=True."""
        config = BusConfiguration()
        assert config.policy_fail_closed is True, (
            "SECURITY VIOLATION: BusConfiguration must default policy_fail_closed=True. "
            "System-wide policy validation must fail closed."
        )

    def test_bus_config_default_maci_enabled(self):
        """BusConfiguration MUST default enable_maci=True."""
        config = BusConfiguration()
        assert config.enable_maci is True, (
            "SECURITY VIOLATION: BusConfiguration must default enable_maci=True. "
            "MACI role separation prevents Gödel bypass attacks."
        )

    def test_bus_config_default_maci_strict_mode(self):
        """BusConfiguration MUST default maci_strict_mode=True."""
        config = BusConfiguration()
        assert config.maci_strict_mode is True, (
            "SECURITY VIOLATION: BusConfiguration must default maci_strict_mode=True. "
            "Strict MACI mode enforces role separation."
        )

    def test_bus_config_for_production_is_secure(self):
        """BusConfiguration.for_production() MUST have all security features enabled."""
        config = BusConfiguration.for_production()

        assert config.policy_fail_closed is True, "Production config must be fail-closed"
        assert config.enable_maci is True, "Production config must enable MACI"
        assert config.maci_strict_mode is True, "Production config must enable MACI strict mode"

    def test_bus_config_for_testing_documents_insecure(self):
        """BusConfiguration.for_testing() may disable security but must be explicit."""
        config = BusConfiguration.for_testing()

        # Testing config is allowed to disable security features
        # This test documents the expected behavior
        assert config.policy_fail_closed is False, "Testing config should disable fail-closed"
        assert config.enable_maci is False, "Testing config should disable MACI"

    def test_bus_config_from_environment_defaults_secure(self):
        """BusConfiguration.from_environment() MUST default to secure values."""
        # Clear relevant environment variables
        env_vars_to_clear = ["POLICY_FAIL_CLOSED", "MACI_ENABLED", "MACI_STRICT_MODE"]
        original_values = {}
        for var in env_vars_to_clear:
            original_values[var] = os.environ.pop(var, None)

        try:
            config = BusConfiguration.from_environment()

            assert config.enable_maci is True, "from_environment() must default enable_maci=True"
            assert config.maci_strict_mode is True, (
                "from_environment() must default maci_strict_mode=True"
            )
        finally:
            # Restore environment variables
            for var, value in original_values.items():
                if value is not None:
                    os.environ[var] = value


class TestRustValidationStrategySecurityDefaults:
    """
    Test that RustValidationStrategy defaults to fail-closed behavior.

    Security Rationale:
    - Rust backend validation is a critical security boundary
    - Validation uncertainty must result in DENY
    - Missing validation methods must fail closed
    """

    def test_rust_validation_default_fail_closed(self):
        """RustValidationStrategy MUST default to fail_closed=True."""
        mock_processor = MagicMock()
        strategy = RustValidationStrategy(rust_processor=mock_processor)

        assert strategy._fail_closed is True, (
            "SECURITY VIOLATION: RustValidationStrategy must default to fail_closed=True. "
            "Rust validation uncertainty must result in DENY."
        )

    def test_rust_validation_explicit_fail_open_allowed(self):
        """Explicit fail_closed=False should be allowed for testing."""
        mock_processor = MagicMock()
        strategy = RustValidationStrategy(rust_processor=mock_processor, fail_closed=False)

        assert strategy._fail_closed is False

    async def test_rust_validation_no_processor_fails_closed(self):
        """RustValidationStrategy with no processor MUST fail closed."""
        strategy = RustValidationStrategy(rust_processor=None)

        message = AgentMessage(
            message_id="test-123",
            sender_id="test-sender",
            to_agent="test-receiver",
            content={"test": "data"},
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

        is_valid, error = await strategy.validate(message)

        assert is_valid is False, "Missing processor must fail validation"
        assert "not available" in error.lower(), "Error must indicate processor unavailable"

    async def test_rust_validation_no_method_fails_closed(self):
        """RustValidationStrategy with processor lacking validate method MUST fail closed."""
        mock_processor = MagicMock(spec=[])  # No methods
        strategy = RustValidationStrategy(rust_processor=mock_processor)

        message = AgentMessage(
            message_id="test-123",
            sender_id="test-sender",
            to_agent="test-receiver",
            content={"test": "data"},
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

        is_valid, error = await strategy.validate(message)

        assert is_valid is False, "Missing validate method must fail validation"
        assert "fail closed" in error.lower() or "no validation method" in error.lower(), (
            "Error must indicate fail-closed behavior"
        )


class TestConstitutionalHashPresence:
    """
    Test that constitutional hash is present in security-critical modules.

    Security Rationale:
    - Constitutional hash provides audit trail
    - All security modules must be constitutionally compliant
    - Hash verification ensures module integrity
    """

    def test_config_has_constitutional_hash(self):
        """BusConfiguration MUST have constitutional hash."""
        bus_config = BusConfiguration()
        assert bus_config.constitutional_hash == CONSTITUTIONAL_HASH, (
            "BusConfiguration must use canonical constitutional hash"
        )

    def test_validation_strategies_has_constitutional_hash(self):
        """validation_strategies.py MUST reference constitutional hash."""
        try:
            from validation_strategies import StaticHashValidationStrategy
        except ImportError:
            from ..validation_strategies import StaticHashValidationStrategy

        # Check that strategies use constitutional hash
        strategy = StaticHashValidationStrategy()
        assert strategy._constitutional_hash == CONSTITUTIONAL_HASH, (
            "StaticHashValidationStrategy must use canonical constitutional hash"
        )


class TestSecurityDocumentation:
    """
    Meta-tests ensuring security decisions are documented.

    These tests serve as documentation and verification that security
    design decisions are intentional and reviewed.
    """

    def test_fail_closed_is_documented(self):
        """Verify fail-closed pattern is documented in config comments."""
        import inspect

        try:
            from config import BusConfiguration as BC
        except ImportError:
            from ..config import BusConfiguration as BC

        source = inspect.getsource(BC)
        assert "fail" in source.lower() and "closed" in source.lower(), (
            "BusConfiguration should document fail-closed behavior in comments"
        )

    def test_maci_security_rationale_documented(self):
        """Verify MACI security rationale is documented."""
        import inspect

        try:
            from config import BusConfiguration as BC
        except ImportError:
            from ..config import BusConfiguration as BC

        source = inspect.getsource(BC)
        # Check for security comments about MACI
        has_maci = "maci" in source.lower()
        has_security_context = (
            "security" in source.lower() or "gödel" in source.lower() or "bypass" in source.lower()
        )
        assert has_maci and has_security_context, (
            "BusConfiguration should document MACI security rationale"
        )


# Run tests directly if executed
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
