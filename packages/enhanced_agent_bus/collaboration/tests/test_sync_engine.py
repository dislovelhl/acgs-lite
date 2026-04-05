"""
Tests for Sync Engine and Operational Transform.

Constitutional Hash: 608508a9bd224290
"""

import asyncio

import pytest

from enhanced_agent_bus.collaboration.models import (
    CollaborationSession,
    DocumentType,
    EditOperation,
    EditOperationType,
)
from enhanced_agent_bus.collaboration.sync_engine import (
    OperationalTransform,
    SyncEngine,
)


class TestOperationalTransform:
    """Test Operational Transform algorithms."""

    def test_transform_insert_insert_different_positions(self):
        """Test transforming two insert operations at different positions."""
        ot = OperationalTransform()

        op1 = EditOperation(
            type=EditOperationType.INSERT,
            path="/content",
            value="X",
            position=5,
            user_id="user-1",
            client_id="client-1",
            version=1,
        )
        op2 = EditOperation(
            type=EditOperationType.INSERT,
            path="/content",
            value="Y",
            position=10,
            user_id="user-2",
            client_id="client-2",
            version=1,
        )

        transformed1, transformed2 = ot.transform_operations(op1, op2)

        # op1 is before op2, so op2's position should increase
        assert transformed1.position == 5
        assert transformed2.position == 11  # 10 + 1 (length of X)

    def test_transform_insert_insert_same_position(self):
        """Test transforming two insert operations at the same position."""
        ot = OperationalTransform()

        op1 = EditOperation(
            type=EditOperationType.INSERT,
            path="/content",
            value="X",
            position=5,
            user_id="user-1",
            client_id="client-1",
            version=1,
            timestamp=1000,
        )
        op2 = EditOperation(
            type=EditOperationType.INSERT,
            path="/content",
            value="Y",
            position=5,
            user_id="user-2",
            client_id="client-2",
            version=1,
            timestamp=1001,  # Later timestamp
        )

        transformed1, transformed2 = ot.transform_operations(op1, op2)

        # op1 has earlier timestamp, so op2 should be adjusted
        assert transformed1.position == 5
        assert transformed2.position == 6

    def test_transform_insert_delete(self):
        """Test transforming insert and delete operations."""
        ot = OperationalTransform()

        op1 = EditOperation(
            type=EditOperationType.INSERT,
            path="/content",
            value="ABC",
            position=5,
            user_id="user-1",
            client_id="client-1",
            version=1,
        )
        op2 = EditOperation(
            type=EditOperationType.DELETE,
            path="/content",
            position=10,
            length=2,
            user_id="user-2",
            client_id="client-2",
            version=1,
        )

        transformed1, transformed2 = ot.transform_operations(op1, op2)

        # Insert is before delete, so delete position should increase
        assert transformed1.position == 5
        assert transformed2.position == 13  # 10 + 3 (length of ABC)

    def test_transform_delete_delete_non_overlapping(self):
        """Test transforming two non-overlapping delete operations."""
        ot = OperationalTransform()

        op1 = EditOperation(
            type=EditOperationType.DELETE,
            path="/content",
            position=5,
            length=2,
            user_id="user-1",
            client_id="client-1",
            version=1,
        )
        op2 = EditOperation(
            type=EditOperationType.DELETE,
            path="/content",
            position=10,
            length=2,
            user_id="user-2",
            client_id="client-2",
            version=1,
        )

        transformed1, transformed2 = ot.transform_operations(op1, op2)

        # op1 is before op2, so op2's position should decrease
        assert transformed1.position == 5
        assert transformed2.position == 8  # 10 - 2 (length of op1)

    def test_transform_different_paths_no_change(self):
        """Test that operations on different paths don't transform."""
        ot = OperationalTransform()

        op1 = EditOperation(
            type=EditOperationType.INSERT,
            path="/title",
            value="X",
            position=0,
            user_id="user-1",
            client_id="client-1",
            version=1,
        )
        op2 = EditOperation(
            type=EditOperationType.INSERT,
            path="/content",
            value="Y",
            position=0,
            user_id="user-2",
            client_id="client-2",
            version=1,
        )

        transformed1, transformed2 = ot.transform_operations(op1, op2)

        # No transformation needed for different paths
        assert transformed1.position == 0
        assert transformed2.position == 0


