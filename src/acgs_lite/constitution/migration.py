"""exp194: PolicyVersionMigrator — automated constitution version migration.

Provides safe schema evolution across constitution versions with rule mapping,
deprecation handling, severity migration, rollback support, and full audit trail.
Zero hot-path overhead (offline tooling only).
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class MigrationStatus(Enum):
    """Status of a migration operation."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


class RuleAction(Enum):
    """Action to take on a rule during migration."""

    KEEP = "keep"
    RENAME = "rename"
    MERGE = "merge"
    SPLIT = "split"
    DEPRECATE = "deprecate"
    REMOVE = "remove"
    TRANSFORM = "transform"


@dataclass
class RuleMigrationStep:
    """A single rule migration instruction."""

    source_rule_id: str
    action: RuleAction
    target_rule_id: str | None = None
    target_rule_ids: list[str] | None = None
    merge_sources: list[str] | None = None
    severity_change: str | None = None
    keyword_changes: dict[str, list[str]] | None = None
    reason: str = ""

    def describe(self) -> str:
        """Human-readable description of this step."""
        if self.action == RuleAction.KEEP:
            return f"Keep {self.source_rule_id} unchanged"
        if self.action == RuleAction.RENAME:
            return f"Rename {self.source_rule_id} → {self.target_rule_id}"
        if self.action == RuleAction.MERGE:
            srcs = ", ".join(self.merge_sources or [])
            return f"Merge [{srcs}] → {self.target_rule_id}"
        if self.action == RuleAction.SPLIT:
            tgts = ", ".join(self.target_rule_ids or [])
            return f"Split {self.source_rule_id} → [{tgts}]"
        if self.action == RuleAction.DEPRECATE:
            repl = f" (replaced by {self.target_rule_id})" if self.target_rule_id else ""
            return f"Deprecate {self.source_rule_id}{repl}"
        if self.action == RuleAction.REMOVE:
            return f"Remove {self.source_rule_id}: {self.reason}"
        if self.action == RuleAction.TRANSFORM:
            parts = [f"Transform {self.source_rule_id}"]
            if self.severity_change:
                parts.append(f"severity→{self.severity_change}")
            if self.keyword_changes:
                parts.append(f"keywords:{self.keyword_changes}")
            return " ".join(parts)
        return f"{self.action.value} {self.source_rule_id}"


@dataclass
class MigrationPlan:
    """A complete migration plan between two constitution versions."""

    source_version: str
    target_version: str
    steps: list[RuleMigrationStep] = field(default_factory=list)
    description: str = ""
    created_at: float = field(default_factory=time.time)
    pre_checks: list[Callable[..., bool]] = field(default_factory=list)

    def add_step(self, step: RuleMigrationStep) -> MigrationPlan:
        """Fluent API: add a migration step."""
        self.steps.append(step)
        return self

    def keep(self, rule_id: str) -> MigrationPlan:
        """Keep a rule unchanged."""
        return self.add_step(RuleMigrationStep(rule_id, RuleAction.KEEP))

    def rename(self, old_id: str, new_id: str, reason: str = "") -> MigrationPlan:
        """Rename a rule ID."""
        return self.add_step(
            RuleMigrationStep(old_id, RuleAction.RENAME, target_rule_id=new_id, reason=reason)
        )

    def merge(self, source_ids: list[str], target_id: str, reason: str = "") -> MigrationPlan:
        """Merge multiple rules into one."""
        return self.add_step(
            RuleMigrationStep(
                source_ids[0],
                RuleAction.MERGE,
                target_rule_id=target_id,
                merge_sources=source_ids,
                reason=reason,
            )
        )

    def split(self, source_id: str, target_ids: list[str], reason: str = "") -> MigrationPlan:
        """Split one rule into multiple."""
        return self.add_step(
            RuleMigrationStep(
                source_id,
                RuleAction.SPLIT,
                target_rule_ids=target_ids,
                reason=reason,
            )
        )

    def deprecate(
        self, rule_id: str, replaced_by: str | None = None, reason: str = ""
    ) -> MigrationPlan:
        """Deprecate a rule, optionally pointing to replacement."""
        return self.add_step(
            RuleMigrationStep(
                rule_id, RuleAction.DEPRECATE, target_rule_id=replaced_by, reason=reason
            )
        )

    def remove(self, rule_id: str, reason: str = "") -> MigrationPlan:
        """Remove a rule entirely."""
        return self.add_step(RuleMigrationStep(rule_id, RuleAction.REMOVE, reason=reason))

    def transform(
        self,
        rule_id: str,
        *,
        severity: str | None = None,
        add_keywords: list[str] | None = None,
        remove_keywords: list[str] | None = None,
        reason: str = "",
    ) -> MigrationPlan:
        """Transform rule properties (severity, keywords)."""
        kw_changes: dict[str, list[str]] | None = None
        if add_keywords or remove_keywords:
            kw_changes = {}
            if add_keywords:
                kw_changes["add"] = add_keywords
            if remove_keywords:
                kw_changes["remove"] = remove_keywords
        return self.add_step(
            RuleMigrationStep(
                rule_id,
                RuleAction.TRANSFORM,
                severity_change=severity,
                keyword_changes=kw_changes,
                reason=reason,
            )
        )

    def add_pre_check(self, check: Callable[..., bool]) -> MigrationPlan:
        """Add a pre-migration validation check."""
        self.pre_checks.append(check)
        return self

    def summary(self) -> dict[str, Any]:
        """Summary of migration plan."""
        action_counts: dict[str, int] = {}
        for step in self.steps:
            key = step.action.value
            action_counts[key] = action_counts.get(key, 0) + 1
        return {
            "source_version": self.source_version,
            "target_version": self.target_version,
            "total_steps": len(self.steps),
            "action_counts": action_counts,
            "description": self.description,
            "steps": [step.describe() for step in self.steps],
        }

    def integrity_hash(self) -> str:
        """Deterministic hash of the plan for tamper detection."""
        parts = [self.source_version, self.target_version]
        for step in self.steps:
            parts.append(f"{step.action.value}:{step.source_rule_id}:{step.target_rule_id}")
        raw = "|".join(parts)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass
