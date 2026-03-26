"""
Tests for enhanced_agent_bus.pqc_validators
Constitutional Hash: 608508a9bd224290
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from enhanced_agent_bus.pqc_validators import (
    PqcValidators,
    _extract_message_content,
    _is_self_validation,
    check_enforcement_for_create,
    check_enforcement_for_update,
    validate_constitutional_hash_pqc,
    validate_maci_record_pqc,
)

# ---------------------------------------------------------------------------
# PqcValidators helper class
# ---------------------------------------------------------------------------


class TestPqcValidators:
    def test_process_returns_string(self):
        v = PqcValidators()
        assert v.process("hello") == "hello"

    def test_process_none_returns_none(self):
        v = PqcValidators()
        assert v.process(None) is None

    def test_process_non_string_returns_none(self):
        v = PqcValidators()
        assert v.process(123) is None  # type: ignore[arg-type]

    def test_custom_constitutional_hash(self):
        v = PqcValidators(constitutional_hash="custom_hash")
        assert v._constitutional_hash == "custom_hash"

    def test_default_constitutional_hash(self):
        v = PqcValidators()
        assert v._constitutional_hash is not None


# ---------------------------------------------------------------------------
# _is_self_validation
# ---------------------------------------------------------------------------


class TestIsSelfValidation:
    def test_self_validation_by_output_author(self):
        assert _is_self_validation("agent_1", "output_999", {"output_author": "agent_1"}) is True

    def test_no_self_validation_different_author(self):
        assert _is_self_validation("agent_1", "output_999", {"output_author": "agent_2"}) is False

    def test_self_validation_agent_id_in_target(self):
        assert _is_self_validation("agent_1", "agent_1_output_42", {}) is True

    def test_no_self_validation_when_empty(self):
        assert _is_self_validation("agent_1", "", {}) is False


# ---------------------------------------------------------------------------
# _extract_message_content
# ---------------------------------------------------------------------------


class TestExtractMessageContent:
    def test_excludes_signature_key(self):
        data = {"a": 1, "signature": "sig", "b": 2}
        content = _extract_message_content(data)
        assert b"signature" not in content
        assert b'"a":1' in content

    def test_returns_bytes(self):
        data = {"key": "value"}
        assert isinstance(_extract_message_content(data), bytes)

    def test_deterministic(self):
        data = {"z": 1, "a": 2}
        assert _extract_message_content(data) == _extract_message_content(data)


# ---------------------------------------------------------------------------
# check_enforcement_for_create
# ---------------------------------------------------------------------------


class TestCheckEnforcementForCreate:
    @pytest.mark.asyncio
    async def test_migration_context_skips_check(self):
        config = MagicMock()
        # Should not raise
        await check_enforcement_for_create("classical", "ed25519", config, migration_context=True)

    @pytest.mark.asyncio
    async def test_non_strict_mode_passes(self):
        config = MagicMock()
        config.get_mode = AsyncMock(return_value="permissive")
        await check_enforcement_for_create("classical", "ed25519", config)

    @pytest.mark.asyncio
    async def test_strict_mode_none_key_raises(self):
        config = MagicMock()
        config.get_mode = AsyncMock(return_value="strict")
        with pytest.raises(Exception, match="PQC key required"):
            await check_enforcement_for_create(None, None, config)

    @pytest.mark.asyncio
    async def test_strict_mode_classical_key_raises(self):
        config = MagicMock()
        config.get_mode = AsyncMock(return_value="strict")
        with pytest.raises(Exception, match="Classical algorithm"):
            await check_enforcement_for_create("classical", "ed25519", config)

    @pytest.mark.asyncio
    async def test_strict_mode_valid_pqc_passes(self):
        config = MagicMock()
        config.get_mode = AsyncMock(return_value="strict")
        # ML-DSA-65 is a valid PQC algorithm
        await check_enforcement_for_create("pqc", "ML-DSA-65", config)

    @pytest.mark.asyncio
    async def test_strict_mode_invalid_pqc_raises(self):
        config = MagicMock()
        config.get_mode = AsyncMock(return_value="strict")
        with pytest.raises(Exception, match="Unsupported PQC algorithm"):
            await check_enforcement_for_create("pqc", "INVALID-ALG", config)

    @pytest.mark.asyncio
    async def test_config_error_defaults_to_strict(self):
        config = MagicMock()
        config.get_mode = AsyncMock(side_effect=RuntimeError("boom"))
        # Defaults to strict, so None key type should raise
        with pytest.raises(Exception, match="PQC key required"):
            await check_enforcement_for_create(None, None, config)


# ---------------------------------------------------------------------------
# check_enforcement_for_update
# ---------------------------------------------------------------------------


class TestCheckEnforcementForUpdate:
    @pytest.mark.asyncio
    async def test_migration_context_skips_check(self):
        config = MagicMock()
        await check_enforcement_for_update("classical", config, migration_context=True)

    @pytest.mark.asyncio
    async def test_non_strict_passes(self):
        config = MagicMock()
        config.get_mode = AsyncMock(return_value="permissive")
        await check_enforcement_for_update("classical", config)

    @pytest.mark.asyncio
    async def test_strict_classical_raises(self):
        config = MagicMock()
        config.get_mode = AsyncMock(return_value="strict")
        with pytest.raises(Exception, match="migrated to PQC"):
            await check_enforcement_for_update("classical", config)

    @pytest.mark.asyncio
    async def test_strict_pqc_passes(self):
        config = MagicMock()
        config.get_mode = AsyncMock(return_value="strict")
        await check_enforcement_for_update("pqc", config)


# ---------------------------------------------------------------------------
# validate_constitutional_hash_pqc
# ---------------------------------------------------------------------------


class TestValidateConstitutionalHashPqc:
    @pytest.mark.asyncio
    async def test_missing_hash_returns_invalid(self):
        result = await validate_constitutional_hash_pqc({})
        assert result.valid is False
        assert any("Missing" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_hash_mismatch_returns_invalid(self):
        result = await validate_constitutional_hash_pqc(
            {"constitutional_hash": "wrong_hash"},
            expected_hash="608508a9bd224290",
        )
        assert result.valid is False
        assert any("mismatch" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_valid_hash_no_signature_returns_valid(self):
        result = await validate_constitutional_hash_pqc(
            {"constitutional_hash": "608508a9bd224290"},
            expected_hash="608508a9bd224290",
        )
        assert result.valid is True

    @pytest.mark.asyncio
    async def test_valid_hash_with_empty_signature_dict_no_pqc(self):
        """When signature is a dict without 'signature' key, PQC disabled => valid, no metadata."""
        result = await validate_constitutional_hash_pqc(
            {
                "constitutional_hash": "608508a9bd224290",
                "signature": {"some_other_key": "value"},
            },
            expected_hash="608508a9bd224290",
            pqc_config=None,
        )
        assert result.valid is True

    @pytest.mark.asyncio
    async def test_valid_hash_with_non_dict_signature(self):
        result = await validate_constitutional_hash_pqc(
            {
                "constitutional_hash": "608508a9bd224290",
                "signature": "raw_string",
            },
            expected_hash="608508a9bd224290",
            pqc_config=None,
        )
        assert result.valid is True


# ---------------------------------------------------------------------------
# validate_maci_record_pqc
# ---------------------------------------------------------------------------


class TestValidateMaciRecordPqc:
    @pytest.mark.asyncio
    async def test_missing_required_fields(self):
        result = await validate_maci_record_pqc({})
        assert result.valid is False
        assert any("agent_id" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_hash_mismatch(self):
        record = {
            "agent_id": "a1",
            "action": "validate",
            "timestamp": "2025-01-01T00:00:00Z",
            "constitutional_hash": "wrong",
        }
        result = await validate_maci_record_pqc(record, expected_hash="608508a9bd224290")
        assert result.valid is False
        assert any("mismatch" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_self_validation_detected(self):
        record = {
            "agent_id": "agent_1",
            "action": "validate",
            "timestamp": "2025-01-01T00:00:00Z",
            "constitutional_hash": "608508a9bd224290",
            "target_output_id": "output_42",
            "output_author": "agent_1",
        }
        result = await validate_maci_record_pqc(record, expected_hash="608508a9bd224290")
        assert result.valid is False
        assert any("Self-validation" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_valid_record_classical(self):
        record = {
            "agent_id": "agent_1",
            "action": "validate",
            "timestamp": "2025-01-01T00:00:00Z",
            "constitutional_hash": "608508a9bd224290",
        }
        result = await validate_maci_record_pqc(record, expected_hash="608508a9bd224290")
        assert result.valid is True

    @pytest.mark.asyncio
    async def test_valid_record_with_pqc_config_disabled(self):
        pqc_config = MagicMock()
        pqc_config.pqc_enabled = False
        record = {
            "agent_id": "agent_1",
            "action": "validate",
            "timestamp": "2025-01-01T00:00:00Z",
        }
        result = await validate_maci_record_pqc(
            record, expected_hash="608508a9bd224290", pqc_config=pqc_config
        )
        assert result.valid is True
        assert result.pqc_metadata is not None
        assert result.pqc_metadata.pqc_enabled is False
