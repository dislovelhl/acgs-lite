"""
Module.

Constitutional Hash: 608508a9bd224290
"""

import asyncio
import time
from unittest.mock import patch

from enhanced_agent_bus.agent_bus import EnhancedAgentBus
from enhanced_agent_bus.message_processor import MessageProcessor
from enhanced_agent_bus.models import CONSTITUTIONAL_HASH, AgentMessage, MessageType
from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)


class TestCellularResilience:
    """
    Stress tests for Phase 13 "Cellular Architecture".
    Focuses on Degraded Mode transitions and sub-5ms latency for Isolated Mode.
    """

    async def test_degraded_mode_on_processor_failure(self):
        """
        Verify that a failure in the MessageProcessor's primary path
        triggers a fallback to local 'DEGRADED' mode in the AgentBus.
        """
        # MACI is disabled for these legacy tests to isolate cellular resilience testing
        bus = EnhancedAgentBus(
            enable_maci=False,
            allow_unstarted=True,
        )  # test-only: MACI off — testing cellular resilience independently

        # Mock the processor to raise an exception, simulating a crash/hang
        with patch.object(
            bus._processor, "process", side_effect=Exception("Infrastructure Crash simulated")
        ):
            message = AgentMessage(
                message_type=MessageType.COMMAND,
                content={"action": "reboot"},
                from_agent="tester",
                to_agent="worker",
                constitutional_hash=CONSTITUTIONAL_HASH,
                metadata={"prevalidated": True},
            )

            result = await bus.send_message(message)

            # Should still be valid because of DEGRADED mode fallback (StaticHashValidationStrategy)
            assert result.is_valid
            assert result.metadata.get("governance_mode") == "DEGRADED"
            assert "Infrastructure Crash simulated" in result.metadata.get("fallback_reason")

    async def test_isolated_mode_latency_benchmark(self):
        """
        Verify that Isolated Mode (Governor-in-a-Box) maintains sub-5ms latency.
        """
        # Initialize processor in isolated mode (MACI disabled for isolated testing)
        processor = MessageProcessor(
            isolated_mode=True, enable_maci=False
        )  # test-only: MACI off — testing cellular resilience independently

        message = AgentMessage(
            message_type=MessageType.COMMAND,
            content={"action": "test"},
            from_agent="governor",
            to_agent="agent",
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

        # Warm up
        await processor.process(message)

        start_time = time.perf_counter()
        for _ in range(100):
            await processor.process(message)
        end_time = time.perf_counter()

        avg_latency_ms = ((end_time - start_time) / 100) * 1000
        logger.info(f"\n[Performance] Avg Isolated Processor Latency: {avg_latency_ms:.4f}ms")

        # Requirement: Sub-5ms
        assert avg_latency_ms < 5.0

    async def test_concurrency_stress_during_outage(self):
        """
        Stress test the AgentBus with high concurrency during a simulated outage.
        Ensures constitutional locks remain intact and state doesn't corrupt.
        """
        # MACI is disabled for these legacy tests to isolate stress testing
        bus = EnhancedAgentBus(
            enable_maci=False,
            allow_unstarted=True,
        )  # test-only: MACI off — testing cellular resilience independently

        # Simulate partial failure: 50% of requests fail to the processor
        # Use asyncio.Lock to prevent race conditions on counter
        counter = 0
        counter_lock = asyncio.Lock()
        original_process = bus._processor.process

        async def flaky_process(msg):
            nonlocal counter
            # Atomic counter increment with lock
            async with counter_lock:
                counter += 1
                current_count = counter

            # Decide based on stable counter value
            if current_count % 2 == 0:
                raise Exception("Transient Deliberation Outage")
            return await original_process(msg)

        with patch.object(bus._processor, "process", side_effect=flaky_process):
            tasks = []
            for i in range(50):
                msg = AgentMessage(
                    message_type=MessageType.COMMAND,
                    content={"id": i},
                    from_agent="tester",
                    to_agent="worker",
                    constitutional_hash=CONSTITUTIONAL_HASH,
                    metadata={"prevalidated": True},
                )
                tasks.append(bus.send_message(msg))

            results = await asyncio.gather(*tasks)

            # All messages should be valid (either via normal path or DEGRADED fallback)
            for res in results:
                assert res.is_valid

            # Verify we actually hit DEGRADED mode for half of them
            degraded_count = sum(
                1 for r in results if r.metadata.get("governance_mode") == "DEGRADED"
            )
            assert degraded_count == 25
            logger.info(
                "[Stress] 50 requests processed: 25 normal, 25 DEGRADED. Zero constitutional breaches."
            )

    async def test_isolated_mode_dependency_decoupling(self):
        """
        Verify that Isolated Mode actually disables dynamic policy lookups.
        Even when use_dynamic_policy=True, isolated_mode=True should override it.
        """
        # Import the module to check its constants
        import enhanced_agent_bus.message_processor as message_processor

        # Test 1: Isolated mode always disables dynamic policy regardless of setting
        # MACI is disabled for these legacy tests to isolate policy decoupling testing
        proc_isolated = MessageProcessor(
            use_dynamic_policy=True,
            isolated_mode=True,
            enable_maci=False,  # test-only: MACI off — testing cellular resilience independently
        )
        assert not proc_isolated._use_dynamic_policy, (
            "Isolated mode should always disable dynamic policy"
        )
        assert proc_isolated._isolated_mode, "Isolated mode flag should be True"

        # Test 2: Isolated mode = False respects POLICY_CLIENT_AVAILABLE
        # (If POLICY_CLIENT_AVAILABLE is False, _use_dynamic_policy remains False)
        proc_normal = MessageProcessor(
            use_dynamic_policy=True,
            isolated_mode=False,
            enable_maci=False,  # test-only: MACI off — testing cellular resilience independently
        )
        expected_dynamic = message_processor.POLICY_CLIENT_AVAILABLE
        assert proc_normal._use_dynamic_policy == expected_dynamic, (
            f"Non-isolated mode with use_dynamic_policy=True should match POLICY_CLIENT_AVAILABLE={expected_dynamic}"
        )
        assert not proc_normal._isolated_mode, "Non-isolated mode flag should be False"
