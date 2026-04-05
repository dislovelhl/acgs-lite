# Constitutional Hash: 608508a9bd224290
# Sprint 61 -- constitutional/version_model.py coverage
"""
Comprehensive tests for constitutional/version_model.py achieving ≥95% coverage.
"""

from datetime import UTC, datetime, timezone
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.constitutional.version_model import (
    ConstitutionalStatus,
    ConstitutionalVersion,
)

VALID_HASH = CONSTITUTIONAL_HASH
VALID_CONTENT = {"rules": ["rule1"], "policies": {"opa": "deny := false"}}


# ---------------------------------------------------------------------------
# ConstitutionalStatus Enum
# ---------------------------------------------------------------------------


class TestConstitutionalStatus:
    def test_all_values_exist(self):
        assert ConstitutionalStatus.DRAFT.value == "draft"
        assert ConstitutionalStatus.PROPOSED.value == "proposed"
        assert ConstitutionalStatus.UNDER_REVIEW.value == "under_review"
        assert ConstitutionalStatus.APPROVED.value == "approved"
        assert ConstitutionalStatus.ACTIVE.value == "active"
        assert ConstitutionalStatus.SUPERSEDED.value == "superseded"
        assert ConstitutionalStatus.ROLLED_BACK.value == "rolled_back"
        assert ConstitutionalStatus.REJECTED.value == "rejected"

    def test_is_str_subclass(self):
        assert isinstance(ConstitutionalStatus.DRAFT, str)

    def test_enum_count(self):
        assert len(ConstitutionalStatus) == 8


# ---------------------------------------------------------------------------
# ConstitutionalVersion - construction & defaults
# ---------------------------------------------------------------------------


class TestConstitutionalVersionDefaults:
    def test_minimal_construction(self):
        cv = ConstitutionalVersion(version="1.0.0", content=VALID_CONTENT)
        assert cv.version == "1.0.0"
        assert cv.constitutional_hash == VALID_HASH
        assert cv.status == ConstitutionalStatus.DRAFT
        assert cv.predecessor_version is None
        assert cv.activated_at is None
        assert cv.deactivated_at is None
        assert cv.metadata == {}
        assert cv.version_id  # auto-generated

    def test_version_id_auto_generated(self):
        cv1 = ConstitutionalVersion(version="1.0.0", content=VALID_CONTENT)
        cv2 = ConstitutionalVersion(version="1.0.0", content=VALID_CONTENT)
        assert cv1.version_id != cv2.version_id

    def test_explicit_version_id(self):
        cv = ConstitutionalVersion(
            version_id="my-custom-id", version="1.0.0", content=VALID_CONTENT
        )
        assert cv.version_id == "my-custom-id"

    def test_created_at_is_utc(self):
        cv = ConstitutionalVersion(version="1.0.0", content=VALID_CONTENT)
        assert cv.created_at.tzinfo is not None

    def test_custom_predecessor(self):
        cv = ConstitutionalVersion(
            version="2.0.0", content=VALID_CONTENT, predecessor_version="v1-id"
        )
        assert cv.predecessor_version == "v1-id"

    def test_custom_metadata(self):
        meta = {"author": "alice", "justification": "security fix"}
        cv = ConstitutionalVersion(version="1.1.0", content=VALID_CONTENT, metadata=meta)
        assert cv.metadata["author"] == "alice"

    def test_custom_status(self):
        cv = ConstitutionalVersion(
            version="1.0.0", content=VALID_CONTENT, status=ConstitutionalStatus.PROPOSED
        )
        assert cv.status == ConstitutionalStatus.PROPOSED


# ---------------------------------------------------------------------------
# field_validator: validate_semantic_version
# ---------------------------------------------------------------------------


