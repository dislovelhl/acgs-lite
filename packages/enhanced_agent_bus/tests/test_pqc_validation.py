"""
Test PQC Validation Integration
================================

Tests for Post-Quantum Cryptographic validation in the Enhanced Agent Bus.

Constitutional Hash: 608508a9bd224290

Coverage:
- PQCValidationStrategy functionality
- CompositeValidationStrategy PQC integration
- AgentMessage PQC fields
- Performance benchmarks
- Hybrid mode fallback behavior
"""

import asyncio
import base64
import hashlib
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Check PQC library availability — some tests only run when installed
try:
    import quantum_research.post_quantum_crypto

    PQC_AVAILABLE = True
except ImportError:
    PQC_AVAILABLE = False

# Ensure proper module path resolution for isolated testing
_current_dir = os.path.dirname(os.path.abspath(__file__))
_parent_dir = os.path.dirname(_current_dir)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

try:
    from enhanced_agent_bus.models import (
        CONSTITUTIONAL_HASH,
        AgentMessage,
        MessageStatus,
        MessageType,
        Priority,
    )

    from ..validation_strategies import (
        CompositeValidationStrategy,
        PQCValidationStrategy,
        StaticHashValidationStrategy,
    )
except ImportError:
    from models import (
        CONSTITUTIONAL_HASH,
        AgentMessage,
        MessageStatus,
        MessageType,
        Priority,
    )
    from validation_strategies import (
        CompositeValidationStrategy,
        PQCValidationStrategy,
        StaticHashValidationStrategy,
    )


@pytest.fixture
def sample_agent_message():
    """Create a sample AgentMessage for testing."""
    return AgentMessage(
        content={"action": "test_action", "data": "test_data"},
        from_agent="test_agent",
        to_agent="target_agent",
        message_type=MessageType.COMMAND,
        priority=Priority.HIGH,
    )


@pytest.fixture
def pqc_validator():
    """Create a PQCValidationStrategy instance."""
    return PQCValidationStrategy(hybrid_mode=True)


@pytest.fixture
def mock_constitutional_validator():
    """Create a mock ConstitutionalHashValidator."""
    mock_validator = AsyncMock()
    mock_validator.verify_governance_decision.return_value = True
    return mock_validator


class TestPQCValidationStrategy:
    """Tests for PQCValidationStrategy."""

    async def test_pqc_validation_without_signature_uses_fallback(
        self, pqc_validator, sample_agent_message
    ):
        """Test that PQC validation falls back to static hash when no signature present."""
        # Message without PQC signature
        is_valid, error = await pqc_validator.validate(sample_agent_message)

        assert is_valid is True
        assert error is None

    @pytest.mark.skipif(
        not PQC_AVAILABLE, reason="quantum_research.post_quantum_crypto not installed"
    )
    async def test_pqc_validation_without_signature_strict_mode(self):
        """Test that PQC validation rejects messages without signature in strict mode."""
        validator = PQCValidationStrategy(hybrid_mode=False)
        message = AgentMessage(content={"test": "data"})

        is_valid, error = await validator.validate(message)

        assert is_valid is False
        assert "PQC signature required" in error

    @pytest.mark.skipif(
        not PQC_AVAILABLE, reason="quantum_research.post_quantum_crypto not installed"
    )
    async def test_pqc_validation_with_invalid_signature(self, sample_agent_message):
        """Test PQC validation with invalid signature."""
        # Use strict mode (hybrid_mode=False) to test actual PQC failure
        validator = PQCValidationStrategy(hybrid_mode=False)

        # Add invalid PQC signature
        sample_agent_message.pqc_signature = "invalid_base64"
        sample_agent_message.pqc_public_key = "invalid_key"

        is_valid, error = await validator.validate(sample_agent_message)

        assert is_valid is False
        assert "PQC validation error" in error or "PQC signature" in error

    async def test_pqc_validation_unavailable_fallback(self, sample_agent_message):
        """Test PQC validation when validator is not available in strict mode."""
        # Use strict mode (hybrid_mode=False) - in hybrid mode it would fall back
        # Create a validator with no validator (simulating unavailable)
        validator = PQCValidationStrategy(validator=None, hybrid_mode=False)
        # Force validator to be None (simulating import failure)
        validator._validator = None

        is_valid, error = await validator.validate(sample_agent_message)

        assert is_valid is False
        assert "PQC validator not available" in error


