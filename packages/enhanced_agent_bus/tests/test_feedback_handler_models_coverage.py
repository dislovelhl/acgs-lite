# Constitutional Hash: 608508a9bd224290
"""
Comprehensive tests for src/core/enhanced_agent_bus/feedback_handler/models.py

Target: ≥95% line coverage of feedback_handler/models.py (83 stmts)
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timezone

import pytest
from pydantic import ValidationError

from enhanced_agent_bus.feedback_handler.enums import FeedbackType, OutcomeStatus
from enhanced_agent_bus.feedback_handler.models import (
    FeedbackBatchRequest,
    FeedbackBatchResponse,
    FeedbackEvent,
    FeedbackQueryParams,
    FeedbackResponse,
    FeedbackStats,
    StoredFeedbackEvent,
)
from enhanced_agent_bus.observability.structured_logging import get_logger

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_event(**kwargs) -> FeedbackEvent:
    """Create a minimal valid FeedbackEvent, optionally overriding fields."""
    defaults = {
        "decision_id": "dec-001",
        "feedback_type": FeedbackType.POSITIVE,
    }
    defaults.update(kwargs)
    return FeedbackEvent(**defaults)


def make_stored(
    id: str = "sfb-001",
    decision_id: str = "dec-001",
    feedback_type: FeedbackType = FeedbackType.POSITIVE,
    outcome: OutcomeStatus = OutcomeStatus.SUCCESS,
    **kwargs,
) -> StoredFeedbackEvent:
    defaults = dict(
        id=id,
        decision_id=decision_id,
        feedback_type=feedback_type,
        outcome=outcome,
        user_id=None,
        tenant_id=None,
        comment=None,
        correction_data=None,
        features=None,
        actual_impact=None,
        metadata=None,
        created_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
    )
    defaults.update(kwargs)
    return StoredFeedbackEvent(**defaults)


# ===========================================================================
# FeedbackType enum
# ===========================================================================


class TestFeedbackTypeEnum:
    def test_positive_value(self):
        assert FeedbackType.POSITIVE == "positive"

    def test_negative_value(self):
        assert FeedbackType.NEGATIVE == "negative"

    def test_neutral_value(self):
        assert FeedbackType.NEUTRAL == "neutral"

    def test_correction_value(self):
        assert FeedbackType.CORRECTION == "correction"

    def test_is_str_subclass(self):
        assert isinstance(FeedbackType.POSITIVE, str)

    def test_all_members(self):
        members = {m.value for m in FeedbackType}
        assert members == {"positive", "negative", "neutral", "correction"}


# ===========================================================================
# OutcomeStatus enum
# ===========================================================================


class TestOutcomeStatusEnum:
    def test_success_value(self):
        assert OutcomeStatus.SUCCESS == "success"

    def test_failure_value(self):
        assert OutcomeStatus.FAILURE == "failure"

    def test_partial_value(self):
        assert OutcomeStatus.PARTIAL == "partial"

    def test_unknown_value(self):
        assert OutcomeStatus.UNKNOWN == "unknown"

    def test_is_str_subclass(self):
        assert isinstance(OutcomeStatus.SUCCESS, str)

    def test_all_members(self):
        members = {m.value for m in OutcomeStatus}
        assert members == {"success", "failure", "partial", "unknown"}


# ===========================================================================
# FeedbackEvent — construction
# ===========================================================================


class TestFeedbackEventConstruction:
    def test_minimal_valid(self):
        ev = make_event()
        assert ev.decision_id == "dec-001"
        assert ev.feedback_type == FeedbackType.POSITIVE
        assert ev.outcome == OutcomeStatus.UNKNOWN

    def test_outcome_default_is_unknown(self):
        ev = make_event()
        assert ev.outcome == OutcomeStatus.UNKNOWN

    def test_optional_fields_default_none(self):
        ev = make_event()
        assert ev.user_id is None
        assert ev.tenant_id is None
        assert ev.comment is None
        assert ev.correction_data is None
        assert ev.features is None
        assert ev.actual_impact is None
        assert ev.metadata is None

    def test_all_fields_set(self):
        ev = make_event(
            decision_id="dec-42",
            feedback_type=FeedbackType.CORRECTION,
            outcome=OutcomeStatus.FAILURE,
            user_id="user-1",
            tenant_id="tenant-1",
            comment="Something went wrong",
            correction_data={"action": "block"},
            features={"score": 0.9},
            actual_impact=0.75,
            metadata={"source": "ui"},
        )
        assert ev.decision_id == "dec-42"
        assert ev.feedback_type == FeedbackType.CORRECTION
        assert ev.outcome == OutcomeStatus.FAILURE
        assert ev.user_id == "user-1"
        assert ev.tenant_id == "tenant-1"
        assert ev.comment == "Something went wrong"
        assert ev.correction_data == {"action": "block"}
        assert ev.features == {"score": 0.9}
        assert ev.actual_impact == 0.75
        assert ev.metadata == {"source": "ui"}

    def test_negative_feedback_type(self):
        ev = make_event(feedback_type=FeedbackType.NEGATIVE)
        assert ev.feedback_type == FeedbackType.NEGATIVE

    def test_neutral_feedback_type(self):
        ev = make_event(feedback_type=FeedbackType.NEUTRAL)
        assert ev.feedback_type == FeedbackType.NEUTRAL

    def test_outcome_success(self):
        ev = make_event(outcome=OutcomeStatus.SUCCESS)
        assert ev.outcome == OutcomeStatus.SUCCESS

    def test_outcome_failure(self):
        ev = make_event(outcome=OutcomeStatus.FAILURE)
        assert ev.outcome == OutcomeStatus.FAILURE

    def test_outcome_partial(self):
        ev = make_event(outcome=OutcomeStatus.PARTIAL)
        assert ev.outcome == OutcomeStatus.PARTIAL

    def test_decision_id_stripped(self):
        ev = make_event(decision_id="  dec-001  ")
        assert ev.decision_id == "dec-001"

    def test_decision_id_leading_space_stripped(self):
        ev = make_event(decision_id="  dec-2")
        assert ev.decision_id == "dec-2"

    def test_decision_id_max_length(self):
        long_id = "x" * 255
        ev = make_event(decision_id=long_id)
        assert len(ev.decision_id) == 255

    def test_actual_impact_zero(self):
        ev = make_event(actual_impact=0.0)
        assert ev.actual_impact == 0.0

    def test_actual_impact_one(self):
        ev = make_event(actual_impact=1.0)
        assert ev.actual_impact == 1.0

    def test_actual_impact_middle(self):
        ev = make_event(actual_impact=0.5)
        assert ev.actual_impact == 0.5


# ===========================================================================
# FeedbackEvent — field validators (validation errors)
# ===========================================================================


class TestFeedbackEventValidation:
    def test_decision_id_empty_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            make_event(decision_id="")
        assert (
            "decision_id" in str(exc_info.value).lower()
            or "min_length" in str(exc_info.value).lower()
        )

    def test_decision_id_whitespace_only_raises(self):
        with pytest.raises(ValidationError):
            make_event(decision_id="   ")

    def test_decision_id_single_space_raises(self):
        with pytest.raises(ValidationError):
            make_event(decision_id=" ")

    def test_decision_id_exceeds_max_length_raises(self):
        with pytest.raises(ValidationError):
            make_event(decision_id="x" * 256)

    def test_actual_impact_below_zero_raises(self):
        with pytest.raises(ValidationError):
            make_event(actual_impact=-0.01)

    def test_actual_impact_above_one_raises(self):
        with pytest.raises(ValidationError):
            make_event(actual_impact=1.01)

    def test_invalid_feedback_type_raises(self):
        with pytest.raises(ValidationError):
            make_event(feedback_type="invalid_type")  # type: ignore[arg-type]

    def test_invalid_outcome_raises(self):
        with pytest.raises(ValidationError):
            make_event(outcome="bad_outcome")  # type: ignore[arg-type]

    def test_comment_max_length_ok(self):
        ev = make_event(comment="x" * 2000)
        assert len(ev.comment) == 2000

    def test_comment_exceeds_max_length_raises(self):
        with pytest.raises(ValidationError):
            make_event(comment="x" * 2001)

    def test_user_id_max_length_ok(self):
        ev = make_event(user_id="u" * 255)
        assert len(ev.user_id) == 255

    def test_user_id_exceeds_max_length_raises(self):
        with pytest.raises(ValidationError):
            make_event(user_id="u" * 256)

    def test_tenant_id_max_length_ok(self):
        ev = make_event(tenant_id="t" * 255)
        assert len(ev.tenant_id) == 255

    def test_tenant_id_exceeds_max_length_raises(self):
        with pytest.raises(ValidationError):
            make_event(tenant_id="t" * 256)


# ===========================================================================
# FeedbackEvent — model_validator (correction_data warning)
# ===========================================================================


class TestFeedbackEventCorrectionValidator:
    def test_correction_with_correction_data_ok(self):
        ev = make_event(
            feedback_type=FeedbackType.CORRECTION,
            correction_data={"new_decision": "block"},
        )
        assert ev.feedback_type == FeedbackType.CORRECTION
        assert ev.correction_data == {"new_decision": "block"}

    def test_correction_without_correction_data_logs_warning(self, caplog):
        with caplog.at_level(logging.WARNING, logger="enhanced_agent_bus.feedback_handler.models"):
            ev = make_event(
                feedback_type=FeedbackType.CORRECTION,
                correction_data=None,
            )
        assert ev.feedback_type == FeedbackType.CORRECTION
        assert ev.correction_data is None
        # Should log a warning
        assert any("correction" in record.message.lower() for record in caplog.records)

    def test_positive_no_correction_data_no_warning(self, caplog):
        with caplog.at_level(logging.WARNING, logger="enhanced_agent_bus.feedback_handler.models"):
            make_event(feedback_type=FeedbackType.POSITIVE)
        # No warning should be emitted for non-correction types
        assert not any("correction_data" in record.message.lower() for record in caplog.records)

    def test_negative_no_correction_data_no_warning(self, caplog):
        with caplog.at_level(logging.WARNING, logger="enhanced_agent_bus.feedback_handler.models"):
            make_event(feedback_type=FeedbackType.NEGATIVE)
        assert not any("correction_data" in record.message.lower() for record in caplog.records)

    def test_neutral_no_correction_data_no_warning(self, caplog):
        with caplog.at_level(logging.WARNING, logger="enhanced_agent_bus.feedback_handler.models"):
            make_event(feedback_type=FeedbackType.NEUTRAL)
        assert not any("correction_data" in record.message.lower() for record in caplog.records)

    def test_model_validator_returns_self(self):
        # model_validator must return the FeedbackEvent instance
        ev = make_event(feedback_type=FeedbackType.CORRECTION, correction_data=None)
        assert isinstance(ev, FeedbackEvent)


# ===========================================================================
# FeedbackEvent — serialisation
# ===========================================================================


class TestFeedbackEventSerialisation:
    def test_model_dump(self):
        ev = make_event(user_id="u1")
        data = ev.model_dump()
        assert data["decision_id"] == "dec-001"
        assert data["user_id"] == "u1"
        assert data["outcome"] == OutcomeStatus.UNKNOWN

    def test_model_dump_json(self):
        ev = make_event(actual_impact=0.5)
        json_str = ev.model_dump_json()
        assert "dec-001" in json_str
        assert "0.5" in json_str

    def test_model_json_schema(self):
        schema = FeedbackEvent.model_json_schema()
        assert "decision_id" in schema.get("properties", {})

    def test_roundtrip_via_dict(self):
        original = make_event(
            feedback_type=FeedbackType.CORRECTION,
            correction_data={"k": "v"},
            actual_impact=0.3,
        )
        data = original.model_dump()
        reconstructed = FeedbackEvent(**data)
        assert reconstructed.decision_id == original.decision_id
        assert reconstructed.feedback_type == original.feedback_type
        assert reconstructed.correction_data == original.correction_data


# ===========================================================================
# FeedbackResponse
# ===========================================================================


class TestFeedbackResponse:
    def test_minimal_valid(self):
        resp = FeedbackResponse(
            feedback_id="fb-1",
            decision_id="dec-1",
            status="accepted",
            timestamp="2024-01-01T00:00:00Z",
        )
        assert resp.feedback_id == "fb-1"
        assert resp.status == "accepted"
        assert resp.details is None

    def test_with_details(self):
        resp = FeedbackResponse(
            feedback_id="fb-2",
            decision_id="dec-2",
            status="accepted",
            timestamp="2024-01-02T00:00:00Z",
            details={"key": "value"},
        )
        assert resp.details == {"key": "value"}

    def test_missing_required_fields_raises(self):
        with pytest.raises(ValidationError):
            FeedbackResponse(feedback_id="fb-3", decision_id="dec-3")  # missing status, timestamp

    def test_model_dump(self):
        resp = FeedbackResponse(
            feedback_id="fb-4",
            decision_id="dec-4",
            status="ok",
            timestamp="2024-01-01T00:00:00Z",
        )
        d = resp.model_dump()
        assert d["feedback_id"] == "fb-4"
        assert d["details"] is None

    def test_json_roundtrip(self):
        resp = FeedbackResponse(
            feedback_id="fb-5",
            decision_id="dec-5",
            status="queued",
            timestamp="2024-06-01T10:00:00Z",
            details={"msg": "ok"},
        )
        json_str = resp.model_dump_json()
        assert "fb-5" in json_str


# ===========================================================================
# FeedbackBatchRequest
# ===========================================================================


class TestFeedbackBatchRequest:
    def test_single_event(self):
        req = FeedbackBatchRequest(events=[make_event()])
        assert len(req.events) == 1

    def test_multiple_events(self):
        events = [make_event(decision_id=f"dec-{i}") for i in range(5)]
        req = FeedbackBatchRequest(events=events)
        assert len(req.events) == 5

    def test_max_100_events(self):
        events = [make_event(decision_id=f"dec-{i}") for i in range(100)]
        req = FeedbackBatchRequest(events=events)
        assert len(req.events) == 100

    def test_101_events_raises(self):
        events = [make_event(decision_id=f"dec-{i}") for i in range(101)]
        with pytest.raises(ValidationError):
            FeedbackBatchRequest(events=events)

    def test_empty_events_raises(self):
        with pytest.raises(ValidationError):
            FeedbackBatchRequest(events=[])

    def test_missing_events_raises(self):
        with pytest.raises(ValidationError):
            FeedbackBatchRequest()  # type: ignore[call-arg]

    def test_model_dump(self):
        req = FeedbackBatchRequest(events=[make_event()])
        d = req.model_dump()
        assert len(d["events"]) == 1


# ===========================================================================
# FeedbackBatchResponse
# ===========================================================================


class TestFeedbackBatchResponse:
    def test_basic_response(self):
        resp = FeedbackBatchResponse(
            total=3,
            accepted=2,
            rejected=1,
            feedback_ids=["fb-1", "fb-2"],
        )
        assert resp.total == 3
        assert resp.accepted == 2
        assert resp.rejected == 1
        assert resp.feedback_ids == ["fb-1", "fb-2"]
        assert resp.errors is None

    def test_with_errors(self):
        resp = FeedbackBatchResponse(
            total=2,
            accepted=1,
            rejected=1,
            feedback_ids=["fb-1"],
            errors=[{"index": "1", "error": "invalid event"}],
        )
        assert resp.errors == [{"index": "1", "error": "invalid event"}]

    def test_all_accepted(self):
        resp = FeedbackBatchResponse(
            total=5,
            accepted=5,
            rejected=0,
            feedback_ids=[f"fb-{i}" for i in range(5)],
        )
        assert resp.rejected == 0

    def test_model_dump(self):
        resp = FeedbackBatchResponse(
            total=1,
            accepted=1,
            rejected=0,
            feedback_ids=["fb-x"],
        )
        d = resp.model_dump()
        assert d["total"] == 1
        assert d["errors"] is None


# ===========================================================================
# FeedbackQueryParams
# ===========================================================================


class TestFeedbackQueryParams:
    def test_defaults(self):
        params = FeedbackQueryParams()
        assert params.decision_id is None
        assert params.user_id is None
        assert params.tenant_id is None
        assert params.feedback_type is None
        assert params.outcome is None
        assert params.start_date is None
        assert params.end_date is None
        assert params.limit == 100
        assert params.offset == 0

    def test_set_all_fields(self):
        now = datetime(2024, 1, 1, tzinfo=UTC)
        later = datetime(2024, 12, 31, tzinfo=UTC)
        params = FeedbackQueryParams(
            decision_id="dec-1",
            user_id="user-1",
            tenant_id="tenant-1",
            feedback_type=FeedbackType.POSITIVE,
            outcome=OutcomeStatus.SUCCESS,
            start_date=now,
            end_date=later,
            limit=50,
            offset=10,
        )
        assert params.decision_id == "dec-1"
        assert params.user_id == "user-1"
        assert params.feedback_type == FeedbackType.POSITIVE
        assert params.outcome == OutcomeStatus.SUCCESS
        assert params.limit == 50
        assert params.offset == 10

    def test_limit_min_1(self):
        params = FeedbackQueryParams(limit=1)
        assert params.limit == 1

    def test_limit_max_1000(self):
        params = FeedbackQueryParams(limit=1000)
        assert params.limit == 1000

    def test_limit_below_1_raises(self):
        with pytest.raises(ValidationError):
            FeedbackQueryParams(limit=0)

    def test_limit_above_1000_raises(self):
        with pytest.raises(ValidationError):
            FeedbackQueryParams(limit=1001)

    def test_offset_zero_ok(self):
        params = FeedbackQueryParams(offset=0)
        assert params.offset == 0

    def test_offset_negative_raises(self):
        with pytest.raises(ValidationError):
            FeedbackQueryParams(offset=-1)

    def test_all_feedback_types(self):
        for ft in FeedbackType:
            params = FeedbackQueryParams(feedback_type=ft)
            assert params.feedback_type == ft

    def test_all_outcome_statuses(self):
        for os_ in OutcomeStatus:
            params = FeedbackQueryParams(outcome=os_)
            assert params.outcome == os_

    def test_model_dump(self):
        params = FeedbackQueryParams(limit=25)
        d = params.model_dump()
        assert d["limit"] == 25


# ===========================================================================
# StoredFeedbackEvent (dataclass)
# ===========================================================================


class TestStoredFeedbackEvent:
    def test_minimal_creation(self):
        sfe = make_stored()
        assert sfe.id == "sfb-001"
        assert sfe.decision_id == "dec-001"
        assert sfe.feedback_type == FeedbackType.POSITIVE
        assert sfe.outcome == OutcomeStatus.SUCCESS

    def test_defaults(self):
        sfe = make_stored()
        assert sfe.processed is False
        assert sfe.published_to_kafka is False

    def test_processed_flag(self):
        sfe = make_stored(processed=True)
        assert sfe.processed is True

    def test_published_flag(self):
        sfe = make_stored(published_to_kafka=True)
        assert sfe.published_to_kafka is True

    def test_optional_fields_none(self):
        sfe = make_stored()
        assert sfe.user_id is None
        assert sfe.tenant_id is None
        assert sfe.comment is None
        assert sfe.correction_data is None
        assert sfe.features is None
        assert sfe.actual_impact is None
        assert sfe.metadata is None

    def test_with_all_optional_fields(self):
        sfe = make_stored(
            user_id="u1",
            tenant_id="t1",
            comment="test comment",
            correction_data={"new": "value"},
            features={"feat": 0.9},
            actual_impact=0.6,
            metadata={"env": "prod"},
        )
        assert sfe.user_id == "u1"
        assert sfe.comment == "test comment"
        assert sfe.actual_impact == 0.6

    def test_created_at_stored(self):
        ts = datetime(2024, 6, 15, 8, 0, tzinfo=UTC)
        sfe = make_stored(created_at=ts)
        assert sfe.created_at == ts

    def test_all_feedback_types_stored(self):
        for ft in FeedbackType:
            sfe = make_stored(feedback_type=ft)
            assert sfe.feedback_type == ft

    def test_all_outcome_statuses_stored(self):
        for os_ in OutcomeStatus:
            sfe = make_stored(outcome=os_)
            assert sfe.outcome == os_

    def test_dataclass_fields_direct_assignment(self):
        sfe = make_stored()
        sfe.processed = True
        assert sfe.processed is True

    def test_dataclass_repr_contains_id(self):
        sfe = make_stored(id="sfb-repr")
        assert "sfb-repr" in repr(sfe)


# ===========================================================================
# FeedbackStats (dataclass)
# ===========================================================================


class TestFeedbackStats:
    def test_all_defaults(self):
        stats = FeedbackStats()
        assert stats.total_count == 0
        assert stats.positive_count == 0
        assert stats.negative_count == 0
        assert stats.neutral_count == 0
        assert stats.correction_count == 0
        assert stats.success_rate == 0.0
        assert stats.average_impact is None
        assert stats.period_start is None
        assert stats.period_end is None

    def test_set_all_fields(self):
        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 1, 31, tzinfo=UTC)
        stats = FeedbackStats(
            total_count=100,
            positive_count=60,
            negative_count=20,
            neutral_count=15,
            correction_count=5,
            success_rate=0.75,
            average_impact=0.45,
            period_start=start,
            period_end=end,
        )
        assert stats.total_count == 100
        assert stats.positive_count == 60
        assert stats.negative_count == 20
        assert stats.neutral_count == 15
        assert stats.correction_count == 5
        assert stats.success_rate == 0.75
        assert stats.average_impact == 0.45
        assert stats.period_start == start
        assert stats.period_end == end

    def test_partial_construction(self):
        stats = FeedbackStats(total_count=10, positive_count=8)
        assert stats.total_count == 10
        assert stats.positive_count == 8
        assert stats.negative_count == 0

    def test_direct_field_mutation(self):
        stats = FeedbackStats()
        stats.total_count = 50
        assert stats.total_count == 50

    def test_success_rate_float(self):
        stats = FeedbackStats(success_rate=1.0)
        assert stats.success_rate == 1.0

    def test_average_impact_zero(self):
        stats = FeedbackStats(average_impact=0.0)
        assert stats.average_impact == 0.0

    def test_repr_contains_total_count(self):
        stats = FeedbackStats(total_count=42)
        assert "42" in repr(stats)


# ===========================================================================
# Module __all__ export check
# ===========================================================================


class TestModuleExports:
    def test_all_exports_importable(self):
        from enhanced_agent_bus.feedback_handler import models as m

        for name in m.__all__:
            assert hasattr(m, name), f"{name} missing from module"

    def test_feedback_event_in_all(self):
        from enhanced_agent_bus.feedback_handler.models import __all__

        assert "FeedbackEvent" in __all__

    def test_feedback_response_in_all(self):
        from enhanced_agent_bus.feedback_handler.models import __all__

        assert "FeedbackResponse" in __all__

    def test_batch_request_in_all(self):
        from enhanced_agent_bus.feedback_handler.models import __all__

        assert "FeedbackBatchRequest" in __all__

    def test_batch_response_in_all(self):
        from enhanced_agent_bus.feedback_handler.models import __all__

        assert "FeedbackBatchResponse" in __all__

    def test_query_params_in_all(self):
        from enhanced_agent_bus.feedback_handler.models import __all__

        assert "FeedbackQueryParams" in __all__

    def test_stored_event_in_all(self):
        from enhanced_agent_bus.feedback_handler.models import __all__

        assert "StoredFeedbackEvent" in __all__

    def test_feedback_stats_in_all(self):
        from enhanced_agent_bus.feedback_handler.models import __all__

        assert "FeedbackStats" in __all__


# ===========================================================================
# Edge / boundary cases
# ===========================================================================


class TestEdgeCases:
    def test_decision_id_single_char(self):
        ev = make_event(decision_id="x")
        assert ev.decision_id == "x"

    def test_decision_id_with_internal_spaces_preserved(self):
        ev = make_event(decision_id="dec 001")
        assert ev.decision_id == "dec 001"

    def test_decision_id_whitespace_trimmed_to_content(self):
        ev = make_event(decision_id="  abc  ")
        assert ev.decision_id == "abc"

    def test_features_dict_preserved(self):
        features = {"a": 1, "b": "hello", "c": [1, 2, 3]}
        ev = make_event(features=features)
        assert ev.features == features

    def test_metadata_dict_preserved(self):
        meta = {"env": "staging", "version": "2.1.0"}
        ev = make_event(metadata=meta)
        assert ev.metadata == meta

    def test_correction_data_nested(self):
        data = {"outer": {"inner": "value"}, "list": [1, 2]}
        ev = make_event(
            feedback_type=FeedbackType.CORRECTION,
            correction_data=data,
        )
        assert ev.correction_data["outer"]["inner"] == "value"

    def test_batch_request_preserves_all_event_types(self):
        events = [
            make_event(feedback_type=FeedbackType.POSITIVE, decision_id="d1"),
            make_event(feedback_type=FeedbackType.NEGATIVE, decision_id="d2"),
            make_event(feedback_type=FeedbackType.NEUTRAL, decision_id="d3"),
            make_event(
                feedback_type=FeedbackType.CORRECTION,
                correction_data={"k": "v"},
                decision_id="d4",
            ),
        ]
        req = FeedbackBatchRequest(events=events)
        types = [e.feedback_type for e in req.events]
        assert FeedbackType.POSITIVE in types
        assert FeedbackType.CORRECTION in types

    def test_stored_event_actual_impact_none(self):
        sfe = make_stored(actual_impact=None)
        assert sfe.actual_impact is None

    def test_query_params_limit_boundary_exactly_1(self):
        params = FeedbackQueryParams(limit=1)
        assert params.limit == 1

    def test_query_params_offset_large_value(self):
        params = FeedbackQueryParams(offset=999999)
        assert params.offset == 999999

    def test_feedback_response_details_empty_dict(self):
        resp = FeedbackResponse(
            feedback_id="fb-empty",
            decision_id="dec-empty",
            status="ok",
            timestamp="2024-01-01T00:00:00Z",
            details={},
        )
        assert resp.details == {}
