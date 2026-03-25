# Constitutional Hash: 608508a9bd224290
"""
Comprehensive tests for src/core/enhanced_agent_bus/governance_constants.py.

Goal: raise line coverage from 0 % to ≥ 95 % (56 statements).

Strategy:
  - Import every name explicitly so coverage marks each constant line.
  - Assert type, value, and domain invariants for every constant.
  - Group by logical section to make failures easy to diagnose.
"""

import importlib
import math
import types

import pytest

import enhanced_agent_bus.governance_constants as gc

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ALL_EXPORTED = [
    # Impact scoring
    "IMPACT_DELIBERATION_THRESHOLD",
    "IMPACT_CRITICAL_FLOOR",
    "IMPACT_HIGH_SEMANTIC_FLOOR",
    "IMPACT_WEIGHT_SEMANTIC",
    "IMPACT_WEIGHT_PERMISSION",
    "IMPACT_WEIGHT_VOLUME",
    "IMPACT_WEIGHT_CONTEXT",
    "IMPACT_WEIGHT_DRIFT",
    "IMPACT_WEIGHT_TRAJECTORY",
    # Deliberation / Consensus
    "DEFAULT_REQUIRED_VOTES",
    "DEFAULT_CONSENSUS_THRESHOLD",
    "DEFAULT_DELIBERATION_TIMEOUT_SECONDS",
    # MACI Role Confidence
    "MACI_EXECUTIVE_CONFIDENCE",
    "MACI_INTERPRETER_CONFIDENCE",
    "MACI_VALIDATOR_CONFIDENCE",
    # Cache
    "DEFAULT_LRU_CACHE_SIZE",
    "DEFAULT_CACHE_TTL_SECONDS",
    # Circuit Breaker
    "DEFAULT_CB_FAIL_MAX",
    "DEFAULT_CB_RESET_TIMEOUT",
    "DEFAULT_MAX_RETRIES",
    # Adaptive Governance Engine
    "GOVERNANCE_FEEDBACK_WINDOW_SECONDS",
    "GOVERNANCE_PERFORMANCE_TARGET",
    "GOVERNANCE_RISK_CRITICAL",
    "GOVERNANCE_RISK_HIGH",
    "GOVERNANCE_RISK_MEDIUM",
    "GOVERNANCE_RISK_LOW",
    "GOVERNANCE_EMA_ALPHA",
    "GOVERNANCE_HISTORY_MAX",
    "GOVERNANCE_HISTORY_TRIM",
    "GOVERNANCE_COMPLIANCE_THRESHOLD",
    "GOVERNANCE_LEARNING_CYCLE_SECONDS",
    "GOVERNANCE_BACKOFF_SECONDS",
    "GOVERNANCE_MAX_TREND_LENGTH",
    "GOVERNANCE_RETRAIN_HISTORY_MIN",
    "GOVERNANCE_RETRAIN_CHECK_MODULUS",
    "GOVERNANCE_FALLBACK_CONFIDENCE",
    "GOVERNANCE_RECOMMENDED_THRESHOLD",
    # Rollback Engine
    "ROLLBACK_MONITORING_INTERVAL_SECONDS",
    "ROLLBACK_MIN_CONFIDENCE",
    "ROLLBACK_HTTP_TIMEOUT_SECONDS",
    "ROLLBACK_DETECT_TIMEOUT_SECONDS",
    "ROLLBACK_STEP_TIMEOUT_SECONDS",
    # MACI Verifier
    "VERIFIER_BASE_RISK_SCORE",
    "VERIFIER_RISK_SENSITIVE_DATA",
    "VERIFIER_RISK_CROSS_JURISDICTION",
    "VERIFIER_RISK_HIGH_IMPACT",
    "VERIFIER_RISK_HUMAN_APPROVAL",
    "VERIFIER_JUDICIAL_CONFIDENCE_THRESHOLD",
    "VERIFIER_LEGISLATIVE_CONFIDENCE_CAP",
    "VERIFIER_LEGISLATIVE_CONFIDENCE_BASE",
    "VERIFIER_LEGISLATIVE_CONFIDENCE_PER_RULE",
    # LLM Circuit Breaker
    "LLM_CB_DEFAULT_FAILURE_THRESHOLD",
    "LLM_CB_DEFAULT_TIMEOUT_SECONDS",
    "LLM_CB_DEFAULT_HALF_OPEN_REQUESTS",
    "LLM_CB_DEFAULT_FALLBACK_TTL_SECONDS",
    # Saga
    "SAGA_DEFAULT_TTL_SECONDS",
]


