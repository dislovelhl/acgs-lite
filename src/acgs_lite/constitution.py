"""Constitutional rules — the core of ACGS-Lite.

A Constitution is a set of Rules that govern agent behavior.
Rules can be loaded from YAML, dicts, or created programmatically.

Constitutional Hash: cdd01ef066bc6cf2
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


class Severity(str, Enum):
    """Rule severity levels."""

    CRITICAL = "critical"  # Blocks action, no override
    HIGH = "high"  # Blocks action, can be overridden with justification
    MEDIUM = "medium"  # Warns but allows
    LOW = "low"  # Informational

    def blocks(self) -> bool:
        """Whether this severity level blocks execution."""
        return self in (Severity.CRITICAL, Severity.HIGH)


# Pre-compile negative verb detection as a single regex at module load time.
# This avoids re-scanning the frozenset on every matches() call.
_NEGATIVE_VERBS_LIST = (
    "without",
    "disable",
    "bypass",
    "remove",
    "skip",
    "no ",
    "delete",
    "override",
    "hide",
    "obfuscate",
    "auto-reject",
    "self-approve",
    "self-validate",
    "delegate entirely",
    "store biometric",
    "export customer",
    "cross-reference",
    "let ai system self",
    "process customer pii",
    "use zip code",
    "deploy loan approval model with known",
    "deploy hiring model without",
)
_NEGATIVE_VERBS_RE = re.compile(
    "|".join(re.escape(v) for v in _NEGATIVE_VERBS_LIST),
    re.IGNORECASE,
)

_POSITIVE_VERBS_SET = frozenset(
    {
        "run",
        "test",
        "generate",
        "create",
        "schedule",
        "implement",
        "log",
        "enable",
        "assign",
        "establish",
        "publish",
        "disclose",
        "build",
        "review",
        "audit",
        "check",
        "verify",
        "assess",
        "evaluate",
        "report",
        "document",
        "plan",
        "prepare",
        "anonymize",
        "share",
        "update",
        "optimize",
        "parallelize",
        "consolidate",
        "migrate",
    }
)

_KW_NEGATIVE_RE = re.compile(
    r"without|disable|bypass|remove|skip|delete|override|hide|"
    r"auto-reject|self-approve|proxy for",
    re.IGNORECASE,
)


# exp94: Pre-compiled risk signal patterns for context scoring.
# Weights: higher = riskier context environment.
_CONTEXT_RISK_SIGNALS: tuple[tuple[re.Pattern[str], float, str], ...] = (
    (re.compile(r"production|prod\b|live\b", re.IGNORECASE), 0.9, "production_environment"),
    (re.compile(r"customer|user.?data|pii|personal", re.IGNORECASE), 0.85, "personal_data"),
    (re.compile(r"financ|payment|billing|credit", re.IGNORECASE), 0.8, "financial_data"),
    (re.compile(r"admin|root|superuser|privileg", re.IGNORECASE), 0.75, "elevated_privilege"),
    (re.compile(r"secret|credential|token|key\b", re.IGNORECASE), 0.7, "sensitive_credential"),
    (re.compile(r"compliance|regulat|gdpr|hipaa|sox", re.IGNORECASE), 0.65, "regulatory_scope"),
    (re.compile(r"staging|pre.?prod|canary", re.IGNORECASE), 0.4, "pre_production"),
    (re.compile(r"test|sandbox|dev\b|local", re.IGNORECASE), 0.1, "test_environment"),
)


def score_context_risk(context: dict[str, Any]) -> dict[str, Any]:
    """exp94: Score a context dict for risk signals.

    Scans both keys and values of the context dict for risk-indicating
    patterns. Returns a composite risk score (0.0–1.0), the matched
    signals, and a recommended handling tier.

    Downstream agents and orchestrators use this to modulate governance
    strictness based on the operational context (e.g., production +
    customer data = maximum strictness; test sandbox = relaxed).

    Args:
        context: The context dict passed to validate(). May be empty.

    Returns:
        dict with keys:
            - ``risk_score``: float 0.0–1.0 (max of matched signal weights)
            - ``signals``: list of matched signal names
            - ``handling_tier``: "maximum" | "elevated" | "standard" | "relaxed"
    """
    if not context:
        return {"risk_score": 0.0, "signals": [], "handling_tier": "standard"}

    # Flatten context to a single searchable string
    parts: list[str] = []
    for k, v in context.items():
        parts.append(str(k))
        parts.append(str(v))
    text = " ".join(parts)

    max_score = 0.0
    signals: list[str] = []

    for pattern, weight, name in _CONTEXT_RISK_SIGNALS:
        if pattern.search(text):
            signals.append(name)
            if weight > max_score:
                max_score = weight

    if max_score >= 0.7:
        tier = "maximum"
    elif max_score >= 0.4:
        tier = "elevated"
    elif max_score > 0.0:
        tier = "relaxed"
    else:
        tier = "standard"

    return {"risk_score": max_score, "signals": signals, "handling_tier": tier}


def governance_decision_report(
    action: str,
    context: dict[str, Any] | None = None,
    rules: Sequence[Rule] | None = None,
) -> dict[str, Any]:
    """exp97: Generate a comprehensive governance report for an action.

    Composes match_detail() + score_context_risk() into a single actionable
    report. Downstream orchestrators call this instead of invoking each
    governance function separately.

    Args:
        action: The action text to evaluate.
        context: Optional context dict for risk scoring.
        rules: Rules to check against. If None, uses empty list.

    Returns:
        dict with keys:
            - ``action``: the input action text
            - ``context_risk``: output of score_context_risk()
            - ``triggered_rules``: list of match_detail() results where matched=True
            - ``rule_count_checked``: total rules evaluated
            - ``decision_hint``: "allow" | "deny" | "escalate" based on triggered rules
            - ``max_severity``: highest severity among triggered rules (or None)
    """
    context_risk = score_context_risk(context or {})

    triggered: list[dict[str, Any]] = []
    max_sev: str | None = None
    sev_order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    max_sev_rank = 0
    checked = 0

    for rule in rules or []:
        checked += 1
        detail = rule.match_detail(action)
        if detail["matched"]:
            triggered.append(detail)
            rank = sev_order.get(detail["severity"], 0)
            if rank > max_sev_rank:
                max_sev_rank = rank
                max_sev = detail["severity"]

    if not triggered:
        hint = "allow"
    elif max_sev in ("critical", "high"):
        hint = "deny"
    else:
        hint = "escalate"

    return {
        "action": action,
        "context_risk": context_risk,
        "triggered_rules": triggered,
        "rule_count_checked": checked,
        "decision_hint": hint,
        "max_severity": max_sev,
    }


class Rule(BaseModel):
    """A single constitutional rule."""

    id: str = Field(..., min_length=1, max_length=50)
    text: str = Field(..., min_length=1, max_length=1000)
    severity: Severity = Severity.HIGH
    keywords: list[str] = Field(default_factory=list)
    patterns: list[str] = Field(default_factory=list)
    category: str = "general"
    # exp96: finer-grained classification within a category
    subcategory: str = ""
    # exp99: inter-rule relationships (rule IDs this rule depends on or reinforces)
    depends_on: list[str] = Field(default_factory=list)
    enabled: bool = True
    # exp90: downstream workflow action when this rule fires
    # Values: "block" | "block_and_notify" | "require_human_review" | "escalate_to_senior" | "warn" | ""
    workflow_action: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    # Cached derived values (set in model_post_init, never mutated after)
    _kw_lower: list[str] = []
    _compiled_pats: list[re.Pattern[str]] = []

    @field_validator("patterns")
    @classmethod
    def validate_patterns(cls, v: list[str]) -> list[str]:
        """Ensure regex patterns are valid."""
        for pattern in v:
            try:
                re.compile(pattern)
            except re.error as e:
                raise ValueError(f"Invalid regex pattern '{pattern}': {e}") from e
        return v

    def model_post_init(self, __context: Any) -> None:
        """Pre-compute derived values to avoid repeated work per match() call."""
        object.__setattr__(self, "_kw_lower", [k.lower() for k in self.keywords])
        object.__setattr__(
            self,
            "_compiled_pats",
            [re.compile(p, re.IGNORECASE) for p in self.patterns],
        )

    def matches_with_signals(self, text_lower: str, has_neg: bool, has_pos: bool) -> bool:
        """Fast match using pre-computed action-level signals (amortised per validate call).

        Args:
            text_lower: action text already lowercased by the caller.
            has_neg: True if action contains a negative/violation verb.
            has_pos: True if action starts with a positive/constructive verb.
        """
        if not self.enabled:
            return False

        for kw_lower in self._kw_lower:  # type: ignore[attr-defined]
            if kw_lower in text_lower:
                if has_pos and not has_neg:
                    if not _KW_NEGATIVE_RE.search(kw_lower):
                        continue
                return True

        return any(pat.search(text_lower) for pat in self._compiled_pats)  # type: ignore[attr-defined]

    def match_detail(self, text: str) -> dict[str, Any]:
        """exp93: Return structured match information for governance consumers.

        Unlike ``matches()`` which returns a bare bool, this provides the
        full context needed for governance dashboards, audit trails, and
        downstream workflow routing: which keyword or pattern triggered,
        the rule's severity and workflow_action, and whether positive-verb
        context was detected.

        Args:
            text: The action text to check.

        Returns:
            dict with keys:
                - ``matched``: True if this rule was triggered
                - ``rule_id``: this rule's ID
                - ``severity``: severity level string
                - ``category``: rule category
                - ``workflow_action``: downstream action hint
                - ``trigger_type``: "keyword" | "pattern" | None
                - ``trigger_value``: the specific keyword or pattern that matched
                - ``positive_context``: True if positive verb was detected
        """
        if not self.enabled:
            return {
                "matched": False,
                "rule_id": self.id,
                "severity": self.severity.value,
                "category": self.category,
                "workflow_action": self.workflow_action,
                "trigger_type": None,
                "trigger_value": None,
                "positive_context": False,
            }

        text_lower = text.lower()
        has_neg = bool(_NEGATIVE_VERBS_RE.search(text_lower))
        has_pos = (not has_neg) and any(
            w in _POSITIVE_VERBS_SET for w in text_lower.split()[:4]
        )

        # Check keywords
        for kw_lower in self._kw_lower:  # type: ignore[attr-defined]
            if kw_lower in text_lower:
                if has_pos and not has_neg:
                    if not _KW_NEGATIVE_RE.search(kw_lower):
                        continue
                return {
                    "matched": True,
                    "rule_id": self.id,
                    "severity": self.severity.value,
                    "category": self.category,
                    "workflow_action": self.workflow_action,
                    "trigger_type": "keyword",
                    "trigger_value": kw_lower,
                    "positive_context": has_pos,
                }

        # Check patterns
        for pat in self._compiled_pats:  # type: ignore[attr-defined]
            if m := pat.search(text_lower):
                return {
                    "matched": True,
                    "rule_id": self.id,
                    "severity": self.severity.value,
                    "category": self.category,
                    "workflow_action": self.workflow_action,
                    "trigger_type": "pattern",
                    "trigger_value": m.group(0),
                    "positive_context": has_pos,
                }

        return {
            "matched": False,
            "rule_id": self.id,
            "severity": self.severity.value,
            "category": self.category,
            "workflow_action": self.workflow_action,
            "trigger_type": None,
            "trigger_value": None,
            "positive_context": has_pos,
        }

    def matches(self, text: str) -> bool:
        """Check if text matches this rule's patterns or keywords.

        Uses context-aware matching: positive/constructive actions
        (testing, auditing, implementing) are not flagged even if they
        contain governance keywords.

        Returns True if the text triggers this rule (i.e., violates it).
        """
        if not self.enabled:
            return False

        text_lower = text.lower()
        has_neg = bool(_NEGATIVE_VERBS_RE.search(text_lower))
        has_pos = (not has_neg) and any(w in _POSITIVE_VERBS_SET for w in text_lower.split()[:4])
        return self.matches_with_signals(text_lower, has_neg, has_pos)


class Constitution(BaseModel):
    """A set of rules that govern agent behavior."""

    name: str = "default"
    version: str = "1.0.0"
    rules: list[Rule] = Field(default_factory=list)
    description: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    # Cached values
    _hash_cache: str = ""
    _active_rules_cache: list[Rule] = []

    def model_post_init(self, __context: Any) -> None:
        """Pre-compute hash and active rules cache."""
        canonical = "|".join(
            f"{r.id}:{r.text}:{r.severity.value}:{','.join(sorted(r.keywords))}"
            for r in sorted(self.rules, key=lambda r: r.id)
        )
        h = hashlib.sha256(canonical.encode()).hexdigest()[:16]
        object.__setattr__(self, "_hash_cache", h)
        object.__setattr__(self, "_active_rules_cache", [r for r in self.rules if r.enabled])

    @property
    def hash(self) -> str:
        """Return the cached constitutional hash."""
        return self._hash_cache  # type: ignore[return-value]

    @property
    def hash_versioned(self) -> str:
        """Return versioned hash string: sha256:v1:<hash>."""
        return f"sha256:v1:{self.hash}"

    @classmethod
    def from_yaml(cls, path: str | Path) -> Constitution:
        """Load a constitution from a YAML file."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Constitution file not found: {path}")
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls._from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Constitution:
        """Create a constitution from a dictionary."""
        return cls._from_dict(data)

    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> Constitution:
        rules_data = data.get("rules", [])
        rules = [
            Rule(
                id=r["id"],
                text=r["text"],
                severity=Severity(r.get("severity", "high")),
                keywords=r.get("keywords", []),
                patterns=r.get("patterns", []),
                category=r.get("category", "general"),
                subcategory=r.get("subcategory", ""),
                depends_on=r.get("depends_on", []),
                enabled=r.get("enabled", True),
                workflow_action=r.get("workflow_action", ""),
                metadata=r.get("metadata", {}),
            )
            for r in rules_data
        ]
        return cls(
            name=data.get("name", "default"),
            version=data.get("version", "1.0.0"),
            rules=rules,
            description=data.get("description", ""),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def from_rules(cls, rules: Sequence[Rule], name: str = "custom") -> Constitution:
        """Create a constitution from a list of Rule objects."""
        return cls(name=name, rules=list(rules))

    @classmethod
    def default(cls) -> Constitution:
        """Return the ACGS default constitution with core safety rules."""
        return cls(
            name="acgs-default",
            version="1.0.0",
            description="ACGS default constitutional rules for AI agent governance",
            rules=[
                Rule(
                    id="ACGS-001",
                    text="Agents must not modify their own validation logic",
                    severity=Severity.CRITICAL,
                    keywords=["self-validate", "bypass validation", "skip check"],
                    category="integrity",
                    subcategory="self-modification",
                    workflow_action="block",
                ),
                Rule(
                    id="ACGS-002",
                    text="All actions must produce an audit trail entry",
                    severity=Severity.HIGH,
                    keywords=["no-audit", "skip audit", "disable logging"],
                    category="audit",
                    subcategory="trail-completeness",
                    workflow_action="require_human_review",
                ),
                Rule(
                    id="ACGS-003",
                    text="Agents must not access data outside their authorized scope",
                    severity=Severity.CRITICAL,
                    keywords=["unauthorized", "escalate privilege", "admin override"],
                    category="access",
                    subcategory="scope-violation",
                    workflow_action="block",
                ),
                Rule(
                    id="ACGS-004",
                    text="Proposers cannot validate their own proposals (MACI)",
                    severity=Severity.CRITICAL,
                    keywords=["self-approve", "auto-approve"],
                    category="maci",
                    subcategory="separation-of-powers",
                    workflow_action="block",
                ),
                Rule(
                    id="ACGS-005",
                    text="All governance changes require constitutional hash verification",
                    severity=Severity.HIGH,
                    keywords=["skip hash", "ignore constitution"],
                    category="integrity",
                    subcategory="hash-verification",
                    workflow_action="require_human_review",
                ),
                Rule(
                    id="ACGS-006",
                    text="Agents must not expose sensitive data in responses",
                    severity=Severity.CRITICAL,
                    keywords=["password", "secret key", "api_key", "private key"],
                    patterns=[
                        r"(?i)(sk-[a-zA-Z0-9]{20,})",
                        r"(?i)(ghp_[a-zA-Z0-9]{36})",
                        r"\b\d{3}-\d{2}-\d{4}\b",
                    ],
                    category="data-protection",
                    subcategory="credential-exposure",
                    workflow_action="block_and_notify",
                ),
            ],
        )

    def get_rule(self, rule_id: str) -> Rule | None:
        """Get a rule by ID."""
        for rule in self.rules:
            if rule.id == rule_id:
                return rule
        return None

    def active_rules(self) -> list[Rule]:
        """Return only enabled rules (cached)."""
        return self._active_rules_cache  # type: ignore[return-value]

    def governance_summary(self) -> dict[str, Any]:
        """exp92: Return governance posture summary for dashboards and agent introspection.

        Provides a structured overview of the constitutional ruleset without
        exposing rule internals. Downstream agents, dashboards, and monitoring
        systems can use this to understand the governance posture at a glance.

        Returns:
            dict with keys:
                - ``total_rules``: total rule count
                - ``active_rules``: enabled rule count
                - ``by_severity``: count of rules per severity level
                - ``by_category``: count of rules per category
                - ``by_workflow_action``: count of rules per workflow_action
                - ``coverage``: dict of governance coverage metrics
        """
        active = self.active_rules()
        by_severity: dict[str, int] = {}
        by_category: dict[str, int] = {}
        by_subcategory: dict[str, int] = {}
        by_workflow: dict[str, int] = {}

        for r in active:
            sev = r.severity.value
            by_severity[sev] = by_severity.get(sev, 0) + 1
            by_category[r.category] = by_category.get(r.category, 0) + 1
            if r.subcategory:
                by_subcategory[r.subcategory] = by_subcategory.get(r.subcategory, 0) + 1
            wa = r.workflow_action or "unspecified"
            by_workflow[wa] = by_workflow.get(wa, 0) + 1

        has_keywords = sum(1 for r in active if r.keywords)
        has_patterns = sum(1 for r in active if r.patterns)
        has_workflow = sum(1 for r in active if r.workflow_action)
        has_subcategory = sum(1 for r in active if r.subcategory)

        return {
            "total_rules": len(self.rules),
            "active_rules": len(active),
            "by_severity": by_severity,
            "by_category": by_category,
            "by_subcategory": by_subcategory,
            "by_workflow_action": by_workflow,
            "coverage": {
                "keyword_rules": has_keywords,
                "pattern_rules": has_patterns,
                "workflow_routed": has_workflow,
                "subcategorized": has_subcategory,
                "blocking_rules": sum(1 for r in active if r.severity.blocks()),
            },
        }

    def diff(self, other: Constitution) -> dict[str, Any]:
        """exp98: Compare two constitutions and report changes.

        Essential for governance auditing and change management. Returns
        a structured diff showing added, removed, and modified rules so
        compliance teams can review constitutional changes before deployment.

        Args:
            other: The constitution to compare against (typically the newer version).

        Returns:
            dict with keys:
                - ``hash_changed``: bool
                - ``old_hash``: this constitution's hash
                - ``new_hash``: other constitution's hash
                - ``added``: list of rule IDs present in other but not self
                - ``removed``: list of rule IDs present in self but not other
                - ``modified``: list of dicts describing per-rule changes
                - ``severity_changes``: list of rules where severity changed
                - ``summary``: human-readable change summary string
        """
        self_rules = {r.id: r for r in self.rules}
        other_rules = {r.id: r for r in other.rules}

        self_ids = set(self_rules)
        other_ids = set(other_rules)

        added = sorted(other_ids - self_ids)
        removed = sorted(self_ids - other_ids)

        modified: list[dict[str, Any]] = []
        severity_changes: list[dict[str, str]] = []

        for rid in sorted(self_ids & other_ids):
            old_r = self_rules[rid]
            new_r = other_rules[rid]
            changes: dict[str, tuple[str, str]] = {}

            if old_r.text != new_r.text:
                changes["text"] = (old_r.text, new_r.text)
            if old_r.severity != new_r.severity:
                changes["severity"] = (old_r.severity.value, new_r.severity.value)
                severity_changes.append(
                    {"rule_id": rid, "old": old_r.severity.value, "new": new_r.severity.value}
                )
            if old_r.category != new_r.category:
                changes["category"] = (old_r.category, new_r.category)
            if old_r.subcategory != new_r.subcategory:
                changes["subcategory"] = (old_r.subcategory, new_r.subcategory)
            if old_r.workflow_action != new_r.workflow_action:
                changes["workflow_action"] = (old_r.workflow_action, new_r.workflow_action)
            if old_r.enabled != new_r.enabled:
                changes["enabled"] = (str(old_r.enabled), str(new_r.enabled))
            if sorted(old_r.keywords) != sorted(new_r.keywords):
                changes["keywords"] = (",".join(sorted(old_r.keywords)),
                                       ",".join(sorted(new_r.keywords)))

            if changes:
                modified.append({"rule_id": rid, "changes": changes})

        parts: list[str] = []
        if added:
            parts.append(f"+{len(added)} rules")
        if removed:
            parts.append(f"-{len(removed)} rules")
        if modified:
            parts.append(f"~{len(modified)} modified")
        if severity_changes:
            parts.append(f"{len(severity_changes)} severity changes")
        summary = ", ".join(parts) if parts else "no changes"

        return {
            "hash_changed": self.hash != other.hash,
            "old_hash": self.hash,
            "new_hash": other.hash,
            "added": added,
            "removed": removed,
            "modified": modified,
            "severity_changes": severity_changes,
            "summary": summary,
        }

    def __len__(self) -> int:
        return len(self.rules)

    def __repr__(self) -> str:
        return f"Constitution(name={self.name!r}, rules={len(self.rules)}, hash={self.hash!r})"
