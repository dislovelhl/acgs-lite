"""Tests for acgs_lite.constitution.snapshot coverage gaps."""

from __future__ import annotations

from typing import Any

import pytest

from acgs_lite.constitution import Constitution
from acgs_lite.constitution.snapshot import ConstitutionSnapshot, capture_snapshot


class TestConstitutionSnapshot:
    def test_to_dict_fields(self) -> None:
        snap = ConstitutionSnapshot(
            constitution_name="test",
            constitution_version="1.0",
            constitution_hash="abc123",
            rule_count=5,
            active_rule_count=4,
            rules_summary=({"id": "R1", "severity": "high"},),
            governance_summary={"healthy": True},
            integrity_report={"valid": True},
            metrics_snapshot={},
            routing_summary={},
            timestamp_ns=1000,
            reason="test snapshot",
            metadata={"key": "value"},
        )
        d = snap.to_dict()
        assert d["constitution_name"] == "test"
        assert d["constitution_version"] == "1.0"
        assert d["constitution_hash"] == "abc123"
        assert d["rule_count"] == 5
        assert d["active_rule_count"] == 4
        assert isinstance(d["rules_summary"], list)
        assert d["reason"] == "test snapshot"
        assert d["metadata"] == {"key": "value"}
        assert d["timestamp_ns"] == 1000

    def test_frozen(self) -> None:
        snap = ConstitutionSnapshot(
            constitution_name="test",
            constitution_version="1.0",
            constitution_hash="abc",
            rule_count=0,
            active_rule_count=0,
            rules_summary=(),
            governance_summary={},
            integrity_report={},
            metrics_snapshot={},
            routing_summary={},
            timestamp_ns=0,
        )
        with pytest.raises(AttributeError):
            snap.constitution_name = "changed"  # type: ignore[misc]


class TestCaptureSnapshot:
    def test_basic_capture(self) -> None:
        c = Constitution.default()
        snap = capture_snapshot(c, reason="unit test")
        assert snap.constitution_name == c.name
        assert snap.constitution_hash == c.hash
        assert snap.rule_count == len(c.rules)
        assert snap.reason == "unit test"
        assert snap.timestamp_ns > 0
        assert snap.metrics_snapshot == {}
        assert snap.routing_summary == {}

    def test_with_metadata(self) -> None:
        c = Constitution.default()
        snap = capture_snapshot(c, metadata={"env": "test"})
        assert snap.metadata == {"env": "test"}

    def test_with_metrics(self) -> None:
        from acgs_lite.constitution.metrics import GovernanceMetrics

        c = Constitution.default()
        m = GovernanceMetrics()
        snap = capture_snapshot(c, metrics=m)
        assert isinstance(snap.metrics_snapshot, dict)

    def test_with_router(self) -> None:
        from types import SimpleNamespace

        c = Constitution.default()
        router = SimpleNamespace(summary=lambda: {"routes": 3})
        snap = capture_snapshot(c, router=router)
        assert snap.routing_summary == {"routes": 3}

    def test_to_dict_roundtrip(self) -> None:
        c = Constitution.default()
        snap = capture_snapshot(c, reason="roundtrip")
        d = snap.to_dict()
        assert d["reason"] == "roundtrip"
        assert isinstance(d["rules_summary"], list)
        assert len(d["rules_summary"]) == snap.rule_count