class TestCompositeValidationStrategyPQC:
    """Tests for CompositeValidationStrategy with PQC integration."""

    async def test_composite_auto_enables_pqc(self):
        """Test that CompositeValidationStrategy auto-enables PQC."""
        composite = CompositeValidationStrategy(enable_pqc=True)

        # Check that PQC strategy was added
        pqc_strategies = [s for s in composite._strategies if isinstance(s, PQCValidationStrategy)]
        assert len(pqc_strategies) == 1

    async def test_composite_pqc_disabled(self):
        """Test CompositeValidationStrategy with PQC disabled."""
        composite = CompositeValidationStrategy(enable_pqc=False)

        # Check that no PQC strategy was added
        pqc_strategies = [s for s in composite._strategies if isinstance(s, PQCValidationStrategy)]
        assert len(pqc_strategies) == 0

    async def test_composite_pqc_prioritization(self, sample_agent_message):
        """Test that PQC validation is prioritized when signature present."""
        composite = CompositeValidationStrategy(enable_pqc=True)

        # Add PQC signature to message
        sample_agent_message.pqc_signature = "test_signature"
        sample_agent_message.pqc_public_key = "test_key"

        # Mock the PQC validator to fail
        for strategy in composite._strategies:
            if isinstance(strategy, PQCValidationStrategy):
                with patch.object(strategy, "validate", return_value=(False, "PQC failed")):
                    is_valid, error = await composite.validate(sample_agent_message)
                    assert is_valid is False
                    assert "PQC:" in error

    async def test_composite_fallback_behavior(self, sample_agent_message):
        """Test composite validation fallback behavior."""
        # Create composite with static hash and PQC
        static_strategy = StaticHashValidationStrategy(strict=True)
        composite = CompositeValidationStrategy(strategies=[static_strategy], enable_pqc=True)

        # Valid message (should pass)
        is_valid, error = await composite.validate(sample_agent_message)
        assert is_valid is True
        assert error is None

        # Invalid constitutional hash (should fail)
        sample_agent_message.constitutional_hash = "invalid_hash"
        is_valid, error = await composite.validate(sample_agent_message)
        assert is_valid is False
        assert "StaticHash:" in error or "hash mismatch" in error.lower()


class TestAgentMessagePQCExtensions:
    """Tests for AgentMessage PQC field extensions."""

    def test_agent_message_pqc_fields_initialization(self):
        """Test that AgentMessage initializes PQC fields correctly."""
        message = AgentMessage()

        assert message.pqc_signature is None
        assert message.pqc_public_key is None
        assert message.pqc_algorithm is None

    def test_agent_message_to_dict_includes_pqc_fields(self):
        """Test that to_dict includes PQC fields."""
        message = AgentMessage()
        message.pqc_signature = "test_sig"
        message.pqc_public_key = "test_key"
        message.pqc_algorithm = "dilithium-3"

        data = message.to_dict()

        assert data["pqc_signature"] == "test_sig"
        assert data["pqc_public_key"] == "test_key"
        assert data["pqc_algorithm"] == "dilithium-3"

    def test_agent_message_from_dict_pqc_fields(self):
        """Test that from_dict handles PQC fields."""
        data = {
            "message_id": "test-123",
            "conversation_id": "conv-123",
            "content": {"test": "data"},
            "from_agent": "agent1",
            "to_agent": "agent2",
            "message_type": "command",
            "priority": 1,
            "status": "pending",
            "constitutional_hash": CONSTITUTIONAL_HASH,
            "pqc_signature": "test_sig",
            "pqc_public_key": "test_key",
            "pqc_algorithm": "dilithium-3",
        }

        message = AgentMessage.from_dict(data)

        assert message.pqc_signature == "test_sig"
        assert message.pqc_public_key == "test_key"
        assert message.pqc_algorithm == "dilithium-3"


class TestPQCHybridModeIntegration:
    """Tests for PQC hybrid mode integration."""

    async def test_hybrid_mode_static_hash_fallback(self, sample_agent_message):
        """Test hybrid mode falls back to static hash validation."""
        validator = PQCValidationStrategy(hybrid_mode=True)

        # Valid constitutional hash
        sample_agent_message.constitutional_hash = CONSTITUTIONAL_HASH
        is_valid, error = await validator.validate(sample_agent_message)

        assert is_valid is True
        assert error is None

        # Invalid constitutional hash
        sample_agent_message.constitutional_hash = "invalid_hash"
        is_valid, error = await validator.validate(sample_agent_message)

        assert is_valid is False
        assert "Constitutional hash mismatch" in error


