"""Tests for the constitution editor module.

Covers RuleDraft, ConstitutionDiff, ConstitutionVersion,
ConstitutionEditor, ConstitutionVersionControl, and merge_constitutions.
"""

from __future__ import annotations

import pytest

from acgs_lite.constitution import Constitution, Rule, Severity
from acgs_lite.constitution.editor import (
    ConstitutionDiff,
    ConstitutionEditor,
    ConstitutionVersion,
    ConstitutionVersionControl,
    RuleDraft,
    merge_constitutions,
)

# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture()
def default_constitution() -> Constitution:
    """Return the ACGS default constitution."""
    return Constitution.default()


@pytest.fixture()
def single_rule_constitution() -> Constitution:
    """Constitution with one rule."""
    return Constitution(
        name="single",
        rules=[
            Rule(
                id="R1",
                text="No harm",
                severity=Severity.HIGH,
                category="safety",
                tags=["core"],
            ),
        ],
    )


@pytest.fixture()
def empty_constitution() -> Constitution:
    """Constitution with no rules."""
    return Constitution(name="empty", rules=[])


@pytest.fixture()
def multi_rule_constitution() -> Constitution:
    """Constitution with several rules for filter tests."""
    return Constitution(
        name="multi",
        rules=[
            Rule(
                id="M1",
                text="Safety first",
                severity=Severity.CRITICAL,
                category="safety",
            ),
            Rule(
                id="M2",
                text="Audit everything",
                severity=Severity.HIGH,
                category="audit",
            ),
            Rule(
                id="M3",
                text="Be transparent",
                severity=Severity.MEDIUM,
                category="transparency",
            ),
            Rule(
                id="M4",
                text="Protect data",
                severity=Severity.HIGH,
                category="safety",
            ),
        ],
    )


# ── RuleDraft tests ───────────────────────────────────────────────────────


class TestRuleDraft:
    def test_creation(self) -> None:
        draft = RuleDraft(
            rule_id="D1",
            text="Do not lie",
            severity=Severity.HIGH,
            category="integrity",
        )
        assert draft.rule_id == "D1"
        assert draft.text == "Do not lie"
        assert draft.severity == Severity.HIGH
        assert draft.category == "integrity"
        assert draft.tags == []

    def test_creation_with_tags(self) -> None:
        draft = RuleDraft(
            rule_id="D2",
            text="Protect PII",
            severity=Severity.CRITICAL,
            category="privacy",
            tags=["gdpr", "hipaa"],
        )
        assert draft.tags == ["gdpr", "hipaa"]

    def test_to_dict(self) -> None:
        draft = RuleDraft(
            rule_id="D3",
            text="Rule text",
            severity=Severity.MEDIUM,
            category="general",
            tags=["a"],
        )
        d = draft.to_dict()
        assert d["rule_id"] == "D3"
        assert d["severity"] == "medium"
        assert d["tags"] == ["a"]

    def test_from_dict_round_trip(self) -> None:
        original = RuleDraft(
            rule_id="RT1",
            text="Round trip",
            severity=Severity.LOW,
            category="test",
            tags=["x", "y"],
        )
        restored = RuleDraft.from_dict(original.to_dict())
        assert restored.rule_id == original.rule_id
        assert restored.text == original.text
        assert restored.severity == original.severity
        assert restored.category == original.category
        assert restored.tags == original.tags

    def test_from_dict_string_severity(self) -> None:
        data = {
            "rule_id": "S1",
            "text": "Test",
            "severity": "critical",
            "category": "safety",
        }
        draft = RuleDraft.from_dict(data)
        assert draft.severity == Severity.CRITICAL

    def test_from_rule(self) -> None:
        rule = Rule(
            id="FR1",
            text="From rule",
            severity=Severity.HIGH,
            category="audit",
            tags=["sox"],
        )
        draft = RuleDraft.from_rule(rule)
        assert draft.rule_id == "FR1"
        assert draft.text == "From rule"
        assert draft.severity == Severity.HIGH
        assert draft.tags == ["sox"]

    def test_mutability(self) -> None:
        draft = RuleDraft(
            rule_id="MUT",
            text="original",
            severity=Severity.LOW,
            category="general",
        )
        draft.text = "modified"
        draft.severity = Severity.CRITICAL
        assert draft.text == "modified"
        assert draft.severity == Severity.CRITICAL


