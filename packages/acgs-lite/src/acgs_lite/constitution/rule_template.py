"""Parameterized rule template system for governance rules.

Allows governance teams to define rule *templates* once and instantiate them
many times with concrete parameter bindings, eliminating copy-paste drift across
large rule sets.

A template is a ``Rule``-like skeleton with ``{param}`` placeholders in text,
keywords, patterns, and category fields.  Instantiation substitutes all
placeholders and returns a fully-formed ``Rule`` ready for inclusion in a
``Constitution``.

Example::

    from acgs_lite.constitution.rule_template import RuleTemplate, RuleTemplateRegistry

    # Define a template once
    registry = RuleTemplateRegistry()
    registry.register(RuleTemplate(
        template_id="DENY_ACCESS",
        text="Agent must not {action} the {resource} without authorisation",
        severity="critical",
        keywords=["{action}", "{resource}"],
        category="access-control",
        workflow_action="block",
        params=["action", "resource"],
    ))

    # Instantiate many rules from one template
    rule1 = registry.instantiate("DENY_ACCESS", rule_id="AC-001",
                                  action="delete", resource="user-database")
    rule2 = registry.instantiate("DENY_ACCESS", rule_id="AC-002",
                                  action="export", resource="audit-log")

"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .core import Rule, Severity


@dataclass
class RuleTemplate:
    """A parameterized blueprint for generating governance rules.

    Attributes:
        template_id: Unique identifier for this template.
        text: Rule description with ``{param}`` placeholders.
        severity: Default severity string (``critical``, ``high``, etc.).
        keywords: List of keyword strings, may contain ``{param}`` placeholders.
        patterns: List of regex pattern strings, may contain ``{param}`` placeholders.
        category: Rule category string, may contain ``{param}`` placeholders.
        workflow_action: Default workflow action string.
        params: Ordered list of parameter names expected at instantiation.
        description: Optional human-readable description of the template.
        tags: Default tags to apply to all instantiated rules.
    """

    template_id: str
    text: str
    severity: str = "high"
    keywords: list[str] = field(default_factory=list)
    patterns: list[str] = field(default_factory=list)
    category: str = "general"
    workflow_action: str = "block"
    params: list[str] = field(default_factory=list)
    description: str = ""
    tags: list[str] = field(default_factory=list)

    def _find_placeholders(self, s: str) -> set[str]:
        """Return all ``{name}`` placeholder names found in *s*."""
        return {m.group(1) for m in re.finditer(r"\{(\w+)\}", s)}

    def _all_template_placeholders(self) -> set[str]:
        """Collect every placeholder used across all template fields."""
        found: set[str] = set()
        for s in [self.text, self.category, self.workflow_action]:
            found |= self._find_placeholders(s)
        for kw in self.keywords:
            found |= self._find_placeholders(kw)
        for pat in self.patterns:
            found |= self._find_placeholders(pat)
        return found

    def validate(self) -> list[str]:
        """Return a list of validation errors (empty = valid).

        Checks that:
        - ``template_id`` is non-empty.
        - ``text`` is non-empty.
        - All placeholders in template fields are declared in ``params``.
        - ``severity`` is a recognised value.
        """
        errors: list[str] = []
        if not self.template_id:
            errors.append("template_id must not be empty")
        if not self.text:
            errors.append("text must not be empty")

        declared = set(self.params)
        used = self._all_template_placeholders()
        undeclared = used - declared
        if undeclared:
            errors.append(f"Placeholders used but not declared in params: {sorted(undeclared)}")

        valid_severities = {s.value for s in Severity}
        if self.severity not in valid_severities:
            errors.append(f"severity '{self.severity}' is not one of {sorted(valid_severities)}")
        return errors

    def instantiate(self, rule_id: str, **kwargs: str) -> Rule:
        """Return a fully-formed ``Rule`` by substituting *kwargs* into placeholders.

        Args:
            rule_id: Unique identifier for the instantiated rule.
            **kwargs: Parameter bindings matching the names in ``params``.

        Raises:
            ValueError: If required parameters are missing, unexpected parameters
                are provided, or the resulting rule fails internal validation.

        Returns:
            A ready-to-use :class:`~acgs_lite.constitution.core.Rule`.
        """
        declared = set(self.params)
        provided = set(kwargs)

        missing = declared - provided
        if missing:
            raise ValueError(
                f"Template '{self.template_id}' missing required params: {sorted(missing)}"
            )
        extra = provided - declared
        if extra:
            raise ValueError(
                f"Template '{self.template_id}' received unexpected params: {sorted(extra)}"
            )

        def _sub(s: str) -> str:
            for k, v in kwargs.items():
                s = s.replace(f"{{{k}}}", v)
            return s

        instantiated_keywords = [_sub(kw) for kw in self.keywords]
        instantiated_patterns = [_sub(pat) for pat in self.patterns]

        rule = Rule(
            id=rule_id,
            text=_sub(self.text),
            severity=Severity(self.severity),
            keywords=instantiated_keywords,
            patterns=instantiated_patterns,
            category=_sub(self.category),
            workflow_action=_sub(self.workflow_action),
            tags=list(self.tags),
        )
        return rule

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a plain dictionary."""
        return {
            "template_id": self.template_id,
            "text": self.text,
            "severity": self.severity,
            "keywords": self.keywords,
            "patterns": self.patterns,
            "category": self.category,
            "workflow_action": self.workflow_action,
            "params": self.params,
            "description": self.description,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RuleTemplate:
        """Reconstruct from a plain dictionary."""
        return cls(
            template_id=data["template_id"],
            text=data["text"],
            severity=data.get("severity", "high"),
            keywords=data.get("keywords", []),
            patterns=data.get("patterns", []),
            category=data.get("category", "general"),
            workflow_action=data.get("workflow_action", "block"),
            params=data.get("params", []),
            description=data.get("description", ""),
            tags=data.get("tags", []),
        )


@dataclass
class InstantiationRecord:
    """Audit record of a single template instantiation.

    Attributes:
        template_id: The template that was instantiated.
        rule_id: The rule ID assigned to the instantiated rule.
        kwargs: The parameter bindings used.
    """

    template_id: str
    rule_id: str
    kwargs: dict[str, str]


class RuleTemplateRegistry:
    """Central registry for rule templates.

    Stores templates by ``template_id`` and provides instantiation with full
    audit trail.

    Example::

        registry = RuleTemplateRegistry()
        registry.register(RuleTemplate(
            template_id="DENY_ACTION",
            text="Agent must not {action} without authorisation",
            severity="critical",
            keywords=["{action}"],
            params=["action"],
        ))

        rule = registry.instantiate("DENY_ACTION", rule_id="AC-001", action="delete")
        assert rule.id == "AC-001"
        assert "delete" in rule.keywords
    """

    def __init__(self) -> None:
        self._templates: dict[str, RuleTemplate] = {}
        self._history: list[InstantiationRecord] = []

    def register(self, template: RuleTemplate, *, overwrite: bool = False) -> None:
        """Register *template* in the registry.

        Args:
            template: The template to register.
            overwrite: If ``False`` (default), raise ``ValueError`` when a template
                with the same ``template_id`` already exists.

        Raises:
            ValueError: If validation errors are found or ``overwrite`` is ``False``
                and the template already exists.
        """
        errors = template.validate()
        if errors:
            raise ValueError(f"Template '{template.template_id}' has validation errors: {errors}")
        if template.template_id in self._templates and not overwrite:
            raise ValueError(
                f"Template '{template.template_id}' already registered. "
                "Pass overwrite=True to replace it."
            )
        self._templates[template.template_id] = template

    def unregister(self, template_id: str) -> None:
        """Remove *template_id* from the registry.

        Raises:
            KeyError: If *template_id* is not registered.
        """
        if template_id not in self._templates:
            raise KeyError(f"Template '{template_id}' not found")
        del self._templates[template_id]

    def get(self, template_id: str) -> RuleTemplate:
        """Return the template for *template_id*.

        Raises:
            KeyError: If not found.
        """
        if template_id not in self._templates:
            raise KeyError(f"Template '{template_id}' not found")
        return self._templates[template_id]

    def list_templates(self) -> list[str]:
        """Return all registered template IDs (sorted)."""
        return sorted(self._templates)

    def count(self) -> int:
        """Return the number of registered templates."""
        return len(self._templates)

    def instantiate(self, template_id: str, *, rule_id: str, **kwargs: str) -> Rule:
        """Instantiate a template and return a ready-to-use :class:`Rule`.

        Args:
            template_id: The template to instantiate.
            rule_id: The unique rule ID to assign to the result.
            **kwargs: Parameter bindings for the template.

        Raises:
            KeyError: If *template_id* is not registered.
            ValueError: If required parameters are missing or unexpected.

        Returns:
            A fully-formed :class:`~acgs_lite.constitution.core.Rule`.
        """
        template = self.get(template_id)
        rule = template.instantiate(rule_id, **kwargs)
        self._history.append(
            InstantiationRecord(
                template_id=template_id,
                rule_id=rule_id,
                kwargs=dict(kwargs),
            )
        )
        return rule

    def instantiate_many(
        self,
        template_id: str,
        bindings: list[dict[str, Any]],
    ) -> list[Rule]:
        """Instantiate a template multiple times from a list of binding dicts.

        Each dict must contain a ``rule_id`` key plus all template parameters.

        Args:
            template_id: The template to instantiate.
            bindings: List of dicts, each with ``rule_id`` and param values.

        Returns:
            List of instantiated :class:`Rule` objects in the same order.

        Raises:
            KeyError: If *template_id* is not registered.
            ValueError: For any binding missing ``rule_id`` or template params.
        """
        rules: list[Rule] = []
        for i, b in enumerate(bindings):
            b = dict(b)
            if "rule_id" not in b:
                raise ValueError(f"Binding at index {i} missing 'rule_id'")
            rule_id = b.pop("rule_id")
            rules.append(self.instantiate(template_id, rule_id=rule_id, **b))
        return rules

    @property
    def history(self) -> list[InstantiationRecord]:
        """Read-only view of the instantiation history."""
        return list(self._history)

    def history_for_template(self, template_id: str) -> list[InstantiationRecord]:
        """Return instantiation records for a specific template."""
        return [r for r in self._history if r.template_id == template_id]

    def to_dict(self) -> dict[str, Any]:
        """Export all templates as a serialisable dictionary."""
        return {
            "templates": [t.to_dict() for t in self._templates.values()],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RuleTemplateRegistry:
        """Reconstruct a registry from a serialised dictionary."""
        registry = cls()
        for td in data.get("templates", []):
            registry.register(RuleTemplate.from_dict(td))
        return registry

    def summary(self) -> dict[str, Any]:
        """Return a human-readable registry summary."""
        return {
            "template_count": len(self._templates),
            "instantiation_count": len(self._history),
            "templates": [
                {
                    "template_id": t.template_id,
                    "params": t.params,
                    "severity": t.severity,
                    "instantiation_count": len(self.history_for_template(t.template_id)),
                }
                for t in self._templates.values()
            ],
        }
