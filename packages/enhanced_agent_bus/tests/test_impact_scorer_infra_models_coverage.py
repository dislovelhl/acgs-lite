# Constitutional Hash: 608508a9bd224290
# Sprint 56 — impact_scorer_infra/models.py coverage
"""
Comprehensive tests for src/core/enhanced_agent_bus/impact_scorer_infra/models.py
Target: ≥95% coverage of all classes, methods, and branches.
"""

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.impact_scorer_infra.models import (
    ImpactVector,
    ScoringConfig,
    ScoringMethod,
    ScoringResult,
)

# ---------------------------------------------------------------------------
# ScoringMethod enum
# ---------------------------------------------------------------------------


class TestScoringMethod:
    def test_all_members_exist(self):
        assert ScoringMethod.SEMANTIC.value == "semantic"
        assert ScoringMethod.MINICPM_SEMANTIC.value == "minicpm_semantic"
        assert ScoringMethod.STATISTICAL.value == "statistical"
        assert ScoringMethod.HEURISTIC.value == "heuristic"
        assert ScoringMethod.LEARNING.value == "learning"
        assert ScoringMethod.ENSEMBLE.value == "ensemble"

    def test_member_count(self):
        assert len(ScoringMethod) == 6

    def test_from_value_semantic(self):
        assert ScoringMethod("semantic") is ScoringMethod.SEMANTIC

    def test_from_value_minicpm_semantic(self):
        assert ScoringMethod("minicpm_semantic") is ScoringMethod.MINICPM_SEMANTIC

    def test_from_value_statistical(self):
        assert ScoringMethod("statistical") is ScoringMethod.STATISTICAL

    def test_from_value_heuristic(self):
        assert ScoringMethod("heuristic") is ScoringMethod.HEURISTIC

    def test_from_value_learning(self):
        assert ScoringMethod("learning") is ScoringMethod.LEARNING

    def test_from_value_ensemble(self):
        assert ScoringMethod("ensemble") is ScoringMethod.ENSEMBLE

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            ScoringMethod("invalid_method")

    def test_members_are_unique(self):
        values = [m.value for m in ScoringMethod]
        assert len(values) == len(set(values))

    def test_identity_equality(self):
        assert ScoringMethod.SEMANTIC == ScoringMethod.SEMANTIC
        assert ScoringMethod.SEMANTIC != ScoringMethod.HEURISTIC

    def test_is_enum_instance(self):
        from enum import Enum

        assert isinstance(ScoringMethod.ENSEMBLE, Enum)


# ---------------------------------------------------------------------------
# ScoringConfig dataclass
# ---------------------------------------------------------------------------


class TestScoringConfigDefaults:
    def test_default_semantic_weight(self):
        cfg = ScoringConfig()
        assert cfg.semantic_weight == 0.2

    def test_default_permission_weight(self):
        cfg = ScoringConfig()
        assert cfg.permission_weight == 0.2

    def test_default_volume_weight(self):
        cfg = ScoringConfig()
        assert cfg.volume_weight == 0.15

    def test_default_context_weight(self):
        cfg = ScoringConfig()
        assert cfg.context_weight == 0.15

    def test_default_drift_weight(self):
        cfg = ScoringConfig()
        assert cfg.drift_weight == 0.1

    def test_default_priority_weight(self):
        cfg = ScoringConfig()
        assert cfg.priority_weight == 0.1

    def test_default_type_weight(self):
        cfg = ScoringConfig()
        assert cfg.type_weight == 0.1

    def test_default_high_impact_threshold(self):
        cfg = ScoringConfig()
        assert cfg.high_impact_threshold == 0.8

    def test_default_medium_impact_threshold(self):
        cfg = ScoringConfig()
        assert cfg.medium_impact_threshold == 0.4

    def test_default_high_semantic_threshold(self):
        cfg = ScoringConfig()
        assert cfg.high_semantic_threshold == 0.7

    def test_default_medium_semantic_threshold(self):
        cfg = ScoringConfig()
        assert cfg.medium_semantic_threshold == 0.3

    def test_default_max_volume_per_minute(self):
        cfg = ScoringConfig()
        assert cfg.max_volume_per_minute == 1000

    def test_default_large_transaction_threshold(self):
        cfg = ScoringConfig()
        assert cfg.large_transaction_threshold == 10000.0

    def test_default_small_transaction_threshold(self):
        cfg = ScoringConfig()
        assert cfg.small_transaction_threshold == 100.0

    def test_default_drift_detection_window(self):
        cfg = ScoringConfig()
        assert cfg.drift_detection_window == 100

    def test_default_drift_alert_threshold(self):
        cfg = ScoringConfig()
        assert cfg.drift_alert_threshold == 3.0

    def test_default_critical_priority_boost(self):
        cfg = ScoringConfig()
        assert cfg.critical_priority_boost == 0.9

    def test_default_high_priority_boost(self):
        cfg = ScoringConfig()
        assert cfg.high_priority_boost == 0.5

    def test_default_medium_priority_boost(self):
        cfg = ScoringConfig()
        assert cfg.medium_priority_boost == 0.2

    def test_default_governance_request_boost(self):
        cfg = ScoringConfig()
        assert cfg.governance_request_boost == 0.4

    def test_default_command_boost(self):
        cfg = ScoringConfig()
        assert cfg.command_boost == 0.2

    def test_default_constitutional_validation_boost(self):
        cfg = ScoringConfig()
        assert cfg.constitutional_validation_boost == 0.3

    def test_default_high_semantic_boost(self):
        cfg = ScoringConfig()
        assert cfg.high_semantic_boost == 0.8


