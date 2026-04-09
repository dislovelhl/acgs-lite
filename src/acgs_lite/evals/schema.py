"""Schema models for offline constitution evaluation scenarios."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True, slots=True)
class EvalScenario:
    """Single offline evaluation scenario."""

    id: str
    input_action: str
    context: dict[str, Any] = field(default_factory=dict)
    expected_valid: bool = True
    expected_action_taken: str | None = None
    expected_rule_ids: list[str] = field(default_factory=list)
    expected_warning: bool | None = None
    expected_review_request: bool | None = None
    expected_escalation: bool | None = None
    expected_incident: bool | None = None
    tags: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvalScenario:
        scenario_id = str(data.get("id", "")).strip()
        if not scenario_id:
            raise ValueError("Eval scenario requires a non-empty 'id'")
        input_action = str(data.get("input_action", "")).strip()
        if not input_action:
            raise ValueError(f"Eval scenario '{scenario_id}' requires a non-empty 'input_action'")
        return cls(
            id=scenario_id,
            input_action=input_action,
            context=dict(data.get("context", {})),
            expected_valid=bool(data.get("expected_valid", True)),
            expected_action_taken=(
                None
                if data.get("expected_action_taken") in (None, "")
                else str(data["expected_action_taken"])
            ),
            expected_rule_ids=[str(rule_id) for rule_id in data.get("expected_rule_ids", [])],
            expected_warning=data.get("expected_warning"),
            expected_review_request=data.get("expected_review_request"),
            expected_escalation=data.get("expected_escalation"),
            expected_incident=data.get("expected_incident"),
            tags=[str(tag) for tag in data.get("tags", [])],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "input_action": self.input_action,
            "context": self.context,
            "expected_valid": self.expected_valid,
            "expected_action_taken": self.expected_action_taken,
            "expected_rule_ids": self.expected_rule_ids,
            "expected_warning": self.expected_warning,
            "expected_review_request": self.expected_review_request,
            "expected_escalation": self.expected_escalation,
            "expected_incident": self.expected_incident,
            "tags": self.tags,
        }


def load_scenarios(path: str | Path) -> list[EvalScenario]:
    """Load evaluation scenarios from YAML."""
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    items = raw.get("scenarios", []) if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        raise ValueError("Eval scenario file must contain a 'scenarios' list or a top-level list")
    return [EvalScenario.from_dict(item) for item in items]


__all__ = ["EvalScenario", "load_scenarios"]
