"""
Additional coverage tests for SyncEngine and OperationalTransform.

Targets branches not covered by test_sync_engine.py to reach ≥90% coverage.
Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from copy import deepcopy
from unittest.mock import AsyncMock, MagicMock, patch

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


def make_op(
    op_type: EditOperationType,
    path: str = "/content",
    value=None,
    position: int | None = None,
    length: int | None = None,
    version: int = 1,
    timestamp: float = 1000.0,
    parent_version: int | None = None,
    old_value=None,
    user_id: str = "user-1",
    client_id: str = "client-1",
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


def make_session(doc_id: str = "doc-1") -> CollaborationSession:
    return CollaborationSession(
        document_id=doc_id,
        document_type=DocumentType.POLICY,
        tenant_id="tenant-1",
    )


# ---------------------------------------------------------------------------
# OperationalTransform - edge cases
# ---------------------------------------------------------------------------


class TestOperationalTransformEdgeCases:
    """Cover branches in OperationalTransform not hit by existing tests."""

    # ----- _transform_insert_insert -----

    def test_insert_insert_none_positions(self):
        """Both positions None → returns originals unchanged."""
        op1 = make_op(EditOperationType.INSERT, position=None)
        op2 = make_op(EditOperationType.INSERT, position=None)
        r1, r2 = OperationalTransform.transform_operations(op1, op2)
        assert r1 is op1
        assert r2 is op2

    def test_insert_insert_op1_none_position(self):
        """op1 position None, op2 has position → unchanged."""
        op1 = make_op(EditOperationType.INSERT, position=None)
        op2 = make_op(EditOperationType.INSERT, position=5)
        r1, r2 = OperationalTransform.transform_operations(op1, op2)
        assert r1 is op1
        assert r2 is op2

    def test_insert_insert_op2_before_op1(self):
        """op2.position < op1.position → op1 position increases."""
        op1 = make_op(EditOperationType.INSERT, position=10, value="AB")
        op2 = make_op(EditOperationType.INSERT, position=5, value="X")
        r1, r2 = OperationalTransform.transform_operations(op1, op2)
        # op2 is before op1 → op1 position should increase by len("X")=1
        assert r1.position == 11
        assert r2.position == 5

    def test_insert_insert_same_position_op1_wins(self):
        """op1.timestamp < op2.timestamp at same position → op2 shifts."""
        op1 = make_op(EditOperationType.INSERT, position=5, value="AB", timestamp=500.0)
        op2 = make_op(EditOperationType.INSERT, position=5, value="X", timestamp=600.0)
        r1, r2 = OperationalTransform.transform_operations(op1, op2)
        assert r1.position == 5
        # op1 wins (earlier), op2 shifts by len("AB")=2
        assert r2.position == 7

    def test_insert_insert_same_position_op2_wins(self):
        """op2.timestamp < op1.timestamp at same position → op1 shifts."""
        op1 = make_op(EditOperationType.INSERT, position=5, value="X", timestamp=600.0)
        op2 = make_op(EditOperationType.INSERT, position=5, value="AB", timestamp=500.0)
        r1, r2 = OperationalTransform.transform_operations(op1, op2)
        # op2 wins (earlier), op1 shifts by len("AB")=2
        assert r1.position == 7
        assert r2.position == 5

    def test_insert_insert_none_value_uses_length_1(self):
        """None value → uses 1 as length for position adjustment."""
        op1 = make_op(EditOperationType.INSERT, position=3, value=None)
        op2 = make_op(EditOperationType.INSERT, position=5, value=None)
        _r1, r2 = OperationalTransform.transform_operations(op1, op2)
        # op1 before op2, value=None → length 1
        assert r2.position == 6

    # ----- _transform_insert_delete -----

    def test_insert_delete_none_positions(self):
        """None positions → return unchanged."""
        op1 = make_op(EditOperationType.INSERT, position=None)
        op2 = make_op(EditOperationType.DELETE, position=None)
        r1, r2 = OperationalTransform.transform_operations(op1, op2)
        assert r1 is op1
        assert r2 is op2

    def test_insert_delete_delete_before_insert(self):
        """Delete is before insert → insert position decreases."""
        op1 = make_op(EditOperationType.INSERT, position=10, value="ABC")
        op2 = make_op(EditOperationType.DELETE, position=3, length=2)
        r1, r2 = OperationalTransform.transform_operations(op1, op2)
        # delete before insert → insert shrinks by length 2
        assert r1.position == max(0, 10 - 2)
        assert r2.position == 3

    def test_insert_delete_delete_before_insert_length_none(self):
        """Delete with None length defaults to 1."""
        op1 = make_op(EditOperationType.INSERT, position=10)
        op2 = make_op(EditOperationType.DELETE, position=3, length=None)
        r1, _r2 = OperationalTransform.transform_operations(op1, op2)
        assert r1.position == 9  # 10 - 1

    def test_delete_insert_transform(self):
        """DELETE op1, INSERT op2 → delegates to _transform_insert_delete."""
        op1 = make_op(EditOperationType.DELETE, position=3, length=2)
        op2 = make_op(EditOperationType.INSERT, position=10, value="ABC")
        r1, r2 = OperationalTransform.transform_operations(op1, op2)
        # The engine calls _transform_insert_delete(op2, op1) and swaps
        # op2 insert at 10, op1 delete at 3 (before insert) → op2 doesn't change; op1 stays
        assert r1 is not None
        assert r2 is not None

    # ----- _transform_delete_delete -----

    def test_delete_delete_none_positions(self):
        """None positions → return unchanged."""
        op1 = make_op(EditOperationType.DELETE, position=None)
        op2 = make_op(EditOperationType.DELETE, position=None)
        r1, r2 = OperationalTransform.transform_operations(op1, op2)
        assert r1 is op1
        assert r2 is op2

    def test_delete_delete_op2_entirely_before_op1(self):
        """op2 entirely before op1 → op1 position decreases."""
        op1 = make_op(EditOperationType.DELETE, position=10, length=3)
        op2 = make_op(EditOperationType.DELETE, position=2, length=4)
        r1, r2 = OperationalTransform.transform_operations(op1, op2)
        # op2 at 2..6, op1 at 10..13 → op2 is entirely before op1
        assert r1.position == 10 - 4
        assert r2.position == 2

    def test_delete_delete_overlapping(self):
        """Overlapping deletes → lengths reduced by overlap."""
        op1 = make_op(EditOperationType.DELETE, position=5, length=5)
        op2 = make_op(EditOperationType.DELETE, position=8, length=5)
        r1, r2 = OperationalTransform.transform_operations(op1, op2)
        # overlap: max(5,8)=8 to min(10,13)=10 → overlap_len=2
        assert r1.length == 3  # 5 - 2
        assert r2.length == 3  # 5 - 2

    def test_delete_delete_none_lengths_default_to_1(self):
        """None lengths default to 1 in delete-delete transform."""
        op1 = make_op(EditOperationType.DELETE, position=2, length=None)
        op2 = make_op(EditOperationType.DELETE, position=10, length=None)
        _r1, r2 = OperationalTransform.transform_operations(op1, op2)
        # op1 at 2..3, op2 at 10..11 → op1 entirely before op2
        assert r2.position == 9  # 10 - 1

    # ----- _transform_replace -----

    def test_replace_op1_newer(self):
        """op1 newer than op2 → op2 becomes no-op insert."""
        op1 = make_op(EditOperationType.REPLACE, timestamp=2000.0, value="new")
        op2 = make_op(EditOperationType.REPLACE, timestamp=1000.0, value="old")
        r1, r2 = OperationalTransform.transform_operations(op1, op2)
        assert r1.value == "new"
        assert r2.type == EditOperationType.INSERT
        assert r2.value is None

    def test_replace_op2_newer_or_equal(self):
        """op2 newer than op1 → op1 becomes no-op insert."""
        op1 = make_op(EditOperationType.REPLACE, timestamp=1000.0, value="old")
        op2 = make_op(EditOperationType.REPLACE, timestamp=2000.0, value="new")
        r1, r2 = OperationalTransform.transform_operations(op1, op2)
        assert r1.type == EditOperationType.INSERT
        assert r1.value is None
        assert r2.value == "new"

    def test_replace_mixed_op1_replace_op2_insert(self):
        """op1 REPLACE, op2 INSERT → _transform_replace called."""
        op1 = make_op(EditOperationType.REPLACE, timestamp=1000.0)
        op2 = make_op(EditOperationType.INSERT, timestamp=2000.0)
        r1, _r2 = OperationalTransform.transform_operations(op1, op2)
        # op1 timestamp <= op2 timestamp → op1 becomes no-op
        assert r1.type == EditOperationType.INSERT
        assert r1.value is None

    def test_replace_mixed_op1_insert_op2_replace(self):
        """op1 INSERT, op2 REPLACE → _transform_replace called."""
        op1 = make_op(EditOperationType.INSERT, timestamp=1000.0)
        op2 = make_op(EditOperationType.REPLACE, timestamp=2000.0)
        r1, _r2 = OperationalTransform.transform_operations(op1, op2)
        assert r1 is not None

    def test_transform_unhandled_falls_through(self):
        """Operations with unhandled type combos return unchanged."""
        op1 = make_op(EditOperationType.MOVE, path="/a")
        op2 = make_op(EditOperationType.MOVE, path="/a")
        r1, r2 = OperationalTransform.transform_operations(op1, op2)
        assert r1 is op1
        assert r2 is op2


# ---------------------------------------------------------------------------
# SyncEngine - document management
# ---------------------------------------------------------------------------


class TestSyncEngineDocumentManagement:
    """Covers initialize_document, get_document with and without Redis."""

    async def test_initialize_document_with_redis(self):
        """initialize_document persists to Redis when redis client provided."""
        redis = AsyncMock()
        engine = SyncEngine(redis_client=redis)
        await engine.initialize_document("doc-r", {"k": "v"})
        redis.set.assert_called_once()
        key, _ = redis.set.call_args[0]
        assert "doc-r" in key

    async def test_get_document_not_found_no_redis(self):
        """get_document returns None when doc missing and no redis."""
        engine = SyncEngine()
        result = await engine.get_document("nonexistent")
        assert result is None

    async def test_get_document_not_found_with_redis_hit(self):
        """get_document loads from Redis when not in memory."""
        import json

        redis = AsyncMock()
        redis.get = AsyncMock(return_value=json.dumps({"loaded": True}))
        engine = SyncEngine(redis_client=redis)
        result = await engine.get_document("redis-doc")
        assert result == {"loaded": True}

    async def test_get_document_not_found_redis_miss(self):
        """get_document returns None when Redis also has no data."""
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        engine = SyncEngine(redis_client=redis)
        result = await engine.get_document("missing-doc")
        assert result is None

    async def test_get_document_returns_deep_copy(self):
        """Mutating returned doc doesn't affect stored doc."""
        engine = SyncEngine()
        await engine.initialize_document("doc-copy", {"a": 1})
        doc = await engine.get_document("doc-copy")
        doc["a"] = 999
        doc2 = await engine.get_document("doc-copy")
        assert doc2["a"] == 1


