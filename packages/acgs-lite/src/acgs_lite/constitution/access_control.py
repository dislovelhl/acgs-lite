"""exp195: GovernanceAccessControl — fine-grained RBAC/ABAC for governance operations.

Resource-level permissions with condition-based access decisions, permission
inheritance, deny-override semantics, and full audit trail. Extends beyond
MACI's 4-role model for granular governance operation control.
Zero hot-path overhead (offline tooling only).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Permission(Enum):
    """Governance operation permissions."""

    READ_RULES = "read_rules"
    WRITE_RULES = "write_rules"
    DELETE_RULES = "delete_rules"
    READ_AUDIT = "read_audit"
    EXPORT_AUDIT = "export_audit"
    VALIDATE = "validate"
    EXECUTE = "execute"
    CONFIGURE = "configure"
    MANAGE_ROLES = "manage_roles"
    EMERGENCY_OVERRIDE = "emergency_override"
    APPROVE = "approve"
    ESCALATE = "escalate"
    VIEW_METRICS = "view_metrics"
    MANAGE_WAIVERS = "manage_waivers"
    MIGRATE = "migrate"


class AccessDecision(Enum):
    """Result of an access check."""

    ALLOW = "allow"
    DENY = "deny"
    ESCALATE = "escalate"


@dataclass
class AccessCondition:
    """A condition that must be true for a permission to apply."""

    name: str
    predicate: Callable[[dict[str, Any]], bool]
    description: str = ""

    def evaluate(self, context: dict[str, Any]) -> bool:
        try:
            return self.predicate(context)
        except Exception:
            return False


@dataclass
class AccessPolicy:
    """A set of permissions with optional conditions and resource scope."""

    name: str
    permissions: set[Permission]
    denied_permissions: set[Permission] = field(default_factory=set)
    resource_scope: str = "*"
    conditions: list[AccessCondition] = field(default_factory=list)
    priority: int = 0

    def grants(self, permission: Permission, context: dict[str, Any] | None = None) -> bool:
        if permission in self.denied_permissions:
            return False
        if permission not in self.permissions:
            return False
        if self.conditions and context is not None:
            return all(c.evaluate(context) for c in self.conditions)
        return not self.conditions

    def matches_resource(self, resource: str) -> bool:
        if self.resource_scope == "*":
            return True
        if self.resource_scope.endswith("*"):
            return resource.startswith(self.resource_scope[:-1])
        return resource == self.resource_scope


@dataclass
class AccessRole:
    """A named role with attached policies and optional parent for inheritance."""

    name: str
    policies: list[AccessPolicy] = field(default_factory=list)
    parent: str | None = None
    description: str = ""
    max_sessions: int = 0

    def add_policy(self, policy: AccessPolicy) -> AccessRole:
        self.policies.append(policy)
        return self


@dataclass
class AccessCheckResult:
    """Detailed result of an access control check."""

    decision: AccessDecision
    permission: Permission
    principal: str
    resource: str
    matched_policy: str | None = None
    reason: str = ""
    checked_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "permission": self.permission.value,
            "principal": self.principal,
            "resource": self.resource,
            "matched_policy": self.matched_policy,
            "reason": self.reason,
            "checked_at": self.checked_at,
        }


class GovernanceAccessControl:
    """Fine-grained access control for governance operations.

    Provides RBAC with optional ABAC conditions, deny-override semantics,
    role inheritance, resource scoping, and a queryable audit log.

    Example::

        acl = GovernanceAccessControl()

        admin_policy = AccessPolicy(
            "admin",
            permissions={Permission.READ_RULES, Permission.WRITE_RULES, Permission.MANAGE_ROLES},
        )
        acl.add_role(AccessRole("admin", policies=[admin_policy]))

        reader_policy = AccessPolicy(
            "reader",
            permissions={Permission.READ_RULES, Permission.READ_AUDIT, Permission.VIEW_METRICS},
        )
        acl.add_role(AccessRole("reader", policies=[reader_policy]))

        acl.assign("agent-007", "admin")

        result = acl.check("agent-007", Permission.WRITE_RULES)
        assert result.decision == AccessDecision.ALLOW
    """

    def __init__(self) -> None:
        self._roles: dict[str, AccessRole] = {}
        self._assignments: dict[str, set[str]] = {}
        self._audit_log: list[AccessCheckResult] = []

    def add_role(self, role: AccessRole) -> None:
        self._roles[role.name] = role

    def remove_role(self, role_name: str) -> bool:
        if role_name not in self._roles:
            return False
        del self._roles[role_name]
        for principal in list(self._assignments):
            self._assignments[principal].discard(role_name)
        return True

    def assign(self, principal: str, role_name: str) -> bool:
        if role_name not in self._roles:
            return False
        if principal not in self._assignments:
            self._assignments[principal] = set()
        self._assignments[principal].add(role_name)
        return True

    def revoke(self, principal: str, role_name: str) -> bool:
        if principal not in self._assignments:
            return False
        self._assignments[principal].discard(role_name)
        return True

    def check(
        self,
        principal: str,
        permission: Permission,
        resource: str = "*",
        context: dict[str, Any] | None = None,
        *,
        record: bool = True,
    ) -> AccessCheckResult:
        """Check if a principal has a permission on a resource."""
        role_names = self._assignments.get(principal, set())
        if not role_names:
            result = AccessCheckResult(
                decision=AccessDecision.DENY,
                permission=permission,
                principal=principal,
                resource=resource,
                reason="No roles assigned",
            )
            if record:
                self._audit_log.append(result)
            return result

        effective_roles = self._resolve_roles(role_names)
        all_policies = sorted(
            (p for r in effective_roles for p in r.policies),
            key=lambda p: p.priority,
            reverse=True,
        )

        for policy in all_policies:
            if not policy.matches_resource(resource):
                continue
            if permission in policy.denied_permissions:
                result = AccessCheckResult(
                    decision=AccessDecision.DENY,
                    permission=permission,
                    principal=principal,
                    resource=resource,
                    matched_policy=policy.name,
                    reason="Explicitly denied",
                )
                if record:
                    self._audit_log.append(result)
                return result

        for policy in all_policies:
            if not policy.matches_resource(resource):
                continue
            if policy.grants(permission, context):
                result = AccessCheckResult(
                    decision=AccessDecision.ALLOW,
                    permission=permission,
                    principal=principal,
                    resource=resource,
                    matched_policy=policy.name,
                    reason="Granted by policy",
                )
                if record:
                    self._audit_log.append(result)
                return result

        result = AccessCheckResult(
            decision=AccessDecision.DENY,
            permission=permission,
            principal=principal,
            resource=resource,
            reason="No matching policy grants this permission",
        )
        if record:
            self._audit_log.append(result)
        return result

    def check_all(
        self,
        principal: str,
        permissions: list[Permission],
        resource: str = "*",
        context: dict[str, Any] | None = None,
    ) -> dict[str, AccessCheckResult]:
        """Check multiple permissions at once."""
        return {perm.value: self.check(principal, perm, resource, context) for perm in permissions}

    def effective_permissions(self, principal: str, resource: str = "*") -> set[Permission]:
        """Return all permissions a principal has on a resource."""
        result: set[Permission] = set()
        for perm in Permission:
            check = self.check(principal, perm, resource, record=False)
            if check.decision == AccessDecision.ALLOW:
                result.add(perm)
        return result

    def principals_with_permission(self, permission: Permission, resource: str = "*") -> list[str]:
        """Find all principals that have a given permission."""
        return [
            p
            for p in self._assignments
            if self.check(p, permission, resource, record=False).decision == AccessDecision.ALLOW
        ]

    def audit_log(
        self,
        principal: str | None = None,
        decision: AccessDecision | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query the access audit log."""
        entries = self._audit_log
        if principal:
            entries = [e for e in entries if e.principal == principal]
        if decision:
            entries = [e for e in entries if e.decision == decision]
        return [e.to_dict() for e in entries[-limit:]]

    def summary(self) -> dict[str, Any]:
        """Access control summary for dashboards."""
        total_checks = len(self._audit_log)
        allow_count = sum(1 for e in self._audit_log if e.decision == AccessDecision.ALLOW)
        deny_count = sum(1 for e in self._audit_log if e.decision == AccessDecision.DENY)
        return {
            "roles": list(self._roles.keys()),
            "role_count": len(self._roles),
            "principals": list(self._assignments.keys()),
            "principal_count": len(self._assignments),
            "total_checks": total_checks,
            "allow_count": allow_count,
            "deny_count": deny_count,
            "deny_rate": round(deny_count / total_checks, 4) if total_checks else 0.0,
        }

    def _resolve_roles(self, role_names: set[str]) -> list[AccessRole]:
        """Resolve role inheritance chain."""
        resolved: list[AccessRole] = []
        visited: set[str] = set()

        def _walk(name: str) -> None:
            if name in visited or name not in self._roles:
                return
            visited.add(name)
            role = self._roles[name]
            resolved.append(role)
            if role.parent:
                _walk(role.parent)

        for rn in role_names:
            _walk(rn)
        return resolved