# ── ConstitutionDiff tests ─────────────────────────────────────────────────


class TestConstitutionDiff:
    def test_empty_diff(self) -> None:
        diff = ConstitutionDiff()
        assert diff.is_empty
        assert diff.summary() == "No changes"

    def test_diff_with_additions(self) -> None:
        draft = RuleDraft(
            rule_id="NEW",
            text="New rule",
            severity=Severity.HIGH,
            category="general",
        )
        diff = ConstitutionDiff(added=[draft])
        assert not diff.is_empty
        assert "Added 1 rule(s)" in diff.summary()
        assert "NEW" in diff.summary()

    def test_diff_with_removals(self) -> None:
        diff = ConstitutionDiff(removed=["OLD-1", "OLD-2"])
        assert not diff.is_empty
        assert "Removed 2 rule(s)" in diff.summary()

    def test_diff_with_modifications(self) -> None:
        diff = ConstitutionDiff(modified=[("R1", {"text": {"old": "a", "new": "b"}})])
        assert not diff.is_empty
        assert "Modified R1" in diff.summary()

    def test_diff_to_dict(self) -> None:
        draft = RuleDraft(
            rule_id="A1",
            text="Added",
            severity=Severity.LOW,
            category="test",
        )
        diff = ConstitutionDiff(
            added=[draft],
            removed=["R1"],
            modified=[("M1", {"text": {"old": "x", "new": "y"}})],
        )
        d = diff.to_dict()
        assert len(d["added"]) == 1
        assert d["removed"] == ["R1"]
        assert d["modified"][0]["rule_id"] == "M1"

    def test_diff_is_frozen(self) -> None:
        diff = ConstitutionDiff()
        with pytest.raises(AttributeError):
            diff.added = []  # type: ignore[misc]


# ── ConstitutionVersion tests ──────────────────────────────────────────────


class TestConstitutionVersion:
    def test_creation(self) -> None:
        v = ConstitutionVersion(
            version=1,
            constitutional_hash="abc123",
            created_at="2026-01-01T00:00:00+00:00",
            description="Test version",
            rule_count=5,
        )
        assert v.version == 1
        assert v.constitutional_hash == "abc123"
        assert v.rule_count == 5
        assert v.diff_from_previous is None

    def test_with_diff(self) -> None:
        diff = ConstitutionDiff(removed=["R1"])
        v = ConstitutionVersion(
            version=2,
            constitutional_hash="def456",
            created_at="2026-01-02T00:00:00+00:00",
            description="Removed R1",
            rule_count=4,
            diff_from_previous=diff,
        )
        assert v.diff_from_previous is not None
        assert not v.diff_from_previous.is_empty

    def test_is_frozen(self) -> None:
        v = ConstitutionVersion(
            version=0,
            constitutional_hash="x",
            created_at="t",
            description="d",
            rule_count=0,
        )
        with pytest.raises(AttributeError):
            v.version = 99  # type: ignore[misc]


# ── ConstitutionEditor tests ──────────────────────────────────────────────