# ---------------------------------------------------------------------------
# SyncEngine - apply_operation
# ---------------------------------------------------------------------------


class TestSyncEngineApplyOperation:
    """Tests for apply_operation including error paths."""

    async def test_apply_operation_document_not_found_raises(self):
        """apply_operation raises CollaborationValidationError for missing doc."""
        engine = SyncEngine()
        session = make_session("nonexistent")
        op = make_op(EditOperationType.SET_PROPERTY, path="/x", value=1)
        with pytest.raises(CollaborationValidationError, match="not found"):
            await engine.apply_operation("nonexistent", op, session)

    async def test_apply_operation_persists_via_redis(self):
        """apply_operation calls _persist_operation when redis is present."""
        redis = AsyncMock()
        engine = SyncEngine(redis_client=redis)
        await engine.initialize_document("doc-redis", {"x": 0})
        session = make_session("doc-redis")
        op = make_op(EditOperationType.SET_PROPERTY, path="/x", value=42)
        await engine.apply_operation("doc-redis", op, session)
        redis.lpush.assert_called()

    async def test_apply_operation_conflict_error_raised(self):
        """apply_operation raises ConflictError when _apply_to_document fails."""
        engine = SyncEngine()
        await engine.initialize_document("doc-fail", {"items": [1, 2, 3]})
        session = make_session("doc-fail")

        with patch.object(engine, "_apply_to_document", side_effect=RuntimeError("boom")):
            op = make_op(EditOperationType.INSERT, path="/items", position=0, value="x")
            with pytest.raises(ConflictError, match="Failed to apply"):
                await engine.apply_operation("doc-fail", op, session)

    async def test_apply_operation_increments_session_version(self):
        """apply_operation increments session.version."""
        engine = SyncEngine()
        await engine.initialize_document("doc-v", {"a": 1})
        session = make_session("doc-v")
        assert session.version == 0
        op = make_op(EditOperationType.SET_PROPERTY, path="/a", value=2)
        await engine.apply_operation("doc-v", op, session)
        assert session.version == 1

    async def test_apply_operation_with_concurrent_history(self):
        """Concurrent ops in history are transformed against incoming op."""
        engine = SyncEngine()
        await engine.initialize_document("doc-hist", {"content": "ABC"})
        session = make_session("doc-hist")

        # Apply op1 first so it's in history
        op1 = make_op(
            EditOperationType.INSERT,
            path="/content",
            value="X",
            position=0,
            version=1,
            parent_version=0,
        )
        await engine.apply_operation("doc-hist", op1, session)

        # Apply op2 with parent_version=0 (concurrent with op1)
        op2 = make_op(
            EditOperationType.INSERT,
            path="/content",
            value="Y",
            position=0,
            version=1,
            parent_version=0,
        )
        await engine.apply_operation("doc-hist", op2, session)
        assert session.version == 2

    async def test_apply_replace_operation(self):
        """REPLACE operation calls _set_property."""
        engine = SyncEngine()
        await engine.initialize_document("doc-rep", {"field": "old"})
        session = make_session("doc-rep")
        op = make_op(EditOperationType.REPLACE, path="/field", value="new")
        await engine.apply_operation("doc-rep", op, session)
        doc = await engine.get_document("doc-rep")
        assert doc["field"] == "new"

    async def test_apply_move_operation_str_destination(self):
        """MOVE operation with string destination path."""
        engine = SyncEngine()
        await engine.initialize_document("doc-mv", {"src": "val", "dst": None})
        session = make_session("doc-mv")
        op = make_op(EditOperationType.MOVE, path="/src", value="/dst")
        await engine.apply_operation("doc-mv", op, session)
        doc = await engine.get_document("doc-mv")
        assert doc.get("dst") == "val"
        assert "src" not in doc

    async def test_apply_move_operation_dict_destination(self):
        """MOVE operation with dict destination (with 'path' key)."""
        engine = SyncEngine()
        await engine.initialize_document("doc-mv2", {"src": "hello"})
        session = make_session("doc-mv2")
        op = make_op(EditOperationType.MOVE, path="/src", value={"path": "/target"})
        await engine.apply_operation("doc-mv2", op, session)
        doc = await engine.get_document("doc-mv2")
        assert doc.get("target") == "hello"

    async def test_apply_insert_into_list(self):
        """INSERT operation inserts into a list at position."""
        engine = SyncEngine()
        await engine.initialize_document("doc-ins", {"items": ["a", "b", "c"]})
        session = make_session("doc-ins")
        op = make_op(EditOperationType.INSERT, path="/items", position=1, value="X")
        await engine.apply_operation("doc-ins", op, session)
        doc = await engine.get_document("doc-ins")
        assert doc["items"][1] == "X"

    async def test_apply_insert_into_nonexistent_path_creates_list(self):
        """INSERT creates missing intermediate path as list."""
        engine = SyncEngine()
        await engine.initialize_document("doc-ins2", {})
        session = make_session("doc-ins2")
        op = make_op(EditOperationType.INSERT, path="/new_list", position=0, value="first")
        await engine.apply_operation("doc-ins2", op, session)
        doc = await engine.get_document("doc-ins2")
        assert doc["new_list"][0] == "first"

    async def test_apply_insert_into_dict_with_key(self):
        """INSERT into a dict with value containing 'key' field."""
        engine = SyncEngine()
        await engine.initialize_document("doc-ins3", {"mapping": {}})
        session = make_session("doc-ins3")
        op = make_op(
            EditOperationType.INSERT,
            path="/mapping",
            position=None,
            value={"key": "mykey", "value": "myval"},
        )
        await engine.apply_operation("doc-ins3", op, session)
        doc = await engine.get_document("doc-ins3")
        assert doc["mapping"]["mykey"] == "myval"

    async def test_apply_insert_into_dict_without_key(self):
        """INSERT into a dict without 'key' uses str(len) as key."""
        engine = SyncEngine()
        await engine.initialize_document("doc-ins4", {"mapping": {}})
        session = make_session("doc-ins4")
        op = make_op(
            EditOperationType.INSERT,
            path="/mapping",
            position=None,
            value="plain_value",
        )
        await engine.apply_operation("doc-ins4", op, session)
        doc = await engine.get_document("doc-ins4")
        assert "0" in doc["mapping"]

    async def test_apply_insert_beyond_list_end(self):
        """INSERT at position beyond list length appends to end."""
        engine = SyncEngine()
        await engine.initialize_document("doc-ins5", {"items": ["a", "b"]})
        session = make_session("doc-ins5")
        op = make_op(EditOperationType.INSERT, path="/items", position=999, value="end")
        await engine.apply_operation("doc-ins5", op, session)
        doc = await engine.get_document("doc-ins5")
        assert doc["items"][-1] == "end"

    async def test_apply_delete_from_list(self):
        """DELETE removes items from a list."""
        engine = SyncEngine()
        await engine.initialize_document("doc-del", {"items": ["a", "b", "c", "d"]})
        session = make_session("doc-del")
        op = make_op(EditOperationType.DELETE, path="/items", position=1, length=2)
        await engine.apply_operation("doc-del", op, session)
        doc = await engine.get_document("doc-del")
        assert doc["items"] == ["a", "d"]

    async def test_apply_delete_beyond_list_bounds(self):
        """DELETE at position beyond list length does nothing."""
        engine = SyncEngine()
        await engine.initialize_document("doc-del2", {"items": ["a"]})
        session = make_session("doc-del2")
        op = make_op(EditOperationType.DELETE, path="/items", position=5, length=1)
        await engine.apply_operation("doc-del2", op, session)
        doc = await engine.get_document("doc-del2")
        assert doc["items"] == ["a"]

    async def test_apply_delete_from_missing_path(self):
        """DELETE on a missing path does nothing."""
        engine = SyncEngine()
        await engine.initialize_document("doc-del3", {})
        session = make_session("doc-del3")
        op = make_op(EditOperationType.DELETE, path="/missing/path", position=0, length=1)
        await engine.apply_operation("doc-del3", op, session)
        doc = await engine.get_document("doc-del3")
        assert doc == {}

    async def test_apply_delete_property_missing_path(self):
        """DELETE_PROPERTY on missing path does nothing."""
        engine = SyncEngine()
        await engine.initialize_document("doc-delp", {"a": 1})
        session = make_session("doc-delp")
        op = make_op(EditOperationType.DELETE_PROPERTY, path="/missing/nested")
        await engine.apply_operation("doc-delp", op, session)
        doc = await engine.get_document("doc-delp")
        assert doc["a"] == 1

    async def test_apply_delete_property_missing_key(self):
        """DELETE_PROPERTY when the key doesn't exist in parent is a no-op."""
        engine = SyncEngine()
        await engine.initialize_document("doc-delp2", {"a": 1})
        session = make_session("doc-delp2")
        op = make_op(EditOperationType.DELETE_PROPERTY, path="/nonexistent")
        await engine.apply_operation("doc-delp2", op, session)
        doc = await engine.get_document("doc-delp2")
        assert doc == {"a": 1}


