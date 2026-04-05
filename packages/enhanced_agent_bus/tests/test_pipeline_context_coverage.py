"""
ACGS-2 Enhanced Agent Bus - Pipeline Context Coverage Tests
Constitutional Hash: 608508a9bd224290

Comprehensive tests for src/core/enhanced_agent_bus/pipeline/context.py
targeting >= 95% line coverage.
"""

import time
from dataclasses import fields
from unittest.mock import MagicMock, patch

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.ifc.labels import (
    Confidentiality,
    IFCLabel,
    IFCViolation,
    Integrity,
)
from enhanced_agent_bus.pipeline.context import PipelineContext, PipelineMetrics
from enhanced_agent_bus.prov.labels import (
    ProvActivity,
    ProvAgent,
    ProvEntity,
    ProvLabel,
    ProvLineage,
    build_prov_label,
)
from enhanced_agent_bus.validators import ValidationResult

# ---------------------------------------------------------------------------
# Helpers: minimal AgentMessage mock
# ---------------------------------------------------------------------------


def _make_message(**kwargs):
    """Return a minimal AgentMessage-like mock."""
    msg = MagicMock()
    msg.ifc_label = None  # default: no IFC label on message
    for k, v in kwargs.items():
        setattr(msg, k, v)
    return msg


def _make_validation_result(is_valid=True, errors=None, metadata=None):
    return ValidationResult(
        is_valid=is_valid,
        errors=errors or [],
        metadata=metadata or {},
    )


def _make_prov_label(stage_name="security_scan"):
    return build_prov_label(
        stage_name=stage_name,
        started_at="2024-01-01T00:00:00+00:00",
        ended_at="2024-01-01T00:00:01+00:00",
    )


# ===========================================================================
# PipelineMetrics Tests
# ===========================================================================


class TestPipelineMetricsDefaults:
    def test_default_values(self):
        m = PipelineMetrics()
        assert m.session_resolution_time_ms == 0.0
        assert m.security_scan_time_ms == 0.0
        assert m.verification_time_ms == 0.0
        assert m.strategy_time_ms == 0.0
        assert m.total_time_ms == 0.0
        assert m.cache_hits == 0
        assert m.cache_misses == 0
        assert m.sessions_resolved == 0
        assert m.sessions_not_found == 0
        assert m.sessions_errors == 0


class TestPipelineMetricsRecordSessionResolved:
    def test_increments_counter_and_time(self):
        m = PipelineMetrics()
        m.record_session_resolved(15.5)
        assert m.sessions_resolved == 1
        assert m.session_resolution_time_ms == 15.5

    def test_accumulates_multiple_calls(self):
        m = PipelineMetrics()
        m.record_session_resolved(10.0)
        m.record_session_resolved(20.0)
        assert m.sessions_resolved == 2
        assert m.session_resolution_time_ms == 30.0

    def test_zero_duration(self):
        m = PipelineMetrics()
        m.record_session_resolved(0.0)
        assert m.sessions_resolved == 1
        assert m.session_resolution_time_ms == 0.0


class TestPipelineMetricsRecordSessionNotFound:
    def test_increments_counter(self):
        m = PipelineMetrics()
        m.record_session_not_found()
        assert m.sessions_not_found == 1

    def test_accumulates(self):
        m = PipelineMetrics()
        for _ in range(3):
            m.record_session_not_found()
        assert m.sessions_not_found == 3


class TestPipelineMetricsRecordSessionError:
    def test_increments_error_counter(self):
        m = PipelineMetrics()
        m.record_session_error()
        assert m.sessions_errors == 1

    def test_multiple_errors(self):
        m = PipelineMetrics()
        m.record_session_error()
        m.record_session_error()
        assert m.sessions_errors == 2


class TestPipelineMetricsRecordCacheHit:
    def test_increments_cache_hits(self):
        m = PipelineMetrics()
        m.record_cache_hit()
        assert m.cache_hits == 1

    def test_multiple_hits(self):
        m = PipelineMetrics()
        for _ in range(5):
            m.record_cache_hit()
        assert m.cache_hits == 5


