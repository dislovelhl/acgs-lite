"""
Shadow Mode Verification for Unified PSV-Verus Integration
Constitutional Hash: 608508a9bd224290

NOTE: This is a standalone verification script, not a library module.
"""

import asyncio
import logging

from enhanced_agent_bus._compat.policy.models import VerificationStatus
from enhanced_agent_bus.observability.structured_logging import get_logger

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = get_logger(__name__)


async def verify_proven_integration():
    """
    Verifies that the AgentBusIntegration correctly uses the proven policy generator.
    """
    from enhanced_agent_bus.ai_assistant.integration import (
        AgentBusIntegration,
        IntegrationConfig,
    )

    logger.info("Starting Shadow Mode Verification for Unified Generator...")

    # Initialize integration with governance enabled
    config = IntegrationConfig(enable_governance=True)
    integration = AgentBusIntegration(config=config)

    # Mock NLU result for a sensitive action
    class MockIntent:
        """Minimal intent stub for integration testing."""

        def __init__(self, name):
            self.name = name

    class MockNLUResult:
        """Minimal NLU result stub for integration testing."""

        def __init__(self, intent_name):
            self.primary_intent = MockIntent(intent_name)
            self.entities = []

    class MockContext:
        """Minimal context stub for integration testing."""

        def __init__(self):
            self.user_id = "test_user"
            self.session_id = "test_session"

    # Test Case 1: Admin access (should be PROVEN/VERIFIED)
    nlu_admin = MockNLUResult("admin_access")
    context = MockContext()

    logger.info("Case 1: Admin Access...")
    result_admin = await integration._check_governance(nlu_admin, context)
    logger.info(f"Result: {result_admin}")

    assert result_admin["is_allowed"] is True
    assert result_admin["verification_status"] in [
        VerificationStatus.VERIFIED.value,
        VerificationStatus.PROVEN.value,
    ]

    # Test Case 2: Restricted action (should be handled by generator)
    nlu_restricted = MockNLUResult("delete_all_data")
    logger.info("Case 2: Restricted Action...")
    result_restricted = await integration._check_governance(nlu_restricted, context)
    logger.info(f"Result: {result_restricted}")

    # Even if restricted, the formality of the proof is what we're testing
    assert "policy_id" in result_restricted

    logger.info("Shadow Mode Verification Successful!")


if __name__ == "__main__":
    asyncio.run(verify_proven_integration())
