"""
Module.

Constitutional Hash: 608508a9bd224290
"""

import asyncio
import logging
import time

try:
    from src.core.breakthrough.verification.z3_smt_verifier import (
        ConstitutionalVerifier,
        PolicySpecification,
    )
except ImportError:
    ConstitutionalVerifier = None  # type: ignore[assignment,misc]
    PolicySpecification = None  # type: ignore[assignment,misc]

from enhanced_agent_bus.message_processor import MessageProcessor
from enhanced_agent_bus.models import AgentMessage, MessageType, Priority
from enhanced_agent_bus.observability.structured_logging import get_logger

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = get_logger(__name__)


async def run_verification():
    logger.info("Starting Session Isolation and Performance Verification...")

    # 1. Initialize Verifier and Processor
    verifier = ConstitutionalVerifier()
    processor = MessageProcessor(constitutional_verifier=verifier)

    # 2. Define a base policy that allows everything but 'restricted_action'
    # Actually, the verifier usually has constitutional policies loaded.
    # We'll add a session-specific override that forbids something.

    session_a = "session_alpha"
    session_b = "session_beta"

    # Define an override for Session A: forbid 'danger_score > 5'
    overrides_a = [
        {
            "policy_id": "policy_a_strict",
            "name": "Strict Danger Policy",
            "variables": {"danger_score": "int"},
            "constraints": ["danger_score <= 5"],
        }
    ]

    # Load overrides
    verifier.load_session_overrides(session_a, overrides_a)

    # 3. Test Session Isolation
    logger.info("Testing Session Isolation...")

    msg_a_safe = AgentMessage(
        content={"danger_score": 3},
        message_type=MessageType.COMMAND,
        priority=Priority.MEDIUM,
        conversation_id=session_a,
        tenant_id="default-tenant",
    )

    msg_a_unsafe = AgentMessage(
        content={"danger_score": 10},
        message_type=MessageType.COMMAND,
        priority=Priority.MEDIUM,
        conversation_id=session_a,
        tenant_id="default-tenant",
    )

    msg_b_unsafe_content = AgentMessage(
        content={"danger_score": 10},
        message_type=MessageType.COMMAND,
        priority=Priority.MEDIUM,
        conversation_id=session_b,  # No override for session B
        tenant_id="default-tenant",
    )

    # Verify Session A (with override)
    res_a_safe = await processor.process(msg_a_safe)
    if not res_a_safe.is_valid:
        logger.error(f"Session A safe message rejected: {res_a_safe.errors}")
    assert res_a_safe.is_valid, f"Session A safe message rejected: {res_a_safe.errors}"

    res_a_unsafe = await processor.process(msg_a_unsafe)
    assert not res_a_unsafe.is_valid, "Session A unsafe message accepted"
    logger.info("✓ Session A correctly enforced policy override")

    # Verify Session B (isolation)
    res_b_unsafe = await processor.process(msg_b_unsafe_content)
    assert res_b_unsafe.is_valid, "Session B message rejected (leaked override from A)"
    logger.info("✓ Session B isolated from Session A overrides")

    # 4. Performance Measurement (Switching Overhead)
    logger.info("Measuring Switching Overhead...")

    iterations = 100
    start_time = time.perf_counter()

    for i in range(iterations):
        # Swap sessions every iteration
        sess = session_a if i % 2 == 0 else session_b
        msg = AgentMessage(
            content={"danger_score": 3},
            message_type=MessageType.COMMAND,
            priority=Priority.MEDIUM,
            conversation_id=sess,
            tenant_id="default-tenant",
        )
        await processor.process(msg)

    end_time = time.perf_counter()
    avg_latency = (end_time - start_time) / iterations * 1000

    logger.info(f"Average processing latency (with session switching): {avg_latency:.4f}ms")

    if avg_latency < 5.0:  # Giving some room for general processing overhead
        logger.info("✓ Switching overhead is within acceptable limits")
    else:
        logger.warning(
            f"Latency {avg_latency:.4f}ms might be high for target, but includes full processing."
        )

    # 5. Test Clearing Overrides
    logger.info("Testing Clearance...")
    verifier.clear_session_overrides(session_a)
    res_a_previously_unsafe = await processor.process(msg_a_unsafe)
    assert res_a_previously_unsafe.is_valid, "Session A still enforcing cleared override"
    logger.info("✓ Session overrides cleared successfully")

    logger.info("Verification Complete!")


if __name__ == "__main__":
    asyncio.run(run_verification())
