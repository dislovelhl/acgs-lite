"""MACI-role-based scope policy for Auth0 Token Vault connections.

Defines which OAuth scopes each MACI role is constitutionally allowed to request
from each external provider (GitHub, Google, Slack, etc.).

Constitutional Hash: 608508a9bd224290

Example YAML format::

    # constitution.yaml
    token_vault:
      constitutional_hash: "608508a9bd224290"
      connections:
        github:
          EXECUTIVE:
            permitted_scopes: ["read:user", "repo:read"]
            high_risk_scopes: []
          JUDICIAL:
            permitted_scopes: ["read:user"]
            high_risk_scopes: []
          IMPLEMENTER:
            permitted_scopes: ["read:user", "repo:read", "repo:write"]
            high_risk_scopes: ["repo:write"]
        google-oauth2:
          EXECUTIVE:
            permitted_scopes:
              - "openid"
              - "https://www.googleapis.com/auth/calendar.freebusy"
            high_risk_scopes: []
          IMPLEMENTER:
            permitted_scopes:
              - "openid"
              - "https://www.googleapis.com/auth/calendar"
            high_risk_scopes:
              - "https://www.googleapis.com/auth/calendar"
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

try:
    import yaml

    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


class ScopeRiskLevel(str, Enum):
    """Risk classification for OAuth scopes.

    LOW:    Read-only, no PII, no write. E.g. ``repo:read``, ``calendar.freebusy``.
    MEDIUM: PII access or limited write. E.g. ``read:user``, ``email``.
    HIGH:   Write access, deletion, or sensitive data. E.g. ``repo:write``, ``calendar``.
    CRITICAL: Destructive or irreversible operations. E.g. ``delete:*``, admin scopes.
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# Built-in heuristic classification for well-known OAuth scopes.
# Projects can extend this via MACIScopePolicy.register_scope_risk().
_BUILTIN_SCOPE_RISK: dict[str, ScopeRiskLevel] = {
    # GitHub
    "read:user": ScopeRiskLevel.MEDIUM,
    "user:email": ScopeRiskLevel.MEDIUM,
    "repo:read": ScopeRiskLevel.LOW,
    "repo": ScopeRiskLevel.HIGH,
    "repo:write": ScopeRiskLevel.HIGH,
    "delete_repo": ScopeRiskLevel.CRITICAL,
    "admin:org": ScopeRiskLevel.CRITICAL,
    # Google Calendar
    "https://www.googleapis.com/auth/calendar.freebusy": ScopeRiskLevel.LOW,
    "https://www.googleapis.com/auth/calendar.readonly": ScopeRiskLevel.LOW,
    "https://www.googleapis.com/auth/calendar.events.readonly": ScopeRiskLevel.LOW,
    "https://www.googleapis.com/auth/calendar": ScopeRiskLevel.HIGH,
    "https://www.googleapis.com/auth/calendar.events": ScopeRiskLevel.HIGH,
    # Google Drive
    "https://www.googleapis.com/auth/drive.readonly": ScopeRiskLevel.LOW,
    "https://www.googleapis.com/auth/drive": ScopeRiskLevel.HIGH,
    "https://www.googleapis.com/auth/drive.file": ScopeRiskLevel.MEDIUM,
    # Slack
    "channels:read": ScopeRiskLevel.LOW,
    "channels:write": ScopeRiskLevel.HIGH,
    "chat:write": ScopeRiskLevel.HIGH,
    "files:write": ScopeRiskLevel.HIGH,
    # Common OIDC
    "openid": ScopeRiskLevel.LOW,
    "profile": ScopeRiskLevel.MEDIUM,
    "email": ScopeRiskLevel.MEDIUM,
}


@dataclass
class ConnectionScopeRule:
    """Scope permissions for a single (connection, MACI role) pair.

    Attributes:
        connection: External provider name (e.g. ``"github"``, ``"google-oauth2"``).
        role: MACI role name (e.g. ``"EXECUTIVE"``, ``"IMPLEMENTER"``).
        permitted_scopes: Scopes this role may request for this connection.
        high_risk_scopes: Subset of permitted_scopes that require CIBA step-up.
    """

    connection: str
    role: str
    permitted_scopes: list[str] = field(default_factory=list)
    high_risk_scopes: list[str] = field(default_factory=list)

    def is_permitted(self, scope: str) -> bool:
        """Return True if *scope* is constitutionally permitted for this rule."""
        return scope in self.permitted_scopes

    def requires_step_up(self, scope: str) -> bool:
        """Return True if *scope* requires CIBA step-up before retrieval."""
        return scope in self.high_risk_scopes

    def denied_scopes(self, requested: list[str]) -> list[str]:
        """Return the subset of *requested* scopes that are not permitted."""
        return [s for s in requested if s not in self.permitted_scopes]

    def step_up_scopes(self, requested: list[str]) -> list[str]:
        """Return the subset of *requested* scopes that trigger CIBA step-up."""
        return [s for s in requested if s in self.high_risk_scopes]