# ---------------------------------------------------------------------------
# SyncEngine - _set_property / _get_property
# ---------------------------------------------------------------------------


class TestSyncEnginePropertyHelpers:
    """Unit-level tests for property manipulation helpers."""

    def test_set_property_root_level(self):
        engine = SyncEngine()
        doc = {}
        engine._set_property(doc, "/key", "value")
        assert doc["key"] == "value"

    def test_set_property_nested_creates_intermediate(self):
        engine = SyncEngine()
        doc = {}
        engine._set_property(doc, "/a/b/c", 42)
        assert doc["a"]["b"]["c"] == 42

    def test_get_property_missing_key_returns_none(self):
        engine = SyncEngine()
        doc = {"a": {"b": 1}}
        result = engine._get_property(doc, "/a/x")
        assert result is None

    def test_get_property_existing_key(self):
        engine = SyncEngine()
        doc = {"a": {"b": 5}}
        assert engine._get_property(doc, "/a/b") == 5

    def test_move_property_dict_without_path_key(self):
        """_move_property with dict destination missing 'path' key does nothing to destination."""
        engine = SyncEngine()
        doc = {"src": "value"}
        engine._move_property(doc, "/src", {"no_path": "here"})
        # src deleted, but no destination set
        assert "src" not in doc

    def test_set_property_existing_intermediate_key(self):
        """_set_property traverses existing intermediate keys without creating new ones."""
        engine = SyncEngine()
        doc = {"a": {"b": {"old": 1}}}
        engine._set_property(doc, "/a/b/new", 42)
        assert doc["a"]["b"]["new"] == 42
        assert doc["a"]["b"]["old"] == 1

    def test_set_property_empty_path(self):
        """_set_property with root path '/' splits to ['', ''] but sets last part."""
        engine = SyncEngine()
        doc = {}
        # path "/" splits to ["", ""] after strip → parts[-1] = ""
        engine._set_property(doc, "/", "value")
        # should set doc[""] = "value"
        assert doc.get("") == "value"

    def test_delete_at_path_target_is_not_list(self):
        """_delete_at_path when target is a dict (not list) does nothing."""
        engine = SyncEngine()
        doc = {"data": {"key": "value"}}
        # Navigate to "data" which is a dict, then position-based delete is ignored
        engine._delete_at_path(doc, "/data", position=0, length=1)
        # Should not raise; dict is unchanged
        assert doc["data"] == {"key": "value"}

    def test_delete_at_path_position_none_on_list(self):
        """_delete_at_path with position=None on a list does nothing."""
        engine = SyncEngine()
        doc = {"items": ["a", "b"]}
        engine._delete_at_path(doc, "/items", position=None, length=1)
        assert doc["items"] == ["a", "b"]


