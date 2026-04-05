"""
MCP Tool Allowlist Policy for ACGS-2 Pipeline.

Provides a ToolAllowlistPolicy Pydantic model that maps MACI roles to sets of
permitted MCP tool names, a canonical MCP_TOOL_CATALOG frozenset of all known
tools, and a resolve_effective_allowlist() function implementing INTERSECTION
merge semantics for tenant-scoped overrides.

Binding decisions from run-20260308-003 consensus:
  C-1: Lives alongside tool_privilege.py in middlewares/
  C-2: Uses existing MACIRole enum (PIGR aliases documented only)
  C-3: Exact tool names (frozensets), no glob patterns
  C-4: Always fail-closed, no strict_mode toggle
  C-6: INTERSECTION merge — tenants can only RESTRICT, never EXPAND

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..maci_enforcement import MACIRole
from .tool_privilege import _CONSTITUTIONAL_MUTATION_TOOLS

# ---------------------------------------------------------------------------
# MCP Tool Catalog — canonical set of all registered MCP tool names.
#
# neural-mcp tools (11): src/neural-mcp/src/tools/registry.ts
# EAB MCP tools (5):     packages/enhanced_agent_bus/mcp_server/server.py
# ---------------------------------------------------------------------------

MCP_TOOL_CATALOG: frozenset[str] = frozenset(
    {
        # --- neural-mcp tools ---
        "neural_load_domains",
        "neural_train",
        "neural_status",
        "neural_patterns",
        "neural_dependencies",
        "neural_optimize",
        "hitl_request_approval",
        "hitl_check_status",
        "exa_governance_search",
        "exa_competitor_monitor",
        "exa_constitutional_papers",
        # --- EAB MCP tools ---
        "validate_constitutional_compliance",
        "get_active_principles",
        "query_governance_precedents",
        "submit_governance_request",
        "get_governance_metrics",
    }
)

# ---------------------------------------------------------------------------
# Default per-role MCP allowlists.
#
# Role mapping (task manifest PIGR aliases → MACIRole):
#   PROPOSER  → EXECUTIVE
#   IMPLEMENTER → IMPLEMENTER
#   GOVERNOR  → JUDICIAL
#   REVIEWER  → AUDITOR
#
# Principle: least-privilege. Each role gets only the MCP tools it needs.
# Constitutional mutation tools are globally denied via _CONSTITUTIONAL_MUTATION_TOOLS
# in tool_privilege.py and are never included here.
# ---------------------------------------------------------------------------

DEFAULT_MCP_ALLOWLISTS: dict[MACIRole, frozenset[str]] = {
    # EXECUTIVE (PROPOSER) — can query domains, patterns, and request HITL
    MACIRole.EXECUTIVE: frozenset(
        {
            "neural_load_domains",
            "neural_status",
            "neural_patterns",
            "neural_dependencies",
            "hitl_request_approval",
            "hitl_check_status",
            "get_active_principles",
            "query_governance_precedents",
            "get_governance_metrics",
        }
    ),
    # LEGISLATIVE — can query governance precedents and principles
    MACIRole.LEGISLATIVE: frozenset(
        {
            "neural_status",
            "neural_patterns",
            "neural_dependencies",
            "get_active_principles",
            "query_governance_precedents",
            "get_governance_metrics",
            "exa_governance_search",
            "exa_constitutional_papers",
        }
    ),
    # JUDICIAL (GOVERNOR) — can validate compliance and check HITL status
    MACIRole.JUDICIAL: frozenset(
        {
            "neural_status",
            "neural_patterns",
            "validate_constitutional_compliance",
            "get_active_principles",
            "query_governance_precedents",
            "hitl_check_status",
            "get_governance_metrics",
        }
    ),
    # MONITOR — read-only access to status and metrics
    MACIRole.MONITOR: frozenset(
        {
            "neural_status",
            "neural_patterns",
            "hitl_check_status",
            "get_governance_metrics",
        }
    ),
    # AUDITOR (REVIEWER) — can query precedents and metrics for audit
    MACIRole.AUDITOR: frozenset(
        {
            "neural_status",
            "neural_patterns",
            "neural_dependencies",
            "validate_constitutional_compliance",
            "get_active_principles",
            "query_governance_precedents",
            "get_governance_metrics",
            "exa_governance_search",
            "exa_constitutional_papers",
        }
    ),
    # CONTROLLER — can enforce controls and check governance state
    MACIRole.CONTROLLER: frozenset(
        {
            "neural_status",
            "neural_patterns",
            "validate_constitutional_compliance",
            "get_active_principles",
            "get_governance_metrics",
        }
    ),
    # IMPLEMENTER — can train models, load domains, and submit requests
    MACIRole.IMPLEMENTER: frozenset(
        {
            "neural_load_domains",
            "neural_train",
            "neural_status",
            "neural_patterns",
            "neural_dependencies",
            "neural_optimize",
            "submit_governance_request",
            "get_governance_metrics",
        }
    ),
}


# ---------------------------------------------------------------------------
# Policy model
# ---------------------------------------------------------------------------


class ToolAllowlistPolicy(BaseModel):
    """Per-role MCP tool allowlist policy.

    Maps each MACI role to a frozenset of permitted MCP tool names.
    Tools not in the allowlist are denied by default (fail-closed).
    Tenant overrides can only RESTRICT via INTERSECTION merge.

    Constitutional Hash: 608508a9bd224290
    """

    role_allowlists: dict[str, list[str]] = Field(
        default_factory=dict,
        description=(
            "Mapping of MACIRole value → list of permitted MCP tool names. "
            "Empty list means no MCP tools permitted for that role."
        ),
    )

    model_config = {"frozen": True}

    @classmethod
    def from_defaults(cls) -> ToolAllowlistPolicy:
        """Create a policy from the default per-role MCP allowlists."""
        return cls(
            role_allowlists={
                role.value: sorted(tools) for role, tools in DEFAULT_MCP_ALLOWLISTS.items()
            }
        )

    def get_allowlist(self, role: MACIRole) -> frozenset[str]:
        """Get the frozenset of permitted tools for a MACI role.

        Returns an empty frozenset for unknown roles (fail-closed).
        """
        tools = self.role_allowlists.get(role.value, [])
        return frozenset(tools)


# ---------------------------------------------------------------------------
# INTERSECTION merge for tenant overrides
# ---------------------------------------------------------------------------


def resolve_effective_allowlist(
    role: MACIRole,
    *,
    system_policy: ToolAllowlistPolicy | None = None,
    tenant_overrides: dict[str, list[str]] | None = None,
) -> frozenset[str]:
    """Resolve the effective MCP tool allowlist for a role.

    Implements INTERSECTION merge semantics (consensus decision C-6):
    - Start with system-wide default allowlist for the role
    - If tenant overrides exist for the role, INTERSECT with tenant set
    - Tenant overrides can only RESTRICT, never EXPAND beyond system defaults
    - Constitutional mutation tools are always excluded

    Args:
        role: The MACI role to resolve for.
        system_policy: System-wide policy. Defaults to DEFAULT_MCP_ALLOWLISTS.
        tenant_overrides: Optional tenant-scoped overrides mapping role value
            to list of tool names.

    Returns:
        Frozenset of permitted MCP tool names for the role.
    """
    if system_policy is not None:
        system_tools = system_policy.get_allowlist(role)
    else:
        system_tools = DEFAULT_MCP_ALLOWLISTS.get(role, frozenset())

    if tenant_overrides is None:
        effective = system_tools
    else:
        tenant_tools_list = tenant_overrides.get(role.value)
        if tenant_tools_list is None:
            # No tenant override for this role — use system defaults
            effective = system_tools
        else:
            # INTERSECTION: tenant can only narrow, not widen
            effective = system_tools & frozenset(tenant_tools_list)

    # Defence-in-depth: strip any constitutional mutation tools that may have
    # been injected via tenant overrides or misconfigured system policy.
    return effective - _CONSTITUTIONAL_MUTATION_TOOLS


__all__ = [
    "DEFAULT_MCP_ALLOWLISTS",
    "MCP_TOOL_CATALOG",
    "ToolAllowlistPolicy",
    "resolve_effective_allowlist",
]
