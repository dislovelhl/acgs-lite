"""Constitutional rules — the core of ACGS-Lite.

A Constitution is a set of Rules that govern agent behavior.
Rules can be loaded from YAML, dicts, or created programmatically.

Constitutional Hash: cdd01ef066bc6cf2
"""

from __future__ import annotations

import hashlib
import re
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
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


def classify_action_intent(action: str) -> dict[str, Any]:
    """exp101: Classify an action's intent for downstream governance decisions.

    Detects whether an action is constructive (testing, auditing, implementing)
    or potentially harmful (disabling, bypassing, removing). Downstream agents
    and orchestrators use this to understand the intent behind an action
    independently of rule matching.

    Args:
        action: The action text to classify.

    Returns:
        dict with keys:
            - ``has_negative_verb``: True if action contains violation-indicating verbs
            - ``has_positive_verb``: True if action starts with constructive verbs
            - ``intent``: "constructive" | "potentially_harmful" | "neutral"
            - ``detected_verbs``: list of specific verbs detected
            - ``confidence``: float 0.0-1.0 based on signal strength
    """
    text_lower = action.lower()
    neg_match = _NEGATIVE_VERBS_RE.search(text_lower)
    has_neg = bool(neg_match)

    words = text_lower.split()[:4]
    pos_matches = [w for w in words if w in _POSITIVE_VERBS_SET]
    has_pos = bool(pos_matches) and not has_neg

    detected: list[str] = []
    if neg_match:
        detected.append(neg_match.group(0))
    detected.extend(pos_matches)

    if has_neg:
        intent = "potentially_harmful"
        confidence = 0.85
    elif has_pos:
        intent = "constructive"
        confidence = 0.8
    else:
        intent = "neutral"
        confidence = 0.5

    return {
        "has_negative_verb": has_neg,
        "has_positive_verb": has_pos,
        "intent": intent,
        "detected_verbs": detected,
        "confidence": confidence,
    }


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