@pytest.mark.skip(reason="Requires pytest-benchmark plugin")
class TestPQCPerformanceBenchmarks:
    """Performance benchmarks for PQC validation."""

    async def test_pqc_validation_performance_baseline(self, benchmark):
        """Benchmark PQC validation performance."""
        validator = PQCValidationStrategy(hybrid_mode=True)
        message = AgentMessage(content={"test": "benchmark"})

        # Benchmark the validation
        async def validate_message():
            return await validator.validate(message)

        result = await benchmark(validate_message)
        assert result[0] is True  # Should pass (hybrid mode fallback)

    async def test_composite_validation_performance(self, benchmark):
        """Benchmark composite validation with PQC."""
        composite = CompositeValidationStrategy(enable_pqc=True)
        message = AgentMessage(content={"test": "benchmark"})

        async def validate_message():
            return await composite.validate(message)

        result = await benchmark(validate_message)
        assert result[0] is True  # Should pass


@pytest.mark.skip(reason="Requires full quantum_research package with PQCSignature class")
class TestPQCSecurityProperties:
    """Tests for PQC security properties."""

    async def test_pqc_signature_verification_logic(self):
        """Test the PQC signature verification logic."""
        # Create a mock validator and pass it directly to the constructor
        mock_validator = MagicMock()
        mock_validator.verify_governance_decision.return_value = True

        validator = PQCValidationStrategy(validator=mock_validator, hybrid_mode=True)

        # Create a message with PQC signature - both must be valid base64
        message = AgentMessage(content={"test": "data"})
        message.pqc_signature = base64.b64encode(b"test_signature").decode()
        message.pqc_public_key = base64.b64encode(b"test_public_key").decode()

        _is_valid, _error = await validator.validate(message)

        # Verify the mock was called correctly
        assert mock_validator.verify_governance_decision.called
        call_args = mock_validator.verify_governance_decision.call_args
        assert len(call_args[0]) == 3  # decision, signature, public_key


# ============================================================================
# Phase 1 PQC Migration: Hybrid Mode Tests (T028)
# ============================================================================