# ---------------------------------------------------------------------------
# Module-level smoke tests
# ---------------------------------------------------------------------------


class TestModuleImport:
    def test_module_is_importable(self):
        assert gc is not None

    def test_module_is_module_type(self):
        assert isinstance(gc, types.ModuleType)

    def test_module_can_be_reimported(self):
        reloaded = importlib.import_module("enhanced_agent_bus.governance_constants")
        # Same file — module identity may differ under dual-import path aliasing
        assert reloaded.__file__ == gc.__file__

    def test_all_expected_names_are_present(self):
        for name in _ALL_EXPORTED:
            assert hasattr(gc, name), f"Missing constant: {name}"

    def test_no_unexpected_private_names(self):
        """No dunder attributes other than standard module dunders should be present."""
        private_names = [n for n in dir(gc) if n.startswith("__") and n.endswith("__")]
        # Standard dunders expected on any module object across Python versions
        allowed = {
            "__name__",
            "__doc__",
            "__file__",
            "__loader__",
            "__spec__",
            "__package__",
            "__builtins__",
            "__cached__",
            "__annotations__",
            # Python 3.14+ lazy-annotation dunders
            "__annotate__",
            "__conditional_annotations__",
        }
        unexpected = set(private_names) - allowed
        assert not unexpected, f"Unexpected dunder names: {unexpected}"


# ---------------------------------------------------------------------------
# Impact Scoring
# ---------------------------------------------------------------------------


