# Constitutional Hash: 608508a9bd224290
"""
Tests for src/core/enhanced_agent_bus/constitutional/version_model.py
Coverage target: ≥90%
"""

import re
from datetime import UTC, datetime, timezone
from unittest.mock import patch
from uuid import UUID

import pytest
from pydantic import ValidationError

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.constitutional.version_model import (
    ConstitutionalStatus,
    ConstitutionalVersion,
)

VALID_HASH = CONSTITUTIONAL_HASH
VALID_VERSION = "1.0.0"
VALID_CONTENT: dict = {"rules": ["rule1"], "policies": {}}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_version(**kwargs) -> ConstitutionalVersion:
    """Return a ConstitutionalVersion with sensible defaults."""
    defaults = {
        "version": VALID_VERSION,
        "constitutional_hash": VALID_HASH,
        "content": VALID_CONTENT,
    }
    defaults.update(kwargs)
    return ConstitutionalVersion(**defaults)


# ---------------------------------------------------------------------------
# ConstitutionalStatus enum
# ---------------------------------------------------------------------------


class TestConstitutionalStatus:
    def test_all_members_exist(self):
        expected = {
            "DRAFT",
            "PROPOSED",
            "UNDER_REVIEW",
            "APPROVED",
            "ACTIVE",
            "SUPERSEDED",
            "ROLLED_BACK",
            "REJECTED",
        }
        assert {m.name for m in ConstitutionalStatus} == expected

    def test_values_are_lowercase_strings(self):
        for member in ConstitutionalStatus:
            assert member.value == member.value.lower()
            assert isinstance(member.value, str)

    def test_is_str_enum(self):
        assert ConstitutionalStatus.ACTIVE == "active"
        assert ConstitutionalStatus.DRAFT == "draft"


# ---------------------------------------------------------------------------
# ConstitutionalVersion construction
# ---------------------------------------------------------------------------


class TestConstitutionalVersionConstruction:
    def test_minimal_valid_construction(self):
        v = make_version()
        assert v.version == VALID_VERSION
        assert v.constitutional_hash == VALID_HASH
        assert v.content == VALID_CONTENT
        assert v.status == ConstitutionalStatus.DRAFT

    def test_version_id_is_valid_uuid(self):
        v = make_version()
        UUID(v.version_id)  # raises if invalid

    def test_version_id_auto_generated(self):
        v1 = make_version()
        v2 = make_version()
        assert v1.version_id != v2.version_id

    def test_explicit_version_id(self):
        vid = "abc-123"
        v = make_version(version_id=vid)
        assert v.version_id == vid

    def test_created_at_is_utc_datetime(self):
        v = make_version()
        assert isinstance(v.created_at, datetime)
        assert v.created_at.tzinfo is not None

    def test_activated_at_and_deactivated_at_default_none(self):
        v = make_version()
        assert v.activated_at is None
        assert v.deactivated_at is None

    def test_predecessor_version_default_none(self):
        v = make_version()
        assert v.predecessor_version is None

    def test_predecessor_version_explicit(self):
        v = make_version(predecessor_version="previous-id-999")
        assert v.predecessor_version == "previous-id-999"

    def test_metadata_defaults_to_empty_dict(self):
        v = make_version()
        assert v.metadata == {}

    def test_metadata_explicit(self):
        meta = {"author": "alice", "justification": "security patch"}
        v = make_version(metadata=meta)
        assert v.metadata == meta

    def test_default_hash_is_constitutional_hash(self):
        # When no hash supplied, default should equal CONSTITUTIONAL_HASH constant
        v = ConstitutionalVersion(version=VALID_VERSION, content=VALID_CONTENT)
        assert v.constitutional_hash == VALID_HASH

    def test_explicit_status(self):
        v = make_version(status=ConstitutionalStatus.PROPOSED)
        assert v.status == ConstitutionalStatus.PROPOSED

    def test_all_statuses_accepted(self):
        for status in ConstitutionalStatus:
            v = make_version(status=status)
            assert v.status == status


# ---------------------------------------------------------------------------
# Semantic version validation
# ---------------------------------------------------------------------------


class TestSemanticVersionValidation:
    @pytest.mark.parametrize("ver", ["0.0.0", "1.0.0", "10.20.30", "999.0.1"])
    def test_valid_versions_accepted(self, ver: str):
        v = make_version(version=ver)
        assert v.version == ver

    @pytest.mark.parametrize(
        "bad_ver",
        [
            "1.0",
            "1",
            "1.0.0.0",
            "a.b.c",
            "1.0.x",
            "",
            "v1.0.0",
        ],
    )
    def test_invalid_version_format_raises(self, bad_ver: str):
        with pytest.raises(ValidationError):
            make_version(version=bad_ver)

    def test_negative_version_numbers_raise(self):
        # The regex itself blocks negative numbers since it matches \d+
        # but explicit negative test to confirm behaviour
        with pytest.raises(ValidationError):
            make_version(version="-1.0.0")

    def test_version_parts_are_integers(self):
        v = make_version(version="3.14.15")
        assert v.major_version == 3
        assert v.minor_version == 14
        assert v.patch_version == 15


