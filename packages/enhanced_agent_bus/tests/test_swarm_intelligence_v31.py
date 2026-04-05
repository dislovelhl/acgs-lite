"""
Comprehensive tests for Swarm Intelligence Layer v3.1

Tests new v3.1 features:
- Byzantine consensus enhancements (timeout recovery, fault detection)
- Enhanced MessageBus (TTL, priority, patterns, dead letter queue)
- Self-healing agent health monitoring
- Predictive task decomposition with ML patterns
- Dashboard metrics endpoint

Constitutional Hash: 608508a9bd224290
"""

import asyncio
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from ..swarm_intelligence import (
    CONSTITUTIONAL_HASH,
    AgentCapability,
    AgentMessage,
    AgentState,
    CapabilityMatcher,
    ConsensusMechanism,
    ConsensusProposal,
    ConsensusType,
    DecompositionPattern,
    MessageBus,
    MessageEnvelope,
    SwarmAgent,
    SwarmCoordinator,
    SwarmTask,
    TaskDecomposer,
    TaskPriority,
    create_swarm_coordinator,
)

# =============================================================================
# Byzantine Consensus v3.1 Tests
# =============================================================================


class TestByzantineConsensusV31:
    """Tests for enhanced Byzantine consensus with fault tolerance."""

    async def test_consensus_timeout_recovery(self):
        """Consensus should auto-resolve on timeout with default=False."""
        consensus = ConsensusMechanism()

        proposal = await consensus.create_proposal(
            proposer_id="agent-001",
            action="test_action",
            context={},
            timeout_seconds=1,  # 1 second timeout
        )

        # Wait for timeout
        await asyncio.sleep(1.1)

        # Check consensus with timeout recovery
        is_decided, result = consensus.check_consensus(
            proposal.id, total_voters=3, timeout_recovery=True
        )

        assert is_decided is True
        assert result is False  # Default to rejection on timeout
        assert proposal.result is False

    async def test_byzantine_fault_detection(self):
        """Detect Byzantine fault when voter changes their vote."""
        consensus = ConsensusMechanism()

        proposal = await consensus.create_proposal(
            proposer_id="agent-001",
            action="test_action",
            context={},
        )

        # Cast initial vote
        result1 = await consensus.vote(proposal.id, "agent-002", True)
        assert result1 is True

        # Attempt to change vote (Byzantine fault)
        result2 = await consensus.vote(proposal.id, "agent-002", False)
        assert result2 is False  # Vote change should be rejected

        # Check faulty voters
        faulty = consensus.get_faulty_voters()
        assert "agent-002" in faulty

    async def test_consensus_proposal_expiration_cleanup(self):
        """Expired proposals should be cleaned up automatically."""
        consensus = ConsensusMechanism(max_proposal_age_minutes=0)

        proposal = await consensus.create_proposal(
            proposer_id="agent-001",
            action="test_action",
            context={},
            timeout_seconds=0,
        )

        # Force resolve to add to completed
        await consensus.force_resolve(proposal.id, True)

        # Create another proposal to trigger cleanup
        proposal2 = await consensus.create_proposal(
            proposer_id="agent-001",
            action="test_action2",
            context={},
        )

        # Old proposal should be cleaned up
        assert consensus.get_proposal(proposal.id) is None

    async def test_consensus_force_resolve(self):
        """Should be able to forcefully resolve a proposal."""
        consensus = ConsensusMechanism()

        proposal = await consensus.create_proposal(
            proposer_id="agent-001",
            action="test_action",
            context={},
        )

        result = await consensus.force_resolve(proposal.id, True)
        assert result is True
        assert proposal.result is True
        assert proposal.completed_at is not None

    def test_consensus_proposal_stats(self):
        """Should provide statistics about proposals."""
        consensus = ConsensusMechanism()

        stats = consensus.get_proposal_stats()
        assert "total_proposals" in stats
        assert "active_proposals" in stats
        assert "completed_proposals" in stats
        assert "faulty_voters" in stats


# =============================================================================
# Enhanced MessageBus v3.1 Tests
# =============================================================================