class TestPipelineMetricsRecordCacheMiss:
    def test_increments_cache_misses(self):
        m = PipelineMetrics()
        m.record_cache_miss()
        assert m.cache_misses == 1

    def test_multiple_misses(self):
        m = PipelineMetrics()
        m.record_cache_miss()
        m.record_cache_miss()
        assert m.cache_misses == 2


class TestPipelineMetricsRecordSecurityScan:
    def test_adds_duration(self):
        m = PipelineMetrics()
        m.record_security_scan(7.3)
        assert m.security_scan_time_ms == 7.3

    def test_accumulates(self):
        m = PipelineMetrics()
        m.record_security_scan(3.0)
        m.record_security_scan(4.0)
        assert m.security_scan_time_ms == pytest.approx(7.0)


class TestPipelineMetricsRecordVerification:
    def test_accumulates(self):
        m = PipelineMetrics()
        m.record_verification(5.0)
        m.record_verification(5.0)
        m.record_verification(5.0)
        assert m.verification_time_ms == 10.0

    def test_accumulates(self):
        m = PipelineMetrics()
        m.record_verification(5.0)
        m.record_verification(5.0)
        assert m.verification_time_ms == pytest.approx(10.0)


class TestPipelineMetricsRecordStrategy:
    def test_adds_duration(self):
        m = PipelineMetrics()
        m.record_strategy(99.9)
        assert m.strategy_time_ms == pytest.approx(99.9)

    def test_accumulates(self):
        m = PipelineMetrics()
        m.record_strategy(1.0)
        m.record_strategy(2.0)
        assert m.strategy_time_ms == pytest.approx(3.0)


class TestPipelineMetricsFinalize:
    def test_sets_total_time_ms(self):
        m = PipelineMetrics()
        start = time.perf_counter()
        time.sleep(0.001)  # tiny sleep so total_time_ms > 0
        m.finalize(start)
        assert m.total_time_ms > 0

    def test_total_time_ms_is_positive(self):
        m = PipelineMetrics()
        start = time.perf_counter() - 0.1  # simulate 100 ms already elapsed
        m.finalize(start)
        assert m.total_time_ms >= 100.0


class TestPipelineMetricsToDict:
    def test_returns_correct_keys(self):
        m = PipelineMetrics()
        d = m.to_dict()
        assert "timing_ms" in d
        assert "counters" in d
        assert "rates" in d

    def test_timing_keys(self):
        m = PipelineMetrics()
        m.record_security_scan(1.0)
        m.record_verification(2.0)
        m.record_strategy(3.0)
        m.record_session_resolved(4.0)
        d = m.to_dict()
        timing = d["timing_ms"]
        assert timing["session_resolution"] == pytest.approx(4.0)
        assert timing["security_scan"] == pytest.approx(1.0)
        assert timing["verification"] == pytest.approx(2.0)
        assert timing["strategy"] == pytest.approx(3.0)
        assert timing["total"] == pytest.approx(0.0)

    def test_counter_keys(self):
        m = PipelineMetrics()
        m.record_session_resolved(1.0)
        m.record_session_not_found()
        m.record_session_error()
        m.record_cache_hit()
        m.record_cache_miss()
        d = m.to_dict()
        counters = d["counters"]
        assert counters["sessions_resolved"] == 1
        assert counters["sessions_not_found"] == 1
        assert counters["sessions_errors"] == 1
        assert counters["cache_hits"] == 1
        assert counters["cache_misses"] == 1

    def test_cache_hit_rate_when_no_cache_activity(self):
        m = PipelineMetrics()
        d = m.to_dict()
        assert d["rates"]["cache_hit_rate"] == 0.0

    def test_cache_hit_rate_calculated(self):
        m = PipelineMetrics()
        m.record_cache_hit()
        m.record_cache_miss()
        d = m.to_dict()
        expected = round(1 / 2, 4)
        assert d["rates"]["cache_hit_rate"] == pytest.approx(expected)

    def test_session_resolution_rate_when_zero(self):
        m = PipelineMetrics()
        d = m.to_dict()
        assert d["rates"]["session_resolution_rate"] == 0.0

    def test_session_resolution_rate_calculated(self):
        m = PipelineMetrics()
        m.record_session_resolved(1.0)
        m.record_session_not_found()
        m.record_session_error()
        d = m.to_dict()
        expected = round(1 / 3, 4)
        assert d["rates"]["session_resolution_rate"] == pytest.approx(expected)

    def test_rounding_applied(self):
        m = PipelineMetrics()
        m.record_security_scan(1.23456789)
        d = m.to_dict()
        # The value should be rounded to 2 decimal places
        assert d["timing_ms"]["security_scan"] == round(1.23456789, 2)

    def test_all_cache_hits_rate_is_one(self):
        m = PipelineMetrics()
        m.record_cache_hit()
        d = m.to_dict()
        assert d["rates"]["cache_hit_rate"] == 1.0

    def test_all_cache_misses_rate_is_zero(self):
        m = PipelineMetrics()
        m.record_cache_miss()
        d = m.to_dict()
        assert d["rates"]["cache_hit_rate"] == 0.0


