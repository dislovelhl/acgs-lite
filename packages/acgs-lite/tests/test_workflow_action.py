"""Tests for ViolationAction enum and workflow_action dispatch in GovernanceEngine.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import pytest

from acgs_lite import AuditLog, Constitution, GovernanceEngine, Rule, Severity, ViolationAction
from acgs_lite.errors import ConstitutionalViolationError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rule(
    rule_id: str,
    keywords: list[str],
    *,
    severity: Severity = Severity.HIGH,
    workflow_action: ViolationAction = ViolationAction.BLOCK,
) -> Rule:
    return Rule(
        id=rule_id,
        text=f"Rule {rule_id}",
        keywords=keywords,
        severity=severity,
        workflow_action=workflow_action,
    )


def _engine(rules: list[Rule], *, strict: bool = True) -> GovernanceEngine:
    return GovernanceEngine(Constitution.from_rules(rules), strict=strict)


def _engine_with_audit(rules: list[Rule], *, strict: bool = True) -> tuple[GovernanceEngine, AuditLog]:
    audit_log = AuditLog()
    return GovernanceEngine(Constitution.from_rules(rules), strict=strict, audit_log=audit_log), audit_log


# ---------------------------------------------------------------------------
# ViolationAction enum
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestViolationActionEnum:
    def test_values(self) -> None:
        assert ViolationAction.WARN.value == "warn"
        assert ViolationAction.BLOCK.value == "block"
        assert ViolationAction.BLOCK_AND_NOTIFY.value == "block_and_notify"
        assert ViolationAction.REQUIRE_HUMAN_REVIEW.value == "require_human_review"
        assert ViolationAction.ESCALATE.value == "escalate_to_senior"
        assert ViolationAction.HALT.value == "halt_and_alert"

    def test_str_enum_equality(self) -> None:
        """ViolationAction(str, Enum) compares equal to its string value."""
        assert ViolationAction.BLOCK == "block"
        assert ViolationAction.WARN == "warn"

    def test_default_is_block(self) -> None:
        rule = Rule(id="R1", text="test rule", keywords=["test"])
        assert rule.workflow_action == ViolationAction.BLOCK

    def test_backwards_compat_string_values(self) -> None:
        """Old string values are accepted by Pydantic (coerced to enum)."""
        r = Rule(id="R1", text="test", keywords=["t"], workflow_action="warn")
        assert r.workflow_action is ViolationAction.WARN
        r2 = Rule(id="R2", text="test", keywords=["t"], workflow_action="block_and_notify")
        assert r2.workflow_action is ViolationAction.BLOCK_AND_NOTIFY

    def test_empty_string_coerced_to_block(self) -> None:
        """Legacy empty-string default is coerced to BLOCK."""
        r = Rule(id="R1", text="test", keywords=["t"], workflow_action="")
        assert r.workflow_action is ViolationAction.BLOCK

    def test_invalid_value_raises(self) -> None:
        with pytest.raises(Exception):
            Rule(id="R1", text="test", keywords=["t"], workflow_action="bogus_action")


# ---------------------------------------------------------------------------
# WARN action — non-blocking
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestWarnAction:
    def test_warn_does_not_raise(self) -> None:
        """A WARN rule violation should not raise; it appears in result.warnings."""
        engine = _engine(
            [
                _rule(
                    "W1",
                    ["plaintext"],
                    severity=Severity.MEDIUM,
                    workflow_action=ViolationAction.WARN,
                )
            ],
            strict=True,
        )
        result = engine.validate("send data in plaintext format")
        assert result.valid is True
        assert result.violations == []
        assert len(result.warnings) == 1
        assert result.warnings[0].rule_id == "W1"
        assert result.action_taken == ViolationAction.WARN

    def test_warn_does_not_raise_strict_false(self) -> None:
        engine = _engine(
            [
                _rule(
                    "W1", ["plaintext"], severity=Severity.LOW, workflow_action=ViolationAction.WARN
                )
            ],
            strict=False,
        )
        result = engine.validate("send plaintext notice")
        assert result.valid is True
        assert len(result.warnings) == 1

    def test_warn_critical_severity_still_non_blocking(self) -> None:
        """Even CRITICAL severity is non-blocking when workflow_action=WARN."""
        engine = _engine(
            [
                _rule(
                    "W-CRIT",
                    ["plaintext"],
                    severity=Severity.CRITICAL,
                    workflow_action=ViolationAction.WARN,
                )
            ],
            strict=True,
        )
        result = engine.validate("send data in plaintext format")
        assert result.valid is True
        assert result.violations == []
        assert len(result.warnings) == 1


# ---------------------------------------------------------------------------
# BLOCK action — raises when strict=True
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBlockAction:
    def test_block_raises_when_strict(self) -> None:
        """A BLOCK rule violation raises ConstitutionalViolationError when strict=True."""
        engine = _engine(
            [
                _rule(
                    "B1",
                    ["plaintext"],
                    severity=Severity.HIGH,
                    workflow_action=ViolationAction.BLOCK,
                )
            ],
        )
        with pytest.raises(ConstitutionalViolationError) as exc:
            engine.validate("send data in plaintext format")
        assert exc.value.enforcement_action == ViolationAction.BLOCK

    def test_block_does_not_raise_when_not_strict(self) -> None:
        """When strict=False, BLOCK violations are recorded but don't raise."""
        engine = _engine(
            [
                _rule(
                    "B1",
                    ["plaintext"],
                    severity=Severity.HIGH,
                    workflow_action=ViolationAction.BLOCK,
                )
            ],
            strict=False,
        )
        result = engine.validate("send data in plaintext")
        assert result.valid is False
        assert result.action_taken == ViolationAction.BLOCK
        assert len(result.violations) == 1
        assert result.violations[0].rule_id == "B1"
        assert result.warnings == []


