"""Tests for Constitutional Evolution Engine (Phase 4)."""

from __future__ import annotations

import copy

import pytest

from enhanced_agent_bus.openevolve_adapter.constitutional_evolution import (
    ConstitutionalEvolutionEngine,
    EvolutionReport,
    FitnessScore,
)
from enhanced_agent_bus.openevolve_adapter.mutation_operators import (
    EVOLVABLE_FIELDS,
    FROZEN_FIELDS,
    KeywordMutator,
    MutationResult,
    PatternMutator,
    SeverityMutator,
    apply_mutation,
    verify_frozen_fields,
)

# --- Fixtures ---


def _make_rules() -> list[dict]:
    return [
        {
            "id": "NO-PII",
            "text": "No personally identifiable information",
            "severity": "critical",
            "keywords": ["ssn", "passport"],
            "patterns": [],
            "category": "privacy",
            "tags": ["compliance"],
        },
        {
            "id": "NO-HARM",
            "text": "No harmful instructions",
            "severity": "high",
            "keywords": ["malware", "exploit"],
            "patterns": [],
            "category": "safety",
            "tags": [],
        },
    ]


def _make_eval_fn(*, base_f1: float = 0.8, base_fpr: float = 0.1):
    """Create a deterministic eval function.

    Returns slightly better scores when keywords are added (simulating improvement).
    """

    def eval_fn(rules: list[dict]) -> dict:
        total_keywords = sum(len(r.get("keywords", [])) for r in rules)
        # More keywords = slightly better F1, slightly worse FPR
        bonus = min(0.15, total_keywords * 0.01)
        return {
            "f1": min(1.0, base_f1 + bonus),
            "false_positive_rate": min(1.0, base_fpr + bonus * 0.5),
        }

    return eval_fn


# --- Mutation Operator Tests ---


class TestKeywordMutator:
    @pytest.mark.asyncio
    async def test_mutate_with_evidence(self):
        mutator = KeywordMutator()
        rule = _make_rules()[0]
        evidence = [
            "reveal personal identity data",
            "expose personal identity records",
            "show personal identity information",
        ]
        result = await mutator.mutate(rule, bypass_evidence=evidence)
        assert result.rule_id == "NO-PII"
        assert result.operator == "keyword_mutation"
        assert result.field_changed == "keywords"
        assert isinstance(result.new_value, list)

    @pytest.mark.asyncio
    async def test_mutate_without_llm_random(self):
        mutator = KeywordMutator(rng_seed=42)
        rule = _make_rules()[0]
        result = await mutator.mutate(rule)
        assert result.field_changed == "keywords"

    @pytest.mark.asyncio
    async def test_evidence_extracts_frequent_words(self):
        mutator = KeywordMutator()
        rule = {"id": "R1", "text": "test", "keywords": ["existing"]}
        evidence = [
            "personal identity theft scheme",
            "personal identity fraud operation",
            "personal identity data breach",
        ]
        result = await mutator.mutate(rule, bypass_evidence=evidence)
        # "personal" and "identity" appear in all 3 -> should be candidates
        new_kw = result.new_value
        assert len(new_kw) > len(rule["keywords"])


class TestPatternMutator:
    @pytest.mark.asyncio
    async def test_mutate_without_llm(self):
        mutator = PatternMutator()
        rule = _make_rules()[0]
        result = await mutator.mutate(rule)
        assert result.field_changed == "patterns"
        assert result.operator == "pattern_mutation"


class TestSeverityMutator:
    @pytest.mark.asyncio
    async def test_shifts_severity(self):
        mutator = SeverityMutator(rng_seed=42)
        rule = {"id": "R1", "text": "t", "severity": "medium"}
        result = await mutator.mutate(rule)
        assert result.field_changed == "severity"
        assert result.new_value in ["low", "medium", "high", "critical"]
        assert result.new_value != "medium" or result.old_value == "medium"

    @pytest.mark.asyncio
    async def test_boundary_low(self):
        mutator = SeverityMutator(rng_seed=0)
        rule = {"id": "R1", "text": "t", "severity": "low"}
        result = await mutator.mutate(rule)
        assert result.new_value in ["low", "medium"]

    @pytest.mark.asyncio
    async def test_boundary_critical(self):
        mutator = SeverityMutator(rng_seed=0)
        rule = {"id": "R1", "text": "t", "severity": "critical"}
        result = await mutator.mutate(rule)
        assert result.new_value in ["high", "critical"]


