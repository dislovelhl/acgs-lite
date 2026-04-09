"""Tests for constitution diffing and amendment review artifacts."""

from __future__ import annotations

from acgs_lite import Constitution, Rule, Severity, ViolationAction
from acgs_lite.constitution.diffing import compare_constitutions
from acgs_lite.constitution.merging import apply_amendments_with_report


def _rule(
    rule_id: str,
    *,
    text: str = "base text",
    severity: Severity = Severity.HIGH,
    workflow_action: ViolationAction = ViolationAction.BLOCK,
    keywords: list[str] | None = None,
) -> Rule:
    return Rule(
        id=rule_id,
        text=text,
        severity=severity,
        workflow_action=workflow_action,
        keywords=keywords or ["base"],
    )


def _constitution(*rules: Rule) -> Constitution:
    return Constitution.from_rules(list(rules), name="diff-test")


def test_compare_reports_added_rule() -> None:
    before = _constitution(_rule("R1"))
    after = _constitution(_rule("R1"), _rule("R2", text="new"))

    result = before.compare(after)

    assert result["added"] == ["R2"]
    assert result["added_rules"][0]["after"]["id"] == "R2"


def test_compare_reports_removed_rule() -> None:
    before = _constitution(_rule("R1"), _rule("R2"))
    after = _constitution(_rule("R1"))

    result = before.compare(after)

    assert result["removed"] == ["R2"]
    assert result["removed_rules"][0]["before"]["id"] == "R2"


def test_compare_reports_text_field_change() -> None:
    before = _constitution(_rule("R1", text="before"))
    after = _constitution(_rule("R1", text="after"))

    result = before.compare(after)

    assert result["modified"][0]["field_changes"]["text"]["before"] == "before"
    assert result["modified"][0]["field_changes"]["text"]["after"] == "after"


def test_compare_reports_severity_field_change() -> None:
    before = _constitution(_rule("R1", severity=Severity.LOW))
    after = _constitution(_rule("R1", severity=Severity.CRITICAL))

    result = before.compare(after)

    assert result["modified"][0]["field_changes"]["severity"] == {
        "before": "low",
        "after": "critical",
    }


def test_compare_reports_workflow_action_field_change() -> None:
    before = _constitution(_rule("R1", workflow_action=ViolationAction.BLOCK))
    after = _constitution(_rule("R1", workflow_action=ViolationAction.REQUIRE_HUMAN_REVIEW))

    result = before.compare(after)

    assert result["modified"][0]["field_changes"]["workflow_action"] == {
        "before": "block",
        "after": "require_human_review",
    }


def test_compare_exposes_pre_and_post_hashes_and_lineage() -> None:
    before = _constitution(_rule("R1"))
    after = _constitution(_rule("R1", text="changed"))

    result = Constitution.compare(before, after)

    assert result["before_hash"] == before.hash
    assert result["after_hash"] == after.hash
    assert result["lineage"]["hash_transition"] == [before.hash, after.hash]


def test_diff_summary_returns_human_readable_summary() -> None:
    before = _constitution(_rule("R1"))
    after = _constitution(_rule("R1"), _rule("R2"))

    summary = before.diff_summary(after)

    assert "added" in summary


def test_constitution_compare_returns_dict() -> None:
    before = _constitution(_rule("R1"))
    after = _constitution(_rule("R1", text="changed"))

    result = Constitution.compare(before, after)

    assert isinstance(result, dict)


def test_constitution_diff_summary_returns_string() -> None:
    before = _constitution(_rule("R1"))
    after = _constitution(_rule("R1", text="changed"))

    summary = before.diff_summary(after)

    assert isinstance(summary, str)
    assert len(summary) > 0


def test_compare_constitutions_returns_structured_diff_object() -> None:
    before = _constitution(_rule("R1"))
    after = _constitution(_rule("R1", text="changed"))

    diff = compare_constitutions(before, after)

    assert diff.before_hash == before.hash
    assert diff.after_hash == after.hash
    assert diff.modified_rules[0].field_changes["text"]["after"] == "changed"


def test_apply_amendments_with_report_returns_diff_and_metadata() -> None:
    before = _constitution(_rule("R1"))
    amendment = {
        "amendment_type": "modify_workflow",
        "title": "Route to review",
        "changes": {
            "rule_id": "R1",
            "workflow_action": "require_human_review",
        },
    }

    after, report = apply_amendments_with_report(before, [amendment])

    assert after.get_rule("R1").workflow_action == ViolationAction.REQUIRE_HUMAN_REVIEW
    artifact = report.to_dict()
    assert artifact["before_hash"] == before.hash
    assert artifact["after_hash"] == after.hash
    assert artifact["amendment_metadata"][0]["title"] == "Route to review"
    assert artifact["diff"]["modified"][0]["field_changes"]["workflow_action"]["after"] == (
        "require_human_review"
    )
