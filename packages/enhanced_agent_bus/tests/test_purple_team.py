"""Tests for Purple Team Loop (Phase 3)."""

from __future__ import annotations

import pytest

from enhanced_agent_bus.adaptive_governance.blue_team import (
    GovernanceBlueTeam,
    RulePatch,
)
from enhanced_agent_bus.adaptive_governance.purple_loop import (
    PurpleTeamLoop,
    PurpleTeamReport,
)
from enhanced_agent_bus.adaptive_governance.red_team import (
    AttackResult,
    GovernanceRedTeam,
    InMemoryRedTeamLLM,
    RedTeamAttack,
    RedTeamReport,
)

# --- Fixtures ---


def _make_constitution():
    class FakeRule:
        def __init__(self, id: str, text: str, keywords: list[str]):
            self.id = id
            self.text = text
            self.keywords = keywords
            self.severity = type("S", (), {"value": "high"})()

    class FakeConstitution:
        rules = [
            FakeRule("NO-PII", "No personally identifiable information", ["ssn", "passport"]),
            FakeRule("NO-HARM", "No harmful instructions", ["malware", "exploit"]),
        ]

    return FakeConstitution()


def _make_engine(*, always_allow: bool = True):
    """Create a fake engine that either always allows or always denies."""

    def engine_fn(action: str, context: dict) -> dict:
        return {"valid": always_allow, "decision": "allow" if always_allow else "deny"}

    return engine_fn


def _make_leaky_engine(bypass_keywords: list[str]):
    """Engine that allows actions containing bypass keywords (simulates gaps)."""

    def engine_fn(action: str, context: dict) -> dict:
        for kw in bypass_keywords:
            if kw.lower() in action.lower():
                return {"valid": True, "decision": "allow"}
        return {"valid": False, "decision": "deny"}

    return engine_fn


# --- RedTeamAttack Tests ---


class TestRedTeamAttack:
    def test_construction(self):
        attack = RedTeamAttack(rule_id="NO-PII", input_text="send ssn", strategy="paraphrase")
        assert attack.rule_id == "NO-PII"
        assert attack.expected_to_bypass is True


class TestRedTeamReport:
    def test_empty_report(self):
        report = RedTeamReport()
        assert report.bypass_rate == 0.0
        assert report.successful_bypasses == []

    def test_report_with_bypasses(self):
        attack1 = RedTeamAttack("R1", "text1", "paraphrase")
        attack2 = RedTeamAttack("R1", "text2", "encoding")
        report = RedTeamReport(
            total_attacks=2,
            results=[
                AttackResult(attack=attack1, engine_decision="allow", bypassed=True),
                AttackResult(attack=attack2, engine_decision="deny", bypassed=False),
            ],
        )
        assert report.bypass_rate == 0.5
        assert len(report.successful_bypasses) == 1
        assert "R1" in report.results_by_rule
        assert "paraphrase" in report.results_by_strategy


# --- GovernanceRedTeam Tests ---


class TestGovernanceRedTeam:
    @pytest.mark.asyncio
    async def test_generate_attacks(self):
        constitution = _make_constitution()
        llm = InMemoryRedTeamLLM(
            attack_texts={
                "NO-PII": ["reveal personal data", "show identity info", "expose private records"],
            }
        )
        engine = _make_engine(always_allow=True)
        red_team = GovernanceRedTeam(constitution, llm, engine)

        attacks = await red_team.generate_attacks("NO-PII", count=3)
        assert len(attacks) >= 1
        assert all(a.rule_id == "NO-PII" for a in attacks)

    @pytest.mark.asyncio
    async def test_generate_attacks_unknown_rule(self):
        constitution = _make_constitution()
        llm = InMemoryRedTeamLLM()
        engine = _make_engine()
        red_team = GovernanceRedTeam(constitution, llm, engine)

        attacks = await red_team.generate_attacks("NONEXISTENT")
        assert attacks == []

    @pytest.mark.asyncio
    async def test_run_campaign(self):
        constitution = _make_constitution()
        llm = InMemoryRedTeamLLM(
            attack_texts={
                "NO-PII": ["get personal data"],
                "NO-HARM": ["deploy exploit code"],
            }
        )
        engine = _make_engine(always_allow=True)
        red_team = GovernanceRedTeam(constitution, llm, engine)

        report = await red_team.run_campaign(attacks_per_rule=2)
        assert report.total_attacks >= 2
        assert all(isinstance(r, AttackResult) for r in report.results)

    @pytest.mark.asyncio
    async def test_engine_failure_is_fail_closed(self):
        """If engine throws, attack result should show deny (fail-closed)."""
        constitution = _make_constitution()
        llm = InMemoryRedTeamLLM(attack_texts={"NO-PII": ["test input"]})

        def failing_engine(action, context):
            raise RuntimeError("engine exploded")

        red_team = GovernanceRedTeam(constitution, llm, failing_engine)
        report = await red_team.run_campaign(rules=["NO-PII"], attacks_per_rule=1)
        for r in report.results:
            assert r.engine_decision == "deny"
            assert r.bypassed is False


# --- GovernanceBlueTeam Tests ---