class TestConstitutionEditorCRUD:
    def test_initial_state(self, default_constitution: Constitution) -> None:
        editor = ConstitutionEditor(default_constitution)
        assert editor.rule_count == len(default_constitution.rules)
        assert not editor.has_changes

    def test_add_rule(self, single_rule_constitution: Constitution) -> None:
        editor = ConstitutionEditor(single_rule_constitution)
        draft = editor.add_rule("R2", "Be fair", Severity.MEDIUM, "fairness")
        assert draft.rule_id == "R2"
        assert editor.rule_count == 2
        assert editor.has_changes

    def test_add_duplicate_raises(self, single_rule_constitution: Constitution) -> None:
        editor = ConstitutionEditor(single_rule_constitution)
        with pytest.raises(ValueError, match="already exists"):
            editor.add_rule("R1", "Duplicate", Severity.LOW, "general")

    def test_remove_rule(self, single_rule_constitution: Constitution) -> None:
        editor = ConstitutionEditor(single_rule_constitution)
        removed = editor.remove_rule("R1")
        assert removed.rule_id == "R1"
        assert editor.rule_count == 0
        assert editor.has_changes

    def test_remove_nonexistent_raises(self, empty_constitution: Constitution) -> None:
        editor = ConstitutionEditor(empty_constitution)
        with pytest.raises(KeyError, match="not found"):
            editor.remove_rule("NOPE")

    def test_update_rule_text(self, single_rule_constitution: Constitution) -> None:
        editor = ConstitutionEditor(single_rule_constitution)
        updated = editor.update_rule("R1", text="Updated text")
        assert updated.text == "Updated text"
        assert editor.has_changes

    def test_update_rule_severity(self, single_rule_constitution: Constitution) -> None:
        editor = ConstitutionEditor(single_rule_constitution)
        editor.update_rule("R1", severity=Severity.CRITICAL)
        assert editor.get_rule("R1").severity == Severity.CRITICAL

    def test_update_rule_category(self, single_rule_constitution: Constitution) -> None:
        editor = ConstitutionEditor(single_rule_constitution)
        editor.update_rule("R1", category="new-cat")
        assert editor.get_rule("R1").category == "new-cat"

    def test_update_rule_tags(self, single_rule_constitution: Constitution) -> None:
        editor = ConstitutionEditor(single_rule_constitution)
        editor.update_rule("R1", tags=["new-tag"])
        assert editor.get_rule("R1").tags == ["new-tag"]

    def test_update_nonexistent_raises(self, empty_constitution: Constitution) -> None:
        editor = ConstitutionEditor(empty_constitution)
        with pytest.raises(KeyError, match="not found"):
            editor.update_rule("NOPE", text="x")

    def test_get_rule(self, single_rule_constitution: Constitution) -> None:
        editor = ConstitutionEditor(single_rule_constitution)
        draft = editor.get_rule("R1")
        assert draft.rule_id == "R1"

    def test_get_rule_not_found(self, empty_constitution: Constitution) -> None:
        editor = ConstitutionEditor(empty_constitution)
        with pytest.raises(KeyError, match="not found"):
            editor.get_rule("MISSING")

    def test_list_rules_all(self, multi_rule_constitution: Constitution) -> None:
        editor = ConstitutionEditor(multi_rule_constitution)
        assert len(editor.list_rules()) == 4

    def test_list_rules_by_category(self, multi_rule_constitution: Constitution) -> None:
        editor = ConstitutionEditor(multi_rule_constitution)
        safety = editor.list_rules(category="safety")
        assert len(safety) == 2
        assert all(d.category == "safety" for d in safety)

    def test_list_rules_by_severity(self, multi_rule_constitution: Constitution) -> None:
        editor = ConstitutionEditor(multi_rule_constitution)
        high = editor.list_rules(severity=Severity.HIGH)
        assert len(high) == 2
        assert all(d.severity == Severity.HIGH for d in high)

    def test_list_rules_combined_filter(self, multi_rule_constitution: Constitution) -> None:
        editor = ConstitutionEditor(multi_rule_constitution)
        result = editor.list_rules(category="safety", severity=Severity.CRITICAL)
        assert len(result) == 1
        assert result[0].rule_id == "M1"