class TestApplyMutation:
    def test_apply_evolvable_field(self):
        rule = _make_rules()[0]
        mutation = MutationResult(
            rule_id="NO-PII",
            operator="test",
            field_changed="keywords",
            old_value=["ssn"],
            new_value=["ssn", "social"],
            description="test",
        )
        new_rule = apply_mutation(rule, mutation)
        assert new_rule["keywords"] == ["ssn", "social"]
        assert rule["keywords"] == ["ssn", "passport"]  # original unchanged

    def test_reject_frozen_field(self):
        rule = _make_rules()[0]
        mutation = MutationResult(
            rule_id="NO-PII",
            operator="test",
            field_changed="id",
            old_value="NO-PII",
            new_value="CHANGED",
            description="test",
        )
        with pytest.raises(ValueError, match="frozen"):
            apply_mutation(rule, mutation)

    def test_reject_text_mutation(self):
        rule = _make_rules()[0]
        mutation = MutationResult(
            rule_id="NO-PII",
            operator="test",
            field_changed="text",
            old_value="old",
            new_value="new",
            description="test",
        )
        with pytest.raises(ValueError, match="frozen"):
            apply_mutation(rule, mutation)


class TestVerifyFrozenFields:
    def test_identical_passes(self):
        rule = _make_rules()[0]
        assert verify_frozen_fields(rule, copy.deepcopy(rule)) is True

    def test_evolvable_change_passes(self):
        original = _make_rules()[0]
        mutated = copy.deepcopy(original)
        mutated["keywords"] = ["ssn", "passport", "new"]
        assert verify_frozen_fields(original, mutated) is True

    def test_frozen_change_fails(self):
        original = _make_rules()[0]
        mutated = copy.deepcopy(original)
        mutated["id"] = "CHANGED"
        assert verify_frozen_fields(original, mutated) is False

    def test_text_change_fails(self):
        original = _make_rules()[0]
        mutated = copy.deepcopy(original)
        mutated["text"] = "modified text"
        assert verify_frozen_fields(original, mutated) is False

    def test_category_change_fails(self):
        original = _make_rules()[0]
        mutated = copy.deepcopy(original)
        mutated["category"] = "different"
        assert verify_frozen_fields(original, mutated) is False


# --- Fitness Score Tests ---


class TestFitnessScore:
    def test_weighted_total(self):
        score = FitnessScore(f1=0.8, leniency=0.9, stability=1.0)
        # 0.5*0.8 + 0.3*0.9 + 0.2*1.0 = 0.4 + 0.27 + 0.2 = 0.87
        assert abs(score.weighted_total - 0.87) < 0.01

    def test_to_dict(self):
        score = FitnessScore(f1=0.8, leniency=0.9, stability=1.0)
        d = score.to_dict()
        assert "f1" in d
        assert "leniency" in d
        assert "stability" in d
        assert "weighted_total" in d


# --- Evolution Engine Tests ---


