# Constitutional Hash: 608508a9bd224290
"""
Comprehensive tests for swarm_intelligence/models.py targeting ≥95% coverage.

Tests cover:
- AgentCapability dataclass (all fields, defaults, edge cases)
- SwarmTask dataclass (all fields, defaults, optional fields)
- SwarmAgent dataclass (all fields, defaults)
- ConsensusProposal dataclass (all fields, defaults)
- AgentMessage dataclass (all fields, broadcast case)
- DecompositionPattern dataclass (all fields)
- MessageEnvelope dataclass (__post_init__, is_expired logic, edge cases)
"""

from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import patch

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.swarm_intelligence.enums import (
    AgentState,
    ConsensusType,
    TaskPriority,
)
from enhanced_agent_bus.swarm_intelligence.models import (
    AgentCapability,
    AgentMessage,
    ConsensusProposal,
    DecompositionPattern,
    MessageEnvelope,
    SwarmAgent,
    SwarmTask,
)

# ---------------------------------------------------------------------------
# AgentCapability
# ---------------------------------------------------------------------------


class TestAgentCapability:
    """Tests for the AgentCapability dataclass."""

    def test_minimal_construction(self):
        cap = AgentCapability(name="compute", description="General computation")
        assert cap.name == "compute"
        assert cap.description == "General computation"

    def test_default_proficiency(self):
        cap = AgentCapability(name="a", description="b")
        assert cap.proficiency == 1.0

    def test_default_cost_factor(self):
        cap = AgentCapability(name="a", description="b")
        assert cap.cost_factor == 1.0

    def test_default_max_concurrent(self):
        cap = AgentCapability(name="a", description="b")
        assert cap.max_concurrent == 1

    def test_explicit_all_fields(self):
        cap = AgentCapability(
            name="nlp",
            description="Natural language processing",
            proficiency=0.9,
            cost_factor=2.5,
            max_concurrent=4,
        )
        assert cap.name == "nlp"
        assert cap.description == "Natural language processing"
        assert cap.proficiency == 0.9
        assert cap.cost_factor == 2.5
        assert cap.max_concurrent == 4

    def test_proficiency_zero(self):
        cap = AgentCapability(name="a", description="b", proficiency=0.0)
        assert cap.proficiency == 0.0

    def test_proficiency_max(self):
        cap = AgentCapability(name="a", description="b", proficiency=1.0)
        assert cap.proficiency == 1.0

    def test_cost_factor_zero(self):
        cap = AgentCapability(name="a", description="b", cost_factor=0.0)
        assert cap.cost_factor == 0.0

    def test_max_concurrent_large(self):
        cap = AgentCapability(name="a", description="b", max_concurrent=100)
        assert cap.max_concurrent == 100

    def test_equality(self):
        cap1 = AgentCapability(
            name="a", description="b", proficiency=0.5, cost_factor=1.5, max_concurrent=2
        )
        cap2 = AgentCapability(
            name="a", description="b", proficiency=0.5, cost_factor=1.5, max_concurrent=2
        )
        assert cap1 == cap2

    def test_inequality(self):
        cap1 = AgentCapability(name="a", description="b")
        cap2 = AgentCapability(name="c", description="b")
        assert cap1 != cap2


# ---------------------------------------------------------------------------
# SwarmTask
# ---------------------------------------------------------------------------


