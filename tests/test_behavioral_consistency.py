from __future__ import annotations

from acgs_lite.constitution import Constitution
from acgs_lite.constitution.policy_linter import LintCode, PolicyLinter
from acgs_lite.constitution.testing import BehavioralConsistencyAuditor, BehavioralConsistencyCase
from acgs_lite.engine.core import GovernanceEngine


def test_behavioral_consistency_auditor_reports_matching_rule_behavior() -> None:
    engine = GovernanceEngine(Constitution.from_template("gitlab"), strict=False)
    auditor = BehavioralConsistencyAuditor(
        cases=[
            BehavioralConsistencyCase(
                rule_id="GL-005",
                should_block=("disable governance in ci pipeline execution",),
                should_allow=("run pipeline with governance validation enabled",),
                description="CI/CD governance bypass rule should block bypass language but allow compliant pipeline runs",
            )
        ]
    )

    report = auditor.audit(engine)

    assert report.total_cases == 1
    assert report.failed_cases == 0
    assert report.pass_rate == 1.0


def test_behavioral_consistency_auditor_detects_mismatches() -> None:
    engine = GovernanceEngine(Constitution.from_template("gitlab"), strict=False)
    auditor = BehavioralConsistencyAuditor(
        cases=[
            BehavioralConsistencyCase(
                rule_id="GL-005",
                should_block=("run pipeline with governance validation enabled",),
                should_allow=(),
                description="Intentional mismatch to prove the auditor catches inconsistencies",
            )
        ]
    )

    report = auditor.audit(engine)

    assert report.total_cases == 1
    assert report.failed_cases == 1
    assert report.findings
    assert report.findings[0].rule_id == "GL-005"


def test_builtin_templates_avoid_positive_directive_framing() -> None:
    linter = PolicyLinter()
    for domain in ["gitlab", "healthcare", "finance", "security", "general"]:
        constitution = Constitution.from_template(domain)
        report = linter.lint_constitution(constitution)
        codes = {issue.code for issue in report.issues}
        assert LintCode.POSITIVE_DIRECTIVE_RISK not in codes, domain