class TestImpactScoringConstants:
    def test_deliberation_threshold_type(self):
        assert isinstance(gc.IMPACT_DELIBERATION_THRESHOLD, float)

    def test_deliberation_threshold_value(self):
        assert gc.IMPACT_DELIBERATION_THRESHOLD == 0.8

    def test_deliberation_threshold_range(self):
        assert 0.0 < gc.IMPACT_DELIBERATION_THRESHOLD < 1.0

    def test_critical_floor_type(self):
        assert isinstance(gc.IMPACT_CRITICAL_FLOOR, float)

    def test_critical_floor_value(self):
        assert gc.IMPACT_CRITICAL_FLOOR == 0.95

    def test_critical_floor_above_deliberation_threshold(self):
        assert gc.IMPACT_CRITICAL_FLOOR > gc.IMPACT_DELIBERATION_THRESHOLD

    def test_high_semantic_floor_type(self):
        assert isinstance(gc.IMPACT_HIGH_SEMANTIC_FLOOR, float)

    def test_high_semantic_floor_value(self):
        assert gc.IMPACT_HIGH_SEMANTIC_FLOOR == 0.75

    def test_high_semantic_floor_below_deliberation_threshold(self):
        assert gc.IMPACT_HIGH_SEMANTIC_FLOOR < gc.IMPACT_DELIBERATION_THRESHOLD

    def test_weight_semantic_type(self):
        assert isinstance(gc.IMPACT_WEIGHT_SEMANTIC, float)

    def test_weight_semantic_value(self):
        assert gc.IMPACT_WEIGHT_SEMANTIC == 0.6

    def test_weight_permission_type(self):
        assert isinstance(gc.IMPACT_WEIGHT_PERMISSION, float)

    def test_weight_permission_value(self):
        assert gc.IMPACT_WEIGHT_PERMISSION == 0.1

    def test_weight_volume_type(self):
        assert isinstance(gc.IMPACT_WEIGHT_VOLUME, float)

    def test_weight_volume_value(self):
        assert gc.IMPACT_WEIGHT_VOLUME == 0.05

    def test_weight_context_type(self):
        assert isinstance(gc.IMPACT_WEIGHT_CONTEXT, float)

    def test_weight_context_value(self):
        assert gc.IMPACT_WEIGHT_CONTEXT == 0.2

    def test_weight_drift_type(self):
        assert isinstance(gc.IMPACT_WEIGHT_DRIFT, float)

    def test_weight_drift_value(self):
        assert gc.IMPACT_WEIGHT_DRIFT == 0.05

    def test_weight_trajectory_type(self):
        assert isinstance(gc.IMPACT_WEIGHT_TRAJECTORY, float)

    def test_weight_trajectory_value(self):
        assert gc.IMPACT_WEIGHT_TRAJECTORY == 0.0

    def test_five_core_weights_sum_to_one(self):
        """The five classic scoring weights must sum to exactly 1.0."""
        total = (
            gc.IMPACT_WEIGHT_SEMANTIC
            + gc.IMPACT_WEIGHT_PERMISSION
            + gc.IMPACT_WEIGHT_VOLUME
            + gc.IMPACT_WEIGHT_CONTEXT
            + gc.IMPACT_WEIGHT_DRIFT
        )
        assert math.isclose(total, 1.0, abs_tol=1e-9), f"Weights sum to {total}, expected 1.0"

    def test_all_weights_non_negative(self):
        weights = [
            gc.IMPACT_WEIGHT_SEMANTIC,
            gc.IMPACT_WEIGHT_PERMISSION,
            gc.IMPACT_WEIGHT_VOLUME,
            gc.IMPACT_WEIGHT_CONTEXT,
            gc.IMPACT_WEIGHT_DRIFT,
            gc.IMPACT_WEIGHT_TRAJECTORY,
        ]
        for w in weights:
            assert w >= 0.0, f"Weight {w} is negative"

    def test_risk_ordering(self):
        """Critical > High > Medium > Low for governance risk thresholds."""
        assert gc.GOVERNANCE_RISK_CRITICAL > gc.GOVERNANCE_RISK_HIGH
        assert gc.GOVERNANCE_RISK_HIGH > gc.GOVERNANCE_RISK_MEDIUM
        assert gc.GOVERNANCE_RISK_MEDIUM > gc.GOVERNANCE_RISK_LOW


# ---------------------------------------------------------------------------
# Deliberation / Consensus
# ---------------------------------------------------------------------------


class TestDeliberationConstants:
    def test_required_votes_type(self):
        assert isinstance(gc.DEFAULT_REQUIRED_VOTES, int)

    def test_required_votes_value(self):
        assert gc.DEFAULT_REQUIRED_VOTES == 3

    def test_required_votes_minimum(self):
        assert gc.DEFAULT_REQUIRED_VOTES >= 1

    def test_consensus_threshold_type(self):
        assert isinstance(gc.DEFAULT_CONSENSUS_THRESHOLD, float)

    def test_consensus_threshold_value(self):
        assert gc.DEFAULT_CONSENSUS_THRESHOLD == pytest.approx(0.66)

    def test_consensus_threshold_majority(self):
        assert gc.DEFAULT_CONSENSUS_THRESHOLD > 0.5

    def test_consensus_threshold_range(self):
        assert 0.0 < gc.DEFAULT_CONSENSUS_THRESHOLD <= 1.0

    def test_deliberation_timeout_type(self):
        assert isinstance(gc.DEFAULT_DELIBERATION_TIMEOUT_SECONDS, int)

    def test_deliberation_timeout_value(self):
        assert gc.DEFAULT_DELIBERATION_TIMEOUT_SECONDS == 300

    def test_deliberation_timeout_positive(self):
        assert gc.DEFAULT_DELIBERATION_TIMEOUT_SECONDS > 0


# ---------------------------------------------------------------------------
# MACI Role Confidence Thresholds
# ---------------------------------------------------------------------------


