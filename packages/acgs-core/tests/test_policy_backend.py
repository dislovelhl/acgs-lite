"""Tests for PolicyBackend ABC and implementations."""

from __future__ import annotations

import pytest

from acgs.policy import HeuristicBackend, PolicyBackend, PolicyDecision


class TestPolicyDecision:
    def test_allowed_decision(self):
        d = PolicyDecision(allowed=True, backend="test")
        assert d.allowed is True
        assert d.violations == []

    def test_denied_decision(self):
        d = PolicyDecision(allowed=False, violations=[{"rule_id": "R1"}], backend="test")
        assert d.allowed is False
        assert len(d.violations) == 1


class TestHeuristicBackend:
    def test_conforms_to_abc(self):
        import acgs

        engine = acgs.GovernanceEngine(acgs.Constitution.default())
        backend = HeuristicBackend(engine)
        assert isinstance(backend, PolicyBackend)
        assert backend.name == "heuristic"

    def test_evaluate_returns_decision(self):
        import acgs

        engine = acgs.GovernanceEngine(acgs.Constitution.default())
        backend = HeuristicBackend(engine)
        decision = backend.evaluate("hello world")
        assert isinstance(decision, PolicyDecision)
        assert decision.allowed is True
        assert decision.backend == "heuristic"

    def test_evaluate_with_violation(self):
        import acgs

        rule = acgs.Rule(
            id="block-test",
            text="Block test keyword",
            severity=acgs.Severity.HIGH,
            keywords=["blocked"],
        )
        engine = acgs.GovernanceEngine(
            acgs.Constitution.from_rules([rule]), strict=False
        )
        backend = HeuristicBackend(engine)
        decision = backend.evaluate("do blocked action")
        assert decision.allowed is False
        assert any(v["rule_id"] == "block-test" for v in decision.violations)


class TestCedarBackend:
    def test_conforms_to_abc(self):
        cedarpy = pytest.importorskip("cedarpy")
        from acgs.cedar import CedarBackend

        backend = CedarBackend("permit(principal, action, resource);")
        assert isinstance(backend, PolicyBackend)
        assert backend.name == "cedar"

    def test_evaluate_permit_all(self):
        pytest.importorskip("cedarpy")
        from acgs.cedar import CedarBackend

        backend = CedarBackend("permit(principal, action, resource);")
        decision = backend.evaluate("read", agent_id="alice")
        assert isinstance(decision, PolicyDecision)
        assert decision.allowed is True
        assert decision.backend == "cedar"

    def test_evaluate_deny_all(self):
        pytest.importorskip("cedarpy")
        from acgs.cedar import CedarBackend

        backend = CedarBackend("forbid(principal, action, resource);")
        decision = backend.evaluate("read", agent_id="alice")
        assert decision.allowed is False

    def test_from_policy_dir(self, tmp_path):
        pytest.importorskip("cedarpy")
        from acgs.cedar import CedarBackend

        (tmp_path / "test.cedar").write_text("permit(principal, action, resource);")
        backend = CedarBackend.from_policy_dir(tmp_path)
        assert backend.evaluate("anything").allowed is True

    def test_fail_closed_on_error(self):
        pytest.importorskip("cedarpy")
        from acgs.cedar import CedarBackend

        backend = CedarBackend("permit(principal, action, resource);")
        backend._policies = "INVALID"
        decision = backend.evaluate("test")
        assert decision.allowed is False

    def test_stats_tracking(self):
        pytest.importorskip("cedarpy")
        from acgs.cedar import CedarBackend

        backend = CedarBackend("permit(principal, action, resource);")
        backend.evaluate("a")
        backend.evaluate("b")
        assert backend.stats["total"] == 2
        assert backend.stats["allowed"] == 2


class TestBackendInterchangeability:
    """Both backends produce PolicyDecision from the same evaluate() call."""

    def test_swap_backends(self):
        cedarpy = pytest.importorskip("cedarpy")
        import acgs
        from acgs.cedar import CedarBackend

        engine = acgs.GovernanceEngine(acgs.Constitution.default())
        heuristic = HeuristicBackend(engine)
        cedar = CedarBackend("permit(principal, action, resource);")

        h_result = heuristic.evaluate("hello")
        c_result = cedar.evaluate("hello")

        # Both return PolicyDecision
        assert type(h_result) is type(c_result) is PolicyDecision
        # Both allowed for safe input
        assert h_result.allowed is True
        assert c_result.allowed is True
