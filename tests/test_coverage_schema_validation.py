"""Tests for acgs_lite.constitution.schema_validation coverage gaps."""

from __future__ import annotations

import pytest

from acgs_lite.constitution import Constitution
from acgs_lite.constitution.schema_validation import validate_rules, validate_yaml_schema


class TestValidateYamlSchema:
    def test_valid_schema(self) -> None:
        data = {
            "rules": [
                {
                    "id": "R1",
                    "text": "No harmful content",
                    "severity": "high",
                    "keywords": ["harmful"],
                }
            ]
        }
        result = validate_yaml_schema(data)
        assert result["valid"] is True
        assert result["errors"] == []

    def test_non_dict_root(self) -> None:
        result = validate_yaml_schema("not a dict")  # type: ignore[arg-type]
        assert result["valid"] is False
        assert "Root must be an object" in result["errors"][0]

    def test_missing_rules(self) -> None:
        result = validate_yaml_schema({})
        assert result["valid"] is False
        assert any("'rules' is required" in e for e in result["errors"])

    def test_rules_not_list(self) -> None:
        result = validate_yaml_schema({"rules": "not a list"})
        assert result["valid"] is False
        assert any("must be an array" in e for e in result["errors"])

    def test_rule_not_dict(self) -> None:
        result = validate_yaml_schema({"rules": ["not a dict"]})
        assert result["valid"] is False
        assert any("must be an object" in e for e in result["errors"])

    def test_missing_id(self) -> None:
        result = validate_yaml_schema({"rules": [{"text": "ok", "keywords": ["k"]}]})
        assert result["valid"] is False
        assert any("'id' is required" in e for e in result["errors"])

    def test_duplicate_id(self) -> None:
        rules = [
            {"id": "R1", "text": "a", "keywords": ["k"]},
            {"id": "R1", "text": "b", "keywords": ["k"]},
        ]
        result = validate_yaml_schema({"rules": rules})
        assert result["valid"] is False
        assert any("duplicate" in e for e in result["errors"])

    def test_missing_text(self) -> None:
        result = validate_yaml_schema({"rules": [{"id": "R1", "keywords": ["k"]}]})
        assert result["valid"] is False
        assert any("'text' is required" in e for e in result["errors"])

    def test_invalid_severity(self) -> None:
        result = validate_yaml_schema(
            {"rules": [{"id": "R1", "text": "ok", "severity": "ultra", "keywords": ["k"]}]}
        )
        assert result["valid"] is False
        assert any("invalid severity" in e for e in result["errors"])

    def test_invalid_workflow_action(self) -> None:
        result = validate_yaml_schema(
            {
                "rules": [
                    {
                        "id": "R1",
                        "text": "ok",
                        "keywords": ["k"],
                        "workflow_action": "explode",
                    }
                ]
            }
        )
        assert result["valid"] is False
        assert any("invalid workflow_action" in e for e in result["errors"])

    def test_warning_no_keywords_or_patterns(self) -> None:
        result = validate_yaml_schema({"rules": [{"id": "R1", "text": "ok"}]})
        assert result["valid"] is True
        assert len(result["warnings"]) > 0
        assert any("no keywords or patterns" in w for w in result["warnings"])

    def test_valid_workflow_actions(self) -> None:
        for action in ["block", "block_and_notify", "require_human_review", "warn", ""]:
            result = validate_yaml_schema(
                {
                    "rules": [
                        {
                            "id": "R1",
                            "text": "ok",
                            "keywords": ["k"],
                            "workflow_action": action,
                        }
                    ]
                }
            )
            assert result["valid"] is True, f"Failed for action: {action}"


class TestValidateRules:
    def test_valid_constitution(self) -> None:
        c = Constitution.default()
        errors = validate_rules(c)
        assert isinstance(errors, list)

    def test_duplicate_rule_ids_detected_by_constitution(self) -> None:
        """Constitution itself rejects duplicate IDs via validate_rules internally."""
        from acgs_lite.constitution.rule import Rule, Severity

        r1 = Rule(id="DUP", text="first", severity=Severity.HIGH, keywords=["a"])
        r2 = Rule(id="DUP", text="second", severity=Severity.HIGH, keywords=["b"])
        with pytest.raises(ValueError):
            Constitution(rules=[r1, r2])

    def test_no_keywords_accepted_by_constitution(self) -> None:
        """Empty keywords is valid — validate_rules does not reject it.

        The YAML schema validator issues a *warning* (not an error) for rules
        with no keywords or patterns.  At the Constitution model level, empty
        keywords is allowed because rules may rely on patterns instead.
        """
        from acgs_lite.constitution.rule import Rule, Severity

        r = Rule(id="NOKEY", text="some text", severity=Severity.HIGH, keywords=[])
        c = Constitution(rules=[r])
        assert len(c.rules) == 1
        assert c.rules[0].keywords == []