class TestSyncEngine:
    """Test SyncEngine."""

    @pytest.fixture
    async def sync_engine(self):
        engine = SyncEngine()
        await engine.initialize_document(
            "doc-123", {"title": "Test Document", "content": "Hello World"}
        )
        return engine

    async def test_initialize_document(self):
        engine = SyncEngine()
        await engine.initialize_document("doc-456", {"title": "New Doc", "items": []})

        doc = await engine.get_document("doc-456")
        assert doc["title"] == "New Doc"
        assert doc["items"] == []

    async def test_apply_set_property_operation(self, sync_engine):
        session = CollaborationSession(
            document_id="doc-123",
            document_type=DocumentType.POLICY,
            tenant_id="tenant-1",
        )

        op = EditOperation(
            type=EditOperationType.SET_PROPERTY,
            path="/title",
            value="Updated Title",
            user_id="user-1",
            client_id="client-1",
            version=1,
        )

        await sync_engine.apply_operation("doc-123", op, session)

        doc = await sync_engine.get_document("doc-123")
        assert doc["title"] == "Updated Title"
        assert session.version == 1

    async def test_apply_nested_set_property(self, sync_engine):
        session = CollaborationSession(
            document_id="doc-123",
            document_type=DocumentType.POLICY,
            tenant_id="tenant-1",
        )

        op = EditOperation(
            type=EditOperationType.SET_PROPERTY,
            path="/metadata/author",
            value="John Doe",
            user_id="user-1",
            client_id="client-1",
            version=1,
        )

        await sync_engine.apply_operation("doc-123", op, session)

        doc = await sync_engine.get_document("doc-123")
        assert doc["metadata"]["author"] == "John Doe"

    async def test_apply_delete_property(self, sync_engine):
        # First add a property
        session = CollaborationSession(
            document_id="doc-123",
            document_type=DocumentType.POLICY,
            tenant_id="tenant-1",
        )

        await sync_engine.apply_operation(
            "doc-123",
            EditOperation(
                type=EditOperationType.SET_PROPERTY,
                path="/temp",
                value="value",
                user_id="user-1",
                client_id="client-1",
                version=1,
            ),
            session,
        )

        # Now delete it
        await sync_engine.apply_operation(
            "doc-123",
            EditOperation(
                type=EditOperationType.DELETE_PROPERTY,
                path="/temp",
                user_id="user-1",
                client_id="client-1",
                version=2,
            ),
            session,
        )

        doc = await sync_engine.get_document("doc-123")
        assert "temp" not in doc

    async def test_get_operation_history(self, sync_engine):
        session = CollaborationSession(
            document_id="doc-123",
            document_type=DocumentType.POLICY,
            tenant_id="tenant-1",
        )

        # Apply multiple operations
        for i in range(5):
            op = EditOperation(
                type=EditOperationType.SET_PROPERTY,
                path=f"/prop{i}",
                value=f"value{i}",
                user_id="user-1",
                client_id="client-1",
                version=i + 1,
            )
            await sync_engine.apply_operation("doc-123", op, session)

        # Get history since version 2
        history = await sync_engine.get_operation_history("doc-123", since_version=2)
        assert len(history) == 3  # versions 3, 4, 5

    async def test_batch_apply_operations(self, sync_engine):
        session = CollaborationSession(
            document_id="doc-123",
            document_type=DocumentType.POLICY,
            tenant_id="tenant-1",
        )

        operations = [
            EditOperation(
                type=EditOperationType.SET_PROPERTY,
                path=f"/prop{i}",
                value=f"value{i}",
                user_id="user-1",
                client_id="client-1",
                version=i + 1,
            )
            for i in range(3)
        ]

        applied = await sync_engine.batch_apply_operations("doc-123", operations, session)

        assert len(applied) == 3

        doc = await sync_engine.get_document("doc-123")
        for i in range(3):
            assert doc[f"prop{i}"] == f"value{i}"

    async def test_undo_last_operation(self, sync_engine):
        session = CollaborationSession(
            document_id="doc-123",
            document_type=DocumentType.POLICY,
            tenant_id="tenant-1",
        )

        # Apply operation
        op = EditOperation(
            type=EditOperationType.SET_PROPERTY,
            path="/temp",
            value="original",
            user_id="user-1",
            client_id="client-1",
            version=1,
        )
        await sync_engine.apply_operation("doc-123", op, session)

        # Undo
        undone = await sync_engine.undo_last_operation("doc-123", session)
        assert undone is not None
        assert undone.operation_id == op.operation_id

        doc = await sync_engine.get_document("doc-123")
        assert "temp" not in doc

    async def test_undo_empty_history(self, sync_engine):
        session = CollaborationSession(
            document_id="doc-123",
            document_type=DocumentType.POLICY,
            tenant_id="tenant-1",
        )

        undone = await sync_engine.undo_last_operation("doc-123", session)
        assert undone is None


class TestSyncEngineConcurrency:
    """Test concurrent operations."""

    async def test_concurrent_edits_transformed(self):
        """Test that concurrent edits are properly transformed."""
        engine = SyncEngine()
        await engine.initialize_document("doc-concurrent", {"content": "ABCDEF"})

        session = CollaborationSession(
            document_id="doc-concurrent",
            document_type=DocumentType.POLICY,
            tenant_id="tenant-1",
        )

        # Simulate concurrent edits
        op1 = EditOperation(
            type=EditOperationType.INSERT,
            path="/content",
            value="X",
            position=3,
            user_id="user-1",
            client_id="client-1",
            version=1,
            timestamp=1000,
        )
        op2 = EditOperation(
            type=EditOperationType.INSERT,
            path="/content",
            value="Y",
            position=3,
            user_id="user-2",
            client_id="client-2",
            version=1,
            timestamp=1001,
        )

        # Apply both
        await engine.apply_operation("doc-concurrent", op1, session)
        await engine.apply_operation("doc-concurrent", op2, session)

        # Both should be in history
        history = await engine.get_operation_history("doc-concurrent")
        assert len(history) == 2