class TestSwarmTask:
    """Tests for the SwarmTask dataclass."""

    def _make_task(self, **overrides):
        defaults = {
            "id": "task-001",
            "description": "Do something",
            "required_capabilities": ["compute"],
        }
        defaults.update(overrides)
        return SwarmTask(**defaults)

    def test_minimal_construction(self):
        task = self._make_task()
        assert task.id == "task-001"
        assert task.description == "Do something"
        assert task.required_capabilities == ["compute"]

    def test_default_priority(self):
        task = self._make_task()
        assert task.priority == TaskPriority.NORMAL

    def test_default_dependencies_empty(self):
        task = self._make_task()
        assert task.dependencies == []

    def test_default_timeout(self):
        task = self._make_task()
        assert task.timeout_seconds == 300

    def test_default_retry_count(self):
        task = self._make_task()
        assert task.retry_count == 0

    def test_default_max_retries(self):
        task = self._make_task()
        assert task.max_retries == 3

    def test_constitutional_hash_default(self):
        task = self._make_task()
        assert task.constitutional_hash == CONSTITUTIONAL_HASH

    def test_created_at_is_utc_datetime(self):
        task = self._make_task()
        assert isinstance(task.created_at, datetime)
        assert task.created_at.tzinfo is not None

    def test_started_at_none_by_default(self):
        task = self._make_task()
        assert task.started_at is None

    def test_completed_at_none_by_default(self):
        task = self._make_task()
        assert task.completed_at is None

    def test_assigned_agent_none_by_default(self):
        task = self._make_task()
        assert task.assigned_agent is None

    def test_result_none_by_default(self):
        task = self._make_task()
        assert task.result is None

    def test_error_none_by_default(self):
        task = self._make_task()
        assert task.error is None

    def test_explicit_priority_critical(self):
        task = self._make_task(priority=TaskPriority.CRITICAL)
        assert task.priority == TaskPriority.CRITICAL

    def test_explicit_priority_low(self):
        task = self._make_task(priority=TaskPriority.LOW)
        assert task.priority == TaskPriority.LOW

    def test_with_dependencies(self):
        task = self._make_task(dependencies=["task-000", "task-999"])
        assert task.dependencies == ["task-000", "task-999"]

    def test_with_assigned_agent(self):
        task = self._make_task(assigned_agent="agent-7")
        assert task.assigned_agent == "agent-7"

    def test_with_result(self):
        task = self._make_task(result={"output": 42})
        assert task.result == {"output": 42}

    def test_with_error(self):
        task = self._make_task(error="timeout exceeded")
        assert task.error == "timeout exceeded"

    def test_multiple_required_capabilities(self):
        task = self._make_task(required_capabilities=["nlp", "vision", "planning"])
        assert len(task.required_capabilities) == 3

    def test_dependencies_are_independent_instances(self):
        task1 = self._make_task()
        task2 = self._make_task()
        task1.dependencies.append("x")
        assert task2.dependencies == []

    def test_explicit_created_at(self):
        fixed = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        task = self._make_task(created_at=fixed)
        assert task.created_at == fixed

    def test_explicit_started_at(self):
        fixed = datetime(2025, 1, 1, 12, 5, 0, tzinfo=UTC)
        task = self._make_task(started_at=fixed)
        assert task.started_at == fixed

    def test_explicit_completed_at(self):
        fixed = datetime(2025, 1, 1, 12, 10, 0, tzinfo=UTC)
        task = self._make_task(completed_at=fixed)
        assert task.completed_at == fixed

    def test_custom_timeout(self):
        task = self._make_task(timeout_seconds=60)
        assert task.timeout_seconds == 60

    def test_custom_retry_count(self):
        task = self._make_task(retry_count=2)
        assert task.retry_count == 2

    def test_custom_max_retries(self):
        task = self._make_task(max_retries=10)
        assert task.max_retries == 10


# ---------------------------------------------------------------------------
# SwarmAgent
# ---------------------------------------------------------------------------


