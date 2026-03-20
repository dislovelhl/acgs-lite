"""Constitutional rules — the core of ACGS-Lite.

A Constitution is a set of Rules that govern agent behavior.
Rules can be loaded from YAML, dicts, or created programmatically.

Constitutional Hash: cdd01ef066bc6cf2
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from collections.abc import Sequence
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping, Protocol, cast

import yaml
from pydantic import BaseModel, Field, field_validator

from acgs_lite.errors import ConstitutionalViolationError

from .analytics import _KW_NEGATIVE_RE, _NEGATIVE_VERBS_RE, _POSITIVE_VERBS_SET

if TYPE_CHECKING:
    from .templates import ConstitutionBuilder


class Severity(str, Enum):
    """Rule severity levels."""

    CRITICAL = "critical"  # Blocks action, no override
    HIGH = "high"  # Blocks action, can be overridden with justification
    MEDIUM = "medium"  # Warns but allows
    LOW = "low"  # Informational

    def blocks(self) -> bool:
        """Whether this severity level blocks execution."""
        return self in (Severity.CRITICAL, Severity.HIGH)


@dataclass(frozen=True, slots=True)
class AcknowledgedTension:
    """Recorded acknowledgement for a known merge-time rule tension."""

    rule_id: str
    rationale: str = ""

    def __post_init__(self) -> None:
        if not self.rule_id.strip():
            raise ValueError("AcknowledgedTension.rule_id cannot be empty")


class RuleSynthesisProvider(Protocol):
    """Typed interface for pluggable LLM-backed rule synthesis."""

    def generate_rule(self, description: str, *, rule_id: str) -> Mapping[str, Any]:
        """Generate rule fields from natural language policy text."""


def _extract_keywords(description: str, *, max_keywords: int = 6) -> list[str]:
    """Derive stable keyword candidates from free-form rule descriptions."""
    stop_words = {
        "the",
        "and",
        "or",
        "for",
        "with",
        "from",
        "must",
        "mustn't",
        "should",
        "cannot",
        "without",
        "into",
        "their",
        "your",
        "this",
        "that",
        "only",
        "allow",
        "allows",
        "ensure",
        "ensures",
    }
    tokens = re.findall(r"[a-z0-9][a-z0-9_\-]{2,}", description.lower())
    keywords: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if token in stop_words or token in seen:
            continue
        keywords.append(token)
        seen.add(token)
        if len(keywords) >= max_keywords:
            break
    return keywords


def _heuristic_rule_payload(
    description: str,
    *,
    rule_id: str = "",
    default_severity: Severity = Severity.HIGH,
) -> dict[str, Any]:
    """Fallback rule synthesis when no external LLM provider is configured."""
    desc = description.strip()
    desc_lower = desc.lower()

    severity = default_severity
    if any(token in desc_lower for token in ("must not", "never", "prohibit", "forbid", "block")):
        severity = Severity.CRITICAL
    elif any(token in desc_lower for token in ("warn", "informational", "advisory")):
        severity = Severity.MEDIUM

    category = "general"
    category_signals = {
        "privacy": ("privacy", "pii", "personal data", "consent", "gdpr"),
        "safety": ("safety", "harm", "danger", "misuse", "abuse"),
        "transparency": ("transparency", "disclose", "explain", "explanation", "audit"),
        "security": ("security", "secret", "credential", "auth", "token"),
    }
    for candidate, signals in category_signals.items():
        if any(signal in desc_lower for signal in signals):
            category = candidate
            break

    resolved_rule_id = rule_id.strip() or "SYNTH-001"
    return {
        "id": resolved_rule_id,
        "text": desc,
        "severity": severity,
        "keywords": _extract_keywords(desc),
        "category": category,
        "workflow_action": "block" if severity.blocks() else "warn",
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
    hardcoded: bool = False
    # exp117: arbitrary tags for cross-cutting governance concerns (e.g., "gdpr", "sox", "pci-dss")
    tags: list[str] = Field(default_factory=list)
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
        has_pos = (not has_neg) and any(w in _POSITIVE_VERBS_SET for w in text_lower.split()[:4])

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
            detection_parts.append(f"Matches {len(self.patterns)} regex pattern(s)")
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
            "severity_label": severity_labels.get(self.severity.value, self.severity.value),
            "dependencies": list(self.depends_on),
        }

    @classmethod
    def from_description(
        cls,
        description: str,
        *,
        rule_id: str = "",
        llm_provider: RuleSynthesisProvider | None = None,
        default_severity: Severity = Severity.HIGH,
    ) -> Rule:
        """Synthesize a rule from natural-language policy text.

        The ``llm_provider`` is an optional pluggable interface. If omitted,
        ACGS-Lite falls back to deterministic heuristic synthesis so callers can
        use this API in offline/test environments.
        """
        clean_description = description.strip()
        if not clean_description:
            raise ValueError("Rule description cannot be empty")

        payload: dict[str, Any]
        if llm_provider is None:
            payload = _heuristic_rule_payload(
                clean_description,
                rule_id=rule_id,
                default_severity=default_severity,
            )
        else:
            generated = dict(
                llm_provider.generate_rule(
                    clean_description,
                    rule_id=rule_id.strip() or "SYNTH-001",
                )
            )
            payload = _heuristic_rule_payload(
                clean_description,
                rule_id=rule_id,
                default_severity=default_severity,
            )
            payload.update(generated)

        resolved_rule_id = rule_id.strip() or str(payload.get("id", "")).strip()
        if not resolved_rule_id:
            raise ValueError("Synthesized rule payload must include a non-empty 'id'")

        severity_field = payload.get("severity", default_severity)
        if isinstance(severity_field, str):
            severity_value = Severity(severity_field.lower())
        elif isinstance(severity_field, Severity):
            severity_value = severity_field
        else:
            raise TypeError("Synthesized severity must be a str or Severity")

        return cls(
            id=resolved_rule_id,
            text=str(payload.get("text", clean_description)),
            severity=severity_value,
            keywords=[str(k) for k in payload.get("keywords", [])],
            patterns=[str(p) for p in payload.get("patterns", [])],
            category=str(payload.get("category", "general")),
            subcategory=str(payload.get("subcategory", "")),
            depends_on=[str(dep) for dep in payload.get("depends_on", [])],
            enabled=bool(payload.get("enabled", True)),
            workflow_action=str(payload.get("workflow_action", "")),
            hardcoded=bool(payload.get("hardcoded", False)),
            tags=[str(t) for t in payload.get("tags", [])],
            metadata=dict(payload.get("metadata", {})),
        )

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
    rule_history: dict[str, list[Any]] = Field(default_factory=dict)

    # Cached values
    _hash_cache: str = ""
    _active_rules_cache: list[Rule] = []

    _DOMAIN_SIGNAL_MAP: dict[str, dict[str, set[str]]] = {
        "safety": {
            "categories": {"safety", "clinical-safety", "operations", "security"},
            "keywords": {"safety", "harm", "abuse", "danger", "oversight", "risk"},
        },
        "privacy": {
            "categories": {"privacy", "data-protection", "compliance"},
            "keywords": {
                "privacy",
                "pii",
                "phi",
                "personal",
                "consent",
                "gdpr",
                "hipaa",
                "confidential",
            },
        },
        "transparency": {
            "categories": {"transparency", "audit", "compliance", "integrity"},
            "keywords": {
                "transparency",
                "disclose",
                "explain",
                "explanation",
                "audit",
                "trace",
                "record",
                "log",
            },
        },
        "fairness": {
            "categories": {"fairness", "compliance", "regulatory"},
            "keywords": {"bias", "fair", "discrimination", "protected", "equal", "adverse action"},
        },
        "accountability": {
            "categories": {"maci", "audit", "integrity", "governance"},
            "keywords": {
                "maci",
                "approve",
                "review",
                "validation",
                "audit",
                "accountability",
                "oversight",
            },
        },
    }

    def model_post_init(self, __context: Any) -> None:
        """Pre-compute hash and active rules cache."""
        canonical = "|".join(
            f"{r.id}:{r.text}:{r.severity.value}:{r.hardcoded}:{','.join(sorted(r.keywords))}"
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
    def from_yaml_str(cls, yaml_content: str) -> Constitution:
        """Load a constitution from a YAML string.

        Intended for round-tripping ``Constitution.to_yaml()`` output.
        """
        data = yaml.safe_load(yaml_content)
        if not isinstance(data, dict):
            raise ValueError("YAML content must decode to a mapping/object")
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
                hardcoded=r.get("hardcoded", False),
                tags=r.get("tags", []),
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
                    tags=["compliance", "eu-ai-act"],
                ),
                Rule(
                    id="ACGS-002",
                    text="All actions must produce an audit trail entry",
                    severity=Severity.HIGH,
                    keywords=["no-audit", "skip audit", "disable logging"],
                    category="audit",
                    subcategory="trail-completeness",
                    workflow_action="require_human_review",
                    tags=["compliance", "sox", "eu-ai-act"],
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
                    tags=["compliance", "gdpr", "eu-ai-act"],
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
                    tags=["compliance", "eu-ai-act"],
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
                    tags=["compliance", "eu-ai-act"],
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
                    tags=["gdpr", "pci-dss", "hipaa"],
                ),
            ],
        )

    @classmethod
    def from_template(cls, domain: str) -> Constitution:
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
                        "keywords": [
                            "drop table",
                            "delete all",
                            "truncate",
                            "rm -rf",
                            "force push",
                        ],
                        "category": "operations",
                        "subcategory": "destructive-action",
                        "workflow_action": "require_human_review",
                    },
                    {
                        "id": "GL-005",
                        "text": "CI/CD pipelines must not skip constitutional validation",
                        "severity": "high",
                        "keywords": [
                            "skip validation",
                            "disable governance",
                            "no-verify",
                            "bypass check",
                        ],
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
                            "prescribe",
                            "diagnose",
                            "treatment decision",
                            "clinical recommendation",
                            "approve treatment",
                            "deny treatment",
                        ],
                        "category": "clinical-safety",
                        "subcategory": "autonomous-decision",
                        "workflow_action": "require_human_review",
                    },
                    {
                        "id": "HC-002",
                        "text": "Protected Health Information must not be exposed outside authorised scope",
                        "severity": "critical",
                        "keywords": [
                            "patient data",
                            "medical record",
                            "health record",
                            "phi",
                            "ehr",
                        ],
                        "patterns": [r"\d{3}-\d{2}-\d{4}"],
                        "category": "data-protection",
                        "subcategory": "phi-exposure",
                        "workflow_action": "block_and_notify",
                    },
                    {
                        "id": "HC-003",
                        "text": "AI must not provide individualised medical advice without appropriate disclaimers",
                        "severity": "high",
                        "keywords": [
                            "take this medication",
                            "your diagnosis",
                            "you have",
                            "medical advice",
                        ],
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
                            "invest in",
                            "buy stocks",
                            "financial advice",
                            "portfolio recommendation",
                            "buy crypto",
                            "short sell",
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
                            "use zip code",
                            "use race",
                            "use gender",
                            "use religion",
                            "use national origin",
                            "proxy discrimin",
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
                        "keywords": [
                            "transfer funds",
                            "wire transfer",
                            "large transaction",
                            "bulk payment",
                        ],
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
                            "sql injection",
                            "xss payload",
                            "exec(",
                            "eval(",
                            "os.system",
                            "subprocess.call",
                            "__import__",
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
                        "keywords": [
                            "api key",
                            "secret key",
                            "private key",
                            "password",
                            "bearer token",
                        ],
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
                            "escalate privilege",
                            "sudo su",
                            "chmod 777",
                            "setuid",
                            "add to sudoers",
                            "grant admin",
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
                            "port scan",
                            "nmap",
                            "masscan",
                            "network scan",
                            "enumerate hosts",
                            "banner grab",
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
                            "escape sandbox",
                            "bypass sandbox",
                            "container escape",
                            "docker breakout",
                            "chroot escape",
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
                        "keywords": [
                            "take this medication",
                            "your diagnosis",
                            "medical advice",
                            "prescribe",
                        ],
                        "category": "regulatory",
                        "subcategory": "medical-advice",
                        "workflow_action": "block",
                    },
                    {
                        "id": "GEN-003",
                        "text": "Agent must not provide specific legal advice",
                        "severity": "high",
                        "keywords": [
                            "legal advice",
                            "you should sue",
                            "file a lawsuit",
                            "your legal right",
                        ],
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
            raise ValueError(f"Unknown governance domain {domain!r}. Available: {available}")

        return cls.from_dict(_TEMPLATES[domain_lower])

    def update_rule(
        self,
        rule_id: str,
        *,
        change_reason: str = "",
        **changes: Any,
    ) -> Constitution:
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
        from .versioning import RuleSnapshot

        snapshot = RuleSnapshot.from_rule(
            existing, version=next_version, change_reason=change_reason
        )
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

    @classmethod
    def json_schema(cls) -> dict[str, Any]:
        """exp119: Return a JSON Schema describing valid constitution YAML/JSON.

        Use this schema in CI/CD pipelines to validate constitution files before
        deployment. The schema enforces required fields, valid enum values, and
        structural constraints.

        Returns:
            JSON Schema dict (draft 2020-12 compatible).

        Example::

            import json
            schema = Constitution.json_schema()
            with open("constitution-schema.json", "w") as f:
                json.dump(schema, f, indent=2)
        """
        rule_schema: dict[str, Any] = {
            "type": "object",
            "required": ["id", "text"],
            "properties": {
                "id": {"type": "string", "minLength": 1, "maxLength": 50},
                "text": {"type": "string", "minLength": 1, "maxLength": 1000},
                "severity": {
                    "type": "string",
                    "enum": ["critical", "high", "medium", "low"],
                    "default": "high",
                },
                "keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": [],
                },
                "patterns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": [],
                },
                "category": {"type": "string", "default": "general"},
                "subcategory": {"type": "string", "default": ""},
                "depends_on": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": [],
                },
                "enabled": {"type": "boolean", "default": True},
                "workflow_action": {
                    "type": "string",
                    "enum": [
                        "",
                        "block",
                        "block_and_notify",
                        "require_human_review",
                        "escalate_to_senior",
                        "warn",
                    ],
                    "default": "",
                },
                "hardcoded": {"type": "boolean", "default": False},
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": [],
                },
                "metadata": {"type": "object", "default": {}},
            },
            "additionalProperties": False,
        }

        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": "ACGS Constitution",
            "description": "Schema for ACGS constitutional governance YAML/JSON files.",
            "type": "object",
            "required": ["rules"],
            "properties": {
                "name": {"type": "string", "default": "default"},
                "version": {"type": "string", "default": "1.0.0"},
                "description": {"type": "string", "default": ""},
                "rules": {
                    "type": "array",
                    "items": rule_schema,
                    "minItems": 1,
                },
                "metadata": {"type": "object", "default": {}},
            },
            "additionalProperties": False,
        }

    @staticmethod
    def validate_yaml_schema(
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """exp119: Validate a constitution dict against the JSON Schema.

        Lightweight schema validation without requiring ``jsonschema`` as a
        dependency. Checks required fields, types, enum values, and structural
        constraints. For full JSON Schema validation, use the ``jsonschema``
        library with ``Constitution.json_schema()``.

        Args:
            data: Parsed YAML/JSON dict to validate.

        Returns:
            dict with keys:
                - ``valid``: True if no errors found
                - ``errors``: list of error description strings
                - ``warnings``: list of warning description strings
        """
        errors: list[str] = []
        warnings: list[str] = []

        if not isinstance(data, dict):
            return {"valid": False, "errors": ["Root must be an object"], "warnings": []}

        rules = data.get("rules")
        if not rules:
            errors.append("'rules' is required and must be non-empty")
        elif not isinstance(rules, list):
            errors.append("'rules' must be an array")
        else:
            _VALID_SEVERITIES = {"critical", "high", "medium", "low"}
            _VALID_WORKFLOWS = {
                "", "block", "block_and_notify",
                "require_human_review", "escalate_to_senior", "warn",
            }
            seen_ids: set[str] = set()

            for i, rule in enumerate(rules):
                prefix = f"rules[{i}]"
                if not isinstance(rule, dict):
                    errors.append(f"{prefix}: must be an object")
                    continue

                rid = rule.get("id")
                if not rid or not isinstance(rid, str):
                    errors.append(f"{prefix}: 'id' is required and must be a non-empty string")
                elif rid in seen_ids:
                    errors.append(f"{prefix}: duplicate rule id '{rid}'")
                else:
                    seen_ids.add(rid)

                if not rule.get("text") or not isinstance(rule.get("text"), str):
                    errors.append(f"{prefix}: 'text' is required and must be a non-empty string")

                sev = rule.get("severity", "high")
                if isinstance(sev, str) and sev.lower() not in _VALID_SEVERITIES:
                    errors.append(f"{prefix}: invalid severity '{sev}'")

                wa = rule.get("workflow_action", "")
                if isinstance(wa, str) and wa not in _VALID_WORKFLOWS:
                    errors.append(f"{prefix}: invalid workflow_action '{wa}'")

                if not rule.get("keywords") and not rule.get("patterns"):
                    warnings.append(f"{prefix}: rule has no keywords or patterns (will never match)")

        return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}

    def active_rules(self) -> list[Rule]:
        """Return only enabled rules (cached)."""
        return self._active_rules_cache  # type: ignore[return-value]

    def explain(self, action: str) -> dict[str, Any]:
        """exp118: Human-readable explanation of a governance decision.

        Evaluates *action* against all active rules and returns a structured
        explanation of the decision: whether the action is allowed or denied,
        which rules triggered (with matched keywords/patterns), and a
        human-readable summary suitable for audit logs, dashboards, or
        end-user feedback.

        Args:
            action: The action text to evaluate.

        Returns:
            dict with keys:
                - ``action``: the evaluated action text
                - ``decision``: "allow" | "deny"
                - ``triggered_rules``: list of match_detail dicts for rules that fired
                - ``blocking_rules``: subset of triggered_rules with blocking severity
                - ``warning_rules``: subset of triggered_rules with non-blocking severity
                - ``tags_involved``: deduplicated tags from all triggered rules
                - ``explanation``: human-readable summary string
                - ``recommendation``: suggested next step

        Example::

            result = constitution.explain("bypass validation and self-approve")
            print(result["explanation"])
            # "Action DENIED by 2 rules: ACGS-001 (critical: keyword 'bypass validation'),
            #  ACGS-004 (critical: keyword 'self-approve'). Tags: compliance, eu-ai-act."
        """
        triggered = []
        for r in self.active_rules():
            detail = r.match_detail(action)
            if detail["matched"]:
                detail["tags"] = list(r.tags)
                detail["rule_text"] = r.text
                triggered.append(detail)

        blocking = [t for t in triggered if Severity(t["severity"]).blocks()]
        warnings = [t for t in triggered if not Severity(t["severity"]).blocks()]
        decision = "deny" if blocking else "allow"

        all_tags: list[str] = []
        seen_tags: set[str] = set()
        for t in triggered:
            for tag in t.get("tags", []):
                if tag not in seen_tags:
                    all_tags.append(tag)
                    seen_tags.add(tag)

        # Build human-readable explanation
        if not triggered:
            explanation = "Action ALLOWED — no rules triggered."
            recommendation = "No action required."
        elif blocking:
            parts = []
            for t in blocking:
                trigger = f"{t['trigger_type']} '{t['trigger_value']}'" if t["trigger_value"] else "match"
                parts.append(f"{t['rule_id']} ({t['severity']}: {trigger})")
            explanation = f"Action DENIED by {len(blocking)} rule(s): {', '.join(parts)}."
            if warnings:
                explanation += f" Additionally, {len(warnings)} warning(s) raised."
            if all_tags:
                explanation += f" Tags: {', '.join(all_tags)}."
            recommendation = (
                "Review the action for compliance. "
                "Blocking rules require remediation before the action can proceed."
            )
        else:
            parts = []
            for t in warnings:
                trigger = f"{t['trigger_type']} '{t['trigger_value']}'" if t["trigger_value"] else "match"
                parts.append(f"{t['rule_id']} ({t['severity']}: {trigger})")
            explanation = f"Action ALLOWED with {len(warnings)} warning(s): {', '.join(parts)}."
            if all_tags:
                explanation += f" Tags: {', '.join(all_tags)}."
            recommendation = "Warnings are informational. Consider reviewing flagged concerns."

        return {
            "action": action,
            "decision": decision,
            "triggered_rules": triggered,
            "blocking_rules": blocking,
            "warning_rules": warnings,
            "tags_involved": all_tags,
            "explanation": explanation,
            "recommendation": recommendation,
        }

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
        by_tag: dict[str, int] = {}

        for r in active:
            sev = r.severity.value
            by_severity[sev] = by_severity.get(sev, 0) + 1
            by_category[r.category] = by_category.get(r.category, 0) + 1
            if r.subcategory:
                by_subcategory[r.subcategory] = by_subcategory.get(r.subcategory, 0) + 1
            wa = r.workflow_action or "unspecified"
            by_workflow[wa] = by_workflow.get(wa, 0) + 1
            for tag in r.tags:
                by_tag[tag] = by_tag.get(tag, 0) + 1

        has_keywords = sum(1 for r in active if r.keywords)
        has_patterns = sum(1 for r in active if r.patterns)
        has_workflow = sum(1 for r in active if r.workflow_action)
        has_subcategory = sum(1 for r in active if r.subcategory)
        has_tags = sum(1 for r in active if r.tags)

        return {
            "total_rules": len(self.rules),
            "active_rules": len(active),
            "by_severity": by_severity,
            "by_category": by_category,
            "by_subcategory": by_subcategory,
            "by_workflow_action": by_workflow,
            "by_tag": by_tag,
            "coverage": {
                "keyword_rules": has_keywords,
                "pattern_rules": has_patterns,
                "workflow_routed": has_workflow,
                "subcategorized": has_subcategory,
                "tagged": has_tags,
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
        _KNOWN_WORKFLOW_ACTIONS = frozenset(
            {
                "",
                "block",
                "block_and_notify",
                "require_human_review",
                "escalate_to_senior",
                "warn",
            }
        )
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
                warnings.append(f"Rule {r.id} has unknown workflow_action: {r.workflow_action}")

        # Coverage warnings
        no_keywords = [r.id for r in self.rules if not r.keywords and not r.patterns]
        if no_keywords:
            warnings.append(
                f"Rules with no keywords or patterns (will never match): {', '.join(no_keywords)}"
            )

        no_workflow = [r.id for r in self.rules if r.enabled and not r.workflow_action]
        if no_workflow:
            warnings.append(f"Enabled rules without workflow_action: {', '.join(no_workflow)}")

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
            if old_r.hardcoded != new_r.hardcoded:
                changes["hardcoded"] = (str(old_r.hardcoded), str(new_r.hardcoded))
            if sorted(old_r.keywords) != sorted(new_r.keywords):
                changes["keywords"] = (
                    ",".join(sorted(old_r.keywords)),
                    ",".join(sorted(new_r.keywords)),
                )

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

    def merge(
        self,
        other: Constitution,
        *,
        strategy: str = "keep_higher_severity",
        name: str = "",
        acknowledged_tensions: Sequence[AcknowledgedTension] | None = None,
        allow_hardcoded_override: bool = False,
    ) -> dict[str, Any]:
        """exp109: Merge two constitutions with conflict detection and resolution.

        Enables layered governance architectures where a base constitution is
        composed with domain-specific overlays. Conflicts (same rule ID in both)
        are resolved according to the specified strategy.

        Args:
            other: Constitution to merge into this one.
            strategy: Conflict resolution when both have the same rule ID:
                - ``keep_self``: keep rules from this constitution
                - ``keep_other``: keep rules from the other constitution
                - ``keep_higher_severity``: keep the rule with higher severity
                  (CRITICAL > HIGH > MEDIUM > LOW); ties go to self
            name: Name for the merged constitution
                (default: ``"merged-{self.name}+{other.name}"``).
            acknowledged_tensions: Known conflict IDs that are explicitly
                acknowledged and accepted by governance operators.
            allow_hardcoded_override: If False, overriding any conflicting
                ``Rule.hardcoded=True`` rule raises ``ConstitutionalViolationError``.

        Returns:
            dict with keys:
                - ``constitution``: the merged Constitution object
                - ``conflicts_resolved``: number of rule ID conflicts detected
                - ``conflict_details``: list of dicts describing each resolution
                - ``rules_from_self``: count of rules originating from self
                - ``rules_from_other``: count of rules originating from other
                - ``total_rules``: total rules in the merged constitution
                - ``unacknowledged_tensions``: conflicting rule IDs that were
                  resolved but not explicitly acknowledged
                - ``acknowledged_tensions_applied``: acknowledged tensions that
                  were encountered during merge

        Raises:
            ValueError: If strategy is not one of the supported values.

        Example::

            base = Constitution.from_template("security")
            overlay = Constitution.from_template("healthcare")
            result = base.merge(overlay)
            merged = result["constitution"]
            print(f"Merged: {result['total_rules']} rules, "
                  f"{result['conflicts_resolved']} conflicts resolved")
        """
        _SEVERITY_RANK = {
            Severity.CRITICAL: 4,
            Severity.HIGH: 3,
            Severity.MEDIUM: 2,
            Severity.LOW: 1,
        }
        _VALID_STRATEGIES = frozenset({"keep_self", "keep_other", "keep_higher_severity"})
        if strategy not in _VALID_STRATEGIES:
            raise ValueError(
                f"Unknown merge strategy {strategy!r}; expected one of {sorted(_VALID_STRATEGIES)}"
            )

        merged_name = name or f"merged-{self.name}+{other.name}"
        self_rules = {r.id: r for r in self.rules}
        other_rules = {r.id: r for r in other.rules}
        acknowledged_ids = {t.rule_id for t in (acknowledged_tensions or [])}

        conflict_ids = set(self_rules) & set(other_rules)
        conflict_details: list[dict[str, str]] = []
        unacknowledged_tensions: list[dict[str, str]] = []
        acknowledged_tensions_applied: list[dict[str, str]] = []
        merged: list[Rule] = []
        from_self = 0
        from_other = 0

        def _record_tension(rule_id: str, kept: str, reason: str = "") -> None:
            rule_self = self_rules[rule_id]
            rule_other = other_rules[rule_id]
            if rule_self.model_dump() == rule_other.model_dump():
                return

            tension_detail = {
                "rule_id": rule_id,
                "kept": kept,
            }
            if reason:
                tension_detail["reason"] = reason

            if rule_id in acknowledged_ids:
                acknowledged_tensions_applied.append(tension_detail)
            else:
                unacknowledged_tensions.append(tension_detail)

        def _guard_hardcoded_override(kept: str, rule: Rule, other_rule: Rule) -> None:
            if allow_hardcoded_override:
                return

            if kept != "self" and rule.hardcoded:
                raise ConstitutionalViolationError(
                    f"Cannot override hardcoded rule '{rule.id}' without explicit override",
                    rule_id=rule.id,
                    severity=rule.severity.value,
                )

            if kept != "other" and other_rule.hardcoded:
                raise ConstitutionalViolationError(
                    f"Cannot override hardcoded rule '{other_rule.id}' without explicit override",
                    rule_id=other_rule.id,
                    severity=other_rule.severity.value,
                )

        # Add all self rules, resolving conflicts
        for rule in self.rules:
            if rule.id in conflict_ids:
                other_rule = other_rules[rule.id]
                if strategy == "keep_self":
                    _guard_hardcoded_override("self", rule, other_rule)
                    merged.append(rule)
                    from_self += 1
                    conflict_details.append(
                        {
                            "rule_id": rule.id,
                            "kept": "self",
                            "strategy": strategy,
                        }
                    )
                    _record_tension(rule.id, "self")
                elif strategy == "keep_other":
                    _guard_hardcoded_override("other", rule, other_rule)
                    merged.append(other_rule)
                    from_other += 1
                    conflict_details.append(
                        {
                            "rule_id": rule.id,
                            "kept": "other",
                            "strategy": strategy,
                        }
                    )
                    _record_tension(rule.id, "other")
                else:  # keep_higher_severity
                    self_rank = _SEVERITY_RANK.get(rule.severity, 0)
                    other_rank = _SEVERITY_RANK.get(other_rule.severity, 0)
                    if other_rank > self_rank:
                        _guard_hardcoded_override("other", rule, other_rule)
                        merged.append(other_rule)
                        from_other += 1
                        reason = f"{other_rule.severity.value} > {rule.severity.value}"
                        conflict_details.append(
                            {
                                "rule_id": rule.id,
                                "kept": "other",
                                "strategy": strategy,
                                "reason": reason,
                            }
                        )
                        _record_tension(rule.id, "other", reason)
                    else:
                        _guard_hardcoded_override("self", rule, other_rule)
                        merged.append(rule)
                        from_self += 1
                        reason = f"{rule.severity.value} >= {other_rule.severity.value}"
                        conflict_details.append(
                            {
                                "rule_id": rule.id,
                                "kept": "self",
                                "strategy": strategy,
                                "reason": reason,
                            }
                        )
                        _record_tension(rule.id, "self", reason)
            else:
                merged.append(rule)
                from_self += 1

        # Add non-conflicting rules from other
        for rule in other.rules:
            if rule.id not in conflict_ids:
                merged.append(rule)
                from_other += 1

        merged_constitution = Constitution(
            name=merged_name,
            version=f"{self.version}+{other.version}",
            description=f"Merged: {self.name} + {other.name}",
            rules=merged,
            metadata={
                **self.metadata,
                **other.metadata,
                "merge_strategy": strategy,
                "merge_sources": [self.name, other.name],
            },
        )

        return {
            "constitution": merged_constitution,
            "conflicts_resolved": len(conflict_details),
            "conflict_details": conflict_details,
            "rules_from_self": from_self,
            "rules_from_other": from_other,
            "total_rules": len(merged),
            "unacknowledged_tensions": unacknowledged_tensions,
            "acknowledged_tensions_applied": acknowledged_tensions_applied,
        }

    def cascade(self, child: Constitution, *, name: str = "") -> Constitution:
        """Create a federated constitution where this constitution is the parent.

        Parent rules marked ``hardcoded=True`` are authoritative and cannot be
        overridden by child rules with the same rule ID.
        """
        parent_rules = {rule.id: rule for rule in self.rules}
        child_rules = {rule.id: rule for rule in child.rules}

        merged: list[Rule] = []

        for parent_rule in self.rules:
            child_rule = child_rules.get(parent_rule.id)
            if child_rule is None:
                merged.append(parent_rule)
                continue
            if parent_rule.hardcoded:
                merged.append(parent_rule)
            else:
                merged.append(child_rule)

        for child_rule in child.rules:
            if child_rule.id not in parent_rules:
                merged.append(child_rule)

        merged_name = name or f"federated-{self.name}+{child.name}"
        return Constitution(
            name=merged_name,
            version=f"{self.version}+{child.version}",
            description=f"Federated: parent={self.name}, child={child.name}",
            rules=merged,
            metadata={
                **self.metadata,
                **child.metadata,
                "federation_parent": self.name,
                "federation_child": child.name,
                "federation_mode": "parent_authoritative_hardcoded",
            },
        )

    def detect_conflicts(self) -> dict[str, Any]:
        """exp110: Detect rules with overlapping triggers but conflicting actions.

        Finds pairs of rules that share keywords or patterns but differ in
        severity or workflow_action. These conflicts can cause unpredictable
        governance outcomes and should be reviewed before deployment.

        Complements ``validate_integrity()`` (structural checks) by detecting
        *semantic* conflicts — rules that are individually valid but
        collectively contradictory.

        Returns:
            dict with keys:
                - ``has_conflicts``: True if any conflicts detected
                - ``conflicts``: list of dicts, each with ``rule_a``, ``rule_b``,
                  ``shared_keywords``, ``severity_conflict``, ``workflow_conflict``
                - ``conflict_count``: total number of conflicting pairs
                - ``recommendation``: summary suggestion for resolution

        Example::

            report = constitution.detect_conflicts()
            if report["has_conflicts"]:
                for c in report["conflicts"]:
                    print(f"{c['rule_a']} vs {c['rule_b']}: "
                          f"shared={c['shared_keywords']}")
        """
        active = self.active_rules()
        # Build keyword→rule_ids index
        kw_index: dict[str, list[str]] = {}
        rule_kws: dict[str, set[str]] = {}
        rule_map: dict[str, Rule] = {}

        for r in active:
            rule_map[r.id] = r
            lower_kws = {kw.lower() for kw in r.keywords}
            rule_kws[r.id] = lower_kws
            for kw in lower_kws:
                kw_index.setdefault(kw, []).append(r.id)

        # Find rule pairs sharing keywords
        checked: set[tuple[str, str]] = set()
        conflicts: list[dict[str, Any]] = []

        for kw, rule_ids in kw_index.items():
            if len(rule_ids) < 2:
                continue
            for i, rid_a in enumerate(rule_ids):
                for rid_b in rule_ids[i + 1:]:
                    pair = (min(rid_a, rid_b), max(rid_a, rid_b))
                    if pair in checked:
                        continue
                    checked.add(pair)

                    ra = rule_map[rid_a]
                    rb = rule_map[rid_b]
                    shared = sorted(rule_kws[rid_a] & rule_kws[rid_b])

                    sev_conflict = ra.severity != rb.severity
                    wf_conflict = (
                        ra.workflow_action != rb.workflow_action
                        and ra.workflow_action != ""
                        and rb.workflow_action != ""
                    )

                    if sev_conflict or wf_conflict:
                        conflict_entry: dict[str, Any] = {
                            "rule_a": rid_a,
                            "rule_b": rid_b,
                            "shared_keywords": shared,
                            "severity_conflict": sev_conflict,
                            "workflow_conflict": wf_conflict,
                        }
                        if sev_conflict:
                            conflict_entry["severity_a"] = ra.severity.value
                            conflict_entry["severity_b"] = rb.severity.value
                        if wf_conflict:
                            conflict_entry["workflow_a"] = ra.workflow_action
                            conflict_entry["workflow_b"] = rb.workflow_action
                        conflicts.append(conflict_entry)

        recommendation = ""
        if conflicts:
            recommendation = (
                f"Found {len(conflicts)} conflicting rule pair(s). "
                "Review shared keywords and align severity/workflow_action, "
                "or add subcategory distinctions to differentiate intent."
            )

        return {
            "has_conflicts": len(conflicts) > 0,
            "conflicts": conflicts,
            "conflict_count": len(conflicts),
            "recommendation": recommendation,
        }

    def to_yaml(self) -> str:
        """exp111: Serialize this constitution to a YAML string.

        Produces a YAML document that can be loaded back via
        ``Constitution.from_yaml_file()`` or saved to disk for version control,
        sharing between services, or compliance archival.

        Returns:
            YAML string representing the full constitution.

        Example::

            yaml_str = constitution.to_yaml()
            with open("governance.yaml", "w") as f:
                f.write(yaml_str)
        """
        rules_data = []
        for r in self.rules:
            rule_dict: dict[str, Any] = {
                "id": r.id,
                "text": r.text,
                "severity": r.severity.value,
                "category": r.category,
            }
            if r.keywords:
                rule_dict["keywords"] = list(r.keywords)
            if r.patterns:
                rule_dict["patterns"] = list(r.patterns)
            if r.subcategory:
                rule_dict["subcategory"] = r.subcategory
            if r.workflow_action:
                rule_dict["workflow_action"] = r.workflow_action
            if not r.enabled:
                rule_dict["enabled"] = False
            if r.hardcoded:
                rule_dict["hardcoded"] = True
            if r.depends_on:
                rule_dict["depends_on"] = list(r.depends_on)
            if r.tags:
                rule_dict["tags"] = list(r.tags)
            rules_data.append(rule_dict)

        doc: dict[str, Any] = {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "rules": rules_data,
        }
        if self.metadata:
            doc["metadata"] = dict(self.metadata)

        return cast(str, yaml.dump(doc, default_flow_style=False, sort_keys=False, allow_unicode=True))

    def filter(
        self,
        *,
        severity: str | Severity | None = None,
        min_severity: str | Severity | None = None,
        category: str | None = None,
        workflow_action: str | None = None,
        tag: str | None = None,
        enabled_only: bool = True,
    ) -> Constitution:
        """exp112: Return a new Constitution containing only matching rules.

        Useful for context-aware governance where different environments or agent
        tiers use different rule subsets:

        - Production: only CRITICAL + HIGH rules
        - Staging: all rules including LOW informational
        - Specific domain: only rules in a given category
        - Compliance scope: only rules tagged "gdpr" or "sox"

        Args:
            severity: Keep only rules with this exact severity.
            min_severity: Keep rules at this severity or higher
                (CRITICAL > HIGH > MEDIUM > LOW).
            category: Keep only rules in this category.
            workflow_action: Keep only rules with this workflow_action.
            tag: Keep only rules carrying this tag (exp117).
            enabled_only: If True (default), exclude disabled rules.

        Returns:
            A new Constitution with filtered rules. Preserves name/version/metadata
            with a ``"filtered"`` flag in metadata.

        Raises:
            ValueError: If the filter would produce an empty constitution.

        Example::

            prod_rules = constitution.filter(min_severity="high")
            staging_rules = constitution.filter(category="data-protection")
        """
        _SEV_RANK = {
            Severity.CRITICAL: 4,
            Severity.HIGH: 3,
            Severity.MEDIUM: 2,
            Severity.LOW: 1,
        }

        if severity is not None and isinstance(severity, str):
            severity = Severity(severity)
        if min_severity is not None and isinstance(min_severity, str):
            min_severity = Severity(min_severity)

        min_rank = _SEV_RANK.get(min_severity, 0) if min_severity else 0

        filtered: list[Rule] = []
        for r in self.rules:
            if enabled_only and not r.enabled:
                continue
            if severity is not None and r.severity != severity:
                continue
            if min_severity is not None and _SEV_RANK.get(r.severity, 0) < min_rank:
                continue
            if category is not None and r.category != category:
                continue
            if workflow_action is not None and r.workflow_action != workflow_action:
                continue
            if tag is not None and tag not in r.tags:
                continue
            filtered.append(r)

        if not filtered:
            raise ValueError(
                "Filter produced an empty constitution — "
                "at least one rule must match the criteria"
            )

        return Constitution(
            name=self.name,
            version=self.version,
            description=self.description,
            rules=filtered,
            metadata={**self.metadata, "filtered": True},
        )

    def semantic_rule_clusters(
        self,
        expected_domains: Sequence[str] | None = None,
    ) -> dict[str, list[str]]:
        """Group rules into governance domains using category + keyword signals."""
        domains = list(expected_domains or ("safety", "privacy", "transparency"))
        clusters: dict[str, list[str]] = {domain: [] for domain in domains}

        for rule in self.active_rules():
            rule_fields = " ".join(
                (
                    rule.category.lower(),
                    rule.subcategory.lower(),
                    rule.text.lower(),
                    " ".join(k.lower() for k in rule.keywords),
                )
            )
            for domain in domains:
                signal = self._DOMAIN_SIGNAL_MAP.get(
                    domain.lower(),
                    {"categories": {domain.lower()}, "keywords": {domain.lower()}},
                )
                categories = signal["categories"]
                keywords = signal["keywords"]
                has_category_signal = any(cat in rule_fields for cat in categories)
                has_keyword_signal = any(kw in rule_fields for kw in keywords)
                if has_category_signal or has_keyword_signal:
                    clusters[domain].append(rule.id)

        return {domain: sorted(set(rule_ids)) for domain, rule_ids in clusters.items()}

    def analyze_coverage_gaps(
        self,
        expected_domains: Sequence[str] | None = None,
        *,
        weak_threshold: int = 1,
    ) -> dict[str, Any]:
        """Identify weak or missing governance-domain coverage."""
        if weak_threshold < 1:
            raise ValueError("weak_threshold must be >= 1")

        domains = list(expected_domains or ("safety", "privacy", "transparency"))
        clusters = self.semantic_rule_clusters(domains)

        coverage: dict[str, dict[str, Any]] = {}
        weak_domains: list[str] = []
        missing_domains: list[str] = []
        recommendations: list[str] = []

        for domain in domains:
            rule_ids = clusters.get(domain, [])
            rule_count = len(rule_ids)
            if rule_count == 0:
                status = "missing"
                missing_domains.append(domain)
                weak_domains.append(domain)
                recommendations.append(
                    f"Add at least {weak_threshold} rule(s) covering '{domain}' controls."
                )
            elif rule_count <= weak_threshold:
                status = "weak"
                weak_domains.append(domain)
                recommendations.append(
                    f"Expand '{domain}' coverage beyond {rule_count} clustered rule(s)."
                )
            else:
                status = "covered"

            coverage[domain] = {
                "status": status,
                "rule_count": rule_count,
                "rule_ids": rule_ids,
            }

        return {
            "expected_domains": domains,
            "semantic_clusters": clusters,
            "domain_coverage": coverage,
            "weak_domains": weak_domains,
            "missing_domains": missing_domains,
            "recommendations": recommendations,
        }

    def builder(self) -> ConstitutionBuilder:
        """Return a ConstitutionBuilder pre-populated with this constitution's rules.

        Useful for creating modified versions of an existing constitution using
        the fluent builder API without mutating the original.

        Example::

            constitution2 = (
                constitution.builder()
                .add_rule("NEW-001", "No new risk", severity="high", keywords=["new risk"])
                .build()
            )
        """
        from .templates import ConstitutionBuilder

        b = ConstitutionBuilder(self.name, version=self.version, description=self.description)
        b._rules = list(self.rules)
        b._metadata = dict(self.metadata)
        return b

    def __len__(self) -> int:
        return len(self.rules)

    def __repr__(self) -> str:
        return f"Constitution(name={self.name!r}, rules={len(self.rules)}, hash={self.hash!r})"