class TestMessageBusV31:
    """Tests for enhanced MessageBus with TTL, priority, and patterns."""

    async def test_message_ttl_expiration(self):
        """Messages should expire after TTL."""
        bus = MessageBus(default_ttl_seconds=1)

        # Send message with 1 second TTL
        msg_id = await bus.send(
            sender_id="agent-001",
            recipient_id="agent-002",
            message_type="test",
            payload={"data": "test"},
            ttl_seconds=1,
        )

        # Wait for expiration
        await asyncio.sleep(1.1)

        # Message should be expired
        messages = await bus.receive("agent-002")
        assert len(messages) == 0  # Expired messages filtered out

    async def test_message_priority_ordering(self):
        """Messages should be returned in priority order."""
        bus = MessageBus()

        # Send messages with different priorities
        await bus.send("agent-001", "agent-003", "test", {"p": 5}, priority=5)
        await bus.send("agent-001", "agent-003", "test", {"p": 1}, priority=1)
        await bus.send("agent-001", "agent-003", "test", {"p": 3}, priority=3)

        # Receive messages
        messages = await bus.receive("agent-003")

        # Should be in priority order (1, 3, 5)
        assert messages[0].payload["p"] == 1
        assert messages[1].payload["p"] == 3
        assert messages[2].payload["p"] == 5

    async def test_pattern_based_subscription(self):
        """Pattern subscriptions should match multiple topics."""
        bus = MessageBus()

        # Subscribe with pattern
        await bus.subscribe("agent-001", "events.*", pattern=True)

        # Publish to matching topics
        count1 = await bus.publish("agent-002", "events.user.login", {})
        count2 = await bus.publish("agent-002", "events.system.error", {})
        count3 = await bus.publish("agent-002", "other.topic", {})  # Should not match

        assert count1 == 1
        assert count2 == 1
        assert count3 == 0

    async def test_dead_letter_queue(self):
        """Expired unacknowledged messages should go to dead letter queue."""
        bus = MessageBus(default_ttl_seconds=0)

        # Send message with very short TTL
        await bus.send(
            sender_id="agent-001",
            recipient_id="agent-002",
            message_type="test",
            payload={"data": "test"},
            ttl_seconds=1,
        )

        # Wait for expiration
        await asyncio.sleep(1.1)

        # Trigger cleanup by receiving (this should move expired unacknowledged messages to DLQ)
        await bus.receive("agent-002")

        # Check dead letter queue
        dlq = await bus.get_dead_letter_queue()
        assert len(dlq) >= 1

    async def test_persistent_message_replay(self):
        """Persistent messages should be replayable."""
        bus = MessageBus()

        # Send persistent message
        await bus.send(
            sender_id="agent-001",
            recipient_id="agent-002",
            message_type="test",
            payload={"data": "persistent"},
            persistent=True,
        )

        # Replay persistent messages
        replayed = await bus.replay_persistent_messages("agent-002")
        assert len(replayed) == 1
        assert replayed[0].payload["data"] == "persistent"

    async def test_message_stats(self):
        """Should provide message statistics."""
        bus = MessageBus()

        await bus.send("agent-001", "agent-002", "test", {})
        await bus.send("agent-001", "agent-003", "test", {})

        # Global stats
        stats = await bus.get_message_stats()
        assert stats["total_messages"] == 2

        # Per-agent stats
        stats2 = await bus.get_message_stats("agent-002")
        assert stats2["total_messages"] == 1


# =============================================================================
# Self-Healing Health Monitoring Tests
# =============================================================================


class TestSelfHealingHealth:
    """Tests for self-healing agent health monitoring."""

    async def test_health_check_detects_stuck_task(self):
        """Health check should detect agents stuck on tasks."""
        coordinator = SwarmCoordinator()

        # Create agent with capability to match task
        agent = await coordinator.spawn_agent(
            "TestAgent",
            [AgentCapability(name="testing", description="Test capability", proficiency=0.8)],
        )
        task_id = await coordinator.submit_task("Test task", ["testing"], decompose=False)

        # Assign task to agent
        assigned = await coordinator.assign_tasks()
        assert assigned == 1, "Task should be assigned"
        assert agent.state == AgentState.BUSY, "Agent should be busy"
        assert agent.current_task == task_id, "Agent should have the task assigned"

        # Manually set task start time to be old (超过 600s 限制)
        task = coordinator.get_task(task_id)
        task.started_at = datetime.now(UTC) - timedelta(seconds=1000)

        # Health check should detect stuck task
        health = await coordinator.check_agent_health(agent.id, max_task_duration_seconds=600)

        assert health["healthy"] is False, f"Expected unhealthy but got: {health}"
        assert "stuck" in str(health["issues"]).lower() or "task" in str(health["issues"]).lower()

    async def test_health_check_high_failure_rate(self):
        """Health check should detect high failure rate."""
        coordinator = SwarmCoordinator()

        agent = await coordinator.spawn_agent("TestAgent", ["general"])

        # Simulate high failure rate
        agent.tasks_failed = 8
        agent.tasks_completed = 2

        health = await coordinator.check_agent_health(agent.id)

        assert health["healthy"] is False
        assert health["action"] == "terminate"
        assert "failure rate" in str(health["issues"]).lower()

    async def test_self_healing_terminate_action(self):
        """Self-healing should terminate unhealthy agents."""
        coordinator = SwarmCoordinator()

        agent = await coordinator.spawn_agent("TestAgent", ["general"])
        agent.tasks_failed = 8
        agent.tasks_completed = 2

        health = await coordinator.check_agent_health(agent.id)
        assert health["action"] == "terminate"

        # Perform healing
        result = await coordinator.perform_self_healing(agent.id, health)
        assert result is True

        # Agent should be terminated
        assert coordinator.get_agent(agent.id) is None

    async def test_run_health_checks_batch(self):
        """Should run health checks on all agents."""
        coordinator = SwarmCoordinator()

        await coordinator.spawn_agent("Agent1", ["general"])
        await coordinator.spawn_agent("Agent2", ["general"])

        results = await coordinator.run_health_checks(auto_heal=False)

        assert len(results) == 2
        for result in results:
            assert "healthy" in result
            assert "agent_id" in result

    def test_health_stats(self):
        """Should provide comprehensive health statistics."""
        coordinator = SwarmCoordinator()

        # Can't easily add agents without async, but we can test the method exists
        stats = coordinator.get_health_stats()
        assert "healthy_agents" in stats
        assert "unhealthy_agents" in stats
        assert "health_ratio" in stats