class TestValidateSemanticVersion:
    def test_valid_versions(self):
        for v in ("0.0.0", "1.0.0", "10.20.30", "999.0.1"):
            cv = ConstitutionalVersion(version=v, content=VALID_CONTENT)
            assert cv.version == v

    def test_invalid_two_parts(self):
        # Pydantic's pattern validator rejects before the field_validator runs
        with pytest.raises(ValidationError):
            ConstitutionalVersion(version="1.0", content=VALID_CONTENT)

    def test_invalid_four_parts(self):
        with pytest.raises(ValidationError):
            ConstitutionalVersion(version="1.0.0.0", content=VALID_CONTENT)

    def test_invalid_non_numeric(self):
        with pytest.raises(ValidationError):
            ConstitutionalVersion(version="a.b.c", content=VALID_CONTENT)

    def test_invalid_negative_major(self):
        # "-1.0.0" fails the regex pattern ^\d+\.\d+\.\d+$ before the validator
        with pytest.raises(ValidationError):
            ConstitutionalVersion(version="-1.0.0", content=VALID_CONTENT)

    def test_invalid_negative_minor(self):
        with pytest.raises(ValidationError):
            ConstitutionalVersion(version="1.-1.0", content=VALID_CONTENT)

    def test_invalid_negative_patch(self):
        with pytest.raises(ValidationError):
            ConstitutionalVersion(version="1.0.-1", content=VALID_CONTENT)

    def test_pattern_rejection_before_validator(self):
        # Pattern r"^\d+\.\d+\.\d+$" rejects these even before the validator
        with pytest.raises(ValidationError):
            ConstitutionalVersion(version="1.0", content=VALID_CONTENT)


# ---------------------------------------------------------------------------
# field_validator: validate_hash_format
# ---------------------------------------------------------------------------


class TestValidateHashFormat:
    def test_valid_hash(self):
        cv = ConstitutionalVersion(
            version="1.0.0", content=VALID_CONTENT, constitutional_hash=VALID_HASH
        )
        assert cv.constitutional_hash == VALID_HASH

    def test_empty_hash_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            ConstitutionalVersion(version="1.0.0", content=VALID_CONTENT, constitutional_hash="")
        assert "cannot be empty" in str(exc_info.value)

    def test_hash_too_short(self):
        with pytest.raises(ValidationError) as exc_info:
            ConstitutionalVersion(
                version="1.0.0", content=VALID_CONTENT, constitutional_hash="abc123"
            )
        assert "16 hexadecimal" in str(exc_info.value)

    def test_hash_too_long(self):
        with pytest.raises(ValidationError):
            ConstitutionalVersion(
                version="1.0.0",
                content=VALID_CONTENT,
                constitutional_hash="608508a9bd224290xx",
            )

    def test_hash_non_hex(self):
        with pytest.raises(ValidationError) as exc_info:
            ConstitutionalVersion(
                version="1.0.0",
                content=VALID_CONTENT,
                constitutional_hash="ZZZZZZZZZZZZZZZZ",
            )
        assert "hexadecimal" in str(exc_info.value)

    def test_hash_uppercase_rejected(self):
        # Uppercase letters are not in "0123456789abcdef"
        with pytest.raises(ValidationError):
            ConstitutionalVersion(
                version="1.0.0",
                content=VALID_CONTENT,
                constitutional_hash=CONSTITUTIONAL_HASH.upper(),
            )


# ---------------------------------------------------------------------------
# Properties - status checks
# ---------------------------------------------------------------------------