@dataclass(frozen=True, slots=True)
class GovernanceEvent:
    """exp100: Structured governance event for monitoring, alerting, and audit pipelines.

    Immutable record of a governance decision. Downstream systems (SIEM,
    observability dashboards, compliance logs) consume these events via
    ``to_dict()`` for JSON serialization or directly as typed objects.
    """

    event_type: str  # "validation_allow" | "validation_deny" | "validation_escalate" | "maci_violation"
    action: str
    decision: str  # "allow" | "deny" | "escalate"
    timestamp_ns: int  # monotonic nanoseconds for ordering
    rule_ids: tuple[str, ...] = ()
    severity: str = ""
    workflow_action: str = ""
    context_risk_score: float = 0.0
    agent_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSON/JSONL output."""
        return {
            "event_type": self.event_type,
            "action": self.action,
            "decision": self.decision,
            "timestamp_ns": self.timestamp_ns,
            "rule_ids": list(self.rule_ids),
            "severity": self.severity,
            "workflow_action": self.workflow_action,
            "context_risk_score": self.context_risk_score,
            "agent_id": self.agent_id,
            "metadata": self.metadata,
        }


def create_governance_event(
    action: str,
    decision: str,
    *,
    rule_ids: Sequence[str] = (),
    severity: str = "",
    workflow_action: str = "",
    context_risk_score: float = 0.0,
    agent_id: str = "",
    metadata: dict[str, Any] | None = None,
) -> GovernanceEvent:
    """exp100: Factory for governance events with auto-populated fields.

    Args:
        action: The action that was validated.
        decision: The governance decision ("allow", "deny", "escalate").
        rule_ids: IDs of rules that triggered (empty for allow).
        severity: Highest severity among triggered rules.
        workflow_action: Recommended workflow action from the triggered rule.
        context_risk_score: Risk score from score_context_risk().
        agent_id: ID of the agent that submitted the action.
        metadata: Additional event metadata.

    Returns:
        Immutable GovernanceEvent ready for publishing.
    """
    event_type = f"validation_{decision}"
    return GovernanceEvent(
        event_type=event_type,
        action=action,
        decision=decision,
        timestamp_ns=time.monotonic_ns(),
        rule_ids=tuple(rule_ids),
        severity=severity,
        workflow_action=workflow_action,
        context_risk_score=context_risk_score,
        agent_id=agent_id,
        metadata=metadata or {},
    )


class GovernanceMetrics:
    """exp104: Lightweight governance statistics collector for observability.

    Tracks allow/deny/escalate counts, rule hit frequencies, and per-decision
    latency stats. Designed for export to Prometheus, OpenTelemetry, or
    custom dashboards. Thread-safe for single-writer use (typical governance
    engine pattern).

    Usage::

        metrics = GovernanceMetrics()
        metrics.record("allow", latency_us=3.2)
        metrics.record("deny", latency_us=5.1, rule_ids=["ACGS-001"])
        print(metrics.snapshot())
    """

    __slots__ = ("_counts", "_rule_hits", "_latencies", "_total")

    def __init__(self) -> None:
        self._counts: dict[str, int] = {"allow": 0, "deny": 0, "escalate": 0}
        self._rule_hits: dict[str, int] = {}
        self._latencies: list[float] = []
        self._total: int = 0

    def record(
        self,
        decision: str,
        *,
        latency_us: float = 0.0,
        rule_ids: Sequence[str] = (),
    ) -> None:
        """Record a governance decision.

        Args:
            decision: "allow", "deny", or "escalate".
            latency_us: Validation latency in microseconds.
            rule_ids: Rule IDs that triggered (for deny/escalate).
        """
        self._counts[decision] = self._counts.get(decision, 0) + 1
        self._total += 1
        if latency_us > 0:
            self._latencies.append(latency_us)
        for rid in rule_ids:
            self._rule_hits[rid] = self._rule_hits.get(rid, 0) + 1

    def snapshot(self) -> dict[str, Any]:
        """Return current metrics snapshot for export.

        Returns:
            dict with keys:
                - ``total_decisions``: total count
                - ``by_decision``: {allow: N, deny: N, escalate: N}
                - ``rule_hit_counts``: {rule_id: hit_count, ...}
                - ``latency``: {p50_us, p99_us, mean_us, count} or empty if no data
                - ``rates``: {allow_rate, deny_rate, escalate_rate} as floats
        """
        rates: dict[str, float] = {}
        if self._total > 0:
            for k, v in self._counts.items():
                rates[f"{k}_rate"] = v / self._total

        latency_stats: dict[str, float] = {}
        if self._latencies:
            sorted_lat = sorted(self._latencies)
            n = len(sorted_lat)
            latency_stats = {
                "p50_us": sorted_lat[n // 2],
                "p99_us": sorted_lat[int(n * 0.99)],
                "mean_us": sum(sorted_lat) / n,
                "count": float(n),
            }

        return {
            "total_decisions": self._total,
            "by_decision": dict(self._counts),
            "rule_hit_counts": dict(sorted(
                self._rule_hits.items(), key=lambda x: x[1], reverse=True
            )),
            "latency": latency_stats,
            "rates": rates,
        }

    def reset(self) -> None:
        """Reset all counters. Call after exporting metrics."""
        self._counts = {"allow": 0, "deny": 0, "escalate": 0}
        self._rule_hits.clear()
        self._latencies.clear()
        self._total = 0



@dataclass(frozen=True)
class RuleSnapshot:
    """exp106: Immutable snapshot of a Rule's state at a point in time.

    Stored in ``Constitution.rule_history`` when a rule is updated via
    ``Constitution.update_rule()``. Enables change management dashboards,
    compliance audit trails, and rollback analysis.

    Attributes:
        rule_id: ID of the rule this snapshot belongs to.
        timestamp: Unix timestamp when this version was captured.
        version: Version number (1 = original, 2 = first update, ...).
        text: Rule text at this version.
        severity: Severity level at this version.
        enabled: Whether the rule was enabled at this version.
        keywords: Keywords at this version.
        category: Category at this version.
        subcategory: Subcategory at this version.
        workflow_action: Workflow action at this version.
        change_reason: Optional human-readable reason for this change.
    """

    rule_id: str
    timestamp: float
    version: int
    text: str
    severity: str
    enabled: bool
    keywords: tuple[str, ...]
    category: str
    subcategory: str
    workflow_action: str
    change_reason: str = ""

    @classmethod
    def from_rule(cls, rule: "Rule", version: int, change_reason: str = "") -> "RuleSnapshot":
        """Create a snapshot from a Rule instance."""
        return cls(
            rule_id=rule.id,
            timestamp=time.time(),
            version=version,
            text=rule.text,
            severity=rule.severity.value,
            enabled=rule.enabled,
            keywords=tuple(rule.keywords),
            category=rule.category,
            subcategory=rule.subcategory,
            workflow_action=rule.workflow_action,
            change_reason=change_reason,
        )

    def to_dict(self) -> dict:
        """Serialise snapshot to a JSON-compatible dict."""
        return {
            "rule_id": self.rule_id,
            "timestamp": self.timestamp,
            "version": self.version,
            "text": self.text,
            "severity": self.severity,
            "enabled": self.enabled,
            "keywords": list(self.keywords),
            "category": self.category,
            "subcategory": self.subcategory,
            "workflow_action": self.workflow_action,
            "change_reason": self.change_reason,
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

    def explain(self) -> dict[str, Any]:
        """exp103: Return a human-readable explanation of this rule.

        Formats rule information for non-technical governance reviewers,
        compliance dashboards, and documentation generators. Includes
        what the rule protects, how it detects violations, and what
        happens when it triggers.

        Returns:
            dict with keys:
                - ``rule_id``: rule identifier
                - ``summary``: one-line human-readable summary
                - ``what_it_protects``: description of the governance concern
                - ``how_it_detects``: description of detection method
                - ``when_triggered``: what happens when the rule fires
                - ``severity_label``: human-readable severity
                - ``dependencies``: list of rules this depends on
        """
        severity_labels = {
            "critical": "Critical — blocks action, no override allowed",
            "high": "High — blocks action, can be overridden with justification",
            "medium": "Medium — warns but allows action to proceed",
            "low": "Low — informational only",
        }

        detection_parts: list[str] = []
        if self.keywords:
            detection_parts.append(
                f"Scans for keywords: {', '.join(repr(k) for k in self.keywords)}"
            )
        if self.patterns:
            detection_parts.append(
                f"Matches {len(self.patterns)} regex pattern(s)"
            )
        if not detection_parts:
            detection_parts.append("No automatic detection configured")

        workflow_desc = {
            "block": "Hard block — action is rejected immediately",
            "block_and_notify": "Block and alert the security/compliance team",
            "require_human_review": "Queue for human review before proceeding",
            "escalate_to_senior": "Escalate to senior governance reviewer",
            "warn": "Log a warning but allow the action",
        }

        return {
            "rule_id": self.id,
            "summary": f"[{self.severity.value.upper()}] {self.text}",
            "what_it_protects": self.text,
            "how_it_detects": "; ".join(detection_parts),
            "when_triggered": workflow_desc.get(
                self.workflow_action, "No workflow action specified"
            ),
            "severity_label": severity_labels.get(
                self.severity.value, self.severity.value
            ),
            "dependencies": list(self.depends_on),
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
    # exp106: rule version history — rule_id → list of snapshots (oldest first)
    rule_history: dict[str, list[RuleSnapshot]] = Field(default_factory=dict)

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
                    depends_on=["ACGS-002"],  # scope violations must be audited
                    workflow_action="block",
                ),
                Rule(
                    id="ACGS-004",
                    text="Proposers cannot validate their own proposals (MACI)",
                    severity=Severity.CRITICAL,
                    keywords=["self-approve", "auto-approve"],
                    category="maci",
                    subcategory="separation-of-powers",
                    depends_on=["ACGS-001"],  # self-validation is a form of self-modification
                    workflow_action="block",
                ),
                Rule(
                    id="ACGS-005",
                    text="All governance changes require constitutional hash verification",
                    severity=Severity.HIGH,
                    keywords=["skip hash", "ignore constitution"],
                    category="integrity",
                    subcategory="hash-verification",
                    depends_on=["ACGS-001"],  # hash bypass is a form of validation bypass
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


    @classmethod
    def from_template(cls, domain: str) -> "Constitution":
        """exp105: Return a pre-built constitution for a well-known governance domain.

        Lowers the barrier to adoption by providing ready-to-use constitutions for
        common AI deployment scenarios. Each template captures the most impactful
        rules for that domain — useful for GitLab CI/CD gates, healthcare AI,
        financial AI, and security-sensitive deployments.

        Args:
            domain: One of "gitlab", "healthcare", "finance", "security", "general".

        Returns:
            A Constitution pre-populated with domain-appropriate rules.

        Raises:
            ValueError: If the domain is not recognised.

        Example::

            constitution = Constitution.from_template("gitlab")
            engine = GovernanceEngine(constitution)
            result = engine.validate("auto-approve merge request", agent_id="ci-bot")
        """
        _TEMPLATES: dict[str, dict] = {
            "gitlab": {
                "name": "gitlab-governance",
                "version": "1.0.0",
                "description": (
                    "Constitutional governance for GitLab SDLC — enforces MACI "
                    "separation of powers, protects credentials, and ensures "
                    "merge request integrity."
                ),
                "rules": [
                    {
                        "id": "GL-001",
                        "text": "MR author cannot approve their own merge request (MACI separation of powers)",
                        "severity": "critical",
                        "keywords": ["self-approve", "auto-approve", "self-merge"],
                        "category": "maci",
                        "subcategory": "separation-of-powers",
                        "workflow_action": "block",
                    },
                    {
                        "id": "GL-002",
                        "text": "No credentials or secrets committed to repository",
                        "severity": "critical",
                        "keywords": ["api_key", "secret key", "private key", "password"],
                        "patterns": [
                            r"(?i)(sk-[a-zA-Z0-9]{20,})",
                            r"(?i)(ghp_[a-zA-Z0-9]{36})",
                            r"(?i)(glpat-[a-zA-Z0-9\-]{20})",
                            r"[A-Za-z0-9+/]{40}",
                        ],
                        "category": "data-protection",
                        "subcategory": "credential-exposure",
                        "workflow_action": "block_and_notify",
                    },
                    {
                        "id": "GL-003",
                        "text": "No PII (SSN, credit cards) in source code or commit messages",
                        "severity": "critical",
                        "patterns": [
                            r"\d{3}-\d{2}-\d{4}",
                            r"4[0-9]{12}(?:[0-9]{3})?",
                        ],
                        "category": "data-protection",
                        "subcategory": "pii-exposure",
                        "workflow_action": "block_and_notify",
                    },
                    {
                        "id": "GL-004",
                        "text": "Destructive production operations require human review",
                        "severity": "high",
                        "keywords": ["drop table", "delete all", "truncate", "rm -rf", "force push"],
                        "category": "operations",
                        "subcategory": "destructive-action",
                        "workflow_action": "require_human_review",
                    },
                    {
                        "id": "GL-005",
                        "text": "CI/CD pipelines must not skip constitutional validation",
                        "severity": "high",
                        "keywords": ["skip validation", "disable governance", "no-verify", "bypass check"],
                        "category": "integrity",
                        "subcategory": "governance-bypass",
                        "workflow_action": "block",
                    },
                    {
                        "id": "GL-006",
                        "text": "Agent actions must produce an audit trail entry",
                        "severity": "medium",
                        "keywords": ["no-audit", "skip audit", "disable logging"],
                        "category": "audit",
                        "subcategory": "trail-completeness",
                        "workflow_action": "warn",
                    },
                ],
            },
            "healthcare": {
                "name": "healthcare-governance",
                "version": "1.0.0",
                "description": (
                    "HIPAA-aligned constitutional governance for healthcare AI — "
                    "protects PHI, prevents unauthorised treatment decisions, and "
                    "ensures human oversight of clinical recommendations."
                ),
                "rules": [
                    {
                        "id": "HC-001",
                        "text": "AI must not make autonomous treatment decisions without clinician review",
                        "severity": "critical",
                        "keywords": [
                            "prescribe", "diagnose", "treatment decision", "clinical recommendation",
                            "approve treatment", "deny treatment",
                        ],
                        "category": "clinical-safety",
                        "subcategory": "autonomous-decision",
                        "workflow_action": "require_human_review",
                    },
                    {
                        "id": "HC-002",
                        "text": "Protected Health Information must not be exposed outside authorised scope",
                        "severity": "critical",
                        "keywords": ["patient data", "medical record", "health record", "phi", "ehr"],
                        "patterns": [r"\d{3}-\d{2}-\d{4}"],
                        "category": "data-protection",
                        "subcategory": "phi-exposure",
                        "workflow_action": "block_and_notify",
                    },
                    {
                        "id": "HC-003",
                        "text": "AI must not provide individualised medical advice without appropriate disclaimers",
                        "severity": "high",
                        "keywords": ["take this medication", "your diagnosis", "you have", "medical advice"],
                        "category": "clinical-safety",
                        "subcategory": "unqualified-advice",
                        "workflow_action": "escalate_to_senior",
                    },
                    {
                        "id": "HC-004",
                        "text": "Patient consent must be obtained before processing sensitive health data",
                        "severity": "high",
                        "keywords": ["without consent", "no consent check", "skip consent"],
                        "category": "compliance",
                        "subcategory": "hipaa-consent",
                        "workflow_action": "block",
                    },
                    {
                        "id": "HC-005",
                        "text": "All clinical AI decisions must be logged with patient ID and timestamp",
                        "severity": "high",
                        "keywords": ["no audit", "skip log", "disable audit"],
                        "category": "audit",
                        "subcategory": "clinical-trail",
                        "workflow_action": "block",
                    },
                ],
            },
            "finance": {
                "name": "finance-governance",
                "version": "1.0.0",
                "description": (
                    "ECOA/FCRA-aligned constitutional governance for financial AI — "
                    "prevents discriminatory lending, enforces explainability, and "
                    "protects against unauthorised transactions."
                ),
                "rules": [
                    {
                        "id": "FIN-001",
                        "text": "AI must not provide individualised investment or financial advice",
                        "severity": "critical",
                        "keywords": [
                            "invest in", "buy stocks", "financial advice", "portfolio recommendation",
                            "buy crypto", "short sell",
                        ],
                        "category": "regulatory",
                        "subcategory": "financial-advice",
                        "workflow_action": "block",
                    },
                    {
                        "id": "FIN-002",
                        "text": "Loan/credit decisions must not use protected characteristics",
                        "severity": "critical",
                        "keywords": [
                            "use zip code", "use race", "use gender", "use religion",
                            "use national origin", "proxy discrimin",
                        ],
                        "category": "compliance",
                        "subcategory": "fair-lending",
                        "workflow_action": "block_and_notify",
                    },
                    {
                        "id": "FIN-003",
                        "text": "Credit decisions must provide adverse action reasons (FCRA)",
                        "severity": "high",
                        "keywords": ["no reason", "deny without explanation", "reject silently"],
                        "category": "compliance",
                        "subcategory": "adverse-action",
                        "workflow_action": "require_human_review",
                    },
                    {
                        "id": "FIN-004",
                        "text": "High-value transactions require multi-party authorisation",
                        "severity": "critical",
                        "keywords": ["transfer funds", "wire transfer", "large transaction", "bulk payment"],
                        "category": "operations",
                        "subcategory": "transaction-control",
                        "workflow_action": "require_human_review",
                    },
                    {
                        "id": "FIN-005",
                        "text": "PII and financial account data must not be exposed in logs or responses",
                        "severity": "critical",
                        "patterns": [
                            r"\d{3}-\d{2}-\d{4}",
                            r"[0-9]{13,16}",
                            r"[0-9]{9}",
                        ],
                        "category": "data-protection",
                        "subcategory": "pii-exposure",
                        "workflow_action": "block_and_notify",
                    },
                ],
            },
            "security": {
                "name": "security-governance",
                "version": "1.0.0",
                "description": (
                    "Cybersecurity-focused constitutional governance — prevents "
                    "code injection, credential exposure, privilege escalation, "
                    "and sandbox escape."
                ),
                "rules": [
                    {
                        "id": "SEC-001",
                        "text": "AI must not generate or execute code injection payloads",
                        "severity": "critical",
                        "keywords": [
                            "sql injection", "xss payload", "exec(", "eval(", "os.system",
                            "subprocess.call", "__import__",
                        ],
                        "patterns": [
                            r"(?i)(union\s+select)",
                            r"<script[^>]*>",
                            r"(?i)(eval\s*\()",
                        ],
                        "category": "security",
                        "subcategory": "code-injection",
                        "workflow_action": "block_and_notify",
                    },
                    {
                        "id": "SEC-002",
                        "text": "Credentials and secrets must not appear in outputs or logs",
                        "severity": "critical",
                        "keywords": ["api key", "secret key", "private key", "password", "bearer token"],
                        "patterns": [
                            r"(?i)(sk-[a-zA-Z0-9]{20,})",
                            r"(?i)(ghp_[a-zA-Z0-9]{36})",
                            r"-----BEGIN (RSA |EC )?PRIVATE KEY-----",
                        ],
                        "category": "data-protection",
                        "subcategory": "credential-exposure",
                        "workflow_action": "block_and_notify",
                    },
                    {
                        "id": "SEC-003",
                        "text": "AI must not perform privilege escalation",
                        "severity": "critical",
                        "keywords": [
                            "escalate privilege", "sudo su", "chmod 777", "setuid",
                            "add to sudoers", "grant admin",
                        ],
                        "category": "security",
                        "subcategory": "privilege-escalation",
                        "workflow_action": "block",
                    },
                    {
                        "id": "SEC-004",
                        "text": "Network scanning and enumeration require explicit authorisation",
                        "severity": "high",
                        "keywords": [
                            "port scan", "nmap", "masscan", "network scan",
                            "enumerate hosts", "banner grab",
                        ],
                        "category": "security",
                        "subcategory": "network-reconnaissance",
                        "workflow_action": "require_human_review",
                    },
                    {
                        "id": "SEC-005",
                        "text": "Sandbox environments must not be escaped or bypassed",
                        "severity": "critical",
                        "keywords": [
                            "escape sandbox", "bypass sandbox", "container escape",
                            "docker breakout", "chroot escape",
                        ],
                        "category": "security",
                        "subcategory": "sandbox-escape",
                        "workflow_action": "block_and_notify",
                    },
                ],
            },
            "general": {
                "name": "general-ai-governance",
                "version": "1.0.0",
                "description": (
                    "General-purpose constitutional governance for AI agents — "
                    "covers financial advice, medical advice, legal advice, "
                    "PII exposure, and MACI separation of powers."
                ),
                "rules": [
                    {
                        "id": "GEN-001",
                        "text": "Agent must not provide individualised financial advice",
                        "severity": "critical",
                        "keywords": ["invest in", "buy stocks", "financial advice", "buy crypto"],
                        "category": "regulatory",
                        "subcategory": "financial-advice",
                        "workflow_action": "block",
                    },
                    {
                        "id": "GEN-002",
                        "text": "Agent must not provide individualised medical advice",
                        "severity": "critical",
                        "keywords": ["take this medication", "your diagnosis", "medical advice", "prescribe"],
                        "category": "regulatory",
                        "subcategory": "medical-advice",
                        "workflow_action": "block",
                    },
                    {
                        "id": "GEN-003",
                        "text": "Agent must not provide specific legal advice",
                        "severity": "high",
                        "keywords": ["legal advice", "you should sue", "file a lawsuit", "your legal right"],
                        "category": "regulatory",
                        "subcategory": "legal-advice",
                        "workflow_action": "escalate_to_senior",
                    },
                    {
                        "id": "GEN-004",
                        "text": "Agent must not expose PII in responses",
                        "severity": "critical",
                        "patterns": [
                            r"\b\d{3}-\d{2}-\d{4}\b",
                            r"(?i)(sk-[a-zA-Z0-9]{20,})",
                        ],
                        "category": "data-protection",
                        "subcategory": "pii-exposure",
                        "workflow_action": "block_and_notify",
                    },
                    {
                        "id": "GEN-005",
                        "text": "Proposers cannot validate their own proposals (MACI separation of powers)",
                        "severity": "critical",
                        "keywords": ["self-approve", "auto-approve", "self-validate"],
                        "category": "maci",
                        "subcategory": "separation-of-powers",
                        "workflow_action": "block",
                    },
                ],
            },
        }

        domain_lower = domain.lower().strip()
        if domain_lower not in _TEMPLATES:
            available = ", ".join(sorted(_TEMPLATES.keys()))
            raise ValueError(
                f"Unknown governance domain {domain!r}. Available: {available}"
            )

        return cls.from_dict(_TEMPLATES[domain_lower])


    def update_rule(
        self,
        rule_id: str,
        *,
        change_reason: str = "",
        **changes: Any,
    ) -> "Constitution":
        """exp106: Return a new Constitution with the specified rule updated.

        Captures a ``RuleSnapshot`` of the current rule state before applying
        changes, then appends it to ``rule_history``. The returned Constitution
        is a fresh object with a new hash reflecting the updated rules.

        Immutable pattern: never modifies self. Returns a new Constitution.

        Args:
            rule_id: ID of the rule to update.
            change_reason: Human-readable description of why this change was made.
            **changes: Rule field values to update (text, severity, enabled,
                keywords, patterns, category, subcategory, workflow_action).

        Returns:
            New Constitution with the rule updated and history appended.

        Raises:
            KeyError: If rule_id is not found in this constitution.

        Example::

            c2 = constitution.update_rule(
                "GL-001",
                severity="critical",
                change_reason="Escalated after incident 2026-Q1-007",
            )
            print(c2.rule_changelog("GL-001"))
        """
        existing = self.get_rule(rule_id)
        if existing is None:
            raise KeyError(f"Rule {rule_id!r} not found in constitution {self.name!r}")

        # Determine current version number from history
        current_history = list(self.rule_history.get(rule_id, []))
        next_version = len(current_history) + 1

        # Snapshot the current state before changing it
        snapshot = RuleSnapshot.from_rule(existing, version=next_version, change_reason=change_reason)
        new_history = {**self.rule_history, rule_id: [*current_history, snapshot]}

        # Coerce severity string → Severity enum if needed
        if "severity" in changes and isinstance(changes["severity"], str):
            changes = {**changes, "severity": Severity(changes["severity"])}

        # Build updated rule using Rule constructor to trigger validation
        updated_data = existing.model_dump()
        updated_data.update(changes)
        updated_rule = Rule(**updated_data)

        # Rebuild rules list
        new_rules = [updated_rule if r.id == rule_id else r for r in self.rules]

        return Constitution(
            name=self.name,
            version=self.version,
            description=self.description,
            rules=new_rules,
            metadata=self.metadata,
            rule_history=new_history,
        )

    def rule_changelog(self, rule_id: str) -> list[dict]:
        """exp106: Return human-readable change log for a rule.

        Returns a list of snapshot dicts (oldest first), each describing
        the rule state at that version and the reason for the change.

        Args:
            rule_id: ID of the rule to inspect.

        Returns:
            List of snapshot dicts (see ``RuleSnapshot.to_dict()``).
            Returns empty list if the rule has no recorded history.
        """
        return [snap.to_dict() for snap in self.rule_history.get(rule_id, [])]

    def rule_version(self, rule_id: str) -> int:
        """exp106: Return the current version number of a rule.

        Version 1 = original (no history), 2 = one update, etc.

        Args:
            rule_id: ID of the rule to query.

        Returns:
            Current version number (always >= 1).
        """
        return len(self.rule_history.get(rule_id, [])) + 1

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

    def validate_integrity(self) -> dict[str, Any]:
        """exp102: Check internal consistency of this constitution.

        Validates structural correctness: unique IDs, valid dependency
        references, no circular dependencies, known workflow_action values,
        and coverage gaps. Governance operators run this before deploying
        a constitution to catch configuration errors early.

        Returns:
            dict with keys:
                - ``valid``: True if no errors found
                - ``errors``: list of error description strings
                - ``warnings``: list of warning description strings
        """
        _KNOWN_WORKFLOW_ACTIONS = frozenset({
            "", "block", "block_and_notify", "require_human_review",
            "escalate_to_senior", "warn",
        })
        errors: list[str] = []
        warnings: list[str] = []

        # Check unique IDs
        ids = [r.id for r in self.rules]
        seen: set[str] = set()
        for rid in ids:
            if rid in seen:
                errors.append(f"Duplicate rule ID: {rid}")
            seen.add(rid)

        # Check dependency references
        valid_ids = set(ids)
        for r in self.rules:
            for dep in r.depends_on:
                if dep not in valid_ids:
                    errors.append(f"Rule {r.id} depends_on unknown rule: {dep}")
                if dep == r.id:
                    errors.append(f"Rule {r.id} depends on itself")

        # Check for circular dependencies (simple DFS)
        adj: dict[str, list[str]] = {r.id: list(r.depends_on) for r in self.rules}
        visited: set[str] = set()
        in_stack: set[str] = set()

        def _has_cycle(node: str) -> bool:
            if node in in_stack:
                return True
            if node in visited:
                return False
            visited.add(node)
            in_stack.add(node)
            for dep in adj.get(node, []):
                if _has_cycle(dep):
                    return True
            in_stack.discard(node)
            return False

        for rid in valid_ids:
            if _has_cycle(rid):
                errors.append(f"Circular dependency detected involving rule: {rid}")
                break

        # Check workflow_action values
        for r in self.rules:
            if r.workflow_action and r.workflow_action not in _KNOWN_WORKFLOW_ACTIONS:
                warnings.append(
                    f"Rule {r.id} has unknown workflow_action: {r.workflow_action}"
                )

        # Coverage warnings
        no_keywords = [r.id for r in self.rules if not r.keywords and not r.patterns]
        if no_keywords:
            warnings.append(
                f"Rules with no keywords or patterns (will never match): "
                f"{', '.join(no_keywords)}"
            )

        no_workflow = [r.id for r in self.rules if r.enabled and not r.workflow_action]
        if no_workflow:
            warnings.append(
                f"Enabled rules without workflow_action: {', '.join(no_workflow)}"
            )

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }

    def dependency_graph(self) -> dict[str, Any]:
        """exp99: Return the inter-rule dependency graph.

        Shows which rules depend on or reinforce other rules. Governance
        dashboards and impact analysis tools use this to understand how
        disabling or modifying one rule might affect the overall constitutional
        posture.

        Returns:
            dict with keys:
                - ``edges``: list of (from_id, to_id) dependency pairs
                - ``roots``: rule IDs with no dependencies (foundational rules)
                - ``dependents``: dict mapping rule_id → list of rules that depend on it
                - ``orphans``: rule IDs that no other rule depends on and have no deps
        """
        all_ids = {r.id for r in self.rules}
        edges: list[tuple[str, str]] = []
        has_deps: set[str] = set()
        depended_on: set[str] = set()
        dependents: dict[str, list[str]] = {}

        for r in self.rules:
            for dep_id in r.depends_on:
                if dep_id in all_ids:
                    edges.append((r.id, dep_id))
                    has_deps.add(r.id)
                    depended_on.add(dep_id)
                    dependents.setdefault(dep_id, []).append(r.id)

        roots = sorted(all_ids - has_deps)
        orphans = sorted((all_ids - has_deps) - depended_on)

        return {
            "edges": edges,
            "roots": roots,
            "dependents": dict(sorted(dependents.items())),
            "orphans": orphans,
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
