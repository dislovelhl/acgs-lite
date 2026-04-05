"""
Tests for Legacy Policy Conversion Tools.
Constitutional Hash: 608508a9bd224290

Phase 10 Task 8: Legacy Policy Conversion Tools

Tests cover:
- JSON policy to Rego conversion
- YAML policy to Rego conversion
- Custom DSL parsing and conversion
- Constitutional compliance injection
- Conversion report generation
- OPA compilation testing
"""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

import pytest

# Governance and constitutional compliance test markers
pytestmark = [pytest.mark.governance, pytest.mark.constitutional]

from ..enterprise_sso.policy_converter import (
    CONSTITUTIONAL_HASH,
    ConversionReport,
    ConversionResult,
    ConversionSeverity,
    ConversionWarning,
    OPAValidator,
    PolicyConverter,
    PolicyFormat,
)

# =============================================================================
# Test Classes
# =============================================================================


class TestJSONToRegoConversion:
    """Test JSON policy to Rego conversion."""

    @pytest.fixture
    def converter(self):
        return PolicyConverter()

    def test_convert_simple_json_policy(self, converter):
        """Test converting a simple JSON policy."""
        json_policy = {
            "rules": [
                {
                    "name": "allow_read",
                    "effect": "allow",
                    "conditions": [{"field": "action", "operator": "equals", "value": "read"}],
                }
            ]
        }

        result = converter.convert_json(json_policy)

        assert result.success is True
        assert result.source_format == PolicyFormat.JSON
        assert "package policy" in result.rego_policy
        assert "allow if" in result.rego_policy
        assert CONSTITUTIONAL_HASH in result.rego_policy

    def test_convert_json_with_allow_rules(self, converter):
        """Test JSON policy with allow rules."""
        json_policy = {
            "allow": [
                {"action": "read", "resource": "documents"},
                {"action": "write", "resource": "reports"},
            ]
        }

        result = converter.convert_json(json_policy)

        assert result.success is True
        assert "default allow := false" in result.rego_policy
        assert "allow if" in result.rego_policy
        assert "read" in result.rego_policy

    def test_convert_json_with_deny_rules(self, converter):
        """Test JSON policy with deny rules."""
        json_policy = {
            "deny": [
                {"action": "delete", "resource": "critical"},
            ]
        }

        result = converter.convert_json(json_policy)

        assert result.success is True
        assert "deny if" in result.rego_policy
        assert "delete" in result.rego_policy

    def test_convert_json_with_conditions(self, converter):
        """Test JSON policy with conditions."""
        json_policy = {
            "conditions": [
                {"field": "role", "operator": "equals", "value": "admin"},
                {"field": "department", "operator": "in", "value": ["engineering", "security"]},
            ]
        }

        result = converter.convert_json(json_policy)

        assert result.success is True
        assert "input.role ==" in result.rego_policy
        assert "input.department in" in result.rego_policy

    def test_convert_json_with_unknown_operator(self, converter):
        """Test warning for unknown operator."""
        json_policy = {
            "conditions": [
                {"field": "value", "operator": "fuzzy_match", "value": "test"},
            ]
        }

        result = converter.convert_json(json_policy)

        assert result.success is True
        assert len(result.warnings) > 0
        assert any("fuzzy_match" in w.message for w in result.warnings)

    def test_convert_json_with_custom_package(self, converter):
        """Test custom package name."""
        json_policy = {"rules": []}

        result = converter.convert_json(json_policy, package_name="myapp.policies")

        assert result.success is True
        assert "package myapp.policies" in result.rego_policy

    def test_convert_json_records_conversion_time(self, converter):
        """Test that conversion time is recorded."""
        json_policy = {"rules": [{"name": "test", "effect": "allow", "conditions": []}]}

        result = converter.convert_json(json_policy)

        assert result.conversion_time_ms > 0

    def test_convert_json_includes_constitutional_hash(self, converter):
        """Test constitutional hash is included."""
        json_policy = {"action": "test"}

        result = converter.convert_json(json_policy)

        assert result.constitutional_hash == CONSTITUTIONAL_HASH
        assert CONSTITUTIONAL_HASH in result.rego_policy


