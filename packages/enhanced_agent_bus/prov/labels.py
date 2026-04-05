"""
W3C PROV provenance label system for ACGS-2 Enhanced Agent Bus.

Implements PROV-AGENT-style annotations on governance decision points,
recording the entity generated, the activity that generated it, and
the enhanced-agent-bus service agent responsible.

Mirrors src/neural-mcp/src/prov/labels.ts for the Python pipeline.
Reference: W3C PROV-DM https://www.w3.org/TR/prov-dm/
Constitutional Hash: 608508a9bd224290
NIST 800-53 AU-2, AU-9 — Audit Events, Protection of Audit Information
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

# ---------------------------------------------------------------------------
# Module-level constants (mirror TypeScript counterparts)
# ---------------------------------------------------------------------------

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH: str = CONSTITUTIONAL_HASH  # pragma: allowlist secret
"""ACGS-2 constitutional hash for governance compliance."""

PROV_SCHEMA_VERSION: str = "1.0.0"
"""PROV schema version for forward compatibility."""

SERVICE_AGENT_ID: str = "acgs:agent/enhanced-agent-bus"
"""Stable URI for the enhanced-agent-bus service agent."""

SERVICE_AGENT_LABEL: str = "ACGS-2 Enhanced Agent Bus"
"""Human-readable label for the service agent."""

# Maps pipeline stage name → W3C PROV entity type for its output.
ENTITY_TYPE_MAP: dict[str, str] = {
    "security_scan": "acgs:SecurityScanResult",
    "constitutional_validation": "acgs:ConstitutionalValidationResult",
    "maci_enforcement": "acgs:MACIValidationResult",
    "impact_scoring": "acgs:ImpactScore",
    "hitl_review": "acgs:HITLDecision",
    "temporal_policy": "acgs:TemporalPolicyDecision",
    "tool_privilege": "acgs:ToolPrivilegeDecision",
    "strategy": "acgs:GovernanceDecision",
    "ifc_check": "acgs:IFCFlowDecision",
}

# Maps pipeline stage name → W3C PROV activity type for the invocation.
ACTIVITY_TYPE_MAP: dict[str, str] = {
    "security_scan": "acgs:SecurityScanning",
    "constitutional_validation": "acgs:ConstitutionalValidation",
    "maci_enforcement": "acgs:MACIEnforcement",
    "impact_scoring": "acgs:ImpactScoring",
    "hitl_review": "acgs:HITLReview",
    "temporal_policy": "acgs:TemporalPolicyEvaluation",
    "tool_privilege": "acgs:ToolPrivilegeEvaluation",
    "strategy": "acgs:GovernanceStrategyExecution",
    "ifc_check": "acgs:IFCFlowCheck",
}


# ---------------------------------------------------------------------------
# W3C PROV data model — frozen dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProvAgent:
    """A W3C PROV Agent — something bearing responsibility for an activity.

    Attributes:
        id: Stable URI identifier for this agent.
        type: W3C PROV agent type string.
        label: Human-readable label.
    """

    id: str
    type: str
    label: str

    def to_dict(self) -> dict[str, str]:
        """Serialize to a plain dict for storage/transport."""
        return {"id": self.id, "type": self.type, "label": self.label}

    @classmethod
    def from_dict(cls, data: dict) -> ProvAgent:
        """Deserialize from a plain dict produced by :meth:`to_dict`."""
        return cls(id=data["id"], type=data["type"], label=data["label"])


@dataclass(frozen=True)
class ProvActivity:
    """A W3C PROV Activity — something that occurs over time acting upon entities.

    Attributes:
        id: Globally unique identifier for this activity instance.
        type: W3C PROV activity type (e.g. ``"acgs:SecurityScanning"``).
        label: Human-readable label.
        started_at_time: ISO 8601 timezone.utc timestamp when the activity started.
        ended_at_time: ISO 8601 timezone.utc timestamp when the activity ended.
        was_associated_with: ID of the agent associated with this activity.
    """

    id: str
    type: str
    label: str
    started_at_time: str
    ended_at_time: str
    was_associated_with: str

    def to_dict(self) -> dict[str, str]:
        """Serialize to a plain dict for storage/transport."""
        return {
            "id": self.id,
            "type": self.type,
            "label": self.label,
            "started_at_time": self.started_at_time,
            "ended_at_time": self.ended_at_time,
            "was_associated_with": self.was_associated_with,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ProvActivity:
        """Deserialize from a plain dict produced by :meth:`to_dict`."""
        return cls(
            id=data["id"],
            type=data["type"],
            label=data["label"],
            started_at_time=data["started_at_time"],
            ended_at_time=data["ended_at_time"],
            was_associated_with=data["was_associated_with"],
        )


@dataclass(frozen=True)
class ProvEntity:
    """A W3C PROV Entity — a thing with identity that has provenance.

    Attributes:
        id: Globally unique identifier for this entity instance.
        type: W3C PROV entity type (e.g. ``"acgs:SecurityScanResult"``).
        label: Human-readable label.
        generated_at_time: ISO 8601 timezone.utc timestamp when this entity was generated.
        was_generated_by: ID of the activity that generated this entity.
        was_attributed_to: ID of the agent attributed this entity.
    """

    id: str
    type: str
    label: str
    generated_at_time: str
    was_generated_by: str
    was_attributed_to: str

    def to_dict(self) -> dict[str, str]:
        """Serialize to a plain dict for storage/transport."""
        return {
            "id": self.id,
            "type": self.type,
            "label": self.label,
            "generated_at_time": self.generated_at_time,
            "was_generated_by": self.was_generated_by,
            "was_attributed_to": self.was_attributed_to,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ProvEntity:
        """Deserialize from a plain dict produced by :meth:`to_dict`."""
        return cls(
            id=data["id"],
            type=data["type"],
            label=data["label"],
            generated_at_time=data["generated_at_time"],
            was_generated_by=data["was_generated_by"],
            was_attributed_to=data["was_attributed_to"],
        )


@dataclass(frozen=True)
class ProvLabel:
    """Complete W3C PROV label for a single governance decision point.

    Immutable: frozen=True mirrors the IFCLabel pattern and ensures the
    audit trail cannot be mutated after the fact.

    Attributes:
        entity: The governance artefact (decision output) being annotated.
        activity: The pipeline stage (invocation) that generated the entity.
        agent: The service agent (enhanced-agent-bus) responsible.
        constitutional_hash: ACGS-2 governance compliance anchor.
        schema_version: Forward-compatibility version string.
    """

    entity: ProvEntity
    activity: ProvActivity
    agent: ProvAgent
    constitutional_hash: str = CONSTITUTIONAL_HASH  # pragma: allowlist secret
    schema_version: str = PROV_SCHEMA_VERSION

    def to_dict(self) -> dict:
        """Serialize to a plain dict for storage/transport."""
        return {
            "entity": self.entity.to_dict(),
            "activity": self.activity.to_dict(),
            "agent": self.agent.to_dict(),
            "constitutional_hash": self.constitutional_hash,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ProvLabel:
        """Deserialize from a plain dict produced by :meth:`to_dict`."""
        return cls(
            entity=ProvEntity.from_dict(data["entity"]),
            activity=ProvActivity.from_dict(data["activity"]),
            agent=ProvAgent.from_dict(data["agent"]),
            constitutional_hash=data.get("constitutional_hash", CONSTITUTIONAL_HASH),
            schema_version=data.get("schema_version", PROV_SCHEMA_VERSION),
        )

    def __repr__(self) -> str:
        return (
            f"ProvLabel(stage={self.activity.label!r}, "
            f"entity={self.entity.id!r}, "
            f"at={self.entity.generated_at_time!r})"
        )


# ---------------------------------------------------------------------------
# ProvLineage — ordered list of ProvLabels for a single message
# ---------------------------------------------------------------------------


@dataclass
class ProvLineage:
    """Ordered provenance chain for a single message through the pipeline.

    Not frozen — the pipeline appends entries as stages complete.

    Attributes:
        labels: Chronologically ordered list of ProvLabel stamps.
    """

    labels: list[ProvLabel] = field(default_factory=list)

    def append(self, label: ProvLabel) -> None:
        """Append a new provenance stamp to the lineage chain."""
        self.labels.append(label)

    def to_dict(self) -> list[dict]:
        """Serialize the full lineage chain."""
        return [lbl.to_dict() for lbl in self.labels]

    @classmethod
    def from_dict(cls, data: list[dict]) -> ProvLineage:
        """Deserialize from a list of dicts produced by :meth:`to_dict`."""
        return cls(labels=[ProvLabel.from_dict(d) for d in data])

    def __len__(self) -> int:
        return len(self.labels)

    def __iter__(self):
        return iter(self.labels)


# ---------------------------------------------------------------------------
# Factory functions (mirror TypeScript counterparts)
# ---------------------------------------------------------------------------


def _utc_now_iso() -> str:
    """Return the current timezone.utc time as an ISO 8601 string."""
    return datetime.now(tz=UTC).isoformat()


def make_prov_id(stage_name: str, suffix: str, issued_at: str) -> str:
    """Generate a URI-safe provenance ID.

    Colons and dots in the ISO 8601 timestamp are replaced with hyphens
    to produce a valid URI path component.

    Args:
        stage_name: Pipeline stage name (e.g. ``"security_scan"``).
        suffix: ``"entity"`` or ``"activity"``.
        issued_at: ISO 8601 timezone.utc timestamp string.

    Returns:
        URI-safe string of the form ``"acgs:{stage}/{suffix}/{safe_ts}"``.
    """
    safe_ts = issued_at.replace(":", "-").replace(".", "-")
    return f"acgs:{stage_name}/{suffix}/{safe_ts}"


def make_service_agent() -> ProvAgent:
    """Return the singleton W3C PROV agent for the enhanced-agent-bus service."""
    return ProvAgent(
        id=SERVICE_AGENT_ID,
        type="prov:SoftwareAgent",
        label=SERVICE_AGENT_LABEL,
    )


def make_tool_activity(
    stage_name: str,
    started_at: str,
    ended_at: str,
) -> ProvActivity:
    """Build a ProvActivity for a pipeline stage invocation.

    Args:
        stage_name: Pipeline stage name (e.g. ``"constitutional_validation"``).
        started_at: ISO 8601 timezone.utc timestamp when the stage began.
        ended_at: ISO 8601 timezone.utc timestamp when the stage finished.

    Returns:
        An immutable :class:`ProvActivity` instance.
    """
    activity_type = ACTIVITY_TYPE_MAP.get(stage_name, f"acgs:{stage_name}")
    activity_id = make_prov_id(stage_name, "activity", started_at)
    return ProvActivity(
        id=activity_id,
        type=activity_type,
        label=f"Execute {stage_name}",
        started_at_time=started_at,
        ended_at_time=ended_at,
        was_associated_with=SERVICE_AGENT_ID,
    )


def make_tool_entity(
    stage_name: str,
    activity_id: str,
    generated_at: str,
) -> ProvEntity:
    """Build a ProvEntity for a pipeline stage's governance output.

    Args:
        stage_name: Pipeline stage name (e.g. ``"impact_scoring"``).
        activity_id: The ID of the generating activity.
        generated_at: ISO 8601 timezone.utc timestamp when the entity was produced.

    Returns:
        An immutable :class:`ProvEntity` instance.
    """
    entity_type = ENTITY_TYPE_MAP.get(stage_name, f"acgs:{stage_name}Result")
    entity_id = make_prov_id(stage_name, "entity", generated_at)
    return ProvEntity(
        id=entity_id,
        type=entity_type,
        label=f"Output of {stage_name}",
        generated_at_time=generated_at,
        was_generated_by=activity_id,
        was_attributed_to=SERVICE_AGENT_ID,
    )


def build_prov_label(
    stage_name: str,
    started_at: str,
    ended_at: str | None = None,
) -> ProvLabel:
    """Assemble a complete ProvLabel for a single governance decision point.

    This is the primary public factory; callers pass the stage name and
    timestamps and receive a fully-formed, immutable provenance label.

    Args:
        stage_name: Pipeline stage name (e.g. ``"strategy"``).
        started_at: ISO 8601 timezone.utc timestamp when the stage began.
        ended_at: ISO 8601 timezone.utc timestamp when the stage finished.
            Defaults to the current timezone.utc time if not supplied.

    Returns:
        An immutable :class:`ProvLabel` anchored to the constitutional hash.
    """
    resolved_ended_at = ended_at if ended_at is not None else _utc_now_iso()
    agent = make_service_agent()
    activity = make_tool_activity(stage_name, started_at, resolved_ended_at)
    entity = make_tool_entity(stage_name, activity.id, resolved_ended_at)
    return ProvLabel(
        entity=entity,
        activity=activity,
        agent=agent,
        constitutional_hash=CONSTITUTIONAL_HASH,  # pragma: allowlist secret
        schema_version=PROV_SCHEMA_VERSION,
    )