# ===========================================================================
# PipelineContext Tests — Instantiation
# ===========================================================================


class TestPipelineContextDefaults:
    def test_creates_with_message(self):
        msg = _make_message()
        ctx = PipelineContext(message=msg)
        assert ctx.message is msg

    def test_default_session_is_none(self):
        ctx = PipelineContext(message=_make_message())
        assert ctx.session is None
        assert ctx.session_id is None

    def test_default_cache_fields(self):
        ctx = PipelineContext(message=_make_message())
        assert ctx.cache_key is None
        assert ctx.cache_hit is False

    def test_default_security_fields(self):
        ctx = PipelineContext(message=_make_message())
        assert ctx.security_passed is False
        assert ctx.security_result is None

    def test_default_verification_results(self):
        ctx = PipelineContext(message=_make_message())
        assert ctx.verification_results == {}

    def test_default_strategy_result(self):
        ctx = PipelineContext(message=_make_message())
        assert ctx.strategy_result is None

    def test_default_early_result(self):
        ctx = PipelineContext(message=_make_message())
        assert ctx.early_result is None

    def test_default_tenant_fields(self):
        ctx = PipelineContext(message=_make_message())
        assert ctx.tenant_id is None
        assert ctx.tenant_validated is False
        assert ctx.tenant_errors == []

    def test_default_constitutional_fields(self):
        ctx = PipelineContext(message=_make_message())
        assert ctx.constitutional_hash == CONSTITUTIONAL_HASH
        assert ctx.message_constitutional_hash is None
        assert ctx.constitutional_validated is False

    def test_default_maci_fields(self):
        ctx = PipelineContext(message=_make_message())
        assert ctx.maci_role is None
        assert ctx.maci_action is None
        assert ctx.maci_enforced is False
        assert ctx.maci_result is None

    def test_default_governance_fields(self):
        ctx = PipelineContext(message=_make_message())
        assert ctx.governance_decision is None
        assert ctx.governance_allowed is True
        assert ctx.governance_reasoning is None
        assert ctx.impact_score == 0.0

    def test_default_execution_tracking(self):
        ctx = PipelineContext(message=_make_message())
        assert ctx.middleware_path == []
        assert isinstance(ctx.start_time, float)

    def test_default_metrics(self):
        ctx = PipelineContext(message=_make_message())
        assert isinstance(ctx.metrics, PipelineMetrics)

    def test_default_ifc_label(self):
        ctx = PipelineContext(message=_make_message())
        assert ctx.ifc_label.confidentiality == Confidentiality.PUBLIC
        assert ctx.ifc_label.integrity == Integrity.MEDIUM

    def test_default_ifc_violations(self):
        ctx = PipelineContext(message=_make_message())
        assert ctx.ifc_violations == []

    def test_default_action_history(self):
        ctx = PipelineContext(message=_make_message())
        assert ctx.action_history == []

    def test_default_prov_lineage(self):
        ctx = PipelineContext(message=_make_message())
        assert isinstance(ctx.prov_lineage, ProvLineage)
        assert len(ctx.prov_lineage) == 0

    def test_default_orchestration_fields(self):
        ctx = PipelineContext(message=_make_message())
        assert ctx.orchestration_result is None
        assert ctx.orchestrator_used is False