class TestConstitutionEditorDiffAndBuild:
    def test_diff_no_changes(self, default_constitution: Constitution) -> None:
        editor = ConstitutionEditor(default_constitution)
        diff = editor.diff()
        assert diff.is_empty

    def test_diff_added(self, single_rule_constitution: Constitution) -> None:
        editor = ConstitutionEditor(single_rule_constitution)
        editor.add_rule("NEW-1", "New rule", Severity.LOW, "general")
        diff = editor.diff()
        assert len(diff.added) == 1
        assert diff.added[0].rule_id == "NEW-1"

    def test_diff_removed(self, single_rule_constitution: Constitution) -> None:
        editor = ConstitutionEditor(single_rule_constitution)
        editor.remove_rule("R1")
        diff = editor.diff()
        assert diff.removed == ["R1"]

    def test_diff_modified(self, single_rule_constitution: Constitution) -> None:
        editor = ConstitutionEditor(single_rule_constitution)
        editor.update_rule("R1", text="Changed text")
        diff = editor.diff()
        assert len(diff.modified) == 1
        rid, changes = diff.modified[0]
        assert rid == "R1"
        assert "text" in changes

    def test_build_produces_valid_constitution(
        self, single_rule_constitution: Constitution
    ) -> None:
        editor = ConstitutionEditor(single_rule_constitution)
        editor.add_rule("R2", "New rule", Severity.MEDIUM, "general")
        result = editor.build()
        assert isinstance(result, Constitution)
        assert len(result.rules) == 2
        rule_ids = {r.id for r in result.rules}
        assert "R1" in rule_ids
        assert "R2" in rule_ids

    def test_build_does_not_mutate_original(self, single_rule_constitution: Constitution) -> None:
        original_hash = single_rule_constitution.hash
        original_count = len(single_rule_constitution.rules)
        editor = ConstitutionEditor(single_rule_constitution)
        editor.add_rule("R2", "Extra", Severity.LOW, "general")
        _new = editor.build()
        assert single_rule_constitution.hash == original_hash
        assert len(single_rule_constitution.rules) == original_count

    def test_build_with_default_constitution(self, default_constitution: Constitution) -> None:
        editor = ConstitutionEditor(default_constitution)
        result = editor.build()
        assert len(result.rules) == len(default_constitution.rules)

    def test_reset_reverts_changes(self, single_rule_constitution: Constitution) -> None:
        editor = ConstitutionEditor(single_rule_constitution)
        editor.add_rule("TEMP", "Temporary", Severity.LOW, "general")
        assert editor.has_changes
        editor.reset()
        assert not editor.has_changes
        assert editor.rule_count == 1

    def test_has_changes_false_after_undo(self, single_rule_constitution: Constitution) -> None:
        editor = ConstitutionEditor(single_rule_constitution)
        editor.update_rule("R1", text="Changed")
        assert editor.has_changes
        editor.update_rule("R1", text="No harm")
        assert not editor.has_changes


class TestConstitutionEditorValidation:
    def test_validate_empty_text(self, empty_constitution: Constitution) -> None:
        editor = ConstitutionEditor(empty_constitution)
        editor.add_rule("BAD", "   ", Severity.LOW, "general")
        issues = editor.validate_draft()
        assert any("empty text" in i for i in issues)

    def test_validate_empty_category(self, empty_constitution: Constitution) -> None:
        editor = ConstitutionEditor(empty_constitution)
        editor.add_rule("BAD", "Valid text", Severity.LOW, "  ")
        issues = editor.validate_draft()
        assert any("empty category" in i for i in issues)

    def test_validate_empty_id(self, empty_constitution: Constitution) -> None:
        editor = ConstitutionEditor(empty_constitution)
        # Bypass add_rule validation by inserting directly
        editor._drafts[""] = RuleDraft(
            rule_id="",
            text="text",
            severity=Severity.LOW,
            category="general",
        )
        issues = editor.validate_draft()
        assert any("empty ID" in i for i in issues)

    def test_validate_clean(self, default_constitution: Constitution) -> None:
        editor = ConstitutionEditor(default_constitution)
        issues = editor.validate_draft()
        assert issues == []


# ── ConstitutionVersionControl tests ───────────────────────────────────────


