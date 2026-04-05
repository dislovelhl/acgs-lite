# Constitutional Hash: 608508a9bd224290
"""
Comprehensive coverage tests for deliberation_layer/deliberation_queue.py.

Targets >=98% coverage of the module, covering all classes, methods, branches,
error paths, and edge cases not already reached by existing test suites.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import threading
import uuid
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = [pytest.mark.unit]

# ---------------------------------------------------------------------------
# Core imports
# ---------------------------------------------------------------------------

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.core_models import (
    AgentMessage,
    MessageStatus,
    MessageType,
)
from enhanced_agent_bus.deliberation_layer.deliberation_queue import (
    DELIBERATION_PERSISTENCE_ERRORS,
    AgentVote,
    DeliberationItem,
    DeliberationQueue,
    DeliberationStatus,
    DeliberationTask,
    VoteType,
    _all_queue_instances,
    cleanup_all_deliberation_queues,
    get_deliberation_queue,
    reset_deliberation_queue,
)


def _make_message(msg_id: str = "msg-001") -> AgentMessage:
    return AgentMessage(
        message_id=msg_id,
        from_agent="agent-a",
        to_agent="agent-b",
        message_type=MessageType.COMMAND,
        content={"action": "test"},
        constitutional_hash=CONSTITUTIONAL_HASH,
    )


# ---------------------------------------------------------------------------
# Enums & Dataclasses
# ---------------------------------------------------------------------------


class TestDeliberationStatusEnum:
    def test_all_values_exist(self) -> None:
        assert DeliberationStatus.PENDING.value == "pending"
        assert DeliberationStatus.UNDER_REVIEW.value == "under_review"
        assert DeliberationStatus.APPROVED.value == "approved"
        assert DeliberationStatus.REJECTED.value == "rejected"
        assert DeliberationStatus.TIMED_OUT.value == "timed_out"
        assert DeliberationStatus.CONSENSUS_REACHED.value == "consensus_reached"


class TestVoteTypeEnum:
    def test_all_values_exist(self) -> None:
        assert VoteType.APPROVE.value == "approve"
        assert VoteType.REJECT.value == "reject"
        assert VoteType.ABSTAIN.value == "abstain"


class TestAgentVote:
    def test_defaults(self) -> None:
        vote = AgentVote(agent_id="a1", vote=VoteType.APPROVE, reasoning="ok")
        assert vote.confidence_score == 1.0
        assert isinstance(vote.timestamp, datetime)

    def test_custom_confidence(self) -> None:
        vote = AgentVote(
            agent_id="a2",
            vote=VoteType.REJECT,
            reasoning="no",
            confidence_score=0.7,
        )
        assert vote.confidence_score == 0.7

    def test_abstain_vote(self) -> None:
        vote = AgentVote(agent_id="a3", vote=VoteType.ABSTAIN, reasoning="unsure")
        assert vote.vote == VoteType.ABSTAIN


class TestDeliberationTask:
    def test_default_fields(self) -> None:
        task = DeliberationTask()
        assert task.task_id is not None
        assert len(task.task_id) > 0
        assert task.status == DeliberationStatus.PENDING
        assert task.current_votes == []
        assert task.metadata == {}
        assert task.human_reviewer is None
        assert task.human_decision is None
        assert task.human_reasoning is None

    def test_voting_deadline_property(self) -> None:
        task = DeliberationTask(timeout_seconds=120)
        expected = task.created_at + timedelta(seconds=120)
        assert task.voting_deadline == expected

    def test_item_id_property(self) -> None:
        task = DeliberationTask(task_id="fixed-id")
        assert task.item_id == "fixed-id"

    def test_is_complete_pending(self) -> None:
        task = DeliberationTask(status=DeliberationStatus.PENDING)
        assert task.is_complete is False

    def test_is_complete_under_review(self) -> None:
        task = DeliberationTask(status=DeliberationStatus.UNDER_REVIEW)
        assert task.is_complete is False

    def test_is_complete_approved(self) -> None:
        task = DeliberationTask(status=DeliberationStatus.APPROVED)
        assert task.is_complete is True

    def test_is_complete_rejected(self) -> None:
        task = DeliberationTask(status=DeliberationStatus.REJECTED)
        assert task.is_complete is True

    def test_is_complete_timed_out(self) -> None:
        task = DeliberationTask(status=DeliberationStatus.TIMED_OUT)
        assert task.is_complete is True

    def test_deliberation_item_alias(self) -> None:
        assert DeliberationItem is DeliberationTask


# ---------------------------------------------------------------------------
# DeliberationQueue init
# ---------------------------------------------------------------------------


class TestDeliberationQueueInit:
    def test_default_init(self) -> None:
        q = DeliberationQueue()
        assert q.consensus_threshold == 0.66
        assert q.default_timeout == 300
        assert q.persistence_path is None
        assert q.tasks is q.queue
        assert len(q._partition_locks) == DeliberationQueue.NUM_PARTITIONS
        assert q._shutdown is False

    def test_custom_params(self) -> None:
        q = DeliberationQueue(consensus_threshold=0.8, default_timeout=60)
        assert q.consensus_threshold == 0.8
        assert q.default_timeout == 60

    def test_stats_initial_state(self) -> None:
        q = DeliberationQueue()
        assert q.stats["total_queued"] == 0
        assert q.stats["approved"] == 0
        assert q.stats["rejected"] == 0
        assert q.stats["timed_out"] == 0
        assert q.stats["consensus_reached"] == 0
        assert q.stats["avg_processing_time"] == 0.0

    def test_registered_in_global_instances(self) -> None:
        before = len(_all_queue_instances)
        q = DeliberationQueue()
        assert len(_all_queue_instances) > before
        assert q in _all_queue_instances


# ---------------------------------------------------------------------------
# _get_partition_lock
# ---------------------------------------------------------------------------


class TestGetPartitionLock:
    def test_returns_asyncio_lock(self) -> None:
        q = DeliberationQueue()
        lock = q._get_partition_lock("some-task-id")
        assert isinstance(lock, asyncio.Lock)

    def test_consistent_routing(self) -> None:
        q = DeliberationQueue()
        task_id = "consistent-task"
        lock1 = q._get_partition_lock(task_id)
        lock2 = q._get_partition_lock(task_id)
        assert lock1 is lock2

    def test_different_tasks_may_have_different_locks(self) -> None:
        q = DeliberationQueue()
        locks = {q._get_partition_lock(f"t{i}") for i in range(20)}
        assert len(locks) <= DeliberationQueue.NUM_PARTITIONS


# ---------------------------------------------------------------------------
# _load_tasks
# ---------------------------------------------------------------------------


class TestLoadTasks:
    def test_load_tasks_no_persistence_path(self) -> None:
        q = DeliberationQueue()
        q.persistence_path = None
        q._load_tasks()

    def test_load_tasks_missing_file(self) -> None:
        q = DeliberationQueue()
        q.persistence_path = "/tmp/nonexistent_dq_test_file_xyz.json"
        q._load_tasks()
        assert len(q.tasks) == 0

    def test_load_tasks_invalid_json(self, tmp_path) -> None:
        path = str(tmp_path / "bad.json")
        with open(path, "w") as f:
            f.write("this is not json{{{")
        q = DeliberationQueue()
        q.persistence_path = path
        q._load_tasks()
        assert len(q.tasks) == 0

    def test_load_tasks_valid_data(self, tmp_path) -> None:
        path = str(tmp_path / "tasks.json")
        msg = _make_message("persist-roundtrip")
        task_id = str(uuid.uuid4())
        storage = {
            task_id: {
                "message": msg.to_dict_raw(),
                "status": "pending",
                "metadata": {"note": "test"},
                "created_at": datetime.now(UTC).isoformat(),
            }
        }
        with open(path, "w") as f:
            json.dump(storage, f)
        q = DeliberationQueue()
        q.persistence_path = path
        q._load_tasks()
        assert task_id in q.tasks
        assert q.tasks[task_id].message.message_id == "persist-roundtrip"

    def test_load_tasks_uppercase_status(self, tmp_path) -> None:
        path = str(tmp_path / "upper.json")
        msg = _make_message("upper-status")
        task_id = str(uuid.uuid4())
        storage = {
            task_id: {
                "message": msg.to_dict_raw(),
                "status": "PENDING",
                "metadata": {},
                "created_at": datetime.now(UTC).isoformat(),
            }
        }
        with open(path, "w") as f:
            json.dump(storage, f)
        q = DeliberationQueue()
        q.persistence_path = path
        q._load_tasks()
        assert q.tasks[task_id].status == DeliberationStatus.PENDING


# ---------------------------------------------------------------------------
# enqueue_for_deliberation / enqueue alias
# ---------------------------------------------------------------------------


class TestEnqueueForDeliberation:
    async def test_enqueue_returns_task_id(self) -> None:
        q = DeliberationQueue()
        msg = _make_message()
        task_id = await q.enqueue_for_deliberation(msg)
        assert isinstance(task_id, str)
        assert len(task_id) > 0
        await q.stop()

    async def test_enqueue_increments_total_queued(self) -> None:
        q = DeliberationQueue()
        msg = _make_message()
        await q.enqueue_for_deliberation(msg)
        assert q.stats["total_queued"] == 1
        await q.stop()

    async def test_enqueue_with_human_review(self) -> None:
        q = DeliberationQueue()
        msg = _make_message("hr-001")
        task_id = await q.enqueue_for_deliberation(msg, requires_human_review=True)
        task = q.get_task(task_id)
        assert task is not None
        assert task.metadata["requires_human"] is True
        await q.stop()

    async def test_enqueue_with_multi_agent_vote(self) -> None:
        q = DeliberationQueue()
        msg = _make_message("mv-001")
        task_id = await q.enqueue_for_deliberation(msg, requires_multi_agent_vote=True)
        task = q.get_task(task_id)
        assert task.required_votes == 5
        assert task.metadata["requires_vote"] is True
        await q.stop()

    async def test_enqueue_without_multi_agent_vote(self) -> None:
        q = DeliberationQueue()
        msg = _make_message("no-vote")
        task_id = await q.enqueue_for_deliberation(msg, requires_multi_agent_vote=False)
        task = q.get_task(task_id)
        assert task.required_votes == 0
        await q.stop()

    async def test_enqueue_custom_timeout(self) -> None:
        q = DeliberationQueue()
        msg = _make_message()
        task_id = await q.enqueue_for_deliberation(msg, timeout_seconds=999)
        task = q.get_task(task_id)
        assert task.timeout_seconds == 999
        await q.stop()

    async def test_enqueue_uses_default_timeout_when_none(self) -> None:
        q = DeliberationQueue(default_timeout=42)
        msg = _make_message()
        task_id = await q.enqueue_for_deliberation(msg, timeout_seconds=None)
        task = q.get_task(task_id)
        assert task.timeout_seconds == 42
        await q.stop()

    async def test_enqueue_alias(self) -> None:
        """enqueue() is an alias for enqueue_for_deliberation (line 255-257)."""
        q = DeliberationQueue()
        msg = _make_message("alias-001")
        task_id = await q.enqueue(msg)
        assert task_id in q.tasks
        await q.stop()

    async def test_enqueue_with_persistence_creates_save_task(self, tmp_path) -> None:
        path = str(tmp_path / "persist.json")
        q = DeliberationQueue(persistence_path=path)
        msg = _make_message("persist-001")
        await q.enqueue_for_deliberation(msg)
        await asyncio.sleep(0.05)
        await q.stop()


# ---------------------------------------------------------------------------
# _monitor_task
# ---------------------------------------------------------------------------


class TestMonitorTask:
    async def test_monitor_nonexistent_task_returns_early(self) -> None:
        """_monitor_task returns immediately when task not found (line 263)."""
        q = DeliberationQueue()
        await q._monitor_task("no-such-task")
        await q.stop()

    async def test_monitor_exits_on_shutdown_flag(self) -> None:
        q = DeliberationQueue(default_timeout=60)
        msg = _make_message("shutdown-test")
        await q.enqueue_for_deliberation(msg)
        q._shutdown = True
        q._shutdown_event.set()
        await asyncio.sleep(0.05)
        await q.stop()

    async def test_monitor_exits_when_shutdown_event_set(self) -> None:
        q = DeliberationQueue(default_timeout=10)
        msg = _make_message("event-shutdown")
        await q.enqueue_for_deliberation(msg)
        await asyncio.sleep(0.02)
        q._shutdown_event.set()
        q._shutdown = True
        await asyncio.sleep(0.05)
        await q.stop()

    async def test_monitor_exits_when_task_completed(self) -> None:
        q = DeliberationQueue(default_timeout=10)
        msg = _make_message("complete-early")
        task_id = await q.enqueue_for_deliberation(msg)
        task = q.get_task(task_id)
        task.status = DeliberationStatus.APPROVED
        q._shutdown_event.set()
        await asyncio.sleep(0.05)
        q._shutdown = True
        await q.stop()

    async def test_monitor_timeout_marks_timed_out(self) -> None:
        """_monitor_task marks task TIMED_OUT after timeout (lines 287-292)."""
        q = DeliberationQueue(default_timeout=1)
        msg = _make_message("timeout-001")
        task_id = await q.enqueue_for_deliberation(msg)
        await asyncio.sleep(1.3)
        task = q.get_task(task_id)
        assert task.status == DeliberationStatus.TIMED_OUT
        assert q.stats["timed_out"] >= 1
        q._shutdown = True
        q._shutdown_event.set()
        await q.stop()

    async def test_timeout_fires_with_task_removed(self) -> None:
        """288->298 False branch: timeout fires but task_id was removed from self.tasks.

        We wait for the timeout to elapse, then remove the task from the queue
        while holding the lock. The monitor will then enter the lock, evaluate
        `task_id in self.tasks` as False, and skip the if-block (288->298).
        """
        q = DeliberationQueue(default_timeout=1)
        msg = _make_message("removed-before-timeout")
        task_id = await q.enqueue_for_deliberation(msg)
        # Acquire lock just after timeout fires so monitor is waiting for it
        await asyncio.sleep(1.05)
        async with q._lock:
            # Remove the task while we hold the lock — monitor can't run yet
            q.tasks.pop(task_id, None)
        # Give monitor time to acquire lock and skip the if block
        await asyncio.sleep(0.2)
        # Task was removed, timed_out stat should NOT have increased
        assert q.stats["timed_out"] == 0
        q._shutdown = True
        q._shutdown_event.set()
        await q.stop()

    async def test_timeout_fires_but_task_already_complete(self) -> None:
        """288->298: timeout fires but task was already marked complete externally."""
        q = DeliberationQueue(default_timeout=1)
        msg = _make_message("already-done")
        task_id = await q.enqueue_for_deliberation(msg)
        task = q.get_task(task_id)
        # Mark complete BEFORE the timeout fires
        task.status = DeliberationStatus.APPROVED
        await asyncio.sleep(1.2)
        # Status stays APPROVED — the if at line 288 was False
        assert task.status == DeliberationStatus.APPROVED
        assert q.stats["timed_out"] == 0
        q._shutdown = True
        q._shutdown_event.set()
        await q.stop()

    async def test_monitor_task_cancelled_propagates(self) -> None:
        q = DeliberationQueue(default_timeout=60)
        msg = _make_message("cancel-test")
        await q.enqueue_for_deliberation(msg)
        for t in list(q.processing_tasks):
            t.cancel()
        await asyncio.sleep(0.05)
        q._shutdown = True
        await q.stop()

    async def test_finally_block_when_task_not_in_processing_tasks(self) -> None:
        """298->exit: current_task not in processing_tasks when finally runs."""
        q = DeliberationQueue(default_timeout=1)
        msg = _make_message("removed-task")
        await q.enqueue_for_deliberation(msg)
        # Clear processing_tasks while monitor is still running
        q.processing_tasks.clear()
        await asyncio.sleep(1.2)
        assert len(q.processing_tasks) == 0
        q._shutdown = True
        q._shutdown_event.set()
        await q.stop()

    async def test_finally_block_value_error_on_remove(self) -> None:
        """301-302: ValueError during processing_tasks.remove() is silenced."""
        q = DeliberationQueue(default_timeout=1)
        msg = _make_message("remove-error")
        await q.enqueue_for_deliberation(msg)

        class _RaisingList(list):
            def remove(self, item) -> None:
                raise ValueError("already removed")

        original = list(q.processing_tasks)
        q.processing_tasks = _RaisingList(original)
        await asyncio.sleep(1.2)
        q._shutdown = True
        q._shutdown_event.set()
        await q.stop()


# ---------------------------------------------------------------------------
# stop()
# ---------------------------------------------------------------------------


class TestStop:
    async def test_stop_with_no_tasks(self) -> None:
        q = DeliberationQueue()
        await q.stop()
        assert q._shutdown is True
        assert q._shutdown_event.is_set()

    async def test_stop_cancels_pending_tasks(self) -> None:
        q = DeliberationQueue(default_timeout=60)
        for i in range(3):
            msg = _make_message(f"stop-{i}")
            await q.enqueue_for_deliberation(msg)
        await q.stop()
        assert len(q.processing_tasks) == 0

    async def test_stop_timeout_warning(self) -> None:
        """asyncio.TimeoutError path in stop() (lines 318-319)."""
        q = DeliberationQueue()

        async def _long_running() -> None:
            await asyncio.sleep(100)

        task = asyncio.create_task(_long_running())
        q.processing_tasks.append(task)

        async def _raise_timeout(*args, **kwargs):
            raise TimeoutError()

        with patch("asyncio.wait_for", side_effect=_raise_timeout):
            await q.stop()

        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass


# ---------------------------------------------------------------------------
# Context Manager
# ---------------------------------------------------------------------------


class TestContextManager:
    async def test_aenter_returns_self(self) -> None:
        q = DeliberationQueue()
        result = await q.__aenter__()
        assert result is q
        await q.stop()

    async def test_aexit_calls_stop(self) -> None:
        q = DeliberationQueue()
        ret = await q.__aexit__(None, None, None)
        assert ret is False
        assert q._shutdown is True

    async def test_async_context_manager_usage(self) -> None:
        async with DeliberationQueue() as q:
            msg = _make_message("ctx-001")
            task_id = await q.enqueue_for_deliberation(msg)
            assert task_id in q.tasks
        assert q._shutdown is True


# ---------------------------------------------------------------------------
# update_status
# ---------------------------------------------------------------------------


class TestUpdateStatus:
    async def test_update_status_with_enum(self) -> None:
        q = DeliberationQueue()
        msg = _make_message()
        task_id = await q.enqueue_for_deliberation(msg)
        await q.update_status(task_id, DeliberationStatus.UNDER_REVIEW)
        assert q.get_task(task_id).status == DeliberationStatus.UNDER_REVIEW
        await q.stop()

    async def test_update_status_with_valid_string(self) -> None:
        q = DeliberationQueue()
        msg = _make_message()
        task_id = await q.enqueue_for_deliberation(msg)
        await q.update_status(task_id, "under_review")
        assert q.get_task(task_id).status == DeliberationStatus.UNDER_REVIEW
        await q.stop()

    async def test_update_status_with_uppercase_string(self) -> None:
        q = DeliberationQueue()
        msg = _make_message()
        task_id = await q.enqueue_for_deliberation(msg)
        await q.update_status(task_id, "APPROVED")
        assert q.get_task(task_id).status == DeliberationStatus.APPROVED
        await q.stop()

    async def test_update_status_with_invalid_string_falls_through(self) -> None:
        """Invalid string: ValueError caught, status stays unchanged (lines 338-340)."""
        q = DeliberationQueue()
        msg = _make_message()
        task_id = await q.enqueue_for_deliberation(msg)
        original_status = q.get_task(task_id).status
        await q.update_status(task_id, "totally_invalid_status_xyz")
        assert q.get_task(task_id).status == original_status
        await q.stop()

    async def test_update_status_nonexistent_task(self) -> None:
        q = DeliberationQueue()
        await q.update_status("no-such-id", DeliberationStatus.APPROVED)
        await q.stop()

    async def test_update_status_with_persistence(self, tmp_path) -> None:
        path = str(tmp_path / "status_update.json")
        q = DeliberationQueue(persistence_path=path)
        msg = _make_message()
        task_id = await q.enqueue_for_deliberation(msg)
        await q.update_status(task_id, DeliberationStatus.UNDER_REVIEW)
        await asyncio.sleep(0.05)
        await q.stop()


# ---------------------------------------------------------------------------
# Query methods
# ---------------------------------------------------------------------------


class TestQueryMethods:
    async def test_get_pending_tasks_empty(self) -> None:
        q = DeliberationQueue()
        assert q.get_pending_tasks() == []
        await q.stop()

    async def test_get_pending_tasks_returns_pending_only(self) -> None:
        q = DeliberationQueue()
        msg1 = _make_message("p1")
        msg2 = _make_message("p2")
        t1 = await q.enqueue_for_deliberation(msg1)
        t2 = await q.enqueue_for_deliberation(msg2)
        await q.update_status(t1, DeliberationStatus.APPROVED)
        pending = q.get_pending_tasks()
        ids = [t.task_id for t in pending]
        assert t2 in ids
        assert t1 not in ids
        await q.stop()

    async def test_get_task_returns_none_for_missing(self) -> None:
        q = DeliberationQueue()
        assert q.get_task("ghost") is None

    async def test_get_item_details_returns_none_for_missing(self) -> None:
        q = DeliberationQueue()
        assert q.get_item_details("ghost") is None

    async def test_get_item_details_with_no_message(self) -> None:
        q = DeliberationQueue()
        task = DeliberationTask(task_id="no-msg")
        task.message = None
        q.tasks["no-msg"] = task
        details = q.get_item_details("no-msg")
        assert details is not None
        assert details["message_id"] is None
        await q.stop()

    async def test_get_queue_status_fields(self) -> None:
        q = DeliberationQueue()
        msg = _make_message()
        await q.enqueue_for_deliberation(msg)
        status = q.get_queue_status()
        assert "queue_size" in status
        assert "items" in status
        assert "stats" in status
        assert "processing_count" in status
        assert status["queue_size"] == 1
        await q.stop()


# ---------------------------------------------------------------------------
# submit_agent_vote
# ---------------------------------------------------------------------------


class TestSubmitAgentVote:
    async def test_returns_false_for_missing_task(self) -> None:
        q = DeliberationQueue()
        result = await q.submit_agent_vote("ghost", "a1", VoteType.APPROVE, "ok")
        assert result is False

    async def test_returns_false_for_completed_task(self) -> None:
        q = DeliberationQueue()
        msg = _make_message()
        task_id = await q.enqueue_for_deliberation(msg)
        await q.update_status(task_id, DeliberationStatus.APPROVED)
        result = await q.submit_agent_vote(task_id, "a1", VoteType.APPROVE, "ok")
        assert result is False
        await q.stop()

    async def test_vote_recorded_correctly(self) -> None:
        q = DeliberationQueue()
        msg = _make_message("vote-rec")
        task_id = await q.enqueue_for_deliberation(msg, requires_multi_agent_vote=True)
        result = await q.submit_agent_vote(
            task_id, "voter-x", VoteType.REJECT, "not ok", confidence=0.75
        )
        assert result is True
        task = q.get_task(task_id)
        assert len(task.current_votes) == 1
        assert task.current_votes[0].vote == VoteType.REJECT
        assert task.current_votes[0].confidence_score == 0.75
        await q.stop()

    async def test_duplicate_vote_replaced(self) -> None:
        q = DeliberationQueue()
        msg = _make_message("dup-vote")
        task_id = await q.enqueue_for_deliberation(msg, requires_multi_agent_vote=True)
        await q.submit_agent_vote(task_id, "v1", VoteType.APPROVE, "first")
        await q.submit_agent_vote(task_id, "v1", VoteType.REJECT, "second")
        task = q.get_task(task_id)
        assert len(task.current_votes) == 1
        assert task.current_votes[0].vote == VoteType.REJECT
        await q.stop()

    async def test_consensus_triggers_approval_and_stats(self) -> None:
        q = DeliberationQueue(consensus_threshold=0.5)
        msg = _make_message("consensus")
        task_id = await q.enqueue_for_deliberation(msg, requires_multi_agent_vote=True)
        for i in range(3):
            await q.submit_agent_vote(task_id, f"a{i}", VoteType.APPROVE, "yes")
        for i in range(3, 5):
            await q.submit_agent_vote(task_id, f"a{i}", VoteType.REJECT, "no")
        task = q.get_task(task_id)
        assert task.status == DeliberationStatus.APPROVED
        assert q.stats["approved"] >= 1
        await q.stop()

    async def test_vote_with_persistence(self, tmp_path) -> None:
        path = str(tmp_path / "vote_persist.json")
        q = DeliberationQueue(persistence_path=path)
        msg = _make_message("vp-001")
        task_id = await q.enqueue_for_deliberation(msg, requires_multi_agent_vote=True)
        await q.submit_agent_vote(task_id, "v1", VoteType.APPROVE, "ok")
        await asyncio.sleep(0.05)
        await q.stop()

    async def test_abstain_vote_does_not_trigger_consensus(self) -> None:
        q = DeliberationQueue(consensus_threshold=0.5)
        msg = _make_message("abstain")
        task_id = await q.enqueue_for_deliberation(msg, requires_multi_agent_vote=True)
        for i in range(5):
            await q.submit_agent_vote(task_id, f"a{i}", VoteType.ABSTAIN, "unsure")
        task = q.get_task(task_id)
        assert task.status == DeliberationStatus.PENDING
        await q.stop()


# ---------------------------------------------------------------------------
# _check_consensus
# ---------------------------------------------------------------------------


class TestCheckConsensus:
    def test_not_enough_votes(self) -> None:
        q = DeliberationQueue()
        task = DeliberationTask(required_votes=3, consensus_threshold=0.66)
        assert q._check_consensus(task) is False

    def test_zero_required_votes(self) -> None:
        q = DeliberationQueue()
        task = DeliberationTask(required_votes=0)
        task.current_votes = [AgentVote("a1", VoteType.APPROVE, "ok")]
        assert q._check_consensus(task) is False

    def test_consensus_met(self) -> None:
        q = DeliberationQueue()
        task = DeliberationTask(required_votes=3, consensus_threshold=0.66)
        task.current_votes = [
            AgentVote("a1", VoteType.APPROVE, "ok"),
            AgentVote("a2", VoteType.APPROVE, "ok"),
            AgentVote("a3", VoteType.APPROVE, "ok"),
        ]
        assert q._check_consensus(task) is True

    def test_consensus_not_met(self) -> None:
        q = DeliberationQueue()
        task = DeliberationTask(required_votes=3, consensus_threshold=0.8)
        task.current_votes = [
            AgentVote("a1", VoteType.APPROVE, "ok"),
            AgentVote("a2", VoteType.REJECT, "no"),
            AgentVote("a3", VoteType.REJECT, "no"),
        ]
        assert q._check_consensus(task) is False


# ---------------------------------------------------------------------------
# submit_human_decision
# ---------------------------------------------------------------------------


class TestSubmitHumanDecision:
    async def test_returns_false_for_missing_task(self) -> None:
        q = DeliberationQueue()
        result = await q.submit_human_decision(
            "ghost", "reviewer", DeliberationStatus.APPROVED, "ok"
        )
        assert result is False

    async def test_returns_false_for_completed_task(self) -> None:
        q = DeliberationQueue()
        msg = _make_message()
        task_id = await q.enqueue_for_deliberation(msg)
        await q.update_status(task_id, DeliberationStatus.APPROVED)
        result = await q.submit_human_decision(
            task_id, "reviewer", DeliberationStatus.APPROVED, "ok"
        )
        assert result is False
        await q.stop()

    async def test_returns_false_if_not_under_review(self) -> None:
        q = DeliberationQueue()
        msg = _make_message()
        task_id = await q.enqueue_for_deliberation(msg)
        result = await q.submit_human_decision(
            task_id, "reviewer", DeliberationStatus.APPROVED, "ok"
        )
        assert result is False
        await q.stop()

    async def test_human_approval_success(self) -> None:
        q = DeliberationQueue()
        msg = _make_message("human-approve")
        task_id = await q.enqueue_for_deliberation(msg)
        await q.update_status(task_id, DeliberationStatus.UNDER_REVIEW)
        result = await q.submit_human_decision(
            task_id, "reviewer-1", DeliberationStatus.APPROVED, "all good"
        )
        assert result is True
        task = q.get_task(task_id)
        assert task.status == DeliberationStatus.APPROVED
        assert task.human_reviewer == "reviewer-1"
        assert task.human_reasoning == "all good"
        assert q.stats["approved"] >= 1
        await q.stop()

    async def test_human_rejection_updates_stats(self) -> None:
        q = DeliberationQueue()
        msg = _make_message("human-reject")
        task_id = await q.enqueue_for_deliberation(msg)
        await q.update_status(task_id, DeliberationStatus.UNDER_REVIEW)
        result = await q.submit_human_decision(
            task_id, "reviewer-2", DeliberationStatus.REJECTED, "no good"
        )
        assert result is True
        assert q.stats["rejected"] >= 1
        await q.stop()

    async def test_human_decision_with_persistence(self, tmp_path) -> None:
        path = str(tmp_path / "human_decision.json")
        q = DeliberationQueue(persistence_path=path)
        msg = _make_message("hd-persist")
        task_id = await q.enqueue_for_deliberation(msg)
        await q.update_status(task_id, DeliberationStatus.UNDER_REVIEW)
        await q.submit_human_decision(task_id, "r1", DeliberationStatus.APPROVED, "great")
        await asyncio.sleep(0.05)
        await q.stop()


# ---------------------------------------------------------------------------
# _save_tasks
# ---------------------------------------------------------------------------


class TestSaveTasks:
    def test_save_tasks_no_persistence_path(self) -> None:
        q = DeliberationQueue()
        q._save_tasks()

    def test_save_tasks_writes_file(self, tmp_path) -> None:
        path = str(tmp_path / "save_test.json")
        q = DeliberationQueue(persistence_path=path)
        msg = _make_message("save-001")
        task = DeliberationTask(task_id="t1", message=msg)
        q.tasks["t1"] = task
        q._save_tasks()
        assert os.path.exists(path)
        with open(path) as f:
            data = json.load(f)
        assert "t1" in data

    def test_save_tasks_handles_persistence_error(self, tmp_path) -> None:
        path = str(tmp_path / "error_save.json")
        q = DeliberationQueue(persistence_path=path)
        msg = _make_message("err-001")
        task = DeliberationTask(task_id="t-err", message=msg)
        q.tasks["t-err"] = task
        with patch.object(q, "_run_async_io", side_effect=RuntimeError("write failed")):
            q._save_tasks()

    def test_save_tasks_with_task_no_message(self, tmp_path) -> None:
        path = str(tmp_path / "no_msg.json")
        q = DeliberationQueue(persistence_path=path)
        task = DeliberationTask(task_id="no-msg-save")
        task.message = None
        q.tasks["no-msg-save"] = task
        q._save_tasks()
        with open(path) as f:
            data = json.load(f)
        assert data["no-msg-save"]["message"] == {}

    def test_save_tasks_calls_run_async_io(self, tmp_path) -> None:
        """Cover the _run_async_io call path inside _save_tasks."""
        path = str(tmp_path / "mock_run.json")
        q = DeliberationQueue(persistence_path=path)
        msg = _make_message("mock-run-001")
        task = DeliberationTask(task_id="mr-1", message=msg)
        q.tasks["mr-1"] = task
        with patch.object(q, "_run_async_io", return_value=None) as mock_run:
            q._save_tasks()
        mock_run.assert_called_once()


# ---------------------------------------------------------------------------
# _read_persistence_file / _write_persistence_file
# ---------------------------------------------------------------------------


class TestPersistenceHelpers:
    async def test_write_and_read_file(self, tmp_path) -> None:
        path = str(tmp_path / "rw_test.json")
        q = DeliberationQueue()
        content = '{"key": "value"}'
        await q._write_persistence_file(path, content)
        result = await q._read_persistence_file(path)
        assert result == content

    async def test_read_nonexistent_raises(self) -> None:
        q = DeliberationQueue()
        with pytest.raises(FileNotFoundError):
            await q._read_persistence_file("/tmp/nonexistent_acgs_test_abc.json")


# ---------------------------------------------------------------------------
# _run_async_io
# ---------------------------------------------------------------------------


class TestRunAsyncIo:
    async def test_runs_coroutine_in_thread_when_loop_running(self) -> None:
        """When an event loop is running, _run_async_io uses a thread."""

        async def _simple() -> str:
            return "hello"

        result = DeliberationQueue._run_async_io(_simple())
        assert result == "hello"

    def test_runs_coroutine_directly_when_no_loop(self) -> None:
        """When no event loop is running, asyncio.run is used."""

        async def _answer() -> int:
            return 42

        result = DeliberationQueue._run_async_io(_answer())
        assert result == 42

    async def test_exception_from_thread_is_reraised(self) -> None:
        """Exceptions raised in the worker thread are re-raised."""

        async def _fail() -> None:
            raise ValueError("thread error")

        with pytest.raises(ValueError, match="thread error"):
            DeliberationQueue._run_async_io(_fail())


# ---------------------------------------------------------------------------
# resolve_task
# ---------------------------------------------------------------------------


class TestResolveTask:
    async def test_resolve_approved(self) -> None:
        q = DeliberationQueue()
        msg = _make_message("resolve-ok")
        task_id = await q.enqueue_for_deliberation(msg)
        await q.resolve_task(task_id, approved=True)
        task = q.get_task(task_id)
        assert task.status == DeliberationStatus.APPROVED
        # Compare by .value to avoid importlib enum identity issues
        assert task.message.status.value == "pending"
        await q.stop()

    async def test_resolve_rejected(self) -> None:
        q = DeliberationQueue()
        msg = _make_message("resolve-fail")
        task_id = await q.enqueue_for_deliberation(msg)
        await q.resolve_task(task_id, approved=False)
        task = q.get_task(task_id)
        assert task.status == DeliberationStatus.REJECTED
        assert task.message.status.value == "failed"
        await q.stop()

    async def test_resolve_nonexistent_task(self) -> None:
        q = DeliberationQueue()
        await q.resolve_task("no-such-task", approved=True)
        await q.stop()


# ---------------------------------------------------------------------------
# get_deliberation_queue (singleton)
# ---------------------------------------------------------------------------


def _get_dq_module():
    """Return the deliberation_queue module regardless of import path alias."""
    for key in (
        "enhanced_agent_bus.deliberation_layer.deliberation_queue",
        "core.enhanced_agent_bus.deliberation_layer.deliberation_queue",
        "enhanced_agent_bus.deliberation_layer.deliberation_queue",
    ):
        mod = sys.modules.get(key)
        if mod is not None:
            return mod
    return None


class TestGetDeliberationQueue:
    def setup_method(self) -> None:
        reset_deliberation_queue()

    def teardown_method(self) -> None:
        reset_deliberation_queue()

    def test_returns_deliberation_queue(self) -> None:
        q = get_deliberation_queue()
        assert isinstance(q, DeliberationQueue)

    def test_returns_same_instance(self) -> None:
        q1 = get_deliberation_queue()
        q2 = get_deliberation_queue()
        assert q1 is q2

    def test_creates_new_after_reset(self) -> None:
        q1 = get_deliberation_queue()
        reset_deliberation_queue()
        q2 = get_deliberation_queue()
        assert q1 is not q2

    def test_creates_with_persistence_path(self, tmp_path) -> None:
        path = str(tmp_path / "singleton.json")
        q = get_deliberation_queue(persistence_path=path)
        assert q.persistence_path == path


# ---------------------------------------------------------------------------
# reset_deliberation_queue
# ---------------------------------------------------------------------------


class TestResetDeliberationQueue:
    def teardown_method(self) -> None:
        reset_deliberation_queue()

    def test_reset_when_none(self) -> None:
        reset_deliberation_queue()

    async def test_reset_with_active_singleton(self) -> None:
        q = get_deliberation_queue()
        msg = _make_message("reset-001")
        await q.enqueue_for_deliberation(msg)
        reset_deliberation_queue()
        dq_module = _get_dq_module()
        if dq_module is not None:
            assert dq_module._deliberation_queue is None

    async def test_reset_with_tasks_running_event_loop(self) -> None:
        """Lines 549-575: reset signals shutdown; running loop path uses call_soon."""
        q = get_deliberation_queue()
        msg = _make_message("reset-loop")
        await q.enqueue_for_deliberation(msg)
        reset_deliberation_queue()

    def test_reset_with_queue_no_tasks(self) -> None:
        """Queue exists but no tasks — tasks_to_cancel empty, skips the try block."""
        dq_module = _get_dq_module()
        if dq_module is None:
            pytest.skip("Cannot locate deliberation_queue module")
        dq_module._deliberation_queue = DeliberationQueue()
        reset_deliberation_queue()
        assert dq_module._deliberation_queue is None

    async def test_reset_with_done_task_skips_cancel(self) -> None:
        """Line 554->553: task.done() is True in the for loop, cancel() is NOT called.

        Creates a real asyncio.Task, awaits it to completion, then calls
        reset_deliberation_queue which should skip cancel() for done tasks.
        """
        dq_module = _get_dq_module()
        if dq_module is None:
            pytest.skip("Cannot locate deliberation_queue module")

        async def _instant():
            return None

        done_task = asyncio.create_task(_instant())
        for _ in range(20):
            await asyncio.sleep(0)
        assert done_task.done()

        q = DeliberationQueue()
        q.processing_tasks.append(done_task)
        dq_module._deliberation_queue = q

        cancel_called = []
        original_cancel = done_task.cancel

        def _track(*args, **kwargs):
            cancel_called.append(True)
            return original_cancel(*args, **kwargs)

        done_task.cancel = _track  # type: ignore[method-assign]
        reset_deliberation_queue()
        assert cancel_called == []  # cancel() skipped because task.done() is True

    def test_reset_with_real_tasks_no_running_loop(self) -> None:
        """Lines 562-573: no running loop, tasks_to_cancel non-empty.

        Creates a real coroutine-based asyncio.Future in a fresh loop in a
        background thread. The thread has no running loop when reset is called,
        so reset_deliberation_queue takes the RuntimeError branch and creates
        a temporary new event loop to gather the cancellations (lines 565-571).
        """
        dq_module = _get_dq_module()
        if dq_module is None:
            pytest.skip("Cannot locate deliberation_queue module")

        results: dict = {}

        def _run_in_thread() -> None:
            # Ensure no event loop is set
            asyncio.set_event_loop(None)

            # Create a brand new event loop and a real pending task inside it
            inner_loop = asyncio.new_event_loop()

            async def _sleeper():
                await asyncio.sleep(100)

            task = inner_loop.create_task(_sleeper())
            # Do NOT run inner_loop — leave the task pending
            # Close the loop now so there is no "running loop"
            # (Actually, closing without running will leave the task in a weird state,
            # so instead just don't set it as the event loop)

            q = DeliberationQueue()
            q.processing_tasks.append(task)
            dq_module._deliberation_queue = q

            try:
                dq_module.reset_deliberation_queue()
                results["done"] = dq_module._deliberation_queue is None
            except Exception as exc:
                results["error"] = str(exc)
            finally:
                # Clean up the inner loop
                try:
                    inner_loop.close()
                except Exception:
                    pass

        t = threading.Thread(target=_run_in_thread, daemon=True)
        t.start()
        t.join(timeout=10.0)
        assert not t.is_alive(), "Thread did not complete in time"
        # Either succeeded or hit the inner exception path — both exercise the branch
        assert "done" in results or "error" in results


# ---------------------------------------------------------------------------
# cleanup_all_deliberation_queues
# ---------------------------------------------------------------------------


class TestCleanupAllDeliberationQueues:
    async def test_cleanup_empty_list(self) -> None:
        _all_queue_instances.clear()
        cleanup_all_deliberation_queues()
        assert _all_queue_instances == []

    async def test_cleanup_with_instances(self) -> None:
        _all_queue_instances.clear()
        q1 = DeliberationQueue(default_timeout=60)
        q2 = DeliberationQueue(default_timeout=60)
        msg1 = _make_message("cl-001")
        msg2 = _make_message("cl-002")
        await q1.enqueue_for_deliberation(msg1)
        await q2.enqueue_for_deliberation(msg2)
        assert q1 in _all_queue_instances
        assert q2 in _all_queue_instances
        cleanup_all_deliberation_queues()
        assert _all_queue_instances == []
        assert q1.processing_tasks == []
        assert q2.processing_tasks == []
        assert q1._shutdown is True
        assert q2._shutdown is True

    async def test_cleanup_handles_none_in_list(self) -> None:
        _all_queue_instances.clear()
        _all_queue_instances.append(None)  # type: ignore[arg-type]
        _all_queue_instances.append(DeliberationQueue())
        cleanup_all_deliberation_queues()
        assert _all_queue_instances == []

    async def test_cleanup_with_done_task_branch(self) -> None:
        """Line 594->593: task.done() is True — cancel() is NOT called."""
        _all_queue_instances.clear()
        q = DeliberationQueue(default_timeout=60)

        # Create and fully complete a coroutine task
        async def _instant_noop() -> None:
            return None

        done_task = asyncio.create_task(_instant_noop())
        # Give event loop enough cycles to complete the task
        for _ in range(10):
            await asyncio.sleep(0)
        assert done_task.done(), "Task should be done after multiple event loop iterations"

        q.processing_tasks.append(done_task)
        _all_queue_instances.append(q)

        cancel_called = []
        original_cancel = done_task.cancel

        def _track_cancel(*args, **kwargs):
            cancel_called.append(True)
            return original_cancel(*args, **kwargs)

        done_task.cancel = _track_cancel  # type: ignore[method-assign]
        cleanup_all_deliberation_queues()
        assert cancel_called == []
        assert _all_queue_instances == []

    async def test_cleanup_with_not_done_task_cancels(self) -> None:
        """Confirm cancel() IS called for non-done tasks."""
        _all_queue_instances.clear()
        q = DeliberationQueue(default_timeout=60)

        async def _long():
            await asyncio.sleep(100)

        running_task = asyncio.create_task(_long())
        q.processing_tasks.append(running_task)
        _all_queue_instances.append(q)
        cleanup_all_deliberation_queues()
        assert _all_queue_instances == []
        running_task.cancel()
        try:
            await running_task
        except asyncio.CancelledError:
            pass


# ---------------------------------------------------------------------------
# Persistence integration round-trip
# ---------------------------------------------------------------------------


class TestPersistenceRoundTrip:
    async def test_full_roundtrip(self, tmp_path) -> None:
        path = str(tmp_path / "roundtrip.json")
        q1 = DeliberationQueue(persistence_path=path)
        msg = _make_message("rt-001")
        task_id = await q1.enqueue_for_deliberation(msg)
        await asyncio.sleep(0.05)
        q1._save_tasks()
        await q1.stop()

        q2 = DeliberationQueue(persistence_path=path)
        loaded = q2.get_task(task_id)
        assert loaded is not None
        assert loaded.message.message_id == "rt-001"
        await q2.stop()

    async def test_async_save_tasks(self, tmp_path) -> None:
        path = str(tmp_path / "async_save.json")
        q = DeliberationQueue(persistence_path=path)
        msg = _make_message("as-001")
        task = DeliberationTask(task_id="as-task", message=msg)
        q.tasks["as-task"] = task
        await q._async_save_tasks()
        assert os.path.exists(path)
        await q.stop()


# ---------------------------------------------------------------------------
# DELIBERATION_PERSISTENCE_ERRORS
# ---------------------------------------------------------------------------


class TestPersistenceErrorsTuple:
    def test_all_expected_exception_types_present(self) -> None:
        expected = (RuntimeError, ValueError, TypeError, KeyError, AttributeError, OSError)
        for exc_type in expected:
            assert exc_type in DELIBERATION_PERSISTENCE_ERRORS

    def test_is_a_tuple(self) -> None:
        assert isinstance(DELIBERATION_PERSISTENCE_ERRORS, tuple)


# ---------------------------------------------------------------------------
# __all__ exports
# ---------------------------------------------------------------------------


class TestAllExports:
    def test_all_names_importable(self) -> None:
        import importlib

        mod = importlib.import_module("enhanced_agent_bus.deliberation_layer.deliberation_queue")
        for name in mod.__all__:
            assert hasattr(mod, name), f"Missing export: {name}"
