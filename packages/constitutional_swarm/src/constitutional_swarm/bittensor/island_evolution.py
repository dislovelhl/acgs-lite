"""Island-Based TAO Emission Tuning.

Evolves the emission weight formula using island-based evolution.
Four islands with different parameter families compete. Event-driven
migration breaks local optima when ceiling is detected.

Fitness: Spearman rank correlation between genome-predicted emission
weights and actual miner quality (measured by validator consensus).

Evolutionary patterns: Island model, ceiling detection, tournament
selection, Gaussian mutation, single-point crossover.
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field
from typing import Any

from constitutional_swarm.bittensor.protocol import TIER_TAO_MULTIPLIER, MinerTier


@dataclass(frozen=True, slots=True)
class EmissionGenome:
    """A candidate emission weight formula parameterization."""

    genome_id: str
    reputation_weight: float
    tier_multiplier_scale: float
    precedent_bonus: float
    authenticity_weight: float
    generation: int
    parent_id: str | None = None

    def compute_weight(
        self,
        reputation: float,
        tier: MinerTier,
        precedent_count: int,
        manifold_trust: float,
    ) -> float:
        """Compute raw emission weight for a single miner."""
        base_tier = TIER_TAO_MULTIPLIER[tier]
        return (
            self.reputation_weight * reputation
            + self.tier_multiplier_scale * base_tier
            + self.precedent_bonus * min(precedent_count, 50) / 50.0
            + self.authenticity_weight * manifold_trust
        )


@dataclass(frozen=True, slots=True)
class MinerQualityObservation:
    """Ground truth quality ranking from validator consensus."""

    miner_uid: str
    consensus_quality: float
    acceptance_rate: float
    reputation: float
    tier: MinerTier
    precedent_contributions: int
    manifold_trust: float


@dataclass(frozen=True, slots=True)
class IslandIdentity:
    """Island metadata."""

    island_id: str
    family: str


@dataclass
class Island:
    """A subpopulation of emission genomes."""

    identity: IslandIdentity
    population: list[EmissionGenome]
    best_genome: EmissionGenome | None = None
    best_fitness: float = -1.0
    generation: int = 0
    fitness_history: list[float] = field(default_factory=list)
    stagnation_count: int = 0


@dataclass(frozen=True, slots=True)
class MigrationEvent:
    """Records a genome migrating between islands."""

    genome: EmissionGenome
    from_island: str
    to_island: str
    trigger: str
    timestamp: float


def _spearman_rho(x: list[float], y: list[float]) -> float:
    """Compute Spearman rank correlation coefficient."""
    n = len(x)
    if n < 2:
        return 0.0

    def _rank(values: list[float]) -> list[float]:
        indexed = sorted(enumerate(values), key=lambda p: p[1])
        ranks = [0.0] * n
        for rank, (idx, _) in enumerate(indexed):
            ranks[idx] = float(rank)
        return ranks

    rx = _rank(x)
    ry = _rank(y)
    d_sq = sum((rx[i] - ry[i]) ** 2 for i in range(n))
    return 1.0 - (6.0 * d_sq) / (n * (n * n - 1))


class EmissionEvolver:
    """Island-based evolutionary optimizer for TAO emission parameters.

    Usage:
        evolver = EmissionEvolver(seed=42)
        evolver.initialize_islands()

        # Each epoch:
        observations = gather_observations()
        evolver.evolve_all(observations)
        weights = evolver.compute_emission_weights(observations)
    """

    def __init__(
        self,
        *,
        population_per_island: int = 10,
        mutation_rate: float = 0.3,
        mutation_sigma: float = 0.05,
        crossover_rate: float = 0.3,
        stagnation_threshold: int = 10,
        seed: int | None = None,
    ) -> None:
        self._pop_size = population_per_island
        self._mutation_rate = mutation_rate
        self._mutation_sigma = mutation_sigma
        self._crossover_rate = crossover_rate
        self._stagnation_threshold = stagnation_threshold
        self._rng = random.Random(seed)  # noqa: S311 - deterministic simulation, not crypto
        self._islands: dict[str, Island] = {}
        self._migrations: list[MigrationEvent] = []
        self._global_best: EmissionGenome | None = None
        self._global_best_fitness: float = -1.0
        self._total_generations: int = 0

    @property
    def active_genome(self) -> EmissionGenome | None:
        """The genome currently used for live emission weight computation."""
        return self._global_best

    @property
    def islands(self) -> dict[str, Island]:
        return dict(self._islands)

    @property
    def migrations(self) -> list[MigrationEvent]:
        return list(self._migrations)

    def initialize_islands(self) -> None:
        """Create 4 islands with family-biased initial populations."""
        families = {
            "reputation_heavy": {
                "rep": (0.6, 0.9),
                "tier": (0.1, 0.3),
                "prec": (0.0, 0.2),
                "auth": (0.0, 0.2),
            },
            "tier_heavy": {
                "rep": (0.1, 0.3),
                "tier": (1.5, 3.0),
                "prec": (0.1, 0.3),
                "auth": (0.1, 0.3),
            },
            "precedent_heavy": {
                "rep": (0.1, 0.3),
                "tier": (0.5, 1.0),
                "prec": (0.3, 0.8),
                "auth": (0.1, 0.3),
            },
            "balanced": {
                "rep": (0.2, 0.5),
                "tier": (0.5, 1.5),
                "prec": (0.1, 0.4),
                "auth": (0.2, 0.5),
            },
        }

        for family_name, ranges in families.items():
            identity = IslandIdentity(
                island_id=f"island-{family_name}",
                family=family_name,
            )
            population = []
            for _ in range(self._pop_size):
                genome = EmissionGenome(
                    genome_id=uuid.uuid4().hex[:8],
                    reputation_weight=self._rng.uniform(*ranges["rep"]),
                    tier_multiplier_scale=self._rng.uniform(*ranges["tier"]),
                    precedent_bonus=self._rng.uniform(*ranges["prec"]),
                    authenticity_weight=self._rng.uniform(*ranges["auth"]),
                    generation=0,
                )
                population.append(genome)
            self._islands[identity.island_id] = Island(
                identity=identity,
                population=population,
            )

    def evaluate_genome(
        self,
        genome: EmissionGenome,
        observations: list[MinerQualityObservation],
    ) -> float:
        """Spearman rank correlation between genome's weights and ground truth."""
        if len(observations) < 2:
            return 0.0

        predicted = [
            genome.compute_weight(o.reputation, o.tier, o.precedent_contributions, o.manifold_trust)
            for o in observations
        ]
        actual = [o.consensus_quality for o in observations]
        return _spearman_rho(predicted, actual)

    def evolve_island(
        self,
        island: Island,
        observations: list[MinerQualityObservation],
    ) -> Island:
        """One generation: evaluate, select, crossover, mutate, replace."""
        # Evaluate all genomes
        scored = [(g, self.evaluate_genome(g, observations)) for g in island.population]
        scored.sort(key=lambda p: p[1], reverse=True)

        best_genome, best_fitness = scored[0]

        # Check improvement
        improved = best_fitness > island.best_fitness + 1e-6
        new_stagnation = 0 if improved else island.stagnation_count + 1

        # Tournament selection + offspring
        new_pop: list[EmissionGenome] = []

        # Elitism: keep top 2
        for g, _ in scored[:2]:
            new_pop.append(g)

        # Fill remaining via tournament + mutation
        while len(new_pop) < self._pop_size:
            parent = self._tournament_select(scored)

            # Crossover
            if self._rng.random() < self._crossover_rate and len(scored) > 1:
                other = self._tournament_select(scored)
                child = self._crossover(parent, other, island.generation + 1)
            else:
                child = parent

            # Mutation
            if self._rng.random() < self._mutation_rate:
                child = self._mutate(child, island.generation + 1)

            new_pop.append(child)

        return Island(
            identity=island.identity,
            population=new_pop,
            best_genome=best_genome,
            best_fitness=best_fitness,
            generation=island.generation + 1,
            fitness_history=[*island.fitness_history, best_fitness],
            stagnation_count=new_stagnation,
        )

    def check_ceiling(self, island: Island) -> bool:
        """True if island has stagnated beyond threshold."""
        return island.stagnation_count >= self._stagnation_threshold

    def migrate(self, from_island: Island, to_island: Island) -> tuple[Island, Island]:
        """Inject from_island's best genome into to_island, replacing worst."""
        if from_island.best_genome is None:
            return from_island, to_island

        # Find worst in target
        to_pop = list(to_island.population)
        if not to_pop:
            return from_island, to_island

        # Replace worst with migrant
        migrant = EmissionGenome(
            genome_id=uuid.uuid4().hex[:8],
            reputation_weight=from_island.best_genome.reputation_weight,
            tier_multiplier_scale=from_island.best_genome.tier_multiplier_scale,
            precedent_bonus=from_island.best_genome.precedent_bonus,
            authenticity_weight=from_island.best_genome.authenticity_weight,
            generation=to_island.generation,
            parent_id=from_island.best_genome.genome_id,
        )

        # Replace last (worst after sorting is maintained)
        to_pop[-1] = migrant

        self._migrations.append(
            MigrationEvent(
                genome=migrant,
                from_island=from_island.identity.island_id,
                to_island=to_island.identity.island_id,
                trigger="ceiling_detected",
                timestamp=0.0,
            )
        )

        new_to = Island(
            identity=to_island.identity,
            population=to_pop,
            best_genome=to_island.best_genome,
            best_fitness=to_island.best_fitness,
            generation=to_island.generation,
            fitness_history=list(to_island.fitness_history),
            stagnation_count=0,  # Reset after migration
        )
        return from_island, new_to

    def evolve_all(self, observations: list[MinerQualityObservation]) -> None:
        """One generation across all islands with ceiling-triggered migration."""
        if not self._islands:
            self.initialize_islands()

        # Evolve each island
        for island_id in list(self._islands):
            island = self._islands[island_id]
            self._islands[island_id] = self.evolve_island(island, observations)

        # Check ceilings and migrate
        stagnant = [iid for iid, island in self._islands.items() if self.check_ceiling(island)]

        if stagnant:
            # Find best non-stagnant island (or global best)
            best_island_id = max(
                self._islands,
                key=lambda iid: self._islands[iid].best_fitness,
            )
            for stag_id in stagnant:
                if stag_id != best_island_id:
                    source = self._islands[best_island_id]
                    target = self._islands[stag_id]
                    _, new_target = self.migrate(source, target)
                    self._islands[stag_id] = new_target

        # Update global best
        for island in self._islands.values():
            if island.best_genome and island.best_fitness > self._global_best_fitness:
                self._global_best = island.best_genome
                self._global_best_fitness = island.best_fitness

        self._total_generations += 1

    def compute_emission_weights(
        self,
        observations: list[MinerQualityObservation],
    ) -> dict[str, float]:
        """Use active genome to compute normalized emission weights."""
        genome = self._global_best
        if genome is None or not observations:
            return {}

        raw = {
            o.miner_uid: genome.compute_weight(
                o.reputation, o.tier, o.precedent_contributions, o.manifold_trust
            )
            for o in observations
        }
        total = sum(raw.values())
        if total <= 0:
            return {uid: 1.0 / len(raw) for uid in raw}
        return {uid: w / total for uid, w in raw.items()}

    def summary(self) -> dict[str, Any]:
        """Operational summary."""
        return {
            "total_generations": self._total_generations,
            "total_migrations": len(self._migrations),
            "global_best_fitness": round(self._global_best_fitness, 4),
            "global_best_genome": (
                {
                    "reputation_weight": round(self._global_best.reputation_weight, 4),
                    "tier_multiplier_scale": round(self._global_best.tier_multiplier_scale, 4),
                    "precedent_bonus": round(self._global_best.precedent_bonus, 4),
                    "authenticity_weight": round(self._global_best.authenticity_weight, 4),
                }
                if self._global_best
                else None
            ),
            "islands": {
                iid: {
                    "family": island.identity.family,
                    "generation": island.generation,
                    "best_fitness": round(island.best_fitness, 4),
                    "stagnation": island.stagnation_count,
                    "ceiling": self.check_ceiling(island),
                }
                for iid, island in self._islands.items()
            },
        }

    # -- Internal Evolution Operators ----------------------------------------

    def _tournament_select(
        self,
        scored: list[tuple[EmissionGenome, float]],
        k: int = 3,
    ) -> EmissionGenome:
        """Tournament selection: pick best of k random candidates."""
        candidates = self._rng.sample(scored, min(k, len(scored)))
        return max(candidates, key=lambda p: p[1])[0]

    def _mutate(self, genome: EmissionGenome, generation: int) -> EmissionGenome:
        """Gaussian mutation on all parameters."""
        s = self._mutation_sigma
        return EmissionGenome(
            genome_id=uuid.uuid4().hex[:8],
            reputation_weight=max(0.0, genome.reputation_weight + self._rng.gauss(0, s)),
            tier_multiplier_scale=max(
                0.0, genome.tier_multiplier_scale + self._rng.gauss(0, s * 2)
            ),
            precedent_bonus=max(0.0, genome.precedent_bonus + self._rng.gauss(0, s)),
            authenticity_weight=max(0.0, genome.authenticity_weight + self._rng.gauss(0, s)),
            generation=generation,
            parent_id=genome.genome_id,
        )

    def _crossover(
        self,
        a: EmissionGenome,
        b: EmissionGenome,
        generation: int,
    ) -> EmissionGenome:
        """Single-point crossover between two genomes."""
        point = self._rng.randint(0, 3)
        params_a = [
            a.reputation_weight,
            a.tier_multiplier_scale,
            a.precedent_bonus,
            a.authenticity_weight,
        ]
        params_b = [
            b.reputation_weight,
            b.tier_multiplier_scale,
            b.precedent_bonus,
            b.authenticity_weight,
        ]
        child_params = params_a[:point] + params_b[point:]
        return EmissionGenome(
            genome_id=uuid.uuid4().hex[:8],
            reputation_weight=child_params[0],
            tier_multiplier_scale=child_params[1],
            precedent_bonus=child_params[2],
            authenticity_weight=child_params[3],
            generation=generation,
            parent_id=a.genome_id,
        )