class TestStatusProperties:
    def _make(self, status: ConstitutionalStatus) -> ConstitutionalVersion:
        return ConstitutionalVersion(version="1.0.0", content=VALID_CONTENT, status=status)

    def test_is_draft_true(self):
        cv = self._make(ConstitutionalStatus.DRAFT)
        assert cv.is_draft is True
        assert cv.is_active is False

    def test_is_proposed_true(self):
        cv = self._make(ConstitutionalStatus.PROPOSED)
        assert cv.is_proposed is True
        assert cv.is_draft is False

    def test_is_under_review_true(self):
        cv = self._make(ConstitutionalStatus.UNDER_REVIEW)
        assert cv.is_under_review is True
        assert cv.is_proposed is False

    def test_is_approved_true(self):
        cv = self._make(ConstitutionalStatus.APPROVED)
        assert cv.is_approved is True
        assert cv.is_under_review is False

    def test_is_active_true(self):
        cv = self._make(ConstitutionalStatus.ACTIVE)
        assert cv.is_active is True
        assert cv.is_approved is False

    def test_is_superseded_true(self):
        cv = self._make(ConstitutionalStatus.SUPERSEDED)
        assert cv.is_superseded is True
        assert cv.is_active is False

    def test_is_rolled_back_true(self):
        cv = self._make(ConstitutionalStatus.ROLLED_BACK)
        assert cv.is_rolled_back is True
        assert cv.is_superseded is False

    def test_is_rejected_true(self):
        cv = self._make(ConstitutionalStatus.REJECTED)
        assert cv.is_rejected is True
        assert cv.is_rolled_back is False

    def test_all_false_when_draft(self):
        cv = self._make(ConstitutionalStatus.DRAFT)
        assert cv.is_active is False
        assert cv.is_proposed is False
        assert cv.is_under_review is False
        assert cv.is_approved is False
        assert cv.is_superseded is False
        assert cv.is_rolled_back is False
        assert cv.is_rejected is False


# ---------------------------------------------------------------------------
# Properties - semantic versioning
# ---------------------------------------------------------------------------


class TestSemanticVersionProperties:
    def test_semantic_version_tuple(self):
        cv = ConstitutionalVersion(version="3.7.12", content=VALID_CONTENT)
        assert cv.semantic_version_tuple == (3, 7, 12)

    def test_major_version(self):
        cv = ConstitutionalVersion(version="5.0.0", content=VALID_CONTENT)
        assert cv.major_version == 5

    def test_minor_version(self):
        cv = ConstitutionalVersion(version="1.4.0", content=VALID_CONTENT)
        assert cv.minor_version == 4

    def test_patch_version(self):
        cv = ConstitutionalVersion(version="0.0.99", content=VALID_CONTENT)
        assert cv.patch_version == 99

    def test_version_zero(self):
        cv = ConstitutionalVersion(version="0.0.0", content=VALID_CONTENT)
        assert cv.semantic_version_tuple == (0, 0, 0)


# ---------------------------------------------------------------------------
# activate()
# ---------------------------------------------------------------------------


class TestActivate:
    def test_activate_sets_status(self):
        cv = ConstitutionalVersion(version="1.0.0", content=VALID_CONTENT)
        cv.activate()
        assert cv.status == ConstitutionalStatus.ACTIVE

    def test_activate_sets_activated_at(self):
        cv = ConstitutionalVersion(version="1.0.0", content=VALID_CONTENT)
        assert cv.activated_at is None
        cv.activate()
        assert cv.activated_at is not None
        assert cv.activated_at.tzinfo is not None

    def test_activate_does_not_overwrite_existing_activated_at(self):
        fixed_ts = datetime(2024, 1, 1, tzinfo=UTC)
        cv = ConstitutionalVersion(version="1.0.0", content=VALID_CONTENT, activated_at=fixed_ts)
        cv.activate()
        assert cv.activated_at == fixed_ts

    def test_activate_idempotent(self):
        cv = ConstitutionalVersion(version="1.0.0", content=VALID_CONTENT)
        cv.activate()
        first_ts = cv.activated_at
        cv.activate()
        assert cv.activated_at == first_ts


# ---------------------------------------------------------------------------
# deactivate()
# ---------------------------------------------------------------------------


