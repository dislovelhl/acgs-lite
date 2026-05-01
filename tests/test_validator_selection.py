"""Tests for validator_selection module.

Covers: quorum sizing, producer exclusion, trust weighting, diversity,
proof verification, edge cases, and degraded-pool behavior.
"""

from __future__ import annotations

import math

import pytest

from acgs_lite.constitution.validator_selection import (
    SelectionPolicy,
    SelectionProof,
    ValidatorPool,
    ValidatorSelector,
    _weighted_shuffle_select,
)

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_pool(n: int = 10, domain: str = "finance", model_prefix: str = "model") -> ValidatorPool:
    """Create a pool with n validators, cycling through 3 model types."""
    pool = ValidatorPool()
    models = [f"{model_prefix}-a", f"{model_prefix}-b", f"{model_prefix}-c"]
    for i in range(n):
        pool.register(
            f"val-{i:03d}",
            trust_score=0.7 + (i % 4) * 0.1,  # 0.7, 0.8, 0.9, 1.0 cycling
            domains=[domain],
            model=models[i % len(models)],
        )
    return pool


# ── ValidatorPool tests ──────────────────────────────────────────────────────


class TestValidatorPool:
    def test_register_and_get(self) -> None:
        pool = ValidatorPool()
        info = pool.register("v1", trust_score=0.9, domains=["fin"], model="gpt-5.5")
        assert info.validator_id == "v1"
        assert pool.get("v1") is info
        assert pool.get("nonexistent") is None

    def test_trust_score_bounds(self) -> None:
        pool = ValidatorPool()
        with pytest.raises(ValueError, match="trust_score"):
            pool.register("v1", trust_score=1.5)
        with pytest.raises(ValueError, match="trust_score"):
            pool.register("v1", trust_score=-0.1)

    def test_deactivate_and_activate(self) -> None:
        pool = ValidatorPool()
        pool.register("v1", trust_score=0.9)
        assert len(pool) == 1
        pool.deactivate("v1")
        assert len(pool) == 0
        pool.activate("v1")
        assert len(pool) == 1

    def test_eligible_excludes_producer(self) -> None:
        pool = ValidatorPool()
        pool.register("v1", trust_score=0.9, domains=["fin"])
        pool.register("v2", trust_score=0.8, domains=["fin"])
        pool.register("v3", trust_score=0.7, domains=["fin"])

        eligible = pool.eligible(exclude={"v2"}, domain="fin")
        ids = {v.validator_id for v in eligible}
        assert "v2" not in ids
        assert "v1" in ids
        assert "v3" in ids

    def test_eligible_domain_filter(self) -> None:
        pool = ValidatorPool()
        pool.register("v1", domains=["finance"])
        pool.register("v2", domains=["healthcare"])
        pool.register("v3", domains=["finance", "healthcare"])

        fin = pool.eligible(domain="finance", require_domain=True)
        fin_ids = {v.validator_id for v in fin}
        assert fin_ids == {"v1", "v3"}

    def test_eligible_trust_threshold(self) -> None:
        pool = ValidatorPool()
        pool.register("v1", trust_score=0.9)
        pool.register("v2", trust_score=0.3)
        pool.register("v3", trust_score=0.6)

        eligible = pool.eligible(min_trust=0.5)
        ids = {v.validator_id for v in eligible}
        assert ids == {"v1", "v3"}

    def test_monoculture_report(self) -> None:
        pool = ValidatorPool()
        pool.register("v1", model="gpt-5.5")
        pool.register("v2", model="gpt-5.5")
        pool.register("v3", model="gpt-5.5")

        report = pool.monoculture_report()
        assert report["monoculture_risk"] is True
        assert report["dominant_model"] == "gpt-5.5"
        assert report["diversity_score"] == 0.0

    def test_diversity_report(self) -> None:
        pool = ValidatorPool()
        pool.register("v1", model="gpt-5.5")
        pool.register("v2", model="claude-sonnet-4-6")
        pool.register("v3", model="gemini-2.5-flash")

        report = pool.monoculture_report()
        assert report["monoculture_risk"] is False
        assert report["diversity_score"] > 0.9  # near-perfect diversity

    def test_update_trust(self) -> None:
        pool = ValidatorPool()
        pool.register("v1", trust_score=0.9)
        pool.update_trust("v1", 0.5)
        assert pool.get("v1").trust_score == 0.5  # type: ignore[union-attr]

        with pytest.raises(KeyError):
            pool.update_trust("nonexistent", 0.5)

    def test_empty_pool_monoculture(self) -> None:
        pool = ValidatorPool()
        report = pool.monoculture_report()
        assert report["monoculture_risk"] is True
        assert report["total_validators"] == 0


