"""
ACGS-2 LangGraph Orchestration - Constitutional Checkpoints Tests
Constitutional Hash: 608508a9bd224290
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from enhanced_agent_bus.langgraph_orchestration.exceptions import (
    CheckpointError,
    ConstitutionalViolationError,
)
from enhanced_agent_bus.models import (
    CONSTITUTIONAL_HASH,
    Checkpoint,
    CheckpointStatus,
    ExecutionContext,
    GraphState,
)

from ..constitutional_checkpoints import (
    CheckpointValidator,
    ConstitutionalCheckpoint,
    ConstitutionalCheckpointManager,
    ConstitutionalHashValidator,
    MACIRoleValidator,
    StateIntegrityValidator,
    create_checkpoint_manager,
)


class TestConstitutionalHashValidator:
    """Tests for ConstitutionalHashValidator."""

    def test_create_validator(self):
        """Test creating hash validator."""
        validator = ConstitutionalHashValidator()
        assert validator.expected_hash == CONSTITUTIONAL_HASH

    def test_create_with_custom_hash(self):
        """Test creating with custom hash."""
        validator = ConstitutionalHashValidator(expected_hash="custom_hash")
        assert validator.expected_hash == "custom_hash"

    async def test_validate_matching_hash(self):
        """Test validation with matching hash."""
        validator = ConstitutionalHashValidator()
        state = GraphState(data={"test": "value"})
        checkpoint = Checkpoint(
            workflow_id="wf1",
            run_id="run1",
            node_id="node1",
            step_index=0,
            state=state,
        )
        context = ExecutionContext(graph_id="graph1")

        is_valid, violations = await validator.validate(checkpoint, context)

        assert is_valid is True
        assert len(violations) == 0

    async def test_validate_mismatched_checkpoint_hash(self):
        """Test validation with mismatched checkpoint hash."""
        validator = ConstitutionalHashValidator()
        state = GraphState(data={})
        checkpoint = Checkpoint(
            workflow_id="wf1",
            run_id="run1",
            node_id="node1",
            step_index=0,
            state=state,
            constitutional_hash="wrong_hash",
        )
        context = ExecutionContext(graph_id="graph1")

        is_valid, violations = await validator.validate(checkpoint, context)

        assert is_valid is False
        assert len(violations) >= 1
        assert any("checkpoint" in v.lower() for v in violations)

    async def test_validate_mismatched_state_hash(self):
        """Test validation with mismatched state hash."""
        validator = ConstitutionalHashValidator()
        state = GraphState(data={}, constitutional_hash="wrong_hash")
        checkpoint = Checkpoint(
            workflow_id="wf1",
            run_id="run1",
            node_id="node1",
            step_index=0,
            state=state,
        )
        context = ExecutionContext(graph_id="graph1")

        is_valid, violations = await validator.validate(checkpoint, context)

        assert is_valid is False
        assert any("state" in v.lower() for v in violations)


class TestStateIntegrityValidator:
    """Tests for StateIntegrityValidator."""

    async def test_validate_state_integrity(self):
        """Test state integrity validation."""
        validator = StateIntegrityValidator()
        state = GraphState(data={"key": "value"}, version=1)
        checkpoint = Checkpoint(
            workflow_id="wf1",
            run_id="run1",
            node_id="node1",
            step_index=1,
            state=state,
        )
        context = ExecutionContext(graph_id="graph1")

        is_valid, _violations = await validator.validate(checkpoint, context)

        assert is_valid is True
        assert "state_checksum" in checkpoint.metadata

    async def test_validate_invalid_version(self):
        """Test validation catches invalid version."""
        validator = StateIntegrityValidator()
        state = GraphState(data={}, version=0)
        checkpoint = Checkpoint(
            workflow_id="wf1",
            run_id="run1",
            node_id="node1",
            step_index=5,  # Non-zero step with zero version
            state=state,
        )
        context = ExecutionContext(graph_id="graph1")

        is_valid, violations = await validator.validate(checkpoint, context)

        assert is_valid is False
        assert any("version" in v.lower() for v in violations)


class TestMACIRoleValidator:
    """Tests for MACIRoleValidator."""

    async def test_validate_without_maci(self):
        """Test validation passes without MACI enforcer."""
        validator = MACIRoleValidator()
        state = GraphState(data={})
        checkpoint = Checkpoint(
            workflow_id="wf1",
            run_id="run1",
            node_id="node1",
            step_index=0,
            state=state,
        )
        context = ExecutionContext(graph_id="graph1")

        is_valid, _violations = await validator.validate(checkpoint, context)

        assert is_valid is True
        assert checkpoint.maci_validated is True

    async def test_validate_with_maci_enforcer(self):
        """Test validation with MACI enforcer."""
        mock_enforcer = MagicMock()
        validator = MACIRoleValidator(maci_enforcer=mock_enforcer)

        state = GraphState(data={})
        checkpoint = Checkpoint(
            workflow_id="wf1",
            run_id="run1",
            node_id="node1",
            step_index=0,
            state=state,
        )
        context = ExecutionContext(graph_id="graph1", maci_session_id="session1")

        is_valid, _violations = await validator.validate(checkpoint, context)

        assert is_valid is True
        assert checkpoint.maci_validated is True


class TestConstitutionalCheckpoint:
    """Tests for ConstitutionalCheckpoint."""

    def test_create_checkpoint(self):
        """Test creating constitutional checkpoint."""
        state = GraphState(data={"key": "value"})
        cc = ConstitutionalCheckpoint(
            workflow_id="wf1",
            run_id="run1",
            node_id="node1",
            step_index=0,
            state=state,
        )

        assert cc.checkpoint.workflow_id == "wf1"
        assert cc.checkpoint.node_id == "node1"
        assert cc.checkpoint.constitutional_hash == CONSTITUTIONAL_HASH

    def test_add_validator(self):
        """Test adding validators."""
        state = GraphState(data={})
        cc = ConstitutionalCheckpoint(
            workflow_id="wf1",
            run_id="run1",
            node_id="node1",
            step_index=0,
            state=state,
        )

        validator = ConstitutionalHashValidator()
        cc.add_validator("hash", validator)

        assert len(cc._validators) == 1

    async def test_validate_success(self):
        """Test successful validation."""
        state = GraphState(data={}, version=1)
        cc = ConstitutionalCheckpoint(
            workflow_id="wf1",
            run_id="run1",
            node_id="node1",
            step_index=1,
            state=state,
        )
        cc.add_validator("hash", ConstitutionalHashValidator())

        context = ExecutionContext(graph_id="graph1")
        result = await cc.validate(context)

        assert result is True
        assert cc.checkpoint.status == CheckpointStatus.VALIDATED
        assert cc.checkpoint.constitutional_validated is True

    async def test_validate_failure_raises(self):
        """Test validation failure raises exception."""
        state = GraphState(data={}, constitutional_hash="wrong")
        cc = ConstitutionalCheckpoint(
            workflow_id="wf1",
            run_id="run1",
            node_id="node1",
            step_index=0,
            state=state,
        )
        cc.add_validator("hash", ConstitutionalHashValidator())

        context = ExecutionContext(graph_id="graph1")

        with pytest.raises(ConstitutionalViolationError):
            await cc.validate(context)

        assert cc.checkpoint.status == CheckpointStatus.FAILED

    def test_to_dict(self):
        """Test serialization to dict."""
        state = GraphState(data={"key": "value"})
        cc = ConstitutionalCheckpoint(
            workflow_id="wf1",
            run_id="run1",
            node_id="node1",
            step_index=0,
            state=state,
        )

        result = cc.to_dict()

        assert "checkpoint" in result
        assert "validation_results" in result


class TestConstitutionalCheckpointManager:
    """Tests for ConstitutionalCheckpointManager."""

    def test_create_manager(self):
        """Test creating checkpoint manager."""
        manager = ConstitutionalCheckpointManager()
        assert manager.constitutional_hash == CONSTITUTIONAL_HASH
        assert len(manager._validators) >= 1

    def test_create_manager_with_options(self):
        """Test creating manager with options."""
        manager = ConstitutionalCheckpointManager(
            enable_integrity_check=False,
            constitutional_hash="custom_hash",
        )
        assert manager.constitutional_hash == "custom_hash"

    async def test_create_checkpoint(self):
        """Test creating a checkpoint."""
        manager = ConstitutionalCheckpointManager()
        context = ExecutionContext(graph_id="graph1")
        state = GraphState(data={"test": "data"}, version=1)

        checkpoint = await manager.create_checkpoint(
            context=context,
            node_id="node1",
            state=state,
            metadata={"custom": "metadata"},
        )

        assert checkpoint.workflow_id == context.workflow_id
        assert checkpoint.node_id == "node1"
        assert checkpoint.status == CheckpointStatus.VALIDATED
        assert checkpoint.id in manager._checkpoints

    async def test_create_checkpoint_without_validation(self):
        """Test creating checkpoint without validation."""
        manager = ConstitutionalCheckpointManager()
        context = ExecutionContext(graph_id="graph1")
        state = GraphState(data={})

        checkpoint = await manager.create_checkpoint(
            context=context,
            node_id="node1",
            state=state,
            validate=False,
        )

        assert checkpoint.status == CheckpointStatus.CREATED

    async def test_get_checkpoint(self):
        """Test getting a checkpoint."""
        manager = ConstitutionalCheckpointManager()
        context = ExecutionContext(graph_id="graph1")
        state = GraphState(data={}, version=1)

        created = await manager.create_checkpoint(
            context=context,
            node_id="node1",
            state=state,
        )

        retrieved = await manager.get_checkpoint(created.id)

        assert retrieved is not None
        assert retrieved.id == created.id

    async def test_get_checkpoint_not_found(self):
        """Test getting nonexistent checkpoint."""
        manager = ConstitutionalCheckpointManager()
        result = await manager.get_checkpoint("nonexistent")
        assert result is None

    async def test_restore_checkpoint(self):
        """Test restoring from checkpoint."""
        manager = ConstitutionalCheckpointManager()
        context = ExecutionContext(graph_id="graph1")
        state = GraphState(data={"restored": "data"}, version=1)

        created = await manager.create_checkpoint(
            context=context,
            node_id="node1",
            state=state,
        )

        checkpoint, restored_state = await manager.restore_checkpoint(created.id, context)

        assert checkpoint.id == created.id
        assert checkpoint.status == CheckpointStatus.RESTORED
        assert restored_state.data == {"restored": "data"}

    async def test_restore_checkpoint_not_found(self):
        """Test restoring nonexistent checkpoint raises."""
        manager = ConstitutionalCheckpointManager()
        context = ExecutionContext(graph_id="graph1")

        with pytest.raises(CheckpointError):
            await manager.restore_checkpoint("nonexistent", context)

    async def test_restore_checkpoint_hash_mismatch(self):
        """Test restoring with hash mismatch raises."""
        manager = ConstitutionalCheckpointManager()
        context = ExecutionContext(graph_id="graph1")
        state = GraphState(data={}, version=1)

        created = await manager.create_checkpoint(
            context=context,
            node_id="node1",
            state=state,
        )

        # Modify checkpoint hash
        manager._checkpoints[created.id].constitutional_hash = "wrong_hash"

        with pytest.raises(CheckpointError):
            await manager.restore_checkpoint(created.id, context)

    async def test_list_checkpoints(self):
        """Test listing checkpoints."""
        manager = ConstitutionalCheckpointManager()
        context = ExecutionContext(graph_id="graph1")

        for i in range(3):
            state = GraphState(data={"index": i}, version=1)
            await manager.create_checkpoint(
                context=context,
                node_id=f"node{i}",
                state=state,
            )

        checkpoints = await manager.list_checkpoints(context.workflow_id)

        assert len(checkpoints) == 3

    async def test_delete_checkpoint(self):
        """Test deleting checkpoint."""
        manager = ConstitutionalCheckpointManager()
        context = ExecutionContext(graph_id="graph1")
        state = GraphState(data={}, version=1)

        created = await manager.create_checkpoint(
            context=context,
            node_id="node1",
            state=state,
        )

        deleted = await manager.delete_checkpoint(created.id)

        assert deleted is True
        assert created.id not in manager._checkpoints

    async def test_delete_nonexistent_checkpoint(self):
        """Test deleting nonexistent checkpoint."""
        manager = ConstitutionalCheckpointManager()
        deleted = await manager.delete_checkpoint("nonexistent")
        assert deleted is False

    async def test_cleanup_old_checkpoints(self):
        """Test cleaning up old checkpoints."""
        manager = ConstitutionalCheckpointManager()
        context = ExecutionContext(graph_id="graph1")

        for i in range(10):
            state = GraphState(data={"index": i}, version=1)
            await manager.create_checkpoint(
                context=context,
                node_id=f"node{i}",
                state=state,
            )

        deleted_count = await manager.cleanup_old_checkpoints(context.workflow_id, keep_count=3)

        assert deleted_count == 7
        remaining = await manager.list_checkpoints(context.workflow_id)
        assert len(remaining) == 3


class TestCreateCheckpointManager:
    """Tests for create_checkpoint_manager factory."""

    def test_create_default_manager(self):
        """Test creating manager with defaults."""
        manager = create_checkpoint_manager()
        assert isinstance(manager, ConstitutionalCheckpointManager)
        assert manager.enable_integrity_check is True

    def test_create_with_maci(self):
        """Test creating manager with MACI enforcer."""
        mock_enforcer = MagicMock()
        manager = create_checkpoint_manager(maci_enforcer=mock_enforcer)
        assert manager.maci_enforcer is mock_enforcer

    def test_create_without_integrity_check(self):
        """Test creating manager without integrity check."""
        manager = create_checkpoint_manager(enable_integrity_check=False)
        # Should have only hash validator
        validator_names = [name for name, _ in manager._validators]
        assert "state_integrity" not in validator_names

    def test_create_with_custom_hash(self):
        """Test creating manager with custom hash."""
        manager = create_checkpoint_manager(constitutional_hash="custom")
        assert manager.constitutional_hash == "custom"
