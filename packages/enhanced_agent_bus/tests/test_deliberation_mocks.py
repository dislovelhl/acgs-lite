"""Tests for deliberation_layer/deliberation_mocks.py.

Covers MockComponent, MockItem, MockVote, factory functions,
enums, routing/queue/voting/processing mock methods, and explicit getters.
"""

import pytest

from enhanced_agent_bus.deliberation_layer.deliberation_mocks import (
    MOCK_STORAGE,
    MockComponent,
    MockDeliberationStatus,
    MockItem,
    MockMagicMock,
    MockVote,
    MockVoteType,
    create_mock_adaptive_router,
    create_mock_deliberation_queue,
    create_mock_impact_scorer,
    create_mock_llm_assistant,
    create_mock_opa_guard,
    create_mock_redis_queue,
    create_mock_redis_voting,
    mock_calculate_message_impact,
)

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TestMockDeliberationStatus:
    def test_values(self):
        assert MockDeliberationStatus.PENDING.value == "pending"
        assert MockDeliberationStatus.APPROVED.value == "approved"
        assert MockDeliberationStatus.CONSENSUS_REACHED.value == "consensus_reached"


class TestMockVoteType:
    def test_values(self):
        assert MockVoteType.APPROVE.value == "approve"
        assert MockVoteType.REJECT.value == "reject"
        assert MockVoteType.ABSTAIN.value == "abstain"


# ---------------------------------------------------------------------------
# MockMagicMock
# ---------------------------------------------------------------------------


class TestMockMagicMock:
    def test_callable(self):
        m = MockMagicMock()
        result = m()
        assert isinstance(result, MockMagicMock)

    def test_attribute_access(self):
        m = MockMagicMock()
        assert isinstance(m.any_attr, MockMagicMock)

    def test_chained_calls(self):
        m = MockMagicMock()
        result = m.foo.bar.baz()
        assert isinstance(result, MockMagicMock)


# ---------------------------------------------------------------------------
# MockItem / MockVote
# ---------------------------------------------------------------------------


class TestMockItem:
    def test_defaults(self):
        item = MockItem()
        assert item.current_votes == []
        assert item.status == "pending"
        assert item.item_id is None
        assert item.created_at is not None

    def test_fields_assignable(self):
        item = MockItem()
        item.item_id = "test-1"
        item.task_id = "task-1"
        assert item.item_id == "test-1"


class TestMockVote:
    def test_defaults(self):
        vote = MockVote()
        assert vote.vote is None
        assert vote.agent_id is None


# ---------------------------------------------------------------------------
# MockComponent explicit methods
# ---------------------------------------------------------------------------


class TestMockComponentExplicit:
    def test_get_routing_stats(self):
        c = MockComponent()
        assert c.get_routing_stats() == {}

    def test_get_queue_status(self):
        c = MockComponent()
        status = c.get_queue_status()
        assert "stats" in status
        assert "queue_size" in status

    def test_get_stats(self):
        c = MockComponent()
        assert c.get_stats() == {}

    def test_get_task_missing(self):
        c = MockComponent()
        assert c.get_task("nonexistent") is None

    @pytest.mark.asyncio
    async def test_initialize(self):
        c = MockComponent()
        await c.initialize()  # should not raise

    @pytest.mark.asyncio
    async def test_close(self):
        c = MockComponent()
        await c.close()  # should not raise

    def test_set_impact_threshold(self):
        c = MockComponent()
        c.set_impact_threshold(0.5)  # no-op, should not raise


# ---------------------------------------------------------------------------
# MockComponent dynamic methods
# ---------------------------------------------------------------------------


class TestMockComponentDynamic:
    @pytest.mark.asyncio
    async def test_enqueue_returns_task_id(self):
        c = MockComponent()
        tid = await c.enqueue_for_deliberation("test message")
        assert isinstance(tid, str)
        assert len(tid) > 0

    @pytest.mark.asyncio
    async def test_enqueue_creates_item_in_queue(self):
        c = MockComponent()
        tid = await c.enqueue("msg")
        assert c.get_task(tid) is not None

    @pytest.mark.asyncio
    async def test_route_message_low_impact(self):
        class Msg:
            impact_score = 0.1

        c = MockComponent()
        result = await c.route_message(Msg())
        assert result["lane"] == "fast"

    @pytest.mark.asyncio
    async def test_route_message_high_impact(self):
        class Msg:
            impact_score = 0.8

        c = MockComponent()
        result = await c.route_message(Msg())
        assert result["lane"] == "deliberation"

    @pytest.mark.asyncio
    async def test_route_no_impact(self):
        class Msg:
            pass

        c = MockComponent()
        result = await c.route(Msg())
        assert result["lane"] == "fast"

    @pytest.mark.asyncio
    async def test_submit_agent_vote(self):
        c = MockComponent()
        tid = await c.enqueue_for_deliberation("msg")
        result = await c.submit_agent_vote(tid, "agent-1", "approve")
        assert result is True
        item = c.get_task(tid)
        assert len(item.current_votes) == 1

    @pytest.mark.asyncio
    async def test_submit_agent_vote_missing_task(self):
        c = MockComponent()
        result = await c.submit_agent_vote("bad-id", "agent-1", "approve")
        assert result is False

    @pytest.mark.asyncio
    async def test_submit_human_decision(self):
        c = MockComponent()
        tid = await c.enqueue("msg")
        result = await c.submit_human_decision(tid, "reviewer", "approved")
        assert result is True
        assert c.get_task(tid).status == "approved"

    @pytest.mark.asyncio
    async def test_process_message(self):
        c = MockComponent()
        result = await c.process_message("msg")
        assert result["success"] is True
        assert result["lane"] == "fast"

    @pytest.mark.asyncio
    async def test_force_deliberation(self):
        c = MockComponent()
        result = await c.force_deliberation("msg", "testing")
        assert result["lane"] == "deliberation"
        assert result["forced"] is True

    @pytest.mark.asyncio
    async def test_submit_generic(self):
        c = MockComponent()
        result = await c.submit_something()
        assert result is True

    @pytest.mark.asyncio
    async def test_resolve_generic(self):
        c = MockComponent()
        result = await c.resolve_conflict()
        assert result is True

    @pytest.mark.asyncio
    async def test_unknown_method(self):
        c = MockComponent()
        result = await c.some_random_method()
        assert result == {}


# ---------------------------------------------------------------------------
# Factory functions
# ---------------------------------------------------------------------------


class TestFactoryFunctions:
    def test_create_mock_impact_scorer(self):
        assert isinstance(create_mock_impact_scorer(), MockComponent)

    def test_create_mock_adaptive_router(self):
        assert isinstance(create_mock_adaptive_router(), MockComponent)

    def test_create_mock_deliberation_queue(self):
        assert isinstance(create_mock_deliberation_queue(), MockComponent)

    def test_create_mock_llm_assistant(self):
        assert isinstance(create_mock_llm_assistant(), MockComponent)

    def test_create_mock_redis_queue(self):
        assert isinstance(create_mock_redis_queue(), MockComponent)

    def test_create_mock_redis_voting(self):
        assert isinstance(create_mock_redis_voting(), MockComponent)

    def test_create_mock_opa_guard(self):
        assert isinstance(create_mock_opa_guard(), MockComponent)


class TestMockCalculateImpact:
    def test_returns_zero(self):
        assert mock_calculate_message_impact() == 0.0
        assert mock_calculate_message_impact("anything", key="val") == 0.0


class TestMockStorage:
    def test_has_tasks_and_stats(self):
        assert "tasks" in MOCK_STORAGE
        assert "stats" in MOCK_STORAGE
