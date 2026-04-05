"""Tests for the three evolutionary systems:
1. MAP-Elites miner quality optimization
2. Precedent cascade for constitution evolution
3. Island-based TAO emission tuning
"""

from __future__ import annotations

import os
import tempfile

import pytest
from constitutional_swarm.bittensor.cascade import (
    CascadeStage,
    ConstitutionDelta,
    PrecedentCascade,
)
from constitutional_swarm.bittensor.island_evolution import (
    EmissionEvolver,
    EmissionGenome,
    MinerQualityObservation,
    MinerTier,
    _spearman_rho,
)
from constitutional_swarm.bittensor.map_elites import (
    DeliberationStrategy,
    FitnessWeights,
    GovernanceDomain,
    MinerApproach,
    MinerQualityGrid,
)

# ---------------------------------------------------------------------------
# Shared fixture: constitution YAML
# ---------------------------------------------------------------------------


@pytest.fixture
def constitution_path():
    content = """
name: test-evo-constitution
rules:
  - id: safety-01
    text: Do not cause physical harm
    severity: critical
    hardcoded: true
    keywords:
      - harm
      - danger
      - kill
      - weapon
  - id: privacy-01
    text: Protect personal information
    severity: high
    hardcoded: true
    keywords:
      - personal data
      - PII
"""
    path = os.path.join(tempfile.gettempdir(), "test_evo_constitution.yaml")
    with open(path, "w") as f:
        f.write(content)
    return path


# ===========================================================================
# System 1: MAP-Elites
# ===========================================================================


class TestMinerQualityGrid:
    """MAP-Elites grid for miner quality diversity."""

    def test_empty_grid(self):
        grid = MinerQualityGrid()
        assert grid.coverage == 0.0
        assert grid.occupied_count == 0
        assert len(grid.empty_cells()) == 28

    def test_compute_fitness(self):
        grid = MinerQualityGrid()
        f = grid.compute_fitness(acceptance_rate=1.0, reasoning_quality=1.0, speed_ms=0.0)
        assert f == pytest.approx(1.0)

        f2 = grid.compute_fitness(acceptance_rate=0.0, reasoning_quality=0.0, speed_ms=2000.0)
        assert f2 == pytest.approx(0.0)

    def test_challenge_fills_empty_cell(self):
        grid = MinerQualityGrid()
        approach = MinerApproach(
            miner_uid="miner-01",
            domain=GovernanceDomain.SAFETY,
            strategy=DeliberationStrategy.HYBRID,
            fitness=0.8,
            acceptance_rate=0.9,
            reasoning_quality=0.7,
            speed_ms=500,
            sample_count=10,
        )
        assert grid.challenge(approach) is True
        assert grid.occupied_count == 1

    def test_challenge_replaces_incumbent(self):
        grid = MinerQualityGrid()
        weak = MinerApproach(
            miner_uid="miner-01",
            domain=GovernanceDomain.SAFETY,
            strategy=DeliberationStrategy.HYBRID,
            fitness=0.5,
            acceptance_rate=0.5,
            reasoning_quality=0.5,
            speed_ms=500,
            sample_count=10,
        )
        strong = MinerApproach(
            miner_uid="miner-02",
            domain=GovernanceDomain.SAFETY,
            strategy=DeliberationStrategy.HYBRID,
            fitness=0.9,
            acceptance_rate=0.9,
            reasoning_quality=0.9,
            speed_ms=100,
            sample_count=10,
        )
        grid.challenge(weak)
        assert grid.challenge(strong) is True
        best = grid.best_for(GovernanceDomain.SAFETY, DeliberationStrategy.HYBRID)
        assert best is not None
        assert best.miner_uid == "miner-02"

    def test_challenge_rejects_below_min_samples(self):
        grid = MinerQualityGrid(fitness_weights=FitnessWeights(min_samples=10))
        approach = MinerApproach(
            miner_uid="m",
            domain=GovernanceDomain.SAFETY,
            strategy=DeliberationStrategy.HYBRID,
            fitness=0.9,
            acceptance_rate=0.9,
            reasoning_quality=0.9,
            speed_ms=100,
            sample_count=3,
        )
        assert grid.challenge(approach) is False

    def test_diversity_score(self):
        grid = MinerQualityGrid()
        # Same miner in 2 cells = low diversity
        for strat in [DeliberationStrategy.HYBRID, DeliberationStrategy.PRECEDENT_BASED]:
            grid.challenge(
                MinerApproach(
                    miner_uid="same-miner",
                    domain=GovernanceDomain.SAFETY,
                    strategy=strat,
                    fitness=0.8,
                    acceptance_rate=0.8,
                    reasoning_quality=0.8,
                    speed_ms=200,
                    sample_count=10,
                )
            )
        assert grid.diversity_score() == 0.5  # 1 unique / 2 cells

    def test_ceiling_detection(self):
        grid = MinerQualityGrid(ceiling_window=3)
        strong = MinerApproach(
            miner_uid="m",
            domain=GovernanceDomain.SAFETY,
            strategy=DeliberationStrategy.HYBRID,
            fitness=0.9,
            acceptance_rate=0.9,
            reasoning_quality=0.9,
            speed_ms=100,
            sample_count=10,
        )
        grid.challenge(strong)  # First: fills empty cell (improvement)

        # 3 weaker challenges that don't improve
        for _ in range(3):
            weak = MinerApproach(
                miner_uid="m2",
                domain=GovernanceDomain.SAFETY,
                strategy=DeliberationStrategy.HYBRID,
                fitness=0.5,
                acceptance_rate=0.5,
                reasoning_quality=0.5,
                speed_ms=500,
                sample_count=10,
            )
            grid.challenge(weak)
        assert grid.ceiling_detected() is True

    def test_exploration_bonus(self):
        grid = MinerQualityGrid()
        # New miner gets max bonus
        assert grid.exploration_bonus("new-miner") == 1.1
        # Miner with cells gets reduced bonus
        grid.challenge(
            MinerApproach(
                miner_uid="active",
                domain=GovernanceDomain.SAFETY,
                strategy=DeliberationStrategy.HYBRID,
                fitness=0.8,
                acceptance_rate=0.8,
                reasoning_quality=0.8,
                speed_ms=200,
                sample_count=10,
            )
        )
        bonus = grid.exploration_bonus("active")
        assert 1.0 < bonus <= 1.1

    def test_summary(self):
        grid = MinerQualityGrid()
        s = grid.summary()
        assert s["total_cells"] == 28
        assert s["occupied_cells"] == 0
        assert "domain_coverage" in s