# ---------------------------------------------------------------------------
# SyncEngine - undo_last_operation
# ---------------------------------------------------------------------------


class TestSyncEngineUndo:
    """Cover undo branches."""

    async def test_undo_with_redis_persists(self):
        """undo_last_operation persists to redis when available."""
        redis = AsyncMock()
        engine = SyncEngine(redis_client=redis)
        # Keep a second key so the doc stays non-empty after undo
        await engine.initialize_document("doc-undo", {"x": "old", "other": "keep"})
        session = make_session("doc-undo")

        op = make_op(EditOperationType.SET_PROPERTY, path="/x", value="new", old_value="old")
        await engine.apply_operation("doc-undo", op, session)

        # Reset call count after initialization + apply
        redis.set.reset_mock()
        await engine.undo_last_operation("doc-undo", session)
        # After undo, _persist_to_redis is called if doc is non-empty (truthy)
        redis.set.assert_called()

    async def test_undo_insert_creates_delete_inverse(self):
        """Undoing an INSERT creates a DELETE inverse."""
        engine = SyncEngine()
        await engine.initialize_document("doc-undo-ins", {"items": []})
        session = make_session("doc-undo-ins")

        op = make_op(EditOperationType.INSERT, path="/items", position=0, value="X")
        await engine.apply_operation("doc-undo-ins", op, session)
        await engine.undo_last_operation("doc-undo-ins", session)
        assert session.version == 0

    async def test_undo_delete_creates_insert_inverse(self):
        """Undoing a DELETE creates an INSERT inverse."""
        engine = SyncEngine()
        await engine.initialize_document("doc-undo-del", {"items": ["a"]})
        session = make_session("doc-undo-del")

        op = make_op(
            EditOperationType.DELETE,
            path="/items",
            position=0,
            length=1,
            old_value="a",
        )
        await engine.apply_operation("doc-undo-del", op, session)
        await engine.undo_last_operation("doc-undo-del", session)
        assert session.version == 0

    async def test_undo_set_property_with_old_value(self):
        """Undoing SET_PROPERTY with old_value restores previous value."""
        engine = SyncEngine()
        await engine.initialize_document("doc-undo-set", {"key": "original"})
        session = make_session("doc-undo-set")

        op = make_op(
            EditOperationType.SET_PROPERTY,
            path="/key",
            value="changed",
            old_value="original",
        )
        await engine.apply_operation("doc-undo-set", op, session)
        await engine.undo_last_operation("doc-undo-set", session)
        doc = await engine.get_document("doc-undo-set")
        assert doc["key"] == "original"

    async def test_undo_set_property_no_old_value(self):
        """Undoing SET_PROPERTY without old_value creates DELETE_PROPERTY inverse."""
        engine = SyncEngine()
        await engine.initialize_document("doc-undo-set2", {})
        session = make_session("doc-undo-set2")

        op = make_op(
            EditOperationType.SET_PROPERTY,
            path="/new_key",
            value="val",
            old_value=None,
        )
        await engine.apply_operation("doc-undo-set2", op, session)
        await engine.undo_last_operation("doc-undo-set2", session)
        doc = await engine.get_document("doc-undo-set2")
        assert "new_key" not in doc

    async def test_undo_replace_creates_inverse_replace(self):
        """Undoing a REPLACE creates a REPLACE with swapped values."""
        engine = SyncEngine()
        await engine.initialize_document("doc-undo-rep", {"x": "old"})
        session = make_session("doc-undo-rep")

        op = make_op(
            EditOperationType.REPLACE,
            path="/x",
            value="new",
            old_value="old",
        )
        await engine.apply_operation("doc-undo-rep", op, session)
        await engine.undo_last_operation("doc-undo-rep", session)
        doc = await engine.get_document("doc-undo-rep")
        assert doc["x"] == "old"

    async def test_undo_other_operation_returns_original(self):
        """Undoing MOVE (unhandled type) returns operation as-is."""
        engine = SyncEngine()
        await engine.initialize_document("doc-undo-mv", {"src": "v"})
        session = make_session("doc-undo-mv")

        op = make_op(EditOperationType.MOVE, path="/src", value="/dst")
        await engine.apply_operation("doc-undo-mv", op, session)
        # undo - MOVE has no explicit inverse, returns operation unchanged
        result = await engine.undo_last_operation("doc-undo-mv", session)
        assert result is not None


