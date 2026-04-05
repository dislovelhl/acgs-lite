"""Tests for TierManager — Phase 5."""

from __future__ import annotations

import pytest
from constitutional_swarm.bittensor.protocol import TIER_TAO_MULTIPLIER, MinerTier
from constitutional_swarm.bittensor.tier_manager import (
    _COMPLEXITY_MIN_TIER,
    MinerPerformance,
    TaskComplexity,
    TierManager,
)
from constitutional_swarm.capability import CapabilityRegistry

# ---------------------------------------------------------------------------
# TaskComplexity → min tier mapping
# ---------------------------------------------------------------------------


class TestComplexityMapping:
    def test_low_requires_apprentice(self):
        assert _COMPLEXITY_MIN_TIER[TaskComplexity.LOW] == MinerTier.APPRENTICE

    def test_medium_requires_journeyman(self):
        assert _COMPLEXITY_MIN_TIER[TaskComplexity.MEDIUM] == MinerTier.JOURNEYMAN

    def test_high_requires_master(self):
        assert _COMPLEXITY_MIN_TIER[TaskComplexity.HIGH] == MinerTier.MASTER

    def test_constitutional_requires_elder(self):
        assert _COMPLEXITY_MIN_TIER[TaskComplexity.CONSTITUTIONAL] == MinerTier.ELDER


# ---------------------------------------------------------------------------
# MinerPerformance
# ---------------------------------------------------------------------------


class TestMinerPerformance:
    def test_acceptance_rate_empty(self):
        perf = MinerPerformance("m1")
        assert perf.acceptance_rate == 0.0

    def test_acceptance_rate(self):
        perf = MinerPerformance("m1", judgments_validated=8, judgments_rejected=2)
        assert perf.acceptance_rate == pytest.approx(0.8)

    def test_domain_specialist(self):
        perf = MinerPerformance("m1", domains={"finance"})
        assert perf.is_domain_specialist is True

    def test_not_domain_specialist_empty(self):
        perf = MinerPerformance("m1")
        assert perf.is_domain_specialist is False

    def test_summary(self):
        perf = MinerPerformance("m1", current_tier=MinerTier.JOURNEYMAN)
        s = perf.summary()
        assert s["current_tier"] == "journeyman"
        assert s["tao_multiplier"] == TIER_TAO_MULTIPLIER[MinerTier.JOURNEYMAN]


# ---------------------------------------------------------------------------
# TierManager — registration
# ---------------------------------------------------------------------------


class TestTierManagerRegistration:
    def test_register_miner(self):
        mgr = TierManager()
        perf = mgr.register_miner("miner-01")
        assert perf.miner_uid == "miner-01"
        assert perf.current_tier == MinerTier.APPRENTICE

    def test_register_with_domains(self):
        mgr = TierManager()
        mgr.register_miner("miner-01", domains={"finance", "healthcare"})
        perf = mgr.get_performance("miner-01")
        assert "finance" in perf.domains

    def test_register_idempotent(self):
        mgr = TierManager()
        mgr.register_miner("m1")
        mgr.register_miner("m1")
        assert len(mgr.all_miners) == 1

    def test_unregister(self):
        mgr = TierManager()
        mgr.register_miner("m1")
        mgr.unregister_miner("m1")
        assert mgr.get_performance("m1") is None

    def test_registry_synced_on_register(self):
        reg = CapabilityRegistry()
        mgr = TierManager(reg)
        mgr.register_miner("m1", domains={"finance"})
        assert "m1" in reg.agents


# ---------------------------------------------------------------------------
# TierManager — performance recording + tier promotion
# ---------------------------------------------------------------------------


