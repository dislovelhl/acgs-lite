"""
ACGS-2 LangGraph Orchestration - Persistence Tests
Constitutional Hash: 608508a9bd224290
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.models import (
    CONSTITUTIONAL_HASH,
    Checkpoint,
    CheckpointStatus,
    ExecutionResult,
    ExecutionStatus,
    GraphState,
)

from ..persistence import (
    InMemoryStatePersistence,
    RedisStatePersistence,
    StatePersistence,
    create_state_persistence,
)


class TestInMemoryStatePersistence:
    """Tests for InMemoryStatePersistence."""

    def test_create_persistence(self):
        """Test creating in-memory persistence."""
        persistence = InMemoryStatePersistence()
        assert persistence.constitutional_hash == CONSTITUTIONAL_HASH
        assert len(persistence._snapshots) == 0

    def test_create_with_custom_hash(self):
        """Test creating with custom hash."""
        persistence = InMemoryStatePersistence(constitutional_hash="custom")
        assert persistence.constitutional_hash == "custom"

    async def test_save_and_load_state(self):
        """Test saving and loading state."""
        persistence = InMemoryStatePersistence()
        state = GraphState(data={"key": "value"}, version=1)

        snapshot_id = await persistence.save_state(
            workflow_id="wf1",
            run_id="run1",
            state=state,
            node_id="node1",
            step_index=0,
        )

        assert snapshot_id is not None

        loaded = await persistence.load_state("wf1")

        assert loaded is not None
        assert loaded.data == {"key": "value"}

    async def test_load_state_not_found(self):
        """Test loading nonexistent state."""
        persistence = InMemoryStatePersistence()
        loaded = await persistence.load_state("nonexistent")
        assert loaded is None

    async def test_save_multiple_states(self):
        """Test saving multiple state versions."""
        persistence = InMemoryStatePersistence()

        for i in range(3):
            state = GraphState(data={"version": i}, version=i)
            await persistence.save_state(
                workflow_id="wf1",
                run_id="run1",
                state=state,
                node_id=f"node{i}",
                step_index=i,
            )

        # Should get latest
        loaded = await persistence.load_state("wf1")
        assert loaded.data["version"] == 2

    async def test_save_and_load_checkpoint(self):
        """Test saving and loading checkpoint."""
        persistence = InMemoryStatePersistence()
        state = GraphState(data={"test": "data"})
        checkpoint = Checkpoint(
            id="cp1",
            workflow_id="wf1",
            run_id="run1",
            node_id="node1",
            step_index=0,
            state=state,
        )

        await persistence.save_checkpoint(checkpoint)
        loaded = await persistence.load_checkpoint("cp1")

        assert loaded is not None
        assert loaded.id == "cp1"
        assert loaded.workflow_id == "wf1"

    async def test_load_checkpoint_not_found(self):
        """Test loading nonexistent checkpoint."""
        persistence = InMemoryStatePersistence()
        loaded = await persistence.load_checkpoint("nonexistent")
        assert loaded is None

    async def test_list_checkpoints(self):
        """Test listing checkpoints."""
        persistence = InMemoryStatePersistence()

        for i in range(3):
            state = GraphState(data={"index": i})
            checkpoint = Checkpoint(
                id=f"cp{i}",
                workflow_id="wf1",
                run_id="run1",
                node_id=f"node{i}",
                step_index=i,
                state=state,
            )
            await persistence.save_checkpoint(checkpoint)

        checkpoints = await persistence.list_checkpoints("wf1")

        assert len(checkpoints) == 3
        assert checkpoints[0].id == "cp0"

    async def test_list_checkpoints_by_run_id(self):
        """Test listing checkpoints filtered by run_id."""
        persistence = InMemoryStatePersistence()

        for run_id in ["run1", "run1", "run2"]:
            state = GraphState(data={})
            checkpoint = Checkpoint(
                workflow_id="wf1",
                run_id=run_id,
                node_id="node1",
                step_index=0,
                state=state,
            )
            await persistence.save_checkpoint(checkpoint)

        run1_checkpoints = await persistence.list_checkpoints("wf1", run_id="run1")

        assert len(run1_checkpoints) == 2

    async def test_delete_checkpoint(self):
        """Test deleting checkpoint."""
        persistence = InMemoryStatePersistence()
        state = GraphState(data={})
        checkpoint = Checkpoint(
            id="cp1",
            workflow_id="wf1",
            run_id="run1",
            node_id="node1",
            step_index=0,
            state=state,
        )

        await persistence.save_checkpoint(checkpoint)
        deleted = await persistence.delete_checkpoint("cp1")

        assert deleted is True
        loaded = await persistence.load_checkpoint("cp1")
        assert loaded is None

    async def test_delete_nonexistent_checkpoint(self):
        """Test deleting nonexistent checkpoint."""
        persistence = InMemoryStatePersistence()
        deleted = await persistence.delete_checkpoint("nonexistent")
        assert deleted is False

    async def test_save_and_load_execution_result(self):
        """Test saving and loading execution result."""
        persistence = InMemoryStatePersistence()
        state = GraphState(data={"final": "result"})
        result = ExecutionResult(
            workflow_id="wf1",
            run_id="run1",
            status=ExecutionStatus.COMPLETED,
            final_state=state,
            total_execution_time_ms=100.0,
            node_count=5,
            step_count=10,
        )

        await persistence.save_execution_result(result)
        loaded = await persistence.load_execution_result("wf1", "run1")

        assert loaded is not None
        assert loaded.status == ExecutionStatus.COMPLETED
        assert loaded.total_execution_time_ms == 100.0

    async def test_load_execution_result_not_found(self):
        """Test loading nonexistent execution result."""
        persistence = InMemoryStatePersistence()
        loaded = await persistence.load_execution_result("wf1", "run1")
        assert loaded is None

    def test_clear(self):
        """Test clearing all data."""
        persistence = InMemoryStatePersistence()
        persistence._snapshots["test"] = MagicMock()
        persistence._checkpoints["test"] = MagicMock()
        persistence._results["test"] = MagicMock()
        persistence._workflow_states["test"] = ["id1"]

        persistence.clear()

        assert len(persistence._snapshots) == 0
        assert len(persistence._checkpoints) == 0
        assert len(persistence._results) == 0
        assert len(persistence._workflow_states) == 0


class TestRedisStatePersistence:
    """Tests for RedisStatePersistence (unit tests without Redis)."""

    def test_create_persistence(self):
        """Test creating Redis persistence."""
        persistence = RedisStatePersistence()
        assert persistence.redis_url == "redis://localhost:6379"
        assert persistence.key_prefix == "acgs2:langgraph:"
        assert persistence.ttl_seconds == 86400

    def test_create_with_custom_settings(self):
        """Test creating with custom settings."""
        persistence = RedisStatePersistence(
            redis_url="redis://custom:6380",
            key_prefix="custom:",
            ttl_seconds=3600,
        )
        assert persistence.redis_url == "redis://custom:6380"
        assert persistence.key_prefix == "custom:"
        assert persistence.ttl_seconds == 3600

    def test_key_generation(self):
        """Test key generation methods."""
        persistence = RedisStatePersistence(key_prefix="test:")

        state_key = persistence._state_key("wf1", "run1")
        assert state_key == "test:state:wf1:run1"

        checkpoint_key = persistence._checkpoint_key("cp1")
        assert checkpoint_key == "test:checkpoint:cp1"

        result_key = persistence._result_key("wf1", "run1")
        assert result_key == "test:result:wf1:run1"

        index_key = persistence._workflow_checkpoints_key("wf1")
        assert index_key == "test:checkpoints:wf1"


class TestCreateStatePersistence:
    """Tests for create_state_persistence factory."""

    def test_create_memory_persistence(self):
        """Test creating memory persistence."""
        persistence = create_state_persistence(backend="memory")
        assert isinstance(persistence, InMemoryStatePersistence)

    def test_create_redis_persistence(self):
        """Test creating Redis persistence."""
        persistence = create_state_persistence(
            backend="redis",
            redis_url="redis://localhost:6379",
        )
        assert isinstance(persistence, RedisStatePersistence)

    def test_create_with_custom_hash(self):
        """Test creating persistence with custom hash."""
        persistence = create_state_persistence(
            backend="memory",
            constitutional_hash="custom",
        )
        assert persistence.constitutional_hash == "custom"

    def test_create_unknown_backend(self):
        """Test creating with unknown backend."""
        with pytest.raises(ValueError, match="Unknown"):
            create_state_persistence(backend="unknown")

    def test_create_redis_with_options(self):
        """Test creating Redis persistence with options."""
        persistence = create_state_persistence(
            backend="redis",
            redis_url="redis://custom:6380",
            key_prefix="myapp:",
            ttl_seconds=7200,
        )
        assert isinstance(persistence, RedisStatePersistence)
        assert persistence.redis_url == "redis://custom:6380"
        assert persistence.key_prefix == "myapp:"
        assert persistence.ttl_seconds == 7200
