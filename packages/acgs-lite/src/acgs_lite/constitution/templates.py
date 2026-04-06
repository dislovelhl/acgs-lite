"""Constitutional rules — the core of ACGS-Lite.

A Constitution is a set of Rules that govern agent behavior.
Rules can be loaded from YAML, dicts, or created programmatically.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from typing import Any

from .core import Constitution, Rule, Severity
from .rule import ViolationAction


class ConstitutionBuilder:
    """exp108: Fluent builder for programmatic constitution construction.

    Provides a method-chaining API for building ``Constitution`` objects in code,
    without needing to write YAML. Useful for:

    - Unit tests that need targeted constitutions
    - Application code that constructs rules from database or config
    - Composing constitutions from reusable rule sets

    Example::

        from acgs_lite.constitution import ConstitutionBuilder

        constitution = (
            ConstitutionBuilder("my-governance", version="2.0.0")
            .description("Governance rules for our production agent")
            .add_rule(
                "SAFE-001",
                "Agent must not provide financial advice",
                severity="critical",
                keywords=["invest", "buy stocks", "financial advice"],
                category="regulatory",
                workflow_action=ViolationAction.BLOCK,
            )
            .add_rule(
                "SAFE-002",
                "Agent must not expose PII",
                severity="critical",
                patterns=[r"\b\\d{3}-\\d{2}-\\d{4}\b"],
                category="data-protection",
                workflow_action=ViolationAction.BLOCK_AND_NOTIFY,
            )
            .build()
        )
    """

    def __init__(
        self,
        name: str = "custom",
        *,
        version: str = "1.0.0",
        description: str = "",
    ) -> None:
        self._name = name
        self._version = version
        self._description = description
        self._rules: list[Rule] = []
        self._metadata: dict[str, Any] = {}
        self._rule_ids: set[str] = set()

    def description(self, text: str) -> ConstitutionBuilder:
        """Set the constitution description. Returns self for chaining."""
        self._description = text
        return self

    def metadata(self, **kwargs: Any) -> ConstitutionBuilder:
        """Set metadata key-value pairs. Returns self for chaining."""
        self._metadata.update(kwargs)
        return self

    def add_rule(
        self,
        rule_id: str,
        text: str,
        *,
        severity: str | Severity = Severity.HIGH,
        keywords: list[str] | None = None,
        patterns: list[str] | None = None,
        category: str = "general",
        subcategory: str = "",
        workflow_action: ViolationAction | str = "",
        enabled: bool = True,
        depends_on: list[str] | None = None,
        tags: list[str] | None = None,
        priority: int = 0,
        **rule_kwargs: Any,
    ) -> ConstitutionBuilder:
        """Add a rule to the constitution being built. Returns self for chaining.

        Args:
            rule_id: Unique rule ID (e.g. "SAFE-001").
            text: Human-readable rule description.
            severity: Severity level — "critical", "high", "medium", "low" or Severity enum.
            keywords: List of trigger keywords (case-insensitive).
            patterns: List of regex patterns to match.
            category: Rule category for grouping and filtering.
            subcategory: Finer-grained sub-classification.
            workflow_action: Downstream action — "block", "block_and_notify",
                             "require_human_review", "escalate_to_senior", "warn".
            enabled: Whether the rule is active (default True).
            depends_on: List of rule IDs this rule depends on.
            **rule_kwargs: Additional Rule fields passed through.

        Raises:
            ValueError: If rule_id is already registered in this builder.
        """
        if rule_id in self._rule_ids:
            raise ValueError(f"Rule ID {rule_id!r} already exists in this builder")

        _sev = Severity(severity) if isinstance(severity, str) else severity
        _wa = ViolationAction(workflow_action) if isinstance(workflow_action, str) and workflow_action else workflow_action
        rule = Rule(
            id=rule_id,
            text=text,
            severity=_sev,
            keywords=keywords or [],
            patterns=patterns or [],
            category=category,
            subcategory=subcategory,
            workflow_action=_wa,  # type: ignore[arg-type]  # Pydantic coerces str→ViolationAction
            enabled=enabled,
            depends_on=depends_on or [],
            tags=tags or [],
            priority=priority,
            **rule_kwargs,
        )
        self._rules.append(rule)
        self._rule_ids.add(rule_id)
        return self

    def add_rules(self, rules: list[Rule]) -> ConstitutionBuilder:
        """Add pre-built Rule objects. Returns self for chaining."""
        for r in rules:
            if r.id in self._rule_ids:
                raise ValueError(f"Rule ID {r.id!r} already exists in this builder")
            self._rules.append(r)
            self._rule_ids.add(r.id)
        return self

    def extend_from(self, constitution: Constitution) -> ConstitutionBuilder:
        """Copy all rules from an existing constitution into this builder.

        Useful for composing templates:

            builder = (
                ConstitutionBuilder("extended-gitlab")
                .extend_from(Constitution.from_template("gitlab"))
                .add_rule("CUSTOM-001", "Extra org rule", severity="high", keywords=["forbidden"])
                .build()
            )
        """
        for r in constitution.rules:
            if r.id not in self._rule_ids:
                self._rules.append(r)
                self._rule_ids.add(r.id)
        return self

    def remove_rule(self, rule_id: str) -> ConstitutionBuilder:
        """Remove a rule by ID. Returns self for chaining.

        Raises:
            KeyError: If rule_id is not present.
        """
        if rule_id not in self._rule_ids:
            raise KeyError(f"Rule ID {rule_id!r} not found in builder")
        self._rules = [r for r in self._rules if r.id != rule_id]
        self._rule_ids.discard(rule_id)
        return self

    def build(self) -> Constitution:
        """Build and return the Constitution.

        Raises:
            ValueError: If no rules have been added.
        """
        if not self._rules:
            raise ValueError("Cannot build an empty constitution — add at least one rule")
        return Constitution(
            name=self._name,
            version=self._version,
            description=self._description,
            rules=list(self._rules),
            metadata=dict(self._metadata),
        )

    def __len__(self) -> int:
        return len(self._rules)

    def __repr__(self) -> str:
        return f"ConstitutionBuilder(name={self._name!r}, rules={len(self._rules)})"
