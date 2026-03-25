"""Coverage tests for under-covered governance modules.

Targets:
- voting.py (CondorcetVoting, PolicyBallot) — was 17%
- tags.py (TagRegistry) — was 33%
- routing.py (GovernanceRouter) — was 31%
- sla.py (SLAManager) — was 44%
- trust_score.py (TrustScoreManager) — was 45%
- simulation.py (simulate_constitution_change) — was 28%

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import pytest

# ─── voting.py ────────────────────────────────────────────────────────────────


class TestPolicyBallot:
    def test_basic_ballot(self) -> None:
        from acgs_lite.constitution.voting import PolicyBallot

        b = PolicyBallot(voter_id="alice", ranking=["a", "b", "c"])
        assert b.voter_id == "alice"
        assert b.ranking == ["a", "b", "c"]
        assert b.weight == 1.0
        assert b.timestamp != ""
        assert b.metadata == {}

    def test_ballot_with_weight_and_metadata(self) -> None:
        from acgs_lite.constitution.voting import PolicyBallot

        b = PolicyBallot(
            voter_id="bob",
            ranking=["x", "y"],
            weight=2.5,
            timestamp="2024-01-01T00:00:00Z",
            metadata={"role": "admin"},
        )
        assert b.weight == 2.5
        assert b.timestamp == "2024-01-01T00:00:00Z"
        assert b.metadata == {"role": "admin"}

    def test_empty_ranking_raises(self) -> None:
        from acgs_lite.constitution.voting import PolicyBallot

        with pytest.raises(ValueError, match="at least one option"):
            PolicyBallot(voter_id="x", ranking=[])

    def test_duplicate_ranking_raises(self) -> None:
        from acgs_lite.constitution.voting import PolicyBallot

        with pytest.raises(ValueError, match="duplicate"):
            PolicyBallot(voter_id="x", ranking=["a", "a"])

    def test_prefers_a_over_b(self) -> None:
        from acgs_lite.constitution.voting import PolicyBallot

        b = PolicyBallot(voter_id="x", ranking=["a", "b", "c"])
        assert b.prefers("a", "b") == 1
        assert b.prefers("b", "a") == -1
        assert b.prefers("a", "c") == 1

    def test_prefers_only_one_in_ranking(self) -> None:
        from acgs_lite.constitution.voting import PolicyBallot

        b = PolicyBallot(voter_id="x", ranking=["a", "b"])
        # "c" is not in ranking
        assert b.prefers("a", "c") == 1   # a in ranking, c not
        assert b.prefers("c", "a") == -1  # c not in ranking, a is
        assert b.prefers("c", "d") == 0   # neither in ranking

    def test_to_dict(self) -> None:
        from acgs_lite.constitution.voting import PolicyBallot

        b = PolicyBallot(voter_id="v1", ranking=["opt1", "opt2"], weight=1.5)
        d = b.to_dict()
        assert d["voter_id"] == "v1"
        assert d["ranking"] == ["opt1", "opt2"]
        assert d["weight"] == 1.5

    def test_repr(self) -> None:
        from acgs_lite.constitution.voting import PolicyBallot

        b = PolicyBallot(voter_id="v", ranking=["a"])
        assert "v" in repr(b)


class TestCondorcetVoting:
    def test_too_few_options_raises(self) -> None:
        from acgs_lite.constitution.voting import CondorcetVoting

        with pytest.raises(ValueError, match="at least 2"):
            CondorcetVoting(question="q", options=["only_one"])

    def test_duplicate_options_raises(self) -> None:
        from acgs_lite.constitution.voting import CondorcetVoting

        with pytest.raises(ValueError, match="Duplicate"):
            CondorcetVoting(question="q", options=["a", "a"])

    def test_basic_condorcet_winner(self) -> None:
        from acgs_lite.constitution.voting import CondorcetVoting

        vote = CondorcetVoting(question="Pick", options=["a", "b", "c"], quorum=3)
        vote.cast(voter_id="v1", ranking=["a", "b", "c"])
        vote.cast(voter_id="v2", ranking=["a", "c", "b"])
        vote.cast(voter_id="v3", ranking=["a", "b", "c"])
        result = vote.resolve()
        assert result["winner"] == "a"
        assert result["method"] == "condorcet"
        assert result["quorum_met"] is True

    def test_no_condorcet_winner_falls_back_to_smith_set(self) -> None:
        from acgs_lite.constitution.voting import CondorcetVoting

        # Condorcet paradox: a>b>c>a cycle
        vote = CondorcetVoting(question="Cycle", options=["a", "b", "c"], quorum=3)
        vote.cast(voter_id="v1", ranking=["a", "b", "c"])
        vote.cast(voter_id="v2", ranking=["b", "c", "a"])
        vote.cast(voter_id="v3", ranking=["c", "a", "b"])
        result = vote.resolve()
        assert result["winner"] is None
        assert result["method"] == "smith_set"
        assert len(result["smith_set"]) > 0

    def test_quorum_not_met(self) -> None:
        from acgs_lite.constitution.voting import CondorcetVoting

        vote = CondorcetVoting(question="Q", options=["x", "y"], quorum=5)
        vote.cast(voter_id="solo", ranking=["x", "y"])
        result = vote.resolve()
        assert result["winner"] is None
        assert result["quorum_met"] is False
        assert result["method"] == "quorum_not_met"

    def test_cast_on_closed_ballot_raises(self) -> None:
        from acgs_lite.constitution.voting import CondorcetVoting

        vote = CondorcetVoting(question="Q", options=["a", "b"], quorum=1)
        vote.cast(voter_id="v1", ranking=["a", "b"])
        vote.resolve()
        with pytest.raises(ValueError, match="closed"):
            vote.cast(voter_id="v2", ranking=["b", "a"])

    def test_cast_unknown_option_raises(self) -> None:
        from acgs_lite.constitution.voting import CondorcetVoting

        vote = CondorcetVoting(question="Q", options=["a", "b"])
        with pytest.raises(ValueError, match="Unknown option"):
            vote.cast(voter_id="v", ranking=["a", "z"])

    def test_ballot_update(self) -> None:
        from acgs_lite.constitution.voting import CondorcetVoting

        vote = CondorcetVoting(question="Q", options=["a", "b"], quorum=1)
        vote.cast(voter_id="v1", ranking=["a", "b"])
        vote.cast(voter_id="v1", ranking=["b", "a"])  # update
        assert len(vote.ballots()) == 1

    def test_weighted_votes(self) -> None:
        from acgs_lite.constitution.voting import CondorcetVoting

        vote = CondorcetVoting(question="Q", options=["a", "b"], quorum=2)
        vote.cast(voter_id="heavy", ranking=["a", "b"], weight=10.0)
        vote.cast(voter_id="light", ranking=["b", "a"], weight=1.0)
        result = vote.resolve()
        assert result["winner"] == "a"

    def test_cancel(self) -> None:
        from acgs_lite.constitution.voting import BallotStatus, CondorcetVoting

        vote = CondorcetVoting(question="Q", options=["a", "b"])
        vote.cancel(reason="test")
        assert vote.status == BallotStatus.CANCELLED

    def test_cancel_closed_raises(self) -> None:
        from acgs_lite.constitution.voting import CondorcetVoting

        vote = CondorcetVoting(question="Q", options=["a", "b"], quorum=1)
        vote.cast(voter_id="v", ranking=["a", "b"])
        vote.resolve()
        with pytest.raises(ValueError, match="Cannot cancel"):
            vote.cancel()

    def test_cancel_raises_on_resolve(self) -> None:
        from acgs_lite.constitution.voting import CondorcetVoting

        vote = CondorcetVoting(question="Q", options=["a", "b"])
        vote.cancel()
        with pytest.raises(ValueError, match="cancelled"):
            vote.resolve()

    def test_resolve_already_resolved_returns_cached(self) -> None:
        from acgs_lite.constitution.voting import CondorcetVoting

        vote = CondorcetVoting(question="Q", options=["a", "b"], quorum=1)
        vote.cast(voter_id="v", ranking=["a", "b"])
        r1 = vote.resolve()
        r2 = vote.resolve()
        assert r1 is r2

    def test_summary(self) -> None:
        from acgs_lite.constitution.voting import CondorcetVoting

        vote = CondorcetVoting(question="Q", options=["a", "b"], quorum=2)
        vote.cast(voter_id="v1", ranking=["a", "b"])
        s = vote.summary()
        assert s["ballot_count"] == 1
        assert s["quorum"] == 2
        assert s["quorum_met"] is False
        assert "v1" in s["voters"]

    def test_to_dict(self) -> None:
        from acgs_lite.constitution.voting import CondorcetVoting

        vote = CondorcetVoting(question="Q", options=["a", "b"], quorum=1)
        vote.cast(voter_id="v", ranking=["a", "b"])
        d = vote.to_dict()
        assert "ballots" in d
        assert "result" in d

    def test_repr(self) -> None:
        from acgs_lite.constitution.voting import CondorcetVoting

        vote = CondorcetVoting(question="Test Q", options=["a", "b"])
        assert "Test Q" in repr(vote)

    def test_two_option_vote(self) -> None:
        from acgs_lite.constitution.voting import CondorcetVoting

        vote = CondorcetVoting(question="Binary", options=["yes", "no"], quorum=2)
        vote.cast(voter_id="v1", ranking=["yes", "no"])
        vote.cast(voter_id="v2", ranking=["yes", "no"])
        result = vote.resolve()
        assert result["winner"] == "yes"
        assert "pairwise_summary" in result


# ─── tags.py ──────────────────────────────────────────────────────────────────


class TestTagRegistry:
    def test_tag_and_query(self) -> None:
        from acgs_lite.constitution.tags import TagRegistry

        reg = TagRegistry()
        reg.tag("rule:R1", ["pii", "gdpr"])
        assert "pii" in reg.tags_for("rule:R1")
        assert "rule:R1" in reg.items_for_tag("pii")

    def test_untag(self) -> None:
        from acgs_lite.constitution.tags import TagRegistry

        reg = TagRegistry()
        reg.tag("rule:R1", ["pii", "gdpr"])
        reg.untag("rule:R1", ["pii"])
        assert "pii" not in reg.tags_for("rule:R1")
        assert "gdpr" in reg.tags_for("rule:R1")

    def test_untag_last_tag_removes_item(self) -> None:
        from acgs_lite.constitution.tags import TagRegistry

        reg = TagRegistry()
        reg.tag("rule:R1", ["solo"])
        reg.untag("rule:R1", ["solo"])
        assert reg.tags_for("rule:R1") == set()
        assert "rule:R1" not in reg.all_items()

    def test_untag_nonexistent_item_noop(self) -> None:
        from acgs_lite.constitution.tags import TagRegistry

        reg = TagRegistry()
        reg.untag("nonexistent", ["tag"])  # should not raise

    def test_clear_tags(self) -> None:
        from acgs_lite.constitution.tags import TagRegistry

        reg = TagRegistry()
        reg.tag("item", ["a", "b", "c"])
        reg.clear_tags("item")
        assert reg.tags_for("item") == set()

    def test_remove_item(self) -> None:
        from acgs_lite.constitution.tags import TagRegistry

        reg = TagRegistry()
        reg.tag("item", ["x", "y"])
        reg.remove_item("item")
        assert "item" not in reg.all_items()
        assert reg.items_for_tag("x") == set()

    def test_items_for_any_tag(self) -> None:
        from acgs_lite.constitution.tags import TagRegistry

        reg = TagRegistry()
        reg.tag("r1", ["a"])
        reg.tag("r2", ["b"])
        reg.tag("r3", ["c"])
        result = reg.items_for_any_tag(["a", "b"])
        assert "r1" in result
        assert "r2" in result
        assert "r3" not in result

    def test_items_for_all_tags(self) -> None:
        from acgs_lite.constitution.tags import TagRegistry

        reg = TagRegistry()
        reg.tag("r1", ["a", "b"])
        reg.tag("r2", ["a"])
        result = reg.items_for_all_tags(["a", "b"])
        assert "r1" in result
        assert "r2" not in result

    def test_items_for_all_tags_empty_list(self) -> None:
        from acgs_lite.constitution.tags import TagRegistry

        reg = TagRegistry()
        reg.tag("r1", ["a"])
        assert reg.items_for_all_tags([]) == set()

    def test_rename_tag(self) -> None:
        from acgs_lite.constitution.tags import TagRegistry

        reg = TagRegistry()
        reg.tag("r1", ["critical"])
        reg.tag("r2", ["critical"])
        count = reg.rename_tag("critical", "severity:critical")
        assert count == 2
        assert "severity:critical" in reg.tags_for("r1")
        assert "critical" not in reg.tags_for("r1")

    def test_merge_tags(self) -> None:
        from acgs_lite.constitution.tags import TagRegistry

        reg = TagRegistry()
        reg.tag("r1", ["pii"])
        reg.merge_tags("pii", "gdpr:pii")
        assert "gdpr:pii" in reg.tags_for("r1")
        assert "pii" not in reg.tags_for("r1")

    def test_bulk_tag(self) -> None:
        from acgs_lite.constitution.tags import TagRegistry

        reg = TagRegistry()
        reg.bulk_tag(["r1", "r2", "r3"], ["security"])
        for item in ["r1", "r2", "r3"]:
            assert "security" in reg.tags_for(item)

    def test_bulk_untag(self) -> None:
        from acgs_lite.constitution.tags import TagRegistry

        reg = TagRegistry()
        reg.bulk_tag(["r1", "r2"], ["security", "pii"])
        reg.bulk_untag(["r1", "r2"], ["pii"])
        for item in ["r1", "r2"]:
            assert "pii" not in reg.tags_for(item)
            assert "security" in reg.tags_for(item)

    def test_all_tags(self) -> None:
        from acgs_lite.constitution.tags import TagRegistry

        reg = TagRegistry()
        reg.tag("r1", ["z", "a", "m"])
        tags = reg.all_tags()
        assert tags == sorted(["z", "a", "m"])

    def test_all_items(self) -> None:
        from acgs_lite.constitution.tags import TagRegistry

        reg = TagRegistry()
        reg.tag("r2", ["t"])
        reg.tag("r1", ["t"])
        assert reg.all_items() == ["r1", "r2"]

    def test_tag_stats(self) -> None:
        from acgs_lite.constitution.tags import TagRegistry

        reg = TagRegistry()
        reg.tag("r1", ["a"])
        reg.tag("r2", ["a", "b"])
        stats = reg.tag_stats()
        tag_names = [s.tag for s in stats]
        assert "a" in tag_names
        assert "b" in tag_names
        a_stat = next(s for s in stats if s.tag == "a")
        assert a_stat.item_count == 2

    def test_stats_for_tag(self) -> None:
        from acgs_lite.constitution.tags import TagRegistry

        reg = TagRegistry()
        reg.tag("r1", ["pii"])
        s = reg.stats_for_tag("pii")
        assert s is not None
        assert s.item_count == 1
        assert "r1" in s.items

    def test_stats_for_nonexistent_tag(self) -> None:
        from acgs_lite.constitution.tags import TagRegistry

        reg = TagRegistry()
        assert reg.stats_for_tag("nope") is None

    def test_summary(self) -> None:
        from acgs_lite.constitution.tags import TagRegistry

        reg = TagRegistry()
        reg.tag("r1", ["a", "b"])
        reg.tag("r2", ["b"])
        s = reg.summary()
        assert s["total_tags"] == 2
        assert s["total_items"] == 2
        assert s["total_tag_assignments"] == 3


# ─── routing.py ───────────────────────────────────────────────────────────────


class TestGovernanceRouter:
    def _make_constitution(self, name: str) -> object:
        from acgs_lite import Constitution, Rule

        rules = [Rule(id="R1", text=f"Rule for {name}", keywords=[name])]
        return Constitution.from_rules(rules, name=name)

    def test_resolve_default(self) -> None:
        from acgs_lite.constitution.routing import GovernanceRouter

        default = self._make_constitution("default")
        router = GovernanceRouter(default=default)
        resolved = router.resolve()
        assert resolved is default

    def test_resolve_by_agent_id(self) -> None:
        from acgs_lite.constitution.routing import GovernanceRouter

        default = self._make_constitution("default")
        agent_c = self._make_constitution("agent")
        router = GovernanceRouter(default=default)
        router.add_route("data-agent", agent_c)
        assert router.resolve(agent_id="data-agent") is agent_c
        assert router.resolve(agent_id="unknown") is default

    def test_resolve_by_domain(self) -> None:
        from acgs_lite.constitution.routing import GovernanceRouter

        default = self._make_constitution("default")
        health_c = self._make_constitution("healthcare")
        router = GovernanceRouter(default=default)
        router.add_domain_route("healthcare", health_c)
        assert router.resolve(domain="healthcare") is health_c
        assert router.resolve(domain="finance") is default

    def test_resolve_agent_takes_priority_over_domain(self) -> None:
        from acgs_lite.constitution.routing import GovernanceRouter

        default = self._make_constitution("default")
        agent_c = self._make_constitution("agent")
        domain_c = self._make_constitution("domain")
        router = GovernanceRouter(default=default)
        router.add_route("agent-x", agent_c)
        router.add_domain_route("healthcare", domain_c)
        # agent takes priority even when domain also provided
        assert router.resolve(agent_id="agent-x", domain="healthcare") is agent_c

    def test_resolve_custom_route(self) -> None:
        from acgs_lite.constitution.routing import GovernanceRouter

        default = self._make_constitution("default")
        strict_c = self._make_constitution("strict")
        router = GovernanceRouter(default=default)
        router.add_custom_route(
            "prod-strict",
            lambda context=None, **kw: kw.get("env") == "production",
            strict_c,
        )
        assert router.resolve(env="production") is strict_c
        assert router.resolve(env="staging") is default

    def test_add_route_chaining(self) -> None:
        from acgs_lite.constitution.routing import GovernanceRouter

        default = self._make_constitution("default")
        c1 = self._make_constitution("c1")
        c2 = self._make_constitution("c2")
        router = GovernanceRouter(default=default)
        result = router.add_route("a1", c1).add_domain_route("d1", c2)
        assert result is router

    def test_resolve_with_info_agent(self) -> None:
        from acgs_lite.constitution.routing import GovernanceRouter

        default = self._make_constitution("default")
        agent_c = self._make_constitution("agent")
        router = GovernanceRouter(default=default)
        router.add_route("agent-1", agent_c)
        info = router.resolve_with_info(agent_id="agent-1")
        assert info["route_type"] == "agent"
        assert info["route_key"] == "agent-1"
        assert info["constitution"] is agent_c

    def test_resolve_with_info_domain(self) -> None:
        from acgs_lite.constitution.routing import GovernanceRouter

        default = self._make_constitution("default")
        domain_c = self._make_constitution("fin")
        router = GovernanceRouter(default=default)
        router.add_domain_route("finance", domain_c)
        info = router.resolve_with_info(domain="finance")
        assert info["route_type"] == "domain"
        assert info["route_key"] == "finance"

    def test_resolve_with_info_custom(self) -> None:
        from acgs_lite.constitution.routing import GovernanceRouter

        default = self._make_constitution("default")
        strict_c = self._make_constitution("strict")
        router = GovernanceRouter(default=default)
        router.add_custom_route("high-risk", lambda **kw: kw.get("risk") == "high", strict_c)
        info = router.resolve_with_info(risk="high")
        assert info["route_type"] == "custom"
        assert info["route_key"] == "high-risk"

    def test_resolve_with_info_default(self) -> None:
        from acgs_lite.constitution.routing import GovernanceRouter

        default = self._make_constitution("default")
        router = GovernanceRouter(default=default)
        info = router.resolve_with_info()
        assert info["route_type"] == "default"
        assert info["constitution"] is default

    def test_summary(self) -> None:
        from acgs_lite.constitution.routing import GovernanceRouter

        default = self._make_constitution("default")
        router = GovernanceRouter(default=default)
        router.add_route("a1", self._make_constitution("a1"))
        router.add_domain_route("d1", self._make_constitution("d1"))
        router.add_custom_route("c1", lambda **kw: False, self._make_constitution("c1"))
        s = router.summary()
        assert s["total_routes"] == 3
        assert "a1" in s["agent_routes"]
        assert "d1" in s["domain_routes"]
        assert "c1" in s["custom_routes"]


# ─── sla.py ───────────────────────────────────────────────────────────────────


class TestSLAManager:
    def test_define_and_record_no_breach(self) -> None:
        from acgs_lite.constitution.sla import SLAManager, SLAMetricType, SLATarget

        mgr = SLAManager()
        mgr.define("validate", SLATarget(metric=SLAMetricType.LATENCY_P99, threshold_ms=10.0))
        breaches = mgr.record("validate", latency_ms=5.0)
        assert len(breaches) == 0

    def test_record_triggers_breach(self) -> None:
        from acgs_lite.constitution.sla import SLAManager, SLAMetricType, SLATarget

        mgr = SLAManager()
        mgr.define("validate", SLATarget(metric=SLAMetricType.LATENCY_P99, threshold_ms=10.0))
        breaches = mgr.record("validate", latency_ms=15.0)
        assert len(breaches) == 1
        assert breaches[0].actual_value == 15.0
        assert breaches[0].target_value == 10.0

    def test_error_rate_breach(self) -> None:
        from acgs_lite.constitution.sla import SLAManager, SLAMetricType, SLATarget

        mgr = SLAManager()
        mgr.define(
            "api", SLATarget(metric=SLAMetricType.ERROR_RATE_MAX, threshold_rate=0.1)
        )
        mgr.record("api", success=True)
        mgr.record("api", success=True)
        mgr.record("api", success=False)
        mgr.record("api", success=False)
        # 50% error rate > 10% threshold
        all_breaches = mgr.breaches("api")
        assert len(all_breaches) > 0

    def test_no_breach_for_unknown_operation(self) -> None:
        from acgs_lite.constitution.sla import SLAManager

        mgr = SLAManager()
        breaches = mgr.record("unknown_op", latency_ms=999.0)
        assert breaches == []

    def test_record_batch(self) -> None:
        from acgs_lite.constitution.sla import SLAManager, SLAMetricType, SLATarget

        mgr = SLAManager()
        mgr.define("op", SLATarget(metric=SLAMetricType.LATENCY_P50, threshold_ms=5.0))
        breaches = mgr.record_batch("op", [2.0, 3.0, 10.0, 20.0])
        assert len(breaches) == 2  # 10 and 20 exceed 5ms

    def test_percentile_latency(self) -> None:
        from acgs_lite.constitution.sla import SLAManager

        mgr = SLAManager()
        for ms in [1.0, 2.0, 3.0, 4.0, 100.0]:
            mgr.record("op", latency_ms=ms)
        p50 = mgr.percentile_latency("op", 50)
        assert p50 is not None
        assert p50 < 100.0

    def test_percentile_latency_empty(self) -> None:
        from acgs_lite.constitution.sla import SLAManager

        mgr = SLAManager()
        assert mgr.percentile_latency("noop", 99) is None

    def test_error_rate_empty(self) -> None:
        from acgs_lite.constitution.sla import SLAManager

        mgr = SLAManager()
        assert mgr.error_rate("noop") == 0.0

    def test_error_rate_all_success(self) -> None:
        from acgs_lite.constitution.sla import SLAManager

        mgr = SLAManager()
        mgr.record("op", success=True)
        mgr.record("op", success=True)
        assert mgr.error_rate("op") == 0.0

    def test_breaches_all(self) -> None:
        from acgs_lite.constitution.sla import SLAManager, SLAMetricType, SLATarget

        mgr = SLAManager()
        mgr.define("a", SLATarget(metric=SLAMetricType.LATENCY_P99, threshold_ms=1.0))
        mgr.define("b", SLATarget(metric=SLAMetricType.LATENCY_P99, threshold_ms=1.0))
        mgr.record("a", latency_ms=5.0)
        mgr.record("b", latency_ms=5.0)
        all_b = mgr.breaches()
        assert len(all_b) == 2

    def test_remove_targets(self) -> None:
        from acgs_lite.constitution.sla import SLAManager, SLAMetricType, SLATarget

        mgr = SLAManager()
        mgr.define("op", SLATarget(metric=SLAMetricType.LATENCY_P99, threshold_ms=5.0))
        assert mgr.remove_targets("op") is True
        assert mgr.remove_targets("op") is False

    def test_get_targets(self) -> None:
        from acgs_lite.constitution.sla import SLAManager, SLAMetricType, SLATarget

        mgr = SLAManager()
        t = SLATarget(metric=SLAMetricType.LATENCY_P95, threshold_ms=20.0)
        mgr.define("op", t)
        targets = mgr.get_targets("op")
        assert len(targets) == 1
        assert targets[0].threshold_ms == 20.0

    def test_list_operations(self) -> None:
        from acgs_lite.constitution.sla import SLAManager, SLAMetricType, SLATarget

        mgr = SLAManager()
        mgr.define("a", SLATarget(metric=SLAMetricType.LATENCY_P50, threshold_ms=5.0))
        mgr.define("b", SLATarget(metric=SLAMetricType.LATENCY_P50, threshold_ms=5.0))
        ops = mgr.list_operations()
        assert "a" in ops and "b" in ops

    def test_compliance_report(self) -> None:
        from acgs_lite.constitution.sla import SLAManager, SLAMetricType, SLATarget

        mgr = SLAManager()
        mgr.define("validate", SLATarget(metric=SLAMetricType.LATENCY_P99, threshold_ms=10.0))
        mgr.record("validate", latency_ms=4.0)
        mgr.record("validate", latency_ms=15.0)
        report = mgr.compliance_report()
        assert report["total_observations"] == 2
        assert report["total_breaches"] == 1
        assert "validate" in report["operations"]
        op = report["operations"]["validate"]
        assert op["breach_count"] == 1

    def test_observations(self) -> None:
        from acgs_lite.constitution.sla import SLAManager

        mgr = SLAManager()
        mgr.record("op", latency_ms=3.0)
        mgr.record("op", latency_ms=7.0)
        obs = mgr.observations("op")
        assert len(obs) == 2

    def test_timestamp_override(self) -> None:
        from acgs_lite.constitution.sla import SLAManager, SLAMetricType, SLATarget

        mgr = SLAManager()
        mgr.define("op", SLATarget(metric=SLAMetricType.LATENCY_P99, threshold_ms=5.0))
        mgr.record("op", latency_ms=10.0, timestamp=1000.0)
        b = mgr.breaches("op")
        assert b[0].timestamp == 1000.0

    def test_multiple_targets_same_operation(self) -> None:
        from acgs_lite.constitution.sla import SLAManager, SLAMetricType, SLATarget

        mgr = SLAManager()
        mgr.define("op", SLATarget(metric=SLAMetricType.LATENCY_P50, threshold_ms=5.0))
        mgr.define("op", SLATarget(metric=SLAMetricType.LATENCY_P99, threshold_ms=10.0))
        breaches = mgr.record("op", latency_ms=8.0)
        # Exceeds P50 (5ms) but not P99 (10ms)
        assert len(breaches) == 1


# ─── trust_score.py ───────────────────────────────────────────────────────────


class TestTrustScoreManager:
    def test_register_and_score(self) -> None:
        from acgs_lite.constitution.trust_score import TrustConfig, TrustScoreManager

        mgr = TrustScoreManager()
        mgr.register("agent:a1", TrustConfig(initial_score=0.9))
        assert mgr.score("agent:a1") == pytest.approx(0.9)

    def test_score_unregistered_raises(self) -> None:
        from acgs_lite.constitution.trust_score import TrustScoreManager

        mgr = TrustScoreManager()
        with pytest.raises(KeyError):
            mgr.score("unknown")

    def test_double_register_raises(self) -> None:
        from acgs_lite.constitution.trust_score import TrustConfig, TrustScoreManager

        mgr = TrustScoreManager()
        mgr.register("a", TrustConfig())
        with pytest.raises(ValueError, match="already registered"):
            mgr.register("a", TrustConfig())

    def test_overwrite_register(self) -> None:
        from acgs_lite.constitution.trust_score import TrustConfig, TrustScoreManager

        mgr = TrustScoreManager()
        mgr.register("a", TrustConfig(initial_score=1.0))
        mgr.register("a", TrustConfig(initial_score=0.5), overwrite=True)
        assert mgr.score("a") == pytest.approx(0.5)

    def test_compliant_decision_recovers_score(self) -> None:
        from acgs_lite.constitution.trust_score import TrustConfig, TrustScoreManager

        mgr = TrustScoreManager()
        mgr.register("a", TrustConfig(initial_score=0.7, recovery_per_decision=0.1))
        mgr.record_decision("a", compliant=True)
        assert mgr.score("a") == pytest.approx(0.8)

    def test_score_capped_at_1(self) -> None:
        from acgs_lite.constitution.trust_score import TrustConfig, TrustScoreManager

        mgr = TrustScoreManager()
        mgr.register("a", TrustConfig(initial_score=1.0))
        mgr.record_decision("a", compliant=True)
        assert mgr.score("a") == pytest.approx(1.0)

    def test_violation_decreases_score(self) -> None:
        from acgs_lite.constitution.trust_score import TrustConfig, TrustScoreManager

        mgr = TrustScoreManager()
        mgr.register("a", TrustConfig(initial_score=1.0))
        mgr.record_decision("a", compliant=False, severity="critical")
        assert mgr.score("a") == pytest.approx(0.8)

    def test_severity_penalties(self) -> None:
        from acgs_lite.constitution.trust_score import TrustConfig, TrustScoreManager

        for severity, expected_penalty in [
            ("critical", 0.20),
            ("high", 0.10),
            ("medium", 0.05),
            ("low", 0.02),
        ]:
            mgr = TrustScoreManager()
            mgr.register("a", TrustConfig(initial_score=1.0))
            mgr.record_decision("a", compliant=False, severity=severity)
            assert mgr.score("a") == pytest.approx(1.0 - expected_penalty)

    def test_unknown_severity_uses_medium(self) -> None:
        from acgs_lite.constitution.trust_score import TrustConfig, TrustScoreManager

        mgr = TrustScoreManager()
        mgr.register("a", TrustConfig(initial_score=1.0))
        mgr.record_decision("a", compliant=False, severity="exotic")
        assert mgr.score("a") == pytest.approx(0.95)  # medium penalty

    def test_score_floored_at_decay_floor(self) -> None:
        from acgs_lite.constitution.trust_score import TrustConfig, TrustScoreManager

        mgr = TrustScoreManager()
        mgr.register("a", TrustConfig(initial_score=0.1, decay_floor=0.1))
        mgr.record_decision("a", compliant=False, severity="critical")
        assert mgr.score("a") >= 0.1

    def test_tier_trusted(self) -> None:
        from acgs_lite.constitution.trust_score import TrustConfig, TrustScoreManager

        mgr = TrustScoreManager()
        mgr.register("a", TrustConfig(initial_score=1.0, trusted_threshold=0.8))
        assert mgr.tier("a") == "trusted"

    def test_tier_monitored(self) -> None:
        from acgs_lite.constitution.trust_score import TrustConfig, TrustScoreManager

        mgr = TrustScoreManager()
        mgr.register(
            "a",
            TrustConfig(initial_score=0.6, trusted_threshold=0.8, monitored_threshold=0.5),
        )
        assert mgr.tier("a") == "monitored"

    def test_tier_restricted(self) -> None:
        from acgs_lite.constitution.trust_score import TrustConfig, TrustScoreManager

        mgr = TrustScoreManager()
        mgr.register(
            "a",
            TrustConfig(initial_score=0.3, trusted_threshold=0.8, monitored_threshold=0.5),
        )
        assert mgr.tier("a") == "restricted"

    def test_tier_unregistered_raises(self) -> None:
        from acgs_lite.constitution.trust_score import TrustScoreManager

        mgr = TrustScoreManager()
        with pytest.raises(KeyError):
            mgr.tier("ghost")

    def test_auto_register_on_record(self) -> None:
        from acgs_lite.constitution.trust_score import TrustScoreManager

        mgr = TrustScoreManager()
        mgr.record_decision("new-agent", compliant=True)
        assert mgr.score("new-agent") <= 1.0

    def test_history(self) -> None:
        from acgs_lite.constitution.trust_score import TrustConfig, TrustScoreManager

        mgr = TrustScoreManager()
        mgr.register("a", TrustConfig())
        mgr.record_decision("a", compliant=True)
        mgr.record_decision("a", compliant=False, severity="high")
        h = mgr.history("a")
        assert len(h) == 2
        assert h[0].compliant is True
        assert h[1].compliant is False
        assert h[1].severity == "high"

    def test_history_unregistered_raises(self) -> None:
        from acgs_lite.constitution.trust_score import TrustScoreManager

        mgr = TrustScoreManager()
        with pytest.raises(KeyError):
            mgr.history("ghost")

    def test_restricted_agents(self) -> None:
        from acgs_lite.constitution.trust_score import TrustConfig, TrustScoreManager

        mgr = TrustScoreManager()
        mgr.register(
            "low-trust",
            TrustConfig(initial_score=0.1, trusted_threshold=0.8, monitored_threshold=0.5),
        )
        mgr.register("high-trust", TrustConfig(initial_score=1.0))
        restricted = mgr.restricted_agents()
        assert "low-trust" in restricted
        assert "high-trust" not in restricted

    def test_list_agents(self) -> None:
        from acgs_lite.constitution.trust_score import TrustConfig, TrustScoreManager

        mgr = TrustScoreManager()
        mgr.register("b", TrustConfig())
        mgr.register("a", TrustConfig())
        assert mgr.list_agents() == ["a", "b"]

    def test_summary(self) -> None:
        from acgs_lite.constitution.trust_score import TrustConfig, TrustScoreManager

        mgr = TrustScoreManager()
        mgr.register("a", TrustConfig(initial_score=1.0))
        mgr.register(
            "b",
            TrustConfig(initial_score=0.1, trusted_threshold=0.8, monitored_threshold=0.5),
        )
        mgr.record_decision("a", compliant=False, severity="high", note="test note")
        s = mgr.summary()
        assert s["agent_count"] == 2
        assert s["restricted_count"] >= 1

    def test_trust_config_validation(self) -> None:
        from acgs_lite.constitution.trust_score import TrustConfig

        with pytest.raises(ValueError):
            TrustConfig(initial_score=1.5)  # > 1.0

        with pytest.raises(ValueError):
            TrustConfig(monitored_threshold=0.9, trusted_threshold=0.5)  # monitored > trusted

    def test_event_fields(self) -> None:
        from acgs_lite.constitution.trust_score import TrustConfig, TrustScoreManager

        mgr = TrustScoreManager()
        mgr.register("a", TrustConfig(initial_score=1.0))
        evt = mgr.record_decision("a", compliant=False, severity="medium", note="audit note")
        assert evt.agent_id == "a"
        assert evt.compliant is False
        assert evt.severity == "medium"
        assert evt.delta < 0
        assert evt.note == "audit note"
        assert evt.score_before > evt.score_after


# ─── simulation.py ────────────────────────────────────────────────────────────


class TestSimulateConstitutionChange:
    def _make_constitution(self) -> object:
        from acgs_lite import Constitution, Rule

        rules = [
            Rule(id="R1", text="allow data access", keywords=["data", "access"]),
            Rule(id="R2", text="deny pii export", keywords=["pii", "export"], enabled=True),
        ]
        return Constitution.from_rules(rules, name="test")

    def test_no_changes_no_change_rate(self) -> None:
        from acgs_lite.constitution.simulation import simulate_constitution_change

        c = self._make_constitution()
        report = simulate_constitution_change(c, ["access data"], {})
        assert report.total == 1
        assert isinstance(report.change_rate, float)
        assert report.to_dict()["total"] == 1

    def test_remove_rule_changes_decision(self) -> None:
        from acgs_lite.constitution.simulation import simulate_constitution_change

        c = self._make_constitution()
        report = simulate_constitution_change(
            c,
            ["pii export", "access data"],
            {"remove": ["R2"]},
        )
        assert report.summary["rule_changes"]["removed"] == 1
        assert report.total == 2

    def test_add_rule(self) -> None:
        from acgs_lite.constitution.simulation import simulate_constitution_change

        c = self._make_constitution()
        new_rule = {"id": "R3", "text": "deny secret access", "keywords": ["secret"]}
        report = simulate_constitution_change(c, ["access secret"], {"add": [new_rule]})
        assert report.summary["rule_changes"]["added"] == 1

    def test_update_rule(self) -> None:
        from acgs_lite.constitution.simulation import simulate_constitution_change

        c = self._make_constitution()
        report = simulate_constitution_change(
            c,
            ["access data"],
            {"update": {"R1": {"text": "deny data access", "keywords": ["data", "access"]}}},
        )
        assert report.summary["rule_changes"]["updated"] == 1

    def test_empty_actions_list(self) -> None:
        from acgs_lite.constitution.simulation import simulate_constitution_change

        c = self._make_constitution()
        report = simulate_constitution_change(c, [], {})
        assert report.total == 0
        assert report.change_rate == 0.0

    def test_simulation_result_structure(self) -> None:
        from acgs_lite.constitution.simulation import simulate_constitution_change

        c = self._make_constitution()
        report = simulate_constitution_change(c, ["action1", "action2"], {})
        d = report.to_dict()
        assert "results" in d
        assert len(d["results"]) == 2
        for r in d["results"]:
            assert "action" in r
            assert "before_decision" in r
            assert "after_decision" in r
            assert "changed" in r

    def test_transitions_counted(self) -> None:
        from acgs_lite.constitution.simulation import simulate_constitution_change

        c = self._make_constitution()
        report = simulate_constitution_change(c, ["a1", "a2", "a3"], {})
        assert isinstance(report.summary["transitions"], dict)