class TestConstitutionVersionControl:
    def test_initial_version(self, default_constitution: Constitution) -> None:
        vc = ConstitutionVersionControl(default_constitution)
        assert vc.latest_version == 0
        v0 = vc.get_version(0)
        assert v0.version == 0
        assert v0.description == "Initial version"
        assert v0.diff_from_previous is None

    def test_commit_creates_version(self, single_rule_constitution: Constitution) -> None:
        vc = ConstitutionVersionControl(single_rule_constitution)
        editor = ConstitutionEditor(single_rule_constitution)
        editor.add_rule("R2", "New rule", Severity.LOW, "general")
        new_c = editor.build()
        v1 = vc.commit(new_c, "Added R2")
        assert v1.version == 1
        assert v1.description == "Added R2"
        assert v1.rule_count == 2
        assert vc.latest_version == 1

    def test_get_version_out_of_range(self, default_constitution: Constitution) -> None:
        vc = ConstitutionVersionControl(default_constitution)
        with pytest.raises(IndexError):
            vc.get_version(5)

    def test_get_constitution(self, single_rule_constitution: Constitution) -> None:
        vc = ConstitutionVersionControl(single_rule_constitution)
        c0 = vc.get_constitution(0)
        assert c0.hash == single_rule_constitution.hash

    def test_get_constitution_out_of_range(self, default_constitution: Constitution) -> None:
        vc = ConstitutionVersionControl(default_constitution)
        with pytest.raises(IndexError):
            vc.get_constitution(99)

    def test_diff_between_versions(self, single_rule_constitution: Constitution) -> None:
        vc = ConstitutionVersionControl(single_rule_constitution)
        editor = ConstitutionEditor(single_rule_constitution)
        editor.add_rule("R2", "Added rule", Severity.HIGH, "audit")
        new_c = editor.build()
        vc.commit(new_c, "Added R2")
        diff = vc.diff(0, 1)
        assert len(diff.added) == 1
        assert diff.added[0].rule_id == "R2"

    def test_history(self, single_rule_constitution: Constitution) -> None:
        vc = ConstitutionVersionControl(single_rule_constitution)
        editor = ConstitutionEditor(single_rule_constitution)
        editor.add_rule("R2", "Rule 2", Severity.LOW, "general")
        vc.commit(editor.build(), "v1")
        editor2 = ConstitutionEditor(vc.get_constitution(1))
        editor2.add_rule("R3", "Rule 3", Severity.LOW, "general")
        vc.commit(editor2.build(), "v2")
        hist = vc.history()
        assert len(hist) == 3
        assert hist[0].version == 0
        assert hist[1].version == 1
        assert hist[2].version == 2

    def test_rollback(self, single_rule_constitution: Constitution) -> None:
        vc = ConstitutionVersionControl(single_rule_constitution)
        editor = ConstitutionEditor(single_rule_constitution)
        editor.add_rule("R2", "Added", Severity.LOW, "general")
        vc.commit(editor.build(), "Added R2")
        rolled_back = vc.rollback(0)
        assert len(rolled_back.rules) == 1
        assert vc.latest_version == 1  # history unchanged

    def test_export_history(self, single_rule_constitution: Constitution) -> None:
        vc = ConstitutionVersionControl(single_rule_constitution)
        editor = ConstitutionEditor(single_rule_constitution)
        editor.remove_rule("R1")
        vc.commit(editor.build(), "Removed R1")
        export = vc.export_history()
        assert len(export) == 2
        assert export[0]["diff"] is None
        assert export[1]["diff"] is not None
        assert export[1]["diff"]["removed"] == ["R1"]

    def test_commit_records_hash(self, single_rule_constitution: Constitution) -> None:
        vc = ConstitutionVersionControl(single_rule_constitution)
        editor = ConstitutionEditor(single_rule_constitution)
        editor.add_rule("R2", "Rule 2", Severity.LOW, "general")
        new_c = editor.build()
        v1 = vc.commit(new_c, "Add R2")
        assert v1.constitutional_hash == new_c.hash

    def test_diff_records_modifications(self, single_rule_constitution: Constitution) -> None:
        vc = ConstitutionVersionControl(single_rule_constitution)
        editor = ConstitutionEditor(single_rule_constitution)
        editor.update_rule("R1", text="Updated text")
        vc.commit(editor.build(), "Updated R1")
        diff = vc.diff(0, 1)
        assert len(diff.modified) == 1
        assert diff.modified[0][0] == "R1"