class TestSwarmAgent:
    """Tests for the SwarmAgent dataclass."""

    def _make_capability(self):
        return AgentCapability(name="compute", description="General compute")

    def _make_agent(self, **overrides):
        defaults = {
            "id": "agent-001",
            "name": "Worker-1",
            "capabilities": [self._make_capability()],
        }
        defaults.update(overrides)
        return SwarmAgent(**defaults)

    def test_minimal_construction(self):
        agent = self._make_agent()
        assert agent.id == "agent-001"
        assert agent.name == "Worker-1"

    def test_default_state(self):
        agent = self._make_agent()
        assert agent.state == AgentState.INITIALIZING

    def test_default_current_task_none(self):
        agent = self._make_agent()
        assert agent.current_task is None

    def test_default_tasks_completed(self):
        agent = self._make_agent()
        assert agent.tasks_completed == 0

    def test_default_tasks_failed(self):
        agent = self._make_agent()
        assert agent.tasks_failed == 0

    def test_default_total_execution_time(self):
        agent = self._make_agent()
        assert agent.total_execution_time == 0.0

    def test_created_at_utc(self):
        agent = self._make_agent()
        assert isinstance(agent.created_at, datetime)
        assert agent.created_at.tzinfo is not None

    def test_last_active_utc(self):
        agent = self._make_agent()
        assert isinstance(agent.last_active, datetime)
        assert agent.last_active.tzinfo is not None

    def test_constitutional_hash_default(self):
        agent = self._make_agent()
        assert agent.constitutional_hash == CONSTITUTIONAL_HASH

    def test_explicit_state_ready(self):
        agent = self._make_agent(state=AgentState.READY)
        assert agent.state == AgentState.READY

    def test_explicit_state_busy(self):
        agent = self._make_agent(state=AgentState.BUSY)
        assert agent.state == AgentState.BUSY

    def test_explicit_state_error(self):
        agent = self._make_agent(state=AgentState.ERROR)
        assert agent.state == AgentState.ERROR

    def test_explicit_state_terminated(self):
        agent = self._make_agent(state=AgentState.TERMINATED)
        assert agent.state == AgentState.TERMINATED

    def test_explicit_state_waiting(self):
        agent = self._make_agent(state=AgentState.WAITING)
        assert agent.state == AgentState.WAITING

    def test_with_current_task(self):
        agent = self._make_agent(current_task="task-42")
        assert agent.current_task == "task-42"

    def test_multiple_capabilities(self):
        caps = [
            AgentCapability(name="nlp", description="NLP"),
            AgentCapability(name="vision", description="Vision"),
        ]
        agent = self._make_agent(capabilities=caps)
        assert len(agent.capabilities) == 2

    def test_empty_capabilities(self):
        agent = self._make_agent(capabilities=[])
        assert agent.capabilities == []

    def test_tasks_completed_nonzero(self):
        agent = self._make_agent(tasks_completed=50)
        assert agent.tasks_completed == 50

    def test_tasks_failed_nonzero(self):
        agent = self._make_agent(tasks_failed=3)
        assert agent.tasks_failed == 3

    def test_execution_time_nonzero(self):
        agent = self._make_agent(total_execution_time=1234.56)
        assert agent.total_execution_time == 1234.56

    def test_explicit_created_at(self):
        fixed = datetime(2025, 6, 1, tzinfo=UTC)
        agent = self._make_agent(created_at=fixed)
        assert agent.created_at == fixed

    def test_explicit_last_active(self):
        fixed = datetime(2025, 6, 2, tzinfo=UTC)
        agent = self._make_agent(last_active=fixed)
        assert agent.last_active == fixed


# ---------------------------------------------------------------------------
# ConsensusProposal
# ---------------------------------------------------------------------------


