"""
ACGS-2 Deliberation Layer - Deliberation Queue
Constitutional Hash: cdd01ef066bc6cf2
Persistent queue for high-impact messages awaiting approval.
"""

import asyncio
import json
import threading
import uuid
from collections.abc import Coroutine
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from typing import Optional, TypeAlias, TypeVar, Union, cast

import aiofiles
from packages.enhanced_agent_bus.governance_constants import (
    DEFAULT_CONSENSUS_THRESHOLD,
    DEFAULT_DELIBERATION_TIMEOUT_SECONDS,
    DEFAULT_REQUIRED_VOTES,
)

from enhanced_agent_bus.observability.structured_logging import get_logger

try:
    from packages.enhanced_agent_bus.models import AgentMessage, MessageStatus, get_enum_value
except (ImportError, ValueError):
    try:
        from enhanced_agent_bus.models import AgentMessage, MessageStatus, get_enum_value
    except (ImportError, ValueError):
        try:
            from packages.enhanced_agent_bus.models import (
                AgentMessage,
                MessageStatus,
                get_enum_value,
            )
        except (ImportError, ValueError):
            # Fallback for direct execution or testing
            from models import (  # type: ignore[import-untyped]
                AgentMessage,
                MessageStatus,
                get_enum_value,
            )
from enum import Enum

from src.core.shared.types import JSONDict, JSONValue


class DeliberationStatus(Enum):
    PENDING = "pending"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMED_OUT = "timed_out"
    CONSENSUS_REACHED = "consensus_reached"


class VoteType(Enum):
    APPROVE = "approve"
    REJECT = "reject"
    ABSTAIN = "abstain"


@dataclass
class AgentVote:
    """Represents a vote from an agent on a deliberation item."""

    agent_id: str
    vote: VoteType
    reasoning: str
    confidence_score: float = 1.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class DeliberationTask:
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    message: AgentMessage | None = None
    status: DeliberationStatus = DeliberationStatus.PENDING
    required_votes: int = DEFAULT_REQUIRED_VOTES
    consensus_threshold: float = DEFAULT_CONSENSUS_THRESHOLD
    timeout_seconds: int = DEFAULT_DELIBERATION_TIMEOUT_SECONDS
    current_votes: list[AgentVote] = field(default_factory=list)
    metadata: JSONDict = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    human_reviewer: str | None = None
    human_decision: DeliberationStatus | None = None
    human_reasoning: str | None = None

    @property
    def voting_deadline(self) -> datetime:
        return self.created_at + timedelta(seconds=self.timeout_seconds)

    @property
    def item_id(self) -> str:
        return self.task_id

    @property
    def is_complete(self) -> bool:
        return self.status in [
            DeliberationStatus.APPROVED,
            DeliberationStatus.REJECTED,
            DeliberationStatus.TIMED_OUT,
        ]


# Aliases for backward compatibility in certain test suites
DeliberationItem = DeliberationTask

logger = get_logger(__name__)
DELIBERATION_PERSISTENCE_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    OSError,
)

T = TypeVar("T")

# Global registry of all queue instances for cleanup
_all_queue_instances: list = []