# ── merge_constitutions tests ─────────────────────────────────────────────


class TestMergeConstitutions:
    def test_no_conflict(self) -> None:
        base = Constitution(
            name="base",
            rules=[
                Rule(
                    id="R1",
                    text="Rule one",
                    severity=Severity.HIGH,
                    category="general",
                ),
            ],
        )
        theirs = Constitution(
            name="theirs",
            rules=[
                Rule(
                    id="R1",
                    text="Rule one",
                    severity=Severity.HIGH,
                    category="general",
                ),
                Rule(
                    id="R2",
                    text="Rule two",
                    severity=Severity.LOW,
                    category="general",
                ),
            ],
        )
        merged = merge_constitutions(base, theirs)
        ids = {r.id for r in merged.rules}
        assert ids == {"R1", "R2"}

    def test_theirs_wins(self) -> None:
        base = Constitution(
            name="base",
            rules=[
                Rule(
                    id="R1",
                    text="Original",
                    severity=Severity.LOW,
                    category="general",
                ),
            ],
        )
        theirs = Constitution(
            name="theirs",
            rules=[
                Rule(
                    id="R1",
                    text="Modified",
                    severity=Severity.CRITICAL,
                    category="safety",
                ),
            ],
        )
        merged = merge_constitutions(base, theirs, conflict_resolution="theirs")
        r = merged.rules[0]
        assert r.text == "Modified"
        assert r.severity == Severity.CRITICAL

    def test_ours_wins(self) -> None:
        base = Constitution(
            name="base",
            rules=[
                Rule(
                    id="R1",
                    text="Original",
                    severity=Severity.LOW,
                    category="general",
                ),
            ],
        )
        theirs = Constitution(
            name="theirs",
            rules=[
                Rule(
                    id="R1",
                    text="Modified",
                    severity=Severity.CRITICAL,
                    category="safety",
                ),
            ],
        )
        merged = merge_constitutions(base, theirs, conflict_resolution="ours")
        r = merged.rules[0]
        assert r.text == "Original"
        assert r.severity == Severity.LOW

    def test_strict_raises_on_conflict(self) -> None:
        base = Constitution(
            name="base",
            rules=[
                Rule(
                    id="R1",
                    text="Original",
                    severity=Severity.LOW,
                    category="general",
                ),
            ],
        )
        theirs = Constitution(
            name="theirs",
            rules=[
                Rule(
                    id="R1",
                    text="Modified",
                    severity=Severity.HIGH,
                    category="general",
                ),
            ],
        )
        with pytest.raises(ValueError, match="strict"):
            merge_constitutions(base, theirs, conflict_resolution="strict")

    def test_strict_no_conflict(self) -> None:
        base = Constitution(
            name="base",
            rules=[
                Rule(
                    id="R1",
                    text="Same",
                    severity=Severity.HIGH,
                    category="general",
                ),
            ],
        )
        theirs = Constitution(
            name="theirs",
            rules=[
                Rule(
                    id="R1",
                    text="Same",
                    severity=Severity.HIGH,
                    category="general",
                ),
                Rule(
                    id="R2",
                    text="New",
                    severity=Severity.LOW,
                    category="general",
                ),
            ],
        )
        merged = merge_constitutions(base, theirs, conflict_resolution="strict")
        assert len(merged.rules) == 2

    def test_rules_only_in_base_kept(self) -> None:
        base = Constitution(
            name="base",
            rules=[
                Rule(
                    id="R1",
                    text="Base only",
                    severity=Severity.HIGH,
                    category="general",
                ),
                Rule(
                    id="R2",
                    text="Shared",
                    severity=Severity.LOW,
                    category="general",
                ),
            ],
        )
        theirs = Constitution(
            name="theirs",
            rules=[
                Rule(
                    id="R2",
                    text="Shared",
                    severity=Severity.LOW,
                    category="general",
                ),
            ],
        )
        merged = merge_constitutions(base, theirs)
        ids = {r.id for r in merged.rules}
        assert "R1" in ids

    def test_invalid_conflict_resolution_raises(self) -> None:
        base = Constitution(name="b", rules=[])
        theirs = Constitution(name="t", rules=[])
        with pytest.raises(ValueError, match="Invalid"):
            merge_constitutions(base, theirs, conflict_resolution="invalid")

    def test_merge_empty_constitutions(self) -> None:
        base = Constitution(name="b", rules=[])
        theirs = Constitution(name="t", rules=[])
        merged = merge_constitutions(base, theirs)
        assert merged.rules == []

    def test_merge_preserves_base_metadata(self) -> None:
        base = Constitution(
            name="base-name",
            version="2.0.0",
            rules=[],
            description="Base description",
        )
        theirs = Constitution(
            name="theirs-name",
            version="3.0.0",
            rules=[],
        )
        merged = merge_constitutions(base, theirs)
        assert merged.name == "base-name"
        assert merged.version == "2.0.0"
        assert merged.description == "Base description"