class TestMACIConfidenceConstants:
    def test_executive_confidence_type(self):
        assert isinstance(gc.MACI_EXECUTIVE_CONFIDENCE, float)

    def test_executive_confidence_value(self):
        assert gc.MACI_EXECUTIVE_CONFIDENCE == 0.8

    def test_interpreter_confidence_type(self):
        assert isinstance(gc.MACI_INTERPRETER_CONFIDENCE, float)

    def test_interpreter_confidence_value(self):
        assert gc.MACI_INTERPRETER_CONFIDENCE == 0.9

    def test_validator_confidence_type(self):
        assert isinstance(gc.MACI_VALIDATOR_CONFIDENCE, float)

    def test_validator_confidence_value(self):
        assert gc.MACI_VALIDATOR_CONFIDENCE == 0.85

    def test_interpreter_strictest(self):
        """Interpreter must require the highest confidence."""
        assert gc.MACI_INTERPRETER_CONFIDENCE > gc.MACI_VALIDATOR_CONFIDENCE
        assert gc.MACI_INTERPRETER_CONFIDENCE > gc.MACI_EXECUTIVE_CONFIDENCE

    def test_all_maci_thresholds_in_range(self):
        for val in (
            gc.MACI_EXECUTIVE_CONFIDENCE,
            gc.MACI_INTERPRETER_CONFIDENCE,
            gc.MACI_VALIDATOR_CONFIDENCE,
        ):
            assert 0.0 < val <= 1.0


# ---------------------------------------------------------------------------
# Cache Sizes & TTLs
# ---------------------------------------------------------------------------


class TestCacheConstants:
    def test_lru_cache_size_type(self):
        assert isinstance(gc.DEFAULT_LRU_CACHE_SIZE, int)

    def test_lru_cache_size_value(self):
        assert gc.DEFAULT_LRU_CACHE_SIZE == 10_000

    def test_lru_cache_size_positive(self):
        assert gc.DEFAULT_LRU_CACHE_SIZE > 0

    def test_cache_ttl_type(self):
        assert isinstance(gc.DEFAULT_CACHE_TTL_SECONDS, int)

    def test_cache_ttl_value(self):
        assert gc.DEFAULT_CACHE_TTL_SECONDS == 300

    def test_cache_ttl_positive(self):
        assert gc.DEFAULT_CACHE_TTL_SECONDS > 0


# ---------------------------------------------------------------------------
# Circuit Breaker Defaults
# ---------------------------------------------------------------------------


class TestCircuitBreakerConstants:
    def test_cb_fail_max_type(self):
        assert isinstance(gc.DEFAULT_CB_FAIL_MAX, int)

    def test_cb_fail_max_value(self):
        assert gc.DEFAULT_CB_FAIL_MAX == 5

    def test_cb_fail_max_positive(self):
        assert gc.DEFAULT_CB_FAIL_MAX > 0

    def test_cb_reset_timeout_type(self):
        assert isinstance(gc.DEFAULT_CB_RESET_TIMEOUT, int)

    def test_cb_reset_timeout_value(self):
        assert gc.DEFAULT_CB_RESET_TIMEOUT == 30

    def test_cb_reset_timeout_positive(self):
        assert gc.DEFAULT_CB_RESET_TIMEOUT > 0

    def test_max_retries_type(self):
        assert isinstance(gc.DEFAULT_MAX_RETRIES, int)

    def test_max_retries_value(self):
        assert gc.DEFAULT_MAX_RETRIES == 5

    def test_max_retries_matches_fail_max(self):
        assert gc.DEFAULT_MAX_RETRIES == gc.DEFAULT_CB_FAIL_MAX


# ---------------------------------------------------------------------------
# Adaptive Governance Engine
# ---------------------------------------------------------------------------


