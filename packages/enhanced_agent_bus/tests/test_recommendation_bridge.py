"""Tests for RecommendationBridge (AmendmentRecommender → ProposalEngine wiring)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from enhanced_agent_bus.adaptive_governance.amendment_recommender import (
    AmendmentRecommendation,
    AmendmentRecommender,
    RecommendationPriority,
    RecommendationTrigger,
)
from enhanced_agent_bus.adaptive_governance.recommendation_bridge import (
    BridgeReport,
    BridgeResult,
    RecommendationBridge,
    recommendation_to_proposal_dict,
)


def _make_recommendation(
    *,
    rec_id: str = "rec-001",
    trigger: RecommendationTrigger = RecommendationTrigger.DTMC_RISK_THRESHOLD,
    priority: RecommendationPriority = RecommendationPriority.HIGH,
    risk: float = 0.85,
) -> AmendmentRecommendation:
    return AmendmentRecommendation(
        recommendation_id=rec_id,
        trigger=trigger,
        priority=priority,
        target_area="governance.high_risk",
        proposed_changes={"threshold": {"from": 0.8, "to": 0.7}},
        justification="DTMC trajectory risk exceeded intervention threshold",
        evidence={"risk_score": risk, "trajectory_prefix": [0, 1, 2, 3]},
        risk_score=risk,
    )


class TestRecommendationToProposalDict:
    def test_basic_transformation(self):
        rec = _make_recommendation()
        result = recommendation_to_proposal_dict(rec)

        assert result["proposed_changes"] == rec.proposed_changes
        assert "DTMC trajectory risk" in result["justification"]
        assert result["proposer_agent_id"] == "adaptive-governance-recommender"
        assert result["target_version"] is None
        assert result["new_version"] is None
        assert result["metadata"]["recommendation_id"] == "rec-001"
        assert result["metadata"]["trigger"] == "dtmc_risk_threshold"
        assert result["metadata"]["priority"] == "high"

    def test_custom_proposer_id(self):
        rec = _make_recommendation()
        result = recommendation_to_proposal_dict(rec, proposer_id="custom-agent")
        assert result["proposer_agent_id"] == "custom-agent"

    def test_justification_minimum_length(self):
        rec = _make_recommendation()
        result = recommendation_to_proposal_dict(rec)
        assert len(result["justification"]) >= 10  # ProposalRequest requires min 10 chars


class TestRecommendationBridge:
    def _make_recommender_with_pending(self, count: int = 2) -> AmendmentRecommender:
        # Use cooldown_minutes=0 to avoid cooldown blocking multiple recommendations
        recommender = AmendmentRecommender(cooldown_minutes=0)
        for i in range(count):
            # Use different trajectory prefixes to target different areas
            prefix = [i % 5]  # Different DTMC states → different target areas
            recommender.evaluate_risk_signal(
                risk_score=0.9 + i * 0.01,
                trajectory_prefix=prefix,
                context={"test": f"rec-{i}"},
            )
        return recommender

    def test_get_pending_as_proposals(self):
        recommender = self._make_recommender_with_pending(3)
        bridge = RecommendationBridge(recommender)

        proposals = bridge.get_pending_as_proposals()
        assert len(proposals) == 3
        for p in proposals:
            assert "proposed_changes" in p
            assert "justification" in p
            assert p["proposer_agent_id"] == "adaptive-governance-recommender"

    @pytest.mark.asyncio
    async def test_dry_run_skips_all(self):
        recommender = self._make_recommender_with_pending(2)
        bridge = RecommendationBridge(recommender, proposal_engine=None)

        report = await bridge.submit_pending()
        assert report.total == 2
        assert report.skipped == 2
        assert report.submitted == 0
        assert report.failed == 0

    @pytest.mark.asyncio
    async def test_submit_with_mock_engine(self):
        recommender = self._make_recommender_with_pending(2)

        class FakeProposal:
            proposal_id = "prop-001"

        class FakeResponse:
            proposal = FakeProposal()

        class MockEngine:
            calls: list = []

            async def create_proposal(self, request):
                self.calls.append(request)
                return FakeResponse()

        engine = MockEngine()
        bridge = RecommendationBridge(recommender, engine, auto_acknowledge=True)

        report = await bridge.submit_pending()
        assert report.submitted == 2
        assert report.failed == 0
        assert len(engine.calls) == 2
        # Auto-acknowledge should have cleared pending
        assert len(recommender.get_pending()) == 0

    @pytest.mark.asyncio
    async def test_engine_failure_continues(self):
        recommender = self._make_recommender_with_pending(3)

        call_count = 0

        class FailingEngine:
            async def create_proposal(self, request):
                nonlocal call_count
                call_count += 1
                if call_count == 2:
                    raise RuntimeError("proposal engine down")

                class FakeResponse:
                    class proposal:
                        proposal_id = f"prop-{call_count}"

                return FakeResponse()

        engine = FailingEngine()
        bridge = RecommendationBridge(recommender, engine, auto_acknowledge=True)

        report = await bridge.submit_pending()
        assert report.submitted == 2
        assert report.failed == 1
        assert report.total == 3

    @pytest.mark.asyncio
    async def test_no_auto_acknowledge(self):
        recommender = self._make_recommender_with_pending(1)

        class MockEngine:
            async def create_proposal(self, request):
                class R:
                    class proposal:
                        proposal_id = "p1"

                return R()

        bridge = RecommendationBridge(
            recommender,
            MockEngine(),
            auto_acknowledge=False,
        )

        await bridge.submit_pending()
        # Should NOT have acknowledged
        assert len(recommender.get_pending()) == 1


class TestBridgeReport:
    def test_summary(self):
        report = BridgeReport(total=5, submitted=3, failed=1, skipped=1)
        s = report.summary()
        assert "5 recommendations" in s
        assert "3 submitted" in s