# ---------------------------------------------------------------------------
# Hash format validation
# ---------------------------------------------------------------------------


class TestHashFormatValidation:
    def test_valid_16_hex_hash(self):
        v = make_version(constitutional_hash=VALID_HASH)
        assert v.constitutional_hash == VALID_HASH

    @pytest.mark.parametrize(
        "bad_hash",
        [
            "",  # empty
            "608508a9bd22429",  # 15 chars
            "608508a9bd2242901",  # 17 chars
            "608508a9bd22429X",  # non-hex char
            CONSTITUTIONAL_HASH.upper(),  # uppercase
        ],
    )
    def test_invalid_hash_raises(self, bad_hash: str):
        with pytest.raises(ValidationError):
            make_version(constitutional_hash=bad_hash)

    def test_all_hex_chars_accepted(self):
        # 16-char string with every hex digit
        valid = "0123456789abcdef"
        v = make_version(constitutional_hash=valid)
        assert v.constitutional_hash == valid


# ---------------------------------------------------------------------------
# Status properties
# ---------------------------------------------------------------------------


class TestStatusProperties:
    def test_is_draft_true_when_draft(self):
        v = make_version(status=ConstitutionalStatus.DRAFT)
        assert v.is_draft is True
        assert v.is_active is False

    def test_is_active_true_when_active(self):
        v = make_version(status=ConstitutionalStatus.ACTIVE)
        assert v.is_active is True
        assert v.is_draft is False

    def test_is_proposed(self):
        v = make_version(status=ConstitutionalStatus.PROPOSED)
        assert v.is_proposed is True

    def test_is_under_review(self):
        v = make_version(status=ConstitutionalStatus.UNDER_REVIEW)
        assert v.is_under_review is True

    def test_is_approved(self):
        v = make_version(status=ConstitutionalStatus.APPROVED)
        assert v.is_approved is True

    def test_is_superseded(self):
        v = make_version(status=ConstitutionalStatus.SUPERSEDED)
        assert v.is_superseded is True

    def test_is_rolled_back(self):
        v = make_version(status=ConstitutionalStatus.ROLLED_BACK)
        assert v.is_rolled_back is True

    def test_is_rejected(self):
        v = make_version(status=ConstitutionalStatus.REJECTED)
        assert v.is_rejected is True

    def test_only_one_property_true_at_a_time(self):
        bool_props = [
            "is_draft",
            "is_proposed",
            "is_under_review",
            "is_approved",
            "is_active",
            "is_superseded",
            "is_rolled_back",
            "is_rejected",
        ]
        status_prop_map = {
            ConstitutionalStatus.DRAFT: "is_draft",
            ConstitutionalStatus.PROPOSED: "is_proposed",
            ConstitutionalStatus.UNDER_REVIEW: "is_under_review",
            ConstitutionalStatus.APPROVED: "is_approved",
            ConstitutionalStatus.ACTIVE: "is_active",
            ConstitutionalStatus.SUPERSEDED: "is_superseded",
            ConstitutionalStatus.ROLLED_BACK: "is_rolled_back",
            ConstitutionalStatus.REJECTED: "is_rejected",
        }
        for status, expected_prop in status_prop_map.items():
            v = make_version(status=status)
            for prop in bool_props:
                if prop == expected_prop:
                    assert getattr(v, prop) is True, f"{prop} should be True for {status}"
                else:
                    assert getattr(v, prop) is False, f"{prop} should be False for {status}"


# ---------------------------------------------------------------------------
# Semantic version tuple / part properties
# ---------------------------------------------------------------------------


class TestSemanticVersionTuple:
    def test_tuple_values(self):
        v = make_version(version="2.5.11")
        assert v.semantic_version_tuple == (2, 5, 11)

    def test_major_version(self):
        assert make_version(version="7.0.0").major_version == 7

    def test_minor_version(self):
        assert make_version(version="0.3.0").minor_version == 3

    def test_patch_version(self):
        assert make_version(version="0.0.9").patch_version == 9

    def test_zero_version(self):
        v = make_version(version="0.0.0")
        assert v.semantic_version_tuple == (0, 0, 0)
        assert v.major_version == 0
        assert v.minor_version == 0
        assert v.patch_version == 0