# ===========================================================================
# PipelineContext.__post_init__ Tests
# ===========================================================================


class TestPipelineContextPostInit:
    def test_adopts_ifc_label_from_message(self):
        secret_label = IFCLabel(
            confidentiality=Confidentiality.SECRET,
            integrity=Integrity.HIGH,
        )
        msg = _make_message(ifc_label=secret_label)
        ctx = PipelineContext(message=msg)
        assert ctx.ifc_label == secret_label

    def test_ignores_none_ifc_label_from_message(self):
        msg = _make_message(ifc_label=None)
        ctx = PipelineContext(message=msg)
        # Should keep default PUBLIC/MEDIUM
        assert ctx.ifc_label.confidentiality == Confidentiality.PUBLIC
        assert ctx.ifc_label.integrity == Integrity.MEDIUM

    def test_ignores_non_ifc_label_type_on_message(self):
        """If message.ifc_label is not an IFCLabel instance, it is ignored."""
        msg = _make_message(ifc_label="not_an_ifc_label")
        ctx = PipelineContext(message=msg)
        assert ctx.ifc_label.confidentiality == Confidentiality.PUBLIC

    def test_message_without_ifc_label_attribute(self):
        """getattr fallback handles messages without ifc_label attribute."""
        msg = MagicMock(spec=[])  # no attributes
        # Need to set message attribute without ifc_label
        msg2 = object.__new__(MagicMock)

        # Just use a plain mock that has no ifc_label
        class NoIFCMessage:
            pass

        plain_msg = NoIFCMessage()
        ctx = PipelineContext(message=plain_msg)  # type: ignore[arg-type]
        assert ctx.ifc_label.confidentiality == Confidentiality.PUBLIC

    def test_explicit_ifc_label_overridden_by_message(self):
        """When message has an IFC label, it overrides the default_factory label."""
        secret_label = IFCLabel(
            confidentiality=Confidentiality.CONFIDENTIAL,
            integrity=Integrity.TRUSTED,
        )
        msg = _make_message(ifc_label=secret_label)
        ctx = PipelineContext(message=msg)
        assert ctx.ifc_label.confidentiality == Confidentiality.CONFIDENTIAL
        assert ctx.ifc_label.integrity == Integrity.TRUSTED


# ===========================================================================
# PipelineContext.record_ifc_violation
# ===========================================================================


class TestPipelineContextRecordIFCViolation:
    def test_appends_violation(self):
        ctx = PipelineContext(message=_make_message())
        label_a = IFCLabel(Confidentiality.SECRET, Integrity.HIGH)
        label_b = IFCLabel(Confidentiality.PUBLIC, Integrity.HIGH)
        v = IFCViolation(
            source_label=label_a,
            target_label=label_b,
            policy="no-write-down",
            detail="secret to public",
        )
        ctx.record_ifc_violation(v)
        assert len(ctx.ifc_violations) == 1
        assert ctx.ifc_violations[0] is v

    def test_appends_multiple_violations(self):
        ctx = PipelineContext(message=_make_message())
        la = IFCLabel(Confidentiality.SECRET, Integrity.HIGH)
        lb = IFCLabel(Confidentiality.PUBLIC, Integrity.HIGH)
        for i in range(3):
            v = IFCViolation(la, lb, f"policy-{i}")
            ctx.record_ifc_violation(v)
        assert len(ctx.ifc_violations) == 3


# ===========================================================================
# PipelineContext.record_prov_label
# ===========================================================================


class TestPipelineContextRecordProvLabel:
    def test_appends_prov_label(self):
        ctx = PipelineContext(message=_make_message())
        label = _make_prov_label("security_scan")
        ctx.record_prov_label(label)
        assert len(ctx.prov_lineage) == 1

    def test_appends_multiple_prov_labels(self):
        ctx = PipelineContext(message=_make_message())
        for stage in ["security_scan", "constitutional_validation", "strategy"]:
            ctx.record_prov_label(_make_prov_label(stage))
        assert len(ctx.prov_lineage) == 3


# ===========================================================================
# PipelineContext.add_middleware
# ===========================================================================


