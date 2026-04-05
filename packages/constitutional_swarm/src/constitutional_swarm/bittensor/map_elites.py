"""MAP-Elites Miner Quality Optimization.

Maintains a quality-diversity grid over (governance_domain x deliberation_strategy).
Each cell tracks the best-performing miner approach for that combination.
Forces exploration of the full behavioral space — prevents convergence to a
single "good enough" strategy.

7 domains x 4 strategies = 28 cells.

Evolutionary pattern: MAP-Elites (Mouret & Clune, 2015).
Ceiling detection per cell and globally.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class GovernanceDomain(Enum):
    """The 7 constitutional governance dimensions."""

    SAFETY = "safety"
    SECURITY = "security"
    PRIVACY = "privacy"
    FAIRNESS = "fairness"
    RELIABILITY = "reliability"
    TRANSPARENCY = "transparency"
    EFFICIENCY = "efficiency"


class DeliberationStrategy(Enum):
    """Deliberation approach families."""

    PRECEDENT_BASED = "precedent_based"
    STAKEHOLDER_ANALYSIS = "stakeholder_analysis"
    CONSTITUTIONAL_REASONING = "constitutional_reasoning"
    HYBRID = "hybrid"


@dataclass(frozen=True, slots=True)
class CellCoordinate:
    """Position in the MAP-Elites grid."""

    domain: GovernanceDomain
    strategy: DeliberationStrategy


@dataclass(frozen=True, slots=True)
class MinerApproach:
    """A snapshot of a miner's behavioral phenotype at evaluation time."""

    miner_uid: str
    domain: GovernanceDomain
    strategy: DeliberationStrategy
    fitness: float
    acceptance_rate: float
    reasoning_quality: float
    speed_ms: float
    sample_count: int
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True, slots=True)
class FitnessWeights:
    """Tunable weights for the composite fitness function."""

    acceptance_weight: float = 0.5
    reasoning_weight: float = 0.3
    speed_weight: float = 0.2
    speed_baseline_ms: float = 1000.0
    min_samples: int = 5


class MinerQualityGrid:
    """MAP-Elites grid: best miner approach per (domain, strategy) cell.

    Properties:
    - Forces diversity: one miner can't dominate all cells
    - Identifies unexplored regions for targeted incentives
    - Ceiling detection signals convergence
    """

    TOTAL_CELLS = len(GovernanceDomain) * len(DeliberationStrategy)  # 28

    def __init__(
        self,
        *,
        fitness_weights: FitnessWeights | None = None,
        ceiling_window: int = 5,
    ) -> None:
        self._weights = fitness_weights or FitnessWeights()
        self._grid: dict[CellCoordinate, MinerApproach] = {}
        self._history: dict[CellCoordinate, list[MinerApproach]] = {}
        self._ceiling_window = ceiling_window
        self._challenge_log: list[tuple[CellCoordinate, bool, float]] = []

    def compute_fitness(
        self,
        acceptance_rate: float,
        reasoning_quality: float,
        speed_ms: float,
    ) -> float:
        """Weighted composite fitness in [0, 1].

        Speed is inverted and normalized against baseline.
        """
        w = self._weights
        speed_score = max(0.0, 1.0 - speed_ms / w.speed_baseline_ms)
        return (
            w.acceptance_weight * acceptance_rate
            + w.reasoning_weight * reasoning_quality
            + w.speed_weight * speed_score
        )

    def challenge(self, approach: MinerApproach) -> bool:
        """Try to place an approach in its grid cell.

        Returns True if it replaces the incumbent or fills an empty cell.
        Requires min_samples to be met.
        """
        if approach.sample_count < self._weights.min_samples:
            return False

        coord = CellCoordinate(domain=approach.domain, strategy=approach.strategy)
        self._history.setdefault(coord, []).append(approach)

        incumbent = self._grid.get(coord)
        replaced = False

        if incumbent is None or approach.fitness > incumbent.fitness:
            self._grid[coord] = approach
            replaced = True

        self._challenge_log.append((coord, replaced, time.time()))
        return replaced

    @property
    def coverage(self) -> float:
        """Fraction of 28 cells occupied."""
        return len(self._grid) / self.TOTAL_CELLS

    @property
    def occupied_count(self) -> int:
        return len(self._grid)

    def best_for(
        self,
        domain: GovernanceDomain,
        strategy: DeliberationStrategy,
    ) -> MinerApproach | None:
        """Return the incumbent for a cell, or None if empty."""
        return self._grid.get(CellCoordinate(domain=domain, strategy=strategy))

    def diversity_score(self) -> float:
        """Unique miner_uids across occupied cells / total occupied.

        Low diversity = one miner dominating many cells.
        """
        if not self._grid:
            return 0.0
        uids = {a.miner_uid for a in self._grid.values()}
        return len(uids) / len(self._grid)

    def empty_cells(self) -> list[CellCoordinate]:
        """Cells with no incumbent — targets for exploration incentives."""
        result = []
        for domain in GovernanceDomain:
            for strategy in DeliberationStrategy:
                coord = CellCoordinate(domain=domain, strategy=strategy)
                if coord not in self._grid:
                    result.append(coord)
        return result

    def domain_coverage(self, domain: GovernanceDomain) -> int:
        """How many strategy cells are filled for a domain (0-4)."""
        return sum(
            1
            for strategy in DeliberationStrategy
            if CellCoordinate(domain=domain, strategy=strategy) in self._grid
        )

    def ceiling_detected(self) -> bool:
        """True when last N challenges produced no improvements globally."""
        if len(self._challenge_log) < self._ceiling_window:
            return False
        recent = self._challenge_log[-self._ceiling_window:]
        return not any(replaced for _, replaced, _ in recent)

    def ceiling_for_cell(self, coord: CellCoordinate) -> bool:
        """True when last N challenges to this specific cell had no improvement."""
        cell_challenges = [
            (replaced, ts)
            for c, replaced, ts in self._challenge_log
            if c == coord
        ]
        if len(cell_challenges) < self._ceiling_window:
            return False
        recent = cell_challenges[-self._ceiling_window:]
        return not any(replaced for replaced, _ in recent)

    def top_miners(self, n: int = 5) -> list[MinerApproach]:
        """Top N miners by fitness across all cells."""
        return sorted(self._grid.values(), key=lambda a: a.fitness, reverse=True)[:n]

    def summary(self) -> dict[str, Any]:
        """Grid statistics for monitoring."""
        return {
            "coverage": round(self.coverage, 3),
            "occupied_cells": self.occupied_count,
            "total_cells": self.TOTAL_CELLS,
            "diversity_score": round(self.diversity_score(), 3),
            "ceiling_detected": self.ceiling_detected(),
            "total_challenges": len(self._challenge_log),
            "unique_miners": len({a.miner_uid for a in self._grid.values()}),
            "domain_coverage": {
                d.value: self.domain_coverage(d) for d in GovernanceDomain
            },
        }

    def exploration_bonus(self, miner_uid: str, multiplier: float = 1.1) -> float:
        """Compute exploration bonus for a miner.

        Miners that occupy cells with low challenge counts or that
        have contributed to empty-cell-adjacent domains get a bonus.
        """
        cells_held = sum(
            1 for a in self._grid.values() if a.miner_uid == miner_uid
        )
        if cells_held == 0:
            return multiplier  # New miner — maximum exploration incentive
        # Bonus decreases as miner occupies more cells (diminishing returns)
        return 1.0 + (multiplier - 1.0) / cells_held
