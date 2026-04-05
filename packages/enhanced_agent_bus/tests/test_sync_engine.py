"""
Tests for collaboration/sync_engine.py - Operational Transform and SyncEngine.
"""

from __future__ import annotations

import pytest

from enhanced_agent_bus.collaboration.models import (
    CollaborationSession,
    CollaborationValidationError,
    ConflictError,
    DocumentType,
    EditOperation,
    EditOperationType,
)
from enhanced_agent_bus.collaboration.sync_engine import (
    OperationalTransform,
    SyncEngine,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _op(
    op_type: EditOperationType,
    path: str = "/content",
    *,
    value=None,
    old_value=None,
    position: int | None = None,
    length: int | None = None,
    timestamp: float = 1.0,
    version: int = 1,
    user_id: str = "user1",
    client_id: str = "client1",
    parent_version: int | None = None,
) -> EditOperation:
    return EditOperation(
        type=op_type,
        path=path,
        value=value,
        old_value=old_value,
        position=position,
        length=length,
        timestamp=timestamp,
        user_id=user_id,
        client_id=client_id,
        version=version,
        parent_version=parent_version,
    )


def _session(document_id: str = "doc1") -> CollaborationSession:
    return CollaborationSession(
        document_id=document_id,
        document_type=DocumentType.POLICY,
        tenant_id="t1",
    )


# ===========================================================================
# OperationalTransform unit tests
# ===========================================================================


class TestOperationalTransform:
    """Unit tests for OperationalTransform static methods."""

    def test_different_paths_no_transform(self):
        op1 = _op(EditOperationType.INSERT, "/a", position=0, value="x")
        op2 = _op(EditOperationType.INSERT, "/b", position=0, value="y")
        t1, t2 = OperationalTransform.transform_operations(op1, op2)
        assert t1.position == 0
        assert t2.position == 0

    # -- insert / insert ---------------------------------------------------

    def test_insert_insert_op1_before_op2(self):
        op1 = _op(EditOperationType.INSERT, position=2, value="ab", timestamp=1.0)
        op2 = _op(EditOperationType.INSERT, position=5, value="c", timestamp=2.0)
        t1, t2 = OperationalTransform.transform_operations(op1, op2)
        assert t1.position == 2
        assert t2.position == 5 + len("ab")

    def test_insert_insert_op2_before_op1(self):
        op1 = _op(EditOperationType.INSERT, position=5, value="a", timestamp=1.0)
        op2 = _op(EditOperationType.INSERT, position=2, value="xyz", timestamp=2.0)
        t1, t2 = OperationalTransform.transform_operations(op1, op2)
        assert t1.position == 5 + len("xyz")
        assert t2.position == 2

    def test_insert_insert_same_position_tie_break_by_timestamp(self):
        op1 = _op(EditOperationType.INSERT, position=3, value="a", timestamp=1.0)
        op2 = _op(EditOperationType.INSERT, position=3, value="b", timestamp=2.0)
        t1, t2 = OperationalTransform.transform_operations(op1, op2)
        # op1.timestamp <= op2.timestamp => op2 shifts
        assert t1.position == 3
        assert t2.position == 3 + len("a")

    def test_insert_insert_none_positions(self):
        op1 = _op(EditOperationType.INSERT, position=None, value="a")
        op2 = _op(EditOperationType.INSERT, position=5, value="b")
        t1, t2 = OperationalTransform.transform_operations(op1, op2)
        assert t1.position is None
        assert t2.position == 5

    # -- insert / delete ---------------------------------------------------

    def test_insert_delete(self):
        op1 = _op(EditOperationType.INSERT, position=2, value="ab")
        op2 = _op(EditOperationType.DELETE, position=5, length=3)
        t1, t2 = OperationalTransform.transform_operations(op1, op2)
        # insert before delete => delete shifts by len("ab") = 2
        assert t2.position == 5 + 2

    def test_delete_insert(self):
        """Delete before insert is handled via the swap path."""
        op1 = _op(EditOperationType.DELETE, position=2, length=3)
        op2 = _op(EditOperationType.INSERT, position=5, value="x")
        t1, t2 = OperationalTransform.transform_operations(op1, op2)
        # insert at 5, delete at 2 with len 3 => insert adjusts to max(0, 5-3)=2
        assert t2.position == 2

    # -- delete / delete ---------------------------------------------------

    def test_delete_delete_non_overlapping_op1_first(self):
        op1 = _op(EditOperationType.DELETE, position=0, length=2)
        op2 = _op(EditOperationType.DELETE, position=5, length=3)
        t1, t2 = OperationalTransform.transform_operations(op1, op2)
        assert t2.position == 5 - 2

    def test_delete_delete_overlapping(self):
        op1 = _op(EditOperationType.DELETE, position=3, length=5)
        op2 = _op(EditOperationType.DELETE, position=5, length=4)
        t1, t2 = OperationalTransform.transform_operations(op1, op2)
        # overlap: max(3,5)=5, min(8,9)=8 => overlap_len=3
        assert t1.length == 5 - 3
        assert t2.length == 4 - 3

    # -- replace -----------------------------------------------------------

    def test_replace_last_write_wins(self):
        op1 = _op(EditOperationType.REPLACE, value="new1", timestamp=1.0)
        op2 = _op(EditOperationType.REPLACE, value="new2", timestamp=2.0)
        t1, t2 = OperationalTransform.transform_operations(op1, op2)
        # op2 is newer => op1 becomes no-op
        assert t1.value is None

    def test_replace_vs_insert(self):
        op1 = _op(EditOperationType.INSERT, position=0, value="x", timestamp=1.0)
        op2 = _op(EditOperationType.REPLACE, value="full", timestamp=2.0)
        t1, t2 = OperationalTransform.transform_operations(op1, op2)
        # replace wins, op1 becomes no-op
        assert t1.value is None

    # -- default fallthrough -----------------------------------------------

    def test_default_passthrough_move(self):
        op1 = _op(EditOperationType.MOVE, value="/dest")
        op2 = _op(EditOperationType.MOVE, value="/dest2")
        t1, t2 = OperationalTransform.transform_operations(op1, op2)
        assert t1.value == "/dest"
        assert t2.value == "/dest2"


# ===========================================================================
# SyncEngine unit tests
# ===========================================================================


class TestSyncEngine:
    """Unit tests for SyncEngine document operations."""

    @pytest.fixture
    def engine(self):
        return SyncEngine(redis_client=None)

    @pytest.fixture
    def session(self):
        return _session()

    @pytest.mark.asyncio
    async def test_initialize_and_get_document(self, engine, session):
        await engine.initialize_document("doc1", {"title": "Test"})
        doc = await engine.get_document("doc1")
        assert doc == {"title": "Test"}

    @pytest.mark.asyncio
    async def test_get_missing_document_returns_none(self, engine):
        assert await engine.get_document("nope") is None

    @pytest.mark.asyncio
    async def test_apply_set_property(self, engine, session):
        await engine.initialize_document("doc1", {"title": "Old"})
        op = _op(EditOperationType.SET_PROPERTY, "/title", value="New", version=0)
        result = await engine.apply_operation("doc1", op, session)
        doc = await engine.get_document("doc1")
        assert doc["title"] == "New"
        assert session.version == 1
        assert result.version == 1

    @pytest.mark.asyncio
    async def test_apply_delete_property(self, engine, session):
        await engine.initialize_document("doc1", {"a": 1, "b": 2})
        op = _op(EditOperationType.DELETE_PROPERTY, "/a", version=0)
        await engine.apply_operation("doc1", op, session)
        doc = await engine.get_document("doc1")
        assert "a" not in doc
        assert doc["b"] == 2

    @pytest.mark.asyncio
    async def test_apply_insert_to_list(self, engine, session):
        await engine.initialize_document("doc1", {"items": [1, 2, 3]})
        op = _op(EditOperationType.INSERT, "/items", value=99, position=1, version=0)
        await engine.apply_operation("doc1", op, session)
        doc = await engine.get_document("doc1")
        assert doc["items"] == [1, 99, 2, 3]

    @pytest.mark.asyncio
    async def test_apply_delete_from_list(self, engine, session):
        await engine.initialize_document("doc1", {"items": ["a", "b", "c", "d"]})
        op = _op(EditOperationType.DELETE, "/items", position=1, length=2, version=0)
        await engine.apply_operation("doc1", op, session)
        doc = await engine.get_document("doc1")
        assert doc["items"] == ["a", "d"]

    @pytest.mark.asyncio
    async def test_apply_replace(self, engine, session):
        await engine.initialize_document("doc1", {"x": "old"})
        op = _op(EditOperationType.REPLACE, "/x", value="replaced", version=0)
        await engine.apply_operation("doc1", op, session)
        doc = await engine.get_document("doc1")
        assert doc["x"] == "replaced"

    @pytest.mark.asyncio
    async def test_apply_move(self, engine, session):
        await engine.initialize_document("doc1", {"src": "val", "dst": None})
        op = _op(EditOperationType.MOVE, "/src", value="/dst", version=0)
        await engine.apply_operation("doc1", op, session)
        doc = await engine.get_document("doc1")
        assert "src" not in doc
        assert doc["dst"] == "val"

    @pytest.mark.asyncio
    async def test_apply_operation_document_not_found(self, engine, session):
        op = _op(EditOperationType.SET_PROPERTY, "/x", value=1, version=0)
        with pytest.raises(CollaborationValidationError, match="not found"):
            await engine.apply_operation("nope", op, session)

    @pytest.mark.asyncio
    async def test_batch_apply(self, engine, session):
        await engine.initialize_document("doc1", {"a": 0, "b": 0})
        ops = [
            _op(EditOperationType.SET_PROPERTY, "/a", value=1, version=0),
            _op(EditOperationType.SET_PROPERTY, "/b", value=2, version=0),
        ]
        applied = await engine.batch_apply_operations("doc1", ops, session)
        assert len(applied) == 2
        doc = await engine.get_document("doc1")
        assert doc["a"] == 1
        assert doc["b"] == 2

    @pytest.mark.asyncio
    async def test_undo_last_operation(self, engine, session):
        await engine.initialize_document("doc1", {"x": "original"})
        op = _op(
            EditOperationType.SET_PROPERTY,
            "/x",
            value="changed",
            old_value="original",
            version=0,
        )
        await engine.apply_operation("doc1", op, session)
        undone = await engine.undo_last_operation("doc1", session)
        assert undone is not None
        doc = await engine.get_document("doc1")
        assert doc["x"] == "original"

    @pytest.mark.asyncio
    async def test_undo_empty_history(self, engine, session):
        await engine.initialize_document("doc1", {})
        result = await engine.undo_last_operation("doc1", session)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_operation_history(self, engine, session):
        await engine.initialize_document("doc1", {"a": 0})
        ops = [_op(EditOperationType.SET_PROPERTY, "/a", value=i, version=0) for i in range(5)]
        for o in ops:
            await engine.apply_operation("doc1", o, session)

        history = await engine.get_operation_history("doc1", since_version=3)
        assert all(op.version > 3 for op in history)

    @pytest.mark.asyncio
    async def test_compact_history(self, engine, session):
        await engine.initialize_document("doc1", {"x": 0})
        for i in range(120):
            op = _op(EditOperationType.SET_PROPERTY, "/x", value=i, version=0)
            await engine.apply_operation("doc1", op, session)

        await engine.compact_history("doc1")
        assert len(engine._operation_history["doc1"]) == 50

    @pytest.mark.asyncio
    async def test_compact_history_noop_for_missing_doc(self, engine):
        await engine.compact_history("nonexistent")  # should not raise

    @pytest.mark.asyncio
    async def test_set_property_nested_creates_path(self, engine, session):
        await engine.initialize_document("doc1", {})
        op = _op(EditOperationType.SET_PROPERTY, "/deep/nested/key", value="val", version=0)
        await engine.apply_operation("doc1", op, session)
        doc = await engine.get_document("doc1")
        assert doc["deep"]["nested"]["key"] == "val"

    @pytest.mark.asyncio
    async def test_delete_property_missing_path(self, engine, session):
        await engine.initialize_document("doc1", {"a": 1})
        op = _op(EditOperationType.DELETE_PROPERTY, "/nonexistent/path", version=0)
        await engine.apply_operation("doc1", op, session)
        doc = await engine.get_document("doc1")
        assert doc == {"a": 1}

    @pytest.mark.asyncio
    async def test_insert_into_dict(self, engine, session):
        await engine.initialize_document("doc1", {"items": {}})
        op = _op(
            EditOperationType.INSERT,
            "/items",
            value={"key": "mykey", "value": 42},
            position=None,
            version=0,
        )
        await engine.apply_operation("doc1", op, session)
        doc = await engine.get_document("doc1")
        assert doc["items"]["mykey"] == 42

    @pytest.mark.asyncio
    async def test_move_with_dict_target(self, engine, session):
        await engine.initialize_document("doc1", {"src": "val"})
        op = _op(
            EditOperationType.MOVE,
            "/src",
            value={"path": "/dest"},
            version=0,
        )
        await engine.apply_operation("doc1", op, session)
        doc = await engine.get_document("doc1")
        assert doc.get("dest") == "val"


# ===========================================================================
# Inverse operation coverage
# ===========================================================================


class TestCreateInverseOperation:
    """Tests for _create_inverse_operation covering all branches."""

    def setup_method(self):
        self.engine = SyncEngine()

    def test_inverse_of_insert(self):
        op = _op(EditOperationType.INSERT, value="hello", position=3, version=1)
        inv = self.engine._create_inverse_operation(op)
        assert inv.type == EditOperationType.DELETE
        assert inv.length == len("hello")

    def test_inverse_of_delete(self):
        op = _op(EditOperationType.DELETE, position=3, length=5, old_value="chunk", version=1)
        inv = self.engine._create_inverse_operation(op)
        assert inv.type == EditOperationType.INSERT
        assert inv.value == "chunk"

    def test_inverse_of_set_property_with_old_value(self):
        op = _op(EditOperationType.SET_PROPERTY, value="new", old_value="old", version=1)
        inv = self.engine._create_inverse_operation(op)
        assert inv.type == EditOperationType.SET_PROPERTY
        assert inv.value == "old"

    def test_inverse_of_set_property_without_old_value(self):
        op = _op(EditOperationType.SET_PROPERTY, value="new", version=1)
        inv = self.engine._create_inverse_operation(op)
        assert inv.type == EditOperationType.DELETE_PROPERTY

    def test_inverse_of_replace(self):
        op = _op(EditOperationType.REPLACE, value="new", old_value="old", version=1)
        inv = self.engine._create_inverse_operation(op)
        assert inv.type == EditOperationType.REPLACE
        assert inv.value == "old"

    def test_inverse_of_move_returns_same(self):
        op = _op(EditOperationType.MOVE, value="/target", version=1)
        inv = self.engine._create_inverse_operation(op)
        assert inv.type == EditOperationType.MOVE