class TestYAMLToRegoConversion:
    """Test YAML policy to Rego conversion."""

    @pytest.fixture
    def converter(self):
        return PolicyConverter()

    def test_convert_simple_yaml_policy(self, converter):
        """Test converting a simple YAML policy."""
        yaml_content = """
policy:
  effect: allow
  principal: admin
  action: read
  resource: documents
"""

        result = converter.convert_yaml(yaml_content)

        assert result.success is True
        assert result.source_format == PolicyFormat.YAML
        assert "package policy" in result.rego_policy
        assert CONSTITUTIONAL_HASH in result.rego_policy

    def test_convert_yaml_with_rules(self, converter):
        """Test YAML with rules list."""
        yaml_content = """
rules:
  - allow_admin_read
  - deny_guest_write
"""

        result = converter.convert_yaml(yaml_content)

        assert result.success is True
        assert "allow if" in result.rego_policy

    def test_convert_yaml_with_key_values(self, converter):
        """Test YAML with simple key-value pairs."""
        yaml_content = """
action: read
resource: documents
principal: user
"""

        result = converter.convert_yaml(yaml_content)

        assert result.success is True
        assert "input.action ==" in result.rego_policy

    def test_convert_yaml_with_custom_package(self, converter):
        """Test custom package name for YAML."""
        yaml_content = "action: test"

        result = converter.convert_yaml(yaml_content, package_name="custom.pkg")

        assert result.success is True
        assert "package custom.pkg" in result.rego_policy

    def test_convert_yaml_includes_source_comment(self, converter):
        """Test YAML conversion includes source comment."""
        yaml_content = "test: value"

        result = converter.convert_yaml(yaml_content)

        assert "Converted from YAML" in result.rego_policy


class TestCustomDSLConversion:
    """Test custom DSL parsing and conversion."""

    @pytest.fixture
    def converter(self):
        return PolicyConverter()

    def test_convert_allow_when_statement(self, converter):
        """Test ALLOW when statement."""
        dsl_content = "ALLOW when role equals admin"

        result = converter.convert_dsl(dsl_content)

        assert result.success is True
        assert "allow if" in result.rego_policy
        assert 'input.role == "admin"' in result.rego_policy

    def test_convert_deny_when_statement(self, converter):
        """Test DENY when statement."""
        dsl_content = "DENY when action equals delete"

        result = converter.convert_dsl(dsl_content)

        assert result.success is True
        assert "deny if" in result.rego_policy
        assert 'input.action == "delete"' in result.rego_policy

    def test_convert_if_then_statement(self, converter):
        """Test IF-THEN statement."""
        dsl_content = "IF role equals admin THEN allow"

        result = converter.convert_dsl(dsl_content)

        assert result.success is True
        assert "allow if" in result.rego_policy

    def test_convert_contains_operator(self, converter):
        """Test contains operator."""
        dsl_content = "ALLOW when email contains @company.com"

        result = converter.convert_dsl(dsl_content)

        assert result.success is True
        assert "contains(input.email" in result.rego_policy

    def test_convert_in_operator(self, converter):
        """Test in operator."""
        dsl_content = "ALLOW when department in [engineering, security, devops]"

        result = converter.convert_dsl(dsl_content)

        assert result.success is True
        assert "input.department in" in result.rego_policy

    def test_convert_multiple_statements(self, converter):
        """Test multiple DSL statements."""
        dsl_content = """
ALLOW when role equals admin
DENY when status equals suspended
IF department equals security THEN allow
"""

        result = converter.convert_dsl(dsl_content)

        assert result.success is True
        assert result.rego_policy.count("if {") >= 3

    def test_dsl_with_comments(self, converter):
        """Test DSL with comments."""
        dsl_content = """
# This is a comment
ALLOW when role equals admin
// Another comment style
DENY when action equals delete
"""

        result = converter.convert_dsl(dsl_content)

        assert result.success is True

    def test_convert_comparison_operators(self, converter):
        """Test conversion of comparison operators in DSL."""
        dsl_content = """
ALLOW when age > 18
ALLOW when score <= 100
ALLOW when status != inactive
ALLOW when rating >= 4.5
"""
        result = converter.convert_dsl(dsl_content)

        assert result.success is True
        assert "input.age > 18" in result.rego_policy
        assert "input.score <= 100" in result.rego_policy
        assert 'input.status != "inactive"' in result.rego_policy
        assert "input.rating >= 4.5" in result.rego_policy
        # Comments should be ignored, only 2 rules should be converted

    def test_dsl_unknown_syntax_warning(self, converter):
        """Test warning for unknown DSL syntax."""
        dsl_content = "INVALID SYNTAX HERE"

        result = converter.convert_dsl(dsl_content)

        assert result.success is True
        assert len(result.warnings) > 0
        assert result.warnings[0].severity == ConversionSeverity.WARNING

    def test_dsl_includes_line_numbers(self, converter):
        """Test that DSL conversion includes line numbers."""
        dsl_content = """
ALLOW when role equals admin
DENY when action equals delete
"""

        result = converter.convert_dsl(dsl_content)

        assert "DSL line" in result.rego_policy