class MigrationResult:
    """Result of executing a migration plan."""

    status: MigrationStatus
    plan: MigrationPlan
    applied_steps: list[dict[str, Any]] = field(default_factory=list)
    skipped_steps: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    started_at: float = 0.0
    completed_at: float = 0.0
    rollback_snapshot: dict[str, Any] | None = None

    @property
    def duration_ms(self) -> float:
        if self.completed_at and self.started_at:
            return (self.completed_at - self.started_at) * 1000
        return 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "source_version": self.plan.source_version,
            "target_version": self.plan.target_version,
            "applied": len(self.applied_steps),
            "skipped": len(self.skipped_steps),
            "errors": self.errors,
            "duration_ms": round(self.duration_ms, 3),
            "plan_hash": self.plan.integrity_hash(),
        }


class PolicyVersionMigrator:
    """Automated constitution version migration engine.

    Executes migration plans with pre-checks, step-by-step application,
    rollback support, and full audit trail. Supports rule rename, merge,
    split, deprecate, remove, and property transform operations.

    Example::

        migrator = PolicyVersionMigrator()

        plan = (
            MigrationPlan("1.0", "2.0", description="Q2 policy refresh")
            .rename("OLD-001", "SAFE-001", reason="Standardize prefix")
            .transform("SAFE-002", severity="critical", add_keywords=["prompt injection"])
            .deprecate("LEGACY-003", replaced_by="SAFE-004")
            .remove("TEMP-099", reason="Temporary rule expired")
        )

        result = migrator.execute(plan, constitution)

        if result.status == MigrationStatus.COMPLETED:
            print(f"Migrated {len(result.applied_steps)} rules")
        else:
            migrator.rollback(result)
    """

    def __init__(self) -> None:
        self._history: list[MigrationResult] = []

    def validate_plan(self, plan: MigrationPlan, constitution: Any) -> list[str]:
        """Validate a migration plan against a constitution without executing.

        Returns list of validation errors (empty = valid).
        """
        errors: list[str] = []
        rule_ids = {r.id for r in getattr(constitution, "rules", [])}

        seen_sources: set[str] = set()
        for step in plan.steps:
            if step.action != RuleAction.MERGE and step.source_rule_id not in rule_ids:
                errors.append(f"Source rule '{step.source_rule_id}' not found in constitution")

            if step.source_rule_id in seen_sources and step.action != RuleAction.MERGE:
                errors.append(f"Duplicate migration for rule '{step.source_rule_id}'")
            seen_sources.add(step.source_rule_id)

            if step.action == RuleAction.RENAME and step.target_rule_id in rule_ids:
                errors.append(f"Rename target '{step.target_rule_id}' already exists")

            if step.action == RuleAction.MERGE and step.merge_sources:
                for src in step.merge_sources:
                    if src not in rule_ids:
                        errors.append(f"Merge source '{src}' not found")

            if step.action == RuleAction.SPLIT and not step.target_rule_ids:
                errors.append(f"Split of '{step.source_rule_id}' has no target IDs")

        for check in plan.pre_checks:
            try:
                if not check(constitution):
                    errors.append(f"Pre-check failed: {getattr(check, '__name__', 'anonymous')}")
            except Exception as exc:
                errors.append(f"Pre-check error: {exc}")

        return errors

    def dry_run(self, plan: MigrationPlan, constitution: Any) -> MigrationResult:
        """Simulate migration without applying changes."""
        errors = self.validate_plan(plan, constitution)
        if errors:
            return MigrationResult(
                status=MigrationStatus.FAILED,
                plan=plan,
                errors=errors,
            )

        simulated: list[dict[str, Any]] = []
        for step in plan.steps:
            simulated.append(
                {
                    "action": step.action.value,
                    "rule_id": step.source_rule_id,
                    "description": step.describe(),
                    "simulated": True,
                }
            )

        return MigrationResult(
            status=MigrationStatus.COMPLETED,
            plan=plan,
            applied_steps=simulated,
        )

    def execute(self, plan: MigrationPlan, constitution: Any) -> MigrationResult:
        """Execute a migration plan against a constitution.

        Creates a rollback snapshot before applying changes. Each step
        is applied atomically — if any step fails, prior steps remain
        applied but the result records the failure point.
        """
        result = MigrationResult(
            status=MigrationStatus.IN_PROGRESS,
            plan=plan,
            started_at=time.time(),
        )

        errors = self.validate_plan(plan, constitution)
        if errors:
            result.status = MigrationStatus.FAILED
            result.errors = errors
            result.completed_at = time.time()
            self._history.append(result)
            return result

        result.rollback_snapshot = self._capture_snapshot(constitution)

        for step in plan.steps:
            try:
                applied = self._apply_step(step, constitution)
                if applied:
                    result.applied_steps.append(
                        {
                            "action": step.action.value,
                            "rule_id": step.source_rule_id,
                            "description": step.describe(),
                        }
                    )
                else:
                    result.skipped_steps.append(
                        {
                            "action": step.action.value,
                            "rule_id": step.source_rule_id,
                            "reason": "No matching rule or no-op",
                        }
                    )
            except Exception as exc:
                result.errors.append(f"Step failed ({step.describe()}): {exc}")
                result.status = MigrationStatus.FAILED
                result.completed_at = time.time()
                self._history.append(result)
                return result

        result.status = MigrationStatus.COMPLETED
        result.completed_at = time.time()
        self._history.append(result)
        return result

    def rollback(self, result: MigrationResult, constitution: Any) -> bool:
        """Rollback a migration using the stored snapshot.

        Returns True if rollback succeeded.
        """
        if not result.rollback_snapshot:
            return False

        snapshot = result.rollback_snapshot
        rules_data = snapshot.get("rules", [])

        if hasattr(constitution, "rules"):
            constitution.rules.clear()
            for rule_data in rules_data:
                try:
                    from .core import Rule, Severity

                    rule = Rule(
                        id=rule_data["id"],
                        text=rule_data["text"],
                        severity=Severity(rule_data["severity"]),
                        keywords=rule_data.get("keywords", []),
                        patterns=rule_data.get("patterns", []),
                    )
                    constitution.rules.append(rule)
                except Exception as exc:
                    logger.warning(
                        "failed to restore migrated rule %r during rollback: %s",
                        rule_data.get("id", "<unknown>"),
                        exc,
                        exc_info=True,
                    )
                    continue

        result.status = MigrationStatus.ROLLED_BACK
        return True

    def history(self) -> list[dict[str, Any]]:
        """Return migration history."""
        return [r.to_dict() for r in self._history]

    def _capture_snapshot(self, constitution: Any) -> dict[str, Any]:
        """Capture rule state for rollback."""
        rules: list[dict[str, Any]] = []
        for rule in getattr(constitution, "rules", []):
            rules.append(
                {
                    "id": rule.id,
                    "text": rule.text,
                    "severity": rule.severity.value
                    if hasattr(rule.severity, "value")
                    else str(rule.severity),
                    "keywords": list(getattr(rule, "keywords", [])),
                    "patterns": [
                        p.pattern if hasattr(p, "pattern") else str(p)
                        for p in getattr(rule, "patterns", [])
                    ],
                }
            )
        return {
            "version": getattr(constitution, "version", "unknown"),
            "rule_count": len(rules),
            "rules": rules,
            "captured_at": time.time(),
        }

    def _apply_step(self, step: RuleMigrationStep, constitution: Any) -> bool:
        """Apply a single migration step. Returns True if applied."""
        rules = getattr(constitution, "rules", [])
        rule_map = {r.id: r for r in rules}

        if step.action == RuleAction.KEEP:
            return step.source_rule_id in rule_map

        if step.action == RuleAction.RENAME:
            rule = rule_map.get(step.source_rule_id)
            if rule and step.target_rule_id:
                rule.id = step.target_rule_id
                return True
            return False

        if step.action == RuleAction.REMOVE:
            rule = rule_map.get(step.source_rule_id)
            if rule:
                rules.remove(rule)
                return True
            return False

        if step.action == RuleAction.DEPRECATE:
            rule = rule_map.get(step.source_rule_id)
            if rule and hasattr(rule, "lifecycle_state"):
                rule.lifecycle_state = "deprecated"
                if step.target_rule_id:
                    rule.replaced_by = step.target_rule_id
                return True
            if rule:
                if not hasattr(rule, "_metadata"):
                    rule._metadata = {}
                rule._metadata["deprecated"] = True
                if step.target_rule_id:
                    rule._metadata["replaced_by"] = step.target_rule_id
                return True
            return False

        if step.action == RuleAction.TRANSFORM:
            rule = rule_map.get(step.source_rule_id)
            if not rule:
                return False
            if step.severity_change:
                from .core import Severity

                with contextlib.suppress(ValueError):
                    rule.severity = Severity(step.severity_change)
            if step.keyword_changes:
                kws = list(getattr(rule, "keywords", []))
                for kw in step.keyword_changes.get("add", []):
                    if kw not in kws:
                        kws.append(kw)
                for kw in step.keyword_changes.get("remove", []):
                    if kw in kws:
                        kws.remove(kw)
                rule.keywords = kws
            return True

        if step.action == RuleAction.MERGE:
            if not step.merge_sources or not step.target_rule_id:
                return False
            all_keywords: list[str] = []
            all_patterns: list[Any] = []
            highest_severity = None
            merged_text_parts: list[str] = []
            for src_id in step.merge_sources:
                src_rule = rule_map.get(src_id)
                if src_rule:
                    merged_text_parts.append(src_rule.text)
                    all_keywords.extend(getattr(src_rule, "keywords", []))
                    all_patterns.extend(getattr(src_rule, "patterns", []))
                    if highest_severity is None or (
                        hasattr(src_rule.severity, "value")
                        and self._severity_rank(src_rule.severity)
                        > self._severity_rank(highest_severity)
                    ):
                        highest_severity = src_rule.severity
            for src_id in step.merge_sources:
                src_rule = rule_map.get(src_id)
                if src_rule and src_rule in rules:
                    rules.remove(src_rule)

            from .core import Rule, Severity

            fallback_severity = (
                highest_severity if highest_severity is not None else Severity.MEDIUM
            )
            merged = Rule(
                id=step.target_rule_id,
                text=" | ".join(merged_text_parts),
                severity=fallback_severity,
                keywords=list(dict.fromkeys(all_keywords)),
                patterns=[],
            )
            rules.append(merged)
            return True

        if step.action == RuleAction.SPLIT:
            if not step.target_rule_ids:
                return False
            src_rule = rule_map.get(step.source_rule_id)
            if not src_rule:
                return False
            from .core import Rule

            kws = list(getattr(src_rule, "keywords", []))
            chunk_size = max(1, len(kws) // len(step.target_rule_ids))
            for i, target_id in enumerate(step.target_rule_ids):
                start = i * chunk_size
                end = start + chunk_size if i < len(step.target_rule_ids) - 1 else len(kws)
                split_rule = Rule(
                    id=target_id,
                    text=f"{src_rule.text} (part {i + 1})",
                    severity=src_rule.severity,
                    keywords=kws[start:end],
                    patterns=[],
                )
                rules.append(split_rule)
            rules.remove(src_rule)
            return True

        return False

    @staticmethod
    def _severity_rank(severity: Any) -> int:
        """Numeric rank for severity comparison."""
        val = severity.value if hasattr(severity, "value") else str(severity)
        return {"low": 1, "medium": 2, "high": 3, "critical": 4}.get(val, 0)
