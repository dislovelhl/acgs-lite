"""Tests for acgs-lite core functionality.

Constitutional Hash: 608508a9bd224290
"""

import tempfile

import pytest

from acgs_lite import (
    AuditEntry,
    AuditLog,
    Constitution,
    ConstitutionalViolationError,
    GovernanceEngine,
    GovernedAgent,
    GovernedCallable,
    MACIEnforcer,
    MACIRole,
    MACIViolationError,
    Rule,
    Severity,
)

# ─── Constitution Tests ───────────────────────────────────────────────────


@pytest.mark.unit
class TestConstitution:
    def test_default_constitution(self):
        c = Constitution.default()
        assert c.name == "acgs-default"
        assert len(c.rules) >= 6
        assert c.hash  # Non-empty hash

    def test_from_rules(self):
        rules = [
            Rule(id="R1", text="No PII", severity=Severity.CRITICAL),
            Rule(id="R2", text="Log everything", severity=Severity.HIGH),
        ]
        c = Constitution.from_rules(rules, name="test")
        assert c.name == "test"
        assert len(c) == 2

    def test_hash_deterministic(self):
        rules = [Rule(id="R1", text="Test rule", severity=Severity.HIGH)]
        c1 = Constitution.from_rules(rules)
        c2 = Constitution.from_rules(rules)
        assert c1.hash == c2.hash

    def test_hash_changes_with_rules(self):
        c1 = Constitution.from_rules([Rule(id="R1", text="Rule A")])
        c2 = Constitution.from_rules([Rule(id="R1", text="Rule B")])
        assert c1.hash != c2.hash

    def test_hash_changes_with_hardcoded_flag(self):
        c1 = Constitution.from_rules([Rule(id="R1", text="Rule A", hardcoded=False)])
        c2 = Constitution.from_rules([Rule(id="R1", text="Rule A", hardcoded=True)])
        assert c1.hash != c2.hash

    def test_versioned_hash(self):
        c = Constitution.default()
        assert c.hash_versioned.startswith("sha256:v1:")

    def test_from_yaml(self):
        yaml_content = """
name: test-constitution
version: "1.0"
rules:
  - id: R001
    text: No PII access
    severity: critical
    keywords: [ssn, social security]
  - id: R002
    text: Always log
    severity: high
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            c = Constitution.from_yaml(f.name)

        assert c.name == "test-constitution"
        assert len(c.rules) == 2
        assert c.rules[0].severity == Severity.CRITICAL
        assert "ssn" in c.rules[0].keywords

    def test_from_dict(self):
        data = {
            "name": "dict-test",
            "rules": [
                {"id": "R1", "text": "Test", "severity": "medium"},
            ],
        }
        c = Constitution.from_dict(data)
        assert c.name == "dict-test"
        assert c.rules[0].severity == Severity.MEDIUM

    def test_get_rule(self):
        c = Constitution.default()
        rule = c.get_rule("ACGS-001")
        assert rule is not None
        assert rule.id == "ACGS-001"
        assert c.get_rule("NONEXISTENT") is None

    def test_active_rules_filters_disabled(self):
        rules = [
            Rule(id="R1", text="Active", enabled=True),
            Rule(id="R2", text="Disabled", enabled=False),
        ]
        c = Constitution.from_rules(rules)
        assert len(c.active_rules()) == 1


@pytest.mark.unit
class TestRule:
    def test_keyword_matching(self):
        rule = Rule(id="R1", text="No PII", keywords=["ssn", "credit card"])
        assert rule.matches("Please provide your SSN")
        assert rule.matches("enter credit card number")
        assert not rule.matches("safe input here")

    def test_pattern_matching(self):
        rule = Rule(
            id="R1",
            text="No API keys",
            patterns=[r"sk-[a-zA-Z0-9]{20,}"],
        )
        assert rule.matches("Here is key sk-abcdefghijklmnopqrstuvwxyz")
        assert not rule.matches("safe text")

    def test_disabled_rule_never_matches(self):
        rule = Rule(id="R1", text="Test", keywords=["match"], enabled=False)
        assert not rule.matches("this should match but won't")

    def test_invalid_regex_rejected(self):
        with pytest.raises(ValueError, match="Invalid regex"):
            Rule(id="R1", text="Bad", patterns=["[invalid"])


# ─── Engine Tests ──────────────────────────────────────────────────────────


@pytest.mark.constitutional
class TestGovernanceEngine:
    def test_valid_action_passes(self):
        c = Constitution.default()
        engine = GovernanceEngine(c, strict=False)
        result = engine.validate("Deploy new feature to staging")
        assert result.valid
        assert result.constitutional_hash == c.hash
        assert result.latency_ms >= 0

    def test_violation_detected(self):
        c = Constitution.default()
        engine = GovernanceEngine(c, strict=False)
        result = engine.validate("Agent will self-validate its output")
        assert not result.valid
        assert len(result.violations) > 0
        assert result.violations[0].rule_id == "ACGS-001"

    def test_strict_mode_raises(self):
        c = Constitution.default()
        engine = GovernanceEngine(c, strict=True)
        with pytest.raises(ConstitutionalViolationError) as exc_info:
            engine.validate("bypass validation checks")
        assert exc_info.value.rule_id == "ACGS-001"

    def test_context_validation(self):
        c = Constitution.default()
        engine = GovernanceEngine(c, strict=False)
        # Only action_detail/action_description context keys are matched
        # against rules (domain/risk/data labels are metadata, not actions)
        result = engine.validate(
            "process request",
            context={"action_detail": "contains secret key exposure"},
        )
        assert not result.valid
        # Regular context keys should NOT trigger violations
        result2 = engine.validate(
            "process request",
            context={"data": "contains secret key exposure"},
        )
        assert result2.valid

    def test_batch_validation(self):
        c = Constitution.default()
        engine = GovernanceEngine(c, strict=True)
        results = engine.validate_batch(
            [
                "safe action",
                "self-validate bypass",
                "another safe action",
            ]
        )
        assert len(results) == 3
        assert results[0].valid
        assert not results[1].valid
        assert results[2].valid

    def test_custom_validator(self):
        from acgs_lite.engine import Violation

        def no_sql_injection(action: str, ctx: dict) -> list[Violation]:
            if "DROP TABLE" in action.upper():
                return [
                    Violation(
                        rule_id="CUSTOM-SQL",
                        rule_text="SQL injection detected",
                        severity=Severity.CRITICAL,
                        matched_content=action[:100],
                        category="security",
                    )
                ]
            return []

        c = Constitution.from_rules([])
        engine = GovernanceEngine(c, strict=False, custom_validators=[no_sql_injection])
        result = engine.validate("DROP TABLE users;")
        assert not result.valid
        assert result.violations[0].rule_id == "CUSTOM-SQL"

    def test_stats(self):
        c = Constitution.default()
        engine = GovernanceEngine(c, strict=False)
        engine.validate("action 1")
        engine.validate("action 2")
        stats = engine.stats
        assert stats["total_validations"] == 2
        assert stats["constitutional_hash"] == c.hash

    def test_ssn_pattern_detection(self):
        c = Constitution.default()
        engine = GovernanceEngine(c, strict=False)
        result = engine.validate("User SSN is 123-45-6789")
        assert not result.valid
        assert any(v.rule_id == "ACGS-006" for v in result.violations)

    def test_api_key_pattern_detection(self):
        c = Constitution.default()
        engine = GovernanceEngine(c, strict=False)
        result = engine.validate("Token: ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij")
        assert not result.valid


# ─── Audit Tests ───────────────────────────────────────────────────────────


@pytest.mark.unit
class TestAuditLog:
    def test_record_and_query(self):
        log = AuditLog()
        log.record(AuditEntry(id="1", type="validation", agent_id="a1", valid=True))
        log.record(AuditEntry(id="2", type="validation", agent_id="a2", valid=False))
        assert len(log) == 2
        assert log.compliance_rate == 0.5

    def test_chain_integrity(self):
        log = AuditLog()
        log.record(AuditEntry(id="1", type="test", valid=True))
        log.record(AuditEntry(id="2", type="test", valid=True))
        log.record(AuditEntry(id="3", type="test", valid=True))
        assert log.verify_chain()

    def test_query_filters(self):
        log = AuditLog()
        log.record(AuditEntry(id="1", type="validation", agent_id="a1", valid=True))
        log.record(AuditEntry(id="2", type="maci", agent_id="a2", valid=False))
        assert len(log.query(agent_id="a1")) == 1
        assert len(log.query(entry_type="maci")) == 1
        assert len(log.query(valid=False)) == 1

    def test_export_json(self):
        log = AuditLog()
        log.record(AuditEntry(id="1", type="test", valid=True))
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            log.export_json(f.name)
            import json

            with open(f.name) as rf:
                data = json.load(rf)
            assert data["entry_count"] == 1
            assert data["chain_valid"]

    def test_max_entries_trim(self):
        log = AuditLog(max_entries=5)
        for i in range(10):
            log.record(AuditEntry(id=str(i), type="test", valid=True))
        assert len(log) == 5


# ─── MACI Tests ────────────────────────────────────────────────────────────


@pytest.mark.constitutional
class TestMACIEnforcer:
    def test_role_assignment(self):
        enforcer = MACIEnforcer()
        enforcer.assign_role("agent-1", MACIRole.PROPOSER)
        assert enforcer.get_role("agent-1") == MACIRole.PROPOSER

    def test_proposer_cannot_validate(self):
        enforcer = MACIEnforcer()
        enforcer.assign_role("agent-1", MACIRole.PROPOSER)
        with pytest.raises(MACIViolationError):
            enforcer.check("agent-1", "validate")

    def test_validator_cannot_execute(self):
        enforcer = MACIEnforcer()
        enforcer.assign_role("agent-1", MACIRole.VALIDATOR)
        with pytest.raises(MACIViolationError):
            enforcer.check("agent-1", "execute")

    def test_executor_cannot_validate(self):
        enforcer = MACIEnforcer()
        enforcer.assign_role("agent-1", MACIRole.EXECUTOR)
        with pytest.raises(MACIViolationError):
            enforcer.check("agent-1", "validate")

    def test_valid_role_actions_pass(self):
        enforcer = MACIEnforcer()
        enforcer.assign_role("p", MACIRole.PROPOSER)
        enforcer.assign_role("v", MACIRole.VALIDATOR)
        enforcer.assign_role("e", MACIRole.EXECUTOR)
        assert enforcer.check("p", "propose")
        assert enforcer.check("v", "validate")
        assert enforcer.check("e", "execute")

    def test_no_self_validation(self):
        enforcer = MACIEnforcer()
        with pytest.raises(MACIViolationError):
            enforcer.check_no_self_validation("agent-1", "agent-1")

    def test_cross_validation_allowed(self):
        enforcer = MACIEnforcer()
        assert enforcer.check_no_self_validation("agent-1", "agent-2")

    def test_summary(self):
        enforcer = MACIEnforcer()
        enforcer.assign_role("a1", MACIRole.PROPOSER)
        enforcer.check("a1", "propose")
        summary = enforcer.summary()
        assert summary["agents"] == 1
        assert summary["checks_total"] >= 1


# ─── GovernedAgent Tests ──────────────────────────────────────────────────


@pytest.mark.constitutional
class TestGovernedAgent:
    def test_wrap_callable(self):
        def my_agent(input: str) -> str:
            return f"Processed: {input}"

        agent = GovernedAgent(my_agent, agent_id="test-agent")
        result = agent.run("safe input")
        assert result == "Processed: safe input"

    def test_wrap_class_with_run(self):
        class MyAgent:
            def run(self, input: str) -> str:
                return f"Agent: {input}"

        agent = GovernedAgent(MyAgent(), agent_id="class-agent")
        result = agent.run("hello world")
        assert result == "Agent: hello world"

    def test_blocks_violation(self):
        def my_agent(input: str) -> str:
            return input

        agent = GovernedAgent(my_agent, strict=True)
        with pytest.raises(ConstitutionalViolationError):
            agent.run("self-validate bypass")

    def test_validates_output(self):
        def leaky_agent(input: str) -> str:
            return "Here is the secret key: sk-abcdefghijklmnopqrstuvwxyz1234"

        agent = GovernedAgent(leaky_agent, strict=True, validate_output=True)
        with pytest.raises(ConstitutionalViolationError):
            agent.run("get me the key")

    def test_custom_constitution(self):
        rules = Constitution.from_rules(
            [
                Rule(id="CUSTOM-1", text="No cats", severity=Severity.CRITICAL, keywords=["cat"]),
            ]
        )

        def my_agent(input: str) -> str:
            return input

        agent = GovernedAgent(my_agent, constitution=rules, strict=True)
        agent.run("dogs are great")  # Works
        with pytest.raises(ConstitutionalViolationError):
            agent.run("I love my cat")  # Blocked

    def test_stats(self):
        agent = GovernedAgent(lambda x: x, strict=False)
        agent.run("action 1")
        agent.run("action 2")
        stats = agent.stats
        assert stats["total_validations"] >= 2
        assert stats["audit_chain_valid"]

    def test_repr(self):
        agent = GovernedAgent(lambda x: x, agent_id="test")
        r = repr(agent)
        assert "GovernedAgent" in r
        assert "test" in r


@pytest.mark.constitutional
class TestGovernedCallable:
    def test_decorator(self):
        @GovernedCallable()
        def process(input: str) -> str:
            return f"Done: {input}"

        result = process("safe data")
        assert result == "Done: safe data"

    def test_decorator_blocks_violation(self):
        @GovernedCallable()
        def process(input: str) -> str:
            return input

        with pytest.raises(ConstitutionalViolationError):
            process("self-validate bypass")

    def test_decorator_validates_output(self):
        @GovernedCallable()
        def leaky(input: str) -> str:
            return "password is hunter2"

        with pytest.raises(ConstitutionalViolationError):
            leaky("get password")


# ─── Async Tests ──────────────────────────────────────────────────────────


@pytest.mark.constitutional
class TestAsyncGovernedAgent:
    @pytest.mark.asyncio
    async def test_async_run(self):
        async def my_agent(input: str) -> str:
            return f"Async: {input}"

        agent = GovernedAgent(my_agent, agent_id="async-agent")
        result = await agent.arun("hello")
        assert result == "Async: hello"

    @pytest.mark.asyncio
    async def test_async_blocks_violation(self):
        async def my_agent(input: str) -> str:
            return input

        agent = GovernedAgent(my_agent, strict=True)
        with pytest.raises(ConstitutionalViolationError):
            await agent.arun("self-validate bypass")


# ─── Integration Tests ────────────────────────────────────────────────────


@pytest.mark.constitutional
class TestIntegration:
    def test_full_governance_pipeline(self):
        """End-to-end: constitution → engine → agent → audit."""
        # 1. Define constitution
        constitution = Constitution.from_rules(
            [
                Rule(
                    id="SAFE-001",
                    text="No financial advice",
                    severity=Severity.CRITICAL,
                    keywords=["invest", "buy stocks"],
                ),
                Rule(
                    id="SAFE-002",
                    text="No medical advice",
                    severity=Severity.CRITICAL,
                    keywords=["prescribe", "diagnosis"],
                ),
            ],
            name="safety-rules",
        )

        # 2. Create governed agent
        def assistant(input: str) -> str:
            return f"I can help with: {input}"

        agent = GovernedAgent(
            assistant,
            constitution=constitution,
            agent_id="assistant-v1",
            strict=False,
        )

        # 3. Run safe actions
        r1 = agent.run("What is the weather?")
        assert r1 == "I can help with: What is the weather?"

        # 4. Run violating action (non-strict, so doesn't raise)
        r2 = agent.run("Should I invest in crypto?")
        assert r2 == "I can help with: Should I invest in crypto?"

        # 5. Check audit trail
        stats = agent.stats
        assert stats["total_validations"] >= 2
        assert stats["audit_chain_valid"]

        # 6. Verify some violations were recorded
        violations = agent.audit_log.query(valid=False)
        assert len(violations) > 0

    def test_maci_with_governed_agents(self):
        """MACI enforcement with multiple governed agents."""
        audit = AuditLog()
        maci = MACIEnforcer(audit_log=audit)

        # Assign roles
        maci.assign_role("proposer-1", MACIRole.PROPOSER)
        maci.assign_role("validator-1", MACIRole.VALIDATOR)
        maci.assign_role("executor-1", MACIRole.EXECUTOR)

        # Proposer can propose
        assert maci.check("proposer-1", "propose")

        # Validator can validate
        assert maci.check("validator-1", "validate")

        # Executor can execute
        assert maci.check("executor-1", "execute")

        # Cross-role violations blocked
        with pytest.raises(MACIViolationError):
            maci.check("proposer-1", "validate")

        with pytest.raises(MACIViolationError):
            maci.check("validator-1", "execute")

        # No self-validation
        with pytest.raises(MACIViolationError):
            maci.check_no_self_validation("agent-1", "agent-1")
