"""Constitution editor — CRUD operations and version management.

Provides mutable draft editing of constitutions with immutable output,
version control with diff tracking, and three-way merge support.

Constitutional Hash: 608508a9bd224290

Usage::

    from acgs_lite.constitution import Constitution, Severity
    from acgs_lite.constitution.editor import (
        ConstitutionEditor,
        ConstitutionVersionControl,
        merge_constitutions,
    )

    # Edit a constitution
    editor = ConstitutionEditor(Constitution.default())
    editor.add_rule("CUSTOM-001", "No PII in logs", Severity.HIGH, "privacy")
    editor.update_rule("ACGS-002", severity=Severity.CRITICAL)
    editor.remove_rule("ACGS-005")

    # Inspect changes
    diff = editor.diff()
    print(diff.summary())

    # Build immutable output
    new_constitution = editor.build()

    # Version control
    vc = ConstitutionVersionControl(Constitution.default())
    vc.commit(new_constitution, "Added PII rule, tightened audit")

    # Merge two constitutions
    merged = merge_constitutions(
        base=Constitution.default(),
        theirs=new_constitution,
        conflict_resolution="theirs",
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .constitution import Constitution
from .rule import Rule, Severity

# ---------------------------------------------------------------------------
# RuleDraft
# ---------------------------------------------------------------------------


@dataclass
class RuleDraft:
    """Mutable draft of a constitutional rule.

    Unlike ``Rule`` (a frozen Pydantic model), a draft can be freely
    modified before being compiled into an immutable ``Rule`` via
    ``ConstitutionEditor.build()``.
    """

    rule_id: str
    text: str
    severity: Severity
    category: str
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return {
            "rule_id": self.rule_id,
            "text": self.text,
            "severity": self.severity.value,
            "category": self.category,
            "tags": list(self.tags),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RuleDraft:
        """Deserialize from a dict."""
        severity = data.get("severity", "high")
        if isinstance(severity, str):
            severity = Severity(severity.lower())
        return cls(
            rule_id=str(data["rule_id"]),
            text=str(data["text"]),
            severity=severity,
            category=str(data.get("category", "general")),
            tags=list(data.get("tags", [])),
        )

    @classmethod
    def from_rule(cls, rule: Rule) -> RuleDraft:
        """Create a draft from an existing ``Rule``."""
        return cls(
            rule_id=rule.id,
            text=rule.text,
            severity=rule.severity,
            category=rule.category,
            tags=list(rule.tags),
        )


# ---------------------------------------------------------------------------
# ConstitutionDiff
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConstitutionDiff:
    """Immutable diff between two constitution states.

    Attributes:
        added: Rules that were added.
        removed: IDs of rules that were removed.
        modified: Tuples of (rule_id, changed_fields) for updated rules.
    """

    added: list[RuleDraft] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    modified: list[tuple[str, dict[str, Any]]] = field(
        default_factory=list,
    )

    @property
    def is_empty(self) -> bool:
        """True when no changes were recorded."""
        return (
            len(self.added) == 0
            and len(self.removed) == 0
            and len(self.modified) == 0
        )

    def summary(self) -> str:
        """Human-readable diff summary."""
        parts: list[str] = []
        if self.added:
            ids = ", ".join(d.rule_id for d in self.added)
            parts.append(f"Added {len(self.added)} rule(s): {ids}")
        if self.removed:
            parts.append(
                f"Removed {len(self.removed)} rule(s): "
                f"{', '.join(self.removed)}"
            )
        if self.modified:
            for rule_id, changes in self.modified:
                fields = ", ".join(sorted(changes.keys()))
                parts.append(f"Modified {rule_id}: {fields}")
        if not parts:
            return "No changes"
        return "\n".join(parts)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return {
            "added": [d.to_dict() for d in self.added],
            "removed": list(self.removed),
            "modified": [
                {"rule_id": rid, "changes": changes}
                for rid, changes in self.modified
            ],
        }


# ---------------------------------------------------------------------------
# ConstitutionVersion
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConstitutionVersion:
    """Immutable metadata about a constitution version.

    Attributes:
        version: Monotonically increasing version number.
        constitutional_hash: Hash of the constitution at this version.
        created_at: ISO-8601 timestamp of when this version was committed.
        description: Human-readable description of the change.
        rule_count: Number of rules in this version.
        diff_from_previous: Diff from the prior version (None for v0).
    """

    version: int
    constitutional_hash: str
    created_at: str
    description: str
    rule_count: int
    diff_from_previous: ConstitutionDiff | None = None


# ---------------------------------------------------------------------------
# ConstitutionEditor
# ---------------------------------------------------------------------------


class ConstitutionEditor:
    """Mutable editor for constitutions.

    Loads an existing ``Constitution`` as a set of ``RuleDraft`` objects,
    allows add/remove/update operations, and produces a NEW immutable
    ``Constitution`` via ``build()``.  The original constitution is never
    mutated.
    """

    __slots__ = ("_base", "_drafts")

    def __init__(self, constitution: Constitution) -> None:
        self._base = constitution
        self._drafts: dict[str, RuleDraft] = {
            r.id: RuleDraft.from_rule(r) for r in constitution.rules
        }

    # -- CRUD ---------------------------------------------------------------

    def add_rule(
        self,
        rule_id: str,
        text: str,
        severity: Severity,
        category: str,
        tags: list[str] | None = None,
    ) -> RuleDraft:
        """Add a new rule draft.

        Raises:
            ValueError: If ``rule_id`` already exists.
        """
        if rule_id in self._drafts:
            raise ValueError(
                f"Rule '{rule_id}' already exists in the editor"
            )
        draft = RuleDraft(
            rule_id=rule_id,
            text=text,
            severity=severity,
            category=category,
            tags=list(tags) if tags is not None else [],
        )
        self._drafts[rule_id] = draft
        return draft

    def remove_rule(self, rule_id: str) -> RuleDraft:
        """Remove a rule draft by ID.

        Returns the removed draft.

        Raises:
            KeyError: If ``rule_id`` is not found.
        """
        try:
            return self._drafts.pop(rule_id)
        except KeyError:
            raise KeyError(
                f"Rule '{rule_id}' not found in the editor"
            ) from None

    def update_rule(
        self,
        rule_id: str,
        *,
        text: str | None = None,
        severity: Severity | None = None,
        category: str | None = None,
        tags: list[str] | None = None,
    ) -> RuleDraft:
        """Update specific fields of an existing rule draft.

        Only supplied keyword arguments are changed.

        Raises:
            KeyError: If ``rule_id`` is not found.
        """
        if rule_id not in self._drafts:
            raise KeyError(
                f"Rule '{rule_id}' not found in the editor"
            )
        draft = self._drafts[rule_id]
        if text is not None:
            draft.text = text
        if severity is not None:
            draft.severity = severity
        if category is not None:
            draft.category = category
        if tags is not None:
            draft.tags = list(tags)
        return draft

    def get_rule(self, rule_id: str) -> RuleDraft:
        """Return the current draft for *rule_id*.

        Raises:
            KeyError: If ``rule_id`` is not found.
        """
        try:
            return self._drafts[rule_id]
        except KeyError:
            raise KeyError(
                f"Rule '{rule_id}' not found in the editor"
            ) from None

    def list_rules(
        self,
        *,
        category: str | None = None,
        severity: Severity | None = None,
    ) -> list[RuleDraft]:
        """Return drafts, optionally filtered by category/severity."""
        result: list[RuleDraft] = []
        for draft in self._drafts.values():
            if category is not None and draft.category != category:
                continue
            if severity is not None and draft.severity != severity:
                continue
            result.append(draft)
        return result

    # -- Diff & build -------------------------------------------------------

    def diff(self) -> ConstitutionDiff:
        """Compute the diff from the base constitution."""
        base_by_id = {r.id: r for r in self._base.rules}
        current_ids = set(self._drafts.keys())
        base_ids = set(base_by_id.keys())

        added = [
            self._drafts[rid]
            for rid in sorted(current_ids - base_ids)
        ]
        removed = sorted(base_ids - current_ids)

        modified: list[tuple[str, dict[str, Any]]] = []
        for rid in sorted(current_ids & base_ids):
            draft = self._drafts[rid]
            base_rule = base_by_id[rid]
            changes: dict[str, Any] = {}
            if draft.text != base_rule.text:
                changes["text"] = {
                    "old": base_rule.text,
                    "new": draft.text,
                }
            if draft.severity != base_rule.severity:
                changes["severity"] = {
                    "old": base_rule.severity.value,
                    "new": draft.severity.value,
                }
            if draft.category != base_rule.category:
                changes["category"] = {
                    "old": base_rule.category,
                    "new": draft.category,
                }
            if list(draft.tags) != list(base_rule.tags):
                changes["tags"] = {
                    "old": list(base_rule.tags),
                    "new": list(draft.tags),
                }
            if changes:
                modified.append((rid, changes))

        return ConstitutionDiff(
            added=added,
            removed=removed,
            modified=modified,
        )

    def build(self) -> Constitution:
        """Produce a NEW ``Constitution`` from the current editor state.

        The original base constitution is never mutated.
        """
        rules = [
            Rule(
                id=d.rule_id,
                text=d.text,
                severity=d.severity,
                category=d.category,
                tags=list(d.tags),
            )
            for d in self._drafts.values()
        ]
        return Constitution(
            name=self._base.name,
            version=self._base.version,
            rules=rules,
            description=self._base.description,
            metadata=dict(self._base.metadata),
        )

    def validate_draft(self) -> list[str]:
        """Check for issues in the current draft state.

        Returns a list of human-readable issue descriptions.
        An empty list means no issues were found.
        """
        issues: list[str] = []
        seen_ids: set[str] = set()
        for draft in self._drafts.values():
            if draft.rule_id in seen_ids:
                issues.append(
                    f"Duplicate rule ID: '{draft.rule_id}'"
                )
            seen_ids.add(draft.rule_id)

            if not draft.rule_id.strip():
                issues.append("Rule has empty ID")
            if not draft.text.strip():
                issues.append(
                    f"Rule '{draft.rule_id}' has empty text"
                )
            if not draft.category.strip():
                issues.append(
                    f"Rule '{draft.rule_id}' has empty category"
                )
        return issues

    def reset(self) -> None:
        """Revert to the base constitution state."""
        self._drafts = {
            r.id: RuleDraft.from_rule(r) for r in self._base.rules
        }

    # -- Properties ---------------------------------------------------------

    @property
    def rule_count(self) -> int:
        """Number of rules currently in the editor."""
        return len(self._drafts)

    @property
    def has_changes(self) -> bool:
        """True if the editor state differs from the base constitution."""
        return not self.diff().is_empty


# ---------------------------------------------------------------------------
# ConstitutionVersionControl
# ---------------------------------------------------------------------------


class ConstitutionVersionControl:
    """Track constitution versions with diff provenance.

    Stores a linear history of constitution snapshots, each tagged with
    a version number, hash, timestamp, and diff from the prior version.
    """

    __slots__ = ("_versions", "_constitutions")

    def __init__(self, initial: Constitution) -> None:
        v0 = ConstitutionVersion(
            version=0,
            constitutional_hash=initial.hash,
            created_at=datetime.now(timezone.utc).isoformat(),
            description="Initial version",
            rule_count=len(initial.rules),
            diff_from_previous=None,
        )
        self._versions: list[ConstitutionVersion] = [v0]
        self._constitutions: list[Constitution] = [initial]

    def commit(
        self,
        constitution: Constitution,
        description: str,
    ) -> ConstitutionVersion:
        """Save a new version.

        Computes the diff from the previous version automatically.

        Args:
            constitution: The new constitution state to record.
            description: Human-readable description of the change.

        Returns:
            The created ``ConstitutionVersion``.
        """
        prev = self._constitutions[-1]
        diff = _diff_constitutions(prev, constitution)
        new_version = len(self._versions)
        version = ConstitutionVersion(
            version=new_version,
            constitutional_hash=constitution.hash,
            created_at=datetime.now(timezone.utc).isoformat(),
            description=description,
            rule_count=len(constitution.rules),
            diff_from_previous=diff,
        )
        self._versions.append(version)
        self._constitutions.append(constitution)
        return version

    def get_version(self, version: int) -> ConstitutionVersion:
        """Retrieve version metadata.

        Raises:
            IndexError: If *version* is out of range.
        """
        if version < 0 or version >= len(self._versions):
            raise IndexError(
                f"Version {version} out of range "
                f"[0, {len(self._versions) - 1}]"
            )
        return self._versions[version]

    def get_constitution(self, version: int) -> Constitution:
        """Retrieve the constitution at *version*.

        Raises:
            IndexError: If *version* is out of range.
        """
        if version < 0 or version >= len(self._constitutions):
            raise IndexError(
                f"Version {version} out of range "
                f"[0, {len(self._constitutions) - 1}]"
            )
        return self._constitutions[version]

    def diff(
        self,
        from_version: int,
        to_version: int,
    ) -> ConstitutionDiff:
        """Compute diff between two versions.

        Raises:
            IndexError: If either version is out of range.
        """
        c_from = self.get_constitution(from_version)
        c_to = self.get_constitution(to_version)
        return _diff_constitutions(c_from, c_to)

    def history(self) -> list[ConstitutionVersion]:
        """Return all version metadata in chronological order."""
        return list(self._versions)

    @property
    def latest_version(self) -> int:
        """The most recent version number."""
        return len(self._versions) - 1

    def rollback(self, version: int) -> Constitution:
        """Return the constitution at *version* (does not modify history).

        This is equivalent to ``get_constitution(version)`` but named
        for intent clarity — use ``commit()`` to record the rollback
        as a new version if desired.

        Raises:
            IndexError: If *version* is out of range.
        """
        return self.get_constitution(version)

    def export_history(self) -> list[dict[str, Any]]:
        """Export version history as JSON-serializable dicts."""
        result: list[dict[str, Any]] = []
        for v in self._versions:
            entry: dict[str, Any] = {
                "version": v.version,
                "constitutional_hash": v.constitutional_hash,
                "created_at": v.created_at,
                "description": v.description,
                "rule_count": v.rule_count,
            }
            if v.diff_from_previous is not None:
                entry["diff"] = v.diff_from_previous.to_dict()
            else:
                entry["diff"] = None
            result.append(entry)
        return result


# ---------------------------------------------------------------------------
# merge_constitutions
# ---------------------------------------------------------------------------


def merge_constitutions(
    base: Constitution,
    theirs: Constitution,
    *,
    conflict_resolution: str = "theirs",
) -> Constitution:
    """Merge two constitutions from a common base.

    Rules present only in *theirs* are added.  Rules present only in
    *base* are kept.  Rules present in both are resolved according to
    *conflict_resolution*:

    - ``"theirs"``: prefer the version from *theirs*.
    - ``"ours"``: prefer the version from *base*.
    - ``"strict"``: raise ``ValueError`` on any conflict.

    Args:
        base: The original / "ours" constitution.
        theirs: The incoming constitution to merge.
        conflict_resolution: Strategy for conflicting rules.

    Returns:
        A new ``Constitution`` containing the merged rule set.

    Raises:
        ValueError: If *conflict_resolution* is ``"strict"`` and a
            conflicting rule is found.
    """
    if conflict_resolution not in ("theirs", "ours", "strict"):
        raise ValueError(
            f"Invalid conflict_resolution: {conflict_resolution!r}; "
            f"expected 'theirs', 'ours', or 'strict'"
        )

    base_by_id = {r.id: r for r in base.rules}
    theirs_by_id = {r.id: r for r in theirs.rules}

    all_ids = dict.fromkeys(
        [r.id for r in base.rules] + [r.id for r in theirs.rules]
    )

    merged_rules: list[Rule] = []
    for rid in all_ids:
        in_base = rid in base_by_id
        in_theirs = rid in theirs_by_id
        if in_base and not in_theirs:
            merged_rules.append(base_by_id[rid])
        elif in_theirs and not in_base:
            merged_rules.append(theirs_by_id[rid])
        else:
            base_rule = base_by_id[rid]
            theirs_rule = theirs_by_id[rid]
            if _rules_equal(base_rule, theirs_rule):
                merged_rules.append(base_rule)
            elif conflict_resolution == "theirs":
                merged_rules.append(theirs_rule)
            elif conflict_resolution == "ours":
                merged_rules.append(base_rule)
            else:
                raise ValueError(
                    f"Conflict on rule '{rid}': strict mode "
                    f"does not allow differing versions"
                )

    return Constitution(
        name=base.name,
        version=base.version,
        rules=merged_rules,
        description=base.description,
        metadata=dict(base.metadata),
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _rules_equal(a: Rule, b: Rule) -> bool:
    """Check equality on the fields tracked by RuleDraft."""
    return (
        a.id == b.id
        and a.text == b.text
        and a.severity == b.severity
        and a.category == b.category
        and list(a.tags) == list(b.tags)
    )


def _diff_constitutions(
    old: Constitution,
    new: Constitution,
) -> ConstitutionDiff:
    """Compute a diff between two constitutions."""
    old_by_id = {r.id: r for r in old.rules}
    new_by_id = {r.id: r for r in new.rules}
    old_ids = set(old_by_id.keys())
    new_ids = set(new_by_id.keys())

    added = [
        RuleDraft.from_rule(new_by_id[rid])
        for rid in sorted(new_ids - old_ids)
    ]
    removed = sorted(old_ids - new_ids)

    modified: list[tuple[str, dict[str, Any]]] = []
    for rid in sorted(old_ids & new_ids):
        old_rule = old_by_id[rid]
        new_rule = new_by_id[rid]
        changes: dict[str, Any] = {}
        if old_rule.text != new_rule.text:
            changes["text"] = {
                "old": old_rule.text,
                "new": new_rule.text,
            }
        if old_rule.severity != new_rule.severity:
            changes["severity"] = {
                "old": old_rule.severity.value,
                "new": new_rule.severity.value,
            }
        if old_rule.category != new_rule.category:
            changes["category"] = {
                "old": old_rule.category,
                "new": new_rule.category,
            }
        if list(old_rule.tags) != list(new_rule.tags):
            changes["tags"] = {
                "old": list(old_rule.tags),
                "new": list(new_rule.tags),
            }
        if changes:
            modified.append((rid, changes))

    return ConstitutionDiff(
        added=added,
        removed=removed,
        modified=modified,
    )