# ---------------------------------------------------------------------------
# SyncEngine - _create_inverse_operation
# ---------------------------------------------------------------------------


class TestCreateInverseOperation:
    """Directly test _create_inverse_operation branches."""

    def test_inverse_insert_none_value_uses_length_1(self):
        """INSERT with value=None → DELETE with length=1."""
        engine = SyncEngine()
        op = make_op(EditOperationType.INSERT, path="/x", value=None, position=0)
        inv = engine._create_inverse_operation(op)
        assert inv.type == EditOperationType.DELETE
        assert inv.length == 1

    def test_inverse_insert_with_value(self):
        """INSERT with value='AB' → DELETE with length=2."""
        engine = SyncEngine()
        op = make_op(EditOperationType.INSERT, path="/x", value="AB", position=3)
        inv = engine._create_inverse_operation(op)
        assert inv.type == EditOperationType.DELETE
        assert inv.length == 2

    def test_inverse_delete(self):
        """DELETE → INSERT restoring old_value."""
        engine = SyncEngine()
        op = make_op(EditOperationType.DELETE, path="/items", position=0, length=1, old_value="X")
        inv = engine._create_inverse_operation(op)
        assert inv.type == EditOperationType.INSERT
        assert inv.value == "X"

    def test_inverse_set_property_with_old_value(self):
        """SET_PROPERTY with old_value → SET_PROPERTY with swapped values."""
        engine = SyncEngine()
        op = make_op(EditOperationType.SET_PROPERTY, path="/k", value="new", old_value="old")
        inv = engine._create_inverse_operation(op)
        assert inv.type == EditOperationType.SET_PROPERTY
        assert inv.value == "old"
        assert inv.old_value == "new"

    def test_inverse_set_property_no_old_value(self):
        """SET_PROPERTY without old_value → DELETE_PROPERTY."""
        engine = SyncEngine()
        op = make_op(EditOperationType.SET_PROPERTY, path="/k", value="new", old_value=None)
        inv = engine._create_inverse_operation(op)
        assert inv.type == EditOperationType.DELETE_PROPERTY

    def test_inverse_replace(self):
        """REPLACE → REPLACE with swapped values."""
        engine = SyncEngine()
        op = make_op(EditOperationType.REPLACE, path="/k", value="new", old_value="old")
        inv = engine._create_inverse_operation(op)
        assert inv.type == EditOperationType.REPLACE
        assert inv.value == "old"

    def test_inverse_delete_property_returns_self(self):
        """DELETE_PROPERTY (unhandled) returns original operation."""
        engine = SyncEngine()
        op = make_op(EditOperationType.DELETE_PROPERTY, path="/k")
        inv = engine._create_inverse_operation(op)
        assert inv is op