# ---------------------------------------------------------------------------
# activate()
# ---------------------------------------------------------------------------


class TestActivate:
    def test_activate_sets_status_to_active(self):
        v = make_version()
        v.activate()
        assert v.status == ConstitutionalStatus.ACTIVE

    def test_activate_sets_activated_at(self):
        v = make_version()
        before = datetime.now(UTC)
        v.activate()
        after = datetime.now(UTC)
        assert v.activated_at is not None
        assert before <= v.activated_at <= after

    def test_activate_does_not_overwrite_existing_activated_at(self):
        existing_ts = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        v = make_version(
            status=ConstitutionalStatus.ACTIVE,
            activated_at=existing_ts,
        )
        v.activate()
        assert v.activated_at == existing_ts

    def test_activate_from_draft(self):
        v = make_version(status=ConstitutionalStatus.DRAFT)
        v.activate()
        assert v.is_active

    def test_activate_idempotent_status(self):
        v = make_version()
        v.activate()
        first_ts = v.activated_at
        v.activate()
        assert v.activated_at == first_ts
        assert v.is_active


# ---------------------------------------------------------------------------
# deactivate()
# ---------------------------------------------------------------------------


class TestDeactivate:
    def test_deactivate_defaults_to_superseded(self):
        v = make_version(status=ConstitutionalStatus.ACTIVE)
        v.deactivate()
        assert v.status == ConstitutionalStatus.SUPERSEDED

    def test_deactivate_superseded_reason(self):
        v = make_version(status=ConstitutionalStatus.ACTIVE)
        v.deactivate(reason="superseded")
        assert v.status == ConstitutionalStatus.SUPERSEDED

    def test_deactivate_rolled_back_reason(self):
        v = make_version(status=ConstitutionalStatus.ACTIVE)
        v.deactivate(reason="rolled_back")
        assert v.status == ConstitutionalStatus.ROLLED_BACK

    def test_deactivate_unknown_reason_defaults_to_superseded(self):
        v = make_version(status=ConstitutionalStatus.ACTIVE)
        v.deactivate(reason="other_reason")
        assert v.status == ConstitutionalStatus.SUPERSEDED

    def test_deactivate_sets_deactivated_at(self):
        v = make_version(status=ConstitutionalStatus.ACTIVE)
        before = datetime.now(UTC)
        v.deactivate()
        after = datetime.now(UTC)
        assert v.deactivated_at is not None
        assert before <= v.deactivated_at <= after

    def test_deactivate_does_not_overwrite_existing_deactivated_at(self):
        existing_ts = datetime(2024, 6, 15, 8, 0, 0, tzinfo=UTC)
        v = make_version(
            status=ConstitutionalStatus.ACTIVE,
            deactivated_at=existing_ts,
        )
        v.deactivate()
        assert v.deactivated_at == existing_ts

    def test_deactivate_idempotent_timestamp(self):
        v = make_version(status=ConstitutionalStatus.ACTIVE)
        v.deactivate()
        first_ts = v.deactivated_at
        v.deactivate()
        assert v.deactivated_at == first_ts


# ---------------------------------------------------------------------------
# to_dict / serialization
# ---------------------------------------------------------------------------


class TestToDict:
    def test_to_dict_returns_dict(self):
        v = make_version()
        d = v.to_dict()
        assert isinstance(d, dict)

    def test_to_dict_contains_expected_keys(self):
        v = make_version()
        d = v.to_dict()
        expected_keys = {
            "version_id",
            "version",
            "constitutional_hash",
            "content",
            "predecessor_version",
            "status",
            "metadata",
            "created_at",
            "activated_at",
            "deactivated_at",
        }
        assert expected_keys.issubset(d.keys())

    def test_to_dict_status_is_string(self):
        v = make_version()
        d = v.to_dict()
        assert isinstance(d["status"], str)

    def test_to_dict_timestamps_serialized(self):
        v = make_version()
        v.activate()
        v.deactivate()
        d = v.to_dict()
        # Pydantic model_dump with field_serializer should handle datetime
        # The values may be datetime objects or ISO strings depending on dump mode
        assert d["created_at"] is not None

    def test_to_dict_none_timestamps_remain_none(self):
        v = make_version()
        d = v.to_dict()
        assert d["activated_at"] is None
        assert d["deactivated_at"] is None

    def test_roundtrip_via_model_dump(self):
        v = make_version(version="2.0.1", metadata={"key": "val"})
        d = v.to_dict()
        assert d["version"] == "2.0.1"
        assert d["metadata"] == {"key": "val"}


# ---------------------------------------------------------------------------
# Datetime serializer
# ---------------------------------------------------------------------------


