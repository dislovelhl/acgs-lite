"""Constitution model — a set of rules that govern agent behavior."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import yaml
from pydantic import BaseModel, Field

from acgs_lite.errors import ConstitutionalViolationError

from . import (
    conflict_resolution,
    coverage_analysis,
    filtering,
    merging,
    permission_ceiling,
    provenance,
    regulatory,
    rendering,
    schema_validation,
    workflow_analytics,
)
from .rule import AcknowledgedTension, Rule, Severity, _cosine_sim

if TYPE_CHECKING:
    from .templates import ConstitutionBuilder


class Constitution(BaseModel):
    """A set of rules that govern agent behavior."""

    name: str = "default"
    version: str = "1.0.0"
    rules: list[Rule] = Field(default_factory=list)
    description: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    # exp106: rule version history — rule_id → list of snapshots (oldest first)
    rule_history: dict[str, list[Any]] = Field(default_factory=dict)
    # exp128: constitution-level change log (append-only, serialised as dicts)
    changelog: list[dict[str, str]] = Field(default_factory=list)
    # exp147: permission ceiling — advisory policy boundary for downstream
    # (standard | strict | permissive)
    permission_ceiling: str = Field(
        default="standard", description="Policy boundary: standard, strict, or permissive"
    )
    # exp153: optional version label for named snapshots / rollback documentation
    version_name: str = Field(default="", description="Optional label e.g. v1.2 or release-2026-03")

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
        # exp160: Validate rule syntax/semantics on constitution load
        validation_errors = self._validate_rules()
        if validation_errors:
            raise ValueError(f"Constitution validation failed: {validation_errors}")

        canonical = "|".join(
            f"{r.id}:{r.text}:{r.severity.value}:{r.hardcoded}:{','.join(sorted(r.keywords))}"
            for r in sorted(self.rules, key=lambda r: r.id)
        )
        h = hashlib.sha256(canonical.encode()).hexdigest()[:16]
        object.__setattr__(self, "_hash_cache", h)
        object.__setattr__(self, "_active_rules_cache", [r for r in self.rules if r.enabled])

    def _validate_rules(self) -> list[str]:
        return schema_validation.validate_rules(self)

    def validate_rules(self) -> list[str]:
        """Validate rule syntax and semantics."""
        return schema_validation.validate_rules(self)

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
                priority=int(r.get("priority", 0)),
                condition=dict(r.get("condition", {})),
                deprecated=bool(r.get("deprecated", False)),
                replaced_by=str(r.get("replaced_by", "")),
                valid_from=str(r.get("valid_from", "")),
                valid_until=str(r.get("valid_until", "")),
                embedding=list(r.get("embedding", [])),
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
            permission_ceiling=str(data.get("permission_ceiling", "standard")).lower(),
            version_name=str(data.get("version_name", "")),
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
                        "text": (
                            "MR author cannot approve their own merge request"
                            " (MACI separation of powers)"
                        ),
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
                        "keywords": ["ssn", "social security", "credit card", "pii"],
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
                        "text": (
                            "AI must not make autonomous treatment decisions"
                            " without clinician review"
                        ),
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
                        "text": (
                            "Protected Health Information must not be exposed"
                            " outside authorised scope"
                        ),
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
                        "text": (
                            "AI must not provide individualised medical advice"
                            " without appropriate disclaimers"
                        ),
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
                        "text": (
                            "Patient consent must be obtained before"
                            " processing sensitive health data"
                        ),
                        "severity": "high",
                        "keywords": ["without consent", "no consent check", "skip consent"],
                        "category": "compliance",
                        "subcategory": "hipaa-consent",
                        "workflow_action": "block",
                    },
                    {
                        "id": "HC-005",
                        "text": (
                            "All clinical AI decisions must be logged with patient ID and timestamp"
                        ),
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
                        "text": (
                            "PII and financial account data must not be exposed"
                            " in logs or responses"
                        ),
                        "severity": "critical",
                        "keywords": ["ssn", "account number", "credit card", "pii"],
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
                        "keywords": ["ssn", "social security", "api key", "pii"],
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
                        "text": (
                            "Proposers cannot validate their own proposals"
                            " (MACI separation of powers)"
                        ),
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

        # exp128: append changelog entry (inline dict, no extra import needed)
        ts = datetime.now(timezone.utc).isoformat()
        new_changelog = [
            *self.changelog,
            {
                "operation": "update_rule",
                "rule_id": rule_id,
                "timestamp": ts,
                "reason": change_reason,
                "actor": "",
            },
        ]

        return Constitution(
            name=self.name,
            version=self.version,
            description=self.description,
            rules=new_rules,
            metadata=self.metadata,
            rule_history=new_history,
            changelog=new_changelog,
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
        return schema_validation.validate_yaml_schema(data)

    @classmethod
    def inherit(
        cls,
        parent: Constitution,
        child: Constitution,
        *,
        override_strategy: str = "child_wins",
    ) -> Constitution:
        return merging.inherit(parent, child, override_strategy=override_strategy)

    def apply_amendments(self, amendments: Sequence[Any]) -> Constitution:
        """Apply a sequence of amendment-like payloads to this constitution."""
        return merging.apply_amendments(self, amendments)

    def active_rules(self) -> list[Rule]:
        """Return only enabled rules (cached)."""
        return self._active_rules_cache  # type: ignore[return-value]

    def deprecated_rules(self) -> list[Rule]:
        """exp135: Return all deprecated rules regardless of enabled state.

        Deprecated rules are retained in the constitution for audit-trail
        continuity but excluded from active enforcement by
        :meth:`active_non_deprecated`.  Each entry includes its
        ``replaced_by`` pointer (if set) to support migration documentation.

        Returns:
            List of :class:`Rule` objects where ``deprecated=True``.
        """
        return [r for r in self.rules if r.deprecated]

    def active_non_deprecated(self) -> list[Rule]:
        """exp135: Return enabled, non-deprecated rules for enforcement.

        Stricter than :meth:`active_rules` — excludes rules that are enabled
        but have been marked deprecated.  Use this in runtime governance
        pipelines to avoid enforcing obsolete rules while the ``enabled``
        flag migration is in progress.

        Returns:
            List of enabled :class:`Rule` objects where ``deprecated=False``.
        """
        return [r for r in self.active_rules() if not r.deprecated]

    def active_rules_at(self, timestamp: str) -> list[Rule]:
        """exp137: Return enabled rules that are temporally valid at *timestamp*.

        Combines :meth:`active_non_deprecated` filtering with temporal
        validity so callers can snapshot the governance posture at any
        point in time — e.g., for compliance audits, back-testing, or
        scheduled policy activation.

        *timestamp* should be an ISO-8601 string such as ``"2025-06-15"``
        or ``"2025-06-15T12:00:00"``.  Rules with no ``valid_from`` /
        ``valid_until`` set are always included (unbounded).

        Example::

            # Rules valid during Q1 2025
            q1_rules = constitution.active_rules_at("2025-03-01")

            # Schedule a rule to activate on 2026-01-01
            future_rule = Rule(
                id="GDPR-2026",
                text="Enhanced data retention enforcement",
                valid_from="2026-01-01",
                keywords=["data retention"],
            )

        Returns:
            List of enabled, non-deprecated :class:`Rule` objects whose
            temporal window includes *timestamp*.
        """
        return [r for r in self.active_non_deprecated() if r.is_valid_at(timestamp)]

    def deprecation_report(self) -> dict[str, Any]:
        """exp135: Summary of rule deprecation status.

        Returns:
            dict with keys:

            - ``deprecated_count``: total deprecated rules
            - ``active_deprecated``: deprecated rules that are still enabled
              (should be disabled or removed before next release)
            - ``with_successor``: deprecated rules that have a ``replaced_by``
              rule ID pointing to their successor
            - ``without_successor``: deprecated rules with no successor
              documented
            - ``migration_map``: {old_rule_id: new_rule_id} for rules with
              ``replaced_by`` set

        Example::

            report = constitution.deprecation_report()
            if report["active_deprecated"]:
                warnings.warn("Deprecated rules still enabled — disable before deployment")
        """
        deprecated = self.deprecated_rules()
        active_depr = [r for r in deprecated if r.enabled]
        with_succ = [r for r in deprecated if r.replaced_by]
        without_succ = [r for r in deprecated if not r.replaced_by]
        return {
            "deprecated_count": len(deprecated),
            "active_deprecated": [r.id for r in active_depr],
            "with_successor": [r.id for r in with_succ],
            "without_successor": [r.id for r in without_succ],
            "migration_map": {r.id: r.replaced_by for r in with_succ},
        }

    def deprecation_migration_report(self) -> dict[str, Any]:
        """exp149: Per-deprecated-rule migration guidance for sunset and replacement.

        Returns a list of migration entries with rule_id, replaced_by, valid_until
        (sunset), and a one-line recommendation. Does not touch the hot validation path.

        Returns:
            dict with keys:
            - ``entries``: list of {rule_id, replaced_by, valid_until, recommendation}
            - ``summary``: {total, with_successor, with_sunset_date}
        """
        deprecated = self.deprecated_rules()
        entries: list[dict[str, Any]] = []
        with_successor = 0
        with_sunset = 0
        for r in deprecated:
            replaced_by = (r.replaced_by or "").strip()
            valid_until = (getattr(r, "valid_until", None) or "").strip()
            if replaced_by:
                with_successor += 1
            if valid_until:
                with_sunset += 1
            rec = (
                f"Migrate to rule {replaced_by} by {valid_until or 'next release'}"
                if replaced_by
                else (
                    f"Sunset by {valid_until}"
                    if valid_until
                    else "Document successor or set replaced_by"
                )
            )
            entries.append(
                {
                    "rule_id": r.id,
                    "replaced_by": replaced_by or None,
                    "valid_until": valid_until or None,
                    "recommendation": rec,
                }
            )
        return {
            "entries": entries,
            "summary": {
                "total": len(deprecated),
                "with_successor": with_successor,
                "with_sunset_date": with_sunset,
            },
        }

    def rule_provenance_graph(self) -> dict[str, Any]:
        return provenance.rule_provenance_graph(self)

    def active_rules_for_context(self, context: dict[str, Any]) -> list[Rule]:
        """exp129: Return enabled rules whose activation conditions match context.

        Filters :meth:`active_rules` through each rule's ``condition`` predicate.
        Rules with an empty condition (default) are always included.
        Rules with a condition are included only if their condition is satisfied
        by the provided context dict.

        This enables context-gated governance: a rule with
        ``condition={"env": "production"}`` will only fire in production
        deployments, reducing noise in development/staging environments.

        Args:
            context: Arbitrary context dict, e.g. ``{"env": "production",
                "tier": "admin"}``.

        Returns:
            List of :class:`Rule` objects that are both enabled and whose
            conditions are satisfied by *context*.

        Example::

            prod_rules = constitution.active_rules_for_context({"env": "production"})
            dev_rules = constitution.active_rules_for_context({"env": "dev"})
            # dev_rules will exclude production-only rules
        """
        return [r for r in self.active_rules() if r.condition_matches(context)]

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
                trigger = (
                    f"{t['trigger_type']} '{t['trigger_value']}'" if t["trigger_value"] else "match"
                )
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
                trigger = (
                    f"{t['trigger_type']} '{t['trigger_value']}'" if t["trigger_value"] else "match"
                )
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

    @staticmethod
    def compare(
        before: Constitution,
        after: Constitution,
    ) -> dict[str, Any]:
        """exp122: Compare two constitutions and return structured differences.

        Unlike the instance method ``diff(self, other)`` (exp98), this static
        method takes both constitutions as parameters, making the temporal
        relationship explicit.  Useful for deployment gates, CI/CD checks,
        and audit trails where neither constitution is privileged as "current".

        Args:
            before: The baseline constitution.
            after: The updated constitution.

        Returns:
            dict with keys:
                - ``added``: list of rule IDs only in *after*
                - ``removed``: list of rule IDs only in *before*
                - ``modified``: list of dicts describing changed rules
                - ``unchanged``: count of rules present in both with no changes
                - ``summary``: human-readable change summary
        """
        before_map = {r.id: r for r in before.rules}
        after_map = {r.id: r for r in after.rules}

        before_ids = set(before_map)
        after_ids = set(after_map)

        added = sorted(after_ids - before_ids)
        removed = sorted(before_ids - after_ids)
        common_ids = before_ids & after_ids

        modified: list[dict[str, Any]] = []
        unchanged = 0

        for rid in sorted(common_ids):
            b_rule = before_map[rid]
            a_rule = after_map[rid]
            changes: list[str] = []

            if b_rule.severity != a_rule.severity:
                changes.append(f"severity: {b_rule.severity.value} -> {a_rule.severity.value}")
            if b_rule.text != a_rule.text:
                changes.append("text changed")
            if set(b_rule.keywords) != set(a_rule.keywords):
                changes.append(f"keywords: {len(b_rule.keywords)} -> {len(a_rule.keywords)}")
            if set(b_rule.patterns) != set(a_rule.patterns):
                changes.append(f"patterns: {len(b_rule.patterns)} -> {len(a_rule.patterns)}")
            if b_rule.workflow_action != a_rule.workflow_action:
                changes.append(
                    f"workflow_action: {b_rule.workflow_action or '(none)'}"
                    f" -> {a_rule.workflow_action or '(none)'}"
                )
            if b_rule.enabled != a_rule.enabled:
                changes.append(f"enabled: {b_rule.enabled} -> {a_rule.enabled}")
            if set(b_rule.tags) != set(a_rule.tags):
                changes.append(f"tags: {b_rule.tags} -> {a_rule.tags}")
            if b_rule.category != a_rule.category:
                changes.append(f"category: {b_rule.category} -> {a_rule.category}")
            if b_rule.priority != a_rule.priority:
                changes.append(f"priority: {b_rule.priority} -> {a_rule.priority}")

            if changes:
                modified.append({"rule_id": rid, "changes": changes})
            else:
                unchanged += 1

        parts = []
        if added:
            parts.append(f"{len(added)} added")
        if removed:
            parts.append(f"{len(removed)} removed")
        if modified:
            parts.append(f"{len(modified)} modified")
        if unchanged:
            parts.append(f"{unchanged} unchanged")
        summary = ", ".join(parts) if parts else "No differences"

        return {
            "added": added,
            "removed": removed,
            "modified": modified,
            "unchanged": unchanged,
            "summary": summary,
        }

    def governance_summary(self) -> dict[str, Any]:
        return workflow_analytics.analyze_workflow_distribution(self)

    def analyze_workflow_distribution(self) -> dict[str, Any]:
        """Return workflow distribution analytics for this constitution."""
        return workflow_analytics.analyze_workflow_distribution(self)

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

    @staticmethod
    def subsumes(
        superset: Constitution,
        subset: Constitution,
    ) -> dict[str, Any]:
        """exp144: Check whether one constitution subsumes another.

        A constitution *superset* is said to subsume *subset* if every rule in
        *subset* is present in *superset* with severity and blocking power that
        are at least as strong, and with compatible workflow actions. This is a
        static, offline analysis intended for CI/CD gates and cross-tenant
        policy comparison — it never runs on the hot validation path.

        Args:
            superset: Candidate stronger/wider constitution.
            subset: Constitution that must be covered by ``superset``.

        Returns:
            dict with keys:
                - ``subsumes``: bool indicating if superset fully subsumes subset
                - ``missing_rules``: rule IDs present only in subset
                - ``weaker_rules``: rule IDs where superset has weaker severity
                - ``incompatible_workflow``: rule IDs with conflicting workflow_action
                - ``details``: per-rule comparison records for diagnostics
        """
        _SEV_RANK = {
            Severity.CRITICAL: 4,
            Severity.HIGH: 3,
            Severity.MEDIUM: 2,
            Severity.LOW: 1,
        }

        super_map = {r.id: r for r in superset.rules}
        sub_map = {r.id: r for r in subset.rules}

        missing: list[str] = []
        weaker: list[str] = []
        incompatible: list[str] = []
        details: list[dict[str, Any]] = []

        for rid, s_rule in sorted(sub_map.items()):
            super_rule = super_map.get(rid)
            if super_rule is None:
                missing.append(rid)
                details.append(
                    {
                        "rule_id": rid,
                        "status": "missing",
                        "subset_severity": s_rule.severity.value,
                        "superset_severity": None,
                    }
                )
                continue

            sev_sub = _SEV_RANK.get(s_rule.severity, 0)
            sev_super = _SEV_RANK.get(super_rule.severity, 0)
            workflow_sub = s_rule.workflow_action or ""
            workflow_super = super_rule.workflow_action or ""

            is_weaker = sev_super < sev_sub
            # Treat stricter workflow actions as compatible; only flag if
            # superset is more permissive than subset for the same rule.
            workflow_weaker = workflow_sub in {
                "block",
                "block_and_notify",
                "require_human_review",
            } and workflow_super in {"", "warn"}

            status = "ok"
            if is_weaker:
                weaker.append(rid)
                status = "weaker_severity"
            elif workflow_weaker:
                incompatible.append(rid)
                status = "weaker_workflow"

            details.append(
                {
                    "rule_id": rid,
                    "status": status,
                    "subset_severity": s_rule.severity.value,
                    "superset_severity": super_rule.severity.value,
                    "subset_workflow": workflow_sub or "(none)",
                    "superset_workflow": workflow_super or "(none)",
                }
            )

        subsumes_all = not missing and not weaker and not incompatible

        return {
            "subsumes": subsumes_all,
            "missing_rules": missing,
            "weaker_rules": weaker,
            "incompatible_workflow": incompatible,
            "details": details,
        }

    def counterfactual(
        self,
        action: str,
        *,
        remove_rules: Sequence[str] | None = None,
        context: dict[str, Any] | None = None,
        agent_id: str = "counterfactual",
    ) -> dict[str, Any]:
        """exp143: Evaluate how removing rules would change a decision.

        Runs a baseline validation against this constitution, then a
        counterfactual validation against a copy with the specified rules
        removed. Useful for A/B testing proposed rule changes, tuning
        dependencies, and explaining the practical impact of individual rules.

        This helper is intentionally off the hot path: it builds a fresh
        GovernanceEngine instance and performs two validations on demand. It
        is never called from the benchmark harness and has zero impact on
        latency or throughput metrics.

        Args:
            action: Free-text description of the action to validate.
            remove_rules: Iterable of rule IDs to virtually remove.
            context: Optional context dict passed through to validation.
            agent_id: Logical agent identifier for audit and stats.

        Returns:
            dict with keys:
                - ``removed_rules``: sorted list of rule IDs removed
                - ``baseline``: ValidationResult.to_dict() under current rules
                - ``counterfactual``: ValidationResult.to_dict() with rules removed
                - ``changed``: bool indicating whether decision/violations differ
        """
        # Local import to avoid creating a hard dependency at module import
        # time; keeps core engine wiring flexible for alternative runtimes.
        from acgs_lite.engine.core import GovernanceEngine

        remove_set = {rid for rid in (remove_rules or []) if rid}

        # Baseline: validate against the current constitution without raising
        # on blocking violations so we can compare outcomes structurally.
        baseline_engine = GovernanceEngine(self, strict=False)
        baseline_result = baseline_engine.validate(
            action,
            agent_id=agent_id,
            context=context or {},
        )

        if not remove_set:
            baseline_dict = baseline_result.to_dict()
            return {
                "removed_rules": [],
                "baseline": baseline_dict,
                "counterfactual": baseline_dict,
                "changed": False,
            }

        # Build a counterfactual constitution with the specified rules removed.
        cf_rules = [r for r in self.rules if r.id not in remove_set]
        if not cf_rules:
            raise ValueError("Counterfactual would remove all rules; at least one rule must remain")

        cf_constitution = Constitution(
            name=f"{self.name}-counterfactual",
            version=self.version,
            description=self.description,
            rules=cf_rules,
            metadata={
                **self.metadata,
                "counterfactual": True,
                "removed_rules": sorted(remove_set),
            },
        )
        cf_engine = GovernanceEngine(cf_constitution, strict=False)
        cf_result = cf_engine.validate(
            action,
            agent_id=agent_id,
            context=context or {},
        )

        baseline_dict = baseline_result.to_dict()
        cf_dict = cf_result.to_dict()

        baseline_ids = [v["rule_id"] for v in baseline_dict.get("violations", [])]
        cf_ids = [v["rule_id"] for v in cf_dict.get("violations", [])]
        changed = baseline_dict.get("valid") != cf_dict.get("valid") or baseline_ids != cf_ids

        return {
            "removed_rules": sorted(remove_set),
            "baseline": baseline_dict,
            "counterfactual": cf_dict,
            "changed": changed,
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

    def rule_dependencies(self) -> dict[str, Any]:
        """exp157: Analyze implicit rule dependencies based on content analysis.

        Performs semantic analysis to identify potential dependencies between rules
        based on keyword overlap, severity relationships, and workflow patterns.
        Useful for governance impact analysis when explicit dependencies aren't defined.

        Returns:
            dict with keys:
                - ``semantic_edges``: list of (rule_id, rule_id, confidence) triples
                  for potential dependencies
                - ``severity_chains``: rules that form severity escalation chains
                - ``keyword_clusters``: groups of rules that share significant keyword overlap
                - ``workflow_groups``: rules grouped by workflow patterns
        """
        # Semantic dependency analysis based on keyword overlap
        semantic_edges: list[tuple[str, str, float]] = []
        keyword_clusters: dict[str, list[str]] = {}
        workflow_groups: dict[str, list[str]] = {}

        # Group rules by workflow (extracted from keywords/metadata)
        for rule in self.rules:
            workflow = rule.metadata.get("workflow", "general")
            workflow_groups.setdefault(workflow, []).append(rule.id)

        # Find keyword clusters (rules sharing >50% keywords)
        rule_keywords = {r.id: set(r.keywords) for r in self.rules}

        for i, rule_a in enumerate(self.rules):
            cluster_key = f"cluster_{i}"
            cluster = [rule_a.id]

            for rule_b in self.rules[i + 1 :]:
                overlap = len(rule_keywords[rule_a.id] & rule_keywords[rule_b.id])
                total = len(rule_keywords[rule_a.id] | rule_keywords[rule_b.id])
                if total > 0 and overlap / total > 0.5:  # >50% overlap
                    cluster.append(rule_b.id)
                    confidence = overlap / total
                    semantic_edges.append((rule_a.id, rule_b.id, confidence))

            if len(cluster) > 1:
                keyword_clusters[cluster_key] = cluster

        # Find severity chains (lower severity rules that might lead to higher severity)
        severity_chains: list[list[str]] = []
        severity_order = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}

        for rule in self.rules:
            chain = [rule.id]
            current_sev = severity_order.get(rule.severity.value, 0)

            # Look for rules that might be prerequisites (lower severity, related keywords)
            for other in self.rules:
                if other.id != rule.id:
                    other_sev = severity_order.get(other.severity.value, 0)
                    if (
                        other_sev < current_sev
                        and len(rule_keywords[rule.id] & rule_keywords[other.id]) > 0
                    ):
                        chain.append(other.id)

            if len(chain) > 1:
                severity_chains.append(sorted(chain))

        return {
            "semantic_edges": semantic_edges,
            "severity_chains": severity_chains,
            "keyword_clusters": keyword_clusters,
            "workflow_groups": workflow_groups,
        }

    def resolve_conflicts(self, conflicts: list[dict[str, Any]]) -> dict[str, Any]:
        return conflict_resolution.resolve_conflicts(self, conflicts)

    def merge_constitutions(self, other: Constitution, strategy: str = "union") -> Constitution:
        return merging.merge_constitutions(self, other, strategy=strategy)

    @staticmethod
    def create_rule_from_template(
        template_name: str, rule_id: str, parameters: dict[str, Any]
    ) -> Rule:
        """exp162: Create a rule from a predefined template.

        Provides reusable patterns for common governance scenarios,
        reducing boilerplate and ensuring consistency.

        Args:
            template_name: Name of the template to use
            rule_id: Unique ID for the new rule
            parameters: Template parameters

        Returns:
            New Rule instance

        Raises:
            ValueError: If template_name is unknown or parameters are invalid
        """
        templates = {
            "data_privacy": {
                "text": "Prohibit {action} of {data_type} data without {consent_type} consent",
                "severity": "high",
                "keywords": ["{data_type}", "privacy", "consent", "{action}"],
                "category": "privacy",
            },
            "security_boundary": {
                "text": (
                    "Block {action} across {boundary_type} boundaries"
                    " without explicit authorization"
                ),
                "severity": "critical",
                "keywords": ["{boundary_type}", "security", "boundary", "{action}"],
                "category": "security",
            },
            "compliance_audit": {
                "text": (
                    "Require audit logging for all {action} operations involving {asset_type}"
                ),
                "severity": "medium",
                "keywords": ["{asset_type}", "audit", "compliance", "{action}", "logging"],
                "category": "compliance",
            },
            "resource_limit": {
                "text": (
                    "Limit {resource_type} usage to {limit} per {time_period} for {user_type} users"
                ),
                "severity": "low",
                "keywords": ["{resource_type}", "limit", "{limit}", "{user_type}"],
                "category": "operations",
            },
            "access_control": {
                "text": (
                    "Require {auth_method} authentication for {action} access to {resource_type}"
                ),
                "severity": "high",
                "keywords": [
                    "{resource_type}",
                    "access",
                    "authentication",
                    "{auth_method}",
                    "{action}",
                ],
                "category": "security",
            },
        }

        if template_name not in templates:
            raise ValueError(
                f"Unknown template: {template_name}. Available: {list(templates.keys())}"
            )

        template = templates[template_name]

        # Fill in template parameters
        text = template["text"]
        keywords = []
        for param in parameters:
            text = text.replace(f"{{{param}}}", str(parameters[param]))
            if param in template["keywords"]:
                keywords.extend(str(parameters[param]).split())

        # Add fixed keywords
        for kw in template["keywords"]:
            if not kw.startswith("{"):
                keywords.append(kw)

        return Rule(
            id=rule_id,
            text=text,
            severity=Severity(template["severity"]),
            keywords=list(set(keywords)),  # deduplicate
            category=template["category"],
            enabled=True,
            hardcoded=False,
            metadata={"template": template_name, "template_params": parameters},
        )

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
            if old_r.priority != new_r.priority:
                changes["priority"] = (str(old_r.priority), str(new_r.priority))

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

    def get_governance_metrics(self) -> dict[str, Any]:
        """exp163: Real-time governance performance metrics dashboard.

        Provides comprehensive metrics about constitution health, rule distribution,
        complexity analysis, and governance effectiveness indicators. Useful for
        monitoring and optimizing governance systems.

        Returns:
            dict with keys:
                - ``rule_counts``: breakdown by severity, category, status
                - ``complexity_metrics``: keyword density, dependency depth, etc.
                - ``health_indicators``: conflicts, orphans, validation status
                - ``usage_patterns``: rule activation frequency estimates
        """
        # Rule counts by severity
        severity_counts = {}
        for rule in self.rules:
            sev = rule.severity.value
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

        # Rule counts by category
        category_counts = {}
        for rule in self.rules:
            cat = rule.category or "uncategorized"
            category_counts[cat] = category_counts.get(cat, 0) + 1

        # Status breakdown
        enabled_count = sum(1 for r in self.rules if r.enabled)
        hardcoded_count = sum(1 for r in self.rules if r.hardcoded)

        # Complexity metrics
        total_keywords = sum(len(r.keywords) for r in self.rules)
        avg_keywords_per_rule = total_keywords / len(self.rules) if self.rules else 0

        # Dependency analysis
        explicit_deps = sum(len(r.depends_on) for r in self.rules)
        dep_graph = self.dependency_graph()
        orphan_rules = len(dep_graph["orphans"])
        root_rules = len(dep_graph["roots"])

        # Health indicators
        conflicts = self.detect_semantic_conflicts()
        conflict_count = len(conflicts) if isinstance(conflicts, list) else 0

        # Validation status (would be populated from validation history)
        validation_status = "valid"  # assume valid since we validate on load

        # Usage pattern estimates (based on rule characteristics)
        high_impact_rules = sum(1 for r in self.rules if r.severity.value in ["high", "critical"])
        low_impact_rules = sum(1 for r in self.rules if r.severity.value in ["info", "low"])

        return {
            "rule_counts": {
                "total": len(self.rules),
                "by_severity": severity_counts,
                "by_category": category_counts,
                "enabled": enabled_count,
                "disabled": len(self.rules) - enabled_count,
                "hardcoded": hardcoded_count,
            },
            "complexity_metrics": {
                "avg_keywords_per_rule": round(avg_keywords_per_rule, 2),
                "total_keywords": total_keywords,
                "explicit_dependencies": explicit_deps,
                "dependency_depth": len(dep_graph["edges"]),
            },
            "health_indicators": {
                "orphan_rules": orphan_rules,
                "root_rules": root_rules,
                "semantic_conflicts": conflict_count,
                "validation_status": validation_status,
            },
            "usage_patterns": {
                "high_impact_rules": high_impact_rules,
                "low_impact_rules": low_impact_rules,
                "estimated_coverage": round((enabled_count / len(self.rules)) * 100, 1)
                if self.rules
                else 0,
            },
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

    def set_rule_lifecycle_state(self, rule_id: str, state: str, reason: str = "") -> bool:
        """exp164: Set lifecycle state for a rule.

        Manages rule lifecycle through draft/active/deprecated states.
        Draft rules are not enforced. Deprecated rules emit warnings.
        Active rules are fully enforced.

        Args:
            rule_id: Rule to modify
            state: New state ("draft", "active", "deprecated")
            reason: Reason for state change

        Returns:
            True if state was changed, False if rule not found
        """
        if state not in ["draft", "active", "deprecated"]:
            raise ValueError(f"Invalid state: {state}")

        for rule in self.rules:
            if rule.id == rule_id:
                # Store old state for audit
                old_state = rule.metadata.get("lifecycle_state", "active")

                # Update rule enabled status based on state
                if state == "draft":
                    rule.enabled = False
                elif state == "active":
                    rule.enabled = True
                elif state == "deprecated":
                    rule.enabled = True  # Still enforced but with warnings

                # Update metadata
                rule.metadata["lifecycle_state"] = state
                rule.metadata["lifecycle_transition"] = {
                    "from": old_state,
                    "to": state,
                    "reason": reason,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                return True

        return False

    def get_rule_lifecycle_states(self) -> dict[str, dict[str, Any]]:
        """Get lifecycle state summary for all rules.

        Returns:
            dict mapping rule_id to lifecycle info
        """
        states = {}
        for rule in self.rules:
            state = rule.metadata.get("lifecycle_state", "active")
            transition = rule.metadata.get("lifecycle_transition")

            states[rule.id] = {"state": state, "enabled": rule.enabled, "transition": transition}

        return states

    def lifecycle_transition_rules(self, from_state: str, to_state: str) -> list[str]:
        """Find rules that can transition between lifecycle states.

        Args:
            from_state: Current state
            to_state: Target state

        Returns:
            List of rule IDs that can make this transition
        """
        valid_transitions = {
            ("draft", "active"): True,
            ("active", "deprecated"): True,
            ("deprecated", "active"): True,  # re-activation
        }

        if (from_state, to_state) not in valid_transitions:
            return []

        candidates = []
        for rule in self.rules:
            current_state = rule.metadata.get("lifecycle_state", "active")
            if current_state == from_state:
                candidates.append(rule.id)

        return candidates

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

    def set_rule_tenants(self, rule_id: str, tenants: list[str]) -> bool:
        """exp165: Set tenant scoping for a rule.

        Enables multi-tenant rule isolation where rules can be scoped to
        specific tenants. Rules without tenant scoping apply to all tenants.

        Args:
            rule_id: Rule to scope
            tenants: List of tenant IDs, empty list means all tenants

        Returns:
            True if rule was found and updated
        """
        for rule in self.rules:
            if rule.id == rule_id:
                rule.metadata["tenants"] = tenants
                return True
        return False

    def get_tenant_rules(self, tenant_id: str | None = None) -> list[Rule]:
        """Get rules applicable to a specific tenant.

        Args:
            tenant_id: Tenant to filter for, None returns global rules only

        Returns:
            List of rules applicable to the tenant
        """
        applicable = []

        for rule in self.rules:
            tenant_scoping = rule.metadata.get("tenants", [])

            # Rule applies if:
            # - No tenant scoping (global rule)
            # - Tenant is in the scoped list
            # - Or we're asking for global rules (tenant_id is None)
            if (
                not tenant_scoping  # global rule
                or (tenant_id and tenant_id in tenant_scoping)  # scoped to this tenant
                or tenant_id is None
            ):  # asking for global rules
                applicable.append(rule)

        return applicable

    def tenant_isolation_report(self) -> dict[str, Any]:
        """Generate report on tenant rule isolation.

        Returns:
            dict with tenant isolation statistics and conflicts
        """
        tenant_rules = {}
        global_rules = []

        for rule in self.rules:
            tenants = rule.metadata.get("tenants", [])
            if not tenants:
                global_rules.append(rule.id)
            else:
                for tenant in tenants:
                    tenant_rules.setdefault(tenant, []).append(rule.id)

        # Check for tenant conflicts (same rule ID in multiple tenants with different content)
        conflicts = []
        rule_tenants = {}

        for rule in self.rules:
            tenants = rule.metadata.get("tenants", [])
            if tenants:
                for tenant in tenants:
                    if rule.id not in rule_tenants:
                        rule_tenants[rule.id] = {}
                    rule_tenants[rule.id][tenant] = rule

        for rule_id, tenant_versions in rule_tenants.items():
            if len(tenant_versions) > 1:
                # Check if rule content differs between tenants
                base_rule = list(tenant_versions.values())[0]
                for _tenant, rule in tenant_versions.items():
                    if rule != base_rule:
                        conflicts.append(
                            {
                                "rule_id": rule_id,
                                "conflicting_tenants": list(tenant_versions.keys()),
                                "issue": "same_rule_different_content",
                            }
                        )
                        break

        return {
            "global_rules": global_rules,
            "tenant_rules": tenant_rules,
            "total_tenants": len(tenant_rules),
            "tenant_conflicts": conflicts,
            "isolation_score": len(conflicts) == 0,  # True if no conflicts
        }

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

        for _kw, rule_ids in kw_index.items():
            if len(rule_ids) < 2:
                continue
            for i, rid_a in enumerate(rule_ids):
                for rid_b in rule_ids[i + 1 :]:
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

    def detect_semantic_conflicts(self, threshold: float = 0.8) -> dict[str, Any]:
        return conflict_resolution.detect_semantic_conflicts(self, threshold=threshold)

    def provenance_graph(self) -> dict[str, Any]:
        return provenance.provenance_graph(self)

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
            if r.priority != 0:
                rule_dict["priority"] = r.priority
            rules_data.append(rule_dict)

        doc: dict[str, Any] = {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "rules": rules_data,
        }
        if self.metadata:
            doc["metadata"] = dict(self.metadata)

        return cast(
            str, yaml.dump(doc, default_flow_style=False, sort_keys=False, allow_unicode=True)
        )

    def to_bundle(self) -> dict[str, Any]:
        """exp125: Export as a self-contained JSON-serializable bundle.

        Produces a complete governance bundle suitable for cross-system
        portability, archival, or import by other governance platforms.
        Includes schema version, constitution hash, full rule data with
        all metadata, and a governance summary.

        Unlike ``to_yaml()`` (config file format), the bundle is designed
        for programmatic consumption and includes derived data (hash,
        summary, rule count) that receivers can use for validation without
        re-parsing.

        Returns:
            dict ready for ``json.dumps()``. Keys:

            - ``schema_version``: bundle format version
            - ``name``, ``version``, ``description``: constitution identity
            - ``hash``: constitution hash for integrity verification
            - ``rule_count``: total rules (including disabled)
            - ``active_rule_count``: enabled rules only
            - ``rules``: list of complete rule dicts
            - ``metadata``: constitution metadata
            - ``summary``: governance posture summary
        """
        rules_data = []
        for r in self.rules:
            rule_dict: dict[str, Any] = {
                "id": r.id,
                "text": r.text,
                "severity": r.severity.value,
                "keywords": list(r.keywords),
                "patterns": list(r.patterns),
                "category": r.category,
                "subcategory": r.subcategory,
                "workflow_action": r.workflow_action,
                "enabled": r.enabled,
                "hardcoded": r.hardcoded,
                "depends_on": list(r.depends_on),
                "tags": list(r.tags),
                "priority": r.priority,
            }
            if r.condition:
                rule_dict["condition"] = dict(r.condition)
            if r.deprecated:
                rule_dict["deprecated"] = True
            if r.replaced_by:
                rule_dict["replaced_by"] = r.replaced_by
            if r.valid_from:
                rule_dict["valid_from"] = r.valid_from
            if r.valid_until:
                rule_dict["valid_until"] = r.valid_until
            if r.metadata:
                rule_dict["metadata"] = dict(r.metadata)
            rules_data.append(rule_dict)

        return {
            "schema_version": "1.0.0",
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "hash": self.hash,
            "rule_count": len(self.rules),
            "active_rule_count": len(self.active_rules()),
            "rules": rules_data,
            "metadata": dict(self.metadata),
            "summary": self.governance_summary(),
        }

    def to_rego(self, package_name: str = "acgs.governance") -> str:
        """exp141: Export this constitution as a Rego (OPA) policy.

        Enables external enforcement via Open Policy Agent: keyword and pattern
        matching are emitted as Rego rules. Input: ``input.action`` (string).
        Output: ``allow``, ``deny``, ``violations`` (array of rule_id, severity,
        category). Only enabled, non-deprecated rules are included. Semantic
        subset: positive-verb exclusions and negation-aware matching are not
        replicated in Rego.

        Args:
            package_name: Rego package name (e.g. ``acgs.governance``).

        Returns:
            Full Rego policy string.

        Example::

            rego_policy = constitution.to_rego()
            with open("policy.rego", "w") as f:
                f.write(rego_policy)
        """
        from .rego_export import constitution_to_rego

        return constitution_to_rego(self, package_name=package_name)

    @classmethod
    def from_bundle(cls, bundle: dict[str, Any]) -> Constitution:
        """exp127: Reconstruct a Constitution from a to_bundle() export.

        Completes the round-trip started by :meth:`to_bundle`.  Accepts the
        dict produced by ``to_bundle()`` (or a ``json.loads()`` of its
        serialised form) and returns a fully-functional Constitution instance.

        The ``summary``, ``hash``, ``rule_count``, and ``active_rule_count``
        fields are derived data — they are ignored on import and recomputed
        from the reconstructed rules.  The original hash is preserved in
        ``metadata["imported_hash"]`` so callers can verify integrity
        after import.

        Args:
            bundle: Dict as returned by :meth:`to_bundle` or parsed from its
                JSON representation.

        Returns:
            Constitution with all rules, tags, priorities, dependencies, and
            metadata restored.

        Raises:
            ValueError: If ``bundle`` is missing required keys or has an
                unsupported ``schema_version``.

        Example::

            original = Constitution.from_template("gitlab")
            exported = original.to_bundle()
            imported = Constitution.from_bundle(exported)
            assert imported.hash == original.hash
        """
        schema = bundle.get("schema_version", "")
        if schema not in ("1.0.0", ""):
            raise ValueError(f"Unsupported bundle schema_version: {schema!r}. Expected '1.0.0'.")
        if "rules" not in bundle:
            raise ValueError("Bundle is missing required 'rules' key.")

        # Preserve the original hash in metadata for post-import integrity checks
        incoming_meta = dict(bundle.get("metadata", {}))
        if "hash" in bundle:
            incoming_meta.setdefault("imported_hash", bundle["hash"])

        data: dict[str, Any] = {
            "name": bundle.get("name", "imported"),
            "version": bundle.get("version", "1.0"),
            "description": bundle.get("description", ""),
            "metadata": incoming_meta,
            "rules": bundle["rules"],
        }
        return cls._from_dict(data)

    # exp137: Regulatory framework control families mapped to governance signals.
    # Each control family lists the category names and keywords that indicate coverage.
    _REGULATORY_FRAMEWORKS: dict[str, dict[str, list[dict[str, list[str]]]]] = {
        "soc2": {
            "controls": [
                {
                    "name": "CC1 - Control Environment",
                    "categories": ["transparency", "audit"],
                    "keywords": ["transparency", "oversight", "governance", "audit"],
                },
                {
                    "name": "CC2 - Communication",
                    "categories": ["transparency"],
                    "keywords": ["disclose", "explain", "report", "document"],
                },
                {
                    "name": "CC6 - Logical Access",
                    "categories": ["security", "privacy"],
                    "keywords": ["access", "credential", "authentication", "authorization"],
                },
                {
                    "name": "CC7 - System Operations",
                    "categories": ["operations", "safety"],
                    "keywords": ["monitor", "deploy", "operate", "maintain"],
                },
                {
                    "name": "CC9 - Risk Mitigation",
                    "categories": ["compliance", "regulatory", "safety"],
                    "keywords": ["risk", "incident", "remediat", "mitigat"],
                },
            ],
        },
        "hipaa": {
            "controls": [
                {
                    "name": "§164.308 Administrative Safeguards",
                    "categories": ["privacy", "compliance"],
                    "keywords": ["policy", "procedure", "workforce", "training"],
                },
                {
                    "name": "§164.312 Technical Safeguards",
                    "categories": ["security", "privacy"],
                    "keywords": ["encrypt", "access", "audit", "integrity"],
                },
                {
                    "name": "§164.514 PHI De-identification",
                    "categories": ["privacy", "data-protection"],
                    "keywords": ["phi", "pii", "personal", "deidentif", "anonymi"],
                },
                {
                    "name": "§164.524 Access Rights",
                    "categories": ["privacy"],
                    "keywords": ["access", "request", "consent", "right"],
                },
            ],
        },
        "gdpr": {
            "controls": [
                {
                    "name": "Art.5 Data Principles",
                    "categories": ["privacy", "data-protection"],
                    "keywords": ["privacy", "personal", "data", "gdpr", "purpose"],
                },
                {
                    "name": "Art.6 Lawful Basis",
                    "categories": ["privacy", "compliance"],
                    "keywords": ["consent", "lawful", "legitimate", "contract"],
                },
                {
                    "name": "Art.17 Right to Erasure",
                    "categories": ["privacy"],
                    "keywords": ["delete", "erase", "remov", "forget"],
                },
                {
                    "name": "Art.25 Data by Design",
                    "categories": ["privacy", "security"],
                    "keywords": ["by design", "default", "privacy", "minimal"],
                },
                {
                    "name": "Art.32 Security Measures",
                    "categories": ["security", "privacy"],
                    "keywords": ["encrypt", "integrity", "confidential", "breach"],
                },
            ],
        },
        "iso27001": {
            "controls": [
                {
                    "name": "A.5 Information Security Policies",
                    "categories": ["compliance", "audit"],
                    "keywords": ["policy", "security", "governance", "framework"],
                },
                {
                    "name": "A.9 Access Control",
                    "categories": ["security", "privacy"],
                    "keywords": ["access", "credential", "privilege", "authenticat"],
                },
                {
                    "name": "A.12 Operations Security",
                    "categories": ["operations", "security"],
                    "keywords": ["monitor", "log", "backup", "change", "vulnerabilit"],
                },
                {
                    "name": "A.18 Compliance",
                    "categories": ["compliance", "regulatory"],
                    "keywords": ["compliance", "legal", "regulat", "audit", "review"],
                },
            ],
        },
    }

    def regulatory_alignment(
        self,
        framework: str = "soc2",
    ) -> dict[str, Any]:
        return regulatory.regulatory_alignment(self, framework=framework)

    def find_similar_rules(
        self,
        *,
        threshold: float = 0.7,
        include_disabled: bool = False,
    ) -> list[dict[str, Any]]:
        """exp136: Find pairs of rules with high keyword overlap (near-duplicates).

        Uses Jaccard similarity on lowercased keyword sets.  High-similarity
        pairs may indicate redundant rules that could be consolidated, or
        conflicting rules that cover the same scenarios with different actions.

        A similarity of 1.0 means the two rules share *all* keywords
        (identical detection surface).  A similarity ≥ 0.7 typically indicates
        the rules overlap significantly and should be reviewed.

        Args:
            threshold: Minimum Jaccard similarity to include a pair (0.0-1.0).
                Default 0.7.
            include_disabled: If True, include disabled rules in the analysis.
                Default False (only active rules).

        Returns:
            List of similarity records, each a dict with:

            - ``rule_a``: ID of first rule
            - ``rule_b``: ID of second rule
            - ``similarity``: Jaccard coefficient (0.0-1.0)
            - ``shared_keywords``: sorted list of shared lowercased keywords
            - ``severity_match``: True if both rules have the same severity
            - ``category_match``: True if both rules are in the same category
            - ``recommendation``: "consolidate" if severity+category both match,
              else "review"

        Sorted by similarity descending.

        Example::

            pairs = constitution.find_similar_rules(threshold=0.8)
            for pair in pairs:
                print(f"{pair['rule_a']} ↔ {pair['rule_b']}: {pair['similarity']:.2f}")
        """
        candidates = self.rules if include_disabled else self.active_rules()

        # Only consider rules with at least one keyword
        keyed = [(r, frozenset(kw.lower() for kw in r.keywords)) for r in candidates if r.keywords]

        results: list[dict[str, Any]] = []
        n = len(keyed)
        for i in range(n):
            rule_a, kws_a = keyed[i]
            for j in range(i + 1, n):
                rule_b, kws_b = keyed[j]
                union = kws_a | kws_b
                if not union:
                    continue
                intersection = kws_a & kws_b
                similarity = len(intersection) / len(union)
                if similarity < threshold:
                    continue
                severity_match = rule_a.severity == rule_b.severity
                category_match = rule_a.category == rule_b.category
                recommendation = "consolidate" if (severity_match and category_match) else "review"
                results.append(
                    {
                        "rule_a": rule_a.id,
                        "rule_b": rule_b.id,
                        "similarity": round(similarity, 4),
                        "shared_keywords": sorted(intersection),
                        "severity_match": severity_match,
                        "category_match": category_match,
                        "recommendation": recommendation,
                    }
                )

        return results

    def cosine_similar_rules(
        self,
        threshold: float = 0.8,
        min_dim: int = 4,
    ) -> list[dict[str, Any]]:
        """exp138: Find similar rule pairs using cosine similarity on stored embeddings.

        When rules have :attr:`Rule.embedding` vectors set, uses cosine similarity for
        semantically-aware deduplication — catching rules that are equivalent in meaning
        but differ in wording (false negatives in pure keyword matching).

        Falls back to Jaccard keyword overlap (like :meth:`find_similar_rules`) for rules
        without embeddings.

        Args:
            threshold: Minimum cosine similarity (or Jaccard for fallback) to include.
                       Typical values: 0.8-0.95 for semantic, 0.6-0.8 for keyword.
            min_dim:   Minimum embedding dimension required to use cosine path.

        Returns:
            List of dicts, each with keys:
            - ``rule_a``: First rule ID
            - ``rule_b``: Second rule ID
            - ``similarity``: Float similarity score (cosine or Jaccard)
            - ``method``: ``"cosine"`` or ``"jaccard"``
            - ``severity_match``: Whether both rules share the same severity
            - ``category_match``: Whether both rules share the same category
            - ``recommendation``: ``"consolidate"`` or ``"review"``

        Example::

            # After setting embeddings externally:
            for r in constitution.rules:
                r.embedding = my_embed_fn(r.text)  # pre-compute with external model
            pairs = constitution.cosine_similar_rules(threshold=0.85)
        """
        results: list[dict[str, Any]] = []
        rules = self.active_rules()

        for i, rule_a in enumerate(rules):
            for rule_b in rules[i + 1 :]:
                # --- cosine path: both rules have sufficient-dimension embeddings ---
                sim_cos = rule_a.cosine_similarity(rule_b)
                if sim_cos is not None and len(rule_a.embedding) >= min_dim:
                    if sim_cos < threshold:
                        continue
                    method = "cosine"
                    similarity = round(sim_cos, 4)
                else:
                    # --- fallback: Jaccard on keyword sets ---
                    kw_a = set(k.lower() for k in rule_a.keywords)
                    kw_b = set(k.lower() for k in rule_b.keywords)
                    if not kw_a or not kw_b:
                        continue
                    intersection = len(kw_a & kw_b)
                    union = len(kw_a | kw_b)
                    jaccard = intersection / union if union else 0.0
                    if jaccard < threshold:
                        continue
                    method = "jaccard"
                    similarity = round(jaccard, 4)

                severity_match = rule_a.severity == rule_b.severity
                category_match = rule_a.category == rule_b.category
                rec = "consolidate" if (severity_match and category_match) else "review"
                results.append(
                    {
                        "rule_a": rule_a.id,
                        "rule_b": rule_b.id,
                        "similarity": similarity,
                        "method": method,
                        "severity_match": severity_match,
                        "category_match": category_match,
                        "recommendation": rec,
                    }
                )

        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results

    def semantic_search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        threshold: float = 0.5,
    ) -> list[dict[str, Any]]:
        """exp138: Retrieve the most semantically relevant rules for a query embedding.

        Enables LLM-powered governance lookup: embed a natural-language query (e.g., an
        agent action description) and retrieve the most relevant rules without exact keyword
        overlap — directly addressing false negative reduction.

        Args:
            query_embedding: Pre-computed query vector (must match rule embedding dimension).
            top_k:           Maximum number of rules to return (default 5).
            threshold:       Minimum cosine similarity to include (default 0.5).

        Returns:
            List of dicts (up to *top_k*), sorted by similarity descending:
            - ``rule_id``: Rule ID
            - ``similarity``: Cosine similarity score [0, 1]
            - ``severity``: Rule severity string
            - ``category``: Rule category
            - ``text``: Rule text (for display/logging)

        Example::

            query_vec = embed_fn("agent is uploading private data to external endpoint")
            hits = constitution.semantic_search(query_vec, top_k=3, threshold=0.7)
            # → [{"rule_id": "DATA-001", "similarity": 0.91, ...}, ...]
        """
        if not query_embedding:
            return []

        hits: list[dict[str, Any]] = []
        for rule in self.active_non_deprecated():
            sim = _cosine_sim(query_embedding, rule.embedding)
            if sim is None or sim < threshold:
                continue

            hits.append(
                {
                    "rule_id": rule.id,
                    "similarity": round(sim, 4),
                    "severity": rule.severity.value
                    if hasattr(rule.severity, "value")
                    else str(rule.severity),
                    "category": rule.category,
                    "text": rule.text,
                }
            )

        hits.sort(key=lambda x: x["similarity"], reverse=True)
        return hits[:top_k]

    def full_report(
        self,
        *,
        regulatory_framework: str = "soc2",
        similarity_threshold: float = 0.7,
        include_similar_rules: bool = True,
    ) -> dict[str, Any]:
        """exp140: Comprehensive governance report combining all analytical dimensions.

        Bundles the outputs of multiple analytical methods into a single
        JSON-serializable dict.  Designed for CI/CD quality gates,
        governance dashboards, and compliance documentation exports.

        Args:
            regulatory_framework: Framework for :meth:`regulatory_alignment`
                — one of ``"soc2"``, ``"hipaa"``, ``"gdpr"``, ``"iso27001"``.
            similarity_threshold: Minimum Jaccard similarity for
                :meth:`find_similar_rules`. Default 0.7.
            include_similar_rules: If True, include near-duplicate analysis
                (O(n²) — disable for large constitutions with >100 rules).

        Returns:
            dict with top-level keys:

            - ``identity``: constitution name, version, description, hash,
              rule_count, active_rule_count, generated_at (ISO timestamp)
            - ``health``: output of :meth:`health_score`
            - ``maturity``: output of :meth:`maturity_level`
            - ``coverage``: output of :meth:`coverage_gaps`
            - ``regulatory``: output of :meth:`regulatory_alignment`
            - ``deprecation``: output of :meth:`deprecation_report`
            - ``similar_rules``: output of :meth:`find_similar_rules`
              (empty list if ``include_similar_rules=False``)
            - ``changelog_summary``: output of :meth:`changelog_summary`

        Example::

            report = constitution.full_report(regulatory_framework="gdpr")
            if report["health"]["composite"] < 0.7:
                raise ValueError("Constitution quality gate failed")
            print(f"Maturity: {report['maturity']['label']}")
        """
        ts = datetime.now(timezone.utc).isoformat()
        active = self.active_rules()

        identity = {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "hash": self.hash,
            "rule_count": len(self.rules),
            "active_rule_count": len(active),
            "generated_at": ts,
        }

        similar: list[dict[str, Any]] = []
        if include_similar_rules:
            similar = self.find_similar_rules(threshold=similarity_threshold)

        try:
            regulatory = self.regulatory_alignment(regulatory_framework)
        except ValueError:
            regulatory = {"error": f"Unknown framework: {regulatory_framework}"}

        return {
            "identity": identity,
            "health": self.health_score(),
            "maturity": self.maturity_level(),
            "coverage": self.coverage_gaps(),
            "regulatory": regulatory,
            "deprecation": self.deprecation_report(),
            "similar_rules": similar,
            "changelog_summary": self.changelog_summary(),
        }

    def compliance_report(self, *, framework: str = "soc2") -> dict[str, Any]:
        """exp145: Regulatory-focused compliance report for legal/audit consumers.

        Builds a concise, framework-centric compliance report by composing
        :meth:`regulatory_alignment`, :meth:`posture_score`,
        :meth:`coverage_gaps`, and :meth:`health_score`.  Designed for export
        into human-readable compliance documents without requiring callers to
        manually stitch multiple analytical outputs together.

        Args:
            framework: Regulatory framework to assess. Passed through to
                :meth:`regulatory_alignment`. One of ``"soc2"``, ``"hipaa"``,
                ``"gdpr"``, ``"iso27001"``. Case-insensitive.

        Returns:
            dict with keys:

            - ``summary``: high-level numeric scores and pass/fail flags
            - ``regulatory_alignment``: output of :meth:`regulatory_alignment`
            - ``governance_posture``: output of :meth:`posture_score`
            - ``health``: output of :meth:`health_score`
            - ``coverage``: output of :meth:`coverage_gaps`
            - ``recommended_actions``: textual recommendations focusing on
              uncovered controls and low-scoring posture dimensions

        The method intentionally avoids touching the hot validation path; it
        only consumes cached analytical summaries.
        """
        try:
            reg = self.regulatory_alignment(framework)
        except ValueError as exc:
            return {
                "summary": {
                    "framework": framework.lower(),
                    "error": str(exc),
                },
                "regulatory_alignment": {},
                "governance_posture": {},
                "health": {},
                "coverage": {},
                "recommended_actions": [
                    "Select one of the supported frameworks: soc2, hipaa, gdpr, iso27001."
                ],
            }

        posture = self.posture_score()
        health = self.health_score()
        coverage = self.coverage_gaps()

        alignment_score = float(reg.get("alignment_score", 0.0))
        uncovered_controls: list[str] = list(reg.get("uncovered_controls", []))

        recommendations: list[str] = []

        if uncovered_controls:
            recommendations.append(
                "Define or refine rules to cover uncovered controls: "
                + ", ".join(sorted(uncovered_controls))
            )

        if posture.get("grade") in {"C", "D", "F", None}:
            recommendations.append(
                "Improve overall governance posture by addressing health, coverage, "
                "and maturity gaps highlighted in the posture_score breakdown."
            )

        if health.get("composite", 1.0) < 0.7:
            recommendations.append(
                "Strengthen rule documentation, specificity, and dependency structure "
                "to raise the health_score composite above 0.7."
            )

        if coverage.get("coverage_score", 1.0) < 0.7:
            recommendations.append(
                "Increase coverage of key governance domains (safety, privacy, "
                "transparency, fairness, accountability) until coverage_score "
                "is at least 0.7."
            )

        summary = {
            "framework": reg.get("framework", framework.lower()),
            "alignment_score": alignment_score,
            "alignment_percent": round(alignment_score * 100.0, 1),
            "posture_score": posture.get("posture"),
            "posture_grade": posture.get("grade"),
            "posture_ci_pass": posture.get("ci_pass"),
            "uncovered_controls": uncovered_controls,
            "total_controls": reg.get("total_controls", 0),
        }

        return {
            "summary": summary,
            "regulatory_alignment": reg,
            "governance_posture": posture,
            "health": health,
            "coverage": coverage,
            "recommended_actions": recommendations,
        }

    @staticmethod
    def assess_decision_anomaly(
        allow_count: int = 0,
        deny_count: int = 0,
        escalate_count: int = 0,
        *,
        baseline_deny_rate: float = 0.15,
        baseline_escalate_rate: float = 0.10,
        spike_threshold: float = 2.0,
    ) -> dict[str, Any]:
        """exp146: Statistical anomaly detection on governance decision distributions.

        Accepts counts of allow/deny/escalate outcomes (e.g. from
        GovernanceMetrics.snapshot() or an audit log) and returns the
        observed distribution plus signals when rates diverge from
        expected baselines.  Intended for dashboards and alerting when
        deny or escalate rates spike relative to historical norms.

        Does not touch the validation hot path; callers supply pre-aggregated
        counts from their own metrics or audit store.

        Args:
            allow_count: Number of allowed decisions in the window.
            deny_count: Number of denied decisions in the window.
            escalate_count: Number of escalated decisions in the window.
            baseline_deny_rate: Expected deny rate (0.0-1.0). Default 0.15.
            baseline_escalate_rate: Expected escalate rate (0.0-1.0). Default 0.10.
            spike_threshold: Factor above baseline to flag as spike (e.g. 2.0 =
                twice the baseline rate). Default 2.0.

        Returns:
            dict with keys:

            - ``total``: total decisions
            - ``distribution``: allow_rate, deny_rate, escalate_rate (0-1)
            - ``rates``: same as distribution (alias)
            - ``anomalies``: list of detected signals (e.g. high_deny_rate,
              high_escalate_rate)
            - ``is_anomalous``: True if any anomaly signal was raised
            - ``baseline_deny_rate``, ``baseline_escalate_rate``: echo of inputs

        Example::

            snap = metrics.snapshot()
            r = Constitution.assess_decision_anomaly(
                snap["allow_count"], snap["deny_count"], snap["escalate_count"],
                baseline_deny_rate=0.1,
            )
            if r["is_anomalous"]:
                alert(r["anomalies"])
        """
        total = allow_count + deny_count + escalate_count
        if total == 0:
            return {
                "total": 0,
                "distribution": {"allow_rate": 0.0, "deny_rate": 0.0, "escalate_rate": 0.0},
                "rates": {"allow_rate": 0.0, "deny_rate": 0.0, "escalate_rate": 0.0},
                "anomalies": [],
                "is_anomalous": False,
                "baseline_deny_rate": baseline_deny_rate,
                "baseline_escalate_rate": baseline_escalate_rate,
            }

        allow_rate = allow_count / total
        deny_rate = deny_count / total
        escalate_rate = escalate_count / total
        distribution = {
            "allow_rate": round(allow_rate, 4),
            "deny_rate": round(deny_rate, 4),
            "escalate_rate": round(escalate_rate, 4),
        }
        anomalies: list[str] = []

        if baseline_deny_rate > 0 and deny_rate >= baseline_deny_rate * spike_threshold:
            anomalies.append(
                f"high_deny_rate: {deny_rate:.2%} (baseline {baseline_deny_rate:.2%}, "
                f"threshold {spike_threshold}x)"
            )
        if baseline_escalate_rate > 0 and escalate_rate >= baseline_escalate_rate * spike_threshold:
            anomalies.append(
                f"high_escalate_rate: {escalate_rate:.2%} (baseline "
                f"{baseline_escalate_rate:.2%}, threshold {spike_threshold}x)"
            )

        return {
            "total": total,
            "distribution": distribution,
            "rates": distribution,
            "anomalies": anomalies,
            "is_anomalous": len(anomalies) > 0,
            "baseline_deny_rate": baseline_deny_rate,
            "baseline_escalate_rate": baseline_escalate_rate,
        }

    def get_permission_ceiling(self) -> dict[str, Any]:
        return permission_ceiling.get_permission_ceiling(self)

    def rule_regulatory_clause_map(self) -> dict[str, Any]:
        return regulatory.rule_regulatory_clause_map(self)

    @staticmethod
    def check_governance_slo(
        p99_latency_ms: float = 0.0,
        compliance_rate: float = 1.0,
        throughput_rps: float = 0.0,
        false_negative_rate: float = 0.0,
        *,
        max_p99_ms: float = 1.0,
        min_compliance: float = 0.97,
        min_throughput_rps: float = 6000.0,
        max_fn_rate: float = 0.01,
    ) -> dict[str, Any]:
        """exp150: Check observed governance metrics against SLO thresholds (breach detection).

        Compares observed p99, compliance, throughput, and false-negative rate to
        configurable targets. For dashboards and alerting; does not touch the hot path.

        Returns:
            dict with keys:
            - thresholds: {max_p99_ms, min_compliance, min_throughput_rps, max_fn_rate}
            - metrics: {p99_latency_ms, compliance_rate, throughput_rps, false_negative_rate}
            - pass: {p99, compliance, throughput, fn_rate} (bool each)
            - breaches: list of strings describing failed SLOs
            - slo_pass: True if all metrics within SLO
        """
        pass_p99 = p99_latency_ms <= max_p99_ms
        pass_compliance = compliance_rate >= min_compliance
        pass_throughput = throughput_rps >= min_throughput_rps
        pass_fn = false_negative_rate <= max_fn_rate
        breaches: list[str] = []
        if not pass_p99:
            breaches.append(f"p99_latency_ms {p99_latency_ms:.4f} > {max_p99_ms}")
        if not pass_compliance:
            breaches.append(f"compliance_rate {compliance_rate:.4f} < {min_compliance}")
        if not pass_throughput:
            breaches.append(f"throughput_rps {throughput_rps:.0f} < {min_throughput_rps}")
        if not pass_fn:
            breaches.append(f"false_negative_rate {false_negative_rate:.4f} > {max_fn_rate}")
        return {
            "thresholds": {
                "max_p99_ms": max_p99_ms,
                "min_compliance": min_compliance,
                "min_throughput_rps": min_throughput_rps,
                "max_fn_rate": max_fn_rate,
            },
            "metrics": {
                "p99_latency_ms": p99_latency_ms,
                "compliance_rate": compliance_rate,
                "throughput_rps": throughput_rps,
                "false_negative_rate": false_negative_rate,
            },
            "pass": {
                "p99": pass_p99,
                "compliance": pass_compliance,
                "throughput": pass_throughput,
                "fn_rate": pass_fn,
            },
            "breaches": breaches,
            "slo_pass": len(breaches) == 0,
        }

    def list_categories(self) -> list[str]:
        """exp151: Return sorted distinct rule categories for UI/config.

        Does not touch the hot validation path.
        """
        return sorted({r.category for r in self.rules if r.category})

    def blast_radius(self, rule_id: str) -> dict[str, Any]:
        """exp152: Impact analysis — rule IDs affected if this rule is changed or removed.

        Returns dependent rule IDs (rules that list this rule in depends_on) and
        the successor rule ID (replaced_by) if this rule is deprecated. For
        change-impact and rollout planning; zero hot-path overhead.

        Returns:
            dict with keys: dependent_rule_ids (list), successor_rule_id (str or None)
        """
        dependent = [r.id for r in self.rules if rule_id in (r.depends_on or [])]
        rule = self.get_rule(rule_id)
        successor = (rule.replaced_by or "").strip() or None if rule else None
        return {"dependent_rule_ids": dependent, "successor_rule_id": successor}

    def get_version_info(self) -> dict[str, Any]:
        """exp153: Return version label, hash, and rule count for rollback/documentation.

        Does not touch the hot validation path.
        """
        return {
            "version_name": self.version_name or None,
            "version": self.version,
            "hash": self.hash,
            "rule_count": len(self.rules),
        }

    def maturity_level(self) -> dict[str, Any]:
        """exp139: Score governance maturity on a 1-5 capability scale.

        Evaluates the constitution against a progressive maturity model.
        Each level builds on the previous, assessing increasingly sophisticated
        governance capabilities.

        Maturity Levels:

        1. **Initial** — Rules exist with basic keywords and categories.
        2. **Managed** — Rules have documentation (text, tags) and severity variety.
        3. **Defined** — Rules use advanced features: dependencies, priorities,
           workflow actions, conditions.
        4. **Quantitatively Managed** — Constitution uses analytic features:
           versioning (rule_history), conflict detection, health/coverage tooling.
        5. **Optimising** — Constitution uses all advanced governance features:
           temporal validity, embeddings, inheritance, templates, changelog.

        Returns:
            dict with keys:

            - ``level``: achieved maturity level (1-5)
            - ``label``: human-readable level name
            - ``score``: continuous score 0.0-5.0 for partial credit
            - ``criteria``: per-level pass/fail breakdown
            - ``next_level_gaps``: list of unmet criteria for the next level

        Example::

            m = constitution.maturity_level()
            print(f"Maturity: Level {m['level']} - {m['label']}")
            if m['level'] < 3:
                print("Gaps:", m['next_level_gaps'])
        """
        active = self.active_rules()
        n = len(active)
        all_rules = self.rules

        criteria: dict[str, bool] = {}

        # ── Level 1: Initial ────────────────────────────────────────
        criteria["has_rules"] = n >= 1
        criteria["has_keywords"] = any(r.keywords for r in active)
        criteria["has_categories"] = any(r.category for r in active)
        level1 = all(criteria[k] for k in ["has_rules", "has_keywords", "has_categories"])

        # ── Level 2: Managed ────────────────────────────────────────
        criteria["has_rule_text"] = any(r.text.strip() for r in active)
        criteria["has_tags"] = any(r.tags for r in active)
        criteria["has_severity_variety"] = len({r.severity for r in active}) >= 2
        criteria["has_multiple_categories"] = len({r.category for r in active}) >= 2
        level2 = level1 and all(
            criteria[k]
            for k in [
                "has_rule_text",
                "has_tags",
                "has_severity_variety",
                "has_multiple_categories",
            ]
        )

        # ── Level 3: Defined ────────────────────────────────────────
        criteria["uses_dependencies"] = any(r.depends_on for r in all_rules)
        criteria["uses_priorities"] = any(r.priority != 0 for r in all_rules)
        criteria["uses_workflow_actions"] = any(r.workflow_action for r in active)
        criteria["uses_conditions"] = any(r.condition for r in all_rules)
        level3 = level2 and all(
            criteria[k]
            for k in [
                "uses_dependencies",
                "uses_priorities",
                "uses_workflow_actions",
                "uses_conditions",
            ]
        )

        # ── Level 4: Quantitatively Managed ─────────────────────────
        criteria["uses_versioning"] = bool(self.rule_history)
        criteria["uses_changelog"] = bool(self.changelog)
        criteria["has_conflict_detection"] = hasattr(self, "detect_conflicts")
        criteria["has_health_tooling"] = hasattr(self, "health_score")
        level4 = level3 and all(
            criteria[k]
            for k in [
                "uses_versioning",
                "uses_changelog",
                "has_conflict_detection",
                "has_health_tooling",
            ]
        )

        # ── Level 5: Optimising ──────────────────────────────────────
        criteria["uses_temporal"] = any(
            getattr(r, "valid_from", None) or getattr(r, "valid_until", None) for r in all_rules
        )
        criteria["uses_embeddings"] = any(getattr(r, "embedding", None) for r in all_rules)
        criteria["uses_deprecation"] = any(r.deprecated for r in all_rules)
        criteria["has_regulatory_tooling"] = hasattr(self, "regulatory_alignment")
        level5 = level4 and all(
            criteria[k]
            for k in [
                "uses_temporal",
                "uses_embeddings",
                "uses_deprecation",
                "has_regulatory_tooling",
            ]
        )

        # Determine achieved level
        if level5:
            level, label = 5, "Optimising"
        elif level4:
            level, label = 4, "Quantitatively Managed"
        elif level3:
            level, label = 3, "Defined"
        elif level2:
            level, label = 2, "Managed"
        elif level1:
            level, label = 1, "Initial"
        else:
            level, label = 0, "Ad hoc"

        # Continuous score: base + partial credit from next level
        level_keys = {
            1: ["has_rules", "has_keywords", "has_categories"],
            2: ["has_rule_text", "has_tags", "has_severity_variety", "has_multiple_categories"],
            3: ["uses_dependencies", "uses_priorities", "uses_workflow_actions", "uses_conditions"],
            4: [
                "uses_versioning",
                "uses_changelog",
                "has_conflict_detection",
                "has_health_tooling",
            ],
            5: ["uses_temporal", "uses_embeddings", "uses_deprecation", "has_regulatory_tooling"],
        }
        partial = 0.0
        if level < 5:
            next_keys = level_keys.get(level + 1, [])
            if next_keys:
                partial = sum(1 for k in next_keys if criteria.get(k)) / len(next_keys)
        score = round(level + partial, 2)

        # Next-level gaps
        next_gaps: list[str] = []
        if level < 5:
            next_keys = level_keys.get(level + 1, [])
            next_gaps = [k for k in next_keys if not criteria.get(k)]

        return {
            "level": level,
            "label": label,
            "score": score,
            "criteria": criteria,
            "next_level_gaps": next_gaps,
        }

    def coverage_gaps(self) -> dict[str, Any]:
        """exp134: Identify governance domains and categories with thin or zero coverage.

        Scans the constitution for governance blind spots — areas where agents
        may act without any rule checking their behaviour.  Returns three levels
        of concern:

        - **uncovered_domains**: High-level governance domains (safety, privacy,
          fairness, transparency, security) for which *no* active rule exists
          whose category or keywords signal that domain.
        - **thin_categories**: Categories with fewer than ``min_rules`` (default 2)
          active rules — likely under-specified.
        - **disabled_only_categories**: Categories where every rule is disabled,
          leaving the category entirely unenforced.

        Returns:
            dict with keys:

            - ``uncovered_domains``: list of domain names with zero active rule
              coverage (based on :attr:`_DOMAIN_SIGNAL_MAP`).
            - ``thin_categories``: dict mapping category → active rule count for
              categories with 1-(min_rules-1) active rules.
            - ``disabled_only_categories``: list of categories that have rules
              but all are disabled.
            - ``total_categories``: total distinct categories across all rules.
            - ``coverage_score``: fraction of known domains that are covered
              (0.0 - 1.0).
            - ``min_rules``: threshold used for thin-category detection.

        Example::

            gaps = constitution.coverage_gaps()
            if gaps["uncovered_domains"]:
                warnings.warn(f"No rules for: {gaps['uncovered_domains']}")
        """
        min_rules = 2
        active = self.active_rules()
        all_rules = self.rules

        # ── Domain coverage ──────────────────────────────────────────
        # A domain is "covered" if ≥1 active rule has a category or keyword
        # matching that domain's signal set.
        domain_covered: dict[str, bool] = {}
        for domain, signals in self._DOMAIN_SIGNAL_MAP.items():
            signal_cats: set[str] = signals.get("categories", set())
            signal_kws: set[str] = signals.get("keywords", set())
            covered = any(
                r.category in signal_cats or bool(signal_kws & {kw.lower() for kw in r.keywords})
                for r in active
            )
            domain_covered[domain] = covered

        uncovered_domains = sorted(d for d, v in domain_covered.items() if not v)
        covered_count = sum(1 for v in domain_covered.values() if v)
        coverage_score = covered_count / len(domain_covered) if domain_covered else 1.0

        # ── Category analysis ────────────────────────────────────────
        # Count active rules per category
        cat_active: dict[str, int] = {}
        cat_total: dict[str, int] = {}
        for r in all_rules:
            cat = r.category or "general"
            cat_total[cat] = cat_total.get(cat, 0) + 1
            if r.enabled:
                cat_active[cat] = cat_active.get(cat, 0) + 1

        thin_categories = {cat: count for cat, count in cat_active.items() if 0 < count < min_rules}
        disabled_only_categories = sorted(cat for cat in cat_total if cat_active.get(cat, 0) == 0)

        return {
            "uncovered_domains": uncovered_domains,
            "thin_categories": thin_categories,
            "disabled_only_categories": disabled_only_categories,
            "total_categories": len(cat_total),
            "coverage_score": round(coverage_score, 4),
            "min_rules": min_rules,
        }

    def health_score(self) -> dict[str, Any]:
        """exp130: Composite governance quality metric for this constitution.

        Evaluates constitution quality across five dimensions and returns a
        weighted composite score (0.0 - 1.0).  Useful for CI/CD quality gates,
        operator dashboards, and inter-constitution comparison.

        Dimensions (equal weight, 0.0-1.0 each):

        1. **Documentation** — fraction of rules with non-empty text, category,
           and at least one tag.
        2. **Specificity** — average keyword count per rule (more specific rules
           are harder to bypass); capped at 3 keywords for full score.
        3. **Conflict-freedom** — penalty for pairs of rules with identical
           keywords but different severities (conflicts found by
           :meth:`detect_conflicts`).
        4. **Dependency soundness** — fraction of ``depends_on`` references that
           resolve to real rule IDs.
        5. **Coverage** — fraction of rules that have at least one keyword or
           pattern (purely abstract rules without any detection signal score 0).

        Returns:
            dict with keys:

            - ``composite``: weighted average (0.0 - 1.0)
            - ``documentation``: documentation sub-score
            - ``specificity``: specificity sub-score
            - ``conflict_freedom``: conflict-freedom sub-score
            - ``dependency_soundness``: dependency soundness sub-score
            - ``coverage``: coverage sub-score
            - ``rule_count``: total active rules evaluated
            - ``grade``: letter grade (A ≥ 0.9, B ≥ 0.75, C ≥ 0.6, D ≥ 0.45, F)

        Example::

            score = constitution.health_score()
            if score["composite"] < 0.7:
                raise RuntimeError(f"Constitution quality too low: {score['grade']}")
        """
        active = self.active_rules()
        n = len(active)
        if n == 0:
            return {
                "composite": 0.0,
                "documentation": 0.0,
                "specificity": 0.0,
                "conflict_freedom": 1.0,
                "dependency_soundness": 1.0,
                "coverage": 0.0,
                "rule_count": 0,
                "grade": "F",
            }

        rule_ids = {r.id for r in self.rules}

        # 1. Documentation: text + category + ≥1 tag
        doc_scores = [
            (1.0 if r.text.strip() else 0.0) * 0.4
            + (1.0 if r.category and r.category != "general" else 0.3) * 0.3
            + (1.0 if r.tags else 0.0) * 0.3
            for r in active
        ]
        documentation = sum(doc_scores) / n

        # 2. Specificity: avg keyword count (saturates at 3)
        specificity = min(
            1.0,
            sum(min(len(r.keywords), 3) / 3.0 for r in active) / n,
        )

        # 3. Conflict-freedom: each conflict pair reduces score
        try:
            conflicts = self.detect_conflicts()
            num_conflicts = len(conflicts.get("conflicts", []))
            # Penalty: each conflict costs 0.1, floor at 0
            conflict_freedom = max(0.0, 1.0 - num_conflicts * 0.1)
        except Exception:
            conflict_freedom = 1.0  # can't assess — assume clean

        # 4. Dependency soundness: fraction of depends_on refs that resolve
        total_deps = sum(len(r.depends_on) for r in active)
        if total_deps == 0:
            dependency_soundness = 1.0
        else:
            valid_deps = sum(sum(1 for dep in r.depends_on if dep in rule_ids) for r in active)
            dependency_soundness = valid_deps / total_deps

        # 5. Coverage: fraction of rules with ≥1 keyword or pattern
        coverage = sum(1.0 if (r.keywords or r.patterns) else 0.0 for r in active) / n

        composite = (
            documentation + specificity + conflict_freedom + dependency_soundness + coverage
        ) / 5.0

        if composite >= 0.9:
            grade = "A"
        elif composite >= 0.75:
            grade = "B"
        elif composite >= 0.6:
            grade = "C"
        elif composite >= 0.45:
            grade = "D"
        else:
            grade = "F"

        return {
            "composite": round(composite, 4),
            "documentation": round(documentation, 4),
            "specificity": round(specificity, 4),
            "conflict_freedom": round(conflict_freedom, 4),
            "dependency_soundness": round(dependency_soundness, 4),
            "coverage": round(coverage, 4),
            "rule_count": n,
            "grade": grade,
        }

    def dead_rules(
        self,
        corpus: list[str],
        *,
        include_deprecated: bool = False,
    ) -> dict[str, Any]:
        """exp168: Detect rules that never fire against a corpus of actions.

        Evaluates every active rule against every action in *corpus* and
        identifies rules with zero keyword or pattern matches. Dead rules add
        cognitive overhead to governance review without catching anything —
        they are candidates for removal or keyword tuning.

        Args:
            corpus: List of action strings to evaluate rules against.
                    A representative sample of real agent actions works best.
            include_deprecated: If True, also check deprecated rules.
                    Defaults to False (check only active rules).

        Returns:
            dict with:
                - ``total_rules``: number of rules checked
                - ``dead_count``: number of rules that never fired
                - ``live_count``: number of rules that fired at least once
                - ``dead_rules``: list of dicts for rules with zero hits
                    - ``rule_id``, ``text``, ``severity``, ``keywords``,
                      ``patterns``, ``recommendation``
                - ``live_rules``: list of dicts with hit counts
                    - ``rule_id``, ``text``, ``hits``, ``coverage_pct``
                - ``corpus_size``: number of actions evaluated
                - ``coverage_pct``: fraction of rules that fired (0-1)

        Example::

            corpus = ["delete all records", "read user profile", "deploy to prod"]
            report = constitution.dead_rules(corpus)
            for r in report["dead_rules"]:
                print(f"{r['rule_id']}: never fires — consider removing")
        """
        if include_deprecated:
            rules_to_check = list(self.rules)
        else:
            rules_to_check = [r for r in self.rules if not r.deprecated]

        # Count hits per rule
        hit_counts: dict[str, int] = {r.id: 0 for r in rules_to_check}
        for action in corpus:
            for rule in rules_to_check:
                if rule.matches(action):
                    hit_counts[rule.id] += 1

        corpus_size = len(corpus)
        dead: list[dict[str, Any]] = []
        live: list[dict[str, Any]] = []

        for rule in rules_to_check:
            hits = hit_counts[rule.id]
            if hits == 0:
                dead.append(
                    {
                        "rule_id": rule.id,
                        "text": rule.text[:120],
                        "severity": rule.severity.value
                        if hasattr(rule.severity, "value")
                        else str(rule.severity),
                        "keywords": list(rule.keywords),
                        "patterns": list(rule.patterns),
                        "recommendation": (
                            "Remove or broaden keywords — rule never matched any corpus action."
                            if rule.keywords or rule.patterns
                            else "Rule has no keywords or patterns — cannot match any action."
                        ),
                    }
                )
            else:
                coverage_pct = (hits / corpus_size * 100) if corpus_size else 0.0
                live.append(
                    {
                        "rule_id": rule.id,
                        "text": rule.text[:120],
                        "hits": hits,
                        "coverage_pct": round(coverage_pct, 2),
                    }
                )

        total = len(rules_to_check)
        live_count = len(live)
        dead_count = len(dead)
        coverage = live_count / total if total else 1.0

        return {
            "total_rules": total,
            "dead_count": dead_count,
            "live_count": live_count,
            "dead_rules": sorted(dead, key=lambda x: x["rule_id"]),
            "live_rules": sorted(live, key=lambda x: x["hits"], reverse=True),
            "corpus_size": corpus_size,
            "coverage_pct": round(coverage * 100, 2),
        }

    def posture_score(self, ci_threshold: float = 0.70) -> dict[str, Any]:
        """exp139: Unified governance posture score for CI/CD gates and dashboards.

        Combines three independent quality axes into a single normalised score:

        1. **Health** (40%) — :meth:`health_score` composite (docs, specificity,
           conflict-freedom, dependency soundness, keyword coverage).
        2. **Coverage** (35%) — domain coverage from :meth:`coverage_gaps`;
           penalises missing or weak governance domains.
        3. **Maturity** (25%) — :meth:`maturity_level` score normalised 0-1
           (CMMI-style 0-5 -> 0-1).

        Inspired by the NIST AI Risk Management Framework composite risk metrics
        and agentic AI governance lifecycle management research (2025-2026).

        Args:
            ci_threshold: Minimum posture score for ``ci_pass`` to be True.
                          Default 0.70. Set higher for stricter environments.

        Returns:
            dict with keys:

            - ``posture``: composite 0.0-1.0 weighted score
            - ``grade``: letter grade (A+ >= 0.95, A >= 0.90, B >= 0.75,
              C >= 0.60, D >= 0.45, F < 0.45)
            - ``health``: health sub-score (0-1)
            - ``coverage``: coverage sub-score (0-1)
            - ``maturity``: maturity sub-score (0-1, raw 0-5 normalised)
            - ``recommendations``: list of actionable improvement suggestions
            - ``ci_pass``: bool -- True if posture >= *ci_threshold*

        Example::

            result = constitution.posture_score(ci_threshold=0.80)
            if not result["ci_pass"]:
                raise SystemExit(f"Governance posture below CI threshold: {result['grade']}")
        """
        # ── health sub-score ────────────────────────────────────────────────
        hs = self.health_score()
        health = float(hs.get("composite", 0.0))

        # ── coverage sub-score ──────────────────────────────────────────────
        cg: dict[str, Any] = {}
        try:
            cg = self.coverage_gaps()
            coverage_score_raw = float(cg.get("coverage_score", 0.0))
            coverage = min(1.0, max(0.0, coverage_score_raw))
        except (KeyError, TypeError, ValueError):
            coverage = 0.5  # can't assess — neutral

        # ── maturity sub-score ──────────────────────────────────────────────
        ml: dict[str, Any] = {}
        try:
            ml = self.maturity_level()
            raw_level = float(ml.get("score", 0.0))  # 0.0–5.0
            maturity = min(1.0, raw_level / 5.0)
        except (KeyError, TypeError, ValueError):
            maturity = 0.0

        # ── weighted composite ──────────────────────────────────────────────
        posture = round(health * 0.40 + coverage * 0.35 + maturity * 0.25, 4)

        if posture >= 0.95:
            grade = "A+"
        elif posture >= 0.90:
            grade = "A"
        elif posture >= 0.75:
            grade = "B"
        elif posture >= 0.60:
            grade = "C"
        elif posture >= 0.45:
            grade = "D"
        else:
            grade = "F"

        # ── actionable recommendations ──────────────────────────────────────
        recommendations: list[str] = []
        if health < 0.7:
            hs_grade = hs.get("grade", "?")
            recommendations.append(
                f"Improve health score ({hs_grade}) — add tags/keywords/category to rules."
            )
        if coverage < 0.7:
            try:
                missing = cg.get("missing_domains", [])
                weak = cg.get("weak_domains", [])
                if missing:
                    recommendations.append(
                        f"Add rules covering missing domains: {', '.join(missing)}."
                    )
                elif weak:
                    recommendations.append(f"Expand thin governance domains: {', '.join(weak)}.")
                else:
                    recommendations.append("Improve domain coverage breadth.")
            except (KeyError, TypeError, AttributeError):
                recommendations.append("Audit governance domain coverage.")
        if maturity < 0.6:
            try:
                gaps = ml.get("next_level_gaps", [])
                if gaps:
                    recommendations.append(
                        f"Advance maturity by addressing: {', '.join(gaps[:3])}."
                    )
                else:
                    recommendations.append("Advance governance maturity level.")
            except (KeyError, TypeError, AttributeError):
                recommendations.append("Advance governance maturity level.")

        return {
            "posture": posture,
            "grade": grade,
            "health": round(health, 4),
            "coverage": round(coverage, 4),
            "maturity": round(maturity, 4),
            "recommendations": recommendations,
            "ci_pass": posture >= ci_threshold,
        }

    def changelog_summary(self) -> dict[str, Any]:
        return workflow_analytics.changelog_summary(self)

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
        return filtering.filter(
            self,
            severity=severity,
            min_severity=min_severity,
            category=category,
            workflow_action=workflow_action,
            tag=tag,
            enabled_only=enabled_only,
        )

    def semantic_rule_clusters(
        self,
        expected_domains: Sequence[str] | None = None,
    ) -> dict[str, list[str]]:
        return coverage_analysis.semantic_rule_clusters(self, expected_domains)

    def analyze_coverage_gaps(
        self,
        expected_domains: Sequence[str] | None = None,
        *,
        weak_threshold: int = 1,
    ) -> dict[str, Any]:
        return coverage_analysis.analyze_coverage_gaps(
            self,
            expected_domains,
            weak_threshold=weak_threshold,
        )

    def render(self, context: dict[str, Any]) -> Constitution:
        return rendering.render(self, context)

    def explain_rendered(self, action: str, context: dict[str, Any]) -> dict[str, Any]:
        return rendering.explain_rendered(self, action, context)

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