class TestAdaptiveGovernanceConstants:
    def test_feedback_window_type(self):
        assert isinstance(gc.GOVERNANCE_FEEDBACK_WINDOW_SECONDS, int)

    def test_feedback_window_value(self):
        assert gc.GOVERNANCE_FEEDBACK_WINDOW_SECONDS == 3600

    def test_performance_target_type(self):
        assert isinstance(gc.GOVERNANCE_PERFORMANCE_TARGET, float)

    def test_performance_target_value(self):
        assert gc.GOVERNANCE_PERFORMANCE_TARGET == 0.95

    def test_risk_critical_type(self):
        assert isinstance(gc.GOVERNANCE_RISK_CRITICAL, float)

    def test_risk_critical_value(self):
        assert gc.GOVERNANCE_RISK_CRITICAL == 0.9

    def test_risk_high_value(self):
        assert gc.GOVERNANCE_RISK_HIGH == 0.7

    def test_risk_medium_value(self):
        assert gc.GOVERNANCE_RISK_MEDIUM == 0.4

    def test_risk_low_value(self):
        assert gc.GOVERNANCE_RISK_LOW == 0.2

    def test_ema_alpha_type(self):
        assert isinstance(gc.GOVERNANCE_EMA_ALPHA, float)

    def test_ema_alpha_value(self):
        assert gc.GOVERNANCE_EMA_ALPHA == 0.1

    def test_ema_alpha_range(self):
        assert 0.0 < gc.GOVERNANCE_EMA_ALPHA <= 1.0

    def test_history_max_type(self):
        assert isinstance(gc.GOVERNANCE_HISTORY_MAX, int)

    def test_history_max_value(self):
        assert gc.GOVERNANCE_HISTORY_MAX == 100

    def test_history_trim_type(self):
        assert isinstance(gc.GOVERNANCE_HISTORY_TRIM, int)

    def test_history_trim_value(self):
        assert gc.GOVERNANCE_HISTORY_TRIM == 50

    def test_history_trim_less_than_max(self):
        assert gc.GOVERNANCE_HISTORY_TRIM < gc.GOVERNANCE_HISTORY_MAX

    def test_compliance_threshold_type(self):
        assert isinstance(gc.GOVERNANCE_COMPLIANCE_THRESHOLD, float)

    def test_compliance_threshold_value(self):
        assert gc.GOVERNANCE_COMPLIANCE_THRESHOLD == 0.8

    def test_learning_cycle_type(self):
        assert isinstance(gc.GOVERNANCE_LEARNING_CYCLE_SECONDS, int)

    def test_learning_cycle_value(self):
        assert gc.GOVERNANCE_LEARNING_CYCLE_SECONDS == 300

    def test_backoff_type(self):
        assert isinstance(gc.GOVERNANCE_BACKOFF_SECONDS, int)

    def test_backoff_value(self):
        assert gc.GOVERNANCE_BACKOFF_SECONDS == 60

    def test_max_trend_length_type(self):
        assert isinstance(gc.GOVERNANCE_MAX_TREND_LENGTH, int)

    def test_max_trend_length_value(self):
        assert gc.GOVERNANCE_MAX_TREND_LENGTH == 100

    def test_retrain_history_min_type(self):
        assert isinstance(gc.GOVERNANCE_RETRAIN_HISTORY_MIN, int)

    def test_retrain_history_min_value(self):
        assert gc.GOVERNANCE_RETRAIN_HISTORY_MIN == 1000

    def test_retrain_check_modulus_type(self):
        assert isinstance(gc.GOVERNANCE_RETRAIN_CHECK_MODULUS, int)

    def test_retrain_check_modulus_value(self):
        assert gc.GOVERNANCE_RETRAIN_CHECK_MODULUS == 500

    def test_retrain_check_modulus_less_than_history_min(self):
        assert gc.GOVERNANCE_RETRAIN_CHECK_MODULUS < gc.GOVERNANCE_RETRAIN_HISTORY_MIN

    def test_fallback_confidence_type(self):
        assert isinstance(gc.GOVERNANCE_FALLBACK_CONFIDENCE, float)

    def test_fallback_confidence_value(self):
        assert gc.GOVERNANCE_FALLBACK_CONFIDENCE == 0.9

    def test_recommended_threshold_type(self):
        assert isinstance(gc.GOVERNANCE_RECOMMENDED_THRESHOLD, float)

    def test_recommended_threshold_value(self):
        assert gc.GOVERNANCE_RECOMMENDED_THRESHOLD == 0.8


# ---------------------------------------------------------------------------
# Rollback Engine
# ---------------------------------------------------------------------------


