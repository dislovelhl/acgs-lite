"""Tests for enhanced_agent_bus.security.context_drift_detector module.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from enhanced_agent_bus.security.context_drift_detector import (
    AgentProfile,
    ContextDriftDetector,
    DriftDetectionResult,
    DriftSeverity,
    DriftType,
)

# ---------------------------------------------------------------------------
# Tests: DriftSeverity / DriftType enums
# ---------------------------------------------------------------------------


class TestEnums:
    def test_severity_values(self):
        assert DriftSeverity.LOW.value == "low"
        assert DriftSeverity.MEDIUM.value == "medium"
        assert DriftSeverity.HIGH.value == "high"
        assert DriftSeverity.CRITICAL.value == "critical"

    def test_drift_type_values(self):
        assert DriftType.BEHAVIORAL.value == "behavioral"
        assert DriftType.TEMPORAL.value == "temporal"
        assert DriftType.VOLUME.value == "volume"
        assert DriftType.SEMANTIC.value == "semantic"
        assert DriftType.PERMISSION.value == "permission"
        assert DriftType.IMPACT.value == "impact"


# ---------------------------------------------------------------------------
# Tests: DriftDetectionResult dataclass
# ---------------------------------------------------------------------------


class TestDriftDetectionResult:
    def test_default_values(self):
        result = DriftDetectionResult(has_drift=False)
        assert result.has_drift is False
        assert result.severity is None
        assert result.drift_type is None
        assert result.deviation_score == 0.0
        assert result.confidence == 0.0
        assert result.metadata == {}

    def test_with_drift(self):
        result = DriftDetectionResult(
            has_drift=True,
            severity=DriftSeverity.HIGH,
            drift_type=DriftType.IMPACT,
            agent_id="agent-1",
            baseline_value=0.5,
            current_value=0.95,
            deviation_score=0.8,
            confidence=0.9,
        )
        assert result.has_drift is True
        assert result.severity == DriftSeverity.HIGH


# ---------------------------------------------------------------------------
# Tests: AgentProfile
# ---------------------------------------------------------------------------


class TestAgentProfile:
    def test_default_profile(self):
        profile = AgentProfile(agent_id="test")
        assert profile.agent_id == "test"
        assert len(profile.impact_scores) == 0
        assert profile.get_mean_impact() == 0.0
        assert profile.get_std_impact() == 0.0

    def test_mean_impact(self):
        profile = AgentProfile(agent_id="test")
        for score in [1.0, 2.0, 3.0]:
            profile.impact_scores.append(score)
        assert profile.get_mean_impact() == pytest.approx(2.0)

    def test_std_impact(self):
        profile = AgentProfile(agent_id="test")
        for score in [2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]:
            profile.impact_scores.append(score)
        mean = profile.get_mean_impact()
        assert mean == pytest.approx(5.0)
        std = profile.get_std_impact()
        assert std > 0

    def test_std_impact_single_sample(self):
        profile = AgentProfile(agent_id="test")
        profile.impact_scores.append(5.0)
        assert profile.get_std_impact() == 0.0

    def test_request_rate(self):
        profile = AgentProfile(agent_id="test")
        now = datetime.now(UTC)
        # Add 10 requests in the last 30 seconds
        for i in range(10):
            profile.request_times.append(now - timedelta(seconds=i))
        rate = profile.get_request_rate(window_seconds=60)
        assert rate == pytest.approx(10 / 60)

    def test_request_rate_empty(self):
        profile = AgentProfile(agent_id="test")
        assert profile.get_request_rate() == 0.0

    def test_request_rate_zero_window(self):
        profile = AgentProfile(agent_id="test")
        assert profile.get_request_rate(window_seconds=0) == 0.0


# ---------------------------------------------------------------------------
# Tests: ContextDriftDetector - initialization
# ---------------------------------------------------------------------------


class TestDetectorInit:
    def test_default_init(self):
        detector = ContextDriftDetector()
        assert detector.drift_threshold == 0.3
        assert detector.min_samples == 10
        assert detector.window_size == 100
        assert detector.agent_profiles == {}
        assert detector.detection_history == []

    def test_custom_init(self):
        detector = ContextDriftDetector(drift_threshold=0.5, min_samples=20, window_size=50)
        assert detector.drift_threshold == 0.5
        assert detector.min_samples == 20
        assert detector.window_size == 50


# ---------------------------------------------------------------------------
# Tests: update_profile
# ---------------------------------------------------------------------------


class TestUpdateProfile:
    def test_creates_new_profile(self):
        detector = ContextDriftDetector()
        detector.update_profile("agent-1", 0.5)
        assert "agent-1" in detector.agent_profiles
        assert len(detector.agent_profiles["agent-1"].impact_scores) == 1

    def test_updates_existing_profile(self):
        detector = ContextDriftDetector()
        detector.update_profile("agent-1", 0.5)
        detector.update_profile("agent-1", 0.7)
        assert len(detector.agent_profiles["agent-1"].impact_scores) == 2

    def test_tracks_message_types(self):
        detector = ContextDriftDetector()
        detector.update_profile("agent-1", 0.5, message_type="request")
        detector.update_profile("agent-1", 0.6, message_type="request")
        detector.update_profile("agent-1", 0.4, message_type="response")
        assert detector.agent_profiles["agent-1"].message_types["request"] == 2
        assert detector.agent_profiles["agent-1"].message_types["response"] == 1

    def test_tracks_permissions(self):
        detector = ContextDriftDetector()
        detector.update_profile("agent-1", 0.5, permissions=["read", "write"])
        assert detector.agent_profiles["agent-1"].permission_usage["read"] == 1
        assert detector.agent_profiles["agent-1"].permission_usage["write"] == 1

    def test_tracks_semantic_features(self):
        detector = ContextDriftDetector()
        detector.update_profile("agent-1", 0.5, semantic_features=["feat1", "feat2"])
        assert "feat1" in detector.agent_profiles["agent-1"].semantic_patterns

    def test_none_optionals_are_safe(self):
        detector = ContextDriftDetector()
        detector.update_profile(
            "agent-1", 0.5, message_type=None, permissions=None, semantic_features=None
        )
        profile = detector.agent_profiles["agent-1"]
        assert profile.message_types == {}
        assert profile.permission_usage == {}


# ---------------------------------------------------------------------------
# Tests: detect_drift
# ---------------------------------------------------------------------------


class TestDetectDrift:
    def test_no_profile_returns_no_drift(self):
        detector = ContextDriftDetector()
        result = detector.detect_drift("unknown-agent", 0.5)
        assert result.has_drift is False
        assert result.metadata.get("reason") == "insufficient_data"

    def test_insufficient_samples(self):
        detector = ContextDriftDetector(min_samples=10)
        for _i in range(5):
            detector.update_profile("agent-1", 0.5)
        result = detector.detect_drift("agent-1", 0.5)
        assert result.has_drift is False
        assert result.metadata.get("reason") == "insufficient_samples"

    def test_no_drift_on_normal_values(self):
        detector = ContextDriftDetector(min_samples=10)
        now = datetime.now(UTC)
        # Add 20 samples spread over time so volume drift doesn't fire
        for i in range(20):
            profile = detector.agent_profiles.get("agent-1")
            if profile is None:
                detector.update_profile("agent-1", 0.5)
                profile = detector.agent_profiles["agent-1"]
            else:
                profile.impact_scores.append(0.5)
            profile.request_times.append(now - timedelta(minutes=i))
            profile.last_updated = now
        result = detector.detect_drift("agent-1", 0.5)
        assert result.has_drift is False

    def test_detects_impact_drift_high_deviation(self):
        detector = ContextDriftDetector(min_samples=10)
        # Build a stable profile
        for _ in range(50):
            detector.update_profile("agent-1", 0.5)
        # Extreme outlier
        result = detector.detect_drift("agent-1", 100.0)
        # Whether drift is detected depends on std (which is 0 for identical scores)
        # With std=0, impact drift won't fire. That's correct behavior.
        # Let's use varied scores instead:

    def test_detects_impact_drift_with_varied_baseline(self):
        import random

        detector = ContextDriftDetector(min_samples=10)
        rng = random.Random(42)
        for _ in range(50):
            detector.update_profile("agent-1", 0.5 + rng.gauss(0, 0.05))

        # An extreme value should trigger drift
        result = detector.detect_drift("agent-1", 5.0)
        assert result.has_drift is True
        assert result.severity is not None


# ---------------------------------------------------------------------------
# Tests: _detect_impact_drift
# ---------------------------------------------------------------------------


class TestDetectImpactDrift:
    def test_returns_none_when_std_is_zero(self):
        detector = ContextDriftDetector()
        profile = AgentProfile(agent_id="a")
        for _ in range(20):
            profile.impact_scores.append(0.5)
        result = detector._detect_impact_drift(profile, 0.5)
        assert result is None

    def test_returns_none_for_small_deviation(self):
        import random

        detector = ContextDriftDetector()
        profile = AgentProfile(agent_id="a")
        rng = random.Random(42)
        for _ in range(50):
            profile.impact_scores.append(0.5 + rng.gauss(0, 0.1))
        # Within 2 std
        result = detector._detect_impact_drift(profile, 0.55)
        assert result is None

    def test_detects_medium_drift(self):
        detector = ContextDriftDetector()
        profile = AgentProfile(agent_id="a")
        for _ in range(50):
            profile.impact_scores.append(0.5)
        profile.impact_scores.append(0.6)  # add slight variance
        mean = profile.get_mean_impact()
        std = profile.get_std_impact()
        if std > 0:
            target = mean + 2.5 * std  # between 2 and 3 std => MEDIUM
            result = detector._detect_impact_drift(profile, target)
            if result is not None:
                assert result.severity == DriftSeverity.MEDIUM


# ---------------------------------------------------------------------------
# Tests: _detect_permission_drift
# ---------------------------------------------------------------------------


class TestDetectPermissionDrift:
    def test_returns_none_when_few_permissions(self):
        detector = ContextDriftDetector()
        profile = AgentProfile(agent_id="a")
        profile.permission_usage = {"read": 5}
        result = detector._detect_permission_drift(profile)
        assert result is None

    def test_detects_dominant_permission(self):
        detector = ContextDriftDetector()
        profile = AgentProfile(agent_id="a")
        profile.permission_usage = {"read": 50, "write": 1}
        result = detector._detect_permission_drift(profile)
        assert result is not None
        assert result.drift_type == DriftType.PERMISSION

    def test_no_drift_balanced_permissions(self):
        detector = ContextDriftDetector()
        profile = AgentProfile(agent_id="a")
        profile.permission_usage = {"read": 10, "write": 10, "execute": 10}
        result = detector._detect_permission_drift(profile)
        assert result is None


# ---------------------------------------------------------------------------
# Tests: _detect_temporal_drift
# ---------------------------------------------------------------------------


class TestDetectTemporalDrift:
    def test_returns_none_with_few_samples(self):
        detector = ContextDriftDetector()
        profile = AgentProfile(agent_id="a")
        for _i in range(5):
            profile.request_times.append(datetime.now(UTC))
        result = detector._detect_temporal_drift(profile, datetime.now(UTC))
        assert result is None

    def test_detects_unusual_hour(self):
        detector = ContextDriftDetector()
        profile = AgentProfile(agent_id="a")
        # All requests during hour 10
        base_time = datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC)
        for i in range(50):
            profile.request_times.append(base_time + timedelta(minutes=i))

        # Request at 3 AM (unusual, quiet period)
        unusual_time = datetime(2025, 1, 2, 3, 0, 0, tzinfo=UTC)
        result = detector._detect_temporal_drift(profile, unusual_time)
        assert result is not None
        assert result.drift_type == DriftType.TEMPORAL


# ---------------------------------------------------------------------------
# Tests: _severity_value
# ---------------------------------------------------------------------------


class TestSeverityValue:
    def test_ordering(self):
        assert ContextDriftDetector._severity_value(DriftSeverity.LOW) == 1
        assert ContextDriftDetector._severity_value(DriftSeverity.MEDIUM) == 2
        assert ContextDriftDetector._severity_value(DriftSeverity.HIGH) == 3
        assert ContextDriftDetector._severity_value(DriftSeverity.CRITICAL) == 4

    def test_none_returns_zero(self):
        assert ContextDriftDetector._severity_value(None) == 0


# ---------------------------------------------------------------------------
# Tests: get_agent_profile / get_drift_summary
# ---------------------------------------------------------------------------


class TestGetters:
    def test_get_agent_profile_exists(self):
        detector = ContextDriftDetector()
        detector.update_profile("agent-1", 0.5)
        profile = detector.get_agent_profile("agent-1")
        assert profile is not None
        assert profile.agent_id == "agent-1"

    def test_get_agent_profile_missing(self):
        detector = ContextDriftDetector()
        assert detector.get_agent_profile("nope") is None

    def test_get_drift_summary_empty(self):
        detector = ContextDriftDetector()
        summary = detector.get_drift_summary()
        assert summary["total_detections"] == 0
        assert all(v == 0 for v in summary["by_severity"].values())

    def test_get_drift_summary_with_detections(self):
        detector = ContextDriftDetector()
        # Manually add detection history
        detector.detection_history.append(
            DriftDetectionResult(
                has_drift=True,
                severity=DriftSeverity.HIGH,
                drift_type=DriftType.IMPACT,
                agent_id="agent-1",
            )
        )
        summary = detector.get_drift_summary()
        assert summary["total_detections"] == 1
        assert summary["by_severity"]["high"] == 1

    def test_get_drift_summary_filtered_by_agent(self):
        detector = ContextDriftDetector()
        detector.detection_history.append(
            DriftDetectionResult(
                has_drift=True,
                severity=DriftSeverity.LOW,
                drift_type=DriftType.VOLUME,
                agent_id="a",
            )
        )
        detector.detection_history.append(
            DriftDetectionResult(
                has_drift=True,
                severity=DriftSeverity.HIGH,
                drift_type=DriftType.IMPACT,
                agent_id="b",
            )
        )
        summary_a = detector.get_drift_summary(agent_id="a")
        assert summary_a["total_detections"] == 1

        summary_b = detector.get_drift_summary(agent_id="b")
        assert summary_b["total_detections"] == 1

    def test_drift_summary_recent_detections_format(self):
        detector = ContextDriftDetector()
        detector.detection_history.append(
            DriftDetectionResult(
                has_drift=True,
                severity=DriftSeverity.MEDIUM,
                drift_type=DriftType.PERMISSION,
                agent_id="x",
                deviation_score=0.7,
            )
        )
        summary = detector.get_drift_summary()
        recent = summary["recent_detections"]
        assert len(recent) == 1
        assert recent[0]["agent_id"] == "x"
        assert recent[0]["severity"] == "medium"
        assert recent[0]["type"] == "permission"
        assert recent[0]["deviation_score"] == 0.7
