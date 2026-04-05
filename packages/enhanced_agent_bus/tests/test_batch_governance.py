"""
Unit tests for Batch Processor Governance.

Constitutional Hash: 608508a9bd224290
"""

import pytest

# Governance and constitutional compliance test markers
pytestmark = [pytest.mark.governance, pytest.mark.constitutional]
from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.batch_processor_infra.governance import (
    BatchGovernanceManager,
)
from enhanced_agent_bus.models import BatchRequest, BatchRequestItem


class TestBatchGovernanceManager:
    def test_validate_batch_context_pass(self):
        manager = BatchGovernanceManager()
        dummy_item = BatchRequestItem(
            from_agent="a", to_agent="b", content={}, message_type="governance_request"
        )
        batch = BatchRequest(
            batch_id="b1", items=[dummy_item], constitutional_hash=CONSTITUTIONAL_HASH
        )

        result = manager.validate_batch_context(batch)
        assert result.is_valid

    def test_validate_batch_context_fail(self):
        """Test that invalid constitutional hash is rejected at model creation."""
        from pydantic import ValidationError

        dummy_item = BatchRequestItem(
            from_agent="a", to_agent="b", content={}, message_type="governance_request"
        )
        # Invalid hash should be rejected at model creation time
        with pytest.raises(ValidationError) as exc_info:
            BatchRequest(batch_id="b1", items=[dummy_item], constitutional_hash="invalid")
        assert "constitutional_hash" in str(exc_info.value)
        assert "Invalid" in str(exc_info.value)

    def test_validate_item_pass(self):
        manager = BatchGovernanceManager()
        item = BatchRequestItem(
            from_agent="a",
            to_agent="b",
            content={},
            message_type="governance_request",
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

        result = manager.validate_item(item)
        assert result.is_valid

    def test_validate_item_fail(self):
        manager = BatchGovernanceManager()
        item = BatchRequestItem(
            from_agent="a",
            to_agent="b",
            content={},
            message_type="governance_request",
            constitutional_hash="wrong-hash",
        )

        result = manager.validate_item(item)
        assert not result.is_valid
        assert "mismatch" in result.errors[0].lower()