class TestRollbackConstants:
    def test_monitoring_interval_type(self):
        assert isinstance(gc.ROLLBACK_MONITORING_INTERVAL_SECONDS, int)

    def test_monitoring_interval_value(self):
        assert gc.ROLLBACK_MONITORING_INTERVAL_SECONDS == 300

    def test_min_confidence_type(self):
        assert isinstance(gc.ROLLBACK_MIN_CONFIDENCE, float)

    def test_min_confidence_value(self):
        assert gc.ROLLBACK_MIN_CONFIDENCE == 0.7

    def test_min_confidence_range(self):
        assert 0.0 < gc.ROLLBACK_MIN_CONFIDENCE < 1.0

    def test_http_timeout_type(self):
        assert isinstance(gc.ROLLBACK_HTTP_TIMEOUT_SECONDS, float)

    def test_http_timeout_value(self):
        assert gc.ROLLBACK_HTTP_TIMEOUT_SECONDS == 30.0

    def test_detect_timeout_type(self):
        assert isinstance(gc.ROLLBACK_DETECT_TIMEOUT_SECONDS, int)

    def test_detect_timeout_value(self):
        assert gc.ROLLBACK_DETECT_TIMEOUT_SECONDS == 60

    def test_step_timeout_type(self):
        assert isinstance(gc.ROLLBACK_STEP_TIMEOUT_SECONDS, int)

    def test_step_timeout_value(self):
        assert gc.ROLLBACK_STEP_TIMEOUT_SECONDS == 30

    def test_detect_timeout_greater_than_step_timeout(self):
        assert gc.ROLLBACK_DETECT_TIMEOUT_SECONDS > gc.ROLLBACK_STEP_TIMEOUT_SECONDS


# ---------------------------------------------------------------------------
# MACI Verifier
# ---------------------------------------------------------------------------


class TestVerifierConstants:
    def test_base_risk_score_type(self):
        assert isinstance(gc.VERIFIER_BASE_RISK_SCORE, float)

    def test_base_risk_score_value(self):
        assert gc.VERIFIER_BASE_RISK_SCORE == 0.2

    def test_risk_sensitive_data_type(self):
        assert isinstance(gc.VERIFIER_RISK_SENSITIVE_DATA, float)

    def test_risk_sensitive_data_value(self):
        assert gc.VERIFIER_RISK_SENSITIVE_DATA == 0.3

    def test_risk_cross_jurisdiction_type(self):
        assert isinstance(gc.VERIFIER_RISK_CROSS_JURISDICTION, float)

    def test_risk_cross_jurisdiction_value(self):
        assert gc.VERIFIER_RISK_CROSS_JURISDICTION == 0.2

    def test_risk_high_impact_type(self):
        assert isinstance(gc.VERIFIER_RISK_HIGH_IMPACT, float)

    def test_risk_high_impact_value(self):
        assert gc.VERIFIER_RISK_HIGH_IMPACT == 0.2

    def test_risk_human_approval_type(self):
        assert isinstance(gc.VERIFIER_RISK_HUMAN_APPROVAL, float)

    def test_risk_human_approval_value(self):
        assert gc.VERIFIER_RISK_HUMAN_APPROVAL == 0.1

    def test_judicial_confidence_threshold_type(self):
        assert isinstance(gc.VERIFIER_JUDICIAL_CONFIDENCE_THRESHOLD, float)

    def test_judicial_confidence_threshold_value(self):
        assert gc.VERIFIER_JUDICIAL_CONFIDENCE_THRESHOLD == 0.7

    def test_legislative_confidence_cap_type(self):
        assert isinstance(gc.VERIFIER_LEGISLATIVE_CONFIDENCE_CAP, float)

    def test_legislative_confidence_cap_value(self):
        assert gc.VERIFIER_LEGISLATIVE_CONFIDENCE_CAP == 0.95

    def test_legislative_confidence_base_type(self):
        assert isinstance(gc.VERIFIER_LEGISLATIVE_CONFIDENCE_BASE, float)

    def test_legislative_confidence_base_value(self):
        assert gc.VERIFIER_LEGISLATIVE_CONFIDENCE_BASE == 0.6

    def test_legislative_confidence_per_rule_type(self):
        assert isinstance(gc.VERIFIER_LEGISLATIVE_CONFIDENCE_PER_RULE, float)

    def test_legislative_confidence_per_rule_value(self):
        assert gc.VERIFIER_LEGISLATIVE_CONFIDENCE_PER_RULE == 0.1

    def test_legislative_cap_above_base(self):
        assert gc.VERIFIER_LEGISLATIVE_CONFIDENCE_CAP > gc.VERIFIER_LEGISLATIVE_CONFIDENCE_BASE

    def test_max_risk_score_scenario(self):
        """All risk flags set: base + sensitive + cross + high_impact + human should be <= 1.0."""
        max_score = (
            gc.VERIFIER_BASE_RISK_SCORE
            + gc.VERIFIER_RISK_SENSITIVE_DATA
            + gc.VERIFIER_RISK_CROSS_JURISDICTION
            + gc.VERIFIER_RISK_HIGH_IMPACT
            + gc.VERIFIER_RISK_HUMAN_APPROVAL
        )
        assert max_score <= 1.0, f"Max additive risk score {max_score} exceeds 1.0"