class TestDatetimeSerializer:
    def test_serialize_datetime_none_returns_none(self):
        v = make_version()
        result = v.serialize_datetime(None)
        assert result is None

    def test_serialize_datetime_returns_iso_string(self):
        v = make_version()
        dt = datetime(2025, 3, 14, 9, 26, 53, tzinfo=UTC)
        result = v.serialize_datetime(dt)
        assert isinstance(result, str)
        # Should be valid ISO format
        parsed = datetime.fromisoformat(result)
        assert parsed.year == 2025

    def test_model_serialize_created_at(self):
        v = make_version()
        # Use model_dump(mode='json') to trigger field_serializer
        d = v.model_dump(mode="json")
        assert isinstance(d["created_at"], str)

    def test_model_serialize_activated_at_none(self):
        v = make_version()
        d = v.model_dump(mode="json")
        assert d["activated_at"] is None

    def test_model_serialize_activated_at_set(self):
        v = make_version()
        v.activate()
        d = v.model_dump(mode="json")
        assert isinstance(d["activated_at"], str)

    def test_model_serialize_deactivated_at_set(self):
        v = make_version(status=ConstitutionalStatus.ACTIVE)
        v.deactivate()
        d = v.model_dump(mode="json")
        assert isinstance(d["deactivated_at"], str)


# ---------------------------------------------------------------------------
# __repr__
# ---------------------------------------------------------------------------


class TestRepr:
    def test_repr_contains_version_id(self):
        v = make_version()
        r = repr(v)
        assert v.version_id in r

    def test_repr_contains_version(self):
        v = make_version(version="3.2.1")
        r = repr(v)
        assert "3.2.1" in r

    def test_repr_contains_hash(self):
        v = make_version()
        r = repr(v)
        assert VALID_HASH in r

    def test_repr_contains_status(self):
        v = make_version(status=ConstitutionalStatus.PROPOSED)
        r = repr(v)
        assert "proposed" in r

    def test_repr_format(self):
        v = make_version()
        r = repr(v)
        assert r.startswith("ConstitutionalVersion(")
        assert r.endswith(")")


# ---------------------------------------------------------------------------
# Edge cases and misc
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_content_can_be_nested_dict(self):
        content = {
            "opa_policies": {"allow": "true"},
            "principles": ["p1", "p2"],
            "metadata": {"source": "governance-v2"},
        }
        v = make_version(content=content)
        assert v.content == content

    def test_version_id_empty_string_gets_replaced(self):
        # __init__ replaces empty version_id with uuid
        # NOTE: pydantic may or may not allow empty string before __init__ runs
        v = ConstitutionalVersion(
            version=VALID_VERSION,
            constitutional_hash=VALID_HASH,
            content=VALID_CONTENT,
            version_id="",
        )
        # After __init__, version_id should be truthy (uuid generated)
        assert v.version_id  # non-empty after replacement

    def test_activate_then_deactivate_lifecycle(self):
        v = make_version()
        assert v.is_draft
        v.activate()
        assert v.is_active
        v.deactivate(reason="superseded")
        assert v.is_superseded
        assert v.activated_at is not None
        assert v.deactivated_at is not None

    def test_full_rollback_lifecycle(self):
        v = make_version()
        v.activate()
        v.deactivate(reason="rolled_back")
        assert v.is_rolled_back
        assert v.deactivated_at is not None

    def test_constitutional_hash_constant_is_imported(self):
        from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

        v = ConstitutionalVersion(version=VALID_VERSION, content=VALID_CONTENT)
        assert v.constitutional_hash == CONSTITUTIONAL_HASH

    def test_version_with_all_timestamps(self):
        ts = datetime(2025, 1, 1, tzinfo=UTC)
        v = make_version(
            status=ConstitutionalStatus.SUPERSEDED,
            created_at=ts,
            activated_at=ts,
            deactivated_at=ts,
        )
        assert v.created_at == ts
        assert v.activated_at == ts
        assert v.deactivated_at == ts

    def test_large_version_numbers(self):
        v = make_version(version="100.200.300")
        assert v.semantic_version_tuple == (100, 200, 300)

    def test_version_zero_zero_zero(self):
        v = make_version(version="0.0.0")
        assert v.semantic_version_tuple == (0, 0, 0)

    def test_model_schema_includes_version_field(self):
        schema = ConstitutionalVersion.model_json_schema()
        assert "version" in schema.get("properties", {})

    def test_predecessor_version_set_correctly(self):
        parent = make_version(version="1.0.0")
        child = make_version(
            version="1.1.0",
            predecessor_version=parent.version_id,
        )
        assert child.predecessor_version == parent.version_id