# ---------------------------------------------------------------------------
# SyncEngine - batch_apply_operations
# ---------------------------------------------------------------------------


class TestBatchApplyOperations:
    """Cover batch_apply_operations branches."""

    async def test_batch_continues_on_error(self):
        """batch_apply_operations skips failing ops and continues."""
        engine = SyncEngine()
        await engine.initialize_document("doc-batch", {"x": 0})
        session = make_session("doc-batch")

        good_op = make_op(EditOperationType.SET_PROPERTY, path="/x", value=1)
        bad_op = make_op(EditOperationType.SET_PROPERTY, path="/x", value=2)

        with patch.object(
            engine,
            "apply_operation",
            side_effect=[
                good_op,  # first call succeeds
                RuntimeError("intentional error"),  # second fails
                good_op,  # third succeeds (different op object)
            ],
        ):
            ops = [good_op, bad_op, good_op]
            result = await engine.batch_apply_operations("doc-batch", ops, session)

        # Should have 2 successfully applied ops
        assert len(result) == 2

    async def test_batch_empty_list(self):
        """batch_apply_operations with empty list returns empty."""
        engine = SyncEngine()
        await engine.initialize_document("doc-batch2", {})
        session = make_session("doc-batch2")
        result = await engine.batch_apply_operations("doc-batch2", [], session)
        assert result == []