class TestScoringConfigCustom:
    def test_custom_weights(self):
        cfg = ScoringConfig(semantic_weight=0.5, permission_weight=0.3)
        assert cfg.semantic_weight == 0.5
        assert cfg.permission_weight == 0.3

    def test_custom_thresholds(self):
        cfg = ScoringConfig(high_impact_threshold=0.9, medium_impact_threshold=0.5)
        assert cfg.high_impact_threshold == 0.9
        assert cfg.medium_impact_threshold == 0.5

    def test_custom_max_volume(self):
        cfg = ScoringConfig(max_volume_per_minute=500)
        assert cfg.max_volume_per_minute == 500

    def test_custom_transaction_thresholds(self):
        cfg = ScoringConfig(large_transaction_threshold=5000.0, small_transaction_threshold=50.0)
        assert cfg.large_transaction_threshold == 5000.0
        assert cfg.small_transaction_threshold == 50.0

    def test_custom_drift_settings(self):
        cfg = ScoringConfig(drift_detection_window=200, drift_alert_threshold=2.5)
        assert cfg.drift_detection_window == 200
        assert cfg.drift_alert_threshold == 2.5

    def test_custom_priority_boosts(self):
        cfg = ScoringConfig(
            critical_priority_boost=1.0,
            high_priority_boost=0.7,
            medium_priority_boost=0.3,
        )
        assert cfg.critical_priority_boost == 1.0
        assert cfg.high_priority_boost == 0.7
        assert cfg.medium_priority_boost == 0.3

    def test_custom_message_type_boosts(self):
        cfg = ScoringConfig(
            governance_request_boost=0.6,
            command_boost=0.3,
            constitutional_validation_boost=0.5,
            high_semantic_boost=0.9,
        )
        assert cfg.governance_request_boost == 0.6
        assert cfg.command_boost == 0.3
        assert cfg.constitutional_validation_boost == 0.5
        assert cfg.high_semantic_boost == 0.9

    def test_zero_weights_allowed(self):
        cfg = ScoringConfig(semantic_weight=0.0, permission_weight=0.0)
        assert cfg.semantic_weight == 0.0
        assert cfg.permission_weight == 0.0

    def test_dataclass_equality(self):
        cfg1 = ScoringConfig()
        cfg2 = ScoringConfig()
        assert cfg1 == cfg2

    def test_dataclass_inequality(self):
        cfg1 = ScoringConfig(semantic_weight=0.1)
        cfg2 = ScoringConfig(semantic_weight=0.9)
        assert cfg1 != cfg2

    def test_is_dataclass(self):
        import dataclasses

        assert dataclasses.is_dataclass(ScoringConfig)

    def test_fields_exist(self):
        import dataclasses

        field_names = {f.name for f in dataclasses.fields(ScoringConfig)}
        assert "semantic_weight" in field_names
        assert "high_impact_threshold" in field_names
        assert "max_volume_per_minute" in field_names
        assert "high_semantic_boost" in field_names


# ---------------------------------------------------------------------------
# ImpactVector dataclass
# ---------------------------------------------------------------------------


class TestImpactVectorDefaults:
    def test_all_defaults_zero(self):
        iv = ImpactVector()
        assert iv.safety == 0.0
        assert iv.security == 0.0
        assert iv.privacy == 0.0
        assert iv.fairness == 0.0
        assert iv.reliability == 0.0
        assert iv.transparency == 0.0
        assert iv.efficiency == 0.0

    def test_to_dict_default(self):
        iv = ImpactVector()
        d = iv.to_dict()
        expected = {
            "safety": 0.0,
            "security": 0.0,
            "privacy": 0.0,
            "fairness": 0.0,
            "reliability": 0.0,
            "transparency": 0.0,
            "efficiency": 0.0,
        }
        assert d == expected

    def test_to_dict_keys(self):
        iv = ImpactVector()
        keys = set(iv.to_dict().keys())
        assert keys == {
            "safety",
            "security",
            "privacy",
            "fairness",
            "reliability",
            "transparency",
            "efficiency",
        }