# ── Edge case tests ────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_editor_with_empty_constitution(self, empty_constitution: Constitution) -> None:
        editor = ConstitutionEditor(empty_constitution)
        assert editor.rule_count == 0
        assert not editor.has_changes
        result = editor.build()
        assert len(result.rules) == 0

    def test_editor_add_then_remove_is_no_change(self, empty_constitution: Constitution) -> None:
        editor = ConstitutionEditor(empty_constitution)
        editor.add_rule("TEMP", "Temporary", Severity.LOW, "general")
        editor.remove_rule("TEMP")
        assert not editor.has_changes

    def test_version_control_with_default(self, default_constitution: Constitution) -> None:
        vc = ConstitutionVersionControl(default_constitution)
        assert vc.latest_version == 0
        v0 = vc.get_version(0)
        assert v0.rule_count == len(default_constitution.rules)
        assert v0.constitutional_hash == default_constitution.hash

    def test_many_rules_editor(self) -> None:
        rules = [
            Rule(
                id=f"BULK-{i:03d}",
                text=f"Bulk rule {i}",
                severity=Severity.LOW,
                category="bulk",
            )
            for i in range(50)
        ]
        c = Constitution(name="bulk", rules=rules)
        editor = ConstitutionEditor(c)
        assert editor.rule_count == 50
        editor.remove_rule("BULK-025")
        assert editor.rule_count == 49
        diff = editor.diff()
        assert diff.removed == ["BULK-025"]

    def test_build_preserves_constitution_name(self, default_constitution: Constitution) -> None:
        editor = ConstitutionEditor(default_constitution)
        result = editor.build()
        assert result.name == default_constitution.name

    def test_multiple_commits_version_numbers(self, single_rule_constitution: Constitution) -> None:
        vc = ConstitutionVersionControl(single_rule_constitution)
        for i in range(5):
            editor = ConstitutionEditor(vc.get_constitution(vc.latest_version))
            editor.add_rule(
                f"V{i + 1}",
                f"Version {i + 1}",
                Severity.LOW,
                "general",
            )
            vc.commit(editor.build(), f"Commit {i + 1}")
        assert vc.latest_version == 5
        hist = vc.history()
        for i, v in enumerate(hist):
            assert v.version == i

    def test_add_rule_with_tags(self, empty_constitution: Constitution) -> None:
        editor = ConstitutionEditor(empty_constitution)
        draft = editor.add_rule(
            "T1",
            "Tagged rule",
            Severity.HIGH,
            "compliance",
            tags=["gdpr", "sox"],
        )
        assert draft.tags == ["gdpr", "sox"]
        built = editor.build()
        rule = built.rules[0]
        assert list(rule.tags) == ["gdpr", "sox"]

    def test_diff_summary_comprehensive(self, multi_rule_constitution: Constitution) -> None:
        editor = ConstitutionEditor(multi_rule_constitution)
        editor.add_rule("NEW", "Brand new", Severity.LOW, "general")
        editor.remove_rule("M2")
        editor.update_rule("M1", text="Safety always first")
        diff = editor.diff()
        summary = diff.summary()
        assert "Added" in summary
        assert "Removed" in summary
        assert "Modified" in summary