# ---------------------------------------------------------------------------
# SyncEngine - Redis helpers
# ---------------------------------------------------------------------------


class TestSyncEngineRedisHelpers:
    """Test Redis persistence helpers including error paths."""

    async def test_persist_to_redis_skips_when_no_redis(self):
        """_persist_to_redis is a no-op when redis is None."""
        engine = SyncEngine()
        await engine._persist_to_redis("doc-1")  # should not raise

    async def test_persist_to_redis_skips_missing_doc(self):
        """_persist_to_redis silently skips documents not in memory."""
        redis = AsyncMock()
        engine = SyncEngine(redis_client=redis)
        await engine._persist_to_redis("nonexistent")
        redis.set.assert_not_called()

    async def test_persist_to_redis_error_handled(self):
        """_persist_to_redis logs but doesn't raise on redis error."""
        redis = AsyncMock()
        redis.set = AsyncMock(side_effect=ConnectionError("redis down"))
        engine = SyncEngine(redis_client=redis)
        await engine.initialize_document("doc-err", {"a": 1})
        # Re-trigger persist (initialize_document already called it; force another)
        # Reset to fail this time
        redis.set.reset_mock()
        redis.set.side_effect = ConnectionError("redis down")
        await engine._persist_to_redis("doc-err")  # should not raise

    async def test_load_from_redis_no_redis(self):
        """_load_from_redis returns None when redis is None."""
        engine = SyncEngine()
        result = await engine._load_from_redis("doc-x")
        assert result is None

    async def test_load_from_redis_error_handled(self):
        """_load_from_redis logs and returns None on error."""
        redis = AsyncMock()
        redis.get = AsyncMock(side_effect=ConnectionError("redis down"))
        engine = SyncEngine(redis_client=redis)
        result = await engine._load_from_redis("doc-err")
        assert result is None

    async def test_persist_operation_no_redis(self):
        """_persist_operation is a no-op when redis is None."""
        engine = SyncEngine()
        op = make_op(EditOperationType.SET_PROPERTY, path="/x", value=1)
        await engine._persist_operation("doc-1", op)  # should not raise

    async def test_persist_operation_with_redis(self):
        """_persist_operation calls lpush and ltrim on redis."""
        redis = AsyncMock()
        engine = SyncEngine(redis_client=redis)
        op = make_op(EditOperationType.SET_PROPERTY, path="/x", value=1)
        await engine._persist_operation("doc-1", op)
        redis.lpush.assert_called_once()
        redis.ltrim.assert_called_once()

    async def test_persist_operation_error_handled(self):
        """_persist_operation logs but doesn't raise on redis error."""
        redis = AsyncMock()
        redis.lpush = AsyncMock(side_effect=ConnectionError("redis down"))
        engine = SyncEngine(redis_client=redis)
        op = make_op(EditOperationType.SET_PROPERTY, path="/x", value=1)
        await engine._persist_operation("doc-1", op)  # should not raise


