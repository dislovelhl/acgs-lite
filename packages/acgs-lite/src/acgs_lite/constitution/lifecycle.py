"""Rule lifecycle and tenant isolation helpers for constitutions."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .constitution import Constitution
    from .rule import Rule


def set_rule_lifecycle_state(
    constitution: Constitution, rule_id: str, state: str, reason: str = ""
) -> bool:
    """exp164: Set lifecycle state for a rule.

    Manages rule lifecycle through draft/active/deprecated states.
    Draft rules are not enforced. Deprecated rules emit warnings.
    Active rules are fully enforced.

    Args:
        constitution: Constitution instance to modify
        rule_id: Rule to modify
        state: New state ("draft", "active", "deprecated")
        reason: Reason for state change

    Returns:
        True if state was changed, False if rule not found
    """
    if state not in ["draft", "active", "deprecated"]:
        raise ValueError(f"Invalid state: {state}")

    for rule in constitution.rules:
        if rule.id == rule_id:
            # Store old state for audit
            old_state = rule.metadata.get("lifecycle_state", "active")

            # Update rule enabled status based on state
            if state == "draft":
                rule.enabled = False
            elif state == "active":
                rule.enabled = True
            elif state == "deprecated":
                rule.enabled = True  # Still enforced but with warnings

            # Update metadata
            rule.metadata["lifecycle_state"] = state
            rule.metadata["lifecycle_transition"] = {
                "from": old_state,
                "to": state,
                "reason": reason,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            return True

    return False


def get_rule_lifecycle_states(constitution: Constitution) -> dict[str, dict[str, Any]]:
    """Get lifecycle state summary for all rules.

    Args:
        constitution: Constitution instance to inspect

    Returns:
        dict mapping rule_id to lifecycle info
    """
    states = {}
    for rule in constitution.rules:
        state = rule.metadata.get("lifecycle_state", "active")
        transition = rule.metadata.get("lifecycle_transition")

        states[rule.id] = {"state": state, "enabled": rule.enabled, "transition": transition}

    return states


def lifecycle_transition_rules(
    constitution: Constitution, from_state: str, to_state: str
) -> list[str]:
    """Find rules that can transition between lifecycle states.

    Args:
        constitution: Constitution instance to inspect
        from_state: Current state
        to_state: Target state

    Returns:
        List of rule IDs that can make this transition
    """
    valid_transitions = {
        ("draft", "active"): True,
        ("active", "deprecated"): True,
        ("deprecated", "active"): True,  # re-activation
    }

    if (from_state, to_state) not in valid_transitions:
        return []

    candidates = []
    for rule in constitution.rules:
        current_state = rule.metadata.get("lifecycle_state", "active")
        if current_state == from_state:
            candidates.append(rule.id)

    return candidates


def set_rule_tenants(
    constitution: Constitution, rule_id: str, tenants: list[str]
) -> bool:
    """exp165: Set tenant scoping for a rule.

    Enables multi-tenant rule isolation where rules can be scoped to
    specific tenants. Rules without tenant scoping apply to all tenants.

    Args:
        constitution: Constitution instance to modify
        rule_id: Rule to scope
        tenants: List of tenant IDs, empty list means all tenants

    Returns:
        True if rule was found and updated
    """
    for rule in constitution.rules:
        if rule.id == rule_id:
            rule.metadata["tenants"] = tenants
            return True
    return False


def get_tenant_rules(
    constitution: Constitution, tenant_id: str | None = None
) -> list[Rule]:
    """Get rules applicable to a specific tenant.

    Args:
        constitution: Constitution instance to inspect
        tenant_id: Tenant to filter for, None returns global rules only

    Returns:
        List of rules applicable to the tenant
    """
    applicable = []

    for rule in constitution.rules:
        tenant_scoping = rule.metadata.get("tenants", [])

        # Rule applies if:
        # - No tenant scoping (global rule)
        # - Tenant is in the scoped list
        # - Or we're asking for global rules (tenant_id is None)
        if (
            not tenant_scoping  # global rule
            or (tenant_id and tenant_id in tenant_scoping)  # scoped to this tenant
            or tenant_id is None
        ):  # asking for global rules
            applicable.append(rule)

    return applicable


def tenant_isolation_report(constitution: Constitution) -> dict[str, Any]:
    """Generate report on tenant rule isolation.

    Args:
        constitution: Constitution instance to inspect

    Returns:
        dict with tenant isolation statistics and conflicts
    """
    tenant_rules: dict[str, list[str]] = {}
    global_rules: list[str] = []

    for rule in constitution.rules:
        tenants = rule.metadata.get("tenants", [])
        if not tenants:
            global_rules.append(rule.id)
        else:
            for tenant in tenants:
                tenant_rules.setdefault(tenant, []).append(rule.id)

    # Check for tenant conflicts (same rule ID in multiple tenants with different content)
    conflicts: list[dict[str, Any]] = []
    rule_tenants: dict[str, dict[str, Any]] = {}

    for rule in constitution.rules:
        tenants = rule.metadata.get("tenants", [])
        if tenants:
            for tenant in tenants:
                if rule.id not in rule_tenants:
                    rule_tenants[rule.id] = {}
                rule_tenants[rule.id][tenant] = rule

    for rule_id, tenant_versions in rule_tenants.items():
        if len(tenant_versions) > 1:
            # Check if rule content differs between tenants
            base_rule = list(tenant_versions.values())[0]
            for _tenant, rule in tenant_versions.items():
                if rule != base_rule:
                    conflicts.append(
                        {
                            "rule_id": rule_id,
                            "conflicting_tenants": list(tenant_versions.keys()),
                            "issue": "same_rule_different_content",
                        }
                    )
                    break

    return {
        "global_rules": global_rules,
        "tenant_rules": tenant_rules,
        "total_tenants": len(tenant_rules),
        "tenant_conflicts": conflicts,
        "isolation_score": len(conflicts) == 0,  # True if no conflicts
    }


def deprecation_report(constitution: Constitution) -> dict[str, Any]:
    """exp135: Summary of rule deprecation status.

    Args:
        constitution: Constitution instance to inspect

    Returns:
        dict with keys:

        - ``deprecated_count``: total deprecated rules
        - ``active_deprecated``: deprecated rules that are still enabled
          (should be disabled or removed before next release)
        - ``with_successor``: deprecated rules that have a ``replaced_by``
          rule ID pointing to their successor
        - ``without_successor``: deprecated rules with no successor
          documented
        - ``migration_map``: {old_rule_id: new_rule_id} for rules with
          ``replaced_by`` set

    Example::

        report = deprecation_report(constitution)
        if report["active_deprecated"]:
            warnings.warn("Deprecated rules still enabled — disable before deployment")
    """
    deprecated = constitution.deprecated_rules()
    active_depr = [r for r in deprecated if r.enabled]
    with_succ = [r for r in deprecated if r.replaced_by]
    without_succ = [r for r in deprecated if not r.replaced_by]
    return {
        "deprecated_count": len(deprecated),
        "active_deprecated": [r.id for r in active_depr],
        "with_successor": [r.id for r in with_succ],
        "without_successor": [r.id for r in without_succ],
        "migration_map": {r.id: r.replaced_by for r in with_succ},
    }


def deprecation_migration_report(constitution: Constitution) -> dict[str, Any]:
    """exp149: Per-deprecated-rule migration guidance for sunset and replacement.

    Returns a list of migration entries with rule_id, replaced_by, valid_until
    (sunset), and a one-line recommendation. Does not touch the hot validation path.

    Args:
        constitution: Constitution instance to inspect

    Returns:
        dict with keys:
        - ``entries``: list of {rule_id, replaced_by, valid_until, recommendation}
        - ``summary``: {total, with_successor, with_sunset_date}
    """
    deprecated = constitution.deprecated_rules()
    entries: list[dict[str, Any]] = []
    with_successor = 0
    with_sunset = 0
    for r in deprecated:
        replaced_by = (r.replaced_by or "").strip()
        valid_until = (getattr(r, "valid_until", None) or "").strip()
        if replaced_by:
            with_successor += 1
        if valid_until:
            with_sunset += 1
        rec = (
            f"Migrate to rule {replaced_by} by {valid_until or 'next release'}"
            if replaced_by
            else (
                f"Sunset by {valid_until}"
                if valid_until
                else "Document successor or set replaced_by"
            )
        )
        entries.append(
            {
                "rule_id": r.id,
                "replaced_by": replaced_by or None,
                "valid_until": valid_until or None,
                "recommendation": rec,
            }
        )
    return {
        "entries": entries,
        "summary": {
            "total": len(deprecated),
            "with_successor": with_successor,
            "with_sunset_date": with_sunset,
        },
    }