class TestPipelineContextAddMiddleware:
    def test_appends_to_path(self):
        ctx = PipelineContext(message=_make_message())
        ctx.add_middleware("SecurityMiddleware")
        assert ctx.middleware_path == ["SecurityMiddleware"]

    def test_appends_multiple(self):
        ctx = PipelineContext(message=_make_message())
        ctx.add_middleware("A")
        ctx.add_middleware("B")
        ctx.add_middleware("C")
        assert ctx.middleware_path == ["A", "B", "C"]


# ===========================================================================
# PipelineContext.set_early_result
# ===========================================================================


class TestPipelineContextSetEarlyResult:
    def test_sets_early_result(self):
        ctx = PipelineContext(message=_make_message())
        result = _make_validation_result(is_valid=False, errors=["blocked"])
        ctx.set_early_result(result)
        assert ctx.early_result is result

    def test_overwrites_existing_early_result(self):
        ctx = PipelineContext(message=_make_message())
        r1 = _make_validation_result(is_valid=False)
        r2 = _make_validation_result(is_valid=True)
        ctx.set_early_result(r1)
        ctx.set_early_result(r2)
        assert ctx.early_result is r2


# ===========================================================================
# PipelineContext.finalize
# ===========================================================================


class TestPipelineContextFinalize:
    def test_finalize_sets_total_time(self):
        ctx = PipelineContext(message=_make_message())
        ctx.finalize()
        assert ctx.metrics.total_time_ms >= 0.0

    def test_finalize_uses_start_time(self):
        ctx = PipelineContext(message=_make_message())
        # Artificially back-date start_time to simulate elapsed work
        ctx.start_time = time.perf_counter() - 0.05
        ctx.finalize()
        assert ctx.metrics.total_time_ms >= 50.0


# ===========================================================================
# PipelineContext.to_validation_result — with strategy_result
# ===========================================================================


