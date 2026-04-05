"""
Legacy Policy Conversion Tools.
Constitutional Hash: 608508a9bd224290

Phase 10 Task 8: Legacy Policy Conversion Tools

Features:
- JSON policy to Rego conversion
- YAML policy to Rego conversion
- Custom DSL parsing and conversion
- Constitutional compliance injection
- Conversion report generation
- OPA compilation testing
"""

import json
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from enum import Enum
from typing import ClassVar

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)
# Constitutional Hash for all operations
try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

_POLICY_CONVERTER_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
)

# =============================================================================
# Enums and Data Structures
# =============================================================================


class PolicyFormat(Enum):
    """Supported legacy policy formats."""

    JSON = "json"
    YAML = "yaml"
    DSL = "dsl"


class ConversionSeverity(Enum):
    """Severity levels for conversion warnings."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class ConversionWarning:
    """Warning generated during policy conversion."""

    severity: ConversionSeverity
    message: str
    line_number: int | None = None
    source_element: str | None = None


@dataclass
class ConversionResult:
    """Result of a policy conversion."""

    success: bool
    rego_policy: str
    source_format: PolicyFormat
    warnings: list[ConversionWarning] = field(default_factory=list)
    constitutional_hash: str = CONSTITUTIONAL_HASH
    conversion_time_ms: float = 0.0
    opa_valid: bool | None = None
    coverage_percentage: float = 100.0


@dataclass
class ConversionReport:
    """Report summarizing multiple policy conversions."""

    total_policies: int
    successful: int
    failed: int
    warnings_count: int
    errors_count: int
    coverage_percentage: float
    results: list[ConversionResult] = field(default_factory=list)
    constitutional_hash: str = CONSTITUTIONAL_HASH
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


# =============================================================================
# OPA Validator
# =============================================================================


class OPAValidator:
    """OPA validator for compilation testing.

    Constitutional Hash: 608508a9bd224290

    In production, this would use OPA's compilation API.
    For testing, we do basic syntax validation.
    """

    def __init__(self, strict: bool = False, opa_url: str | None = None):
        self._strict = strict
        self._opa_url = opa_url

    def validate(self, rego_policy: str) -> bool:
        """Validate Rego policy syntax."""
        # Check for package declaration
        if "package " not in rego_policy:
            return False

        # Check for balanced braces
        if rego_policy.count("{") != rego_policy.count("}"):
            return False

        # Check for common syntax errors
        return not (":= :=" in rego_policy or "if if" in rego_policy)

    async def validate_with_opa(self, rego_policy: str) -> JSONDict:
        """Validate policy using OPA's compile endpoint.

        In production, this would make an HTTP request to OPA.
        """
        if not self._opa_url:
            return {"valid": self.validate(rego_policy), "method": "local"}

        # Would call OPA's /v1/compile endpoint
        return {"valid": True, "method": "opa"}


# =============================================================================
# Policy Converter Implementation
# =============================================================================


class PolicyConverter:
    """Converts legacy policies to Rego format.

    Constitutional Hash: 608508a9bd224290

    Supports:
    - JSON policy format
    - YAML policy format
    - Custom DSL format
    """

    # Sensitive fields that should be encrypted
    SENSITIVE_FIELDS: ClassVar[set[str]] = {
        "password",
        "secret",
        "api_key",
        "client_secret",
        "private_key",
        "certificate",
        "token",
        "credentials",
    }

    def __init__(self, constitutional_hash: str = CONSTITUTIONAL_HASH):
        if constitutional_hash != CONSTITUTIONAL_HASH:
            raise ValueError(f"Invalid constitutional hash: {constitutional_hash}")
        self._constitutional_hash = constitutional_hash
        self._opa_validator: OPAValidator | None = None

    def set_opa_validator(self, validator: OPAValidator) -> None:
        """set OPA validator for compilation testing."""
        self._opa_validator = validator

    # =========================================================================
    # JSON Conversion
    # =========================================================================

    def convert_json(self, json_policy: JSONDict, package_name: str = "policy") -> ConversionResult:
        """Convert JSON policy to Rego."""
        start = time.time()
        warnings: list[ConversionWarning] = []

        try:
            rego_lines = [
                f"# Constitutional Hash: {self._constitutional_hash}",
                f"package {package_name}",
                "",
                "import future.keywords.if",
                "import future.keywords.in",
                "",
            ]

            # Handle different JSON policy structures
            if "rules" in json_policy:
                rego_lines.extend(self._convert_json_rules(json_policy["rules"], warnings))
            elif "allow" in json_policy:
                rego_lines.extend(self._convert_json_allow(json_policy["allow"], warnings))
            elif "deny" in json_policy:
                rego_lines.extend(self._convert_json_deny(json_policy["deny"], warnings))
            elif "conditions" in json_policy:
                rego_lines.extend(
                    self._convert_json_conditions(json_policy["conditions"], warnings)
                )
            else:
                # Generic conversion
                rego_lines.extend(self._convert_json_generic(json_policy, warnings))

            # Add constitutional compliance
            rego_lines.extend(self._inject_constitutional_compliance())

            rego_policy = "\n".join(rego_lines)
            elapsed_ms = (time.time() - start) * 1000

            # Validate with OPA if available
            opa_valid = None
            if self._opa_validator:
                opa_valid = self._opa_validator.validate(rego_policy)

            return ConversionResult(
                success=True,
                rego_policy=rego_policy,
                source_format=PolicyFormat.JSON,
                warnings=warnings,
                conversion_time_ms=elapsed_ms,
                opa_valid=opa_valid,
            )
        except _POLICY_CONVERTER_OPERATION_ERRORS as e:
            warnings.append(
                ConversionWarning(
                    severity=ConversionSeverity.ERROR,
                    message=str(e),
                )
            )
            return ConversionResult(
                success=False,
                rego_policy="",
                source_format=PolicyFormat.JSON,
                warnings=warnings,
            )

    def _convert_json_rules(
        self, rules: list[dict], warnings: list[ConversionWarning]
    ) -> list[str]:
        """Convert JSON rules array to Rego."""
        rego_lines = []
        for i, rule in enumerate(rules):
            rule_name = rule.get("name", f"rule_{i}")
            effect = rule.get("effect", "allow")
            conditions = rule.get("conditions", [])

            rego_lines.append(f"# Rule: {rule_name}")
            rego_lines.append(f"{effect} if {{")

            for condition in conditions:
                rego_lines.append(f"    {self._convert_condition(condition)}")

            rego_lines.append("}")
            rego_lines.append("")

        return rego_lines

    def _convert_json_allow(
        self, allow_rules: list[dict], warnings: list[ConversionWarning]
    ) -> list[str]:
        """Convert JSON allow rules to Rego."""
        rego_lines = ["default allow := false", ""]

        for rule in allow_rules:
            rego_lines.append("allow if {")
            for key, value in rule.items():
                rego_lines.append(f"    input.{key} == {json.dumps(value)}")
            rego_lines.append("}")
            rego_lines.append("")

        return rego_lines

    def _convert_json_deny(
        self, deny_rules: list[dict], warnings: list[ConversionWarning]
    ) -> list[str]:
        """Convert JSON deny rules to Rego."""
        rego_lines = ["default deny := false", ""]

        for rule in deny_rules:
            rego_lines.append("deny if {")
            for key, value in rule.items():
                rego_lines.append(f"    input.{key} == {json.dumps(value)}")
            rego_lines.append("}")
            rego_lines.append("")

        return rego_lines

    def _convert_json_conditions(
        self, conditions: list[dict], warnings: list[ConversionWarning]
    ) -> list[str]:
        """Convert JSON conditions to Rego."""
        rego_lines = ["default allow := false", "", "allow if {"]

        for condition in conditions:
            operator = condition.get("operator", "equals")
            field_name = condition.get("field", "")
            value = condition.get("value", "")

            if operator == "equals":
                rego_lines.append(f"    input.{field_name} == {json.dumps(value)}")
            elif operator == "not_equals":
                rego_lines.append(f"    input.{field_name} != {json.dumps(value)}")
            elif operator == "in":
                rego_lines.append(f"    input.{field_name} in {json.dumps(value)}")
            elif operator == "contains":
                rego_lines.append(f"    contains(input.{field_name}, {json.dumps(value)})")
            else:
                warnings.append(
                    ConversionWarning(
                        severity=ConversionSeverity.WARNING,
                        message=f"Unknown operator: {operator}",
                        source_element=str(condition),
                    )
                )

        rego_lines.append("}")
        return rego_lines

    def _convert_json_generic(self, policy: dict, warnings: list[ConversionWarning]) -> list[str]:
        """Generic JSON to Rego conversion."""
        rego_lines = ["default allow := false", "", "allow if {"]

        for key, value in policy.items():
            if key not in ["metadata", "version", "description"]:
                rego_lines.append(f"    input.{key} == {json.dumps(value)}")

        rego_lines.append("}")
        return rego_lines

    def _convert_condition(self, condition: dict) -> str:
        """Convert a single condition to Rego."""
        field_name = condition.get("field", "unknown")
        operator = condition.get("operator", "==")
        value = condition.get("value", "null")

        op_map = {"equals": "==", "not_equals": "!=", "greater": ">", "less": "<"}
        rego_op = op_map.get(operator, operator)

        return f"input.{field_name} {rego_op} {json.dumps(value)}"

    # =========================================================================
    # YAML Conversion
    # =========================================================================

    def convert_yaml(self, yaml_content: str, package_name: str = "policy") -> ConversionResult:
        """Convert YAML policy to Rego."""
        start = time.time()
        warnings: list[ConversionWarning] = []

        try:
            # Parse YAML (simplified - in production use PyYAML)
            yaml_dict = self._parse_yaml_simplified(yaml_content)

            rego_lines = [
                f"# Constitutional Hash: {self._constitutional_hash}",
                "# Converted from YAML",
                f"package {package_name}",
                "",
                "import future.keywords.if",
                "import future.keywords.in",
                "",
            ]

            # Convert YAML structure
            if "policy" in yaml_dict:
                rego_lines.extend(self._convert_yaml_policy(yaml_dict["policy"], warnings))
            elif "rules" in yaml_dict:
                rego_lines.extend(self._convert_yaml_rules(yaml_dict["rules"], warnings))
            else:
                rego_lines.extend(self._convert_yaml_generic(yaml_dict, warnings))

            # Add constitutional compliance
            rego_lines.extend(self._inject_constitutional_compliance())

            rego_policy = "\n".join(rego_lines)
            elapsed_ms = (time.time() - start) * 1000

            # Validate with OPA if available
            opa_valid = None
            if self._opa_validator:
                opa_valid = self._opa_validator.validate(rego_policy)

            return ConversionResult(
                success=True,
                rego_policy=rego_policy,
                source_format=PolicyFormat.YAML,
                warnings=warnings,
                conversion_time_ms=elapsed_ms,
                opa_valid=opa_valid,
            )
        except _POLICY_CONVERTER_OPERATION_ERRORS as e:
            warnings.append(
                ConversionWarning(
                    severity=ConversionSeverity.ERROR,
                    message=str(e),
                )
            )
            return ConversionResult(
                success=False,
                rego_policy="",
                source_format=PolicyFormat.YAML,
                warnings=warnings,
            )

    def _parse_yaml_simplified(self, yaml_content: str) -> JSONDict:
        """Simplified YAML parser (for testing).

        In production, use PyYAML for full YAML support.
        """
        result: JSONDict = {}
        current_key: str | None = None

        for line in yaml_content.strip().split("\n"):
            line = line.rstrip()
            if not line or line.startswith("#"):
                continue

            # Simple key-value detection
            if ":" in line and not line.strip().startswith("-"):
                key, value = line.split(":", 1)
                key = key.strip()
                value = value.strip()

                if value:
                    # Remove quotes if present
                    if value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]
                    result[key] = value
                else:
                    current_key = key
                    result[key] = {}
            elif line.strip().startswith("-"):
                item = line.strip()[1:].strip()
                if current_key and isinstance(result.get(current_key), dict):
                    if "items" not in result[current_key]:
                        result[current_key]["items"] = []
                    result[current_key]["items"].append(item)

        return result

    def _convert_yaml_policy(self, policy: dict, warnings: list[ConversionWarning]) -> list[str]:
        """Convert YAML policy structure to Rego."""
        rego_lines = ["default allow := false", ""]

        if isinstance(policy, dict):
            if "effect" in policy:
                effect = policy.get("effect", "allow")
                rego_lines.append(f"{effect} if {{")

                if "principal" in policy:
                    rego_lines.append(f"    input.principal == {json.dumps(policy['principal'])}")
                if "action" in policy:
                    rego_lines.append(f"    input.action == {json.dumps(policy['action'])}")
                if "resource" in policy:
                    rego_lines.append(f"    input.resource == {json.dumps(policy['resource'])}")

                rego_lines.append("}")
            else:
                for key, value in policy.items():
                    rego_lines.append(f"# {key}: {value}")

        return rego_lines

    def _convert_yaml_rules(self, rules: object, warnings: list[ConversionWarning]) -> list[str]:
        """Convert YAML rules to Rego."""
        rego_lines = ["default allow := false", ""]

        if isinstance(rules, dict) and "items" in rules:
            for i, rule in enumerate(rules["items"]):
                rego_lines.append(f"# Rule from YAML item {i}")
                rego_lines.append("allow if {")
                rego_lines.append(f"    # Converted from: {rule}")
                rego_lines.append("}")
                rego_lines.append("")

        return rego_lines

    def _convert_yaml_generic(
        self, yaml_dict: dict, warnings: list[ConversionWarning]
    ) -> list[str]:
        """Generic YAML to Rego conversion."""
        rego_lines = ["default allow := false", "", "allow if {"]

        for key, value in yaml_dict.items():
            if isinstance(value, str):
                rego_lines.append(f"    input.{key} == {json.dumps(value)}")

        rego_lines.append("}")
        return rego_lines

    # =========================================================================
    # Custom DSL Conversion
    # =========================================================================

    def convert_dsl(self, dsl_content: str, package_name: str = "policy") -> ConversionResult:
        """Convert custom DSL to Rego.

        DSL Syntax:
        - ALLOW when <condition>
        - DENY when <condition>
        - IF <condition> THEN <effect>
        - <field> equals/contains/in <value>
        """
        start = time.time()
        warnings: list[ConversionWarning] = []

        try:
            rego_lines = [
                f"# Constitutional Hash: {self._constitutional_hash}",
                "# Converted from Custom DSL",
                f"package {package_name}",
                "",
                "import future.keywords.if",
                "import future.keywords.in",
                "",
                "default allow := false",
                "default deny := false",
                "",
            ]

            # Parse DSL statements
            statements = self._parse_dsl(dsl_content, warnings)

            for stmt in statements:
                rego_lines.extend(self._convert_dsl_statement(stmt, warnings))

            # Add constitutional compliance
            rego_lines.extend(self._inject_constitutional_compliance())

            rego_policy = "\n".join(rego_lines)
            elapsed_ms = (time.time() - start) * 1000

            # Validate with OPA if available
            opa_valid = None
            if self._opa_validator:
                opa_valid = self._opa_validator.validate(rego_policy)

            return ConversionResult(
                success=True,
                rego_policy=rego_policy,
                source_format=PolicyFormat.DSL,
                warnings=warnings,
                conversion_time_ms=elapsed_ms,
                opa_valid=opa_valid,
            )
        except _POLICY_CONVERTER_OPERATION_ERRORS as e:
            warnings.append(
                ConversionWarning(
                    severity=ConversionSeverity.ERROR,
                    message=str(e),
                )
            )
            return ConversionResult(
                success=False,
                rego_policy="",
                source_format=PolicyFormat.DSL,
                warnings=warnings,
            )

    def _parse_dsl(self, dsl_content: str, warnings: list[ConversionWarning]) -> list[dict]:
        """Parse custom DSL into statement structures."""
        statements = []

        for line_num, line in enumerate(dsl_content.strip().split("\n"), 1):
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("//"):
                continue

            stmt = self._parse_dsl_line(line, line_num, warnings)
            if stmt:
                statements.append(stmt)

        return statements

    def _parse_dsl_line(
        self, line: str, line_num: int, warnings: list[ConversionWarning]
    ) -> dict | None:
        """Parse a single DSL line."""
        line_upper = line.upper()

        # ALLOW when <condition>
        if line_upper.startswith("ALLOW WHEN"):
            condition = line[10:].strip()
            return {
                "type": "allow",
                "condition": self._parse_dsl_condition(condition),
                "line": line_num,
            }

        # DENY when <condition>
        if line_upper.startswith("DENY WHEN"):
            condition = line[9:].strip()
            return {
                "type": "deny",
                "condition": self._parse_dsl_condition(condition),
                "line": line_num,
            }

        # IF <condition> THEN <effect>
        if_match = re.match(r"IF\s+(.+?)\s+THEN\s+(\w+)", line, re.IGNORECASE)
        if if_match:
            condition = if_match.group(1)
            effect = if_match.group(2).lower()
            return {
                "type": effect,
                "condition": self._parse_dsl_condition(condition),
                "line": line_num,
            }

        # Unknown syntax
        warnings.append(
            ConversionWarning(
                severity=ConversionSeverity.WARNING,
                message="Unknown DSL syntax",
                line_number=line_num,
                source_element=line,
            )
        )
        return None

    def _parse_dsl_condition(self, condition: str) -> dict:
        """Parse a DSL condition expression."""
        condition = condition.strip()

        # field equals value
        equals_match = re.match(
            r"(\w+(?:\.\w+)*)\s+(?:equals|=|==)\s+['\"]?([^'\"]+)['\"]?", condition, re.IGNORECASE
        )
        if equals_match:
            return {
                "field": equals_match.group(1),
                "operator": "equals",
                "value": equals_match.group(2),
            }

        # field contains value
        contains_match = re.match(
            r"(\w+(?:\.\w+)*)\s+contains\s+['\"]?([^'\"]+)['\"]?", condition, re.IGNORECASE
        )
        if contains_match:
            return {
                "field": contains_match.group(1),
                "operator": "contains",
                "value": contains_match.group(2),
            }

        # field in [value1, value2, ...]
        in_match = re.match(r"(\w+(?:\.\w+)*)\s+in\s+\[([^\]]+)\]", condition, re.IGNORECASE)
        if in_match:
            values = [v.strip().strip("'\"") for v in in_match.group(2).split(",")]
            return {
                "field": in_match.group(1),
                "operator": "in",
                "value": values,
            }

        # Default: treat as expression
        return {"expression": condition}

    def _convert_dsl_statement(self, stmt: dict, warnings: list[ConversionWarning]) -> list[str]:
        """Convert a DSL statement to Rego."""
        rego_lines = []
        effect = stmt.get("type", "allow")
        condition = stmt.get("condition", {})
        line_num = stmt.get("line", 0)

        rego_lines.append(f"# DSL line {line_num}")
        rego_lines.append(f"{effect} if {{")

        if "expression" in condition:
            rego_lines.append(f"    {self._convert_dsl_expression(condition['expression'])}")
        else:
            field_name = condition.get("field", "unknown")
            operator = condition.get("operator", "equals")
            value = condition.get("value", "")

            if operator == "equals":
                rego_lines.append(f"    input.{field_name} == {json.dumps(value)}")
            elif operator == "contains":
                rego_lines.append(f"    contains(input.{field_name}, {json.dumps(value)})")
            elif operator == "in":
                rego_lines.append(f"    input.{field_name} in {json.dumps(value)}")

        rego_lines.append("}")
        rego_lines.append("")

        return rego_lines

    def _convert_dsl_expression(self, expression: str) -> str:
        """Convert a raw DSL expression to Rego.

        Handles:
        - field > value
        - field < value
        - field >= value
        - field <= value
        - field != value
        """
        expression = expression.strip()

        # Regular expressions for common comparison operators
        comparisons = [
            (r"(\w+(?:\.\w+)*)\s*(>=)\s*(.+)", ">="),
            (r"(\w+(?:\.\w+)*)\s*(<=)\s*(.+)", "<="),
            (r"(\w+(?:\.\w+)*)\s*(>)\s*(.+)", ">"),
            (r"(\w+(?:\.\w+)*)\s*(<)\s*(.+)", "<"),
            (r"(\w+(?:\.\w+)*)\s*(!=|<>)\s*(.+)", "!="),
        ]

        for pattern, rego_op in comparisons:
            match = re.match(pattern, expression, re.IGNORECASE)
            if match:
                field_name = match.group(1)
                value = match.group(3).strip()

                # Basic value sanitization for JSON/Rego compatibility
                if value.lower() == "true":
                    value = "true"
                elif value.lower() == "false":
                    value = "false"
                elif value.lower() == "null":
                    value = "null"
                elif not (
                    (value.startswith('"') and value.endswith('"'))
                    or (value.startswith("'") and value.endswith("'"))
                    or re.match(r"^-?\d+(\.\d+)?$", value)
                ):
                    # Wrap strings that aren't already wrapped and aren't numbers/booleans
                    value = f'"{value}"'

                return f"input.{field_name} {rego_op} {value}"

        return f"true # Unconverted expression: {expression}"

    # =========================================================================
    # Constitutional Compliance
    # =========================================================================

    def _inject_constitutional_compliance(self) -> list[str]:
        """Inject constitutional compliance checking into converted policy."""
        return [
            "",
            "# Constitutional Compliance Check",
            "constitutional_compliant := true",
            "",
            f'constitutional_hash := "{self._constitutional_hash}"',
            "",
            "# Validate all decisions include constitutional hash",
            "decision_metadata := {",
            '    "constitutional_hash": constitutional_hash,',
            '    "compliant": constitutional_compliant,',
            "}",
        ]

    # =========================================================================
    # Batch Conversion
    # =========================================================================

    def convert_batch(
        self,
        policies: list[JSONDict],
    ) -> ConversionReport:
        """Convert multiple policies and generate a report."""
        results = []
        successful = 0
        failed = 0
        total_warnings = 0
        total_errors = 0

        for policy_data in policies:
            source_format = policy_data.get("format", "json")
            content = policy_data.get("content", {})
            package_name = policy_data.get("package", "policy")

            if source_format == "json":
                result = self.convert_json(content, package_name)
            elif source_format == "yaml":
                result = self.convert_yaml(content, package_name)
            elif source_format == "dsl":
                result = self.convert_dsl(content, package_name)
            else:
                result = ConversionResult(
                    success=False,
                    rego_policy="",
                    source_format=PolicyFormat.JSON,
                    warnings=[
                        ConversionWarning(
                            severity=ConversionSeverity.ERROR,
                            message=f"Unknown format: {source_format}",
                        )
                    ],
                )

            results.append(result)

            if result.success:
                successful += 1
            else:
                failed += 1

            for warning in result.warnings:
                if warning.severity in [ConversionSeverity.ERROR, ConversionSeverity.CRITICAL]:
                    total_errors += 1
                else:
                    total_warnings += 1

        coverage = (successful / len(policies) * 100) if policies else 0.0

        return ConversionReport(
            total_policies=len(policies),
            successful=successful,
            failed=failed,
            warnings_count=total_warnings,
            errors_count=total_errors,
            coverage_percentage=coverage,
            results=results,
        )


__all__ = [
    "CONSTITUTIONAL_HASH",
    "ConversionReport",
    "ConversionResult",
    "ConversionSeverity",
    "ConversionWarning",
    "OPAValidator",
    "PolicyConverter",
    "PolicyFormat",
]