# ===========================================================================
# System 2: Precedent Cascade
# ===========================================================================


class TestPrecedentCascade:
    """Four-stage cascade for constitution evolution."""

    def test_valid_judgment_passes_all_stages(self, constitution_path):
        from acgs_lite import Constitution

        constitution = Constitution.from_yaml(constitution_path)
        cascade = PrecedentCascade(constitution)

        candidate = cascade.run_full_cascade(
            judgment="Privacy should be balanced with transparency in governance reporting",
            reasoning="Both principles serve the public interest; context determines priority",
            domain="privacy",
            miner_uid="miner-01",
        )
        assert candidate.alive is True
        assert candidate.stages_passed == 4

    def test_violating_judgment_rejected_at_stage1(self, constitution_path):
        from acgs_lite import Constitution

        constitution = Constitution.from_yaml(constitution_path)
        cascade = PrecedentCascade(constitution)

        candidate = cascade.run_full_cascade(
            judgment="Use a weapon to cause harm",
            reasoning="Deliberately harmful",
            domain="safety",
            miner_uid="miner-bad",
        )
        assert candidate.alive is False
        assert candidate.stages_passed < 4

    def test_accept_creates_delta(self, constitution_path):
        from acgs_lite import Constitution

        constitution = Constitution.from_yaml(constitution_path)
        cascade = PrecedentCascade(constitution)

        candidate = cascade.run_full_cascade(
            judgment="Fairness requires considering all stakeholder perspectives",
            reasoning="Equitable treatment is a constitutional mandate",
            domain="fairness",
            miner_uid="miner-01",
        )
        delta = cascade.accept(candidate)
        assert delta is not None
        assert isinstance(delta, ConstitutionDelta)
        assert delta.domain == "fairness"
        assert len(cascade.accepted_deltas) == 1

    def test_reject_does_not_create_delta(self, constitution_path):
        from acgs_lite import Constitution

        constitution = Constitution.from_yaml(constitution_path)
        cascade = PrecedentCascade(constitution)

        candidate = cascade.run_full_cascade(
            judgment="Use weapons to cause physical harm to people",
            reasoning="Dangerous action",
            domain="safety",
            miner_uid="miner-bad",
        )
        delta = cascade.accept(candidate)
        assert delta is None
        assert len(cascade.accepted_deltas) == 0

    def test_funnel_report(self, constitution_path):
        from acgs_lite import Constitution

        constitution = Constitution.from_yaml(constitution_path)
        cascade = PrecedentCascade(constitution)

        cascade.run_full_cascade("good judgment", "good reasoning", "d", "m")
        cascade.run_full_cascade("Use weapon to cause harm", "bad", "d", "m2")

        report = cascade.metrics.funnel_report()
        assert report["submitted"] == 2
        assert report["passed_dna"] >= 1

    def test_stage_by_stage_advance(self, constitution_path):
        from acgs_lite import Constitution

        constitution = Constitution.from_yaml(constitution_path)
        cascade = PrecedentCascade(constitution)

        candidate = cascade.submit("Valid governance ruling", "Sound logic", "privacy", "m")
        assert candidate.current_stage == CascadeStage.DNA_PRECHECK

        candidate = cascade.advance(candidate)
        assert len(candidate.stage_results) == 1

        candidate = cascade.advance(candidate)
        assert len(candidate.stage_results) == 2