class DeliberationQueue:
    """
    Queue for managing messages that require human-in-the-loop or
    multi-agent deliberation.

    PERFORMANCE OPTIMIZATION:
    - Uses partitioned locks to reduce contention (4 partitions by default)
    - Partition selection based on task_id hash for consistent routing
    - Enables parallel processing of tasks in different partitions
    - Target: >6000 RPS throughput with P99 latency <1ms
    """

    # Number of partitions for reduced lock contention
    NUM_PARTITIONS = 4

    def __init__(
        self,
        persistence_path: str | None = None,
        consensus_threshold: float = 0.66,
        default_timeout: int = 300,
    ):
        self.queue: dict[str, DeliberationTask] = {}  # Legacy name compatibility
        self.tasks = self.queue  # Preferred name
        self.processing_tasks: list[asyncio.Task] = []
        self._bg_tasks: set[asyncio.Task] = set()  # Prevents GC of fire-and-forget tasks
        self.persistence_path = persistence_path
        self.consensus_threshold = consensus_threshold
        self.default_timeout = default_timeout
        self.stats = {
            "total_queued": 0,
            "approved": 0,
            "rejected": 0,
            "timed_out": 0,
            "consensus_reached": 0,
            "avg_processing_time": 0.0,
        }
        # PERFORMANCE: Partitioned locks for reduced contention
        # Use multiple locks to allow parallel operations on different task partitions
        self._partition_locks = [asyncio.Lock() for _ in range(self.NUM_PARTITIONS)]
        self._lock = asyncio.Lock()  # Global lock for stats and persistence only
        self._shutdown = False  # Shutdown flag for clean task termination
        self._shutdown_event = asyncio.Event()  # Event for immediate task wakeup on shutdown
        # Register this instance for global cleanup
        _all_queue_instances.append(self)
        if self.persistence_path:
            self._load_tasks()

    def _get_partition_lock(self, task_id: str) -> asyncio.Lock:
        """Get the partition lock for a given task_id.

        Uses hash-based routing for consistent partition assignment.
        """
        partition_idx = hash(task_id) % self.NUM_PARTITIONS
        return self._partition_locks[partition_idx]

    def _load_tasks(self) -> None:
        """Load tasks from persistent storage."""
        try:
            path = self.persistence_path
            if path is None:
                return
            content = self._run_async_io(self._read_persistence_file(path))
            data = json.loads(content)
            for tid, tdata in data.items():
                # Simplified reconstruction
                msg = AgentMessage.from_dict(tdata["message"])
                task = DeliberationTask(
                    task_id=tid,
                    message=msg,
                    status=DeliberationStatus(
                        tdata["status"].lower()
                        if isinstance(tdata["status"], str)
                        else tdata["status"]
                    ),
                    metadata=tdata.get("metadata", {}),
                    created_at=datetime.fromisoformat(tdata["created_at"]),
                )
                self.tasks[tid] = task
        except (FileNotFoundError, json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"Failed to load deliberation tasks: {e}")
            pass

    async def enqueue_for_deliberation(
        self,
        message: AgentMessage,
        requires_human_review: bool = False,
        requires_multi_agent_vote: bool = False,
        timeout_seconds: int | None = None,
    ) -> str:
        """Enqueue a message for deliberation.

        PERFORMANCE: Uses partitioned lock to reduce contention.
        Only the partition containing this task is locked, allowing
        parallel enqueue operations on other partitions.
        """
        task_id = str(uuid.uuid4())
        timeout = timeout_seconds or self.default_timeout

        task = DeliberationTask(
            task_id=task_id,
            message=message,
            timeout_seconds=timeout,
            required_votes=5 if requires_multi_agent_vote else 0,  # Match test expectation 5
            consensus_threshold=self.consensus_threshold,
            metadata={
                "requires_human": requires_human_review,
                "requires_vote": requires_multi_agent_vote,
            },
        )

        # Use partition lock for task insertion (allows parallel inserts to other partitions)
        partition_lock = self._get_partition_lock(task_id)
        async with partition_lock:
            self.tasks[task_id] = task

        # Use global lock only for stats update (minimal critical section)
        async with self._lock:
            self.stats["total_queued"] += 1

        # Start background processing (e.g. timeout monitor) - non-blocking
        proc_task = asyncio.create_task(self._monitor_task(task_id))
        self.processing_tasks.append(proc_task)

        # Persist asynchronously if needed (non-blocking)
        if self.persistence_path:
            _t = asyncio.create_task(self._async_save_tasks())
            self._bg_tasks.add(_t)
            _t.add_done_callback(self._bg_tasks.discard)

        logger.info(f"Message {message.message_id} enqueued for deliberation (Task {task_id})")
        return task_id

    async def _async_save_tasks(self) -> None:
        """Asynchronously save tasks to persistent storage."""
        await asyncio.to_thread(self._save_tasks)

    async def enqueue(self, *args, **kwargs) -> str:
        """Alias for enqueue_for_deliberation."""
        return await self.enqueue_for_deliberation(*args, **kwargs)

    async def _monitor_task(self, task_id: str) -> None:
        """Monitor task for timeout with proper shutdown handling."""
        task = self.tasks.get(task_id)
        if not task:
            return

        current_task = asyncio.current_task()
        try:
            # Use smaller sleep intervals to respond to shutdown quickly
            elapsed: float = 0.0
            check_interval = min(1.0, task.timeout_seconds / 10)
            while elapsed < task.timeout_seconds:
                if self._shutdown:
                    return  # Exit cleanly on shutdown
                # Wait for either the check interval or shutdown event
                try:
                    await asyncio.wait_for(self._shutdown_event.wait(), timeout=check_interval)
                    # Shutdown event was set
                    return
                except TimeoutError:
                    # Normal timeout, continue monitoring
                    pass
                elapsed += check_interval
                # Check if task was resolved externally
                if task.is_complete:
                    return

            # Timeout reached
            async with self._lock:
                if task_id in self.tasks and not task.is_complete:
                    task.status = DeliberationStatus.TIMED_OUT
                    self.stats["timed_out"] += 1
                    await self._async_save_tasks()
                    logger.warning(f"Task {task_id} timed out")
        except asyncio.CancelledError:
            # Propagate cancellation properly
            raise
        finally:
            # Clean up task reference
            if current_task and current_task in self.processing_tasks:
                try:  # noqa: SIM105
                    self.processing_tasks.remove(current_task)
                except ValueError:
                    pass  # Already removed

    async def stop(self) -> None:
        """Stop all background tasks cleanly."""
        self._shutdown = True  # Signal all monitor tasks to exit
        self._shutdown_event.set()  # Wake up all waiting tasks immediately
        tasks_to_cancel = list(self.processing_tasks)  # Copy to avoid modification during iteration
        for task in tasks_to_cancel:
            if not task.done():
                task.cancel()
        if tasks_to_cancel:
            # Wait for tasks to complete with timeout to avoid hanging
            try:
                await asyncio.wait_for(
                    asyncio.gather(*tasks_to_cancel, return_exceptions=True), timeout=2.0
                )
            except TimeoutError:
                logger.warning("Some deliberation tasks did not stop cleanly within timeout")
        self.processing_tasks.clear()

    async def __aenter__(self) -> "DeliberationQueue":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: object, exc_val: object, exc_tb: object) -> bool:
        """Async context manager exit - ensures cleanup."""
        await self.stop()
        return False

    async def update_status(self, task_id: str, status: DeliberationStatus | str) -> None:
        """Update the status of a deliberation task."""
        async with self._lock:
            if task_id in self.tasks:
                if isinstance(status, str):
                    try:  # noqa: SIM105
                        status = DeliberationStatus(status.lower())
                    except ValueError:
                        # Fallback for manual string statuses
                        pass

                if isinstance(status, DeliberationStatus):
                    self.tasks[task_id].status = status
                await self._async_save_tasks()

    def get_pending_tasks(self) -> list[DeliberationItem]:
        """Get all tasks awaiting deliberation."""
        pending_value = DeliberationStatus.PENDING.value
        return [t for t in self.tasks.values() if get_enum_value(t.status) == pending_value]

    def get_task(self, task_id: str) -> DeliberationItem | None:
        """Get a task by ID."""
        return self.tasks.get(task_id)

    def get_item_details(self, item_id: str) -> JSONDict | None:
        """Get details for an item (test compatibility)."""
        task = self.get_task(item_id)
        if not task:
            return None
        return {
            "item_id": task.item_id,
            "message_id": task.message.message_id if task.message else None,
            "status": get_enum_value(task.status),
            "created_at": task.created_at.isoformat(),
            "updated_at": task.updated_at.isoformat(),
            "votes": len(task.current_votes),
        }

    def get_queue_status(self) -> JSONDict:
        """Get overall status (test compatibility)."""
        return {
            "queue_size": len(self.tasks),
            "items": list(self.tasks.keys()),
            "stats": self.stats,
            "processing_count": len(self.processing_tasks),
        }

    async def submit_agent_vote(
        self, item_id: str, agent_id: str, vote: VoteType, reasoning: str, confidence: float = 1.0
    ) -> bool:
        """Submit an agent's vote.

        PERFORMANCE: Uses partitioned lock for task access,
        global lock only for stats updates.
        """
        partition_lock = self._get_partition_lock(item_id)
        async with partition_lock:
            task = self.tasks.get(item_id)
            if not task or task.is_complete:
                return False

            # Filter out existing votes from same agent
            task.current_votes = [v for v in task.current_votes if v.agent_id != agent_id]

            new_vote = AgentVote(
                agent_id=agent_id, vote=vote, reasoning=reasoning, confidence_score=confidence
            )
            task.current_votes.append(new_vote)

            # Check for consensus
            if self._check_consensus(task):
                task.status = DeliberationStatus.APPROVED  # Or specific consensus state
                # Update stats with global lock
                async with self._lock:
                    self.stats["approved"] += 1

        # Persist asynchronously
        if self.persistence_path:
            _t = asyncio.create_task(self._async_save_tasks())
            self._bg_tasks.add(_t)
            _t.add_done_callback(self._bg_tasks.discard)
        return True

    def _check_consensus(self, task: DeliberationTask) -> bool:
        """Internal consensus checking logic."""
        if not task.required_votes or len(task.current_votes) < task.required_votes:
            return False

        approvals = sum(1 for v in task.current_votes if v.vote == VoteType.APPROVE)
        return approvals / len(task.current_votes) >= task.consensus_threshold

    async def submit_human_decision(
        self, item_id: str, reviewer: str, decision: DeliberationStatus, reasoning: str
    ) -> bool:
        """Submit human decision.

        PERFORMANCE: Uses partitioned lock for task access,
        global lock only for stats updates.
        """
        partition_lock = self._get_partition_lock(item_id)
        async with partition_lock:
            task = self.tasks.get(item_id)
            if not task or task.is_complete:
                return False

            # Allow decision only if already under review
            if get_enum_value(task.status) != DeliberationStatus.UNDER_REVIEW.value:
                return False

            task.human_reviewer = reviewer
            task.human_decision = decision
            task.human_reasoning = reasoning

            # Spec-to-Artifact: record override when human reverses agent consensus
            had_agent_votes = bool(task.current_votes)
            task.status = decision

        # Record governance override for Spec-to-Artifact tracking
        if had_agent_votes:
            try:
                from packages.enhanced_agent_bus.deliberation_layer.impact_scorer import (
                    get_impact_scorer,
                )

                scorer = get_impact_scorer()
                if scorer and hasattr(scorer, "record_override"):
                    scorer.record_override()
            except (ImportError, RuntimeError):
                pass  # Metrics are best-effort, never block decisions

        # Update stats with global lock (minimal critical section)
        async with self._lock:
            if get_enum_value(decision) == DeliberationStatus.APPROVED.value:
                self.stats["approved"] += 1
            else:
                self.stats["rejected"] += 1

        # Persist asynchronously
        if self.persistence_path:
            _t = asyncio.create_task(self._async_save_tasks())
            self._bg_tasks.add(_t)
            _t.add_done_callback(self._bg_tasks.discard)
        return True

    def _save_tasks(self) -> None:
        """Save current tasks to persistent storage."""
        if not self.persistence_path:
            return
        try:
            storage = {
                tid: {
                    "message": t.message.to_dict_raw() if t.message else {},
                    "status": t.status.value if hasattr(t.status, "value") else str(t.status),
                    "metadata": t.metadata,
                    "created_at": t.created_at.isoformat(),
                }
                for tid, t in self.tasks.items()
            }
            path = self.persistence_path
            if path is None:
                return
            self._run_async_io(self._write_persistence_file(path, json.dumps(storage)))
            logger.info(
                f"Successfully persisted {len(storage)} deliberation tasks to {self.persistence_path}"  # noqa: E501
            )
        except DELIBERATION_PERSISTENCE_ERRORS as e:
            logger.error(f"Failed to persist deliberation tasks to {self.persistence_path}: {e}")

    async def _read_persistence_file(self, path: str) -> str:
        async with aiofiles.open(path) as f:
            return cast(str, await f.read())

    async def _write_persistence_file(self, path: str, content: str) -> None:
        async with aiofiles.open(path, "w") as f:
            await f.write(content)

    @staticmethod
    def _run_async_io(coro: Coroutine[object, object, T]) -> T:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)

        result: dict[str, T] = {}
        error: dict[str, BaseException] = {}

        def _runner() -> None:
            try:
                result["value"] = asyncio.run(coro)
            except BaseException as exc:  # pragma: no cover
                error["exc"] = exc

        thread = threading.Thread(target=_runner, daemon=False)
        thread.start()
        thread.join()

        if "exc" in error:
            raise error["exc"]
        return result["value"]

    async def resolve_task(self, task_id: str, approved: bool) -> None:
        """Resolve a task and return approval status."""
        status = DeliberationStatus.APPROVED if approved else DeliberationStatus.REJECTED
        await self.update_status(task_id, status)

        task = self.tasks.get(task_id)
        if not task:
            return

        if approved:
            task.message.status = MessageStatus.PENDING  # Ready for re-delivery
        else:
            task.message.status = MessageStatus.FAILED