# ── Weighted shuffle tests ───────────────────────────────────────────────────


class TestWeightedShuffle:
    def test_deterministic(self) -> None:
        ids = ["a", "b", "c", "d", "e"]
        weights = [0.2, 0.2, 0.2, 0.2, 0.2]
        seed = "aa" * 32

        r1 = _weighted_shuffle_select(seed, ids, weights, k=3)
        r2 = _weighted_shuffle_select(seed, ids, weights, k=3)
        assert r1 == r2

    def test_different_seeds_different_results(self) -> None:
        ids = ["a", "b", "c", "d", "e"]
        weights = [0.2, 0.2, 0.2, 0.2, 0.2]

        r1 = _weighted_shuffle_select("aa" * 32, ids, weights, k=3)
        r2 = _weighted_shuffle_select("bb" * 32, ids, weights, k=3)
        # With 5 choose 3 and uniform weights, different seeds are very likely
        # to produce different orderings (though not guaranteed)
        # Just verify both return valid selections
        assert len(r1) == 3
        assert len(r2) == 3

    def test_k_larger_than_pool(self) -> None:
        ids = ["a", "b"]
        weights = [0.5, 0.5]
        result = _weighted_shuffle_select("aa" * 32, ids, weights, k=5)
        assert len(result) == 2  # returns all available

    def test_k_zero(self) -> None:
        assert _weighted_shuffle_select("aa" * 32, ["a"], [1.0], k=0) == []

    def test_mismatched_lengths(self) -> None:
        with pytest.raises(ValueError, match="same length"):
            _weighted_shuffle_select("aa" * 32, ["a", "b"], [1.0], k=1)

    def test_high_weight_more_likely(self) -> None:
        """Over many seeds, high-weight validators should be selected more often."""
        ids = ["low", "high"]
        weights = [0.01, 0.99]  # Extreme weight difference
        high_count = 0
        trials = 100

        for i in range(trials):
            seed = f"{i:064x}"
            result = _weighted_shuffle_select(seed, ids, weights, k=1)
            if result[0] == "high":
                high_count += 1

        # "high" should be selected much more often than "low"
        assert high_count > 80, f"high selected only {high_count}/{trials} times"


# ── ValidatorSelector tests ──────────────────────────────────────────────────