# =============================================================================
# Predictive Task Decomposition Tests
# =============================================================================


class TestPredictiveDecomposition:
    """Tests for ML-based predictive task decomposition."""

    def test_predict_api_endpoint_task(self):
        """Should predict API endpoint task characteristics."""
        decomposer = TaskDecomposer()

        task = SwarmTask(
            id="task-001",
            description="Create REST API endpoint for user authentication",
            required_capabilities=["api", "coding"],
            priority=TaskPriority.NORMAL,
        )

        predictions = decomposer.predict_task_characteristics(task)

        assert predictions["matched_pattern"] == "api_endpoint"
        assert predictions["predicted_complexity"] == 4.5
        assert predictions["success_rate"] == 0.88
        assert predictions["confidence"] > 0

    def test_predict_database_migration_task(self):
        """Should predict database migration task characteristics."""
        decomposer = TaskDecomposer()

        task = SwarmTask(
            id="task-002",
            description="Migrate database schema for new user table",
            required_capabilities=["database", "sql"],
            priority=TaskPriority.NORMAL,
        )

        predictions = decomposer.predict_task_characteristics(task)

        assert predictions["matched_pattern"] == "database_migration"
        assert predictions["predicted_complexity"] == 7.0
        assert predictions["success_rate"] == 0.75

    def test_predict_unknown_task_pattern(self):
        """Should provide default predictions for unknown patterns."""
        decomposer = TaskDecomposer()

        task = SwarmTask(
            id="task-003",
            description="Something completely unrelated",
            required_capabilities=["unknown"],
            priority=TaskPriority.NORMAL,
        )

        predictions = decomposer.predict_task_characteristics(task)

        assert predictions["matched_pattern"] is None
        assert predictions["confidence"] == 0.0
        assert predictions["predicted_complexity"] == 5.0  # Default

    def test_select_optimal_strategy(self):
        """Should select appropriate strategy based on predictions."""
        decomposer = TaskDecomposer()

        # High complexity -> granular
        high_complexity = {
            "predicted_complexity": 8.0,
            "success_rate": 0.9,
        }
        strategy = decomposer.select_optimal_strategy(None, high_complexity)
        assert strategy == "granular"

        # Low success rate -> conservative
        low_success = {
            "predicted_complexity": 5.0,
            "success_rate": 0.70,
        }
        strategy = decomposer.select_optimal_strategy(None, low_success)
        assert strategy == "conservative"

        # Fast task -> streamlined
        fast_task = {
            "predicted_complexity": 3.0,
            "success_rate": 0.9,
            "estimated_completion_time": 900,  # 15 minutes
        }
        strategy = decomposer.select_optimal_strategy(None, fast_task)
        assert strategy == "streamlined"

    def test_decompose_refactoring_task(self):
        """Should decompose refactoring tasks."""
        decomposer = TaskDecomposer()

        task = SwarmTask(
            id="task-004",
            description="Refactor the authentication module",
            required_capabilities=["refactoring"],
            priority=TaskPriority.NORMAL,
        )

        subtasks = decomposer.decompose(task, task_type="refactoring")

        assert len(subtasks) == 3
        assert any("analyze" in st.id for st in subtasks)
        assert any("refactor" in st.id for st in subtasks)
        assert any("validate" in st.id for st in subtasks)

    def test_decompose_bug_fix_task(self):
        """Should decompose bug fix tasks."""
        decomposer = TaskDecomposer()

        task = SwarmTask(
            id="task-005",
            description="Fix login bug",
            required_capabilities=["debugging"],
            priority=TaskPriority.NORMAL,
        )

        subtasks = decomposer.decompose(task, task_type="bug_fix")

        assert len(subtasks) == 4
        assert any("reproduce" in st.id for st in subtasks)
        assert any("root_cause" in st.id for st in subtasks)
        assert any("fix" in st.id for st in subtasks)