class TestPipelineContextToValidationResultWithStrategy:
    def _ctx_with_strategy(self, **kwargs):
        ctx = PipelineContext(message=_make_message())
        ctx.strategy_result = _make_validation_result(**kwargs)
        return ctx

    def test_returns_strategy_result(self):
        ctx = self._ctx_with_strategy(is_valid=True)
        result = ctx.to_validation_result()
        assert result.is_valid is True

    def test_merges_pipeline_version(self):
        ctx = self._ctx_with_strategy()
        result = ctx.to_validation_result()
        assert result.metadata.get("pipeline_version") == "2.0.0"

    def test_merges_middleware_path(self):
        ctx = self._ctx_with_strategy()
        ctx.add_middleware("Mw1")
        ctx.add_middleware("Mw2")
        result = ctx.to_validation_result()
        assert result.metadata["middleware_path"] == ["Mw1", "Mw2"]

    def test_merges_metrics(self):
        ctx = self._ctx_with_strategy()
        ctx.metrics.record_cache_hit()
        result = ctx.to_validation_result()
        assert "metrics" in result.metadata
        assert result.metadata["metrics"]["counters"]["cache_hits"] == 1

    def test_cache_hit_flag(self):
        ctx = self._ctx_with_strategy()
        ctx.cache_hit = True
        result = ctx.to_validation_result()
        assert result.metadata["cache_hit"] is True

    def test_session_resolved_true_when_session_set(self):
        ctx = self._ctx_with_strategy()
        ctx.session = MagicMock()
        result = ctx.to_validation_result()
        assert result.metadata["session_resolved"] is True

    def test_session_resolved_false_when_no_session(self):
        ctx = self._ctx_with_strategy()
        ctx.session = None
        result = ctx.to_validation_result()
        assert result.metadata["session_resolved"] is False

    def test_security_scan_passed(self):
        ctx = self._ctx_with_strategy()
        ctx.security_passed = True
        result = ctx.to_validation_result()
        assert result.metadata["security_scan"] == "PASSED"

    def test_security_scan_blocked(self):
        ctx = self._ctx_with_strategy()
        ctx.security_passed = False
        result = ctx.to_validation_result()
        assert result.metadata["security_scan"] == "BLOCKED"

    def test_verification_results_serialised(self):
        ctx = self._ctx_with_strategy()
        vr = _make_validation_result(is_valid=True, errors=[])
        ctx.verification_results["schema"] = vr
        result = ctx.to_validation_result()
        v_dict = result.metadata["verification"]
        assert "schema" in v_dict
        assert v_dict["schema"]["is_valid"] is True
        assert v_dict["schema"]["errors"] == []

    def test_verification_results_with_errors(self):
        ctx = self._ctx_with_strategy()
        vr = _make_validation_result(is_valid=False, errors=["bad field"])
        ctx.verification_results["policy"] = vr
        result = ctx.to_validation_result()
        v_dict = result.metadata["verification"]
        assert v_dict["policy"]["is_valid"] is False
        assert "bad field" in v_dict["policy"]["errors"]

    def test_ifc_label_in_metadata(self):
        ctx = self._ctx_with_strategy()
        result = ctx.to_validation_result()
        assert "ifc_label" in result.metadata
        ldict = result.metadata["ifc_label"]
        assert "confidentiality" in ldict
        assert "integrity" in ldict

    def test_ifc_violations_count(self):
        ctx = self._ctx_with_strategy()
        la = IFCLabel(Confidentiality.SECRET, Integrity.HIGH)
        lb = IFCLabel(Confidentiality.PUBLIC, Integrity.HIGH)
        ctx.record_ifc_violation(IFCViolation(la, lb, "policy"))
        result = ctx.to_validation_result()
        assert result.metadata["ifc_violations_count"] == 1

    def test_action_history_in_metadata(self):
        ctx = self._ctx_with_strategy()
        ctx.action_history.append("stage1")
        ctx.action_history.append("stage2")
        result = ctx.to_validation_result()
        assert result.metadata["action_history"] == ["stage1", "stage2"]

    def test_action_history_is_copy(self):
        """Mutating action_history after result creation should not affect metadata."""
        ctx = self._ctx_with_strategy()
        ctx.action_history.append("stage1")
        result = ctx.to_validation_result()
        ctx.action_history.append("stage2")
        assert result.metadata["action_history"] == ["stage1"]

    def test_prov_lineage_in_metadata(self):
        ctx = self._ctx_with_strategy()
        ctx.record_prov_label(_make_prov_label("security_scan"))
        result = ctx.to_validation_result()
        assert "prov_lineage" in result.metadata
        assert isinstance(result.metadata["prov_lineage"], list)
        assert len(result.metadata["prov_lineage"]) == 1

    def test_prov_lineage_length_in_metadata(self):
        ctx = self._ctx_with_strategy()
        ctx.record_prov_label(_make_prov_label("security_scan"))
        ctx.record_prov_label(_make_prov_label("strategy"))
        result = ctx.to_validation_result()
        assert result.metadata["prov_lineage_length"] == 2

    def test_orchestration_result_none_default(self):
        ctx = self._ctx_with_strategy()
        result = ctx.to_validation_result()
        assert result.metadata["orchestration_result"] is None

    def test_orchestration_result_set(self):
        ctx = self._ctx_with_strategy()
        ctx.orchestration_result = {"decision": "APPROVED"}
        result = ctx.to_validation_result()
        assert result.metadata["orchestration_result"] == {"decision": "APPROVED"}

    def test_orchestrator_used_false(self):
        ctx = self._ctx_with_strategy()
        result = ctx.to_validation_result()
        assert result.metadata["orchestrator_used"] is False

    def test_orchestrator_used_true(self):
        ctx = self._ctx_with_strategy()
        ctx.orchestrator_used = True
        result = ctx.to_validation_result()
        assert result.metadata["orchestrator_used"] is True

    def test_preserves_existing_strategy_metadata(self):
        ctx = PipelineContext(message=_make_message())
        ctx.strategy_result = _make_validation_result(metadata={"custom_key": "custom_value"})
        result = ctx.to_validation_result()
        assert result.metadata.get("custom_key") == "custom_value"
        assert result.metadata.get("pipeline_version") == "2.0.0"

    def test_returns_same_object_as_strategy_result(self):
        ctx = PipelineContext(message=_make_message())
        strategy = _make_validation_result(is_valid=True)
        ctx.strategy_result = strategy
        result = ctx.to_validation_result()
        # to_validation_result modifies strategy_result in-place and returns it
        assert result is strategy

    def test_multiple_verification_results(self):
        ctx = self._ctx_with_strategy()
        ctx.verification_results["a"] = _make_validation_result(is_valid=True)
        ctx.verification_results["b"] = _make_validation_result(is_valid=False, errors=["err"])
        result = ctx.to_validation_result()
        v = result.metadata["verification"]
        assert v["a"]["is_valid"] is True
        assert v["b"]["is_valid"] is False