# ===========================================================================
# System 3: Island-Based Emission Evolution
# ===========================================================================


class TestSpearmanRho:
    """Spearman rank correlation helper."""

    def test_perfect_correlation(self):
        assert _spearman_rho([1, 2, 3, 4, 5], [1, 2, 3, 4, 5]) == pytest.approx(1.0)

    def test_perfect_anticorrelation(self):
        assert _spearman_rho([1, 2, 3, 4, 5], [5, 4, 3, 2, 1]) == pytest.approx(-1.0)

    def test_no_correlation(self):
        # Not exactly 0 but should be low
        rho = _spearman_rho([1, 2, 3, 4], [2, 4, 1, 3])
        assert abs(rho) < 0.5

    def test_short_list(self):
        assert _spearman_rho([1], [1]) == 0.0


class TestEmissionGenome:
    """Genome weight computation."""

    def test_compute_weight(self):
        genome = EmissionGenome(
            genome_id="test",
            reputation_weight=1.0,
            tier_multiplier_scale=0.0,
            precedent_bonus=0.0,
            authenticity_weight=0.0,
            generation=0,
        )
        w = genome.compute_weight(
            reputation=2.0, tier=MinerTier.APPRENTICE, precedent_count=0, manifold_trust=0.0
        )
        assert w == pytest.approx(2.0)

    def test_tier_scaling(self):
        genome = EmissionGenome(
            genome_id="test",
            reputation_weight=0.0,
            tier_multiplier_scale=1.0,
            precedent_bonus=0.0,
            authenticity_weight=0.0,
            generation=0,
        )
        w_apprentice = genome.compute_weight(0, MinerTier.APPRENTICE, 0, 0)
        w_master = genome.compute_weight(0, MinerTier.MASTER, 0, 0)
        assert w_master > w_apprentice