class TestConsensusProposal:
    """Tests for the ConsensusProposal dataclass."""

    def _make_proposal(self, **overrides):
        defaults = {
            "id": "prop-001",
            "proposer_id": "agent-001",
            "action": "deploy_update",
            "context": {"version": "1.2.3"},
        }
        defaults.update(overrides)
        return ConsensusProposal(**defaults)

    def test_minimal_construction(self):
        p = self._make_proposal()
        assert p.id == "prop-001"
        assert p.proposer_id == "agent-001"
        assert p.action == "deploy_update"

    def test_context_stored(self):
        p = self._make_proposal(context={"k": "v", "n": 1})
        assert p.context == {"k": "v", "n": 1}

    def test_default_votes_empty(self):
        p = self._make_proposal()
        assert p.votes == {}

    def test_default_required_type(self):
        p = self._make_proposal()
        assert p.required_type == ConsensusType.MAJORITY

    def test_deadline_is_utc_datetime(self):
        p = self._make_proposal()
        assert isinstance(p.deadline, datetime)
        assert p.deadline.tzinfo is not None

    def test_result_none_by_default(self):
        p = self._make_proposal()
        assert p.result is None

    def test_completed_at_none_by_default(self):
        p = self._make_proposal()
        assert p.completed_at is None

    def test_constitutional_hash_default(self):
        p = self._make_proposal()
        assert p.constitutional_hash == CONSTITUTIONAL_HASH

    def test_explicit_required_type_unanimous(self):
        p = self._make_proposal(required_type=ConsensusType.UNANIMOUS)
        assert p.required_type == ConsensusType.UNANIMOUS

    def test_explicit_required_type_supermajority(self):
        p = self._make_proposal(required_type=ConsensusType.SUPERMAJORITY)
        assert p.required_type == ConsensusType.SUPERMAJORITY

    def test_explicit_required_type_quorum(self):
        p = self._make_proposal(required_type=ConsensusType.QUORUM)
        assert p.required_type == ConsensusType.QUORUM

    def test_with_votes(self):
        p = self._make_proposal(votes={"agent-1": True, "agent-2": False})
        assert p.votes["agent-1"] is True
        assert p.votes["agent-2"] is False

    def test_with_result_true(self):
        p = self._make_proposal(result=True)
        assert p.result is True

    def test_with_result_false(self):
        p = self._make_proposal(result=False)
        assert p.result is False

    def test_with_completed_at(self):
        fixed = datetime(2025, 3, 1, tzinfo=UTC)
        p = self._make_proposal(completed_at=fixed)
        assert p.completed_at == fixed

    def test_votes_are_independent_instances(self):
        p1 = self._make_proposal()
        p2 = self._make_proposal()
        p1.votes["agent-x"] = True
        assert "agent-x" not in p2.votes

    def test_explicit_deadline(self):
        fixed = datetime(2025, 12, 31, tzinfo=UTC)
        p = self._make_proposal(deadline=fixed)
        assert p.deadline == fixed


# ---------------------------------------------------------------------------
# AgentMessage
# ---------------------------------------------------------------------------


class TestAgentMessage:
    """Tests for the AgentMessage dataclass."""

    def _make_message(self, **overrides):
        defaults = {
            "id": "msg-001",
            "sender_id": "agent-A",
            "recipient_id": "agent-B",
            "message_type": "task_update",
            "payload": {"status": "done"},
        }
        defaults.update(overrides)
        return AgentMessage(**defaults)

    def test_minimal_construction(self):
        msg = self._make_message()
        assert msg.id == "msg-001"
        assert msg.sender_id == "agent-A"
        assert msg.recipient_id == "agent-B"
        assert msg.message_type == "task_update"

    def test_payload_stored(self):
        msg = self._make_message(payload={"key": "val", "num": 99})
        assert msg.payload == {"key": "val", "num": 99}

    def test_timestamp_is_utc_datetime(self):
        msg = self._make_message()
        assert isinstance(msg.timestamp, datetime)
        assert msg.timestamp.tzinfo is not None

    def test_acknowledged_false_by_default(self):
        msg = self._make_message()
        assert msg.acknowledged is False

    def test_constitutional_hash_default(self):
        msg = self._make_message()
        assert msg.constitutional_hash == CONSTITUTIONAL_HASH

    def test_broadcast_recipient_none(self):
        msg = self._make_message(recipient_id=None)
        assert msg.recipient_id is None

    def test_acknowledged_true(self):
        msg = self._make_message(acknowledged=True)
        assert msg.acknowledged is True

    def test_explicit_timestamp(self):
        fixed = datetime(2025, 7, 4, tzinfo=UTC)
        msg = self._make_message(timestamp=fixed)
        assert msg.timestamp == fixed

    def test_various_message_types(self):
        for msg_type in ["heartbeat", "error", "task_assignment", "shutdown"]:
            msg = self._make_message(message_type=msg_type)
            assert msg.message_type == msg_type

    def test_empty_payload(self):
        msg = self._make_message(payload={})
        assert msg.payload == {}

    def test_nested_payload(self):
        payload = {"level1": {"level2": {"value": 42}}}
        msg = self._make_message(payload=payload)
        assert msg.payload["level1"]["level2"]["value"] == 42


# ---------------------------------------------------------------------------
# DecompositionPattern
# ---------------------------------------------------------------------------