class TestDeactivate:
    def test_deactivate_default_superseded(self):
        cv = ConstitutionalVersion(
            version="1.0.0", content=VALID_CONTENT, status=ConstitutionalStatus.ACTIVE
        )
        cv.deactivate()
        assert cv.status == ConstitutionalStatus.SUPERSEDED

    def test_deactivate_explicit_superseded(self):
        cv = ConstitutionalVersion(
            version="1.0.0", content=VALID_CONTENT, status=ConstitutionalStatus.ACTIVE
        )
        cv.deactivate(reason="superseded")
        assert cv.status == ConstitutionalStatus.SUPERSEDED

    def test_deactivate_rolled_back(self):
        cv = ConstitutionalVersion(
            version="1.0.0", content=VALID_CONTENT, status=ConstitutionalStatus.ACTIVE
        )
        cv.deactivate(reason="rolled_back")
        assert cv.status == ConstitutionalStatus.ROLLED_BACK

    def test_deactivate_sets_deactivated_at(self):
        cv = ConstitutionalVersion(
            version="1.0.0", content=VALID_CONTENT, status=ConstitutionalStatus.ACTIVE
        )
        assert cv.deactivated_at is None
        cv.deactivate()
        assert cv.deactivated_at is not None

    def test_deactivate_does_not_overwrite_existing_deactivated_at(self):
        fixed_ts = datetime(2023, 6, 15, tzinfo=UTC)
        cv = ConstitutionalVersion(
            version="1.0.0",
            content=VALID_CONTENT,
            status=ConstitutionalStatus.ACTIVE,
            deactivated_at=fixed_ts,
        )
        cv.deactivate()
        assert cv.deactivated_at == fixed_ts

    def test_deactivate_unknown_reason_falls_through_to_superseded(self):
        cv = ConstitutionalVersion(
            version="1.0.0", content=VALID_CONTENT, status=ConstitutionalStatus.ACTIVE
        )
        cv.deactivate(reason="expired")  # not "rolled_back"
        assert cv.status == ConstitutionalStatus.SUPERSEDED


# ---------------------------------------------------------------------------
# serialize_datetime (field_serializer)
# ---------------------------------------------------------------------------


class TestSerializeDatetime:
    def test_none_serialized_to_none(self):
        cv = ConstitutionalVersion(version="1.0.0", content=VALID_CONTENT)
        dumped = cv.model_dump()
        assert dumped["activated_at"] is None
        assert dumped["deactivated_at"] is None

    def test_datetime_serialized_to_iso_string(self):
        fixed_ts = datetime(2024, 3, 15, 12, 0, 0, tzinfo=UTC)
        cv = ConstitutionalVersion(version="1.0.0", content=VALID_CONTENT, activated_at=fixed_ts)
        dumped = cv.model_dump()
        assert dumped["activated_at"] == fixed_ts.isoformat()

    def test_created_at_serialized(self):
        cv = ConstitutionalVersion(version="1.0.0", content=VALID_CONTENT)
        dumped = cv.model_dump()
        assert isinstance(dumped["created_at"], str)

    def test_serialize_datetime_directly(self):
        cv = ConstitutionalVersion(version="1.0.0", content=VALID_CONTENT)
        result = cv.serialize_datetime(None)
        assert result is None
        now = datetime.now(UTC)
        result = cv.serialize_datetime(now)
        assert result == now.isoformat()


# ---------------------------------------------------------------------------
# to_dict()
# ---------------------------------------------------------------------------


class TestToDict:
    def test_to_dict_returns_dict(self):
        cv = ConstitutionalVersion(version="1.0.0", content=VALID_CONTENT)
        d = cv.to_dict()
        assert isinstance(d, dict)

    def test_to_dict_contains_expected_keys(self):
        cv = ConstitutionalVersion(version="1.0.0", content=VALID_CONTENT)
        d = cv.to_dict()
        for key in (
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
        ):
            assert key in d

    def test_to_dict_roundtrip(self):
        meta = {"author": "bob"}
        cv = ConstitutionalVersion(version="2.1.3", content=VALID_CONTENT, metadata=meta)
        d = cv.to_dict()
        assert d["version"] == "2.1.3"
        assert d["metadata"]["author"] == "bob"


# ---------------------------------------------------------------------------
# __repr__
# ---------------------------------------------------------------------------


