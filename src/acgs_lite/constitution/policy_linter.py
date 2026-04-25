"""Governance policy linter — static quality analysis of constitution rules.

Analyzes individual rules and entire constitutions for quality issues such as
overly broad or duplicated keywords, missing descriptions, conflicting severities,
redundant patterns, weak regex anchoring, and structural anti-patterns.

Produces structured lint reports with per-issue severity levels and actionable
fix suggestions. Suitable for CI/CD constitution validation gates, pre-commit
hooks, and governance health dashboards.

Zero hot-path overhead — linting runs offline, never on the critical evaluation path.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class LintSeverity(str, Enum):
    """Severity of a lint issue."""

    ERROR = "error"  # Must fix — breaks governance correctness
    WARNING = "warning"  # Should fix — degrades governance quality
    INFO = "info"  # Consider fixing — best-practice suggestion


class LintCode(str, Enum):
    """Catalogue of lint rule codes."""

    MISSING_DESCRIPTION = "G001"  # Rule has no description
    EMPTY_KEYWORDS = "G002"  # Rule has no keywords or patterns
    DUPLICATE_KEYWORD = "G003"  # Same keyword appears twice in one rule
    OVERLY_SHORT_KEYWORD = "G004"  # Keyword ≤ 2 chars (high false-positive risk)
    DUPLICATE_RULE_ID = "G005"  # Two rules share the same ID
    CONFLICTING_SEVERITY = "G006"  # Same keywords, different severities across rules
    WEAK_REGEX_PATTERN = "G007"  # Pattern has no anchors and is very short
    DUPLICATE_PATTERN = "G008"  # Identical pattern appears in multiple rules
    MISSING_CATEGORY = "G009"  # Rule has no category set
    UNREACHABLE_RULE = "G010"  # Rule is shadowed by a higher-priority identical rule
    KEYWORD_SUBSTRING_OVERLAP = "G011"  # One keyword is a substring of another in the same rule
    DESCRIPTION_TOO_SHORT = "G012"  # Description is fewer than 10 characters
    EXCESSIVE_KEYWORD_COUNT = "G013"  # Rule has > 50 keywords (maintenance risk)
    INVALID_SEVERITY = "G014"  # Severity value is not a recognised tier
    MISSING_WORKFLOW_ACTION = "G015"  # Rule has no workflow_action
    POSITIVE_DIRECTIVE_RISK = (
        "G016"  # Description uses positive directive framing ("ensure X", "always Y")
    )
    # instead of negative constraint framing ("block X", "deny Y").
    # Empirically, negative constraints have stronger governance effect
    # (ref: arXiv:2604.11088 — guardrails study on 25,532 agent rules).


_KNOWN_SEVERITIES = frozenset({"critical", "high", "medium", "low", "info"})
_KNOWN_ACTIONS = frozenset(
    {
        "allow",
        "deny",
        "block",
        "warn",
        "review",
        "flag",
        "monitor",
        "escalate",
        "quarantine",
        "reject",
    }
)


@dataclass
class LintIssue:
    """A single lint finding on a rule or constitution."""

    code: LintCode
    severity: LintSeverity
    rule_id: str | None
    message: str
    suggestion: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
            "severity": self.severity.value,
            "rule_id": self.rule_id,
            "message": self.message,
            "suggestion": self.suggestion,
        }


@dataclass
class LintReport:
    """Aggregated lint results for a constitution or rule set."""

    issues: list[LintIssue] = field(default_factory=list)
    rules_checked: int = 0

    @property
    def errors(self) -> list[LintIssue]:
        return [i for i in self.issues if i.severity == LintSeverity.ERROR]

    @property
    def warnings(self) -> list[LintIssue]:
        return [i for i in self.issues if i.severity == LintSeverity.WARNING]

    @property
    def infos(self) -> list[LintIssue]:
        return [i for i in self.issues if i.severity == LintSeverity.INFO]

    @property
    def passed(self) -> bool:
        """Return True if there are no ERROR-level issues."""
        return not self.errors

    def summary(self) -> str:
        return (
            f"{self.rules_checked} rules checked — "
            f"{len(self.errors)} errors, {len(self.warnings)} warnings, "
            f"{len(self.infos)} info"
        )

    def by_rule(self) -> dict[str | None, list[LintIssue]]:
        """Group issues by rule_id."""
        result: dict[str | None, list[LintIssue]] = {}
        for issue in self.issues:
            result.setdefault(issue.rule_id, []).append(issue)
        return result

    def filter(
        self,
        *,
        severity: LintSeverity | None = None,
        code: LintCode | None = None,
        rule_id: str | None = None,
    ) -> list[LintIssue]:
        """Return issues matching all provided filters."""
        results = self.issues
        if severity is not None:
            results = [i for i in results if i.severity == severity]
        if code is not None:
            results = [i for i in results if i.code == code]
        if rule_id is not None:
            results = [i for i in results if i.rule_id == rule_id]
        return results

    def to_dict(self) -> dict[str, Any]:
        return {
            "rules_checked": self.rules_checked,
            "passed": self.passed,
            "summary": self.summary(),
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "info_count": len(self.infos),
            "issues": [i.to_dict() for i in self.issues],
        }

    def to_text(self) -> str:
        """Render as human-readable text."""
        lines: list[str] = [f"Lint Report: {self.summary()}", ""]
        for issue in sorted(self.issues, key=lambda i: (i.severity.value, str(i.rule_id))):
            rid = f"[{issue.rule_id}] " if issue.rule_id else ""
            lines.append(
                f"  {issue.severity.value.upper()} {issue.code.value}: {rid}{issue.message}"
            )
            if issue.suggestion:
                lines.append(f"    → {issue.suggestion}")
        return "\n".join(lines)


class PolicyLinter:
    """Static quality analyser for governance constitution rules.

    Accepts rule data as plain dicts (compatible with the Constitution's
    internal rule representation) or any object with the expected attributes.
    Returns a :class:`LintReport` with categorised issues and fix suggestions.

    Example usage::

        linter = PolicyLinter()

        rules = [
            {"id": "pii-block", "description": "Block PII", "severity": "critical",
             "keywords": ["ssn", "cc"], "category": "privacy", "workflow_action": "block"},
            {"id": "pii-block", "description": "Duplicate!", "severity": "high",
             "keywords": ["ssn"], "category": "privacy", "workflow_action": "warn"},
        ]

        report = linter.lint_rules(rules)
        print(report.summary())
        print(report.to_text())

        # Or lint a Constitution object directly:
        # report = linter.lint_constitution(constitution)
    """

    def __init__(
        self,
        *,
        max_keyword_length_for_short_check: int = 2,
        max_keywords_per_rule: int = 50,
        min_description_length: int = 10,
        short_pattern_length: int = 4,
    ) -> None:
        self._max_kw_short = max_keyword_length_for_short_check
        self._max_kw_count = max_keywords_per_rule
        self._min_desc_len = min_description_length
        self._short_pat_len = short_pattern_length

    def lint_rules(self, rules: list[dict[str, Any]]) -> LintReport:
        """Lint a list of rule dicts.

        Each dict should have keys: ``id``, ``description``, ``severity``,
        ``keywords``, ``patterns``, ``category``, ``workflow_action``.
        Missing keys are treated as empty/absent (generating appropriate issues).

        Returns:
            A :class:`LintReport` with all findings.
        """
        report = LintReport(rules_checked=len(rules))

        self._check_cross_rule(rules, report)

        for rule in rules:
            self._check_single_rule(rule, report)

        return report

    def lint_constitution(self, constitution: Any) -> LintReport:
        """Lint a :class:`Constitution` object by extracting its rules.

        Calls ``constitution.rules`` (list) or ``constitution.active_rules``
        and normalises each rule to a dict before linting.

        Returns:
            A :class:`LintReport` with all findings.
        """
        raw_rules = getattr(constitution, "rules", None) or getattr(
            constitution, "active_rules", []
        )
        dicts: list[dict[str, Any]] = []
        for r in raw_rules:
            if isinstance(r, dict):
                dicts.append(r)
            else:
                dicts.append(self._rule_to_dict(r))
        return self.lint_rules(dicts)

    def lint_rule(self, rule: dict[str, Any]) -> LintReport:
        """Lint a single rule dict in isolation."""
        report = LintReport(rules_checked=1)
        self._check_single_rule(rule, report)
        return report

    # ------------------------------------------------------------------
    # Single-rule checks
    # ------------------------------------------------------------------

    def _check_single_rule(self, rule: dict[str, Any], report: LintReport) -> None:
        rule_id: str | None = rule.get("id") or rule.get("rule_id") or None

        description = str(rule.get("description", "")).strip()
        severity = str(rule.get("severity", "")).strip().lower()
        category = str(rule.get("category", "")).strip()
        action = str(rule.get("workflow_action", "")).strip().lower()
        keywords: list[str] = list(rule.get("keywords", []))
        patterns: list[str] = list(rule.get("patterns", []))

        if not description:
            report.issues.append(
                LintIssue(
                    code=LintCode.MISSING_DESCRIPTION,
                    severity=LintSeverity.WARNING,
                    rule_id=rule_id,
                    message="Rule has no description.",
                    suggestion="Add a concise description explaining what this rule governs.",
                )
            )
        elif len(description) < self._min_desc_len:
            report.issues.append(
                LintIssue(
                    code=LintCode.DESCRIPTION_TOO_SHORT,
                    severity=LintSeverity.INFO,
                    rule_id=rule_id,
                    message=f"Description is very short ({len(description)} chars).",
                    suggestion="Expand the description to at least 10 characters.",
                )
            )

        if not keywords and not patterns:
            report.issues.append(
                LintIssue(
                    code=LintCode.EMPTY_KEYWORDS,
                    severity=LintSeverity.ERROR,
                    rule_id=rule_id,
                    message="Rule has no keywords or patterns — it can never fire.",
                    suggestion="Add at least one keyword or regex pattern.",
                )
            )

        if not category:
            report.issues.append(
                LintIssue(
                    code=LintCode.MISSING_CATEGORY,
                    severity=LintSeverity.INFO,
                    rule_id=rule_id,
                    message="Rule has no category.",
                    suggestion="Set a category (e.g. 'privacy', 'security', 'compliance').",
                )
            )

        if severity and severity not in _KNOWN_SEVERITIES:
            report.issues.append(
                LintIssue(
                    code=LintCode.INVALID_SEVERITY,
                    severity=LintSeverity.ERROR,
                    rule_id=rule_id,
                    message=f"Unknown severity '{severity}'.",
                    suggestion=f"Use one of: {', '.join(sorted(_KNOWN_SEVERITIES))}.",
                )
            )

        if not action:
            report.issues.append(
                LintIssue(
                    code=LintCode.MISSING_WORKFLOW_ACTION,
                    severity=LintSeverity.WARNING,
                    rule_id=rule_id,
                    message="Rule has no workflow_action.",
                    suggestion=(
                        f"Set workflow_action to one of: {', '.join(sorted(_KNOWN_ACTIONS))}."
                    ),
                )
            )

        # G016 — Positive directive framing check.
        # Research finding (arXiv:2604.11088): in a study of 25,532 agent rules across 5,000+ runs,
        # positive directives ("ensure X", "always do Y") actively hurt performance, while negative
        # constraints ("block X", "do not Y") were the only individually beneficial rule type.
        # Warn when description leads with imperative-positive phrasing rather than constraint phrasing.
        _POSITIVE_DIRECTIVE_MARKERS = (
            "ensure ",
            "always ",
            "must ",
            "make sure",
            "require that",
            "guarantee ",
            "enforce that",
            "confirm ",
            "verify that",
            "maintain ",
            "follow ",
            "use ",
            "provide ",
            "generate ",
            "produce ",
            "allow only",
        )
        _NEGATIVE_CONSTRAINT_MARKERS = (
            "block",
            "deny",
            "prevent",
            "prohibit",
            "reject",
            "refuse",
            "do not",
            "don't",
            "never ",
            "no ",
            "stop ",
            "restrict ",
            "forbid",
            "disallow",
            "ban ",
            "halt ",
            "abort ",
            "exclude ",
            "must not",
        )
        if description:
            desc_lower = description.lower()
            is_positive = any(
                desc_lower.startswith(m) or f" {m}" in desc_lower
                for m in _POSITIVE_DIRECTIVE_MARKERS
            )
            is_negative = any(m in desc_lower for m in _NEGATIVE_CONSTRAINT_MARKERS)
            if is_positive and not is_negative:
                report.issues.append(
                    LintIssue(
                        code=LintCode.POSITIVE_DIRECTIVE_RISK,
                        severity=LintSeverity.INFO,
                        rule_id=rule_id,
                        message=(
                            "Rule description uses positive directive framing "
                            f"(e.g. starts with '{description.split()[0].lower()} ...'). "
                            "Negative constraints outperform positive directives in governance "
                            "effectiveness (arXiv:2604.11088)."
                        ),
                        suggestion=(
                            "Reframe as a negative constraint: e.g. 'Block requests that ...' "
                            "or 'Deny access when ...' instead of 'Ensure that ...'."
                        ),
                    )
                )

        if len(keywords) > self._max_kw_count:
            report.issues.append(
                LintIssue(
                    code=LintCode.EXCESSIVE_KEYWORD_COUNT,
                    severity=LintSeverity.WARNING,
                    rule_id=rule_id,
                    message=(
                        f"Rule has {len(keywords)} keywords (>{self._max_kw_count})"
                        " — maintenance risk."
                    ),
                    suggestion="Split into focused sub-rules or use regex patterns instead.",
                )
            )

        seen_kws: set[str] = set()
        for kw in keywords:
            kw_lower = kw.lower().strip()
            if kw_lower in seen_kws:
                report.issues.append(
                    LintIssue(
                        code=LintCode.DUPLICATE_KEYWORD,
                        severity=LintSeverity.WARNING,
                        rule_id=rule_id,
                        message=f"Keyword '{kw}' appears more than once.",
                        suggestion="Remove the duplicate keyword.",
                    )
                )
            seen_kws.add(kw_lower)

            if len(kw_lower) <= self._max_kw_short:
                report.issues.append(
                    LintIssue(
                        code=LintCode.OVERLY_SHORT_KEYWORD,
                        severity=LintSeverity.WARNING,
                        rule_id=rule_id,
                        message=(
                            f"Keyword '{kw}' is very short ({len(kw_lower)} chars)"
                            " — high false-positive risk."
                        ),
                        suggestion="Use longer, more specific keywords or a regex pattern.",
                    )
                )

        self._check_keyword_substring_overlap(keywords, rule_id, report)

        for pattern in patterns:
            self._check_pattern_quality(pattern, rule_id, report)

    def _check_keyword_substring_overlap(
        self, keywords: list[str], rule_id: str | None, report: LintReport
    ) -> None:
        lowered = [k.lower().strip() for k in keywords]
        for i, kw_a in enumerate(lowered):
            for j, kw_b in enumerate(lowered):
                if i != j and kw_a and kw_b and kw_a in kw_b and kw_a != kw_b:
                    report.issues.append(
                        LintIssue(
                            code=LintCode.KEYWORD_SUBSTRING_OVERLAP,
                            severity=LintSeverity.INFO,
                            rule_id=rule_id,
                            message=(
                                f"Keyword '{kw_a}' is a substring of '{kw_b}'"
                                f" — '{kw_b}' is redundant."
                            ),
                            suggestion=f"Remove '{kw_b}' since '{kw_a}' already covers it.",
                        )
                    )
                    break  # one report per pair is enough

    def _check_pattern_quality(self, pattern: str, rule_id: str | None, report: LintReport) -> None:
        if (
            len(pattern) < self._short_pat_len
            and not pattern.startswith("^")
            and not pattern.endswith("$")
        ):
            try:
                re.compile(pattern)
            except re.error:
                return
            report.issues.append(
                LintIssue(
                    code=LintCode.WEAK_REGEX_PATTERN,
                    severity=LintSeverity.WARNING,
                    rule_id=rule_id,
                    message=(
                        f"Pattern '{pattern}' is very short and unanchored"
                        " — high false-positive risk."
                    ),
                    suggestion="Add anchors (^ / $) or use a longer, more specific pattern.",
                )
            )

    # ------------------------------------------------------------------
    # Cross-rule checks
    # ------------------------------------------------------------------

    def _check_cross_rule(self, rules: list[dict[str, Any]], report: LintReport) -> None:
        seen_ids: dict[str, int] = {}
        keyword_severity_map: dict[str, tuple[str, str]] = {}
        seen_patterns: dict[str, str] = {}

        for rule in rules:
            rule_id: str | None = rule.get("id") or rule.get("rule_id") or None
            severity = str(rule.get("severity", "")).strip().lower()
            keywords: list[str] = [k.lower().strip() for k in rule.get("keywords", [])]
            patterns: list[str] = list(rule.get("patterns", []))

            if rule_id:
                if rule_id in seen_ids:
                    report.issues.append(
                        LintIssue(
                            code=LintCode.DUPLICATE_RULE_ID,
                            severity=LintSeverity.ERROR,
                            rule_id=rule_id,
                            message=f"Rule ID '{rule_id}' appears more than once.",
                            suggestion="Assign unique IDs to every rule.",
                        )
                    )
                else:
                    seen_ids[rule_id] = 1

            for kw in keywords:
                if kw in keyword_severity_map:
                    existing_sev, existing_id = keyword_severity_map[kw]
                    if existing_sev != severity:
                        report.issues.append(
                            LintIssue(
                                code=LintCode.CONFLICTING_SEVERITY,
                                severity=LintSeverity.WARNING,
                                rule_id=rule_id,
                                message=(
                                    f"Keyword '{kw}' has severity '{severity}' here but "
                                    f"'{existing_sev}' in rule '{existing_id}'."
                                ),
                                suggestion="Reconcile severity levels for shared keywords.",
                            )
                        )
                else:
                    keyword_severity_map[kw] = (severity, str(rule_id))

            for pattern in patterns:
                if pattern in seen_patterns:
                    report.issues.append(
                        LintIssue(
                            code=LintCode.DUPLICATE_PATTERN,
                            severity=LintSeverity.WARNING,
                            rule_id=rule_id,
                            message=(
                                f"Pattern '{pattern}' also appears"
                                f" in rule '{seen_patterns[pattern]}'."
                            ),
                            suggestion="Consolidate duplicate patterns into a single rule.",
                        )
                    )
                else:
                    seen_patterns[pattern] = str(rule_id)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _rule_to_dict(rule: Any) -> dict[str, Any]:
        sev = getattr(rule, "severity", "")
        # Handle enum severity (e.g. Severity.CRITICAL → "critical")
        if hasattr(sev, "name"):
            sev = sev.name
        elif hasattr(sev, "value"):
            sev = sev.value
        return {
            "id": getattr(rule, "id", getattr(rule, "rule_id", None)),
            "description": getattr(rule, "description", ""),
            "severity": sev,
            "category": getattr(rule, "category", ""),
            "workflow_action": getattr(rule, "workflow_action", ""),
            "keywords": list(getattr(rule, "keywords", []) or []),
            "patterns": list(getattr(rule, "patterns", []) or []),
        }