class TestDecompositionPattern:
    """Tests for the DecompositionPattern dataclass."""

    def _make_pattern(self, **overrides):
        defaults = {
            "pattern_name": "sequential_pipeline",
            "keywords": ["pipeline", "step", "sequence"],
            "avg_completion_time": 45.5,
            "avg_subtasks": 4,
            "success_rate": 0.95,
            "complexity_score": 3.5,
        }
        defaults.update(overrides)
        return DecompositionPattern(**defaults)

    def test_basic_construction(self):
        p = self._make_pattern()
        assert p.pattern_name == "sequential_pipeline"
        assert p.keywords == ["pipeline", "step", "sequence"]

    def test_avg_completion_time(self):
        p = self._make_pattern(avg_completion_time=120.0)
        assert p.avg_completion_time == 120.0

    def test_avg_subtasks(self):
        p = self._make_pattern(avg_subtasks=10)
        assert p.avg_subtasks == 10

    def test_success_rate(self):
        p = self._make_pattern(success_rate=1.0)
        assert p.success_rate == 1.0

    def test_success_rate_zero(self):
        p = self._make_pattern(success_rate=0.0)
        assert p.success_rate == 0.0

    def test_complexity_min(self):
        p = self._make_pattern(complexity_score=1.0)
        assert p.complexity_score == 1.0

    def test_complexity_max(self):
        p = self._make_pattern(complexity_score=10.0)
        assert p.complexity_score == 10.0

    def test_empty_keywords(self):
        p = self._make_pattern(keywords=[])
        assert p.keywords == []

    def test_single_keyword(self):
        p = self._make_pattern(keywords=["deploy"])
        assert p.keywords == ["deploy"]

    def test_equality(self):
        p1 = self._make_pattern()
        p2 = self._make_pattern()
        assert p1 == p2

    def test_inequality(self):
        p1 = self._make_pattern(pattern_name="a")
        p2 = self._make_pattern(pattern_name="b")
        assert p1 != p2


# ---------------------------------------------------------------------------
# MessageEnvelope
# ---------------------------------------------------------------------------


