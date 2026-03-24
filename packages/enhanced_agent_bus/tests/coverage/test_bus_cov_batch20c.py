"""
Coverage tests for:
1. enhanced_agent_bus.specs.fixtures.temporal
2. enhanced_agent_bus.specs.fixtures.verification
3. enhanced_agent_bus.deliberation_layer.voting_service
4. enhanced_agent_bus.deliberation_layer.opa_guard
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# 1. temporal.py
# ---------------------------------------------------------------------------
from enhanced_agent_bus.specs.fixtures.temporal import (
    CausalValidator,
    SpecTimeline,
    TemporalEvent,
    TemporalViolation,
    TemporalViolationType,
)


class TestTemporalEvent:
    def test_happens_before_true(self):
        now = datetime.now(UTC)
        a = TemporalEvent(id="a", timestamp=now)
        b = TemporalEvent(id="b", timestamp=now + timedelta(seconds=1))
        assert a.happens_before(b) is True

    def test_happens_before_false(self):
        now = datetime.now(UTC)
        a = TemporalEvent(id="a", timestamp=now + timedelta(seconds=1))
        b = TemporalEvent(id="b", timestamp=now)
        assert a.happens_before(b) is False

    def test_is_cause_of_via_effects(self):
        a = TemporalEvent(id="a", effects={"b"})
        b = TemporalEvent(id="b")
        assert a.is_cause_of(b) is True

    def test_is_cause_of_via_causes(self):
        a = TemporalEvent(id="a")
        b = TemporalEvent(id="b", causes={"a"})
        assert a.is_cause_of(b) is True

    def test_is_cause_of_false(self):
        a = TemporalEvent(id="a")
        b = TemporalEvent(id="b")
        assert a.is_cause_of(b) is False

    def test_default_metadata(self):
        e = TemporalEvent(id="x")
        assert e.metadata == {}
        assert isinstance(e.timestamp, datetime)


class TestTemporalViolation:
    def test_creation(self):
        v = TemporalViolation(
            violation_type=TemporalViolationType.CAUSALITY,
            event_a="a",
            event_b="b",
            message="test",
        )
        assert v.violation_type == TemporalViolationType.CAUSALITY
        assert v.event_a == "a"
        assert v.event_b == "b"
        assert isinstance(v.timestamp, datetime)


class TestTemporalViolationType:
    def test_enum_values(self):
        assert TemporalViolationType.CAUSALITY.value == "causality"
        assert TemporalViolationType.ORDERING.value == "ordering"
        assert TemporalViolationType.CLOCK_SKEW.value == "clock_skew"
        assert TemporalViolationType.FUTURE_EVENT.value == "future_event"


class TestSpecTimeline:
    def test_record_event(self):
        tl = SpecTimeline()
        ev = tl.record("e1")
        assert ev.id == "e1"
        assert "e1" in tl.events
        assert tl.order == ["e1"]

    def test_record_with_explicit_timestamp(self):
        tl = SpecTimeline()
        ts = datetime(2024, 1, 1, tzinfo=UTC)
        ev = tl.record("e1", timestamp=ts)
        assert ev.timestamp == ts

    def test_record_with_causes(self):
        tl = SpecTimeline()
        tl.record("cause")
        tl.record("effect", causes={"cause"})
        assert "effect" in tl.events["cause"].effects

    def test_record_with_causes_missing_cause(self):
        tl = SpecTimeline()
        tl.record("effect", causes={"nonexistent"})
        assert "effect" in tl.events

    def test_get_event_found(self):
        tl = SpecTimeline()
        tl.record("e1")
        assert tl.get_event("e1") is not None

    def test_get_event_not_found(self):
        tl = SpecTimeline()
        assert tl.get_event("missing") is None

    def test_happened_before_true(self):
        tl = SpecTimeline()
        t1 = datetime(2024, 1, 1, tzinfo=UTC)
        t2 = datetime(2024, 1, 2, tzinfo=UTC)
        tl.record("a", timestamp=t1)
        tl.record("b", timestamp=t2)
        assert tl.happened_before("a", "b") is True

    def test_happened_before_false_missing(self):
        tl = SpecTimeline()
        tl.record("a")
        assert tl.happened_before("a", "missing") is False
        assert tl.happened_before("missing", "a") is False

    def test_happened_before_false_order(self):
        tl = SpecTimeline()
        t1 = datetime(2024, 1, 2, tzinfo=UTC)
        t2 = datetime(2024, 1, 1, tzinfo=UTC)
        tl.record("a", timestamp=t1)
        tl.record("b", timestamp=t2)
        assert tl.happened_before("a", "b") is False

    def test_get_order(self):
        tl = SpecTimeline()
        tl.record("a")
        tl.record("b")
        order = tl.get_order()
        assert order == ["a", "b"]
        # Verify it returns a copy
        order.append("c")
        assert tl.get_order() == ["a", "b"]

    def test_get_sorted_events(self):
        tl = SpecTimeline()
        t1 = datetime(2024, 1, 2, tzinfo=UTC)
        t2 = datetime(2024, 1, 1, tzinfo=UTC)
        tl.record("later", timestamp=t1)
        tl.record("earlier", timestamp=t2)
        sorted_events = tl.get_sorted_events()
        assert sorted_events[0].id == "earlier"
        assert sorted_events[1].id == "later"

    def test_clear(self):
        tl = SpecTimeline()
        tl.record("a")
        tl.violations.append(
            TemporalViolation(
                violation_type=TemporalViolationType.CAUSALITY,
                event_a="x",
                event_b="y",
                message="test",
            )
        )
        tl.clear()
        assert len(tl.events) == 0
        assert len(tl.order) == 0
        assert len(tl.violations) == 0


class TestCausalValidator:
    def test_init_default_timeline(self):
        cv = CausalValidator()
        assert cv.timeline is not None

    def test_init_with_timeline(self):
        tl = SpecTimeline()
        cv = CausalValidator(tl)
        assert cv.timeline is tl

    def test_validate_causality_valid(self):
        tl = SpecTimeline()
        t1 = datetime(2024, 1, 1, tzinfo=UTC)
        t2 = datetime(2024, 1, 2, tzinfo=UTC)
        tl.record("cause", timestamp=t1)
        tl.record("effect", timestamp=t2)
        cv = CausalValidator(tl)
        assert cv.validate_causality("cause", "effect") is True
        assert len(cv.violations) == 0

    def test_validate_causality_invalid(self):
        tl = SpecTimeline()
        t1 = datetime(2024, 1, 2, tzinfo=UTC)
        t2 = datetime(2024, 1, 1, tzinfo=UTC)
        tl.record("cause", timestamp=t1)
        tl.record("effect", timestamp=t2)
        cv = CausalValidator(tl)
        assert cv.validate_causality("cause", "effect") is False
        assert len(cv.violations) == 1
        assert cv.violations[0].violation_type == TemporalViolationType.CAUSALITY
        # Also appended to timeline violations
        assert len(tl.violations) == 1

    def test_validate_causality_missing_event(self):
        tl = SpecTimeline()
        tl.record("a")
        cv = CausalValidator(tl)
        assert cv.validate_causality("a", "missing") is False
        assert cv.validate_causality("missing", "a") is False

    def test_validate_chain_valid(self):
        tl = SpecTimeline()
        for i in range(3):
            tl.record(f"e{i}", timestamp=datetime(2024, 1, i + 1, tzinfo=UTC))
        cv = CausalValidator(tl)
        valid, violations = cv.validate_chain(["e0", "e1", "e2"])
        assert valid is True
        assert violations == []

    def test_validate_chain_invalid(self):
        tl = SpecTimeline()
        tl.record("e0", timestamp=datetime(2024, 1, 3, tzinfo=UTC))
        tl.record("e1", timestamp=datetime(2024, 1, 2, tzinfo=UTC))
        tl.record("e2", timestamp=datetime(2024, 1, 1, tzinfo=UTC))
        cv = CausalValidator(tl)
        valid, violations = cv.validate_chain(["e0", "e1", "e2"])
        assert valid is False
        assert len(violations) == 2

    def test_check_ordering_valid(self):
        tl = SpecTimeline()
        tl.record("a", timestamp=datetime(2024, 1, 1, tzinfo=UTC))
        tl.record("b", timestamp=datetime(2024, 1, 2, tzinfo=UTC))
        tl.record("c", timestamp=datetime(2024, 1, 3, tzinfo=UTC))
        cv = CausalValidator(tl)
        assert cv.check_ordering(["a", "b", "c"]) is True

    def test_check_ordering_invalid(self):
        tl = SpecTimeline()
        tl.record("a", timestamp=datetime(2024, 1, 2, tzinfo=UTC))
        tl.record("b", timestamp=datetime(2024, 1, 1, tzinfo=UTC))
        cv = CausalValidator(tl)
        assert cv.check_ordering(["a", "b"]) is False
        assert len(cv.violations) == 1
        assert cv.violations[0].violation_type == TemporalViolationType.ORDERING

    def test_check_ordering_missing_event(self):
        tl = SpecTimeline()
        tl.record("a")
        cv = CausalValidator(tl)
        assert cv.check_ordering(["a", "missing"]) is False

    def test_detect_future_events_none(self):
        tl = SpecTimeline()
        tl.record("past", timestamp=datetime(2020, 1, 1, tzinfo=UTC))
        cv = CausalValidator(tl)
        result = cv.detect_future_events()
        assert result == []

    def test_detect_future_events_found(self):
        tl = SpecTimeline()
        future = datetime.now(UTC) + timedelta(days=365)
        tl.record("future_event", timestamp=future)
        cv = CausalValidator(tl)
        result = cv.detect_future_events()
        assert len(result) == 1
        assert result[0].id == "future_event"
        assert len(cv.violations) == 1
        assert cv.violations[0].violation_type == TemporalViolationType.FUTURE_EVENT

    def test_get_violations_returns_copy(self):
        cv = CausalValidator()
        violations = cv.get_violations()
        assert violations == []
        violations.append("something")  # type: ignore[arg-type]
        assert cv.get_violations() == []

    def test_is_valid(self):
        cv = CausalValidator()
        assert cv.is_valid() is True

    def test_is_valid_false(self):
        tl = SpecTimeline()
        tl.record("a", timestamp=datetime(2024, 1, 2, tzinfo=UTC))
        tl.record("b", timestamp=datetime(2024, 1, 1, tzinfo=UTC))
        cv = CausalValidator(tl)
        cv.validate_causality("a", "b")
        assert cv.is_valid() is False

    def test_reset(self):
        tl = SpecTimeline()
        tl.record("a", timestamp=datetime(2024, 1, 2, tzinfo=UTC))
        tl.record("b", timestamp=datetime(2024, 1, 1, tzinfo=UTC))
        cv = CausalValidator(tl)
        cv.validate_causality("a", "b")
        cv.reset()
        assert cv.is_valid() is True
        assert len(cv.violations) == 0


# ---------------------------------------------------------------------------
# 2. verification.py
# ---------------------------------------------------------------------------

from enhanced_agent_bus.specs.fixtures.verification import (
    MACIAgent,
    MACIFramework,
    MACIRole,
    RoleViolationError,
    SelfValidationError,
    SpecZ3SolverContext,
    Z3Result,
    Z3VerificationResult,
    execute_action,
)


class TestSelfValidationError:
    def test_creation(self):
        err = SelfValidationError("agent1", "validate")
        assert err.agent == "agent1"
        assert err.action == "validate"
        assert "agent1" in str(err)
        assert "validate" in str(err)
        assert err.http_status_code == 403
        assert err.error_code == "SELF_VALIDATION_ERROR"


class TestRoleViolationError:
    def test_creation(self):
        err = RoleViolationError("agent1", "executive", "validate")
        assert err.agent == "agent1"
        assert err.role == "executive"
        assert err.action == "validate"
        assert err.http_status_code == 403
        assert err.error_code == "ROLE_VIOLATION_ERROR"


class TestMACIRole:
    def test_enum_values(self):
        assert MACIRole.EXECUTIVE.value == "executive"
        assert MACIRole.LEGISLATIVE.value == "legislative"
        assert MACIRole.JUDICIAL.value == "judicial"


class TestMACIAgent:
    def test_propose_executive(self):
        agent = MACIAgent("exec", MACIRole.EXECUTIVE)
        output_id = agent.propose("content")
        assert output_id == "exec:0"
        assert "exec:0" in agent.outputs

    def test_propose_non_executive_raises(self):
        agent = MACIAgent("judge", MACIRole.JUDICIAL)
        with pytest.raises(RoleViolationError):
            agent.propose("content")

    def test_validate_judicial(self):
        agent = MACIAgent("judge", MACIRole.JUDICIAL)
        result = agent.validate("other:0")
        assert result is True

    def test_validate_non_judicial_raises(self):
        agent = MACIAgent("exec", MACIRole.EXECUTIVE)
        with pytest.raises(RoleViolationError):
            agent.validate("other:0")

    def test_validate_self_output_raises(self):
        agent = MACIAgent("judge", MACIRole.JUDICIAL)
        agent.outputs.append("judge:0")
        with pytest.raises(SelfValidationError):
            agent.validate("judge:0")

    def test_validate_judicial_target_raises(self):
        agent = MACIAgent("judge", MACIRole.JUDICIAL)
        target = MACIAgent("other_judge", MACIRole.JUDICIAL)
        with pytest.raises(RoleViolationError):
            agent.validate("other:0", target)

    def test_validate_executive_target(self):
        agent = MACIAgent("judge", MACIRole.JUDICIAL)
        target = MACIAgent("exec", MACIRole.EXECUTIVE)
        result = agent.validate("exec:0", target)
        assert result is True

    def test_extract_rules_legislative(self):
        agent = MACIAgent("leg", MACIRole.LEGISLATIVE)
        rules = agent.extract_rules("content")
        assert len(rules) == 3
        assert rules[0] == "rule_0"

    def test_extract_rules_non_legislative_raises(self):
        agent = MACIAgent("exec", MACIRole.EXECUTIVE)
        with pytest.raises(RoleViolationError):
            agent.extract_rules("content")


class TestMACIFramework:
    def test_default_agents(self):
        fw = MACIFramework()
        assert fw.executive_agent.role == MACIRole.EXECUTIVE
        assert fw.legislative_agent.role == MACIRole.LEGISLATIVE
        assert fw.judicial_agent.role == MACIRole.JUDICIAL

    def test_get_agent(self):
        fw = MACIFramework()
        assert fw.get_agent("executive") is fw.executive_agent
        assert fw.get_agent("legislative") is fw.legislative_agent
        assert fw.get_agent("judicial") is fw.judicial_agent

    def test_get_agent_invalid_raises(self):
        fw = MACIFramework()
        with pytest.raises(KeyError):
            fw.get_agent("invalid")


class TestZ3Result:
    def test_enum_values(self):
        assert Z3Result.SAT.value == "sat"
        assert Z3Result.UNSAT.value == "unsat"
        assert Z3Result.TIMEOUT.value == "timeout"
        assert Z3Result.UNKNOWN.value == "unknown"


class TestZ3VerificationResult:
    def test_to_dict(self):
        r = Z3VerificationResult(
            sat=True,
            result=Z3Result.SAT,
            model={"x": 5},
            time_ms=1.5,
        )
        d = r.to_dict()
        assert d["sat"] is True
        assert d["result"] == "sat"
        assert d["model"] == {"x": 5}
        assert d["time_ms"] == 1.5

    def test_to_dict_unsat_with_core(self):
        r = Z3VerificationResult(
            sat=False,
            result=Z3Result.UNSAT,
            unsat_core=["c1", "c2"],
        )
        d = r.to_dict()
        assert d["sat"] is False
        assert d["unsat_core"] == ["c1", "c2"]


class TestSpecZ3SolverContext:
    def test_verify_true(self):
        ctx = SpecZ3SolverContext()
        result = ctx.verify("true")
        assert result.sat is True
        assert result.result == Z3Result.SAT
        assert len(ctx.verification_log) == 1

    def test_verify_false(self):
        ctx = SpecZ3SolverContext()
        result = ctx.verify("false")
        assert result.sat is False
        assert result.result == Z3Result.UNSAT

    def test_verify_contradiction_increment(self):
        ctx = SpecZ3SolverContext()
        result = ctx.verify("x = x + 1")
        assert result.sat is False
        assert result.result == Z3Result.UNSAT

    def test_verify_range_contradiction(self):
        ctx = SpecZ3SolverContext()
        result = ctx.verify("x > 10 AND x < 5")
        assert result.sat is False
        assert result.unsat_core == ["c1", "c2"]

    def test_verify_satisfiable_range(self):
        ctx = SpecZ3SolverContext()
        result = ctx.verify("x > 0 AND x < 10")
        assert result.sat is True
        assert result.model == {"x": 5}

    def test_verify_default_sat(self):
        ctx = SpecZ3SolverContext()
        result = ctx.verify("some arbitrary constraint")
        assert result.sat is True
        assert result.result == Z3Result.SAT

    def test_reset(self):
        ctx = SpecZ3SolverContext()
        ctx.verify("true")
        ctx.verify("false")
        assert len(ctx.verification_log) == 2
        ctx.reset()
        assert len(ctx.verification_log) == 0

    def test_verify_with_gt_lt_but_not_contradictory(self):
        """Branch: has > and < but not the specific contradiction pattern."""
        ctx = SpecZ3SolverContext()
        result = ctx.verify("x > 1 AND x < 20")
        # Falls through to the "x > 0" check? No, it's "x > 1" not "x > 0"
        # So it falls to default SAT
        assert result.sat is True


class TestExecuteAction:
    def test_propose(self):
        agent = MACIAgent("exec", MACIRole.EXECUTIVE)
        result = execute_action(agent, "propose", None)
        assert isinstance(result, str)

    def test_validate_own(self):
        agent = MACIAgent("judge", MACIRole.JUDICIAL)
        with pytest.raises(SelfValidationError):
            execute_action(agent, "validate", "own")

    def test_validate_executive(self):
        agent = MACIAgent("judge", MACIRole.JUDICIAL)
        result = execute_action(agent, "validate", "executive")
        assert result is True

    def test_validate_judicial(self):
        agent = MACIAgent("judge", MACIRole.JUDICIAL)
        with pytest.raises(RoleViolationError):
            execute_action(agent, "validate", "judicial")

    def test_validate_other(self):
        agent = MACIAgent("judge", MACIRole.JUDICIAL)
        result = execute_action(agent, "validate", "other_target")
        assert result is True

    def test_extract_rules(self):
        agent = MACIAgent("leg", MACIRole.LEGISLATIVE)
        result = execute_action(agent, "extract_rules", None)
        assert isinstance(result, list)

    def test_unknown_action_raises(self):
        agent = MACIAgent("exec", MACIRole.EXECUTIVE)
        with pytest.raises(ValueError, match="Unknown action"):
            execute_action(agent, "unknown_action", None)


# ---------------------------------------------------------------------------
# 3. voting_service.py
# ---------------------------------------------------------------------------

from enhanced_agent_bus.deliberation_layer.voting_service import (
    Election,
    ElectionProxy,
    ElectionsDict,
    Vote,
    VotingService,
    VotingStrategy,
)
from enhanced_agent_bus.models import AgentMessage


class TestVotingStrategy:
    def test_values(self):
        assert VotingStrategy.QUORUM.value == "quorum"
        assert VotingStrategy.UNANIMOUS.value == "unanimous"
        assert VotingStrategy.SUPER_MAJORITY.value == "super-majority"


class TestVote:
    def test_creation(self):
        v = Vote(agent_id="a1", decision="APPROVE", reason="looks good")
        assert v.agent_id == "a1"
        assert v.decision == "APPROVE"
        assert isinstance(v.timestamp, datetime)


class TestElectionProxy:
    def test_getattr_strategy_string(self):
        proxy = ElectionProxy({"strategy": "quorum"})
        assert proxy.strategy == VotingStrategy.QUORUM

    def test_getattr_strategy_enum(self):
        proxy = ElectionProxy({"strategy": VotingStrategy.UNANIMOUS})
        assert proxy.strategy == VotingStrategy.UNANIMOUS

    def test_getattr_participants(self):
        proxy = ElectionProxy({"participants": ["a", "b"]})
        assert proxy.participants == {"a", "b"}

    def test_getattr_votes_dict(self):
        proxy = ElectionProxy(
            {
                "votes": {
                    "a1": {
                        "agent_id": "a1",
                        "decision": "APPROVE",
                        "reason": None,
                        "timestamp": datetime.now(UTC),
                    }
                }
            }
        )
        votes = proxy.votes
        assert "a1" in votes
        assert isinstance(votes["a1"], Vote)

    def test_getattr_votes_non_dict(self):
        proxy = ElectionProxy({"votes": {"a1": "raw_value"}})
        votes = proxy.votes
        assert votes["a1"] == "raw_value"

    def test_getattr_other(self):
        proxy = ElectionProxy({"status": "OPEN"})
        assert proxy.status == "OPEN"

    def test_getattr_missing(self):
        proxy = ElectionProxy({})
        assert proxy.nonexistent is None


class TestElectionsDict:
    def test_getitem_dict(self):
        ed = ElectionsDict()
        ed["e1"] = {"status": "OPEN"}
        result = ed["e1"]
        assert isinstance(result, ElectionProxy)
        assert result.status == "OPEN"

    def test_getitem_non_dict(self):
        ed = ElectionsDict()
        ed["e1"] = "raw"
        result = ed["e1"]
        assert result == "raw"


class TestVotingServiceInMemory:
    """Tests for VotingService with force_in_memory=True to avoid Redis."""

    def _make_service(
        self,
        strategy: VotingStrategy = VotingStrategy.QUORUM,
        kafka_bus: object | None = None,
    ) -> VotingService:
        return VotingService(
            default_strategy=strategy,
            force_in_memory=True,
            kafka_bus=kafka_bus,
        )

    def _make_message(self, message_id: str = "msg-1") -> AgentMessage:
        return AgentMessage(message_id=message_id)

    async def test_create_election(self):
        svc = self._make_service()
        msg = self._make_message()
        eid = await svc.create_election(msg, ["a1", "a2"], timeout=60)
        assert eid is not None
        assert eid in svc._in_memory_elections
        data = svc._in_memory_elections[eid]
        assert data["status"] == "OPEN"
        assert set(data["participants"]) == {"a1", "a2"}

    async def test_create_election_default_timeout(self):
        svc = self._make_service()
        msg = self._make_message()
        eid = await svc.create_election(msg, ["a1"])
        assert eid is not None

    async def test_create_election_with_weights(self):
        svc = self._make_service()
        msg = self._make_message()
        eid = await svc.create_election(
            msg, ["a1", "a2"], timeout=60, participant_weights={"a1": 2.0}
        )
        data = svc._in_memory_elections[eid]
        assert data["participant_weights"]["a1"] == 2.0
        assert data["participant_weights"]["a2"] == 1.0

    async def test_cast_vote_approve(self):
        svc = self._make_service()
        msg = self._make_message()
        eid = await svc.create_election(msg, ["a1", "a2"], timeout=300)
        vote = Vote(agent_id="a1", decision="APPROVE")
        result = await svc.cast_vote(eid, vote)
        assert result is True

    async def test_cast_vote_nonexistent_election(self):
        svc = self._make_service()
        vote = Vote(agent_id="a1", decision="APPROVE")
        result = await svc.cast_vote("nonexistent", vote)
        assert result is False

    async def test_cast_vote_closed_election(self):
        svc = self._make_service()
        msg = self._make_message()
        eid = await svc.create_election(msg, ["a1", "a2"], timeout=300)
        svc._in_memory_elections[eid]["status"] = "CLOSED"
        vote = Vote(agent_id="a1", decision="APPROVE")
        result = await svc.cast_vote(eid, vote)
        assert result is False

    async def test_cast_vote_non_participant(self):
        svc = self._make_service()
        msg = self._make_message()
        eid = await svc.create_election(msg, ["a1", "a2"], timeout=300)
        vote = Vote(agent_id="outsider", decision="APPROVE")
        result = await svc.cast_vote(eid, vote)
        assert result is False

    async def test_quorum_resolution_approve(self):
        svc = self._make_service(strategy=VotingStrategy.QUORUM)
        msg = self._make_message()
        eid = await svc.create_election(msg, ["a1", "a2", "a3"], timeout=300)

        await svc.cast_vote(eid, Vote(agent_id="a1", decision="APPROVE"))
        await svc.cast_vote(eid, Vote(agent_id="a2", decision="APPROVE"))

        result = await svc.get_result(eid)
        assert result == "APPROVE"

    async def test_quorum_resolution_deny(self):
        svc = self._make_service(strategy=VotingStrategy.QUORUM)
        msg = self._make_message()
        eid = await svc.create_election(msg, ["a1", "a2"], timeout=300)

        await svc.cast_vote(eid, Vote(agent_id="a1", decision="DENY"))

        result = await svc.get_result(eid)
        assert result == "DENY"

    async def test_unanimous_resolution_approve(self):
        svc = self._make_service(strategy=VotingStrategy.UNANIMOUS)
        msg = self._make_message()
        eid = await svc.create_election(msg, ["a1", "a2"], timeout=300)

        await svc.cast_vote(eid, Vote(agent_id="a1", decision="APPROVE"))
        await svc.cast_vote(eid, Vote(agent_id="a2", decision="APPROVE"))

        result = await svc.get_result(eid)
        assert result == "APPROVE"

    async def test_unanimous_resolution_deny_on_single(self):
        svc = self._make_service(strategy=VotingStrategy.UNANIMOUS)
        msg = self._make_message()
        eid = await svc.create_election(msg, ["a1", "a2"], timeout=300)

        await svc.cast_vote(eid, Vote(agent_id="a1", decision="DENY"))

        result = await svc.get_result(eid)
        assert result == "DENY"

    async def test_super_majority_resolution_approve(self):
        svc = self._make_service(strategy=VotingStrategy.SUPER_MAJORITY)
        msg = self._make_message()
        eid = await svc.create_election(msg, ["a1", "a2", "a3"], timeout=300)

        await svc.cast_vote(eid, Vote(agent_id="a1", decision="APPROVE"))
        await svc.cast_vote(eid, Vote(agent_id="a2", decision="APPROVE"))

        result = await svc.get_result(eid)
        assert result == "APPROVE"

    async def test_super_majority_resolution_deny(self):
        svc = self._make_service(strategy=VotingStrategy.SUPER_MAJORITY)
        msg = self._make_message()
        eid = await svc.create_election(msg, ["a1", "a2", "a3"], timeout=300)

        await svc.cast_vote(eid, Vote(agent_id="a1", decision="DENY"))
        await svc.cast_vote(eid, Vote(agent_id="a2", decision="DENY"))

        result = await svc.get_result(eid)
        assert result == "DENY"

    async def test_get_result_nonexistent(self):
        svc = self._make_service()
        result = await svc.get_result("nonexistent")
        assert result is None

    async def test_get_result_open_not_expired(self):
        svc = self._make_service()
        msg = self._make_message()
        eid = await svc.create_election(msg, ["a1"], timeout=3600)
        result = await svc.get_result(eid)
        assert result is None

    async def test_get_result_expired(self):
        svc = self._make_service()
        msg = self._make_message()
        eid = await svc.create_election(msg, ["a1"], timeout=1)
        # Manually set expires_at to past
        svc._in_memory_elections[eid]["expires_at"] = datetime(2020, 1, 1, tzinfo=UTC)
        result = await svc.get_result(eid)
        assert result == "DENY"

    async def test_get_result_expired_string_format(self):
        svc = self._make_service()
        msg = self._make_message()
        eid = await svc.create_election(msg, ["a1"], timeout=1)
        svc._in_memory_elections[eid]["expires_at"] = "2020-01-01T00:00:00+00:00"
        result = await svc.get_result(eid)
        assert result == "DENY"

    async def test_elections_property(self):
        svc = self._make_service()
        msg = self._make_message()
        eid = await svc.create_election(msg, ["a1"], timeout=60)
        elections = svc.elections
        assert isinstance(elections, ElectionsDict)
        proxy = elections[eid]
        assert isinstance(proxy, ElectionProxy)

    async def test_prepare_vote_dict(self):
        vote = Vote(agent_id="a1", decision="APPROVE", reason="good")
        d = VotingService._prepare_vote_dict(vote)
        assert d["agent_id"] == "a1"
        assert d["decision"] == "APPROVE"
        assert d["reason"] == "good"

    async def test_get_voting_strategy_fallback(self):
        svc = self._make_service(strategy=VotingStrategy.QUORUM)
        strategy = svc._get_voting_strategy({"strategy": "invalid-strategy"})
        assert strategy == VotingStrategy.QUORUM

    async def test_kafka_publish_on_vote(self):
        kafka = AsyncMock()
        kafka.publish_vote_event = AsyncMock(return_value=True)
        svc = self._make_service(kafka_bus=kafka)
        msg = self._make_message()
        eid = await svc.create_election(msg, ["a1"], timeout=300)
        await svc.cast_vote(eid, Vote(agent_id="a1", decision="APPROVE"))
        kafka.publish_vote_event.assert_called_once()

    async def test_kafka_publish_failure(self):
        kafka = AsyncMock()
        kafka.publish_vote_event = AsyncMock(return_value=False)
        svc = self._make_service(kafka_bus=kafka)
        msg = self._make_message()
        eid = await svc.create_election(msg, ["a1"], timeout=300)
        result = await svc.cast_vote(eid, Vote(agent_id="a1", decision="APPROVE"))
        assert result is True  # Continues despite Kafka failure

    async def test_kafka_publish_exception(self):
        kafka = AsyncMock()
        kafka.publish_vote_event = AsyncMock(side_effect=RuntimeError("kafka down"))
        svc = self._make_service(kafka_bus=kafka)
        msg = self._make_message()
        eid = await svc.create_election(msg, ["a1"], timeout=300)
        result = await svc.cast_vote(eid, Vote(agent_id="a1", decision="APPROVE"))
        assert result is True  # Fail-safe continues

    async def test_check_and_update_expiration_not_open(self):
        svc = self._make_service()
        status = await svc._check_and_update_expiration(
            "e1", {"status": "CLOSED", "expires_at": "2020-01-01T00:00:00+00:00"}
        )
        assert status == "CLOSED"

    async def test_check_and_update_expiration_no_expires(self):
        svc = self._make_service()
        status = await svc._check_and_update_expiration("e1", {"status": "OPEN"})
        assert status == "OPEN"

    async def test_parse_expires_at_string(self):
        dt = VotingService._parse_expires_at("2024-01-01T00:00:00Z")
        assert isinstance(dt, datetime)

    async def test_parse_expires_at_datetime(self):
        now = datetime.now(UTC)
        dt = VotingService._parse_expires_at(now)
        assert dt is now

    async def test_closed_election_no_result_recalculates(self):
        svc = self._make_service()
        msg = self._make_message()
        eid = await svc.create_election(msg, ["a1", "a2"], timeout=300)
        # Manually close without result
        svc._in_memory_elections[eid]["status"] = "CLOSED"
        # Add enough votes for resolution
        svc._in_memory_elections[eid]["votes"] = {
            "a1": {"agent_id": "a1", "decision": "APPROVE", "timestamp": "now"},
            "a2": {"agent_id": "a2", "decision": "APPROVE", "timestamp": "now"},
        }
        result = await svc.get_result(eid)
        # Should recalculate and return APPROVE
        assert result == "APPROVE"

    async def test_evaluate_strategy_unknown(self):
        """Test with an unhandled strategy value by calling static method directly."""
        # Simulate an unrecognized strategy by passing a mocked enum
        mock_strategy = MagicMock()
        mock_strategy.__eq__ = lambda s, o: False  # Never matches
        resolved, decision = VotingService._evaluate_strategy_resolution(
            mock_strategy, (1.0, 0.0, 2.0)
        )
        assert resolved is False
        assert decision == "DENY"

    async def test_unanimous_not_resolved(self):
        """Unanimous with no votes yet - not resolved."""
        resolved, decision = VotingService._check_unanimous_resolution(0.0, 0.0, 3.0)
        assert resolved is False

    async def test_super_majority_not_resolved(self):
        """Super majority with insufficient votes."""
        resolved, decision = VotingService._check_super_majority_resolution(1.0, 0.0, 3.0)
        assert resolved is False

    async def test_quorum_not_resolved(self):
        """Quorum with insufficient votes."""
        resolved, decision = VotingService._check_quorum_resolution(0.0, 0.0, 4.0)
        assert resolved is False


class TestVotingServiceRedisPath:
    """Tests covering Redis store paths with mocked store."""

    async def test_create_election_redis_save_failure_fallback(self):
        mock_store = AsyncMock()
        mock_store.save_election = AsyncMock(return_value=False)
        svc = VotingService(election_store=mock_store, force_in_memory=False)
        svc._store_initialized = True
        msg = AgentMessage(message_id="m1")
        eid = await svc.create_election(msg, ["a1"], timeout=60)
        assert eid in svc._in_memory_elections

    async def test_store_vote_redis_failure_fallback(self):
        mock_store = AsyncMock()
        mock_store.add_vote = AsyncMock(return_value=False)
        mock_store.get_election = AsyncMock(
            return_value={
                "status": "OPEN",
                "participants": ["a1"],
                "participant_weights": {"a1": 1.0},
                "votes": {},
                "strategy": "quorum",
            }
        )
        mock_store.save_election = AsyncMock(return_value=True)
        svc = VotingService(election_store=mock_store, force_in_memory=False)
        svc._store_initialized = True
        # Also put in memory for fallback
        svc._in_memory_elections["e1"] = {
            "status": "OPEN",
            "participants": ["a1"],
            "participant_weights": {"a1": 1.0},
            "votes": {},
            "strategy": "quorum",
        }
        vote = Vote(agent_id="a1", decision="APPROVE")
        result = await svc.cast_vote("e1", vote)
        assert result is True

    async def test_ensure_store_initialized_no_getter(self):
        """When get_election_store is None."""
        with patch(
            "enhanced_agent_bus.deliberation_layer.voting_service.get_election_store", None
        ):
            svc = VotingService(force_in_memory=False)
            svc._store_initialized = False
            result = await svc._ensure_store_initialized()
            assert result is False

    async def test_ensure_store_initialized_getter_raises(self):
        """When get_election_store raises."""
        mock_getter = AsyncMock(side_effect=RuntimeError("no redis"))
        with patch(
            "enhanced_agent_bus.deliberation_layer.voting_service.get_election_store", mock_getter
        ):
            svc = VotingService(force_in_memory=False)
            svc._store_initialized = False
            result = await svc._ensure_store_initialized()
            assert result is False

    async def test_ensure_store_initialized_with_existing_store(self):
        mock_store = AsyncMock()
        svc = VotingService(election_store=mock_store, force_in_memory=False)
        svc._store_initialized = False
        result = await svc._ensure_store_initialized()
        assert result is True
        assert svc._store_initialized is True


# ---------------------------------------------------------------------------
# 4. opa_guard.py
# ---------------------------------------------------------------------------

from enhanced_agent_bus.deliberation_layer.opa_guard import (
    OPAGuard,
    close_opa_guard,
    get_opa_guard,
    initialize_opa_guard,
    reset_opa_guard,
)
from enhanced_agent_bus.deliberation_layer.opa_guard_models import (
    GuardDecision,
    GuardResult,
    ReviewResult,
    ReviewStatus,
    SignatureResult,
    SignatureStatus,
)


class TestOPAGuardInit:
    def test_default_init(self):
        guard = OPAGuard()
        assert guard.fail_closed is True
        assert guard.enable_signatures is True
        assert guard.enable_critic_review is True
        assert guard.high_risk_threshold == 0.8
        assert guard.critical_risk_threshold == 0.95

    def test_custom_init(self):
        guard = OPAGuard(fail_closed=False, high_risk_threshold=0.5)
        assert guard.fail_closed is False
        assert guard.high_risk_threshold == 0.5


class TestOPAGuardInitClose:
    async def test_initialize_with_none_client(self):
        guard = OPAGuard()
        mock_client = AsyncMock()
        with patch(
            "enhanced_agent_bus.deliberation_layer.opa_guard.get_opa_client",
            return_value=mock_client,
        ):
            await guard.initialize()
        assert guard.opa_client is mock_client
        mock_client.initialize.assert_called_once()

    async def test_initialize_with_existing_client(self):
        mock_client = AsyncMock()
        mock_client.fail_closed = True
        guard = OPAGuard(opa_client=mock_client)
        await guard.initialize()
        mock_client.initialize.assert_called_once()

    async def test_close(self):
        mock_client = AsyncMock()
        guard = OPAGuard(opa_client=mock_client)
        guard._pending_signatures["x"] = MagicMock()
        guard._pending_reviews["y"] = MagicMock()
        await guard.close()
        mock_client.close.assert_called_once()
        assert len(guard._pending_signatures) == 0
        assert len(guard._pending_reviews) == 0

    async def test_close_no_client(self):
        guard = OPAGuard()
        await guard.close()  # Should not raise


class TestOPAGuardVerifyAction:
    def _make_guard(self, policy_result: dict | None = None, fail_closed: bool = True) -> OPAGuard:
        mock_client = AsyncMock()
        if policy_result is None:
            policy_result = {"allowed": True}
        mock_client.evaluate_policy = AsyncMock(return_value=policy_result)
        return OPAGuard(opa_client=mock_client, fail_closed=fail_closed)

    async def test_allow_low_risk(self):
        guard = self._make_guard({"allowed": True})
        result = await guard.verify_action("agent1", {"type": "read"}, {})
        assert result.decision == GuardDecision.ALLOW
        assert result.is_allowed is True

    async def test_deny_policy_denied(self):
        guard = self._make_guard({"allowed": False, "reason": "policy says no"})
        result = await guard.verify_action("agent1", {"type": "read"}, {})
        assert result.decision == GuardDecision.DENY
        assert result.is_allowed is False

    async def test_deny_constitutional_failure(self):
        mock_client = AsyncMock()
        mock_client.evaluate_policy = AsyncMock(return_value={"allowed": False})
        guard = OPAGuard(opa_client=mock_client)
        result = await guard.verify_action(
            "agent1",
            {"type": "read", "constitutional_hash": "wrong_hash"},
            {},
        )
        assert result.decision == GuardDecision.DENY
        assert result.constitutional_valid is False

    async def test_deny_no_opa_client(self):
        guard = OPAGuard(opa_client=None)
        # Must also mock check_constitutional_compliance to return True
        with patch.object(guard, "check_constitutional_compliance", return_value=True):
            result = await guard.verify_action("agent1", {"type": "read"}, {})
        assert result.decision == GuardDecision.DENY
        assert "OPA client not initialized" in result.validation_errors

    async def test_high_risk_requires_signatures(self):
        guard = self._make_guard({"allowed": True}, fail_closed=True)
        guard.high_risk_threshold = 0.3
        guard.critical_risk_threshold = 0.95
        result = await guard.verify_action(
            "agent1",
            {"type": "delete", "scope": "global", "impact_score": 0.5},
            {},
        )
        assert result.requires_signatures is True
        assert result.decision in (
            GuardDecision.REQUIRE_SIGNATURES,
            GuardDecision.REQUIRE_REVIEW,
        )

    async def test_critical_risk_requires_review(self):
        guard = self._make_guard({"allowed": True})
        guard.critical_risk_threshold = 0.1  # Very low threshold
        result = await guard.verify_action(
            "agent1",
            {"type": "delete", "scope": "global", "impact_score": 1.0},
            {},
        )
        assert result.requires_review is True
        assert result.decision == GuardDecision.REQUIRE_REVIEW

    async def test_verify_action_exception(self):
        mock_client = AsyncMock()
        mock_client.evaluate_policy = AsyncMock(side_effect=RuntimeError("boom"))
        guard = OPAGuard(opa_client=mock_client)
        result = await guard.verify_action("agent1", {"type": "read"}, {})
        assert result.decision == GuardDecision.DENY

    async def test_fallback_warning(self):
        guard = self._make_guard(
            {"allowed": True, "metadata": {"mode": "fallback"}}
        )
        result = await guard.verify_action("agent1", {"type": "read"}, {})
        assert any("fallback" in w for w in result.validation_warnings)


class TestOPAGuardRiskCalculation:
    def test_high_risk_action_type(self):
        guard = OPAGuard()
        score = guard._calculate_risk_score({"type": "delete"}, {}, {})
        assert score >= 0.3

    def test_impact_score_from_action(self):
        guard = OPAGuard()
        score = guard._calculate_risk_score({"type": "read", "impact_score": 1.0}, {}, {})
        assert score >= 0.4

    def test_impact_score_from_context(self):
        guard = OPAGuard()
        score = guard._calculate_risk_score({"type": "read"}, {"impact_score": 1.0}, {})
        assert score >= 0.4

    def test_scope_global(self):
        guard = OPAGuard()
        score = guard._calculate_risk_score({"type": "read", "scope": "global"}, {}, {})
        assert score >= 0.2

    def test_scope_organization(self):
        guard = OPAGuard()
        score = guard._calculate_risk_score({"type": "read", "scope": "organization"}, {}, {})
        assert score >= 0.1

    def test_scope_from_context(self):
        guard = OPAGuard()
        score = guard._calculate_risk_score({"type": "read"}, {"scope": "system"}, {})
        assert score >= 0.2

    def test_policy_metadata_risk(self):
        guard = OPAGuard()
        score = guard._calculate_risk_score(
            {"type": "read"}, {}, {"metadata": {"risk_score": 5.0}}
        )
        assert score >= 0.5

    def test_max_capped_at_1(self):
        guard = OPAGuard()
        score = guard._calculate_risk_score(
            {"type": "delete", "scope": "global", "impact_score": 2.0},
            {},
            {"metadata": {"risk_score": 10.0}},
        )
        assert score <= 1.0

    def test_determine_risk_level(self):
        guard = OPAGuard()
        assert guard._determine_risk_level(0.95) == "critical"
        assert guard._determine_risk_level(0.75) == "high"
        assert guard._determine_risk_level(0.5) == "medium"
        assert guard._determine_risk_level(0.1) == "low"


class TestOPAGuardRiskFactors:
    def test_destructive_action(self):
        guard = OPAGuard()
        factors = guard._identify_risk_factors({"type": "delete"}, {})
        assert any("Destructive" in f for f in factors)

    def test_affects_users(self):
        guard = OPAGuard()
        factors = guard._identify_risk_factors({"type": "read", "affects_users": True}, {})
        assert any("user data" in f for f in factors)

    def test_irreversible(self):
        guard = OPAGuard()
        factors = guard._identify_risk_factors({"type": "read", "irreversible": True}, {})
        assert any("irreversible" in f for f in factors)

    def test_wide_scope(self):
        guard = OPAGuard()
        factors = guard._identify_risk_factors({"type": "read", "scope": "all"}, {})
        assert any("scope" in f.lower() for f in factors)

    def test_scope_from_context(self):
        guard = OPAGuard()
        factors = guard._identify_risk_factors({"type": "read"}, {"scope": "system"})
        assert any("scope" in f.lower() for f in factors)

    def test_production(self):
        guard = OPAGuard()
        factors = guard._identify_risk_factors({"type": "read"}, {"production": True})
        assert any("Production" in f for f in factors)


class TestOPAGuardSignatures:
    async def test_collect_signatures_timeout(self):
        guard = OPAGuard(signature_timeout=1)
        result = await guard.collect_signatures("d1", ["signer1"], timeout=1)
        assert result.status == SignatureStatus.EXPIRED

    async def test_submit_signature_no_pending(self):
        guard = OPAGuard()
        result = await guard.submit_signature("nonexistent", "signer1")
        assert result is False

    async def test_submit_signature_accepted(self):
        guard = OPAGuard()
        sig_result = SignatureResult(
            decision_id="d1",
            required_signers=["signer1"],
            required_count=1,
            threshold=1.0,
        )
        guard._pending_signatures["d1"] = sig_result

        result = await guard.submit_signature("d1", "signer1", reasoning="ok")
        assert result is True

    async def test_reject_signature_no_pending(self):
        guard = OPAGuard()
        result = await guard.reject_signature("nonexistent", "signer1")
        assert result is False

    async def test_reject_signature_accepted(self):
        guard = OPAGuard()
        sig_result = SignatureResult(
            decision_id="d1",
            required_signers=["signer1"],
            required_count=1,
            threshold=1.0,
        )
        event = asyncio.Event()
        sig_result._completion_event = event  # type: ignore[attr-defined]
        guard._pending_signatures["d1"] = sig_result

        result = await guard.reject_signature("d1", "signer1", reason="no")
        assert result is True
        assert event.is_set()

    async def test_submit_signature_completes_collection(self):
        guard = OPAGuard()
        sig_result = SignatureResult(
            decision_id="d1",
            required_signers=["s1"],
            required_count=1,
            threshold=1.0,
        )
        event = asyncio.Event()
        sig_result._completion_event = event  # type: ignore[attr-defined]
        guard._pending_signatures["d1"] = sig_result

        await guard.submit_signature("d1", "s1")
        assert event.is_set()


class TestOPAGuardReviews:
    async def test_submit_for_review_timeout(self):
        guard = OPAGuard(review_timeout=1)
        result = await guard.submit_for_review(
            {"id": "d1"}, ["critic1"], timeout=1
        )
        assert result.status == ReviewStatus.ESCALATED

    async def test_submit_review_no_pending(self):
        guard = OPAGuard()
        result = await guard.submit_review("nonexistent", "critic1", "approve")
        assert result is False

    async def test_submit_review_accepted(self):
        guard = OPAGuard()
        review_result = ReviewResult(
            decision_id="d1",
            required_critics=["critic1"],
        )
        guard._pending_reviews["d1"] = review_result

        result = await guard.submit_review(
            "d1",
            "critic1",
            "approve",
            reasoning="ok",
            concerns=["none"],
            recommendations=["proceed"],
        )
        assert result is True

    async def test_register_unregister_critic(self):
        guard = OPAGuard()
        guard.register_critic_agent("c1", ["safety"], metadata={"level": "high"})
        assert "c1" in guard._critic_agents
        guard.unregister_critic_agent("c1")
        assert "c1" not in guard._critic_agents

    async def test_unregister_nonexistent(self):
        guard = OPAGuard()
        guard.unregister_critic_agent("nonexistent")  # Should not raise


class TestOPAGuardConstitutionalCompliance:
    async def test_hash_mismatch(self):
        mock_client = AsyncMock()
        guard = OPAGuard(opa_client=mock_client)
        result = await guard.check_constitutional_compliance(
            {"constitutional_hash": "wrong"}
        )
        assert result is False

    async def test_no_opa_client_fail_closed(self):
        guard = OPAGuard(opa_client=None, fail_closed=True)
        result = await guard.check_constitutional_compliance({"type": "test"})
        assert result is False

    async def test_no_opa_client_fail_open(self):
        guard = OPAGuard(opa_client=None, fail_closed=False)
        result = await guard.check_constitutional_compliance({"type": "test"})
        assert result is True

    async def test_opa_allows(self):
        mock_client = AsyncMock()
        mock_client.evaluate_policy = AsyncMock(return_value={"allowed": True})
        guard = OPAGuard(opa_client=mock_client)
        result = await guard.check_constitutional_compliance({"type": "test"})
        assert result is True

    async def test_opa_denies(self):
        mock_client = AsyncMock()
        mock_client.evaluate_policy = AsyncMock(return_value={"allowed": False})
        guard = OPAGuard(opa_client=mock_client)
        result = await guard.check_constitutional_compliance({"type": "test"})
        assert result is False

    async def test_opa_exception_fail_closed(self):
        mock_client = AsyncMock()
        mock_client.evaluate_policy = AsyncMock(side_effect=RuntimeError("opa down"))
        guard = OPAGuard(opa_client=mock_client, fail_closed=True)
        result = await guard.check_constitutional_compliance({"type": "test"})
        assert result is False

    async def test_opa_exception_fail_open(self):
        mock_client = AsyncMock()
        mock_client.evaluate_policy = AsyncMock(side_effect=RuntimeError("opa down"))
        guard = OPAGuard(opa_client=mock_client, fail_closed=False)
        result = await guard.check_constitutional_compliance({"type": "test"})
        assert result is True

    async def test_opa_result_not_dict(self):
        mock_client = AsyncMock()
        mock_client.evaluate_policy = AsyncMock(return_value="not a dict")
        guard = OPAGuard(opa_client=mock_client, fail_closed=True)
        result = await guard.check_constitutional_compliance({"type": "test"})
        assert result is False  # fail_closed default


class TestOPAGuardEvaluate:
    async def test_evaluate_allowed(self):
        mock_client = AsyncMock()
        mock_client.evaluate_policy = AsyncMock(
            return_value={"allowed": True, "reasons": ["ok"], "version": "2.0"}
        )
        guard = OPAGuard(opa_client=mock_client)
        result = await guard.evaluate({"msg": "test"})
        assert result["allow"] is True
        assert result["version"] == "2.0"

    async def test_evaluate_no_client_fail_closed(self):
        guard = OPAGuard(opa_client=None, fail_closed=True)
        result = await guard.evaluate({"msg": "test"})
        assert result["allow"] is False
        assert result["version"] == "error"

    async def test_evaluate_no_client_fail_open(self):
        guard = OPAGuard(opa_client=None, fail_closed=False)
        result = await guard.evaluate({"msg": "test"})
        assert result["allow"] is True

    async def test_evaluate_exception(self):
        mock_client = AsyncMock()
        mock_client.evaluate_policy = AsyncMock(side_effect=RuntimeError("boom"))
        guard = OPAGuard(opa_client=mock_client, fail_closed=True)
        result = await guard.evaluate({"msg": "test"})
        assert result["allow"] is False
        assert result["version"] == "fallback"

    async def test_evaluate_exception_fail_open(self):
        mock_client = AsyncMock()
        mock_client.evaluate_policy = AsyncMock(side_effect=RuntimeError("boom"))
        guard = OPAGuard(opa_client=mock_client, fail_closed=False)
        result = await guard.evaluate({"msg": "test"})
        assert result["allow"] is True

    async def test_evaluate_with_allow_key(self):
        mock_client = AsyncMock()
        mock_client.evaluate_policy = AsyncMock(
            return_value={"allow": True, "reasons": ["passed"]}
        )
        guard = OPAGuard(opa_client=mock_client)
        result = await guard.evaluate({"msg": "test"})
        assert result["allow"] is True

    async def test_evaluate_result_not_dict(self):
        mock_client = AsyncMock()
        mock_client.evaluate_policy = AsyncMock(return_value="string_result")
        guard = OPAGuard(opa_client=mock_client, fail_closed=True)
        result = await guard.evaluate({"msg": "test"})
        assert result["allow"] is False  # fail_closed

    async def test_evaluate_missing_keys(self):
        mock_client = AsyncMock()
        mock_client.evaluate_policy = AsyncMock(return_value={})
        guard = OPAGuard(opa_client=mock_client, fail_closed=True)
        result = await guard.evaluate({"msg": "test"})
        assert result["allow"] is False


class TestOPAGuardStatsAndAudit:
    async def test_get_stats(self):
        guard = OPAGuard()
        stats = guard.get_stats()
        assert stats["total_verifications"] == 0
        assert "pending_signatures" in stats
        assert "constitutional_hash" in stats

    async def test_log_decision(self):
        guard = OPAGuard()
        await guard.log_decision({"action": "test"}, {"result": "ok"})
        assert len(guard._audit_log) == 1

    async def test_log_decision_truncation(self):
        guard = OPAGuard()
        guard._audit_log = [{"i": i} for i in range(10001)]
        await guard.log_decision({"action": "test"}, {"result": "ok"})
        assert len(guard._audit_log) == 10000

    async def test_get_audit_log(self):
        guard = OPAGuard()
        await guard.log_decision(
            {"action": "test", "agent_id": "a1"}, {"result": "ok"}
        )
        await guard.log_decision(
            {"action": "test2", "agent_id": "a2"}, {"result": "ok"}
        )
        logs = guard.get_audit_log(limit=10)
        assert len(logs) == 2

    async def test_get_audit_log_filtered(self):
        guard = OPAGuard()
        await guard.log_decision(
            {"action": "test", "agent_id": "a1"}, {"result": "ok"}
        )
        await guard.log_decision(
            {"action": "test2", "agent_id": "a2"}, {"result": "ok"}
        )
        logs = guard.get_audit_log(agent_id="a1")
        assert len(logs) == 1

    async def test_get_audit_log_pagination(self):
        guard = OPAGuard()
        for i in range(5):
            await guard.log_decision({"action": f"test{i}"}, {"result": "ok"})
        logs = guard.get_audit_log(limit=2, offset=1)
        assert len(logs) == 2


class TestOPAGuardGlobalFunctions:
    async def test_get_opa_guard(self):
        reset_opa_guard()
        guard = get_opa_guard()
        assert isinstance(guard, OPAGuard)
        # Second call returns same instance
        assert get_opa_guard() is guard
        reset_opa_guard()

    async def test_initialize_opa_guard(self):
        reset_opa_guard()
        mock_client = AsyncMock()
        with patch(
            "enhanced_agent_bus.deliberation_layer.opa_guard.get_opa_client",
            return_value=mock_client,
        ):
            guard = await initialize_opa_guard(fail_closed=False)
        assert isinstance(guard, OPAGuard)
        assert guard.fail_closed is False
        reset_opa_guard()

    async def test_close_opa_guard(self):
        reset_opa_guard()
        mock_client = AsyncMock()
        with patch(
            "enhanced_agent_bus.deliberation_layer.opa_guard.get_opa_client",
            return_value=mock_client,
        ):
            await initialize_opa_guard()
        await close_opa_guard()
        # After close, get_opa_guard creates new
        reset_opa_guard()

    async def test_close_opa_guard_none(self):
        reset_opa_guard()
        await close_opa_guard()  # Should not raise

    async def test_reset_opa_guard(self):
        reset_opa_guard()
        get_opa_guard()
        reset_opa_guard()
        # After reset, should create new instance
        guard = get_opa_guard()
        assert isinstance(guard, OPAGuard)
        reset_opa_guard()