# ---------------------------------------------------------------------------
# HALT action — always raises regardless of strict
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHaltAction:
    def test_halt_always_raises_when_not_strict(self) -> None:
        """A HALT rule violation always raises, even when strict=False."""
        engine = _engine(
            [
                _rule(
                    "H1",
                    ["plaintext"],
                    severity=Severity.HIGH,
                    workflow_action=ViolationAction.HALT,
                )
            ],
            strict=False,
        )
        with pytest.raises(ConstitutionalViolationError) as exc:
            engine.validate("send data in plaintext format")
        assert exc.value.enforcement_action == ViolationAction.HALT

    def test_halt_raises_when_strict(self) -> None:
        """A HALT violation raises when strict=True as well."""
        engine = _engine(
            [
                _rule(
                    "H1",
                    ["plaintext"],
                    severity=Severity.HIGH,
                    workflow_action=ViolationAction.HALT,
                )
            ],
        )
        with pytest.raises(ConstitutionalViolationError) as exc:
            engine.validate("send data in plaintext format")
        assert exc.value.enforcement_action == ViolationAction.HALT


# ---------------------------------------------------------------------------
# Mixed WARN + BLOCK
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMixedActions:
    def test_warn_and_block_mixed_raises_on_block(self) -> None:
        """Mixed rules: WARN fires silently, BLOCK raises."""
        rules = [
            _rule(
                "W1", ["plaintext"], severity=Severity.MEDIUM, workflow_action=ViolationAction.WARN
            ),
            _rule(
                "B1", ["forbidden"], severity=Severity.HIGH, workflow_action=ViolationAction.BLOCK
            ),
        ]
        engine = _engine(rules)
        with pytest.raises(ConstitutionalViolationError) as exc:
            engine.validate("send plaintext and also forbidden content")
        assert exc.value.enforcement_action == ViolationAction.BLOCK

    def test_only_warn_fires_no_raise(self) -> None:
        """When only WARN rules fire, no exception raised."""
        rules = [
            _rule(
                "W1", ["plaintext"], severity=Severity.MEDIUM, workflow_action=ViolationAction.WARN
            ),
            _rule(
                "B1", ["forbidden"], severity=Severity.HIGH, workflow_action=ViolationAction.BLOCK
            ),
        ]
        engine = _engine(rules)
        result = engine.validate("send data in plaintext format")
        assert result.valid is True
        assert len(result.warnings) == 1
        assert result.violations == []

    def test_action_taken_when_only_warn(self) -> None:
        rules = [
            _rule("W1", ["plaintext"], severity=Severity.LOW, workflow_action=ViolationAction.WARN),
        ]
        engine = _engine(rules)
        result = engine.validate("send data in plaintext format")
        assert result.action_taken == ViolationAction.WARN

    def test_action_taken_none_when_no_violations(self) -> None:
        rules = [_rule("B1", ["forbidden"], workflow_action=ViolationAction.BLOCK)]
        engine = _engine(rules, strict=False)
        result = engine.validate("safe action here")
        assert result.action_taken is None