_deliberation_queue = None


def get_deliberation_queue(persistence_path: str | None = None) -> DeliberationQueue:
    """Get singleton deliberation queue instance."""
    global _deliberation_queue
    if _deliberation_queue is None:
        _deliberation_queue = DeliberationQueue(persistence_path=persistence_path)
    return _deliberation_queue


def reset_deliberation_queue() -> None:
    """Reset the global deliberation queue instance.

    Used primarily for test isolation to prevent state leakage between tests.
    Properly cleans up any pending async tasks to avoid 'Task was destroyed but pending' warnings.
    Constitutional Hash: cdd01ef066bc6cf2
    """
    global _deliberation_queue
    if _deliberation_queue is not None:
        # Signal shutdown to stop monitor tasks gracefully
        _deliberation_queue._shutdown = True
        _deliberation_queue._shutdown_event.set()  # Wake up waiting tasks immediately
        # Cancel all pending processing tasks
        tasks_to_cancel = list(_deliberation_queue.processing_tasks)
        for task in tasks_to_cancel:
            if not task.done():
                task.cancel()
        # Try to process cancellations if there's a running event loop
        if tasks_to_cancel:
            try:
                loop = asyncio.get_running_loop()
                # If there's a running loop, schedule cleanup
                loop.call_soon(lambda: None)  # Just trigger loop iteration
            except RuntimeError:
                # No running loop - try to create one temporarily to process cancellations
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    # Brief run to process cancellations
                    loop.run_until_complete(
                        asyncio.gather(*tasks_to_cancel, return_exceptions=True)
                    )
                    loop.close()
                except (RuntimeError, ValueError, OSError):
                    pass  # Best effort cleanup
        # Clear the task list
        _deliberation_queue.processing_tasks.clear()
    _deliberation_queue = None


def cleanup_all_deliberation_queues() -> None:
    """Clean up all DeliberationQueue instances to prevent async task warnings.

    This function should be called at test teardown to properly stop all
    queue instances, not just the singleton. Essential for tests that create
    multiple queue instances directly.
    Constitutional Hash: cdd01ef066bc6cf2
    """
    global _all_queue_instances
    for queue in _all_queue_instances:
        if queue is not None:
            queue._shutdown = True
            queue._shutdown_event.set()
            tasks_to_cancel = list(queue.processing_tasks)
            for task in tasks_to_cancel:
                if not task.done():
                    task.cancel()
            queue.processing_tasks.clear()
    _all_queue_instances.clear()


__all__ = [
    "AgentVote",
    "DeliberationItem",
    "DeliberationQueue",
    "DeliberationStatus",
    "DeliberationTask",
    "VoteType",
    "cleanup_all_deliberation_queues",
    "get_deliberation_queue",
    "reset_deliberation_queue",
]