class TestImpactVectorCustom:
    def test_custom_safety(self):
        iv = ImpactVector(safety=0.9)
        assert iv.safety == 0.9

    def test_custom_security(self):
        iv = ImpactVector(security=0.7)
        assert iv.security == 0.7

    def test_custom_privacy(self):
        iv = ImpactVector(privacy=0.5)
        assert iv.privacy == 0.5

    def test_custom_fairness(self):
        iv = ImpactVector(fairness=0.3)
        assert iv.fairness == 0.3

    def test_custom_reliability(self):
        iv = ImpactVector(reliability=0.8)
        assert iv.reliability == 0.8

    def test_custom_transparency(self):
        iv = ImpactVector(transparency=0.6)
        assert iv.transparency == 0.6

    def test_custom_efficiency(self):
        iv = ImpactVector(efficiency=0.4)
        assert iv.efficiency == 0.4

    def test_all_dimensions_custom(self):
        iv = ImpactVector(
            safety=0.1,
            security=0.2,
            privacy=0.3,
            fairness=0.4,
            reliability=0.5,
            transparency=0.6,
            efficiency=0.7,
        )
        assert iv.safety == 0.1
        assert iv.security == 0.2
        assert iv.privacy == 0.3
        assert iv.fairness == 0.4
        assert iv.reliability == 0.5
        assert iv.transparency == 0.6
        assert iv.efficiency == 0.7

    def test_to_dict_with_custom_values(self):
        iv = ImpactVector(
            safety=0.9,
            security=0.8,
            privacy=0.7,
            fairness=0.6,
            reliability=0.5,
            transparency=0.4,
            efficiency=0.3,
        )
        d = iv.to_dict()
        assert d["safety"] == 0.9
        assert d["security"] == 0.8
        assert d["privacy"] == 0.7
        assert d["fairness"] == 0.6
        assert d["reliability"] == 0.5
        assert d["transparency"] == 0.4
        assert d["efficiency"] == 0.3

    def test_to_dict_returns_plain_dict(self):
        iv = ImpactVector(safety=1.0)
        d = iv.to_dict()
        assert isinstance(d, dict)

    def test_to_dict_value_types_are_float(self):
        iv = ImpactVector(safety=1.0, security=0.5)
        d = iv.to_dict()
        for v in d.values():
            assert isinstance(v, float)

    def test_to_dict_is_independent_copy(self):
        iv = ImpactVector(safety=0.5)
        d = iv.to_dict()
        d["safety"] = 99.0
        # Mutating the dict must not affect the dataclass
        assert iv.safety == 0.5

    def test_dataclass_equality(self):
        iv1 = ImpactVector(safety=0.5)
        iv2 = ImpactVector(safety=0.5)
        assert iv1 == iv2

    def test_dataclass_inequality(self):
        iv1 = ImpactVector(safety=0.5)
        iv2 = ImpactVector(safety=0.9)
        assert iv1 != iv2

    def test_is_dataclass(self):
        import dataclasses

        assert dataclasses.is_dataclass(ImpactVector)

    def test_seven_dimensions(self):
        import dataclasses

        assert len(dataclasses.fields(ImpactVector)) == 7

    def test_boundary_values(self):
        iv = ImpactVector(safety=0.0, security=1.0)
        d = iv.to_dict()
        assert d["safety"] == 0.0
        assert d["security"] == 1.0

    def test_high_precision_float(self):
        iv = ImpactVector(safety=0.123456789)
        d = iv.to_dict()
        assert d["safety"] == pytest.approx(0.123456789)


# ---------------------------------------------------------------------------
# ScoringResult dataclass
# ---------------------------------------------------------------------------