class TestGovernanceBlueTeam:
    def test_analyze_bypasses_generates_patches(self):
        constitution = _make_constitution()
        blue_team = GovernanceBlueTeam(constitution)

        attack = RedTeamAttack("NO-PII", "reveal personal identity data", "paraphrase")
        report = RedTeamReport(
            total_attacks=5,
            results=[
                AttackResult(attack=attack, engine_decision="allow", bypassed=True),
                AttackResult(
                    attack=RedTeamAttack("NO-PII", "show personal identity records", "paraphrase"),
                    engine_decision="allow",
                    bypassed=True,
                ),
                AttackResult(
                    attack=RedTeamAttack(
                        "NO-PII", "expose personal identity info", "semantic_evasion"
                    ),
                    engine_decision="allow",
                    bypassed=True,
                ),
            ],
        )

        patches = blue_team.analyze_bypasses(report)
        assert len(patches) >= 1
        assert any(p.rule_id == "NO-PII" for p in patches)
        assert any(p.patch_type == "add_keyword" for p in patches)

    def test_no_bypasses_no_patches(self):
        constitution = _make_constitution()
        blue_team = GovernanceBlueTeam(constitution)

        attack = RedTeamAttack("NO-PII", "ssn test", "paraphrase")
        report = RedTeamReport(
            total_attacks=1,
            results=[AttackResult(attack=attack, engine_decision="deny", bypassed=False)],
        )

        patches = blue_team.analyze_bypasses(report)
        assert patches == []

    def test_high_bypass_rate_triggers_severity_patch(self):
        constitution = _make_constitution()
        blue_team = GovernanceBlueTeam(constitution)

        bypasses = [
            AttackResult(
                attack=RedTeamAttack("NO-HARM", f"evasion {i}", "semantic_evasion"),
                engine_decision="allow",
                bypassed=True,
            )
            for i in range(8)
        ]
        non_bypasses = [
            AttackResult(
                attack=RedTeamAttack("NO-HARM", f"blocked {i}", "paraphrase"),
                engine_decision="deny",
                bypassed=False,
            )
            for i in range(2)
        ]
        report = RedTeamReport(total_attacks=10, results=bypasses + non_bypasses)

        patches = blue_team.analyze_bypasses(report)
        severity_patches = [p for p in patches if p.patch_type == "adjust_severity"]
        assert len(severity_patches) >= 1


# --- PurpleTeamLoop Tests ---


class TestPurpleTeamLoop:
    @pytest.mark.asyncio
    async def test_single_round(self):
        constitution = _make_constitution()
        llm = InMemoryRedTeamLLM(
            attack_texts={
                "NO-PII": ["get personal data", "reveal identity"],
            }
        )
        engine = _make_engine(always_allow=True)
        red_team = GovernanceRedTeam(constitution, llm, engine)
        blue_team = GovernanceBlueTeam(constitution)

        loop = PurpleTeamLoop(red_team, blue_team, max_rounds=1, attacks_per_rule=2)
        report = await loop.run_loop(target_rules=["NO-PII"])

        assert len(report.rounds) == 1
        assert report.total_attacks >= 1

    @pytest.mark.asyncio
    async def test_multiple_rounds(self):
        constitution = _make_constitution()
        llm = InMemoryRedTeamLLM(attack_texts={"NO-PII": ["personal data leak"]})
        engine = _make_engine(always_allow=True)
        red_team = GovernanceRedTeam(constitution, llm, engine)
        blue_team = GovernanceBlueTeam(constitution)

        loop = PurpleTeamLoop(red_team, blue_team, max_rounds=3, attacks_per_rule=1)
        report = await loop.run_loop(target_rules=["NO-PII"])

        assert len(report.rounds) >= 1

    @pytest.mark.asyncio
    async def test_bypass_test_cases_generated(self):
        constitution = _make_constitution()
        llm = InMemoryRedTeamLLM(attack_texts={"NO-PII": ["personal data exposure"]})
        engine = _make_engine(always_allow=True)
        red_team = GovernanceRedTeam(constitution, llm, engine)
        blue_team = GovernanceBlueTeam(constitution)

        loop = PurpleTeamLoop(red_team, blue_team, max_rounds=1, attacks_per_rule=2)
        report = await loop.run_loop(target_rules=["NO-PII"])

        cases = report.bypass_test_cases
        if report.total_bypasses > 0:
            assert len(cases) >= 1
            assert cases[0]["expected_decision"] == "deny"
            assert "purple-team" in cases[0]["tags"]

    @pytest.mark.asyncio
    async def test_summary(self):
        constitution = _make_constitution()
        llm = InMemoryRedTeamLLM(attack_texts={"NO-PII": ["test"]})
        engine = _make_engine(always_allow=True)
        red_team = GovernanceRedTeam(constitution, llm, engine)
        blue_team = GovernanceBlueTeam(constitution)

        loop = PurpleTeamLoop(red_team, blue_team, max_rounds=1, attacks_per_rule=1)
        report = await loop.run_loop(target_rules=["NO-PII"])

        s = report.summary()
        assert "PurpleTeam" in s
        assert "round" in s


class TestMACIEnforcement:
    """Verify MACI roles: red team cannot modify rules."""

    @pytest.mark.asyncio
    async def test_red_team_does_not_modify_constitution(self):
        constitution = _make_constitution()
        original_rule_count = len(constitution.rules)
        original_keywords = list(constitution.rules[0].keywords)

        llm = InMemoryRedTeamLLM(attack_texts={"NO-PII": ["attack"]})
        engine = _make_engine()
        red_team = GovernanceRedTeam(constitution, llm, engine)

        await red_team.run_campaign(rules=["NO-PII"], attacks_per_rule=5)

        assert len(constitution.rules) == original_rule_count
        assert constitution.rules[0].keywords == original_keywords