class TestTierPromotion:
    def test_apprentice_no_promotion_below_threshold(self):
        mgr = TierManager()
        mgr.register_miner("m1")
        for _ in range(9):  # need 10 for Journeyman
            mgr.record_judgment("m1", accepted=True)
        perf = mgr.get_performance("m1")
        assert perf.current_tier == MinerTier.APPRENTICE

    def test_promote_to_journeyman(self):
        mgr = TierManager()
        mgr.register_miner("m1")
        promotion = None
        for _i in range(10):
            result = mgr.record_judgment("m1", accepted=True, reputation=1.3)
            if result is not None:
                promotion = result
        assert promotion is not None
        assert promotion.to_tier == MinerTier.JOURNEYMAN
        assert promotion.is_promotion

    def test_promote_to_master(self):
        mgr = TierManager()
        mgr.register_miner("m1", domains={"finance"})
        promotion = None
        for _i in range(50):
            result = mgr.record_judgment("m1", accepted=True, reputation=1.6)
            if result is not None and result.to_tier == MinerTier.MASTER:
                promotion = result
        assert promotion is not None
        assert promotion.to_tier == MinerTier.MASTER

    def test_master_requires_domain_specialist(self):
        mgr = TierManager()
        mgr.register_miner("m1")  # no domains
        for _ in range(50):
            mgr.record_judgment("m1", accepted=True, reputation=1.6)
        perf = mgr.get_performance("m1")
        # No domain → can't reach Master
        assert perf.current_tier != MinerTier.MASTER

    def test_promote_to_elder(self):
        mgr = TierManager()
        mgr.register_miner("m1", domains={"finance"})
        promotion = None
        for _i in range(200):
            result = mgr.record_judgment("m1", accepted=True, reputation=1.9)
            if result is not None and result.to_tier == MinerTier.ELDER:
                promotion = result
        assert promotion is not None
        assert promotion.to_tier == MinerTier.ELDER

    def test_record_precedent_contributes(self):
        mgr = TierManager()
        mgr.register_miner("m1")
        mgr.record_precedent("m1")
        perf = mgr.get_performance("m1")
        assert perf.precedents_contributed == 1

    def test_domain_added_on_judgment(self):
        mgr = TierManager()
        mgr.register_miner("m1")
        mgr.record_judgment("m1", accepted=True, domain="healthcare")
        perf = mgr.get_performance("m1")
        assert "healthcare" in perf.domains

    def test_authenticity_rolling_average(self):
        mgr = TierManager()
        mgr.register_miner("m1")
        mgr.record_judgment("m1", accepted=True, authenticity=0.8)
        mgr.record_judgment("m1", accepted=True, authenticity=0.6)
        perf = mgr.get_performance("m1")
        # EMA from 0: after 0.8 → 0.16; after 0.6 → 0.248
        # Should be positive and below the max input
        assert 0.0 < perf.avg_authenticity < 0.8

    def test_auto_register_on_first_judgment(self):
        mgr = TierManager()
        mgr.record_judgment("unregistered-miner", accepted=True)
        assert mgr.get_performance("unregistered-miner") is not None

    def test_promotion_log_recorded(self):
        mgr = TierManager()
        mgr.register_miner("m1")
        for _ in range(10):
            mgr.record_judgment("m1", accepted=True, reputation=1.3)
        assert len(mgr.promotion_log) >= 1

    def test_evaluate_all_tiers(self):
        mgr = TierManager()
        mgr.register_miner("m1")
        mgr.register_miner("m2")
        # Manually set stats to trigger promotion
        mgr._miners["m1"].judgments_validated = 10
        mgr._miners["m1"].reputation = 1.3
        promotions = mgr.evaluate_all_tiers()
        assert any(p.miner_uid == "m1" for p in promotions)

    def test_tier_distribution(self):
        mgr = TierManager()
        mgr.register_miner("a")
        mgr.register_miner("b")
        dist = mgr.tier_distribution()
        assert dist["apprentice"] == 2

    def test_summary(self):
        mgr = TierManager()
        mgr.register_miner("m1")
        s = mgr.summary()
        assert s["total_miners"] == 1
        assert "tier_distribution" in s


# ---------------------------------------------------------------------------
# TierManager — task routing
# ---------------------------------------------------------------------------


class TestTaskRouting:
    def _setup_mixed_tiers(self) -> TierManager:
        mgr = TierManager()
        # Apprentice
        mgr.register_miner("apprentice", domains={"general"})
        # Journeyman
        mgr.register_miner("journeyman", domains={"finance"})
        mgr._miners["journeyman"].judgments_validated = 10
        mgr._miners["journeyman"].reputation = 1.3
        mgr._miners["journeyman"].current_tier = MinerTier.JOURNEYMAN
        # Master
        mgr.register_miner("master", domains={"finance", "healthcare"})
        mgr._miners["master"].judgments_validated = 50
        mgr._miners["master"].reputation = 1.6
        mgr._miners["master"].current_tier = MinerTier.MASTER
        return mgr

    def test_route_low_any_tier(self):
        mgr = self._setup_mixed_tiers()
        result = mgr.route_task("t1", TaskComplexity.LOW)
        assert result.selected_miner is not None
        assert len(result.eligible_miners) == 3  # all tiers eligible

    def test_route_medium_journeyman_plus(self):
        mgr = self._setup_mixed_tiers()
        result = mgr.route_task("t1", TaskComplexity.MEDIUM)
        assert result.selected_miner in ("journeyman", "master")
        assert "apprentice" not in result.eligible_miners

    def test_route_high_master_only(self):
        mgr = self._setup_mixed_tiers()
        result = mgr.route_task("t1", TaskComplexity.HIGH)
        assert result.selected_miner == "master"

    def test_route_constitutional_no_elder(self):
        mgr = self._setup_mixed_tiers()
        result = mgr.route_task("t1", TaskComplexity.CONSTITUTIONAL)
        assert result.selected_miner is None  # no Elder registered
        assert "No miners" in result.selection_reason

    def test_route_prefers_domain_specialist(self):
        mgr = self._setup_mixed_tiers()
        # Both journeyman and master are eligible for MEDIUM
        result = mgr.route_task("t1", TaskComplexity.MEDIUM, domain="finance")
        # Both have "finance", but master has higher tier → master wins
        assert result.selected_miner == "master"

    def test_eligible_miners_by_complexity(self):
        mgr = self._setup_mixed_tiers()
        eligible = mgr.eligible_miners(TaskComplexity.MEDIUM)
        uids = {p.miner_uid for p in eligible}
        assert "apprentice" not in uids
        assert "journeyman" in uids
        assert "master" in uids

    def test_route_empty_registry(self):
        mgr = TierManager()
        result = mgr.route_task("t1", TaskComplexity.LOW)
        assert result.selected_miner is None

    def test_routing_result_fields(self):
        mgr = self._setup_mixed_tiers()
        result = mgr.route_task("t1", TaskComplexity.LOW)
        assert result.task_id == "t1"
        assert result.complexity == TaskComplexity.LOW
        assert result.min_tier_required == MinerTier.APPRENTICE
