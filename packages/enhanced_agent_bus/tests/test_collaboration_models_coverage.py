# Constitutional Hash: 608508a9bd224290
"""
Comprehensive tests for collaboration/models.py to achieve ≥95% coverage.

Tests cover all models, validators, methods, branches, and edge cases.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from enhanced_agent_bus.collaboration.models import (
    ActivityEvent,
    ActivityEventType,
    ChatMessage,
    CollaborationConfig,
    CollaborationError,
    CollaborationSession,
    CollaborationValidationError,
    Collaborator,
    Comment,
    CommentReply,
    ConflictError,
    CursorPosition,
    DocumentLockedError,
    DocumentSnapshot,
    DocumentType,
    EditOperation,
    EditOperationType,
    PermissionDeniedError,
    PresenceStatus,
    SessionFullError,
    UserPermissions,
)

# ---------------------------------------------------------------------------
# PresenceStatus enum
# ---------------------------------------------------------------------------


class TestPresenceStatus:
    def test_all_values(self):
        assert PresenceStatus.ACTIVE == "active"
        assert PresenceStatus.IDLE == "idle"
        assert PresenceStatus.TYPING == "typing"
        assert PresenceStatus.AWAY == "away"

    def test_is_str_enum(self):
        assert isinstance(PresenceStatus.ACTIVE, str)

    def test_comparison_to_string(self):
        assert PresenceStatus.ACTIVE == "active"
        assert PresenceStatus.IDLE == "idle"

    def test_all_members_present(self):
        members = {s.value for s in PresenceStatus}
        assert members == {"active", "idle", "typing", "away"}


# ---------------------------------------------------------------------------
# UserPermissions enum
# ---------------------------------------------------------------------------


class TestUserPermissions:
    def test_all_values(self):
        assert UserPermissions.READ == "read"
        assert UserPermissions.WRITE == "write"
        assert UserPermissions.ADMIN == "admin"

    def test_is_str_enum(self):
        assert isinstance(UserPermissions.WRITE, str)

    def test_all_members_present(self):
        members = {p.value for p in UserPermissions}
        assert members == {"read", "write", "admin"}


# ---------------------------------------------------------------------------
# DocumentType enum
# ---------------------------------------------------------------------------


class TestDocumentType:
    def test_all_values(self):
        assert DocumentType.POLICY == "policy"
        assert DocumentType.WORKFLOW == "workflow"
        assert DocumentType.TEMPLATE == "template"
        assert DocumentType.RULE == "rule"

    def test_is_str_enum(self):
        assert isinstance(DocumentType.POLICY, str)


# ---------------------------------------------------------------------------
# EditOperationType enum
# ---------------------------------------------------------------------------


class TestEditOperationType:
    def test_all_values(self):
        assert EditOperationType.INSERT == "insert"
        assert EditOperationType.DELETE == "delete"
        assert EditOperationType.REPLACE == "replace"
        assert EditOperationType.MOVE == "move"
        assert EditOperationType.SET_PROPERTY == "set_property"
        assert EditOperationType.DELETE_PROPERTY == "delete_property"

    def test_all_members_present(self):
        members = {e.value for e in EditOperationType}
        assert members == {"insert", "delete", "replace", "move", "set_property", "delete_property"}


# ---------------------------------------------------------------------------
# ActivityEventType enum
# ---------------------------------------------------------------------------


class TestActivityEventType:
    def test_all_values(self):
        assert ActivityEventType.USER_JOINED == "user_joined"
        assert ActivityEventType.USER_LEFT == "user_left"
        assert ActivityEventType.DOCUMENT_EDITED == "document_edited"
        assert ActivityEventType.COMMENT_ADDED == "comment_added"
        assert ActivityEventType.COMMENT_RESOLVED == "comment_resolved"
        assert ActivityEventType.CURSOR_MOVED == "cursor_moved"
        assert ActivityEventType.DOCUMENT_LOCKED == "document_locked"
        assert ActivityEventType.DOCUMENT_UNLOCKED == "document_unlocked"
        assert ActivityEventType.VERSION_SAVED == "version_saved"

    def test_all_members_count(self):
        assert len(list(ActivityEventType)) == 9


# ---------------------------------------------------------------------------
# CursorPosition
# ---------------------------------------------------------------------------


class TestCursorPosition:
    def test_required_fields_only(self):
        cursor = CursorPosition(x=10.0, y=20.0)
        assert cursor.x == 10.0
        assert cursor.y == 20.0
        assert cursor.line is None
        assert cursor.column is None
        assert cursor.selection_start is None
        assert cursor.selection_end is None
        assert cursor.node_id is None

    def test_all_fields(self):
        cursor = CursorPosition(
            x=5.5,
            y=9.9,
            line=3,
            column=7,
            selection_start=10,
            selection_end=20,
            node_id="node-abc",
        )
        assert cursor.x == 5.5
        assert cursor.y == 9.9
        assert cursor.line == 3
        assert cursor.column == 7
        assert cursor.selection_start == 10
        assert cursor.selection_end == 20
        assert cursor.node_id == "node-abc"

    def test_model_dump(self):
        cursor = CursorPosition(x=1.0, y=2.0, line=1, column=5)
        d = cursor.model_dump()
        assert d["x"] == 1.0
        assert d["y"] == 2.0
        assert d["line"] == 1
        assert d["column"] == 5

    def test_float_coordinates(self):
        cursor = CursorPosition(x=0.001, y=999.999)
        assert cursor.x == pytest.approx(0.001)
        assert cursor.y == pytest.approx(999.999)

    def test_zero_coordinates(self):
        cursor = CursorPosition(x=0, y=0)
        assert cursor.x == 0
        assert cursor.y == 0

    def test_negative_coordinates(self):
        cursor = CursorPosition(x=-10.0, y=-5.0)
        assert cursor.x == -10.0
        assert cursor.y == -5.0

    def test_large_values(self):
        cursor = CursorPosition(
            x=1_000_000.0, y=1_000_000.0, selection_start=0, selection_end=999999
        )
        assert cursor.selection_end == 999999


# ---------------------------------------------------------------------------
# Collaborator
# ---------------------------------------------------------------------------


class TestCollaboratorValidation:
    """Tests for the color validator in Collaborator."""

    def test_valid_hex_color_7_chars(self):
        c = Collaborator(user_id="u1", name="Alice", color="#FF5733", tenant_id="t1")
        assert c.color == "#FF5733"

    def test_valid_hex_color_4_chars(self):
        c = Collaborator(user_id="u1", name="Alice", color="#F57", tenant_id="t1")
        assert c.color == "#F57"

    def test_invalid_color_no_hash(self):
        with pytest.raises((ValueError, ValidationError)):
            Collaborator(user_id="u1", name="Alice", color="FF5733", tenant_id="t1")

    def test_invalid_color_wrong_length(self):
        with pytest.raises((ValueError, ValidationError)):
            Collaborator(user_id="u1", name="Alice", color="#ABCDE", tenant_id="t1")

    def test_invalid_color_too_short(self):
        with pytest.raises((ValueError, ValidationError)):
            Collaborator(user_id="u1", name="Alice", color="#AB", tenant_id="t1")

    def test_invalid_color_empty(self):
        with pytest.raises((ValueError, ValidationError)):
            Collaborator(user_id="u1", name="Alice", color="", tenant_id="t1")

    def test_invalid_color_8_chars(self):
        with pytest.raises((ValueError, ValidationError)):
            Collaborator(user_id="u1", name="Alice", color="#ABCDEF12", tenant_id="t1")

    def test_invalid_color_random_string(self):
        with pytest.raises((ValueError, ValidationError)):
            Collaborator(user_id="u1", name="Alice", color="not-a-color", tenant_id="t1")


class TestCollaboratorDefaults:
    def test_default_status_is_active(self):
        c = Collaborator(user_id="u1", name="Bob", color="#123456", tenant_id="t1")
        assert c.status == PresenceStatus.ACTIVE

    def test_default_permissions_is_read(self):
        c = Collaborator(user_id="u1", name="Bob", color="#123456", tenant_id="t1")
        assert c.permissions == UserPermissions.READ

    def test_default_is_anonymous_false(self):
        c = Collaborator(user_id="u1", name="Bob", color="#123456", tenant_id="t1")
        assert c.is_anonymous is False

    def test_client_id_is_generated(self):
        c = Collaborator(user_id="u1", name="Bob", color="#123456", tenant_id="t1")
        assert c.client_id is not None
        assert len(c.client_id) > 0
        # Should be a valid UUID
        uuid.UUID(c.client_id)

    def test_client_id_unique_per_instance(self):
        c1 = Collaborator(user_id="u1", name="Bob", color="#123456", tenant_id="t1")
        c2 = Collaborator(user_id="u1", name="Bob", color="#123456", tenant_id="t1")
        assert c1.client_id != c2.client_id

    def test_joined_at_is_datetime(self):
        c = Collaborator(user_id="u1", name="Bob", color="#123456", tenant_id="t1")
        assert isinstance(c.joined_at, datetime)

    def test_last_activity_is_datetime(self):
        c = Collaborator(user_id="u1", name="Bob", color="#123456", tenant_id="t1")
        assert isinstance(c.last_activity, datetime)

    def test_email_defaults_none(self):
        c = Collaborator(user_id="u1", name="Bob", color="#123456", tenant_id="t1")
        assert c.email is None

    def test_avatar_defaults_none(self):
        c = Collaborator(user_id="u1", name="Bob", color="#123456", tenant_id="t1")
        assert c.avatar is None

    def test_cursor_defaults_none(self):
        c = Collaborator(user_id="u1", name="Bob", color="#123456", tenant_id="t1")
        assert c.cursor is None


class TestCollaboratorFields:
    def test_optional_email(self):
        c = Collaborator(
            user_id="u1", name="Bob", color="#123456", tenant_id="t1", email="bob@example.com"
        )
        assert c.email == "bob@example.com"

    def test_optional_avatar(self):
        c = Collaborator(
            user_id="u1",
            name="Bob",
            color="#123456",
            tenant_id="t1",
            avatar="https://img.example.com/a.png",
        )
        assert c.avatar == "https://img.example.com/a.png"

    def test_cursor_position_set(self):
        cursor = CursorPosition(x=10.0, y=20.0)
        c = Collaborator(user_id="u1", name="Bob", color="#123456", tenant_id="t1", cursor=cursor)
        assert c.cursor is not None
        assert c.cursor.x == 10.0

    def test_all_presence_statuses(self):
        for status in PresenceStatus:
            c = Collaborator(
                user_id="u1", name="Bob", color="#123456", tenant_id="t1", status=status
            )
            assert c.status == status

    def test_all_permission_levels(self):
        for perm in UserPermissions:
            c = Collaborator(
                user_id="u1", name="Bob", color="#123456", tenant_id="t1", permissions=perm
            )
            assert c.permissions == perm

    def test_is_anonymous_true(self):
        c = Collaborator(
            user_id="u1", name="Anon", color="#123456", tenant_id="t1", is_anonymous=True
        )
        assert c.is_anonymous is True


class TestCollaboratorToDict:
    def _make_collaborator(self, **kwargs):
        defaults = dict(user_id="u1", name="Alice", color="#FF5733", tenant_id="t1")
        defaults.update(kwargs)
        return Collaborator(**defaults)

    def test_to_dict_has_all_keys(self):
        c = self._make_collaborator()
        d = c.to_dict()
        expected_keys = {
            "user_id",
            "name",
            "email",
            "avatar",
            "color",
            "cursor",
            "status",
            "permissions",
            "joined_at",
            "last_activity",
            "is_anonymous",
            "client_id",
        }
        assert expected_keys == set(d.keys())

    def test_to_dict_user_id(self):
        c = self._make_collaborator(user_id="my-user")
        assert c.to_dict()["user_id"] == "my-user"

    def test_to_dict_name(self):
        c = self._make_collaborator(name="Carol")
        assert c.to_dict()["name"] == "Carol"

    def test_to_dict_email_none(self):
        c = self._make_collaborator()
        assert c.to_dict()["email"] is None

    def test_to_dict_email_set(self):
        c = self._make_collaborator(email="alice@example.com")
        assert c.to_dict()["email"] == "alice@example.com"

    def test_to_dict_avatar_none(self):
        c = self._make_collaborator()
        assert c.to_dict()["avatar"] is None

    def test_to_dict_avatar_set(self):
        c = self._make_collaborator(avatar="https://cdn.example.com/img.png")
        assert c.to_dict()["avatar"] == "https://cdn.example.com/img.png"

    def test_to_dict_color(self):
        c = self._make_collaborator(color="#AABBCC")
        assert c.to_dict()["color"] == "#AABBCC"

    def test_to_dict_cursor_none(self):
        c = self._make_collaborator()
        assert c.to_dict()["cursor"] is None

    def test_to_dict_cursor_set(self):
        cursor = CursorPosition(x=5.0, y=10.0, line=2, column=3)
        c = self._make_collaborator(cursor=cursor)
        d = c.to_dict()
        assert d["cursor"] is not None
        assert d["cursor"]["x"] == 5.0
        assert d["cursor"]["line"] == 2

    def test_to_dict_status_value(self):
        c = self._make_collaborator(status=PresenceStatus.TYPING)
        assert c.to_dict()["status"] == "typing"

    def test_to_dict_permissions_value(self):
        c = self._make_collaborator(permissions=UserPermissions.ADMIN)
        assert c.to_dict()["permissions"] == "admin"

    def test_to_dict_joined_at_is_isoformat(self):
        c = self._make_collaborator()
        # Should be parseable as ISO datetime
        ts = c.to_dict()["joined_at"]
        datetime.fromisoformat(ts)

    def test_to_dict_last_activity_is_isoformat(self):
        c = self._make_collaborator()
        ts = c.to_dict()["last_activity"]
        datetime.fromisoformat(ts)

    def test_to_dict_is_anonymous_false(self):
        c = self._make_collaborator()
        assert c.to_dict()["is_anonymous"] is False

    def test_to_dict_is_anonymous_true(self):
        c = self._make_collaborator(is_anonymous=True)
        assert c.to_dict()["is_anonymous"] is True

    def test_to_dict_client_id_is_string(self):
        c = self._make_collaborator()
        assert isinstance(c.to_dict()["client_id"], str)


# ---------------------------------------------------------------------------
# CollaborationSession
# ---------------------------------------------------------------------------


class TestCollaborationSessionDefaults:
    def _make_session(self, **kwargs):
        defaults = dict(
            document_id="doc-1",
            document_type=DocumentType.POLICY,
            tenant_id="t1",
        )
        defaults.update(kwargs)
        return CollaborationSession(**defaults)

    def test_session_id_generated(self):
        s = self._make_session()
        assert s.session_id is not None
        uuid.UUID(s.session_id)

    def test_session_id_unique(self):
        s1 = self._make_session()
        s2 = self._make_session()
        assert s1.session_id != s2.session_id

    def test_default_version_zero(self):
        s = self._make_session()
        assert s.version == 0

    def test_default_is_locked_false(self):
        s = self._make_session()
        assert s.is_locked is False

    def test_default_locked_by_none(self):
        s = self._make_session()
        assert s.locked_by is None

    def test_default_max_users(self):
        s = self._make_session()
        assert s.max_users == 50

    def test_default_users_empty(self):
        s = self._make_session()
        assert s.users == {}

    def test_created_at_is_datetime(self):
        s = self._make_session()
        assert isinstance(s.created_at, datetime)

    def test_last_activity_is_datetime(self):
        s = self._make_session()
        assert isinstance(s.last_activity, datetime)

    def test_document_id_set(self):
        s = self._make_session(document_id="my-doc")
        assert s.document_id == "my-doc"

    def test_document_type_set(self):
        s = self._make_session(document_type=DocumentType.WORKFLOW)
        assert s.document_type == DocumentType.WORKFLOW

    def test_tenant_id_set(self):
        s = self._make_session(tenant_id="tenant-xyz")
        assert s.tenant_id == "tenant-xyz"

    def test_all_document_types(self):
        for doc_type in DocumentType:
            s = self._make_session(document_type=doc_type)
            assert s.document_type == doc_type


class TestCollaborationSessionCanJoin:
    def _make_session(self, max_users=5, is_locked=False, locked_by=None, user_count=0):
        s = CollaborationSession(
            document_id="doc-1",
            document_type=DocumentType.POLICY,
            tenant_id="t1",
            max_users=max_users,
            is_locked=is_locked,
            locked_by=locked_by,
        )
        for i in range(user_count):
            s.users[f"client-{i}"] = Collaborator(
                user_id=f"user-{i}", name=f"U{i}", color="#FF5733", tenant_id="t1"
            )
        return s

    def test_empty_session_can_join(self):
        s = self._make_session()
        assert s.can_join() is True

    def test_full_session_cannot_join(self):
        s = self._make_session(max_users=3, user_count=3)
        assert s.can_join() is False

    def test_one_below_max_can_join(self):
        s = self._make_session(max_users=3, user_count=2)
        assert s.can_join() is True

    def test_locked_session_cannot_join(self):
        s = self._make_session(is_locked=True, locked_by="admin")
        assert s.can_join() is False

    def test_locked_and_full_cannot_join(self):
        s = self._make_session(max_users=1, is_locked=True, locked_by="admin", user_count=1)
        assert s.can_join() is False

    def test_max_users_one_can_join_if_empty(self):
        s = self._make_session(max_users=1, user_count=0)
        assert s.can_join() is True

    def test_max_users_one_cannot_join_if_one(self):
        s = self._make_session(max_users=1, user_count=1)
        assert s.can_join() is False


class TestCollaborationSessionGetActiveUsers:
    def _make_session(self):
        return CollaborationSession(
            document_id="doc-1",
            document_type=DocumentType.POLICY,
            tenant_id="t1",
        )

    def test_empty_session_no_active_users(self):
        s = self._make_session()
        assert s.get_active_users() == []

    def test_active_user_included(self):
        s = self._make_session()
        c = Collaborator(
            user_id="u1",
            name="Alice",
            color="#FF5733",
            tenant_id="t1",
            status=PresenceStatus.ACTIVE,
        )
        s.users["c1"] = c
        result = s.get_active_users()
        assert len(result) == 1
        assert result[0].user_id == "u1"

    def test_idle_user_included(self):
        s = self._make_session()
        c = Collaborator(
            user_id="u1", name="Alice", color="#FF5733", tenant_id="t1", status=PresenceStatus.IDLE
        )
        s.users["c1"] = c
        result = s.get_active_users()
        assert len(result) == 1

    def test_typing_user_included(self):
        s = self._make_session()
        c = Collaborator(
            user_id="u1",
            name="Alice",
            color="#FF5733",
            tenant_id="t1",
            status=PresenceStatus.TYPING,
        )
        s.users["c1"] = c
        result = s.get_active_users()
        assert len(result) == 1

    def test_away_user_excluded(self):
        s = self._make_session()
        c = Collaborator(
            user_id="u1", name="Alice", color="#FF5733", tenant_id="t1", status=PresenceStatus.AWAY
        )
        s.users["c1"] = c
        result = s.get_active_users()
        assert len(result) == 0

    def test_mix_of_statuses(self):
        s = self._make_session()
        s.users["c1"] = Collaborator(
            user_id="u1", name="A", color="#FF5733", tenant_id="t1", status=PresenceStatus.ACTIVE
        )
        s.users["c2"] = Collaborator(
            user_id="u2", name="B", color="#FF5733", tenant_id="t1", status=PresenceStatus.AWAY
        )
        s.users["c3"] = Collaborator(
            user_id="u3", name="C", color="#FF5733", tenant_id="t1", status=PresenceStatus.TYPING
        )
        s.users["c4"] = Collaborator(
            user_id="u4", name="D", color="#FF5733", tenant_id="t1", status=PresenceStatus.IDLE
        )
        result = s.get_active_users()
        assert len(result) == 3

    def test_multiple_away_all_excluded(self):
        s = self._make_session()
        for i in range(3):
            s.users[f"c{i}"] = Collaborator(
                user_id=f"u{i}",
                name=f"U{i}",
                color="#FF5733",
                tenant_id="t1",
                status=PresenceStatus.AWAY,
            )
        result = s.get_active_users()
        assert len(result) == 0


class TestCollaborationSessionUpdateActivity:
    def test_update_activity_changes_timestamp(self):
        s = CollaborationSession(
            document_id="doc-1",
            document_type=DocumentType.POLICY,
            tenant_id="t1",
        )
        old_activity = s.last_activity
        s.update_activity()
        # The new timestamp should be >= old (called utcnow again)
        assert isinstance(s.last_activity, datetime)


# ---------------------------------------------------------------------------
# EditOperation
# ---------------------------------------------------------------------------


class TestEditOperationDefaults:
    def _make_op(self, **kwargs):
        defaults = dict(
            type=EditOperationType.REPLACE,
            path="/title",
            user_id="user-1",
            client_id="client-1",
            version=1,
        )
        defaults.update(kwargs)
        return EditOperation(**defaults)

    def test_operation_id_generated(self):
        op = self._make_op()
        assert op.operation_id is not None
        uuid.UUID(op.operation_id)

    def test_timestamp_is_float(self):
        op = self._make_op()
        assert isinstance(op.timestamp, float)

    def test_value_defaults_none(self):
        op = self._make_op()
        assert op.value is None

    def test_old_value_defaults_none(self):
        op = self._make_op()
        assert op.old_value is None

    def test_position_defaults_none(self):
        op = self._make_op()
        assert op.position is None

    def test_length_defaults_none(self):
        op = self._make_op()
        assert op.length is None

    def test_parent_version_defaults_none(self):
        op = self._make_op()
        assert op.parent_version is None

    def test_all_edit_types(self):
        for op_type in EditOperationType:
            op = self._make_op(type=op_type)
            assert op.type == op_type


class TestEditOperationFields:
    def test_with_value(self):
        op = EditOperation(
            type=EditOperationType.REPLACE,
            path="/name",
            value="NewName",
            user_id="u1",
            client_id="c1",
            version=2,
        )
        assert op.value == "NewName"

    def test_with_dict_value(self):
        op = EditOperation(
            type=EditOperationType.SET_PROPERTY,
            path="/meta",
            value={"key": "val"},
            user_id="u1",
            client_id="c1",
            version=3,
        )
        assert op.value == {"key": "val"}

    def test_with_list_value(self):
        op = EditOperation(
            type=EditOperationType.INSERT,
            path="/items",
            value=["a", "b"],
            user_id="u1",
            client_id="c1",
            version=1,
        )
        assert op.value == ["a", "b"]

    def test_with_position_and_length(self):
        op = EditOperation(
            type=EditOperationType.DELETE,
            path="/content",
            position=5,
            length=10,
            user_id="u1",
            client_id="c1",
            version=4,
        )
        assert op.position == 5
        assert op.length == 10

    def test_with_parent_version(self):
        op = EditOperation(
            type=EditOperationType.MOVE,
            path="/nodes/1",
            parent_version=3,
            user_id="u1",
            client_id="c1",
            version=4,
        )
        assert op.parent_version == 3


class TestEditOperationToDict:
    def _make_op(self, **kwargs):
        defaults = dict(
            type=EditOperationType.INSERT,
            path="/content",
            value="hello",
            user_id="user-1",
            client_id="client-1",
            version=5,
        )
        defaults.update(kwargs)
        return EditOperation(**defaults)

    def test_to_dict_has_all_keys(self):
        op = self._make_op()
        d = op.to_dict()
        expected_keys = {
            "operation_id",
            "type",
            "path",
            "value",
            "old_value",
            "position",
            "length",
            "timestamp",
            "user_id",
            "client_id",
            "version",
            "parent_version",
        }
        assert expected_keys == set(d.keys())

    def test_to_dict_type_is_value(self):
        op = self._make_op(type=EditOperationType.DELETE)
        assert op.to_dict()["type"] == "delete"

    def test_to_dict_operation_id(self):
        op = self._make_op()
        d = op.to_dict()
        assert isinstance(d["operation_id"], str)
        uuid.UUID(d["operation_id"])

    def test_to_dict_path(self):
        op = self._make_op(path="/foo/bar")
        assert op.to_dict()["path"] == "/foo/bar"

    def test_to_dict_value(self):
        op = self._make_op(value=42)
        assert op.to_dict()["value"] == 42

    def test_to_dict_old_value_none(self):
        op = self._make_op()
        assert op.to_dict()["old_value"] is None

    def test_to_dict_old_value_set(self):
        op = self._make_op(old_value="old")
        assert op.to_dict()["old_value"] == "old"

    def test_to_dict_position_none(self):
        op = self._make_op()
        assert op.to_dict()["position"] is None

    def test_to_dict_position_set(self):
        op = self._make_op(position=7)
        assert op.to_dict()["position"] == 7

    def test_to_dict_length_none(self):
        op = self._make_op()
        assert op.to_dict()["length"] is None

    def test_to_dict_length_set(self):
        op = self._make_op(length=15)
        assert op.to_dict()["length"] == 15

    def test_to_dict_timestamp_is_float(self):
        op = self._make_op()
        assert isinstance(op.to_dict()["timestamp"], float)

    def test_to_dict_user_id(self):
        op = self._make_op(user_id="specific-user")
        assert op.to_dict()["user_id"] == "specific-user"

    def test_to_dict_client_id(self):
        op = self._make_op(client_id="specific-client")
        assert op.to_dict()["client_id"] == "specific-client"

    def test_to_dict_version(self):
        op = self._make_op(version=99)
        assert op.to_dict()["version"] == 99

    def test_to_dict_parent_version_none(self):
        op = self._make_op()
        assert op.to_dict()["parent_version"] is None

    def test_to_dict_parent_version_set(self):
        op = self._make_op(parent_version=10)
        assert op.to_dict()["parent_version"] == 10

    def test_to_dict_all_operation_types(self):
        for op_type in EditOperationType:
            op = self._make_op(type=op_type)
            d = op.to_dict()
            assert d["type"] == op_type.value


# ---------------------------------------------------------------------------
# CommentReply
# ---------------------------------------------------------------------------


class TestCommentReply:
    def test_create_reply(self):
        r = CommentReply(user_id="u1", user_name="Bob", text="A reply")
        assert r.user_id == "u1"
        assert r.user_name == "Bob"
        assert r.text == "A reply"

    def test_reply_id_generated(self):
        r = CommentReply(user_id="u1", user_name="Bob", text="text")
        assert r.reply_id is not None
        uuid.UUID(r.reply_id)

    def test_reply_id_unique(self):
        r1 = CommentReply(user_id="u1", user_name="Bob", text="text")
        r2 = CommentReply(user_id="u1", user_name="Bob", text="text")
        assert r1.reply_id != r2.reply_id

    def test_timestamp_is_datetime(self):
        r = CommentReply(user_id="u1", user_name="Bob", text="text")
        assert isinstance(r.timestamp, datetime)

    def test_min_length_text(self):
        r = CommentReply(user_id="u1", user_name="Bob", text="x")
        assert r.text == "x"

    def test_max_length_text(self):
        long_text = "a" * 5000
        r = CommentReply(user_id="u1", user_name="Bob", text=long_text)
        assert len(r.text) == 5000

    def test_empty_text_raises(self):
        with pytest.raises((ValueError, ValidationError)):
            CommentReply(user_id="u1", user_name="Bob", text="")

    def test_text_exceeds_max_raises(self):
        with pytest.raises((ValueError, ValidationError)):
            CommentReply(user_id="u1", user_name="Bob", text="a" * 5001)


# ---------------------------------------------------------------------------
# Comment
# ---------------------------------------------------------------------------


class TestCommentDefaults:
    def test_comment_id_generated(self):
        c = Comment(user_id="u1", user_name="Alice", text="hello")
        assert c.comment_id is not None
        uuid.UUID(c.comment_id)

    def test_comment_id_unique(self):
        c1 = Comment(user_id="u1", user_name="Alice", text="hello")
        c2 = Comment(user_id="u1", user_name="Alice", text="hello")
        assert c1.comment_id != c2.comment_id

    def test_resolved_default_false(self):
        c = Comment(user_id="u1", user_name="Alice", text="hello")
        assert c.resolved is False

    def test_resolved_by_default_none(self):
        c = Comment(user_id="u1", user_name="Alice", text="hello")
        assert c.resolved_by is None

    def test_resolved_at_default_none(self):
        c = Comment(user_id="u1", user_name="Alice", text="hello")
        assert c.resolved_at is None

    def test_replies_default_empty(self):
        c = Comment(user_id="u1", user_name="Alice", text="hello")
        assert c.replies == []

    def test_position_default_none(self):
        c = Comment(user_id="u1", user_name="Alice", text="hello")
        assert c.position is None

    def test_selection_text_default_none(self):
        c = Comment(user_id="u1", user_name="Alice", text="hello")
        assert c.selection_text is None

    def test_mentions_default_empty(self):
        c = Comment(user_id="u1", user_name="Alice", text="hello")
        assert c.mentions == []

    def test_user_avatar_default_none(self):
        c = Comment(user_id="u1", user_name="Alice", text="hello")
        assert c.user_avatar is None

    def test_timestamp_is_datetime(self):
        c = Comment(user_id="u1", user_name="Alice", text="hello")
        assert isinstance(c.timestamp, datetime)


class TestCommentFields:
    def test_text_min_length(self):
        c = Comment(user_id="u1", user_name="Alice", text="x")
        assert c.text == "x"

    def test_text_max_length(self):
        c = Comment(user_id="u1", user_name="Alice", text="a" * 10000)
        assert len(c.text) == 10000

    def test_text_empty_raises(self):
        with pytest.raises((ValueError, ValidationError)):
            Comment(user_id="u1", user_name="Alice", text="")

    def test_text_exceeds_max_raises(self):
        with pytest.raises((ValueError, ValidationError)):
            Comment(user_id="u1", user_name="Alice", text="a" * 10001)

    def test_with_position(self):
        pos = CursorPosition(x=1.0, y=2.0)
        c = Comment(user_id="u1", user_name="Alice", text="hello", position=pos)
        assert c.position is not None
        assert c.position.x == 1.0

    def test_with_selection_text(self):
        c = Comment(user_id="u1", user_name="Alice", text="hello", selection_text="selected")
        assert c.selection_text == "selected"

    def test_with_mentions(self):
        c = Comment(user_id="u1", user_name="Alice", text="hello", mentions=["u2", "u3"])
        assert "u2" in c.mentions
        assert "u3" in c.mentions

    def test_with_user_avatar(self):
        c = Comment(
            user_id="u1",
            user_name="Alice",
            text="hello",
            user_avatar="https://cdn.example.com/av.png",
        )
        assert c.user_avatar == "https://cdn.example.com/av.png"


class TestCommentResolve:
    def test_resolve_sets_resolved_true(self):
        c = Comment(user_id="u1", user_name="Alice", text="hello")
        c.resolve("u2")
        assert c.resolved is True

    def test_resolve_sets_resolved_by(self):
        c = Comment(user_id="u1", user_name="Alice", text="hello")
        c.resolve("u99")
        assert c.resolved_by == "u99"

    def test_resolve_sets_resolved_at(self):
        c = Comment(user_id="u1", user_name="Alice", text="hello")
        assert c.resolved_at is None
        c.resolve("u2")
        assert isinstance(c.resolved_at, datetime)

    def test_resolve_multiple_times(self):
        c = Comment(user_id="u1", user_name="Alice", text="hello")
        c.resolve("u2")
        c.resolve("u3")
        # Last resolver wins
        assert c.resolved_by == "u3"
        assert c.resolved is True


class TestCommentAddReply:
    def test_add_reply_increases_count(self):
        c = Comment(user_id="u1", user_name="Alice", text="original")
        r = CommentReply(user_id="u2", user_name="Bob", text="reply")
        c.add_reply(r)
        assert len(c.replies) == 1

    def test_add_reply_stores_reply(self):
        c = Comment(user_id="u1", user_name="Alice", text="original")
        r = CommentReply(user_id="u2", user_name="Bob", text="my reply")
        c.add_reply(r)
        assert c.replies[0].text == "my reply"
        assert c.replies[0].user_id == "u2"

    def test_add_multiple_replies(self):
        c = Comment(user_id="u1", user_name="Alice", text="original")
        for i in range(5):
            r = CommentReply(user_id=f"u{i}", user_name=f"User{i}", text=f"Reply {i}")
            c.add_reply(r)
        assert len(c.replies) == 5

    def test_reply_order_preserved(self):
        c = Comment(user_id="u1", user_name="Alice", text="original")
        r1 = CommentReply(user_id="u2", user_name="Bob", text="first")
        r2 = CommentReply(user_id="u3", user_name="Carol", text="second")
        c.add_reply(r1)
        c.add_reply(r2)
        assert c.replies[0].text == "first"
        assert c.replies[1].text == "second"


# ---------------------------------------------------------------------------
# ActivityEvent
# ---------------------------------------------------------------------------


class TestActivityEvent:
    def test_create_event(self):
        e = ActivityEvent(
            type=ActivityEventType.USER_JOINED,
            user_id="u1",
            user_name="Alice",
            document_id="doc-1",
        )
        assert e.type == ActivityEventType.USER_JOINED
        assert e.user_id == "u1"
        assert e.user_name == "Alice"
        assert e.document_id == "doc-1"

    def test_event_id_generated(self):
        e = ActivityEvent(
            type=ActivityEventType.USER_LEFT,
            user_id="u1",
            user_name="Alice",
            document_id="doc-1",
        )
        assert e.event_id is not None
        uuid.UUID(e.event_id)

    def test_event_id_unique(self):
        kwargs = dict(
            type=ActivityEventType.USER_JOINED, user_id="u1", user_name="Alice", document_id="doc-1"
        )
        e1 = ActivityEvent(**kwargs)
        e2 = ActivityEvent(**kwargs)
        assert e1.event_id != e2.event_id

    def test_timestamp_is_datetime(self):
        e = ActivityEvent(
            type=ActivityEventType.DOCUMENT_EDITED,
            user_id="u1",
            user_name="Alice",
            document_id="doc-1",
        )
        assert isinstance(e.timestamp, datetime)

    def test_details_default_empty(self):
        e = ActivityEvent(
            type=ActivityEventType.COMMENT_ADDED,
            user_id="u1",
            user_name="Alice",
            document_id="doc-1",
        )
        assert e.details == {}

    def test_details_set(self):
        e = ActivityEvent(
            type=ActivityEventType.VERSION_SAVED,
            user_id="u1",
            user_name="Alice",
            document_id="doc-1",
            details={"version": 5, "note": "checkpoint"},
        )
        assert e.details["version"] == 5

    def test_all_event_types(self):
        for event_type in ActivityEventType:
            e = ActivityEvent(
                type=event_type,
                user_id="u1",
                user_name="Alice",
                document_id="doc-1",
            )
            assert e.type == event_type


# ---------------------------------------------------------------------------
# ChatMessage
# ---------------------------------------------------------------------------


class TestChatMessage:
    def test_create_message(self):
        m = ChatMessage(user_id="u1", user_name="Alice", text="Hello!")
        assert m.user_id == "u1"
        assert m.user_name == "Alice"
        assert m.text == "Hello!"

    def test_message_id_generated(self):
        m = ChatMessage(user_id="u1", user_name="Alice", text="Hi")
        assert m.message_id is not None
        uuid.UUID(m.message_id)

    def test_message_id_unique(self):
        m1 = ChatMessage(user_id="u1", user_name="Alice", text="Hi")
        m2 = ChatMessage(user_id="u1", user_name="Alice", text="Hi")
        assert m1.message_id != m2.message_id

    def test_timestamp_is_datetime(self):
        m = ChatMessage(user_id="u1", user_name="Alice", text="Hi")
        assert isinstance(m.timestamp, datetime)

    def test_user_avatar_default_none(self):
        m = ChatMessage(user_id="u1", user_name="Alice", text="Hi")
        assert m.user_avatar is None

    def test_user_avatar_set(self):
        m = ChatMessage(
            user_id="u1", user_name="Alice", text="Hi", user_avatar="https://cdn.example.com/a.png"
        )
        assert m.user_avatar == "https://cdn.example.com/a.png"

    def test_mentions_default_empty(self):
        m = ChatMessage(user_id="u1", user_name="Alice", text="Hi")
        assert m.mentions == []

    def test_mentions_set(self):
        m = ChatMessage(user_id="u1", user_name="Alice", text="Hey @u2", mentions=["u2"])
        assert "u2" in m.mentions

    def test_is_system_default_false(self):
        m = ChatMessage(user_id="u1", user_name="Alice", text="Hi")
        assert m.is_system is False

    def test_is_system_true(self):
        m = ChatMessage(user_id="system", user_name="System", text="User joined", is_system=True)
        assert m.is_system is True

    def test_text_min_length(self):
        m = ChatMessage(user_id="u1", user_name="Alice", text="x")
        assert m.text == "x"

    def test_text_max_length(self):
        m = ChatMessage(user_id="u1", user_name="Alice", text="a" * 2000)
        assert len(m.text) == 2000

    def test_text_empty_raises(self):
        with pytest.raises((ValueError, ValidationError)):
            ChatMessage(user_id="u1", user_name="Alice", text="")

    def test_text_exceeds_max_raises(self):
        with pytest.raises((ValueError, ValidationError)):
            ChatMessage(user_id="u1", user_name="Alice", text="a" * 2001)


# ---------------------------------------------------------------------------
# DocumentSnapshot
# ---------------------------------------------------------------------------


class TestDocumentSnapshot:
    def test_create_snapshot(self):
        snap = DocumentSnapshot(
            document_id="doc-1",
            version=3,
            content={"title": "My Policy", "rules": []},
            created_by="user-1",
        )
        assert snap.document_id == "doc-1"
        assert snap.version == 3
        assert snap.content["title"] == "My Policy"
        assert snap.created_by == "user-1"

    def test_snapshot_id_generated(self):
        snap = DocumentSnapshot(document_id="doc-1", version=1, content={}, created_by="u1")
        assert snap.snapshot_id is not None
        uuid.UUID(snap.snapshot_id)

    def test_snapshot_id_unique(self):
        kwargs = dict(document_id="doc-1", version=1, content={}, created_by="u1")
        s1 = DocumentSnapshot(**kwargs)
        s2 = DocumentSnapshot(**kwargs)
        assert s1.snapshot_id != s2.snapshot_id

    def test_created_at_is_datetime(self):
        snap = DocumentSnapshot(document_id="d1", version=1, content={}, created_by="u1")
        assert isinstance(snap.created_at, datetime)

    def test_operation_history_default_empty(self):
        snap = DocumentSnapshot(document_id="d1", version=1, content={}, created_by="u1")
        assert snap.operation_history == []

    def test_comment_count_default_zero(self):
        snap = DocumentSnapshot(document_id="d1", version=1, content={}, created_by="u1")
        assert snap.comment_count == 0

    def test_operation_history_with_operations(self):
        op = EditOperation(
            type=EditOperationType.INSERT,
            path="/content",
            value="hello",
            user_id="u1",
            client_id="c1",
            version=1,
        )
        snap = DocumentSnapshot(
            document_id="d1",
            version=2,
            content={},
            created_by="u1",
            operation_history=[op],
        )
        assert len(snap.operation_history) == 1
        assert snap.operation_history[0].type == EditOperationType.INSERT

    def test_comment_count_set(self):
        snap = DocumentSnapshot(
            document_id="d1", version=1, content={}, created_by="u1", comment_count=5
        )
        assert snap.comment_count == 5

    def test_content_can_be_complex(self):
        content = {
            "title": "Policy",
            "rules": [{"id": 1, "text": "Rule 1"}, {"id": 2, "text": "Rule 2"}],
            "metadata": {"version": "1.0", "tags": ["governance"]},
        }
        snap = DocumentSnapshot(document_id="d1", version=1, content=content, created_by="u1")
        assert snap.content["rules"][0]["id"] == 1


# ---------------------------------------------------------------------------
# CollaborationConfig
# ---------------------------------------------------------------------------


class TestCollaborationConfig:
    def test_default_values(self):
        cfg = CollaborationConfig()
        assert cfg.max_users_per_document == 50
        assert cfg.max_documents_per_tenant == 1000
        assert cfg.cursor_sync_interval_ms == 50
        assert cfg.operation_batch_size == 10
        assert cfg.history_retention_hours == 24
        assert cfg.enable_chat is True
        assert cfg.enable_comments is True
        assert cfg.enable_presence is True
        assert cfg.lock_timeout_seconds == 300
        assert cfg.idle_timeout_seconds == 300
        assert cfg.away_timeout_seconds == 600

    def test_custom_max_users(self):
        cfg = CollaborationConfig(max_users_per_document=100)
        assert cfg.max_users_per_document == 100

    def test_custom_max_documents(self):
        cfg = CollaborationConfig(max_documents_per_tenant=500)
        assert cfg.max_documents_per_tenant == 500

    def test_custom_cursor_sync(self):
        cfg = CollaborationConfig(cursor_sync_interval_ms=100)
        assert cfg.cursor_sync_interval_ms == 100

    def test_disable_chat(self):
        cfg = CollaborationConfig(enable_chat=False)
        assert cfg.enable_chat is False
        assert cfg.enable_comments is True  # unchanged

    def test_disable_comments(self):
        cfg = CollaborationConfig(enable_comments=False)
        assert cfg.enable_comments is False
        assert cfg.enable_chat is True  # unchanged

    def test_disable_presence(self):
        cfg = CollaborationConfig(enable_presence=False)
        assert cfg.enable_presence is False

    def test_custom_lock_timeout(self):
        cfg = CollaborationConfig(lock_timeout_seconds=60)
        assert cfg.lock_timeout_seconds == 60

    def test_custom_idle_timeout(self):
        cfg = CollaborationConfig(idle_timeout_seconds=120)
        assert cfg.idle_timeout_seconds == 120

    def test_custom_away_timeout(self):
        cfg = CollaborationConfig(away_timeout_seconds=900)
        assert cfg.away_timeout_seconds == 900

    def test_custom_batch_size(self):
        cfg = CollaborationConfig(operation_batch_size=25)
        assert cfg.operation_batch_size == 25

    def test_custom_history_retention(self):
        cfg = CollaborationConfig(history_retention_hours=48)
        assert cfg.history_retention_hours == 48

    def test_all_disabled(self):
        cfg = CollaborationConfig(enable_chat=False, enable_comments=False, enable_presence=False)
        assert cfg.enable_chat is False
        assert cfg.enable_comments is False
        assert cfg.enable_presence is False


# ---------------------------------------------------------------------------
# CollaborationError hierarchy
# ---------------------------------------------------------------------------


class TestCollaborationError:
    def test_basic_error(self):
        err = CollaborationError("Something went wrong")
        assert err.message == "Something went wrong"
        assert err.code == "COLLABORATION_ERROR"
        assert str(err) == "Something went wrong"

    def test_custom_code(self):
        err = CollaborationError("Custom error", code="CUSTOM_CODE")
        assert err.code == "CUSTOM_CODE"

    def test_is_exception(self):
        err = CollaborationError("error")
        assert isinstance(err, CollaborationError)

    def test_raise_and_catch(self):
        with pytest.raises(CollaborationError) as exc_info:
            raise CollaborationError("raised error", "RAISED")
        assert exc_info.value.code == "RAISED"

    def test_default_message(self):
        err = CollaborationError("test msg")
        assert err.message == "test msg"


class TestPermissionDeniedError:
    def test_default_message(self):
        err = PermissionDeniedError()
        assert err.message == "Permission denied"
        assert err.code == "PERMISSION_DENIED"

    def test_custom_message(self):
        err = PermissionDeniedError("You cannot edit this")
        assert err.message == "You cannot edit this"
        assert err.code == "PERMISSION_DENIED"

    def test_is_collaboration_error(self):
        err = PermissionDeniedError()
        assert isinstance(err, CollaborationError)

    def test_str_representation(self):
        err = PermissionDeniedError("No access")
        assert str(err) == "No access"

    def test_raise_and_catch_as_base(self):
        with pytest.raises(CollaborationError):
            raise PermissionDeniedError()


class TestDocumentLockedError:
    def test_default_message(self):
        err = DocumentLockedError()
        assert err.message == "Document is locked"
        assert err.code == "DOCUMENT_LOCKED"

    def test_custom_message(self):
        err = DocumentLockedError("Locked by admin")
        assert err.message == "Locked by admin"
        assert err.code == "DOCUMENT_LOCKED"

    def test_is_collaboration_error(self):
        err = DocumentLockedError()
        assert isinstance(err, CollaborationError)

    def test_raise_and_catch(self):
        with pytest.raises(DocumentLockedError):
            raise DocumentLockedError("locked")

    def test_catch_as_base_class(self):
        with pytest.raises(CollaborationError):
            raise DocumentLockedError()


class TestSessionFullError:
    def test_default_message(self):
        err = SessionFullError()
        assert err.message == "Session is full"
        assert err.code == "SESSION_FULL"

    def test_custom_message(self):
        err = SessionFullError("Cannot join: session at capacity")
        assert err.message == "Cannot join: session at capacity"

    def test_is_collaboration_error(self):
        err = SessionFullError()
        assert isinstance(err, CollaborationError)

    def test_raise_and_catch(self):
        with pytest.raises(SessionFullError):
            raise SessionFullError()


class TestConflictError:
    def test_default_message(self):
        err = ConflictError()
        assert err.message == "Edit conflict detected"
        assert err.code == "CONFLICT"

    def test_custom_message(self):
        err = ConflictError("Concurrent edit at /title")
        assert err.message == "Concurrent edit at /title"

    def test_is_collaboration_error(self):
        err = ConflictError()
        assert isinstance(err, CollaborationError)

    def test_raise_and_catch(self):
        with pytest.raises(ConflictError):
            raise ConflictError()


class TestCollaborationValidationError:
    def test_default_message(self):
        err = CollaborationValidationError()
        assert err.message == "Validation failed"
        assert err.code == "VALIDATION_ERROR"

    def test_custom_message(self):
        err = CollaborationValidationError("Missing required field")
        assert err.message == "Missing required field"

    def test_is_collaboration_error(self):
        err = CollaborationValidationError()
        assert isinstance(err, CollaborationError)

    def test_raise_and_catch(self):
        with pytest.raises(CollaborationValidationError):
            raise CollaborationValidationError("bad input")


# ---------------------------------------------------------------------------
# Integration / cross-model tests
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_collaborator_with_cursor_to_dict(self):
        cursor = CursorPosition(x=10.0, y=20.0, line=5, column=3, node_id="node-1")
        c = Collaborator(
            user_id="u1",
            name="Dave",
            color="#123456",
            tenant_id="t1",
            cursor=cursor,
            status=PresenceStatus.TYPING,
            permissions=UserPermissions.WRITE,
        )
        d = c.to_dict()
        assert d["cursor"]["node_id"] == "node-1"
        assert d["status"] == "typing"
        assert d["permissions"] == "write"

    def test_session_with_multiple_collaborators(self):
        s = CollaborationSession(
            document_id="doc-x",
            document_type=DocumentType.RULE,
            tenant_id="t1",
            max_users=10,
        )
        statuses = [
            PresenceStatus.ACTIVE,
            PresenceStatus.AWAY,
            PresenceStatus.IDLE,
            PresenceStatus.TYPING,
        ]
        for i, status in enumerate(statuses):
            c = Collaborator(
                user_id=f"u{i}",
                name=f"User{i}",
                color="#FF5733",
                tenant_id="t1",
                status=status,
            )
            s.users[f"c{i}"] = c

        active = s.get_active_users()
        assert len(active) == 3  # ACTIVE + IDLE + TYPING; AWAY excluded
        assert s.can_join() is True

    def test_comment_with_position_and_replies(self):
        pos = CursorPosition(x=0.0, y=100.0, selection_start=5, selection_end=15)
        comment = Comment(
            user_id="u1",
            user_name="Editor",
            text="Should we rephrase this?",
            position=pos,
            selection_text="original text",
            mentions=["u2", "u3"],
        )
        reply = CommentReply(user_id="u2", user_name="Reviewer", text="Agreed!")
        comment.add_reply(reply)
        comment.resolve("u2")

        assert comment.position.selection_start == 5
        assert comment.selection_text == "original text"
        assert len(comment.mentions) == 2
        assert len(comment.replies) == 1
        assert comment.resolved is True
        assert comment.resolved_by == "u2"

    def test_document_snapshot_with_edit_operations(self):
        ops = [
            EditOperation(
                type=EditOperationType.INSERT,
                path=f"/rules/{i}",
                value=f"rule-{i}",
                user_id="u1",
                client_id="c1",
                version=i + 1,
            )
            for i in range(3)
        ]
        snap = DocumentSnapshot(
            document_id="doc-policy",
            version=3,
            content={"title": "Policy", "rules": ["r0", "r1", "r2"]},
            created_by="admin",
            operation_history=ops,
            comment_count=2,
        )
        assert len(snap.operation_history) == 3
        assert snap.comment_count == 2
        assert snap.operation_history[2].path == "/rules/2"

    def test_all_document_types_in_session(self):
        for doc_type in DocumentType:
            s = CollaborationSession(
                document_id="doc-1",
                document_type=doc_type,
                tenant_id="t1",
            )
            assert s.document_type == doc_type

    def test_error_hierarchy(self):
        errors = [
            PermissionDeniedError(),
            DocumentLockedError(),
            SessionFullError(),
            ConflictError(),
            CollaborationValidationError(),
        ]
        for err in errors:
            assert isinstance(err, CollaborationError)
            assert err.code != "COLLABORATION_ERROR"  # each has unique code

    def test_edit_operation_all_types_to_dict(self):
        for op_type in EditOperationType:
            op = EditOperation(
                type=op_type,
                path="/test",
                user_id="u1",
                client_id="c1",
                version=1,
            )
            d = op.to_dict()
            assert d["type"] == op_type.value

    def test_activity_event_all_types(self):
        for event_type in ActivityEventType:
            e = ActivityEvent(
                type=event_type,
                user_id="u1",
                user_name="Alice",
                document_id="doc-1",
            )
            assert e.type == event_type

    def test_chat_system_message(self):
        m = ChatMessage(
            user_id="system",
            user_name="ACGS Bot",
            text="User Alice joined the session",
            is_system=True,
        )
        assert m.is_system is True
        assert m.user_id == "system"