# =============================================================================
# Dashboard Metrics Tests
# =============================================================================


class TestDashboardMetrics:
    """Tests for dashboard metrics endpoint."""

    async def test_dashboard_metrics_structure(self):
        """Dashboard should return comprehensive metrics structure."""
        coordinator = create_swarm_coordinator()

        dashboard = await coordinator.get_dashboard_metrics()

        # Check top-level structure
        assert "timestamp" in dashboard
        assert "constitutional_hash" in dashboard
        assert "version" in dashboard
        assert dashboard["version"] == "3.1"

        # Check agents section
        assert "agents" in dashboard
        agents = dashboard["agents"]
        assert "total" in agents
        assert "healthy" in agents
        assert "utilization_rate" in agents

        # Check tasks section
        assert "tasks" in dashboard
        tasks = dashboard["tasks"]
        assert "pending" in tasks
        assert "success_rate" in tasks

        # Check consensus section
        assert "consensus" in dashboard

        # Check messaging section
        assert "messaging" in dashboard

        # Check lifecycle section
        assert "lifecycle" in dashboard

        # Check health section
        assert "health" in dashboard

    async def test_dashboard_metrics_with_agents(self):
        """Dashboard should reflect actual agent state."""
        coordinator = create_swarm_coordinator()

        # Spawn some agents
        await coordinator.spawn_agent("Agent1", ["general"])
        await coordinator.spawn_agent("Agent2", ["general"])

        dashboard = await coordinator.get_dashboard_metrics()

        assert dashboard["agents"]["total"] == 2
        assert dashboard["agents"]["healthy"] == 2
        assert dashboard["health"]["health_ratio"] == 1.0


# =============================================================================
# Integration Tests
# =============================================================================


class TestSwarmV31Integration:
    """Integration tests for v3.1 features working together."""

    async def test_full_task_lifecycle_with_predictions(self):
        """Full task lifecycle should use predictive decomposition."""
        coordinator = create_swarm_coordinator()

        # Spawn agent with proper capabilities
        agent = await coordinator.spawn_agent(
            "TestAgent",
            [AgentCapability(name="coding", description="Coding capability", proficiency=0.9)],
        )

        # Submit task that triggers refactoring decomposition
        # Must include exact keyword "refactoring" in description
        task_id = await coordinator.submit_task(
            "Refactoring authentication module",
            ["refactoring", "coding"],
            decompose=True,
        )

        # Task should be decomposed (refactoring pattern creates 3 subtasks)
        tasks = list(coordinator._tasks.values())
        assert len(tasks) >= 3, (
            f"Expected at least 3 subtasks, got {len(tasks)}: {[t.description for t in tasks]}"
        )

    async def test_health_monitoring_with_messaging(self):
        """Health monitoring should work with message bus."""
        coordinator = create_swarm_coordinator()

        agent = await coordinator.spawn_agent("TestAgent", ["general"])

        # Send health check message
        await coordinator.send_message(
            sender_id="system",
            recipient_id=agent.id,
            message_type="health_check",
            payload={"timestamp": datetime.now(UTC).isoformat()},
        )

        # Update heartbeat
        result = await coordinator.update_agent_heartbeat(agent.id)
        assert result is True

        # Check health
        health = await coordinator.check_agent_health(agent.id)
        assert health["healthy"] is True


# =============================================================================
# Constitutional Compliance Tests
# =============================================================================


class TestConstitutionalComplianceV31:
    """Ensure all v3.1 components maintain constitutional compliance."""

    def test_message_envelope_constitutional_hash(self):
        """MessageEnvelope should embed constitutional hash via AgentMessage."""
        message = AgentMessage(
            id="msg-001",
            sender_id="agent-001",
            recipient_id="agent-002",
            message_type="test",
            payload={},
        )
        envelope = MessageEnvelope(message=message)

        assert envelope.message.constitutional_hash == CONSTITUTIONAL_HASH

    def test_decomposition_pattern_constitutional_compliance(self):
        """Decomposition patterns should not violate constitutional principles."""
        # This is more of a placeholder - in real implementation,
        # patterns would be validated against constitutional rules
        pattern = DecompositionPattern(
            pattern_name="test",
            keywords=["test"],
            avg_completion_time=3600.0,
            avg_subtasks=4,
            success_rate=0.8,
            complexity_score=5.0,
        )

        assert pattern.complexity_score <= 10.0
        assert 0.0 <= pattern.success_rate <= 1.0