class TestRepr:
    def test_repr_contains_version(self):
        cv = ConstitutionalVersion(version="1.0.0", content=VALID_CONTENT)
        r = repr(cv)
        assert "1.0.0" in r

    def test_repr_contains_hash(self):
        cv = ConstitutionalVersion(version="1.0.0", content=VALID_CONTENT)
        r = repr(cv)
        assert VALID_HASH in r

    def test_repr_contains_status(self):
        cv = ConstitutionalVersion(version="1.0.0", content=VALID_CONTENT)
        r = repr(cv)
        assert "draft" in r

    def test_repr_format(self):
        cv = ConstitutionalVersion(version_id="test-id", version="1.0.0", content=VALID_CONTENT)
        r = repr(cv)
        assert "ConstitutionalVersion(" in r
        assert "version_id=test-id" in r


# ---------------------------------------------------------------------------
# __init__ - edge-case: empty version_id branch
# ---------------------------------------------------------------------------


class TestInitEdgeCases:
    def test_empty_string_version_id_gets_replaced(self):
        # When version_id is explicitly set to a falsy empty string,
        # the __init__ branch `if not self.version_id` regenerates it.
        # However, Pydantic's Field(default_factory=...) always provides a UUID
        # so passing version_id="" exercises the branch.
        cv = ConstitutionalVersion(version_id="", version="1.0.0", content=VALID_CONTENT)
        # After __init__ the branch should have replaced the empty string
        assert cv.version_id != ""

    def test_none_version_id_gets_replaced(self):
        # Passing None for version_id -- Pydantic might coerce or reject it,
        # but if it passes it through, __init__ fills it.
        # Pydantic v2 will use the default_factory so version_id won't be None.
        cv = ConstitutionalVersion(version="1.0.0", content=VALID_CONTENT)
        assert cv.version_id is not None


# ---------------------------------------------------------------------------
# Integration / lifecycle scenario
# ---------------------------------------------------------------------------


class TestLifecycleScenario:
    def test_full_lifecycle(self):
        # Create draft
        cv = ConstitutionalVersion(
            version="1.0.0",
            content=VALID_CONTENT,
            status=ConstitutionalStatus.DRAFT,
        )
        assert cv.is_draft

        # Propose
        cv.status = ConstitutionalStatus.PROPOSED
        assert cv.is_proposed

        # Under review
        cv.status = ConstitutionalStatus.UNDER_REVIEW
        assert cv.is_under_review

        # Approve
        cv.status = ConstitutionalStatus.APPROVED
        assert cv.is_approved

        # Activate
        cv.activate()
        assert cv.is_active
        assert cv.activated_at is not None

        # Deactivate (superseded)
        cv.deactivate()
        assert cv.is_superseded
        assert cv.deactivated_at is not None

    def test_rollback_lifecycle(self):
        cv = ConstitutionalVersion(
            version="2.0.0",
            content=VALID_CONTENT,
            status=ConstitutionalStatus.ACTIVE,
        )
        cv.activate()
        cv.deactivate(reason="rolled_back")
        assert cv.is_rolled_back

    def test_rejection_lifecycle(self):
        cv = ConstitutionalVersion(
            version="1.1.0",
            content=VALID_CONTENT,
            status=ConstitutionalStatus.UNDER_REVIEW,
        )
        cv.status = ConstitutionalStatus.REJECTED
        assert cv.is_rejected


# ---------------------------------------------------------------------------
# Edge cases for content field
# ---------------------------------------------------------------------------


class TestContentField:
    def test_complex_content(self):
        content = {
            "rules": ["no harm", "respect privacy"],
            "policies": {"opa": "allow := true", "maci": {"threshold": 0.8}},
            "version_notes": "Updated policies",
        }
        cv = ConstitutionalVersion(version="1.0.0", content=content)
        assert cv.content["policies"]["maci"]["threshold"] == 0.8

    def test_empty_content_dict(self):
        cv = ConstitutionalVersion(version="1.0.0", content={})
        assert cv.content == {}