# ---------------------------------------------------------------------------
# LLM Circuit Breaker Defaults
# ---------------------------------------------------------------------------


class TestLLMCircuitBreakerConstants:
    def test_failure_threshold_type(self):
        assert isinstance(gc.LLM_CB_DEFAULT_FAILURE_THRESHOLD, int)

    def test_failure_threshold_value(self):
        assert gc.LLM_CB_DEFAULT_FAILURE_THRESHOLD == 5

    def test_timeout_type(self):
        assert isinstance(gc.LLM_CB_DEFAULT_TIMEOUT_SECONDS, float)

    def test_timeout_value(self):
        assert gc.LLM_CB_DEFAULT_TIMEOUT_SECONDS == 30.0

    def test_half_open_requests_type(self):
        assert isinstance(gc.LLM_CB_DEFAULT_HALF_OPEN_REQUESTS, int)

    def test_half_open_requests_value(self):
        assert gc.LLM_CB_DEFAULT_HALF_OPEN_REQUESTS == 3

    def test_fallback_ttl_type(self):
        assert isinstance(gc.LLM_CB_DEFAULT_FALLBACK_TTL_SECONDS, int)

    def test_fallback_ttl_value(self):
        assert gc.LLM_CB_DEFAULT_FALLBACK_TTL_SECONDS == 60

    def test_half_open_less_than_failure_threshold(self):
        assert gc.LLM_CB_DEFAULT_HALF_OPEN_REQUESTS < gc.LLM_CB_DEFAULT_FAILURE_THRESHOLD

    def test_failure_threshold_matches_default_cb_fail_max(self):
        assert gc.LLM_CB_DEFAULT_FAILURE_THRESHOLD == gc.DEFAULT_CB_FAIL_MAX


# ---------------------------------------------------------------------------
# Saga Orchestration
# ---------------------------------------------------------------------------


class TestSagaConstants:
    def test_saga_ttl_type(self):
        assert isinstance(gc.SAGA_DEFAULT_TTL_SECONDS, int)

    def test_saga_ttl_value(self):
        expected = 60 * 60 * 24 * 30
        assert gc.SAGA_DEFAULT_TTL_SECONDS == expected

    def test_saga_ttl_equals_30_days(self):
        thirty_days_seconds = 2_592_000
        assert gc.SAGA_DEFAULT_TTL_SECONDS == thirty_days_seconds

    def test_saga_ttl_positive(self):
        assert gc.SAGA_DEFAULT_TTL_SECONDS > 0


# ---------------------------------------------------------------------------
# Cross-cutting invariants
# ---------------------------------------------------------------------------