class TestScoringResultBasic:
    def _make_result(self, **kwargs) -> ScoringResult:
        defaults = dict(
            vector=ImpactVector(),
            aggregate_score=0.5,
            method=ScoringMethod.SEMANTIC,
            confidence=0.9,
        )
        defaults.update(kwargs)
        return ScoringResult(**defaults)

    def test_default_version(self):
        r = self._make_result()
        assert r.version == "3.1.0"

    def test_default_metadata_empty_dict(self):
        r = self._make_result()
        assert r.metadata == {}

    def test_stores_vector(self):
        iv = ImpactVector(safety=0.8)
        r = self._make_result(vector=iv)
        assert r.vector.safety == 0.8

    def test_stores_aggregate_score(self):
        r = self._make_result(aggregate_score=0.75)
        assert r.aggregate_score == 0.75

    def test_stores_method(self):
        r = self._make_result(method=ScoringMethod.ENSEMBLE)
        assert r.method is ScoringMethod.ENSEMBLE

    def test_stores_confidence(self):
        r = self._make_result(confidence=0.95)
        assert r.confidence == 0.95

    def test_custom_metadata(self):
        meta = {"model": "distilbert", "tokens": 512}
        r = self._make_result(metadata=meta)
        assert r.metadata["model"] == "distilbert"
        assert r.metadata["tokens"] == 512

    def test_custom_version(self):
        r = self._make_result(version="4.0.0")
        assert r.version == "4.0.0"

    def test_is_dataclass(self):
        import dataclasses

        r = self._make_result()
        assert dataclasses.is_dataclass(r)

    def test_metadata_default_factory_independent(self):
        """Each instance should get its own empty dict, not share the same object."""
        r1 = self._make_result()
        r2 = self._make_result()
        r1.metadata["key"] = "value"
        assert "key" not in r2.metadata

    def test_all_scoring_methods(self):
        for method in ScoringMethod:
            r = self._make_result(method=method)
            assert r.method is method

    def test_equality(self):
        iv = ImpactVector()
        r1 = ScoringResult(
            vector=iv, aggregate_score=0.5, method=ScoringMethod.HEURISTIC, confidence=0.8
        )
        r2 = ScoringResult(
            vector=iv, aggregate_score=0.5, method=ScoringMethod.HEURISTIC, confidence=0.8
        )
        assert r1 == r2

    def test_inequality_different_score(self):
        iv = ImpactVector()
        r1 = ScoringResult(
            vector=iv, aggregate_score=0.5, method=ScoringMethod.HEURISTIC, confidence=0.8
        )
        r2 = ScoringResult(
            vector=iv, aggregate_score=0.9, method=ScoringMethod.HEURISTIC, confidence=0.8
        )
        assert r1 != r2

    def test_inequality_different_method(self):
        iv = ImpactVector()
        r1 = ScoringResult(
            vector=iv, aggregate_score=0.5, method=ScoringMethod.SEMANTIC, confidence=0.8
        )
        r2 = ScoringResult(
            vector=iv, aggregate_score=0.5, method=ScoringMethod.STATISTICAL, confidence=0.8
        )
        assert r1 != r2

    def test_zero_confidence(self):
        r = self._make_result(confidence=0.0)
        assert r.confidence == 0.0

    def test_full_confidence(self):
        r = self._make_result(confidence=1.0)
        assert r.confidence == 1.0

    def test_metadata_with_nested_structure(self):
        meta: dict = {"sub": {"a": 1, "b": [1, 2, 3]}}
        r = self._make_result(metadata=meta)
        assert r.metadata["sub"]["a"] == 1

    def test_vector_to_dict_from_result(self):
        iv = ImpactVector(safety=0.9, efficiency=0.1)
        r = self._make_result(vector=iv)
        d = r.vector.to_dict()
        assert d["safety"] == 0.9
        assert d["efficiency"] == 0.1


# ---------------------------------------------------------------------------
# Integration / cross-class tests
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_scoring_result_with_all_scoring_methods_and_full_vector(self):
        iv = ImpactVector(
            safety=1.0,
            security=1.0,
            privacy=1.0,
            fairness=1.0,
            reliability=1.0,
            transparency=1.0,
            efficiency=1.0,
        )
        for method in ScoringMethod:
            result = ScoringResult(
                vector=iv,
                aggregate_score=1.0,
                method=method,
                confidence=1.0,
                metadata={"method_name": method.value},
            )
            assert result.method is method
            assert result.aggregate_score == 1.0
            assert result.metadata["method_name"] == method.value

    def test_scoring_config_threshold_ordering(self):
        cfg = ScoringConfig()
        assert cfg.medium_impact_threshold < cfg.high_impact_threshold
        assert cfg.medium_semantic_threshold < cfg.high_semantic_threshold

    def test_impact_vector_to_dict_roundtrip(self):
        iv = ImpactVector(
            safety=0.1,
            security=0.2,
            privacy=0.3,
            fairness=0.4,
            reliability=0.5,
            transparency=0.6,
            efficiency=0.7,
        )
        d = iv.to_dict()
        iv2 = ImpactVector(**d)
        assert iv == iv2

    def test_scoring_result_contains_constitutional_hash_in_metadata(self):
        """Verify the system allows storing constitutional hash in metadata."""
        r = ScoringResult(
            vector=ImpactVector(),
            aggregate_score=0.5,
            method=ScoringMethod.ENSEMBLE,
            confidence=0.9,
            metadata={"constitutional_hash": CONSTITUTIONAL_HASH},
        )
        assert r.metadata["constitutional_hash"] == CONSTITUTIONAL_HASH  # pragma: allowlist secret
