"""
ACGS-2 Enhanced Agent Bus - Constitutional Validation Tests (Debug Version)
Constitutional Hash: 608508a9bd224290

This is a debug version of test_constitutional_validation.py with detailed output.
"""

import pytest

from enhanced_agent_bus.message_processor import MessageProcessor

# Import from module names that conftest.py patches
from enhanced_agent_bus.models import (
    CONSTITUTIONAL_HASH,
    AgentMessage,
    MessageStatus,
    MessageType,
)
from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)
# Mark all tests as governance tests (95% coverage required)
# Constitutional Hash: 608508a9bd224290
pytestmark = [pytest.mark.governance, pytest.mark.constitutional]


class TestMessageProcessorDebug:
    """Debug version of MessageProcessor tests."""

    @pytest.fixture
    def processor(self):
        """Create a MessageProcessor instance with MACI disabled for isolated testing."""
        # MACI is disabled for these legacy tests to isolate constitutional validation
        proc = MessageProcessor(
            enable_maci=False
        )  # test-only: MACI off — testing constitutional validation directly
        logger.debug("\n[DEBUG] Created MessageProcessor:")
        logger.info(f"  - Constitutional hash: {proc.constitutional_hash}")
        logger.info(f"  - Strategy: {proc.processing_strategy.get_name()}")
        logger.info(f"  - Rust enabled: {proc._use_rust}")
        return proc

    @pytest.fixture
    def valid_message(self):
        """Create a valid test message."""
        msg = AgentMessage(
            from_agent="test_agent",
            to_agent="target_agent",
            sender_id="test_sender",
            message_type=MessageType.COMMAND,
            content={"action": "test"},
            payload={"data": "test_data"},
        )
        logger.debug("\n[DEBUG] Created valid message:")
        logger.info(f"  - ID: {msg.message_id}")
        logger.info(f"  - Hash: {msg.constitutional_hash}")
        logger.info(f"  - Status: {msg.status}")
        logger.info(f"  - Expected hash: {CONSTITUTIONAL_HASH}")
        logger.info(f"  - Match: {msg.constitutional_hash == CONSTITUTIONAL_HASH}")
        return msg

    @pytest.fixture
    def invalid_hash_message(self):
        """Create a message with invalid constitutional hash."""
        msg = AgentMessage(
            from_agent="test_agent",
            to_agent="target_agent",
            sender_id="test_sender",
            message_type=MessageType.COMMAND,
            content={"action": "test"},
        )
        msg.constitutional_hash = "invalid_hash"
        logger.debug("\n[DEBUG] Created invalid hash message:")
        logger.info(f"  - ID: {msg.message_id}")
        logger.info(f"  - Hash: {msg.constitutional_hash}")
        logger.info(f"  - Status: {msg.status}")
        return msg

    async def test_process_valid_message_debug(self, processor, valid_message):
        """Test processing a valid message with debug output."""
        logger.debug("\n[DEBUG] Processing valid message...")

        result = await processor.process(valid_message)

        logger.debug("\n[DEBUG] Processing complete:")
        logger.info(f"  - Result valid: {result.is_valid}")
        logger.error(f"  - Result errors: {result.errors}")
        logger.warning(f"  - Result warnings: {result.warnings}")
        logger.info(f"  - Message status: {valid_message.status}")
        logger.info(f"  - Expected status: {MessageStatus.DELIVERED}")

        # Original assertions with detailed error messages
        assert result.is_valid, f"Expected valid result, got errors: {result.errors}"
        assert valid_message.status == MessageStatus.DELIVERED, (
            f"Expected status DELIVERED, got {valid_message.status}"
        )

        logger.debug("\n[DEBUG] ✓ Test passed")

    async def test_process_invalid_hash_message_debug(self, processor, invalid_hash_message):
        """Test processing message with invalid constitutional hash."""
        logger.debug("\n[DEBUG] Processing invalid hash message...")

        result = await processor.process(invalid_hash_message)

        logger.debug("\n[DEBUG] Processing complete:")
        logger.info(f"  - Result valid: {result.is_valid}")
        logger.error(f"  - Result errors: {result.errors}")
        logger.error(f"  - Number of errors: {len(result.errors)}")
        if result.errors:
            logger.error(f"  - First error: {result.errors[0]}")
            logger.info(
                f"  - Contains 'Constitutional hash mismatch': {'Constitutional hash mismatch' in result.errors[0]}"
            )

        # Original assertions with detailed error messages
        assert not result.is_valid, "Expected invalid result"
        assert len(result.errors) > 0, "Expected at least one error"
        assert "Constitutional hash mismatch" in result.errors[0], (
            f"Expected 'Constitutional hash mismatch' in error, got: {result.errors[0]}"
        )

        logger.debug("\n[DEBUG] ✓ Test passed")

    async def test_handler_registration_debug(self, processor, valid_message):
        """Test handler registration and execution."""
        logger.debug("\n[DEBUG] Testing handler registration...")

        handler_called = False

        async def test_handler(msg):
            nonlocal handler_called
            handler_called = True
            logger.debug(f"[DEBUG] Handler called with message {msg.message_id}")

        processor.register_handler(MessageType.COMMAND, test_handler)
        logger.debug("[DEBUG] Handler registered for COMMAND")

        result = await processor.process(valid_message)

        logger.debug("\n[DEBUG] Processing complete:")
        logger.info(f"  - Handler called: {handler_called}")
        logger.info(f"  - Result valid: {result.is_valid}")
        logger.info(f"  - Message status: {valid_message.status}")

        assert handler_called, "Expected handler to be called"
        assert valid_message.status == MessageStatus.DELIVERED

        logger.debug("\n[DEBUG] ✓ Test passed")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