class TestConstitutionalComplianceInjection:
    """Test constitutional compliance injection."""

    @pytest.fixture
    def converter(self):
        return PolicyConverter()

    def test_constitutional_hash_in_header(self, converter):
        """Test constitutional hash in policy header."""
        result = converter.convert_json({"action": "test"})

        assert f"Constitutional Hash: {CONSTITUTIONAL_HASH}" in result.rego_policy

    def test_constitutional_compliant_variable(self, converter):
        """Test constitutional_compliant variable is added."""
        result = converter.convert_json({"action": "test"})

        assert "constitutional_compliant := true" in result.rego_policy

    def test_constitutional_hash_variable(self, converter):
        """Test constitutional_hash variable is added."""
        result = converter.convert_json({"action": "test"})

        assert f'constitutional_hash := "{CONSTITUTIONAL_HASH}"' in result.rego_policy

    def test_decision_metadata_includes_hash(self, converter):
        """Test decision_metadata includes constitutional hash."""
        result = converter.convert_json({"action": "test"})

        assert "decision_metadata" in result.rego_policy
        assert '"constitutional_hash": constitutional_hash' in result.rego_policy

    def test_invalid_constitutional_hash_raises(self):
        """Test that invalid constitutional hash raises error."""
        with pytest.raises(ValueError) as exc_info:
            PolicyConverter(constitutional_hash="invalid_hash")

        assert "Invalid constitutional hash" in str(exc_info.value)


class TestConversionReportGeneration:
    """Test conversion report generation."""

    @pytest.fixture
    def converter(self):
        return PolicyConverter()

    def test_batch_convert_single_policy(self, converter):
        """Test batch conversion with single policy."""
        policies = [{"format": "json", "content": {"action": "test"}}]

        report = converter.convert_batch(policies)

        assert report.total_policies == 1
        assert report.successful == 1
        assert report.failed == 0
        assert report.coverage_percentage == 100.0

    def test_batch_convert_multiple_formats(self, converter):
        """Test batch conversion with multiple formats."""
        policies = [
            {"format": "json", "content": {"action": "test1"}},
            {"format": "yaml", "content": "action: test2"},
            {"format": "dsl", "content": "ALLOW when role equals admin"},
        ]

        report = converter.convert_batch(policies)

        assert report.total_policies == 3
        assert report.successful == 3
        assert len(report.results) == 3

    def test_batch_convert_with_failures(self, converter):
        """Test batch conversion with some failures."""
        policies = [
            {"format": "json", "content": {"action": "test"}},
            {"format": "unknown", "content": "invalid"},
        ]

        report = converter.convert_batch(policies)

        assert report.total_policies == 2
        assert report.successful == 1
        assert report.failed == 1
        assert report.coverage_percentage == 50.0

    def test_batch_convert_tracks_warnings(self, converter):
        """Test batch conversion tracks warnings."""
        policies = [
            {
                "format": "json",
                "content": {"conditions": [{"field": "x", "operator": "unknown_op", "value": "y"}]},
            },
        ]

        report = converter.convert_batch(policies)

        assert report.warnings_count > 0

    def test_report_includes_constitutional_hash(self, converter):
        """Test report includes constitutional hash."""
        policies = [{"format": "json", "content": {}}]

        report = converter.convert_batch(policies)

        assert report.constitutional_hash == CONSTITUTIONAL_HASH

    def test_report_includes_timestamp(self, converter):
        """Test report includes generation timestamp."""
        policies = [{"format": "json", "content": {}}]

        report = converter.convert_batch(policies)

        assert report.generated_at is not None
        assert isinstance(report.generated_at, datetime)

    def test_report_includes_all_results(self, converter):
        """Test report includes all individual results."""
        policies = [
            {"format": "json", "content": {"a": 1}},
            {"format": "json", "content": {"b": 2}},
            {"format": "json", "content": {"c": 3}},
        ]

        report = converter.convert_batch(policies)

        assert len(report.results) == 3
        for result in report.results:
            assert isinstance(result, ConversionResult)


class TestOPACompilationTesting:
    """Test OPA compilation validation."""

    @pytest.fixture
    def converter(self):
        c = PolicyConverter()
        c.set_opa_validator(OPAValidator())
        return c

    def test_valid_rego_passes_opa_check(self, converter):
        """Test valid Rego passes OPA validation."""
        result = converter.convert_json({"action": "test"})

        assert result.success is True
        assert result.opa_valid is True

    def test_opa_validator_checks_package(self):
        """Test OPA validator checks for package."""
        validator = OPAValidator()

        # Missing package should fail
        assert validator.validate("allow := true") is False

        # With package should pass
        assert validator.validate("package test\nallow := true") is True

    def test_opa_validator_checks_braces(self):
        """Test OPA validator checks balanced braces."""
        validator = OPAValidator()

        # Unbalanced braces should fail
        assert validator.validate("package test\nallow if {") is False

        # Balanced should pass
        assert validator.validate("package test\nallow if {}") is True

    def test_converted_policies_are_opa_valid(self, converter):
        """Test all conversion methods produce OPA-valid output."""
        json_result = converter.convert_json({"action": "test"})
        yaml_result = converter.convert_yaml("action: test")
        dsl_result = converter.convert_dsl("ALLOW when role equals admin")

        assert json_result.opa_valid is True
        assert yaml_result.opa_valid is True
        assert dsl_result.opa_valid is True