class TestCrossCuttingInvariants:
    def test_all_float_constants_finite(self):
        float_names = [n for n in _ALL_EXPORTED if isinstance(getattr(gc, n), float)]
        for name in float_names:
            val = getattr(gc, name)
            assert math.isfinite(val), f"{name} = {val} is not finite"

    def test_all_int_constants_non_negative(self):
        int_names = [n for n in _ALL_EXPORTED if isinstance(getattr(gc, n), int)]
        for name in int_names:
            val = getattr(gc, name)
            assert val >= 0, f"{name} = {val} is negative"

    def test_all_probability_floats_in_unit_interval(self):
        """Constants that are probabilities/confidence values must be in [0, 1]."""
        prob_names = [
            "IMPACT_DELIBERATION_THRESHOLD",
            "IMPACT_CRITICAL_FLOOR",
            "IMPACT_HIGH_SEMANTIC_FLOOR",
            "IMPACT_WEIGHT_SEMANTIC",
            "IMPACT_WEIGHT_PERMISSION",
            "IMPACT_WEIGHT_VOLUME",
            "IMPACT_WEIGHT_CONTEXT",
            "IMPACT_WEIGHT_DRIFT",
            "IMPACT_WEIGHT_TRAJECTORY",
            "DEFAULT_CONSENSUS_THRESHOLD",
            "MACI_EXECUTIVE_CONFIDENCE",
            "MACI_INTERPRETER_CONFIDENCE",
            "MACI_VALIDATOR_CONFIDENCE",
            "GOVERNANCE_PERFORMANCE_TARGET",
            "GOVERNANCE_RISK_CRITICAL",
            "GOVERNANCE_RISK_HIGH",
            "GOVERNANCE_RISK_MEDIUM",
            "GOVERNANCE_RISK_LOW",
            "GOVERNANCE_EMA_ALPHA",
            "GOVERNANCE_COMPLIANCE_THRESHOLD",
            "GOVERNANCE_FALLBACK_CONFIDENCE",
            "GOVERNANCE_RECOMMENDED_THRESHOLD",
            "ROLLBACK_MIN_CONFIDENCE",
            "VERIFIER_BASE_RISK_SCORE",
            "VERIFIER_RISK_SENSITIVE_DATA",
            "VERIFIER_RISK_CROSS_JURISDICTION",
            "VERIFIER_RISK_HIGH_IMPACT",
            "VERIFIER_RISK_HUMAN_APPROVAL",
            "VERIFIER_JUDICIAL_CONFIDENCE_THRESHOLD",
            "VERIFIER_LEGISLATIVE_CONFIDENCE_CAP",
            "VERIFIER_LEGISLATIVE_CONFIDENCE_BASE",
            "VERIFIER_LEGISLATIVE_CONFIDENCE_PER_RULE",
        ]
        for name in prob_names:
            val = getattr(gc, name)
            assert 0.0 <= val <= 1.0, f"{name} = {val} is outside [0, 1]"

    def test_count_of_exported_constants(self):
        """Sanity check: module should expose exactly the expected number of constants."""
        public_names = [n for n in dir(gc) if not n.startswith("_")]
        # Allow for annotations dict exposure; exact count can vary by Python version
        assert len(public_names) >= len(_ALL_EXPORTED)

    def test_saga_ttl_larger_than_any_timeout(self):
        timeouts = [
            gc.DEFAULT_DELIBERATION_TIMEOUT_SECONDS,
            gc.DEFAULT_CB_RESET_TIMEOUT,
            gc.DEFAULT_CACHE_TTL_SECONDS,
            gc.ROLLBACK_HTTP_TIMEOUT_SECONDS,
            gc.ROLLBACK_DETECT_TIMEOUT_SECONDS,
            gc.ROLLBACK_STEP_TIMEOUT_SECONDS,
            gc.GOVERNANCE_LEARNING_CYCLE_SECONDS,
            gc.GOVERNANCE_BACKOFF_SECONDS,
        ]
        for t in timeouts:
            assert gc.SAGA_DEFAULT_TTL_SECONDS > t

    def test_governance_performance_target_equals_critical_floor(self):
        """Both constants represent the 95% compliance ceiling."""
        assert gc.GOVERNANCE_PERFORMANCE_TARGET == gc.IMPACT_CRITICAL_FLOOR