# ===========================================================================
# PipelineContext.to_validation_result — fallback (no strategy_result)
# ===========================================================================


class TestPipelineContextToValidationResultFallback:
    def test_returns_invalid_result(self):
        ctx = PipelineContext(message=_make_message())
        # No strategy_result set
        result = ctx.to_validation_result()
        assert result.is_valid is False

    def test_error_message_in_fallback(self):
        ctx = PipelineContext(message=_make_message())
        result = ctx.to_validation_result()
        assert "No strategy result produced" in result.errors

    def test_pipeline_version_in_fallback(self):
        ctx = PipelineContext(message=_make_message())
        result = ctx.to_validation_result()
        assert result.metadata.get("pipeline_version") == "2.0.0"

    def test_middleware_path_in_fallback(self):
        ctx = PipelineContext(message=_make_message())
        ctx.add_middleware("TestMw")
        result = ctx.to_validation_result()
        assert result.metadata.get("middleware_path") == ["TestMw"]

    def test_metrics_in_fallback(self):
        ctx = PipelineContext(message=_make_message())
        result = ctx.to_validation_result()
        assert "metrics" in result.metadata

    def test_fallback_creates_new_validation_result(self):
        ctx = PipelineContext(message=_make_message())
        result = ctx.to_validation_result()
        assert isinstance(result, ValidationResult)


# ===========================================================================
# Integration / Combined Behaviour Tests
# ===========================================================================


class TestPipelineContextIntegration:
    def test_full_happy_path(self):
        """Simulate a full pipeline pass-through and check final result."""
        msg = _make_message()
        ctx = PipelineContext(message=msg)

        # Session
        ctx.session = MagicMock()
        ctx.session_id = "sess-abc"
        ctx.metrics.record_session_resolved(5.0)

        # Cache
        ctx.cache_key = "key-123"
        ctx.cache_hit = True
        ctx.metrics.record_cache_hit()

        # Security
        ctx.security_passed = True
        ctx.metrics.record_security_scan(2.0)

        # Verification
        ctx.verification_results["constitutional"] = _make_validation_result(is_valid=True)
        ctx.metrics.record_verification(3.0)

        # Strategy
        ctx.strategy_result = _make_validation_result(is_valid=True)
        ctx.metrics.record_strategy(4.0)

        # IFC
        label = _make_prov_label("strategy")
        ctx.record_prov_label(label)

        # Middleware path
        for mw in ["SessionMw", "CacheMw", "SecurityMw", "StrategyMw"]:
            ctx.add_middleware(mw)

        ctx.finalize()
        result = ctx.to_validation_result()

        assert result.is_valid is True
        assert result.metadata["pipeline_version"] == "2.0.0"
        assert result.metadata["cache_hit"] is True
        assert result.metadata["session_resolved"] is True
        assert result.metadata["security_scan"] == "PASSED"
        assert result.metadata["prov_lineage_length"] == 1
        assert len(result.metadata["middleware_path"]) == 4

    def test_pipeline_with_ifc_violation(self):
        ctx = PipelineContext(message=_make_message())
        ctx.strategy_result = _make_validation_result(is_valid=False)
        la = IFCLabel(Confidentiality.SECRET, Integrity.HIGH)
        lb = IFCLabel(Confidentiality.PUBLIC, Integrity.MEDIUM)
        ctx.record_ifc_violation(IFCViolation(la, lb, "no-write-down", "secret->public"))
        result = ctx.to_validation_result()
        assert result.metadata["ifc_violations_count"] == 1

    def test_pipeline_metrics_to_dict_after_full_run(self):
        ctx = PipelineContext(message=_make_message())
        ctx.metrics.record_cache_hit()
        ctx.metrics.record_cache_miss()
        ctx.metrics.record_session_resolved(10.0)
        ctx.metrics.record_session_not_found()
        ctx.finalize()
        d = ctx.metrics.to_dict()
        assert d["rates"]["cache_hit_rate"] == pytest.approx(round(1 / 2, 4))
        assert d["rates"]["session_resolution_rate"] == pytest.approx(round(1 / 2, 4))

    def test_start_time_set_at_creation(self):
        before = time.perf_counter()
        ctx = PipelineContext(message=_make_message())
        after = time.perf_counter()
        assert before <= ctx.start_time <= after

    def test_separate_contexts_have_independent_state(self):
        ctx1 = PipelineContext(message=_make_message())
        ctx2 = PipelineContext(message=_make_message())
        ctx1.add_middleware("Mw1")
        ctx2.add_middleware("Mw2")
        assert ctx1.middleware_path == ["Mw1"]
        assert ctx2.middleware_path == ["Mw2"]

    def test_tenant_errors_independent(self):
        ctx1 = PipelineContext(message=_make_message())
        ctx2 = PipelineContext(message=_make_message())
        ctx1.tenant_errors.append("error1")
        assert ctx2.tenant_errors == []

    def test_action_history_independent(self):
        ctx1 = PipelineContext(message=_make_message())
        ctx2 = PipelineContext(message=_make_message())
        ctx1.action_history.append("stage1")
        assert ctx2.action_history == []

    def test_metrics_independent(self):
        ctx1 = PipelineContext(message=_make_message())
        ctx2 = PipelineContext(message=_make_message())
        ctx1.metrics.record_cache_hit()
        assert ctx2.metrics.cache_hits == 0