# ---------------------------------------------------------------------------
# SyncEngine - compact_history
# ---------------------------------------------------------------------------


class TestCompactHistory:
    """Cover compact_history branches."""

    async def test_compact_history_missing_doc(self):
        """compact_history is a no-op for missing doc."""
        engine = SyncEngine()
        await engine.compact_history("nonexistent")  # should not raise

    async def test_compact_history_below_threshold(self):
        """compact_history does nothing when history < 100 ops."""
        engine = SyncEngine()
        await engine.initialize_document("doc-compact", {"x": 0})
        session = make_session("doc-compact")
        # Add a few ops (well below 100)
        for i in range(5):
            op = make_op(EditOperationType.SET_PROPERTY, path="/x", value=i)
            await engine.apply_operation("doc-compact", op, session)
        await engine.compact_history("doc-compact")
        # History should still have 5 ops
        history = await engine.get_operation_history("doc-compact")
        assert len(history) >= 5

    async def test_compact_history_above_threshold(self):
        """compact_history trims to last 50 ops when > 100 exist."""
        engine = SyncEngine()
        await engine.initialize_document("doc-compact2", {"x": 0})
        session = make_session("doc-compact2")
        # Directly stuff history with 110 fake ops
        fake_ops = [
            make_op(EditOperationType.SET_PROPERTY, path="/x", value=i, version=i)
            for i in range(110)
        ]
        engine._operation_history["doc-compact2"] = fake_ops
        await engine.compact_history("doc-compact2")
        assert len(engine._operation_history["doc-compact2"]) == 50

    async def test_compact_history_with_redis(self):
        """compact_history persists to redis after trimming."""
        redis = AsyncMock()
        engine = SyncEngine(redis_client=redis)
        await engine.initialize_document("doc-compact3", {"x": 0})
        fake_ops = [
            make_op(EditOperationType.SET_PROPERTY, path="/x", value=i, version=i)
            for i in range(110)
        ]
        engine._operation_history["doc-compact3"] = fake_ops
        redis.set.reset_mock()
        await engine.compact_history("doc-compact3")
        redis.set.assert_called()


# ---------------------------------------------------------------------------
# SyncEngine - get_operation_history
# ---------------------------------------------------------------------------


class TestGetOperationHistory:
    """Test get_operation_history filtering."""

    async def test_history_since_version_0(self):
        """Default since_version=0 returns all ops."""
        engine = SyncEngine()
        await engine.initialize_document("doc-h", {"x": 0})
        session = make_session("doc-h")
        for i in range(3):
            op = make_op(EditOperationType.SET_PROPERTY, path="/x", value=i)
            await engine.apply_operation("doc-h", op, session)
        history = await engine.get_operation_history("doc-h", since_version=0)
        assert len(history) == 3

    async def test_history_missing_doc_returns_empty(self):
        """Missing doc returns empty list."""
        engine = SyncEngine()
        history = await engine.get_operation_history("nonexistent")
        assert history == []

    async def test_history_version_filter(self):
        """Only ops with version > since_version are returned."""
        engine = SyncEngine()
        await engine.initialize_document("doc-hvf", {"x": 0})
        session = make_session("doc-hvf")
        for i in range(5):
            op = make_op(EditOperationType.SET_PROPERTY, path="/x", value=i)
            await engine.apply_operation("doc-hvf", op, session)
        history = await engine.get_operation_history("doc-hvf", since_version=3)
        # Only ops whose .version > 3 → versions 4 and 5
        assert len(history) == 2


# ---------------------------------------------------------------------------
# SyncEngine - _transform_against_history (version assignment)
# ---------------------------------------------------------------------------


class TestTransformAgainstHistory:
    """Cover _transform_against_history internal behavior."""

    async def test_transform_assigns_correct_version(self):
        """_transform_against_history sets op.version = len(history)+1."""
        engine = SyncEngine()
        await engine.initialize_document("doc-tv", {"x": 0})
        session = make_session("doc-tv")
        # Add 3 ops to history
        for i in range(3):
            op = make_op(EditOperationType.SET_PROPERTY, path="/x", value=i)
            await engine.apply_operation("doc-tv", op, session)
        # The 4th op should be assigned version 4
        op4 = make_op(EditOperationType.SET_PROPERTY, path="/x", value=99)
        transformed = await engine._transform_against_history("doc-tv", op4)
        assert transformed.version == 4

    async def test_transform_empty_history(self):
        """With empty history, version is set to 1."""
        engine = SyncEngine()
        await engine.initialize_document("doc-tv2", {"x": 0})
        op = make_op(EditOperationType.SET_PROPERTY, path="/x", value=1)
        transformed = await engine._transform_against_history("doc-tv2", op)
        assert transformed.version == 1
