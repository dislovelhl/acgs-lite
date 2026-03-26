# Constitutional Hash: 608508a9bd224290
"""
Test PQC MACI Validation (Gödel Bypass Prevention)
==================================================

Unit tests for validate_maci_record_pqc and _is_self_validation logic.

Constitutional Hash: 608508a9bd224290
"""

import time
from unittest.mock import AsyncMock, patch

import pytest

try:
    from enhanced_agent_bus.models import CONSTITUTIONAL_HASH
    from enhanced_agent_bus.pqc_validators import (
        ValidationResult,
        _is_self_validation,
        validate_maci_record_pqc,
    )
except ImportError:
    pytest.skip(
        "validate_maci_record_pqc removed from pqc_validators in Phase 3 refactor",
        allow_module_level=True,
    )


@pytest.mark.pqc
class TestMACISelfValidation:
    """Tests for Gödel bypass prevention (self-validation check)."""

    def test_is_self_validation_target_output_match(self):
        """Rule: agent_id cannot match target_output_id."""
        agent_id = "agent-001"
        target_output_id = "agent-001"
        record = {}
        assert _is_self_validation(agent_id, target_output_id, record) is True

    def test_is_self_validation_output_author_match(self):
        """Rule: agent_id cannot match record output_author."""
        agent_id = "agent-001"
        target_output_id = "agent-002"
        record = {"output_author": "agent-001"}
        assert _is_self_validation(agent_id, target_output_id, record) is True

    def test_is_not_self_validation(self):
        """Valid case: agent is distinct from target and author."""
        agent_id = "agent-003"
        target_output_id = "agent-002"
        record = {"output_author": "agent-001"}
        assert _is_self_validation(agent_id, target_output_id, record) is False


@pytest.mark.pqc
class TestValidateMACIRecordPQC:
    """Tests for validate_maci_record_pqc entry point."""

    async def test_validate_maci_missing_fields(self):
        """Invalid MACI structure should fail."""
        record = {"agent_id": "agent-001"}  # missing action, timestamp
        result = await validate_maci_record_pqc(record)
        assert result.valid is False
        assert any("Missing required MACI field" in e for e in result.errors)

    async def test_validate_maci_hash_mismatch(self):
        """Constitutional hash mismatch should fail."""
        record = {
            "agent_id": "agent-001",
            "action": "validate",
            "timestamp": time.time(),
            "constitutional_hash": "invalid-hash",
        }
        result = await validate_maci_record_pqc(record, expected_hash=CONSTITUTIONAL_HASH)
        assert result.valid is False
        assert "MACI record constitutional hash mismatch" in result.errors

    async def test_validate_maci_self_validation_rejected(self):
        """Gödel bypass: self-validation should be rejected."""
        record = {
            "agent_id": "agent-001",
            "target_output_id": "agent-001",
            "action": "validate",
            "timestamp": time.time(),
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }
        result = await validate_maci_record_pqc(record)
        assert result.valid is False
        assert "Self-validation not allowed (Gödel bypass prevention)" in result.errors

    async def test_validate_maci_pqc_enabled_delegation(self):
        """If PQC is enabled and signature present, it should delegate to validate_constitutional_hash_pqc."""
        record = {
            "agent_id": "agent-001",
            "target_output_id": "agent-002",
            "action": "validate",
            "timestamp": time.time(),
            "constitutional_hash": CONSTITUTIONAL_HASH,
            "signature": {"v2": "hybrid-sig"},
        }

        mock_pqc_config = MagicMock()
        mock_pqc_config.pqc_enabled = True

        with patch(
            "enhanced_agent_bus.pqc_validators.validate_constitutional_hash_pqc"
        ) as mock_val:
            mock_val.return_value = ValidationResult(
                valid=True, constitutional_hash=CONSTITUTIONAL_HASH
            )
            result = await validate_maci_record_pqc(record, pqc_config=mock_pqc_config)

            assert result.valid is True
            mock_val.assert_called_once()


from unittest.mock import MagicMock
