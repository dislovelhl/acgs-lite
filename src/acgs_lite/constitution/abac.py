"""exp226: Attribute-Based Access Control (ABAC) context enrichment.

Bridges the gap between free-form ``context`` dicts and structured policy
predicates.  ``EvaluationContext`` is a typed attribute bag that captures the
six standard ABAC dimensions for AI agent governance:

1. **Subject** — who is acting (agent_id, agent_tier, user_role)
2. **Resource** — what is being accessed (resource_type, data_classification)
3. **Environment** — where/when (deployment_region, tenant_id, time_of_day)
4. **Risk** — current risk posture (tenant_risk_profile)
5. **Custom** — extensible free-form attributes

Rules can already use ``condition`` dicts to check context keys
(exp129 — ``Rule.condition_matches()``).  ``EvaluationContext`` makes those
checks *type-safe and schema-validated* while providing:

- ``to_dict()`` — converts to the flat dict that ``condition_matches()`` consumes
- ``for_interpolation()`` — nested dict for ``${key.subkey}`` resolution (exp223)
- ``merge(other)`` — overlay contexts without mutation
- ``risk_level`` — derived composite risk tier from input attributes

Standard attribute values are intentionally *open* (strings, not enums) so
callers can pass domain-specific values without importing this module.
Common values are documented as class-level constants for discoverability.

Usage::

    from acgs_lite.constitution.abac import EvaluationContext

    ctx = EvaluationContext(
        agent_id="agent-alpha",
        agent_tier="restricted",
        data_classification="PHI",
        deployment_region="EU",
        user_role="clinician",
        tenant_id="hospital-001",
    )

    # Use with Constitution.explain_rendered():
    result = constitution.explain_rendered("access patient records", ctx.for_interpolation())

    # Use with condition_matches() directly:
    if rule.condition_matches(ctx.to_dict()):
        ...

    # Build from an existing dict:
    ctx2 = EvaluationContext.from_dict({"agent_tier": "privileged", "region": "US"})
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

# ── Well-known constant values (open, not enforced) ────────────────────────

# agent_tier
TIER_RESTRICTED = "restricted"
TIER_STANDARD = "standard"
TIER_PRIVILEGED = "privileged"
TIER_AUTONOMOUS = "autonomous"

# data_classification
CLASS_PUBLIC = "public"
CLASS_INTERNAL = "internal"
CLASS_CONFIDENTIAL = "confidential"
CLASS_PII = "PII"
CLASS_PHI = "PHI"
CLASS_SECRET = "secret"  # noqa: S105 — classification label, not a password
CLASS_TOP_SECRET = "top_secret"  # noqa: S105 — classification label, not a password

# deployment_region (ISO 3166 + regulatory zones)
REGION_EU = "EU"
REGION_US = "US"
REGION_UK = "UK"
REGION_APAC = "APAC"
REGION_GLOBAL = "GLOBAL"

# tenant_risk_profile
RISK_LOW = "low"
RISK_MEDIUM = "medium"
RISK_HIGH = "high"
RISK_CRITICAL = "critical"

# ── Risk tier mapping ───────────────────────────────────────────────────────

_TIER_RISK: dict[str, int] = {
    TIER_RESTRICTED: 3,
    TIER_AUTONOMOUS: 3,
    TIER_STANDARD: 1,
    TIER_PRIVILEGED: 2,
}
_CLASS_RISK: dict[str, int] = {
    CLASS_SECRET: 4,
    CLASS_TOP_SECRET: 4,
    CLASS_PHI: 3,
    CLASS_PII: 3,
    CLASS_CONFIDENTIAL: 2,
    CLASS_INTERNAL: 1,
    CLASS_PUBLIC: 0,
}
_PROFILE_RISK: dict[str, int] = {
    RISK_CRITICAL: 4,
    RISK_HIGH: 3,
    RISK_MEDIUM: 2,
    RISK_LOW: 1,
}


@dataclass
class EvaluationContext:
    """Structured ABAC attribute bag for governance evaluation.

    All fields are optional — unset fields are excluded from the generated
    context dict so rules that don't reference them are unaffected.

    Attributes:
        agent_id: Unique identifier of the acting agent.
        agent_tier: Trust tier (``"restricted"``, ``"standard"``,
            ``"privileged"``, ``"autonomous"``).
        user_role: Role of the human user on behalf of whom the agent acts
            (e.g., ``"clinician"``, ``"analyst"``, ``"admin"``).
        resource_type: Type of resource being accessed (e.g., ``"database"``,
            ``"api"``, ``"file"``).
        data_classification: Sensitivity level of data involved
            (``"public"``, ``"internal"``, ``"confidential"``, ``"PII"``,
            ``"PHI"``, ``"secret"``).
        deployment_region: Regulatory jurisdiction (``"EU"``, ``"US"``,
            ``"UK"``, ``"APAC"``, ``"GLOBAL"``).
        tenant_id: Multi-tenant identifier for the caller's organisation.
        tenant_risk_profile: Tenant-level risk posture (``"low"``,
            ``"medium"``, ``"high"``, ``"critical"``).
        time_of_day: ISO-8601 datetime string (auto-set to UTC now if
            ``use_current_time=True`` at construction).
        custom: Arbitrary additional attributes passed through as-is.
    """

    agent_id: str = ""
    agent_tier: str = ""
    user_role: str = ""
    resource_type: str = ""
    data_classification: str = ""
    deployment_region: str = ""
    tenant_id: str = ""
    tenant_risk_profile: str = ""
    time_of_day: str = ""
    custom: dict[str, Any] = field(default_factory=dict)

    # ── factories ───────────────────────────────────────────────────────────

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvaluationContext:
        """Build from a flat or nested dict.

        Recognises both flat keys (``"agent_tier"``) and the nested form
        used by ``for_interpolation()`` (``{"agent": {"tier": "privileged"}}``).
        Unknown keys are placed in ``custom``.

        Args:
            data: Dict of attributes.

        Returns:
            New :class:`EvaluationContext`.
        """
        known = {
            "agent_id",
            "agent_tier",
            "user_role",
            "resource_type",
            "data_classification",
            "deployment_region",
            "tenant_id",
            "tenant_risk_profile",
            "time_of_day",
        }
        kwargs: dict[str, Any] = {}
        custom: dict[str, Any] = {}

        # Unpack nested form: {"agent": {"id": ..., "tier": ...}}
        flat = dict(data)
        for section, subfields in (
            ("agent", ("id", "tier")),
            ("resource", ("type", "classification")),
            ("deployment", ("region",)),
            ("tenant", ("id", "risk_profile")),
        ):
            if isinstance(flat.get(section), dict):
                sub = flat.pop(section)
                for sf in subfields:
                    compound_key = (
                        f"{section}_{sf}" if section != "deployment" else f"deployment_{sf}"
                    )
                    if sf in sub and compound_key not in flat:
                        flat[compound_key] = sub[sf]

        for k, v in flat.items():
            if k in known:
                kwargs[k] = v
            else:
                custom[k] = v

        if custom:
            kwargs["custom"] = custom
        return cls(**kwargs)

    @classmethod
    def now(cls, **kwargs: Any) -> EvaluationContext:
        """Create context with ``time_of_day`` set to current UTC time.

        All other fields passed as keyword arguments.

        Example::

            ctx = EvaluationContext.now(agent_id="alpha", agent_tier="standard")
        """
        ts = datetime.now(timezone.utc).isoformat()
        return cls(time_of_day=ts, **kwargs)

    # ── conversion ──────────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Return flat dict for use with ``Rule.condition_matches()``.

        Only populated fields are included (empty strings and empty dicts
        are excluded to avoid spurious condition mismatches).

        Returns:
            Flat dict with only set attributes.
        """
        result: dict[str, Any] = {}
        for attr in (
            "agent_id",
            "agent_tier",
            "user_role",
            "resource_type",
            "data_classification",
            "deployment_region",
            "tenant_id",
            "tenant_risk_profile",
            "time_of_day",
        ):
            val = getattr(self, attr)
            if val:
                result[attr] = val
        result.update(self.custom)
        return result

    def for_interpolation(self) -> dict[str, Any]:
        """Return nested dict for ``${key.subkey}`` placeholder resolution.

        Produces a structured dict suitable for use with ``render_text()``
        and ``Constitution.explain_rendered()`` (exp223):

        .. code-block:: python

            {
                "agent": {"id": "alpha", "tier": "standard"},
                "resource": {"type": "database", "classification": "PII"},
                "deployment": {"region": "EU"},
                "tenant": {"id": "org-1", "risk_profile": "high"},
                "time_of_day": "2026-03-16T...",
                ...  # custom keys at top level
            }

        Returns:
            Nested dict for use with ``render_text()`` / ``explain_rendered()``.
        """
        result: dict[str, Any] = {}
        if self.agent_id or self.agent_tier:
            result["agent"] = {}
            if self.agent_id:
                result["agent"]["id"] = self.agent_id
            if self.agent_tier:
                result["agent"]["tier"] = self.agent_tier
        if self.user_role:
            result["user"] = {"role": self.user_role}
        if self.resource_type or self.data_classification:
            result["resource"] = {}
            if self.resource_type:
                result["resource"]["type"] = self.resource_type
            if self.data_classification:
                result["resource"]["classification"] = self.data_classification
        if self.deployment_region:
            result["deployment"] = {"region": self.deployment_region}
        if self.tenant_id or self.tenant_risk_profile:
            result["tenant"] = {}
            if self.tenant_id:
                result["tenant"]["id"] = self.tenant_id
            if self.tenant_risk_profile:
                result["tenant"]["risk_profile"] = self.tenant_risk_profile
        if self.time_of_day:
            result["time_of_day"] = self.time_of_day
        result.update(self.custom)
        return result

    # ── analysis ────────────────────────────────────────────────────────────

    @property
    def risk_level(self) -> int:
        """Composite risk score (0-4) derived from agent tier, data classification,
        and tenant risk profile.

        Higher values indicate higher inherent risk:

        - 0: Fully trusted, public data, low-risk tenant
        - 1-2: Standard operations
        - 3: Elevated (restricted agent, PII/PHI data, or high-risk tenant)
        - 4: Critical (secret data, critical tenant, or autonomous agent)

        Returns:
            Integer 0-4.
        """
        tier_score = _TIER_RISK.get(self.agent_tier.lower(), 0)
        class_score = _CLASS_RISK.get(self.data_classification, 0)
        profile_score = _PROFILE_RISK.get(self.tenant_risk_profile.lower(), 0)
        return min(4, max(tier_score, class_score, profile_score))

    @property
    def risk_label(self) -> str:
        """Human-readable risk level label."""
        return ("none", "low", "medium", "high", "critical")[self.risk_level]

    def merge(self, other: EvaluationContext) -> EvaluationContext:
        """Return a new context with *other*'s values overlaid on *self*.

        Fields set in *other* override fields in *self*; unset fields in
        *other* (empty string / empty dict) do not override *self*.

        Args:
            other: Context whose set fields take priority.

        Returns:
            New merged :class:`EvaluationContext`.

        Example::

            base = EvaluationContext(agent_tier="standard", deployment_region="EU")
            override = EvaluationContext(agent_tier="privileged")
            merged = base.merge(override)
            assert merged.agent_tier == "privileged"
            assert merged.deployment_region == "EU"
        """
        merged_custom = {**self.custom, **other.custom}
        return EvaluationContext(
            agent_id=other.agent_id or self.agent_id,
            agent_tier=other.agent_tier or self.agent_tier,
            user_role=other.user_role or self.user_role,
            resource_type=other.resource_type or self.resource_type,
            data_classification=other.data_classification or self.data_classification,
            deployment_region=other.deployment_region or self.deployment_region,
            tenant_id=other.tenant_id or self.tenant_id,
            tenant_risk_profile=other.tenant_risk_profile or self.tenant_risk_profile,
            time_of_day=other.time_of_day or self.time_of_day,
            custom=merged_custom,
        )

    def to_summary(self) -> dict[str, Any]:
        """Return a human-readable summary dict for logging/reporting."""
        return {
            "agent_id": self.agent_id or "(unset)",
            "agent_tier": self.agent_tier or "(unset)",
            "data_classification": self.data_classification or "(unset)",
            "deployment_region": self.deployment_region or "(unset)",
            "risk_level": f"{self.risk_level} ({self.risk_label})",
            "custom_keys": list(self.custom.keys()),
        }

    def __repr__(self) -> str:
        set_fields = {
            k: v
            for k, v in {
                "agent_id": self.agent_id,
                "agent_tier": self.agent_tier,
                "data_classification": self.data_classification,
                "deployment_region": self.deployment_region,
                "risk": self.risk_label,
            }.items()
            if v
        }
        return f"EvaluationContext({', '.join(f'{k}={v!r}' for k, v in set_fields.items())})"