class MACIScopePolicy:
    """Constitutional policy mapping MACI roles to permitted Token Vault scopes.

    Loaded from a YAML constitution file or constructed programmatically.

    The policy is immutable after construction to preserve the constitutional
    integrity; any amendment must go through the standard ACGS amendment flow
    and produce a new MACIScopePolicy instance.

    Usage::

        policy = MACIScopePolicy.from_yaml("constitution.yaml")
        rule = policy.get_rule(connection="github", role="EXECUTIVE")
        denied = rule.denied_scopes(["repo:read", "repo:write"])
        # → ["repo:write"]   (EXECUTIVE may not write)
    """

    def __init__(
        self,
        rules: list[ConnectionScopeRule],
        *,
        constitutional_hash: str = "608508a9bd224290",
        custom_scope_risk: dict[str, ScopeRiskLevel] | None = None,
    ) -> None:
        self._rules: dict[tuple[str, str], ConnectionScopeRule] = {
            (r.connection, r.role): r for r in rules
        }
        self.constitutional_hash = constitutional_hash
        self._scope_risk: dict[str, ScopeRiskLevel] = {
            **_BUILTIN_SCOPE_RISK,
            **(custom_scope_risk or {}),
        }

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------

    @classmethod
    def from_yaml(cls, path: str | Path) -> "MACIScopePolicy":
        """Load policy from a YAML constitution file.

        Args:
            path: Path to the YAML file containing a ``token_vault`` section.

        Returns:
            A new MACIScopePolicy populated from the YAML rules.

        Raises:
            ImportError: If PyYAML is not installed.
            KeyError: If the YAML file is missing required structure.
        """
        if not YAML_AVAILABLE:
            raise ImportError(
                "PyYAML is required to load policies from YAML. Install it with: pip install pyyaml"
            )
        with open(path) as fh:
            data: dict[str, Any] = yaml.safe_load(fh)

        tv = data.get("token_vault", data)
        constitutional_hash = tv.get("constitutional_hash", "608508a9bd224290")
        rules: list[ConnectionScopeRule] = []
        for connection, role_map in tv.get("connections", {}).items():
            for role, role_cfg in role_map.items():
                rules.append(
                    ConnectionScopeRule(
                        connection=connection,
                        role=role,
                        permitted_scopes=list(role_cfg.get("permitted_scopes", [])),
                        high_risk_scopes=list(role_cfg.get("high_risk_scopes", [])),
                    )
                )
        return cls(rules, constitutional_hash=constitutional_hash)

    @classmethod
    def permissive(cls) -> "MACIScopePolicy":
        """Return a policy that permits all scopes for all roles.

        Suitable only for development / testing.  Never use in production.
        """
        logger.warning(
            "MACIScopePolicy.permissive() loaded — ALL scopes permitted. "
            "This must not be used in production."
        )
        return cls(rules=[], constitutional_hash="PERMISSIVE_DEV_ONLY")

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def get_rule(self, *, connection: str, role: str) -> ConnectionScopeRule | None:
        """Return the rule for (connection, role), or None if not configured."""
        return self._rules.get((connection, role))

    def is_connection_permitted(self, *, connection: str, role: str) -> bool:
        """Return True if the role has any entry for the connection."""
        return (connection, role) in self._rules

    def validate(
        self,
        *,
        agent_id: str,
        role: str,
        connection: str,
        requested_scopes: list[str],
    ) -> "PolicyValidationResult":
        """Validate a token request against the constitutional policy.

        Args:
            agent_id: Agent making the request (for audit logging).
            role: MACI role of the agent.
            connection: External provider connection name.
            requested_scopes: OAuth scopes the agent wishes to obtain.

        Returns:
            A PolicyValidationResult capturing the outcome.
        """
        from acgs_auth0.exceptions import (
            ConstitutionalScopeViolation,
            MACIRoleNotPermittedError,
        )

        rule = self.get_rule(connection=connection, role=role)
        if rule is None:
            error = MACIRoleNotPermittedError(agent_id=agent_id, role=role, connection=connection)
            return PolicyValidationResult(
                permitted=False,
                agent_id=agent_id,
                role=role,
                connection=connection,
                requested_scopes=requested_scopes,
                permitted_scopes=[],
                denied_scopes=requested_scopes,
                step_up_required=[],
                error=error,
            )

        denied = rule.denied_scopes(requested_scopes)
        if denied:
            error = ConstitutionalScopeViolation(
                agent_id=agent_id,
                role=role,
                connection=connection,
                requested_scopes=requested_scopes,
                permitted_scopes=rule.permitted_scopes,
            )
            return PolicyValidationResult(
                permitted=False,
                agent_id=agent_id,
                role=role,
                connection=connection,
                requested_scopes=requested_scopes,
                permitted_scopes=rule.permitted_scopes,
                denied_scopes=denied,
                step_up_required=[],
                error=error,
            )

        step_up = rule.step_up_scopes(requested_scopes)
        return PolicyValidationResult(
            permitted=True,
            agent_id=agent_id,
            role=role,
            connection=connection,
            requested_scopes=requested_scopes,
            permitted_scopes=rule.permitted_scopes,
            denied_scopes=[],
            step_up_required=step_up,
            error=None,
        )

    def classify_risk(self, scope: str) -> ScopeRiskLevel:
        """Return the risk classification for a single scope.

        Falls back to MEDIUM for unknown scopes (conservative default).
        """
        return self._scope_risk.get(scope, ScopeRiskLevel.MEDIUM)

    def register_scope_risk(self, scope: str, level: ScopeRiskLevel) -> None:
        """Register a custom risk level for a scope.

        This mutates the policy's risk map.  For production use, prefer
        encoding risk in the YAML constitution instead.
        """
        self._scope_risk[scope] = level


@dataclass
class PolicyValidationResult:
    """Outcome of MACIScopePolicy.validate().

    Attributes:
        permitted: True if all requested scopes are constitutionally allowed.
        agent_id: Agent that made the request.
        role: MACI role of the agent.
        connection: External provider connection.
        requested_scopes: Scopes requested by the agent.
        permitted_scopes: Scopes allowed by the constitutional rule.
        denied_scopes: Requested scopes that were denied.
        step_up_required: Permitted scopes that additionally require CIBA step-up.
        error: Exception instance if ``permitted`` is False, otherwise None.
    """

    permitted: bool
    agent_id: str
    role: str
    connection: str
    requested_scopes: list[str]
    permitted_scopes: list[str]
    denied_scopes: list[str]
    step_up_required: list[str]
    error: Exception | None