class TestMessageEnvelope:
    """Tests for the MessageEnvelope dataclass, including __post_init__ and is_expired."""

    def _make_inner_message(self):
        return AgentMessage(
            id="msg-env-001",
            sender_id="agent-X",
            recipient_id="agent-Y",
            message_type="ping",
            payload={},
        )

    def _make_envelope(self, **overrides):
        defaults = {
            "message": self._make_inner_message(),
        }
        defaults.update(overrides)
        return MessageEnvelope(**defaults)

    # -- Construction and defaults --

    def test_minimal_construction(self):
        env = self._make_envelope()
        assert env.message is not None

    def test_default_priority(self):
        env = self._make_envelope()
        assert env.priority == 5

    def test_default_ttl(self):
        env = self._make_envelope()
        assert env.ttl_seconds == 300

    def test_default_persistent(self):
        env = self._make_envelope()
        assert env.persistent is False

    def test_created_at_utc(self):
        env = self._make_envelope()
        assert isinstance(env.created_at, datetime)
        assert env.created_at.tzinfo is not None

    def test_delivered_at_none_by_default(self):
        env = self._make_envelope()
        assert env.delivered_at is None

    # -- __post_init__: expires_at calculation --

    def test_expires_at_set_from_ttl(self):
        """When expires_at is None and ttl_seconds > 0, expires_at = created_at + ttl."""
        env = self._make_envelope(ttl_seconds=300)
        assert env.expires_at is not None
        expected = env.created_at + timedelta(seconds=300)
        assert env.expires_at == expected

    def test_expires_at_custom_ttl(self):
        env = self._make_envelope(ttl_seconds=60)
        assert env.expires_at == env.created_at + timedelta(seconds=60)

    def test_expires_at_large_ttl(self):
        env = self._make_envelope(ttl_seconds=86400)
        assert env.expires_at == env.created_at + timedelta(seconds=86400)

    def test_expires_at_zero_ttl_not_set(self):
        """When ttl_seconds == 0, expires_at should remain None."""
        env = self._make_envelope(ttl_seconds=0)
        assert env.expires_at is None

    def test_expires_at_explicit_overrides_post_init(self):
        """When expires_at is explicitly provided, __post_init__ does not overwrite it."""
        fixed_expires = datetime(2099, 1, 1, tzinfo=UTC)
        env = self._make_envelope(expires_at=fixed_expires)
        assert env.expires_at == fixed_expires

    def test_expires_at_explicit_with_custom_ttl_uses_explicit(self):
        """Explicit expires_at wins even if ttl_seconds > 0."""
        fixed = datetime(2099, 6, 1, tzinfo=UTC)
        env = self._make_envelope(ttl_seconds=300, expires_at=fixed)
        assert env.expires_at == fixed

    def test_negative_ttl_not_set(self):
        """Negative ttl_seconds: condition ttl_seconds > 0 is False, expires_at stays None."""
        env = self._make_envelope(ttl_seconds=-1)
        assert env.expires_at is None

    # -- is_expired --

    def test_not_expired_when_expires_at_none(self):
        """No expiry set — never expired."""
        env = self._make_envelope(ttl_seconds=0)
        assert env.is_expired() is False

    def test_not_expired_when_future(self):
        """expires_at in the future — not expired."""
        future = datetime.now(UTC) + timedelta(hours=1)
        env = self._make_envelope(expires_at=future, ttl_seconds=0)
        assert env.is_expired() is False

    def test_expired_when_past(self):
        """expires_at in the past — expired."""
        past = datetime.now(UTC) - timedelta(hours=1)
        env = self._make_envelope(expires_at=past, ttl_seconds=0)
        assert env.is_expired() is True

    def test_expired_just_now(self):
        """expires_at set to 1 second ago — expired."""
        just_past = datetime.now(UTC) - timedelta(seconds=1)
        env = self._make_envelope(expires_at=just_past, ttl_seconds=0)
        assert env.is_expired() is True

    def test_not_expired_just_in_future(self):
        """expires_at set to 1 second from now — not expired."""
        near_future = datetime.now(UTC) + timedelta(seconds=1)
        env = self._make_envelope(expires_at=near_future, ttl_seconds=0)
        assert env.is_expired() is False

    def test_is_expired_uses_utc_now(self):
        """is_expired compares against datetime.now(timezone.utc)."""
        past = datetime(2000, 1, 1, tzinfo=UTC)
        env = self._make_envelope(expires_at=past, ttl_seconds=0)
        assert env.is_expired() is True

    def test_persistent_flag(self):
        env = self._make_envelope(persistent=True)
        assert env.persistent is True

    def test_priority_low(self):
        env = self._make_envelope(priority=1)
        assert env.priority == 1

    def test_priority_high(self):
        env = self._make_envelope(priority=10)
        assert env.priority == 10

    def test_delivered_at_explicit(self):
        fixed = datetime(2025, 1, 1, tzinfo=UTC)
        env = self._make_envelope(delivered_at=fixed)
        assert env.delivered_at == fixed

    def test_message_reference_preserved(self):
        msg = self._make_inner_message()
        env = MessageEnvelope(message=msg)
        assert env.message is msg


# ---------------------------------------------------------------------------
# __all__ export
# ---------------------------------------------------------------------------


class TestModuleExports:
    """Verify all names are exported in __all__."""

    def test_all_exports_present(self):
        import enhanced_agent_bus.swarm_intelligence.models as m

        expected = {
            "AgentCapability",
            "SwarmTask",
            "SwarmAgent",
            "ConsensusProposal",
            "AgentMessage",
            "DecompositionPattern",
            "MessageEnvelope",
        }
        assert set(m.__all__) == expected

    def test_all_classes_importable(self):
        from enhanced_agent_bus.swarm_intelligence.models import (
            AgentCapability,
            AgentMessage,
            ConsensusProposal,
            DecompositionPattern,
            MessageEnvelope,
            SwarmAgent,
            SwarmTask,
        )

        for cls in [
            AgentCapability,
            AgentMessage,
            ConsensusProposal,
            DecompositionPattern,
            MessageEnvelope,
            SwarmAgent,
            SwarmTask,
        ]:
            assert cls is not None