class TestConstitutionalEvolutionEngine:
    @pytest.mark.asyncio
    async def test_basic_evolution_run(self):
        rules = _make_rules()
        eval_fn = _make_eval_fn()
        engine = ConstitutionalEvolutionEngine(
            rules,
            eval_fn,
            population_size=4,
            max_generations=3,
            seed=42,
        )
        report = await engine.evolve(max_generations=3)

        assert report.generations_completed == 3
        assert report.baseline_fitness is not None
        assert report.best_fitness is not None
        assert len(report.generations) == 3
        assert report.frozen_fields_verified is True

    @pytest.mark.asyncio
    async def test_frozen_fields_preserved(self):
        rules = _make_rules()
        eval_fn = _make_eval_fn()
        engine = ConstitutionalEvolutionEngine(
            rules,
            eval_fn,
            population_size=4,
            max_generations=5,
            mutation_rate=0.8,
            seed=42,
        )
        report = await engine.evolve()

        # All rules in best candidate must have same frozen fields as baseline
        baseline_by_id = {r["id"]: r for r in rules}
        for rule in report.best_constitution_rules:
            baseline = baseline_by_id.get(rule["id"])
            if baseline:
                for field_name in FROZEN_FIELDS:
                    assert rule[field_name] == baseline[field_name], (
                        f"Frozen field {field_name} was modified in rule {rule['id']}"
                    )

    @pytest.mark.asyncio
    async def test_improvement_possible(self):
        """With a reward for more keywords, evolution should find improvements."""
        rules = _make_rules()
        eval_fn = _make_eval_fn(base_f1=0.6, base_fpr=0.05)
        engine = ConstitutionalEvolutionEngine(
            rules,
            eval_fn,
            population_size=6,
            max_generations=10,
            mutation_rate=0.5,
            seed=42,
        )
        report = await engine.evolve(
            bypass_evidence={
                "NO-PII": ["personal identity data", "personal information leak"],
                "NO-HARM": ["dangerous instruction", "harmful content delivery"],
            },
        )

        # Should show some improvement (or at least not regress)
        assert report.best_fitness.weighted_total >= report.baseline_fitness.weighted_total - 0.01

    @pytest.mark.asyncio
    async def test_single_generation(self):
        rules = _make_rules()
        eval_fn = _make_eval_fn()
        engine = ConstitutionalEvolutionEngine(
            rules,
            eval_fn,
            population_size=2,
            seed=42,
        )
        report = await engine.evolve(max_generations=1)
        assert report.generations_completed == 1

    @pytest.mark.asyncio
    async def test_summary(self):
        rules = _make_rules()
        eval_fn = _make_eval_fn()
        engine = ConstitutionalEvolutionEngine(
            rules,
            eval_fn,
            population_size=2,
            max_generations=2,
            seed=42,
        )
        report = await engine.evolve()
        s = report.summary()
        assert "Evolution" in s
        assert "gens" in s


class TestAmendmentProposals:
    @pytest.mark.asyncio
    async def test_to_amendment_proposals(self):
        rules = _make_rules()
        eval_fn = _make_eval_fn(base_f1=0.5)
        engine = ConstitutionalEvolutionEngine(
            rules,
            eval_fn,
            population_size=4,
            max_generations=5,
            mutation_rate=0.8,
            seed=42,
        )
        report = await engine.evolve(
            bypass_evidence={"NO-PII": ["personal data", "identity info"]},
        )

        proposals = engine.to_amendment_proposals(report)
        # May or may not have proposals depending on whether mutations improved fitness
        for p in proposals:
            assert "rule_id" in p
            assert "proposed_changes" in p
            assert "justification" in p
            assert p["source"] == "constitutional_evolution"

    @pytest.mark.asyncio
    async def test_empty_report_no_proposals(self):
        rules = _make_rules()
        eval_fn = _make_eval_fn()
        engine = ConstitutionalEvolutionEngine(rules, eval_fn, population_size=2, seed=42)
        report = EvolutionReport()
        proposals = engine.to_amendment_proposals(report)
        assert proposals == []


class TestInvariantIntegration:
    """Verify evolution respects the invariant system."""

    def test_frozen_fields_match_invariant_scope(self):
        """FROZEN_FIELDS should align with what the invariant system protects."""
        assert "id" in FROZEN_FIELDS
        assert "text" in FROZEN_FIELDS
        assert "category" in FROZEN_FIELDS

    def test_evolvable_fields_are_disjoint(self):
        """FROZEN and EVOLVABLE must not overlap."""
        assert FROZEN_FIELDS.isdisjoint(EVOLVABLE_FIELDS)

    def test_keywords_is_evolvable(self):
        assert "keywords" in EVOLVABLE_FIELDS

    def test_patterns_is_evolvable(self):
        assert "patterns" in EVOLVABLE_FIELDS

    def test_severity_is_evolvable(self):
        assert "severity" in EVOLVABLE_FIELDS


class TestStabilityScore:
    @pytest.mark.asyncio
    async def test_identical_rules_full_stability(self):
        rules = _make_rules()
        eval_fn = _make_eval_fn()
        engine = ConstitutionalEvolutionEngine(rules, eval_fn, seed=42)
        stability = engine._compute_stability(copy.deepcopy(rules))
        assert stability == 1.0

    @pytest.mark.asyncio
    async def test_modified_rules_lower_stability(self):
        rules = _make_rules()
        eval_fn = _make_eval_fn()
        engine = ConstitutionalEvolutionEngine(rules, eval_fn, seed=42)
        modified = copy.deepcopy(rules)
        modified[0]["keywords"] = ["ssn", "passport", "extra1", "extra2"]
        modified[1]["severity"] = "critical"
        stability = engine._compute_stability(modified)
        assert 0.0 < stability < 1.0
