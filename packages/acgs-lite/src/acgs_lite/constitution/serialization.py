"""Constitution serialization helpers: YAML, bundle, and Rego export."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import yaml

if TYPE_CHECKING:
    from .constitution import Constitution


def to_yaml(constitution: Constitution) -> str:
    """exp111: Serialize a constitution to a YAML string.

    Produces a YAML document that can be loaded back via
    ``Constitution.from_yaml_file()`` or saved to disk for version control,
    sharing between services, or compliance archival.

    Args:
        constitution: The constitution to serialize.

    Returns:
        YAML string representing the full constitution.

    Example::

        yaml_str = to_yaml(constitution)
        with open("governance.yaml", "w") as f:
            f.write(yaml_str)
    """
    rules_data = []
    for r in constitution.rules:
        rule_dict: dict[str, Any] = {
            "id": r.id,
            "text": r.text,
            "severity": r.severity.value,
            "category": r.category,
        }
        if r.keywords:
            rule_dict["keywords"] = list(r.keywords)
        if r.patterns:
            rule_dict["patterns"] = list(r.patterns)
        if r.subcategory:
            rule_dict["subcategory"] = r.subcategory
        rule_dict["workflow_action"] = r.workflow_action.value
        if not r.enabled:
            rule_dict["enabled"] = False
        if r.hardcoded:
            rule_dict["hardcoded"] = True
        if r.depends_on:
            rule_dict["depends_on"] = list(r.depends_on)
        if r.tags:
            rule_dict["tags"] = list(r.tags)
        if r.priority != 0:
            rule_dict["priority"] = r.priority
        if r.condition:
            rule_dict["condition"] = dict(r.condition)
        if r.deprecated:
            rule_dict["deprecated"] = True
        if r.replaced_by:
            rule_dict["replaced_by"] = r.replaced_by
        if r.valid_from:
            rule_dict["valid_from"] = r.valid_from
        if r.valid_until:
            rule_dict["valid_until"] = r.valid_until
        if r.provenance:
            rule_dict["provenance"] = list(r.provenance)
        if r.metadata:
            rule_dict["metadata"] = dict(r.metadata)
        rules_data.append(rule_dict)

    doc: dict[str, Any] = {
        "name": constitution.name,
        "version": constitution.version,
        "description": constitution.description,
        "rules": rules_data,
    }
    if constitution.metadata:
        doc["metadata"] = dict(constitution.metadata)
    if constitution.permission_ceiling != "standard":
        doc["permission_ceiling"] = constitution.permission_ceiling
    if constitution.version_name:
        doc["version_name"] = constitution.version_name

    return cast(str, yaml.dump(doc, default_flow_style=False, sort_keys=False, allow_unicode=True))


def to_bundle(constitution: Constitution) -> dict[str, Any]:
    """exp125: Export a constitution as a self-contained JSON-serializable bundle.

    Produces a complete governance bundle suitable for cross-system
    portability, archival, or import by other governance platforms.
    Includes schema version, constitution hash, full rule data with
    all metadata, and a governance summary.

    Unlike ``to_yaml()`` (config file format), the bundle is designed
    for programmatic consumption and includes derived data (hash,
    summary, rule count) that receivers can use for validation without
    re-parsing.

    Args:
        constitution: The constitution to export.

    Returns:
        dict ready for ``json.dumps()``. Keys:

        - ``schema_version``: bundle format version
        - ``name``, ``version``, ``description``: constitution identity
        - ``hash``: constitution hash for integrity verification
        - ``rule_count``: total rules (including disabled)
        - ``active_rule_count``: enabled rules only
        - ``rules``: list of complete rule dicts
        - ``metadata``: constitution metadata
        - ``summary``: governance posture summary
    """
    rules_data = []
    for r in constitution.rules:
        rule_dict: dict[str, Any] = {
            "id": r.id,
            "text": r.text,
            "severity": r.severity.value,
            "keywords": list(r.keywords),
            "patterns": list(r.patterns),
            "category": r.category,
            "subcategory": r.subcategory,
            "workflow_action": r.workflow_action.value,
            "enabled": r.enabled,
            "hardcoded": r.hardcoded,
            "depends_on": list(r.depends_on),
            "tags": list(r.tags),
            "priority": r.priority,
        }
        if r.condition:
            rule_dict["condition"] = dict(r.condition)
        if r.deprecated:
            rule_dict["deprecated"] = True
        if r.replaced_by:
            rule_dict["replaced_by"] = r.replaced_by
        if r.valid_from:
            rule_dict["valid_from"] = r.valid_from
        if r.valid_until:
            rule_dict["valid_until"] = r.valid_until
        if r.provenance:
            rule_dict["provenance"] = list(r.provenance)
        if r.metadata:
            rule_dict["metadata"] = dict(r.metadata)
        rules_data.append(rule_dict)

    return {
        "schema_version": "1.0.0",
        "name": constitution.name,
        "version": constitution.version,
        "description": constitution.description,
        "hash": constitution.hash,
        "rule_count": len(constitution.rules),
        "active_rule_count": len(constitution.active_rules()),
        "rules": rules_data,
        "metadata": dict(constitution.metadata),
        "summary": constitution.governance_summary(),
    }


def from_bundle(bundle: dict[str, Any]) -> Constitution:
    """exp127: Reconstruct a Constitution from a to_bundle() export.

    Completes the round-trip started by :func:`to_bundle`.  Accepts the
    dict produced by ``to_bundle()`` (or a ``json.loads()`` of its
    serialised form) and returns a fully-functional Constitution instance.

    The ``summary``, ``hash``, ``rule_count``, and ``active_rule_count``
    fields are derived data — they are ignored on import and recomputed
    from the reconstructed rules.  The original hash is preserved in
    ``metadata["imported_hash"]`` so callers can verify integrity
    after import.

    Args:
        bundle: Dict as returned by :func:`to_bundle` or parsed from its
            JSON representation.

    Returns:
        Constitution with all rules, tags, priorities, dependencies, and
        metadata restored.

    Raises:
        ValueError: If ``bundle`` is missing required keys or has an
            unsupported ``schema_version``.

    Example::

        original = Constitution.from_template("gitlab")
        exported = to_bundle(original)
        imported = from_bundle(exported)
        assert imported.hash == original.hash
    """
    from .constitution import Constitution

    schema = bundle.get("schema_version", "")
    if schema not in ("1.0.0", ""):
        raise ValueError(f"Unsupported bundle schema_version: {schema!r}. Expected '1.0.0'.")
    if "rules" not in bundle:
        raise ValueError("Bundle is missing required 'rules' key.")

    # Preserve the original hash in metadata for post-import integrity checks
    incoming_meta = dict(bundle.get("metadata", {}))
    if "hash" in bundle:
        incoming_meta.setdefault("imported_hash", bundle["hash"])

    data: dict[str, Any] = {
        "name": bundle.get("name", "imported"),
        "version": bundle.get("version", "1.0"),
        "description": bundle.get("description", ""),
        "metadata": incoming_meta,
        "rules": bundle["rules"],
    }
    return Constitution._from_dict(data)


def to_rego(constitution: Constitution, package_name: str = "acgs.governance") -> str:
    """exp141: Export a constitution as a Rego (OPA) policy.

    Enables external enforcement via Open Policy Agent: keyword and pattern
    matching are emitted as Rego rules. Input: ``input.action`` (string).
    Output: ``allow``, ``deny``, ``violations`` (array of rule_id, severity,
    category). Only enabled, non-deprecated rules are included. Semantic
    subset: positive-verb exclusions and negation-aware matching are not
    replicated in Rego.

    Args:
        constitution: The constitution to export.
        package_name: Rego package name (e.g. ``acgs.governance``).

    Returns:
        Full Rego policy string.

    Example::

        rego_policy = to_rego(constitution)
        with open("policy.rego", "w") as f:
            f.write(rego_policy)
    """
    from .rego_export import constitution_to_rego

    return constitution_to_rego(constitution, package_name=package_name)