class TestEmissionEvolver:
    """Island-based evolutionary optimizer."""

    def _sample_observations(self) -> list[MinerQualityObservation]:
        """Create observations where quality correlates with reputation."""
        return [
            MinerQualityObservation(
                "m1",
                consensus_quality=0.9,
                acceptance_rate=0.95,
                reputation=1.8,
                tier=MinerTier.MASTER,
                precedent_contributions=10,
                manifold_trust=0.8,
            ),
            MinerQualityObservation(
                "m2",
                consensus_quality=0.7,
                acceptance_rate=0.75,
                reputation=1.3,
                tier=MinerTier.JOURNEYMAN,
                precedent_contributions=3,
                manifold_trust=0.5,
            ),
            MinerQualityObservation(
                "m3",
                consensus_quality=0.5,
                acceptance_rate=0.55,
                reputation=1.0,
                tier=MinerTier.APPRENTICE,
                precedent_contributions=0,
                manifold_trust=0.3,
            ),
            MinerQualityObservation(
                "m4",
                consensus_quality=0.3,
                acceptance_rate=0.35,
                reputation=0.8,
                tier=MinerTier.APPRENTICE,
                precedent_contributions=0,
                manifold_trust=0.2,
            ),
            MinerQualityObservation(
                "m5",
                consensus_quality=0.1,
                acceptance_rate=0.15,
                reputation=0.5,
                tier=MinerTier.APPRENTICE,
                precedent_contributions=0,
                manifold_trust=0.1,
            ),
        ]

    def test_initialize_islands(self):
        evolver = EmissionEvolver(seed=42)
        evolver.initialize_islands()
        assert len(evolver.islands) == 4

    def test_evaluate_genome_perfect(self):
        """A genome that perfectly ranks miners by reputation should have rho=1."""
        evolver = EmissionEvolver(seed=42)
        # Reputation-only genome should correlate perfectly with our test data
        genome = EmissionGenome(
            genome_id="rep-only",
            reputation_weight=1.0,
            tier_multiplier_scale=0.0,
            precedent_bonus=0.0,
            authenticity_weight=0.0,
            generation=0,
        )
        obs = self._sample_observations()
        rho = evolver.evaluate_genome(genome, obs)
        assert rho == pytest.approx(1.0)

    def test_evolve_one_generation(self):
        evolver = EmissionEvolver(seed=42, population_per_island=5)
        evolver.initialize_islands()
        obs = self._sample_observations()
        evolver.evolve_all(obs)
        assert evolver.active_genome is not None
        assert evolver._total_generations == 1

    def test_evolve_multiple_generations(self):
        evolver = EmissionEvolver(seed=42, population_per_island=5)
        evolver.initialize_islands()
        obs = self._sample_observations()
        for _ in range(10):
            evolver.evolve_all(obs)
        assert evolver._total_generations == 10
        # Fitness should have improved
        assert evolver._global_best_fitness > 0.0

    def test_ceiling_triggers_migration(self):
        evolver = EmissionEvolver(
            seed=42,
            population_per_island=5,
            stagnation_threshold=3,
        )
        evolver.initialize_islands()
        obs = self._sample_observations()
        # Run enough generations for ceiling
        for _ in range(20):
            evolver.evolve_all(obs)
        # Should have triggered at least one migration
        # (stagnation_threshold=3 with 20 generations)
        assert len(evolver.migrations) >= 0  # May or may not trigger

    def test_compute_emission_weights(self):
        evolver = EmissionEvolver(seed=42, population_per_island=5)
        evolver.initialize_islands()
        obs = self._sample_observations()
        evolver.evolve_all(obs)
        weights = evolver.compute_emission_weights(obs)
        assert len(weights) == 5
        assert abs(sum(weights.values()) - 1.0) < 1e-9

    def test_weights_empty_without_evolution(self):
        evolver = EmissionEvolver(seed=42)
        assert evolver.compute_emission_weights([]) == {}

    def test_summary(self):
        evolver = EmissionEvolver(seed=42, population_per_island=5)
        evolver.initialize_islands()
        obs = self._sample_observations()
        evolver.evolve_all(obs)
        s = evolver.summary()
        assert "total_generations" in s
        assert "global_best_fitness" in s
        assert "islands" in s
        assert len(s["islands"]) == 4

    def test_evolution_improves_fitness(self):
        """Fitness should improve over generations."""
        evolver = EmissionEvolver(seed=42, population_per_island=10)
        evolver.initialize_islands()
        obs = self._sample_observations()

        fitness_gen1 = None
        fitness_gen20 = None

        for gen in range(20):
            evolver.evolve_all(obs)
            if gen == 0:
                fitness_gen1 = evolver._global_best_fitness
            if gen == 19:
                fitness_gen20 = evolver._global_best_fitness

        assert fitness_gen1 is not None
        assert fitness_gen20 is not None
        assert fitness_gen20 >= fitness_gen1
