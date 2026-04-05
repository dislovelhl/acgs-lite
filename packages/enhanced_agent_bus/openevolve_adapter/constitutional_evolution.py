"""Constitutional rule evolution engine.

Extends the existing openevolve_adapter with LLM-guided mutation of
EVOLVABLE rule parameters (keywords, patterns, severity) while FROZEN
invariants remain immutable. Uses the existing fitness, cascade, and
rollout infrastructure.

MACI roles:
- Evolution engine: PROPOSER (generates candidates)
- Invariant guard: VALIDATOR (checks frozen fields)
- Human approval: EXECUTOR (approves/rejects via Amendment lifecycle)
"""

from __future__ import annotations

import copy
import logging
import random
from dataclasses import dataclass, field
from typing import Any

from .mutation_operators import (
    KeywordMutator,
    PatternMutator,
    SeverityMutator,
    apply_mutation,
    verify_frozen_fields,
)

logger = logging.getLogger(__name__)


@dataclass
class FitnessScore:
    """Multi-objective fitness score for constitutional evolution."""

    f1: float = 0.0  # Governance accuracy (from eval harness)
    leniency: float = 0.0  # 1 - false_positive_rate
    stability: float = 0.0  # 1 - normalized_edit_distance from baseline

    @property
    def weighted_total(self, w_f1: float = 0.5, w_len: float = 0.3, w_stab: float = 0.2) -> float:
        return w_f1 * self.f1 + w_len * self.leniency + w_stab * self.stability

    def to_dict(self) -> dict[str, Any]:
        return {
            "f1": self.f1,
            "leniency": self.leniency,
            "stability": self.stability,
            "weighted_total": self.weighted_total,
        }


@dataclass
class EvolutionGeneration:
    """Results from a single generation of evolution."""

    generation: int
    candidates: list[dict[str, Any]] = field(default_factory=list)
    fitness_scores: list[FitnessScore] = field(default_factory=list)
    best_fitness: FitnessScore | None = None
    best_candidate: dict[str, Any] | None = None


@dataclass
class EvolutionReport:
    """Full report from an evolution run."""

    generations_completed: int = 0
    generations: list[EvolutionGeneration] = field(default_factory=list)
    baseline_fitness: FitnessScore | None = None
    best_fitness: FitnessScore | None = None
    best_constitution_rules: list[dict[str, Any]] = field(default_factory=list)
    improvement_pct: float = 0.0
    frozen_fields_verified: bool = True

    def summary(self) -> str:
        base = self.baseline_fitness.weighted_total if self.baseline_fitness else 0.0
        best = self.best_fitness.weighted_total if self.best_fitness else 0.0
        return (
            f"Evolution: {self.generations_completed} gens, "
            f"baseline={base:.3f}, best={best:.3f}, "
            f"improvement={self.improvement_pct:.1f}%, "
            f"frozen_ok={self.frozen_fields_verified}"
        )


