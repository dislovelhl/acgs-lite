"""
ACGS-2 W3C PROV provenance label system — Python implementation.

Mirrors src/neural-mcp/src/prov/labels.ts for the Python pipeline.
Records the entity generated, the activity that generated it, and
the agent responsible — for every governance decision point.

Reference: W3C PROV-DM https://www.w3.org/TR/prov-dm/
Constitutional Hash: 608508a9bd224290
"""

from .labels import (
    CONSTITUTIONAL_HASH,
    PROV_SCHEMA_VERSION,
    SERVICE_AGENT_ID,
    SERVICE_AGENT_LABEL,
    ProvActivity,
    ProvAgent,
    ProvEntity,
    ProvLabel,
    ProvLineage,
    build_prov_label,
    make_prov_id,
    make_service_agent,
    make_tool_activity,
    make_tool_entity,
)

__all__ = [
    "CONSTITUTIONAL_HASH",
    "PROV_SCHEMA_VERSION",
    "SERVICE_AGENT_ID",
    "SERVICE_AGENT_LABEL",
    "ProvActivity",
    "ProvAgent",
    "ProvEntity",
    "ProvLabel",
    "ProvLineage",
    "build_prov_label",
    "make_prov_id",
    "make_service_agent",
    "make_tool_activity",
    "make_tool_entity",
]