class TestConversionEdgeCases:
    """Test edge cases and error handling."""

    @pytest.fixture
    def converter(self):
        return PolicyConverter()

    def test_empty_json_policy(self, converter):
        """Test empty JSON policy."""
        result = converter.convert_json({})

        assert result.success is True
        assert "package policy" in result.rego_policy

    def test_empty_yaml_content(self, converter):
        """Test empty YAML content."""
        result = converter.convert_yaml("")

        assert result.success is True

    def test_empty_dsl_content(self, converter):
        """Test empty DSL content."""
        result = converter.convert_dsl("")

        assert result.success is True

    def test_deeply_nested_json(self, converter):
        """Test deeply nested JSON structure."""
        json_policy = {
            "rules": [
                {
                    "name": "nested",
                    "effect": "allow",
                    "conditions": [
                        {
                            "field": "data.level1.level2.level3",
                            "operator": "equals",
                            "value": "deep",
                        }
                    ],
                }
            ]
        }

        result = converter.convert_json(json_policy)

        assert result.success is True
        assert "level1.level2.level3" in result.rego_policy

    def test_special_characters_in_values(self, converter):
        """Test special characters in values."""
        json_policy = {
            "conditions": [
                {"field": "path", "operator": "equals", "value": "/api/v1/users?id=123&name=test"}
            ]
        }

        result = converter.convert_json(json_policy)

        assert result.success is True
        assert "/api/v1/users" in result.rego_policy

    def test_unicode_in_policy(self, converter):
        """Test Unicode characters in policy."""
        json_policy = {"conditions": [{"field": "name", "operator": "equals", "value": "用户名"}]}

        result = converter.convert_json(json_policy)

        assert result.success is True
        # JSON encoding may escape unicode - check for either form
        assert "用户名" in result.rego_policy or "\\u7528\\u6237\\u540d" in result.rego_policy

    def test_large_policy_conversion(self, converter):
        """Test conversion of large policy."""
        json_policy = {
            "rules": [
                {
                    "name": f"rule_{i}",
                    "effect": "allow",
                    "conditions": [
                        {"field": f"field_{j}", "operator": "equals", "value": f"value_{j}"}
                        for j in range(10)
                    ],
                }
                for i in range(100)
            ]
        }

        result = converter.convert_json(json_policy)

        assert result.success is True
        assert result.conversion_time_ms < 1000  # Should complete in under 1 second

    def test_dsl_case_insensitivity(self, converter):
        """Test DSL is case insensitive for keywords."""
        dsl_variants = [
            "ALLOW when role equals admin",
            "allow when role equals admin",
            "Allow When Role Equals admin",
        ]

        for dsl in dsl_variants:
            result = converter.convert_dsl(dsl)
            assert result.success is True
            assert "allow if" in result.rego_policy


class TestConversionWarnings:
    """Test conversion warnings and error handling."""

    @pytest.fixture
    def converter(self):
        return PolicyConverter()

    def test_warning_severity_levels(self, converter):
        """Test different warning severity levels."""
        # Create warnings of different severities
        warnings = [
            ConversionWarning(severity=ConversionSeverity.INFO, message="Info"),
            ConversionWarning(severity=ConversionSeverity.WARNING, message="Warning"),
            ConversionWarning(severity=ConversionSeverity.ERROR, message="Error"),
            ConversionWarning(severity=ConversionSeverity.CRITICAL, message="Critical"),
        ]

        assert warnings[0].severity == ConversionSeverity.INFO
        assert warnings[1].severity == ConversionSeverity.WARNING
        assert warnings[2].severity == ConversionSeverity.ERROR
        assert warnings[3].severity == ConversionSeverity.CRITICAL

    def test_warning_includes_line_number(self, converter):
        """Test warnings include line numbers."""
        dsl_content = """
ALLOW when role equals admin
INVALID LINE HERE
DENY when action equals delete
"""

        result = converter.convert_dsl(dsl_content)

        # Find warning with line number
        line_warnings = [w for w in result.warnings if w.line_number is not None]
        assert len(line_warnings) > 0

    def test_warning_includes_source_element(self, converter):
        """Test warnings include source element."""
        dsl_content = "UNKNOWN_COMMAND test"

        result = converter.convert_dsl(dsl_content)

        assert len(result.warnings) > 0
        assert result.warnings[0].source_element is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