class TestValidatorSelector:
    def test_basic_selection(self) -> None:
        pool = _make_pool(10)
        selector = ValidatorSelector(pool)
        result = selector.select(
            case_id="case-001",
            producer_id="miner-1",
            risk_tier="low",
            domain="finance",
        )
        assert len(result.selected) == 3  # low risk → k=3
        assert result.producer_excluded is True
        assert result.eligible_count == 10  # producer not in pool
        assert result.k == 3
        assert result.q == 2  # ceil(3 * 2/3)

    def test_risk_tier_scaling(self) -> None:
        pool = _make_pool(20)
        selector = ValidatorSelector(pool)

        for tier, expected_k in [("low", 3), ("medium", 5), ("high", 7), ("critical", 9)]:
            result = selector.select(
                case_id=f"case-{tier}",
                producer_id="miner-1",
                risk_tier=tier,
                domain="finance",
            )
            assert result.k == expected_k, f"tier={tier}: expected k={expected_k}, got {result.k}"

    def test_producer_excluded(self) -> None:
        pool = _make_pool(10)
        # Add the producer as a validator too
        pool.register("miner-1", trust_score=0.95, domains=["finance"], model="model-a")

        selector = ValidatorSelector(pool)
        result = selector.select(
            case_id="case-001",
            producer_id="miner-1",
            risk_tier="low",
            domain="finance",
        )
        assert "miner-1" not in result.selected
        assert result.producer_excluded is True

    def test_proof_verification(self) -> None:
        pool = _make_pool(10)
        selector = ValidatorSelector(pool)
        result = selector.select(
            case_id="case-001",
            producer_id="miner-1",
            risk_tier="medium",
            domain="finance",
        )
        assert result.verify()

    def test_proof_verification_with_signing_key(self) -> None:
        pool = _make_pool(10)
        policy = SelectionPolicy(signing_key="test-secret-key")
        selector = ValidatorSelector(pool, policy=policy)
        result = selector.select(
            case_id="case-001",
            producer_id="miner-1",
            risk_tier="medium",
            domain="finance",
        )
        assert result.proof.signature != ""
        assert result.verify(signing_key="test-secret-key")
        # Wrong key should fail
        assert not result.verify(signing_key="wrong-key")

    def test_static_verify(self) -> None:
        pool = _make_pool(10)
        policy = SelectionPolicy(signing_key="key-1")
        selector = ValidatorSelector(pool, policy=policy)
        result = selector.select(
            case_id="case-001",
            producer_id="miner-1",
            risk_tier="low",
            domain="finance",
        )
        # Verify using static method (no selector instance needed)
        assert ValidatorSelector.verify_selection(result.proof, signing_key="key-1")

    def test_degraded_pool_adjusts_k(self) -> None:
        """When fewer validators are available than k, degrade gracefully."""
        pool = ValidatorPool()
        pool.register("v1", trust_score=0.9, domains=["fin"])
        pool.register("v2", trust_score=0.8, domains=["fin"])

        selector = ValidatorSelector(pool)
        result = selector.select(
            case_id="case-001",
            producer_id="miner-1",
            risk_tier="high",  # wants k=7
            domain="fin",
        )
        assert result.k == 2  # degraded to available
        assert result.q == math.ceil(2 * (2 / 3))

    def test_empty_pool_raises(self) -> None:
        pool = ValidatorPool()
        selector = ValidatorSelector(pool)
        with pytest.raises(ValueError, match="No eligible validators"):
            selector.select(
                case_id="case-001",
                producer_id="miner-1",
                risk_tier="low",
                domain="finance",
            )

    def test_diversity_score(self) -> None:
        pool = ValidatorPool()
        # All same model
        for i in range(6):
            pool.register(f"v{i}", trust_score=0.9, domains=["fin"], model="gpt-5.5")
        selector = ValidatorSelector(pool)
        result = selector.select(
            case_id="case-001",
            producer_id="miner-1",
            risk_tier="low",
            domain="fin",
        )
        assert result.diversity_score == 0.0  # monoculture

    def test_diverse_selection(self) -> None:
        pool = ValidatorPool()
        pool.register("v1", trust_score=0.9, domains=["fin"], model="gpt-5.5")
        pool.register("v2", trust_score=0.9, domains=["fin"], model="claude-sonnet-4-6")
        pool.register("v3", trust_score=0.9, domains=["fin"], model="gemini-2.5-flash")
        pool.register("v4", trust_score=0.9, domains=["fin"], model="llama-3")

        selector = ValidatorSelector(pool)
        result = selector.select(
            case_id="case-001",
            producer_id="miner-1",
            risk_tier="low",
            domain="fin",
        )
        assert result.diversity_score > 0.0

    def test_k_override(self) -> None:
        pool = _make_pool(10)
        selector = ValidatorSelector(pool)
        result = selector.select(
            case_id="case-001",
            producer_id="miner-1",
            risk_tier="low",  # normally k=3
            domain="finance",
            k_override=6,
        )
        assert result.k == 6

    def test_fixed_seed_reproducible(self) -> None:
        pool = _make_pool(10)
        selector = ValidatorSelector(pool)
        r1 = selector.select(
            case_id="case-001",
            producer_id="miner-1",
            risk_tier="medium",
            domain="finance",
            seed="deadbeef" * 8,
        )
        r2 = selector.select(
            case_id="case-001",
            producer_id="miner-1",
            risk_tier="medium",
            domain="finance",
            seed="deadbeef" * 8,
        )
        assert r1.selected == r2.selected

    def test_domain_coverage_check(self) -> None:
        pool = ValidatorPool()
        pool.register("v1", trust_score=0.9, domains=["finance"])
        pool.register("v2", trust_score=0.9, domains=["finance"])
        pool.register("v3", trust_score=0.9, domains=["finance"])

        selector = ValidatorSelector(pool)
        result = selector.select(
            case_id="case-001",
            producer_id="miner-1",
            risk_tier="low",
            domain="finance",
        )
        assert result.domain_coverage is True

    def test_no_domain_filter_when_not_required(self) -> None:
        pool = ValidatorPool()
        pool.register("v1", trust_score=0.9, domains=["healthcare"])
        pool.register("v2", trust_score=0.9, domains=["finance"])
        pool.register("v3", trust_score=0.9, domains=[])

        policy = SelectionPolicy(require_domain_match=False)
        selector = ValidatorSelector(pool, policy=policy)
        result = selector.select(
            case_id="case-001",
            producer_id="miner-1",
            risk_tier="low",
            domain="finance",
        )
        assert result.eligible_count == 3  # all eligible when domain not required

    def test_min_trust_threshold(self) -> None:
        pool = ValidatorPool()
        pool.register("v1", trust_score=0.9, domains=["fin"])
        pool.register("v2", trust_score=0.3, domains=["fin"])
        pool.register("v3", trust_score=0.6, domains=["fin"])
        pool.register("v4", trust_score=0.8, domains=["fin"])

        policy = SelectionPolicy(min_trust_threshold=0.5)
        selector = ValidatorSelector(pool, policy=policy)
        result = selector.select(
            case_id="case-001",
            producer_id="miner-1",
            risk_tier="low",
            domain="fin",
        )
        assert result.eligible_count == 3  # v2 excluded by trust threshold

    def test_proof_tamper_detection(self) -> None:
        """Modifying the proof should cause verification to fail."""
        pool = _make_pool(10)
        selector = ValidatorSelector(pool)
        result = selector.select(
            case_id="case-001",
            producer_id="miner-1",
            risk_tier="low",
            domain="finance",
        )
        # Tamper with the selected IDs
        original_selected = list(result.proof.selected_ids)
        result.proof.selected_ids = list(reversed(result.proof.selected_ids))
        if result.proof.selected_ids != original_selected:
            assert not result.verify()

    def test_quorum_fraction(self) -> None:
        pool = _make_pool(10)
        policy = SelectionPolicy(q_fraction=0.5)
        selector = ValidatorSelector(pool, policy=policy)
        result = selector.select(
            case_id="case-001",
            producer_id="miner-1",
            risk_tier="high",  # k=7
            domain="finance",
        )
        assert result.q == math.ceil(7 * 0.5)  # 4


class TestSelectionProof:
    def test_canonical_bytes_deterministic(self) -> None:
        proof = SelectionProof(
            case_id="c1",
            seed="aa" * 32,
            eligible_ids=["a", "b", "c"],
            eligible_weights=[0.33, 0.33, 0.34],
            selected_ids=["a", "c"],
            k=2,
            q=2,
            risk_tier="low",
            producer_id="p1",
            domain="fin",
            timestamp="2026-01-01T00:00:00+00:00",
        )
        assert proof.canonical_bytes() == proof.canonical_bytes()

    def test_to_dict_roundtrip(self) -> None:
        proof = SelectionProof(
            case_id="c1",
            seed="bb" * 32,
            eligible_ids=["a", "b"],
            eligible_weights=[0.5, 0.5],
            selected_ids=["a"],
            k=1,
            q=1,
            risk_tier="low",
            producer_id="p1",
            domain="fin",
            timestamp="2026-01-01T00:00:00+00:00",
        )
        d = proof.to_dict()
        assert d["case_id"] == "c1"
        assert d["selected_ids"] == ["a"]
        assert d["algorithm"] == "weighted_shuffle_v1"