class TestHybridModeValidateSignature:
    """Tests for validate_signature() hybrid mode behaviour."""

    @pytest.fixture(autouse=True)
    def _stub_pqc_key_registry(self):
        """Ensure the pqc_key_registry stub module has a key_registry_client attribute.

        The actual module may be absent (namespace package from empty dir) or
        may not be importable when earlier test files haven't registered it in
        sys.modules.  In that case we create a minimal stub package so that
        ``validate_signature`` can import it at call time.
        """
        mod_name = "src.core.services.policy_registry.app.services.pqc_key_registry"

        # Ensure parent package chain exists in sys.modules so importlib can
        # resolve the dotted path.  Earlier PQC test files may or may not have
        # set these up depending on collection order.
        import types

        parent_parts = mod_name.rsplit(".", 1)[0]  # ...app.services
        parents_to_clean: list[str] = []
        for i, _part in enumerate(parent_parts.split(".")):
            dotted = ".".join(parent_parts.split(".")[: i + 1])
            if dotted not in sys.modules:
                stub = types.ModuleType(dotted)
                stub.__path__ = []  # mark as package
                stub.__package__ = ".".join(parent_parts.split(".")[:i]) or dotted
                sys.modules[dotted] = stub
                parents_to_clean.append(dotted)

        # Now ensure the leaf module itself exists.
        mod_created = False
        if mod_name not in sys.modules:
            stub_mod = types.ModuleType(mod_name)
            stub_mod.__path__ = []
            stub_mod.__package__ = parent_parts
            sys.modules[mod_name] = stub_mod
            mod_created = True

        mod = sys.modules[mod_name]
        had_attr = hasattr(mod, "key_registry_client")
        if not had_attr:
            stub_client = MagicMock()
            stub_client._registry = None  # skip registry lookup
            mod.key_registry_client = stub_client

        yield

        # Teardown: restore original state
        if not had_attr and hasattr(mod, "key_registry_client"):
            delattr(mod, "key_registry_client")
        if mod_created and mod_name in sys.modules:
            del sys.modules[mod_name]
        for p in reversed(parents_to_clean):
            sys.modules.pop(p, None)

    @pytest.mark.unit
    async def test_ed25519_accepted_in_hybrid_mode(self):
        """Ed25519 key accepted when HYBRID_MODE_ENABLED=True; audit key_type='classical'."""
        from enhanced_agent_bus.pqc_validators import validate_signature

        with patch(
            "enhanced_agent_bus.pqc_validators.HYBRID_MODE_ENABLED",
            True,
        ):
            result = await validate_signature(
                payload=b"test-payload",
                signature=b"fake-sig",
                key_id="key-001",
                algorithm="Ed25519",
                hybrid_mode=True,
            )
        assert result["valid"] is True
        assert result["key_type"] == "classical"
        assert result["algorithm"] == "Ed25519"

    @pytest.mark.unit
    async def test_ml_dsa_accepted_in_hybrid_mode(self):
        """ML-DSA-65 key accepted when HYBRID_MODE_ENABLED=True; audit key_type='pqc'."""
        from enhanced_agent_bus.pqc_validators import validate_signature

        result = await validate_signature(
            payload=b"test-payload",
            signature=b"fake-sig",
            key_id="key-002",
            algorithm="ML-DSA-65",
            hybrid_mode=True,
        )
        assert result["valid"] is True
        assert result["key_type"] == "pqc"
        assert result["algorithm"] == "ML-DSA-65"

    @pytest.mark.unit
    async def test_ed25519_rejected_in_pqc_only_mode(self):
        """Ed25519 raises ClassicalKeyRejectedError when hybrid mode is off."""
        from enhanced_agent_bus.pqc_validators import (
            ClassicalKeyRejectedError,
            validate_signature,
        )

        with pytest.raises(ClassicalKeyRejectedError) as exc_info:
            await validate_signature(
                payload=b"test-payload",
                signature=b"fake-sig",
                key_id="key-003",
                algorithm="Ed25519",
                hybrid_mode=False,
            )
        assert "classical-key-not-accepted" in str(exc_info.value.details)

    @pytest.mark.unit
    async def test_legacy_alias_normalized(self):
        """Legacy alias 'dilithium3' normalised to 'ML-DSA-65'."""
        from enhanced_agent_bus.pqc_validators import validate_signature

        result = await validate_signature(
            payload=b"test-payload",
            signature=b"fake-sig",
            key_id="key-004",
            algorithm="dilithium3",
            hybrid_mode=True,
        )
        assert result["algorithm"] == "ML-DSA-65"
        assert result["key_type"] == "pqc"

    @pytest.mark.unit
    async def test_revoked_key_status_from_registry(self):
        """Revoked key in registry returns key_status=revoked in result."""
        from enhanced_agent_bus.pqc_validators import validate_signature

        mock_record = MagicMock()
        mock_record.metadata = {"key_status": "revoked"}

        mock_registry = AsyncMock()
        mock_registry.get_key = AsyncMock(return_value=mock_record)

        mock_client = MagicMock()
        mock_client._registry = mock_registry

        with patch(
            "src.core.services.policy_registry.app.services.pqc_key_registry.key_registry_client",
            mock_client,
        ):
            result = await validate_signature(
                payload=b"test-payload",
                signature=b"fake-sig",
                key_id="key-005",
                algorithm="ML-DSA-65",
                hybrid_mode=True,
            )
        assert result["key_status"] == "revoked"

    @pytest.mark.unit
    async def test_key_registry_503_fails_closed(self):
        """Key Registry returning 503/error causes fail-closed KeyRegistryUnavailableError."""
        from enhanced_agent_bus.pqc_validators import (
            KeyRegistryUnavailableError,
            validate_signature,
        )

        mock_registry = AsyncMock()
        mock_registry.get_key = AsyncMock(side_effect=OSError("Connection refused"))

        mock_client = MagicMock()
        mock_client._registry = mock_registry

        with (
            patch(
                "src.core.services.policy_registry.app.services.pqc_key_registry.key_registry_client",
                mock_client,
            ),
            pytest.raises(KeyRegistryUnavailableError),
        ):
            await validate_signature(
                payload=b"test-payload",
                signature=b"fake-sig",
                key_id="key-006",
                algorithm="ML-DSA-65",
                hybrid_mode=True,
            )


if __name__ == "__main__":
    # Run tests if executed directly
    pytest.main([__file__, "-v"])
