"""Canonical MACI role projections for subsystem-specific role models."""

from __future__ import annotations

from typing import Literal

from enhanced_agent_bus._compat.constants import MACIRole

ToolProjectionRole = Literal["proposer", "validator", "executor"]
VerificationProjectionRole = Literal["executive", "legislative", "judicial", "monitor", "auditor"]

MCP_TOOL_ROLE_PROJECTIONS: dict[MACIRole, ToolProjectionRole] = {
    MACIRole.EXECUTIVE: "proposer",
    MACIRole.LEGISLATIVE: "proposer",
    MACIRole.MONITOR: "proposer",
    MACIRole.JUDICIAL: "validator",
    MACIRole.AUDITOR: "validator",
    MACIRole.CONTROLLER: "executor",
    MACIRole.IMPLEMENTER: "executor",
}

VERIFICATION_ROLE_PROJECTIONS: dict[MACIRole, VerificationProjectionRole] = {
    MACIRole.EXECUTIVE: "executive",
    MACIRole.LEGISLATIVE: "legislative",
    MACIRole.JUDICIAL: "judicial",
    MACIRole.MONITOR: "monitor",
    MACIRole.AUDITOR: "auditor",
}


def parse_canonical_maci_role(role: object) -> MACIRole | None:
    """Return the canonical ``MACIRole`` for a role-like input."""
    if isinstance(role, MACIRole):
        return role
    if isinstance(role, str):
        normalized = role.strip()
        if not normalized:
            return None
        try:
            return MACIRole.parse(normalized)
        except ValueError:
            return None
    return None


def project_to_mcp_tool_role(role: object) -> ToolProjectionRole | None:
    """Project a canonical MACI role into the MCP tool-filter role model."""
    canonical_role = parse_canonical_maci_role(role)
    if canonical_role is None:
        return None
    return MCP_TOOL_ROLE_PROJECTIONS.get(canonical_role)


def project_to_verification_role(role: object) -> VerificationProjectionRole | None:
    """Project a canonical MACI role into the verifier role model."""
    canonical_role = parse_canonical_maci_role(role)
    if canonical_role is None:
        return None
    return VERIFICATION_ROLE_PROJECTIONS.get(canonical_role)


__all__ = [
    "MCP_TOOL_ROLE_PROJECTIONS",
    "VERIFICATION_ROLE_PROJECTIONS",
    "parse_canonical_maci_role",
    "project_to_mcp_tool_role",
    "project_to_verification_role",
]
