"""
MACI Tool Filter — Role-Based Tool Access Control for MCP.

Enforces the MACI separation-of-powers principle by restricting which MCP
tools each role may invoke.  Wildcard patterns (``audit_query_*``) are
supported so that new tools are automatically covered when their name
matches an approved prefix.

Role definitions (aligned with maci_enforcement.py):
  - Proposer  : suggests governance actions — read-only tools only.
  - Validator : verifies constitutional compliance — verification tools.
  - Executor  : executes approved actions — write / provisioning tools.

All access denials are logged with structured context for the audit trail.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.maci_role_projection import project_to_mcp_tool_role
from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Role enum (task-specific — maps to the 3-role MACI model described in the
# task brief; deliberately separate from the 7-role MACIRole in
# maci_enforcement.py to avoid coupling this lightweight filter to the full
# enforcement engine.)
# ---------------------------------------------------------------------------


class MACIToolRole(str, Enum):
    """The three canonical MACI roles for tool-level access control."""

    PROPOSER = "proposer"
    VALIDATOR = "validator"
    EXECUTOR = "executor"


# ---------------------------------------------------------------------------
# Default role → tool-pattern matrix
#
# Each value is an ordered list of glob patterns (fnmatch syntax).
# A tool name is *permitted* when it matches at least one pattern in the role's
# list.  Patterns are evaluated left-to-right; first match wins.
#
# Design rationale:
#   Proposer  → read-only:      audit_query_*, policy_list_*, policy_get_*
#   Validator → verification:   audit_verify_*, policy_validate_*, compliance_*
#   Executor  → write actions:  audit_write_*, policy_apply_*, tenant_provision_*
# ---------------------------------------------------------------------------

ROLE_TOOL_MATRIX: dict[MACIToolRole, list[str]] = {
    MACIToolRole.PROPOSER: [
        "audit_query_*",
        "policy_list_*",
        "policy_get_*",
    ],
    MACIToolRole.VALIDATOR: [
        "audit_verify_*",
        "policy_validate_*",
        "compliance_*",
    ],
    MACIToolRole.EXECUTOR: [
        "audit_write_*",
        "policy_apply_*",
        "tenant_provision_*",
    ],
}

# ---------------------------------------------------------------------------
# Configuration dataclass
# ---------------------------------------------------------------------------


@dataclass
class ToolFilterConfig:
    """Runtime configuration for MACIToolFilter.

    Attributes:
        role_tool_matrix: Mapping of role → list of allowed glob patterns.
            Defaults to ``ROLE_TOOL_MATRIX`` when ``None``.
        strict_mode: Deprecated compatibility flag retained for config
            stability. Unknown roles are always denied.
        constitutional_hash: Governance hash embedded in every audit record.
        audit_denials: If ``True`` (default) every denial is emitted to the
            structured logger.
    """

    role_tool_matrix: dict[MACIToolRole, list[str]] | None = None
    strict_mode: bool = True
    constitutional_hash: str = CONSTITUTIONAL_HASH
    audit_denials: bool = True

    def resolved_matrix(self) -> dict[MACIToolRole, list[str]]:
        """Return the effective role → pattern matrix."""
        return self.role_tool_matrix if self.role_tool_matrix is not None else ROLE_TOOL_MATRIX

    @classmethod
    def from_env(cls) -> ToolFilterConfig:
        """Build config from environment variables.

        Recognised variables:

        ``MACI_FILTER_STRICT_MODE``
            Deprecated compatibility flag. Unknown roles are denied
            regardless of this setting.

        ``MACI_FILTER_AUDIT_DENIALS``
            ``"true"`` (default) or ``"false"``.

        ``MACI_FILTER_PROPOSER_PATTERNS``
            Comma-separated glob patterns that override the default proposer
            allowlist.  Example: ``"audit_query_*,policy_get_*"``.

        ``MACI_FILTER_VALIDATOR_PATTERNS``
            Same for the validator role.

        ``MACI_FILTER_EXECUTOR_PATTERNS``
            Same for the executor role.
        """
        strict = os.getenv("MACI_FILTER_STRICT_MODE", "true").lower() == "true"
        audit = os.getenv("MACI_FILTER_AUDIT_DENIALS", "true").lower() == "true"

        env_role_keys = {
            MACIToolRole.PROPOSER: "MACI_FILTER_PROPOSER_PATTERNS",
            MACIToolRole.VALIDATOR: "MACI_FILTER_VALIDATOR_PATTERNS",
            MACIToolRole.EXECUTOR: "MACI_FILTER_EXECUTOR_PATTERNS",
        }
        custom_matrix: dict[MACIToolRole, list[str]] = {}
        matrix_overridden = False

        for role, env_key in env_role_keys.items():
            raw = os.getenv(env_key)
            if raw is not None:
                patterns = [p.strip() for p in raw.split(",") if p.strip()]
                if patterns:
                    custom_matrix[role] = patterns
                    matrix_overridden = True
                    logger.info(
                        "MACI tool filter patterns loaded from env",
                        role=role.value,
                        env_key=env_key,
                        pattern_count=len(patterns),
                    )

        if matrix_overridden:
            # Merge with defaults so un-overridden roles keep their defaults
            merged = dict(ROLE_TOOL_MATRIX)
            merged.update(custom_matrix)
            return cls(role_tool_matrix=merged, strict_mode=strict, audit_denials=audit)

        return cls(strict_mode=strict, audit_denials=audit)


# ---------------------------------------------------------------------------
# Access decision
# ---------------------------------------------------------------------------


@dataclass
class ToolFilterResult:
    """Outcome of a single tool-access check.

    Attributes:
        permitted: ``True`` if the tool call is allowed.
        role: The role that was evaluated.
        tool_name: The tool that was checked.
        matched_pattern: The glob pattern that matched (``None`` on denial).
        reason: Human-readable explanation (logged in audit trail).
        constitutional_hash: Governance hash for traceability.
        evaluated_at: timezone.utc timestamp of the decision.
    """

    permitted: bool
    role: str
    tool_name: str
    matched_pattern: str | None = None
    reason: str = ""
    constitutional_hash: str = CONSTITUTIONAL_HASH
    evaluated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_audit_dict(self) -> JSONDict:
        """Serialise to a structured dict for audit logging."""
        return {
            "permitted": self.permitted,
            "role": self.role,
            "tool_name": self.tool_name,
            "matched_pattern": self.matched_pattern,
            "reason": self.reason,
            "constitutional_hash": self.constitutional_hash,
            "evaluated_at": self.evaluated_at.isoformat(),
        }


# ---------------------------------------------------------------------------
# Core filter
# ---------------------------------------------------------------------------


class MACIToolFilter:
    """Role-based tool access control filter for MCP tool calls.

    This filter enforces the MACI separation-of-powers principle by
    restricting which tools each role may invoke.  It is intentionally
    **stateless** (no I/O, no side effects) so it can be composed into
    any pipeline without coupling concerns.

    Agents NEVER validate their own output — this filter is an independent
    component used by validators, not by the proposing/executing agents
    themselves.

    Example::

        from enhanced_agent_bus.mcp.maci_filter import (
            MACIToolFilter, MACIToolRole,
        )

        flt = MACIToolFilter()

        # Allow
        assert flt.check_access(MACIToolRole.PROPOSER, "audit_query_logs") is True

        # Deny (Proposer cannot write)
        assert flt.check_access(MACIToolRole.PROPOSER, "audit_write_entry") is False

        # Bulk filter
        tools = ["audit_query_logs", "audit_write_entry", "policy_get_v1"]
        allowed = flt.filter_tools(MACIToolRole.PROPOSER, tools)
        # → ["audit_query_logs", "policy_get_v1"]

    Constitutional Hash: 608508a9bd224290
    """

    CONSTITUTIONAL_HASH: str = CONSTITUTIONAL_HASH

    def __init__(self, config: ToolFilterConfig | None = None) -> None:
        """Initialise the filter.

        Args:
            config: Optional ``ToolFilterConfig``.  Defaults to
                ``ToolFilterConfig.from_env()`` which first checks environment
                variables and falls back to the hard-coded
                ``ROLE_TOOL_MATRIX``.
        """
        self._config = config if config is not None else ToolFilterConfig.from_env()
        self._matrix = self._config.resolved_matrix()

        logger.info(
            "MACIToolFilter initialised",
            strict_mode=self._config.strict_mode,
            audit_denials=self._config.audit_denials,
            roles=sorted(r.value for r in self._matrix),
            constitutional_hash=self.CONSTITUTIONAL_HASH,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_access(
        self,
        role: MACIToolRole | str,
        tool_name: str,
        extra: dict[str, Any] | None = None,
    ) -> bool:
        """Return ``True`` if *role* may invoke *tool_name*.

        Args:
            role: MACI role (``MACIToolRole`` or plain string value).
            tool_name: Name of the tool being requested.
            extra: Optional additional context included in the audit record
                on denial (e.g., ``{"agent_id": "agent-007"}``).

        Returns:
            ``True`` when access is permitted; ``False`` otherwise.
        """
        result = self._evaluate(role, tool_name, extra)
        if not result.permitted and self._config.audit_denials:
            self._log_denial(result, extra)
        return result.permitted

    def check_access_detailed(
        self,
        role: MACIToolRole | str,
        tool_name: str,
        extra: dict[str, Any] | None = None,
    ) -> ToolFilterResult:
        """Return a full ``ToolFilterResult`` for the access check.

        Identical to ``check_access`` but exposes the complete decision
        object including the matched pattern and reason, useful for
        building detailed audit trails.

        Args:
            role: MACI role.
            tool_name: Tool being requested.
            extra: Optional audit context.

        Returns:
            ``ToolFilterResult`` with full decision metadata.
        """
        result = self._evaluate(role, tool_name, extra)
        if not result.permitted and self._config.audit_denials:
            self._log_denial(result, extra)
        return result

    def filter_tools(
        self,
        role: MACIToolRole | str,
        tools: list[str],
        extra: dict[str, Any] | None = None,
    ) -> list[str]:
        """Return the subset of *tools* that *role* is permitted to call.

        Preserves the original ordering of ``tools``.  Tools that fail the
        access check are silently removed; each denial is still logged when
        ``config.audit_denials`` is ``True``.

        Args:
            role: MACI role.
            tools: List of candidate tool names.
            extra: Optional audit context applied to each denied tool.

        Returns:
            Filtered list containing only the permitted tool names.
        """
        allowed: list[str] = []
        for tool_name in tools:
            result = self._evaluate(role, tool_name, extra)
            if result.permitted:
                allowed.append(tool_name)
            elif self._config.audit_denials:
                self._log_denial(result, extra)
        return allowed

    def allowed_patterns(self, role: MACIToolRole | str) -> list[str]:
        """Return the list of allowed glob patterns for *role*.

        Returns an empty list for unknown roles.

        Args:
            role: MACI role.

        Returns:
            List of glob pattern strings.
        """
        resolved = self._resolve_role(role)
        if resolved is None:
            return []
        return list(self._matrix.get(resolved, []))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_role(self, role: MACIToolRole | str) -> MACIToolRole | None:
        """Coerce a plain string to ``MACIToolRole``; ``None`` on failure."""
        if isinstance(role, MACIToolRole):
            return role
        try:
            return MACIToolRole(str(role).lower())
        except ValueError:
            projected_role = project_to_mcp_tool_role(role)
            if projected_role is None:
                return None
            return MACIToolRole(projected_role)

    def _evaluate(
        self,
        role: MACIToolRole | str,
        tool_name: str,
        extra: dict[str, Any] | None,
    ) -> ToolFilterResult:
        """Core evaluation: match *tool_name* against *role*'s patterns."""
        resolved_role = self._resolve_role(role)

        # Unknown role handling
        if resolved_role is None:
            reason = f"unknown_role: '{role}' is not a registered MACI tool role; denied"
            return ToolFilterResult(
                permitted=False,
                role=str(role),
                tool_name=tool_name,
                reason=reason,
                constitutional_hash=self.CONSTITUTIONAL_HASH,
            )

        patterns = self._matrix.get(resolved_role, [])

        # Walk patterns in order — first match wins
        for pattern in patterns:
            if fnmatch.fnmatch(tool_name, pattern):
                return ToolFilterResult(
                    permitted=True,
                    role=resolved_role.value,
                    tool_name=tool_name,
                    matched_pattern=pattern,
                    reason=f"permitted: matched pattern '{pattern}'",
                    constitutional_hash=self.CONSTITUTIONAL_HASH,
                )

        # No pattern matched → deny
        reason = (
            f"not_in_allowlist: role='{resolved_role.value}' tool='{tool_name}' "
            f"did not match any of {patterns}"
        )
        return ToolFilterResult(
            permitted=False,
            role=resolved_role.value,
            tool_name=tool_name,
            matched_pattern=None,
            reason=reason,
            constitutional_hash=self.CONSTITUTIONAL_HASH,
        )

    @staticmethod
    def _log_denial(result: ToolFilterResult, extra: dict[str, Any] | None) -> None:
        """Emit a structured warning for every access denial."""
        audit: dict[str, Any] = result.to_audit_dict()
        if extra:
            audit.update(extra)
        logger.warning(
            "MACI tool access denied",
            **{k: v for k, v in audit.items() if k != "permitted"},
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_maci_tool_filter(
    role_tool_matrix: dict[MACIToolRole, list[str]] | None = None,
    strict_mode: bool = True,
    audit_denials: bool = True,
    constitutional_hash: str = CONSTITUTIONAL_HASH,
) -> MACIToolFilter:
    """Factory function for ``MACIToolFilter``.

    Prefer this over direct instantiation when providing programmatic
    configuration instead of environment variables.

    Args:
        role_tool_matrix: Custom role → pattern mapping.  Falls back to the
            default ``ROLE_TOOL_MATRIX`` when ``None``.
        strict_mode: Deprecated compatibility flag retained for config
            stability. Unknown roles are always denied.
        audit_denials: Log denials to the structured logger (default ``True``).
        constitutional_hash: Governance hash for audit records.

    Returns:
        Configured ``MACIToolFilter`` instance.
    """
    config = ToolFilterConfig(
        role_tool_matrix=role_tool_matrix,
        strict_mode=strict_mode,
        audit_denials=audit_denials,
        constitutional_hash=constitutional_hash,
    )
    return MACIToolFilter(config)


__all__ = [
    "ROLE_TOOL_MATRIX",
    "MACIToolFilter",
    "MACIToolRole",
    "ToolFilterConfig",
    "ToolFilterResult",
    "create_maci_tool_filter",
]