# ===========================================================================
# Edge Cases
# ===========================================================================


class TestPipelineContextEdgeCases:
    def test_ifc_label_not_replaced_by_wrong_type_on_message(self):
        """Non-IFCLabel values in message.ifc_label should be ignored."""
        msg = _make_message(ifc_label=42)
        ctx = PipelineContext(message=msg)
        assert ctx.ifc_label.confidentiality == Confidentiality.PUBLIC

    def test_zero_sessions_and_cache_rates(self):
        m = PipelineMetrics()
        d = m.to_dict()
        assert d["rates"]["cache_hit_rate"] == 0.0
        assert d["rates"]["session_resolution_rate"] == 0.0

    def test_constitutional_hash_value(self):
        ctx = PipelineContext(message=_make_message())
        assert ctx.constitutional_hash == CONSTITUTIONAL_HASH  # pragma: allowlist secret

    def test_governance_allowed_defaults_true(self):
        ctx = PipelineContext(message=_make_message())
        assert ctx.governance_allowed is True

    def test_impact_score_defaults_zero(self):
        ctx = PipelineContext(message=_make_message())
        assert ctx.impact_score == 0.0

    def test_set_high_impact_score(self):
        ctx = PipelineContext(message=_make_message())
        ctx.impact_score = 0.95
        assert ctx.impact_score == 0.95

    def test_to_validation_result_with_empty_verification(self):
        ctx = PipelineContext(message=_make_message())
        ctx.strategy_result = _make_validation_result()
        result = ctx.to_validation_result()
        assert result.metadata["verification"] == {}

    def test_security_passed_flag_toggling(self):
        ctx = PipelineContext(message=_make_message())
        ctx.strategy_result = _make_validation_result()
        # Default blocked
        r = ctx.to_validation_result()
        assert r.metadata["security_scan"] == "BLOCKED"
        # Reset metadata and flip flag
        ctx.strategy_result = _make_validation_result()
        ctx.security_passed = True
        r2 = ctx.to_validation_result()
        assert r2.metadata["security_scan"] == "PASSED"

    def test_pipeline_metrics_record_all_session_states(self):
        m = PipelineMetrics()
        m.record_session_resolved(5.0)
        m.record_session_not_found()
        m.record_session_error()
        assert m.sessions_resolved == 1
        assert m.sessions_not_found == 1
        assert m.sessions_errors == 1
        d = m.to_dict()
        assert d["rates"]["session_resolution_rate"] == round(1 / 3, 4)
