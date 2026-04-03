# ACGS - Constitutional AI Governance
# Copyright (C) 2024-2026 ACGS Contributors
# Licensed under AGPL-3.0-or-later. See LICENSE for details.
# Commercial license: https://acgs.ai

"""Domain-scoped and delegated MACI registries.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from typing import Any

from .roles import _ROLE_DENIALS, _ROLE_PERMISSIONS, MACIRole, _is_action_permitted


class DomainScopedRole:
    """Domain-scoped MACI role assignment with cross-domain isolation."""

    __slots__ = ("agent_id", "role", "domains")

    def __init__(self, agent_id: str, role: MACIRole, domains: list[str]) -> None:
        self.agent_id = agent_id
        self.role = role
        self.domains = list(domains)

    def can_act_in(self, domain: str) -> bool:
        """Return True if this scoped role covers *domain*."""
        if not self.domains:
            return True
        return domain.lower() in (d.lower() for d in self.domains)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "role": self.role.value,
            "domains": self.domains,
        }

    def __repr__(self) -> str:
        return (
            f"DomainScopedRole(agent={self.agent_id!r}, "
            f"role={self.role.value!r}, domains={self.domains!r})"
        )


class DomainRoleRegistry:
    """Registry of domain-scoped MACI role assignments."""

    __slots__ = ("_assignments",)

    def __init__(self) -> None:
        self._assignments: dict[str, DomainScopedRole] = {}

    def assign(self, agent_id: str, role: MACIRole, *, domains: list[str]) -> None:
        """Assign a domain-scoped role to an agent."""
        self._assignments[agent_id] = DomainScopedRole(agent_id, role, domains)

    def get(self, agent_id: str) -> DomainScopedRole | None:
        """Return the scoped role for *agent_id*, or None if unregistered."""
        return self._assignments.get(agent_id)

    def check(self, agent_id: str, action: str, *, domain: str = "") -> dict[str, Any]:
        """Check whether *agent_id* may perform *action* in *domain*."""
        scoped = self._assignments.get(agent_id)
        base: dict[str, Any] = {
            "agent_id": agent_id,
            "action": action,
            "domain": domain,
            "role": scoped.role.value if scoped else None,
        }

        if scoped is None:
            return {**base, "allowed": False, "reason": f"agent {agent_id!r} not registered"}

        if domain and not scoped.can_act_in(domain):
            return {
                **base,
                "allowed": False,
                "reason": (
                    f"cross-domain violation: agent {agent_id!r} ({scoped.role.value}) "
                    f"is scoped to {scoped.domains} but tried to act in {domain!r}"
                ),
            }

        allowed = _ROLE_PERMISSIONS.get(scoped.role, set())
        denied = _ROLE_DENIALS.get(scoped.role, set())
        if not _is_action_permitted(action, allowed=allowed, denied=denied):
            return {
                **base,
                "allowed": False,
                "reason": (
                    f"role violation: {scoped.role.value!r} may only perform "
                    f"{sorted(allowed)!r}"
                ),
            }

        return {**base, "allowed": True, "reason": "role and domain check passed"}

    def isolation_report(self) -> dict[str, Any]:
        """Return a summary of domain isolation across all registered agents."""
        roles: dict[str, int] = {}
        domains: set[str] = set()
        cross_domain_risk: list[str] = []

        for scoped in self._assignments.values():
            roles[scoped.role.value] = roles.get(scoped.role.value, 0) + 1
            for d in scoped.domains:
                domains.add(d)
            if not scoped.domains:
                cross_domain_risk.append(scoped.agent_id)

        return {
            "total_agents": len(self._assignments),
            "domains": sorted(domains),
            "role_distribution": roles,
            "agents": [s.to_dict() for s in self._assignments.values()],
            "cross_domain_risk": cross_domain_risk,
        }

    def __len__(self) -> int:
        return len(self._assignments)

    def __repr__(self) -> str:
        return f"DomainRoleRegistry({len(self._assignments)} agents)"


class DerivedRole:
    """Virtual MACI role composing permissions from multiple base roles."""

    __slots__ = ("name", "base_roles", "deny_override", "_permissions", "_denials")

    def __init__(
        self,
        name: str,
        base_roles: list[MACIRole],
        *,
        deny_override: set[str] | None = None,
        allow_override: set[str] | None = None,
    ) -> None:
        self.name = name
        self.base_roles = list(base_roles)
        self.deny_override: set[str] = deny_override or set()

        composed_perms: set[str] = set()
        for role in base_roles:
            composed_perms |= _ROLE_PERMISSIONS.get(role, set())

        if base_roles:
            shared_denials: set[str] = _ROLE_DENIALS.get(base_roles[0], set()).copy()
            for role in base_roles[1:]:
                shared_denials &= _ROLE_DENIALS.get(role, set())
        else:
            shared_denials = set()

        composed_denials: set[str] = set(self.deny_override) | shared_denials

        if allow_override:
            composed_denials -= allow_override
            composed_perms |= allow_override

        self._permissions: frozenset[str] = frozenset(composed_perms - composed_denials)
        self._denials: frozenset[str] = frozenset(composed_denials)

    @property
    def permissions(self) -> frozenset[str]:
        return self._permissions

    @property
    def denials(self) -> frozenset[str]:
        return self._denials

    def can_perform(self, action: str) -> bool:
        """Return True if this derived role may perform *action*."""
        action_lower = action.lower().strip()
        return action_lower not in self._denials and action_lower in self._permissions

    def check(self, action: str) -> dict[str, Any]:
        """Check *action* and return a structured verdict with source attribution."""
        action_lower = action.lower().strip()
        if action_lower in self._denials:
            source = "denied:override" if action_lower in self.deny_override else "denied:base"
            return {
                "action": action,
                "allowed": False,
                "derived_role": self.name,
                "base_roles": [r.value for r in self.base_roles],
                "source": source,
            }
        for role in self.base_roles:
            if action_lower in _ROLE_PERMISSIONS.get(role, set()):
                return {
                    "action": action,
                    "allowed": True,
                    "derived_role": self.name,
                    "base_roles": [r.value for r in self.base_roles],
                    "source": f"inherited:{role.value}",
                }
        return {
            "action": action,
            "allowed": False,
            "derived_role": self.name,
            "base_roles": [r.value for r in self.base_roles],
            "source": "not_found",
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "base_roles": [r.value for r in self.base_roles],
            "permissions": sorted(self._permissions),
            "denials": sorted(self._denials),
        }

    def __repr__(self) -> str:
        return f"DerivedRole(name={self.name!r}, bases={[r.value for r in self.base_roles]!r})"


class DelegationGrant:
    """Revocable authority delegation for governance domains."""

    __slots__ = (
        "grant_id",
        "grantor_id",
        "grantee_id",
        "scopes",
        "max_depth",
        "depth",
        "parent_grant_id",
        "created_at",
        "expires_at",
        "revoked",
        "revoked_at",
        "revocation_reason",
        "metadata",
    )

    def __init__(
        self,
        *,
        grant_id: str,
        grantor_id: str,
        grantee_id: str,
        scopes: list[str],
        max_depth: int = 0,
        depth: int = 0,
        parent_grant_id: str = "",
        created_at: str = "",
        expires_at: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.grant_id = grant_id
        self.grantor_id = grantor_id
        self.grantee_id = grantee_id
        self.scopes = list(scopes)
        self.max_depth = max_depth
        self.depth = depth
        self.parent_grant_id = parent_grant_id
        self.created_at = created_at
        self.expires_at = expires_at
        self.revoked = False
        self.revoked_at = ""
        self.revocation_reason = ""
        self.metadata = metadata or {}

    def is_expired(self, at: str | None = None) -> bool:
        if not self.expires_at:
            return False
        from datetime import datetime, timezone

        ts = at or datetime.now(timezone.utc).isoformat()
        return ts >= self.expires_at

    def is_active(self, at: str | None = None) -> bool:
        return not self.revoked and not self.is_expired(at)

    def covers_scope(self, scope: str) -> bool:
        scope_lower = scope.lower()
        for s in self.scopes:
            s_lower = s.lower()
            if s_lower == "*" or s_lower == scope_lower:
                return True
            if s_lower.endswith("*") and scope_lower.startswith(s_lower[:-1]):
                return True
        return False

    def can_redelegate(self) -> bool:
        return self.depth < self.max_depth

    def to_dict(self) -> dict[str, Any]:
        return {
            "grant_id": self.grant_id,
            "grantor_id": self.grantor_id,
            "grantee_id": self.grantee_id,
            "scopes": self.scopes,
            "max_depth": self.max_depth,
            "depth": self.depth,
            "parent_grant_id": self.parent_grant_id,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "revoked": self.revoked,
            "revoked_at": self.revoked_at,
            "revocation_reason": self.revocation_reason,
            "is_active": self.is_active(),
            "can_redelegate": self.can_redelegate(),
            "metadata": self.metadata,
        }

    def __repr__(self) -> str:
        status = "revoked" if self.revoked else ("active" if self.is_active() else "expired")
        return (
            f"DelegationGrant({self.grant_id!r}, "
            f"{self.grantor_id!r}→{self.grantee_id!r}, "
            f"scopes={self.scopes!r}, {status})"
        )


class DelegationRegistry:
    """Registry for managing governance authority delegations."""

    __slots__ = ("_grants", "_counter", "_history")

    def __init__(self) -> None:
        self._grants: dict[str, DelegationGrant] = {}
        self._counter: int = 0
        self._history: list[dict[str, Any]] = []

    def _next_id(self) -> str:
        self._counter += 1
        return f"DLG-{self._counter:05d}"

    @staticmethod
    def _now() -> str:
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).isoformat()

    def delegate(
        self,
        *,
        grantor_id: str,
        grantee_id: str,
        scopes: list[str],
        max_depth: int = 0,
        expires_at: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> DelegationGrant:
        """Create a new delegation grant."""
        if grantor_id == grantee_id:
            raise ValueError("Cannot delegate authority to self")
        if not scopes:
            raise ValueError("Delegation must specify at least one scope")

        grant = DelegationGrant(
            grant_id=self._next_id(),
            grantor_id=grantor_id,
            grantee_id=grantee_id,
            scopes=scopes,
            max_depth=max_depth,
            depth=0,
            created_at=self._now(),
            expires_at=expires_at,
            metadata=metadata,
        )
        self._grants[grant.grant_id] = grant
        self._history.append(
            {
                "action": "delegate",
                "grant_id": grant.grant_id,
                "grantor_id": grantor_id,
                "grantee_id": grantee_id,
                "scopes": scopes,
                "timestamp": grant.created_at,
            }
        )
        return grant

    def redelegate(
        self,
        *,
        parent_grant_id: str,
        grantee_id: str,
        scopes: list[str] | None = None,
        expires_at: str = "",
    ) -> DelegationGrant:
        """Sub-delegate authority from an existing grant."""
        parent = self._get(parent_grant_id)
        if not parent.is_active():
            raise ValueError(f"Parent grant {parent_grant_id!r} is not active")
        if not parent.can_redelegate():
            raise ValueError(
                f"Grant {parent_grant_id!r} cannot re-delegate "
                f"(depth={parent.depth}, max_depth={parent.max_depth})"
            )
        if parent.grantee_id == grantee_id:
            raise ValueError("Cannot re-delegate to the same grantee")

        effective_scopes = scopes if scopes is not None else list(parent.scopes)
        for s in effective_scopes:
            if not parent.covers_scope(s.rstrip("*")):
                raise ValueError(
                    f"Scope {s!r} is not covered by parent grant "
                    f"{parent_grant_id!r} (scopes={parent.scopes!r})"
                )

        effective_expiry = expires_at
        if parent.expires_at and (not effective_expiry or effective_expiry > parent.expires_at):
            effective_expiry = parent.expires_at

        grant = DelegationGrant(
            grant_id=self._next_id(),
            grantor_id=parent.grantee_id,
            grantee_id=grantee_id,
            scopes=effective_scopes,
            max_depth=parent.max_depth,
            depth=parent.depth + 1,
            parent_grant_id=parent_grant_id,
            created_at=self._now(),
            expires_at=effective_expiry,
        )
        self._grants[grant.grant_id] = grant
        self._history.append(
            {
                "action": "redelegate",
                "grant_id": grant.grant_id,
                "parent_grant_id": parent_grant_id,
                "grantor_id": parent.grantee_id,
                "grantee_id": grantee_id,
                "scopes": effective_scopes,
                "depth": grant.depth,
                "timestamp": grant.created_at,
            }
        )
        return grant

    def revoke(self, grant_id: str, *, reason: str = "", cascade: bool = True) -> int:
        """Revoke a delegation grant."""
        grant = self._get(grant_id)
        if grant.revoked:
            return 0

        now = self._now()
        grant.revoked = True
        grant.revoked_at = now
        grant.revocation_reason = reason
        revoked_count = 1

        self._history.append(
            {
                "action": "revoke",
                "grant_id": grant_id,
                "reason": reason,
                "timestamp": now,
            }
        )

        if cascade:
            for child in self._grants.values():
                if child.parent_grant_id == grant_id and not child.revoked:
                    revoked_count += self.revoke(
                        child.grant_id,
                        reason=f"Cascade: parent {grant_id} revoked",
                        cascade=True,
                    )

        return revoked_count

    def check_authority(
        self,
        agent_id: str,
        *,
        scope: str,
        at: str | None = None,
    ) -> dict[str, Any]:
        """Check if an agent has delegated authority over a scope."""
        for grant in self._grants.values():
            if grant.grantee_id == agent_id and grant.is_active(at) and grant.covers_scope(scope):
                chain = self._build_chain(grant.grant_id)
                return {
                    "authorized": True,
                    "grant_id": grant.grant_id,
                    "grantor_id": grant.grantor_id,
                    "scope": scope,
                    "depth": grant.depth,
                    "delegation_chain": chain,
                }
        return {
            "authorized": False,
            "grant_id": "",
            "grantor_id": "",
            "scope": scope,
            "depth": -1,
            "delegation_chain": [],
        }

    def grants_for(self, agent_id: str) -> list[DelegationGrant]:
        return [g for g in self._grants.values() if g.grantee_id == agent_id and g.is_active()]

    def grants_by(self, agent_id: str) -> list[DelegationGrant]:
        return [g for g in self._grants.values() if g.grantor_id == agent_id and g.is_active()]

    def delegation_tree(self) -> dict[str, Any]:
        """Return the full delegation hierarchy as a tree."""
        children_map: dict[str, list[str]] = {}
        for g in self._grants.values():
            if g.parent_grant_id:
                children_map.setdefault(g.parent_grant_id, []).append(g.grant_id)

        def _build_node(gid: str) -> dict[str, Any]:
            g = self._grants[gid]
            node: dict[str, Any] = {
                "grant_id": gid,
                "grantor_id": g.grantor_id,
                "grantee_id": g.grantee_id,
                "scopes": g.scopes,
                "depth": g.depth,
                "active": g.is_active(),
            }
            kids = children_map.get(gid, [])
            if kids:
                node["children"] = [_build_node(c) for c in kids]
            return node

        roots = [g.grant_id for g in self._grants.values() if not g.parent_grant_id]

        active_count = sum(1 for g in self._grants.values() if g.is_active())
        max_depth = max((g.depth for g in self._grants.values()), default=0)

        return {
            "roots": [_build_node(r) for r in roots],
            "summary": {
                "total_grants": len(self._grants),
                "active_grants": active_count,
                "max_depth": max_depth,
                "unique_grantors": len({g.grantor_id for g in self._grants.values()}),
                "unique_grantees": len({g.grantee_id for g in self._grants.values()}),
            },
        }

    def summary(self) -> dict[str, Any]:
        active = sum(1 for g in self._grants.values() if g.is_active())
        revoked = sum(1 for g in self._grants.values() if g.revoked)
        expired = sum(1 for g in self._grants.values() if g.is_expired() and not g.revoked)
        by_scope: dict[str, int] = {}
        for g in self._grants.values():
            if g.is_active():
                for s in g.scopes:
                    by_scope[s] = by_scope.get(s, 0) + 1

        return {
            "total": len(self._grants),
            "active": active,
            "revoked": revoked,
            "expired": expired,
            "by_scope": by_scope,
            "history_entries": len(self._history),
        }

    def history(self) -> list[dict[str, Any]]:
        return list(self._history)

    def _get(self, grant_id: str) -> DelegationGrant:
        try:
            return self._grants[grant_id]
        except KeyError:
            raise KeyError(f"Grant {grant_id!r} not found") from None

    def _build_chain(self, grant_id: str) -> list[str]:
        chain: list[str] = []
        current_id = grant_id
        seen: set[str] = set()
        while current_id and current_id not in seen:
            seen.add(current_id)
            grant = self._grants.get(current_id)
            if not grant:
                break
            chain.append(current_id)
            current_id = grant.parent_grant_id
        chain.reverse()
        return chain

    def __len__(self) -> int:
        return len(self._grants)

    def __repr__(self) -> str:
        active = sum(1 for g in self._grants.values() if g.is_active())
        return f"DelegationRegistry({len(self._grants)} grants, {active} active)"


__all__ = [
    "DelegationGrant",
    "DelegationRegistry",
    "DerivedRole",
    "DomainRoleRegistry",
    "DomainScopedRole",
]