# ---------------------------------------------------------------------------
# BLOCK_AND_NOTIFY, REQUIRE_HUMAN_REVIEW, ESCALATE — all block
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBlockingVariants:
    def test_block_and_notify_creates_notification_artifact(self) -> None:
        engine = _engine(
            [
                _rule(
                    "BV1",
                    ["plaintext"],
                    severity=Severity.HIGH,
                    workflow_action=ViolationAction.BLOCK_AND_NOTIFY,
                )
            ],
            strict=False,
        )
        result = engine.validate("send data in plaintext format")
        assert result.valid is False
        assert result.action_taken == ViolationAction.BLOCK_AND_NOTIFY
        assert len(result.violations) == 1
        assert len(result.notifications) == 1
        assert result.notifications[0].rule_id == "BV1"
        assert result.review_requests == []
        assert result.escalations == []
        assert result.incident_alerts == []

    def test_require_human_review_creates_review_artifact(self) -> None:
        engine = _engine(
            [
                _rule(
                    "RV1",
                    ["plaintext"],
                    severity=Severity.HIGH,
                    workflow_action=ViolationAction.REQUIRE_HUMAN_REVIEW,
                )
            ],
            strict=False,
        )
        result = engine.validate("send data in plaintext format")
        assert result.valid is False
        assert result.action_taken == ViolationAction.REQUIRE_HUMAN_REVIEW
        assert len(result.review_requests) == 1
        assert result.review_requests[0].rule_id == "RV1"
        assert result.notifications == []
        assert result.escalations == []

    def test_escalate_creates_escalation_artifact(self) -> None:
        engine = _engine(
            [
                _rule(
                    "EV1",
                    ["plaintext"],
                    severity=Severity.HIGH,
                    workflow_action=ViolationAction.ESCALATE,
                )
            ],
            strict=False,
        )
        result = engine.validate("send data in plaintext format")
        assert result.valid is False
        assert result.action_taken == ViolationAction.ESCALATE
        assert len(result.escalations) == 1
        assert result.escalations[0].rule_id == "EV1"
        assert result.notifications == []
        assert result.review_requests == []

    def test_blocking_variants_raise_with_actual_enforcement_action(self) -> None:
        for action in (
            ViolationAction.BLOCK_AND_NOTIFY,
            ViolationAction.REQUIRE_HUMAN_REVIEW,
            ViolationAction.ESCALATE,
        ):
            engine, audit_log = _engine_with_audit(
                [_rule("BV1", ["plaintext"], severity=Severity.HIGH, workflow_action=action)],
            )
            with pytest.raises(ConstitutionalViolationError) as exc:
                engine.validate("send data in plaintext format")
            assert exc.value.enforcement_action == action
            assert len(audit_log.entries) == 1
            metadata = audit_log.entries[0].metadata["enforcement"]
            assert metadata["action_taken"] == action.value


# ---------------------------------------------------------------------------
# match_detail() serialisation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMatchDetail:
    def test_match_detail_workflow_action_is_string(self) -> None:
        """match_detail() returns workflow_action as a plain string value."""
        r = Rule(
            id="R1",
            text="advisory notice",
            keywords=["advisory"],
            workflow_action=ViolationAction.WARN,
        )
        detail = r.match_detail("handle advisory content carefully")
        assert detail["matched"] is True
        assert detail["workflow_action"] == "warn"
        assert isinstance(detail["workflow_action"], str)

    def test_match_detail_no_match_returns_value(self) -> None:
        r = Rule(
            id="R1",
            text="forbidden content",
            keywords=["forbidden"],
            workflow_action=ViolationAction.BLOCK,
        )
        detail = r.match_detail("safe action here")
        assert detail["matched"] is False
        assert detail["workflow_action"] == "block"


# ---------------------------------------------------------------------------
# Heuristic synthesis
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHeuristicSynthesis:
    def test_blocking_severity_gets_block_action(self) -> None:
        """_heuristic_rule_payload sets BLOCK for HIGH/CRITICAL rules."""
        r = Rule.from_description("must not expose credentials", rule_id="S1")
        assert r.workflow_action in (ViolationAction.BLOCK, ViolationAction.WARN)
        # Critical/blocking descriptions should get BLOCK
        r2 = Rule.from_description("block and prohibit any credential exposure", rule_id="S2")
        assert r2.workflow_action == ViolationAction.BLOCK

    def test_advisory_description_gets_warn_action(self) -> None:
        """_heuristic_rule_payload sets WARN for informational/advisory rules."""
        r = Rule.from_description("informational advisory about deployment practices", rule_id="S3")
        assert r.workflow_action == ViolationAction.WARN


# ---------------------------------------------------------------------------
# ConstitutionalViolationError
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestConstitutionalViolationErrorAction:
    def test_enforcement_action_default(self) -> None:
        err = ConstitutionalViolationError("test", rule_id="R1", severity="high")
        assert err.enforcement_action == ViolationAction.BLOCK

    def test_enforcement_action_halt(self) -> None:
        err = ConstitutionalViolationError(
            "test", rule_id="R1", severity="critical", enforcement_action=ViolationAction.HALT
        )
        assert err.enforcement_action == ViolationAction.HALT

    def test_halt_records_incident_artifact_before_raise(self) -> None:
        engine, audit_log = _engine_with_audit(
            [_rule("H1", ["plaintext"], severity=Severity.HIGH, workflow_action=ViolationAction.HALT)],
        )
        with pytest.raises(ConstitutionalViolationError) as exc:
            engine.validate("send data in plaintext format")
        assert exc.value.enforcement_action == ViolationAction.HALT
        assert len(audit_log.entries) == 1
        metadata = audit_log.entries[0].metadata["enforcement"]
        assert metadata["incident_triggered"] is True
        assert metadata["incident_alerts"][0]["rule_id"] == "H1"

    def test_action_string_field_preserved(self) -> None:
        """The existing 'action' str field is unchanged."""
        err = ConstitutionalViolationError(
            "test", rule_id="R1", severity="high", action="leak credentials"
        )
        assert err.action == "leak credentials"


# ---------------------------------------------------------------------------
# Export from top-level acgs / acgs_lite
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExports:
    def test_importable_from_acgs_lite(self) -> None:
        from acgs_lite import ViolationAction as VA  # noqa: PLC0415

        assert VA.BLOCK.value == "block"

    def test_importable_from_acgs(self) -> None:
        from acgs import ViolationAction as VA  # noqa: PLC0415

        assert VA.WARN.value == "warn"