class ConstitutionalEvolutionEngine:
    """Evolutionary optimization of constitutional rules.

    Extends the openevolve_adapter with LLM-guided mutation operators.
    Uses multi-objective fitness: F1 + leniency + stability.

    Parameters
    ----------
    constitution_rules:
        List of rule dicts from the constitution.
    eval_fn:
        Callable that evaluates a set of rules and returns
        ``{"f1": float, "false_positive_rate": float}``
    llm:
        Optional LLM judge for intelligent mutations.
    population_size:
        Number of candidates per generation.
    mutation_rate:
        Probability of mutating each rule in a candidate.
    max_generations:
        Maximum number of generations to run.
    human_approval_every_n:
        Pause for human review every N generations.
    seed:
        Random seed for reproducibility.
    """

    def __init__(
        self,
        constitution_rules: list[dict[str, Any]],
        eval_fn: Any,
        *,
        llm: Any | None = None,
        population_size: int = 8,
        mutation_rate: float = 0.3,
        max_generations: int = 20,
        human_approval_every_n: int = 5,
        seed: int = 42,
    ) -> None:
        self._baseline_rules = [copy.deepcopy(r) for r in constitution_rules]
        self._eval_fn = eval_fn
        self._llm = llm
        self._population_size = population_size
        self._mutation_rate = mutation_rate
        self._max_generations = max_generations
        self._human_approval_every_n = human_approval_every_n
        self._rng = random.Random(seed)

        # Mutation operators
        self._keyword_mutator = KeywordMutator(llm, rng_seed=seed)
        self._pattern_mutator = PatternMutator(llm)
        self._severity_mutator = SeverityMutator(rng_seed=seed)
        self._operators = [
            self._keyword_mutator,
            self._pattern_mutator,
            self._severity_mutator,
        ]

    async def evolve(
        self,
        *,
        max_generations: int | None = None,
        bypass_evidence: dict[str, list[str]] | None = None,
    ) -> EvolutionReport:
        """Run the evolution loop.

        Parameters
        ----------
        max_generations:
            Override the default max generations.
        bypass_evidence:
            Dict mapping rule_id -> list of bypass texts from purple team.
            Used by mutation operators to guide keyword/pattern additions.

        Returns
        -------
        EvolutionReport with best candidate and fitness trajectory.
        """
        gens = max_generations or self._max_generations
        evidence = bypass_evidence or {}
        report = EvolutionReport()

        # Evaluate baseline
        baseline_score = await self._evaluate_fitness(self._baseline_rules)
        report.baseline_fitness = baseline_score
        report.best_fitness = baseline_score
        report.best_constitution_rules = copy.deepcopy(self._baseline_rules)

        # Initialize population with baseline + random mutations
        population = [copy.deepcopy(self._baseline_rules)]
        for _ in range(self._population_size - 1):
            mutant = await self._mutate_rules(
                copy.deepcopy(self._baseline_rules),
                evidence,
            )
            population.append(mutant)

        for gen_num in range(1, gens + 1):
            gen_result = EvolutionGeneration(generation=gen_num)

            # Evaluate all candidates
            scored: list[tuple[list[dict[str, Any]], FitnessScore]] = []
            for candidate_rules in population:
                score = await self._evaluate_fitness(candidate_rules)

                # Verify frozen fields
                if not self._verify_all_frozen(candidate_rules):
                    report.frozen_fields_verified = False
                    logger.warning("frozen_field_violation", extra={"generation": gen_num})
                    continue  # Discard invalid candidate

                scored.append((candidate_rules, score))
                gen_result.fitness_scores.append(score)

            if not scored:
                break

            # Sort by weighted fitness (descending)
            scored.sort(key=lambda x: x[1].weighted_total, reverse=True)
            gen_result.best_fitness = scored[0][1]
            gen_result.best_candidate = scored[0][0]

            # Update best if improved
            if scored[0][1].weighted_total > report.best_fitness.weighted_total:
                report.best_fitness = scored[0][1]
                report.best_constitution_rules = copy.deepcopy(scored[0][0])

            report.generations.append(gen_result)
            report.generations_completed = gen_num

            logger.info(
                "evolution_generation",
                extra={
                    "generation": gen_num,
                    "best_fitness": scored[0][1].weighted_total,
                    "population_size": len(scored),
                },
            )

            # Selection + mutation for next generation
            # Keep top 25% (elitism), mutate the rest from top 50%
            elite_count = max(1, len(scored) // 4)
            parent_pool_size = max(2, len(scored) // 2)
            elites = [copy.deepcopy(s[0]) for s in scored[:elite_count]]
            parents = [s[0] for s in scored[:parent_pool_size]]

            next_gen = list(elites)
            while len(next_gen) < self._population_size:
                parent = copy.deepcopy(self._rng.choice(parents))
                mutant = await self._mutate_rules(parent, evidence)
                next_gen.append(mutant)

            population = next_gen

        # Compute improvement
        base_total = report.baseline_fitness.weighted_total if report.baseline_fitness else 0.0
        best_total = report.best_fitness.weighted_total if report.best_fitness else 0.0
        if base_total > 0:
            report.improvement_pct = ((best_total - base_total) / base_total) * 100
        else:
            report.improvement_pct = 0.0

        return report

    async def _mutate_rules(
        self,
        rules: list[dict[str, Any]],
        evidence: dict[str, list[str]],
    ) -> list[dict[str, Any]]:
        """Apply random mutations to a set of rules."""
        mutated = []
        for rule in rules:
            if self._rng.random() < self._mutation_rate:
                operator = self._rng.choice(self._operators)
                rule_evidence = evidence.get(rule.get("id", ""), None)
                mutation = await operator.mutate(rule, bypass_evidence=rule_evidence)
                new_rule = apply_mutation(rule, mutation)
                mutated.append(new_rule)
            else:
                mutated.append(copy.deepcopy(rule))
        return mutated

    async def _evaluate_fitness(self, rules: list[dict[str, Any]]) -> FitnessScore:
        """Evaluate multi-objective fitness for a candidate rule set."""
        result = self._eval_fn(rules)
        if not isinstance(result, dict):
            result = {"f1": 0.0, "false_positive_rate": 0.0}

        f1 = result.get("f1", 0.0)
        fpr = result.get("false_positive_rate", 0.0)
        leniency = 1.0 - fpr

        # Stability: how different is this from baseline?
        stability = self._compute_stability(rules)

        return FitnessScore(f1=f1, leniency=leniency, stability=stability)

    def _compute_stability(self, rules: list[dict[str, Any]]) -> float:
        """Compute stability score (1.0 = identical to baseline, 0.0 = totally different)."""
        if not self._baseline_rules:
            return 1.0

        total_fields = 0
        changed_fields = 0

        baseline_by_id = {r.get("id", ""): r for r in self._baseline_rules}
        for rule in rules:
            rule_id = rule.get("id", "")
            baseline = baseline_by_id.get(rule_id)
            if baseline is None:
                changed_fields += len(rule)
                total_fields += len(rule)
                continue
            for field_name in ("keywords", "patterns", "severity", "workflow_action", "tags"):
                total_fields += 1
                if rule.get(field_name) != baseline.get(field_name):
                    changed_fields += 1

        if total_fields == 0:
            return 1.0
        return 1.0 - (changed_fields / total_fields)

    def _verify_all_frozen(self, rules: list[dict[str, Any]]) -> bool:
        """Verify no frozen fields were changed in any rule."""
        baseline_by_id = {r.get("id", ""): r for r in self._baseline_rules}
        for rule in rules:
            rule_id = rule.get("id", "")
            baseline = baseline_by_id.get(rule_id)
            if baseline is None:
                continue
            if not verify_frozen_fields(baseline, rule):
                return False
        return True

    def to_amendment_proposals(self, report: EvolutionReport) -> list[dict[str, Any]]:
        """Convert evolution results into amendment proposal dicts.

        These can be submitted to the AmendmentProposalEngine for human approval.
        """
        if not report.best_constitution_rules or not report.best_fitness:
            return []

        proposals = []
        baseline_by_id = {r.get("id", ""): r for r in self._baseline_rules}

        for rule in report.best_constitution_rules:
            rule_id = rule.get("id", "")
            baseline = baseline_by_id.get(rule_id)
            if baseline is None:
                continue

            changes: dict[str, Any] = {}
            for field_name in ("keywords", "patterns", "severity", "workflow_action", "tags"):
                if rule.get(field_name) != baseline.get(field_name):
                    changes[field_name] = {
                        "from": baseline.get(field_name),
                        "to": rule.get(field_name),
                    }

            if changes:
                proposals.append(
                    {
                        "rule_id": rule_id,
                        "proposed_changes": changes,
                        "justification": (
                            f"Evolution engine improvement: "
                            f"fitness {report.baseline_fitness.weighted_total:.3f} -> "
                            f"{report.best_fitness.weighted_total:.3f} "
                            f"({report.improvement_pct:.1f}% improvement)"
                        ),
                        "source": "constitutional_evolution",
                        "generation": report.generations_completed,
                    }
                )

        return proposals


__all__ = [
    "ConstitutionalEvolutionEngine",
    "EvolutionGeneration",
    "EvolutionReport",
    "FitnessScore",
]
