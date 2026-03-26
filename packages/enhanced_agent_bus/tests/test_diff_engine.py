"""Tests for constitutional.diff_engine module."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from enhanced_agent_bus.constitutional.diff_engine import (
    ConstitutionalDiffEngine,
    DiffChange,
    PrincipleChange,
    SemanticDiff,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_version(
    version_id="v1",
    version="1.0.0",
    content=None,
    constitutional_hash="hash-a",
):
    """Create a mock ConstitutionalVersion."""
    v = MagicMock()
    v.version_id = version_id
    v.version = version
    v.content = content or {}
    v.constitutional_hash = constitutional_hash
    return v


def _make_storage(versions=None):
    """Create a mock ConstitutionalStorageService."""
    storage = AsyncMock()
    _versions = versions or {}

    async def get_version(vid):
        return _versions.get(vid)

    storage.get_version = AsyncMock(side_effect=get_version)
    return storage


@pytest.fixture()
def engine():
    storage = _make_storage()
    return ConstitutionalDiffEngine(storage=storage)


# ---------------------------------------------------------------------------
# DiffChange / PrincipleChange models
# ---------------------------------------------------------------------------


class TestModels:
    def test_diff_change_creation(self):
        dc = DiffChange(
            change_type="added",
            path="principles.new_one",
            new_value="val",
        )
        assert dc.change_type == "added"
        assert dc.path == "principles.new_one"

    def test_principle_change_creation(self):
        pc = PrincipleChange(
            principle_id="p1",
            change_type="removed",
            old_content="old stuff",
            impact_level="critical",
        )
        assert pc.principle_id == "p1"
        assert pc.impact_level == "critical"

    def test_semantic_diff_defaults(self):
        sd = SemanticDiff(
            from_version="1.0",
            to_version="2.0",
            from_version_id="v1",
            to_version_id="v2",
            from_hash="a",
            to_hash="b",
            hash_changed=True,
        )
        assert sd.total_changes == 0
        assert sd.all_changes == []
        assert sd.breaking_changes == []


# ---------------------------------------------------------------------------
# _compute_content_diff
# ---------------------------------------------------------------------------


class TestComputeContentDiff:
    def test_added_fields(self, engine):
        diff = SemanticDiff(
            from_version="1",
            to_version="2",
            from_version_id="v1",
            to_version_id="v2",
            from_hash="a",
            to_hash="b",
            hash_changed=False,
        )
        engine._compute_content_diff(diff, {}, {"new_key": "val"})
        assert diff.additions_count == 1
        assert "new_key" in diff.added_fields
        assert diff.total_changes == 1

    def test_removed_fields(self, engine):
        diff = SemanticDiff(
            from_version="1",
            to_version="2",
            from_version_id="v1",
            to_version_id="v2",
            from_hash="a",
            to_hash="b",
            hash_changed=False,
        )
        engine._compute_content_diff(diff, {"old_key": "val"}, {})
        assert diff.removals_count == 1
        assert "old_key" in diff.removed_fields

    def test_modified_fields(self, engine):
        diff = SemanticDiff(
            from_version="1",
            to_version="2",
            from_version_id="v1",
            to_version_id="v2",
            from_hash="a",
            to_hash="b",
            hash_changed=False,
        )
        engine._compute_content_diff(diff, {"key": "old"}, {"key": "new"})
        assert diff.modifications_count == 1
        assert "key" in diff.modified_fields
        assert diff.modified_fields["key"]["from"] == "old"
        assert diff.modified_fields["key"]["to"] == "new"

    def test_nested_dict_recursion(self, engine):
        diff = SemanticDiff(
            from_version="1",
            to_version="2",
            from_version_id="v1",
            to_version_id="v2",
            from_hash="a",
            to_hash="b",
            hash_changed=False,
        )
        engine._compute_content_diff(
            diff,
            {"nested": {"a": 1}},
            {"nested": {"a": 2}},
        )
        assert diff.modifications_count == 1
        assert "nested.a" in diff.modified_fields

    def test_no_changes(self, engine):
        diff = SemanticDiff(
            from_version="1",
            to_version="2",
            from_version_id="v1",
            to_version_id="v2",
            from_hash="a",
            to_hash="b",
            hash_changed=False,
        )
        engine._compute_content_diff(diff, {"a": 1}, {"a": 1})
        assert diff.total_changes == 0

    def test_all_changes_tracked(self, engine):
        diff = SemanticDiff(
            from_version="1",
            to_version="2",
            from_version_id="v1",
            to_version_id="v2",
            from_hash="a",
            to_hash="b",
            hash_changed=False,
        )
        engine._compute_content_diff(
            diff,
            {"removed": 1, "modified": "old"},
            {"modified": "new", "added": 3},
        )
        assert len(diff.all_changes) == 3
        types = {c.change_type for c in diff.all_changes}
        assert types == {"added", "removed", "modified"}


# ---------------------------------------------------------------------------
# _assess_impact
# ---------------------------------------------------------------------------


class TestAssessImpact:
    def test_hash_changed_is_critical(self, engine):
        diff = SemanticDiff(
            from_version="1",
            to_version="2",
            from_version_id="v1",
            to_version_id="v2",
            from_hash="a",
            to_hash="b",
            hash_changed=True,
        )
        engine._assess_impact(diff)
        assert diff.impact_level == "critical"

    def test_principle_removed_is_critical(self, engine):
        diff = SemanticDiff(
            from_version="1",
            to_version="2",
            from_version_id="v1",
            to_version_id="v2",
            from_hash="a",
            to_hash="a",
            hash_changed=False,
            principle_changes=[PrincipleChange(principle_id="p1", change_type="removed")],
        )
        engine._assess_impact(diff)
        assert diff.impact_level == "critical"

    def test_many_changes_is_high(self, engine):
        diff = SemanticDiff(
            from_version="1",
            to_version="2",
            from_version_id="v1",
            to_version_id="v2",
            from_hash="a",
            to_hash="a",
            hash_changed=False,
            total_changes=15,
        )
        engine._assess_impact(diff)
        assert diff.impact_level == "high"

    def test_principle_added_is_high(self, engine):
        diff = SemanticDiff(
            from_version="1",
            to_version="2",
            from_version_id="v1",
            to_version_id="v2",
            from_hash="a",
            to_hash="a",
            hash_changed=False,
            principle_changes=[
                PrincipleChange(principle_id="p1", change_type="added", new_content="x")
            ],
        )
        engine._assess_impact(diff)
        assert diff.impact_level == "high"

    def test_moderate_changes_is_medium(self, engine):
        diff = SemanticDiff(
            from_version="1",
            to_version="2",
            from_version_id="v1",
            to_version_id="v2",
            from_hash="a",
            to_hash="a",
            hash_changed=False,
            total_changes=5,
        )
        engine._assess_impact(diff)
        assert diff.impact_level == "medium"

    def test_few_changes_is_low(self, engine):
        diff = SemanticDiff(
            from_version="1",
            to_version="2",
            from_version_id="v1",
            to_version_id="v2",
            from_hash="a",
            to_hash="a",
            hash_changed=False,
            total_changes=1,
        )
        engine._assess_impact(diff)
        assert diff.impact_level == "low"


# ---------------------------------------------------------------------------
# _detect_breaking_changes
# ---------------------------------------------------------------------------


class TestDetectBreakingChanges:
    def test_modified_breaking_field(self, engine):
        diff = SemanticDiff(
            from_version="1",
            to_version="2",
            from_version_id="v1",
            to_version_id="v2",
            from_hash="a",
            to_hash="b",
            hash_changed=True,
            modified_fields={"constitutional_hash": {"from": "a", "to": "b"}},
        )
        engine._detect_breaking_changes(diff)
        assert len(diff.breaking_changes) >= 1
        assert "constitutional_hash" in diff.breaking_changes[0]

    def test_removed_breaking_field(self, engine):
        diff = SemanticDiff(
            from_version="1",
            to_version="2",
            from_version_id="v1",
            to_version_id="v2",
            from_hash="a",
            to_hash="b",
            hash_changed=True,
            removed_fields={"enforcement_rules": {"rule1": True}},
        )
        engine._detect_breaking_changes(diff)
        assert any("enforcement_rules" in bc for bc in diff.breaking_changes)

    def test_removed_principle_is_breaking(self, engine):
        diff = SemanticDiff(
            from_version="1",
            to_version="2",
            from_version_id="v1",
            to_version_id="v2",
            from_hash="a",
            to_hash="b",
            hash_changed=True,
            principle_changes=[
                PrincipleChange(principle_id="p1", change_type="removed", old_content="x")
            ],
        )
        engine._detect_breaking_changes(diff)
        assert any("p1" in bc for bc in diff.breaking_changes)

    def test_non_breaking_field_not_flagged(self, engine):
        diff = SemanticDiff(
            from_version="1",
            to_version="2",
            from_version_id="v1",
            to_version_id="v2",
            from_hash="a",
            to_hash="a",
            hash_changed=False,
            modified_fields={"description": {"from": "old", "to": "new"}},
        )
        engine._detect_breaking_changes(diff)
        assert len(diff.breaking_changes) == 0


# ---------------------------------------------------------------------------
# _assess_principle_impact
# ---------------------------------------------------------------------------


class TestAssessPrincipleImpact:
    def test_critical_principle_name(self, engine):
        assert engine._assess_principle_impact("core_governance_v1", "a", "b") == "critical"
        assert engine._assess_principle_impact("maci_rules", "a", "b") == "critical"

    def test_high_similarity_is_low(self, engine):
        old = "The agent must follow all governance rules strictly."
        new = "The agent must follow all governance rules strictly!"
        assert engine._assess_principle_impact("misc", old, new) == "low"

    def test_low_similarity_is_high(self, engine):
        old = "Always verify identity before action."
        new = "Completely different principle about logging and monitoring."
        result = engine._assess_principle_impact("misc", old, new)
        assert result in ("medium", "high")


# ---------------------------------------------------------------------------
# _stringify_principle
# ---------------------------------------------------------------------------


class TestStringifyPrinciple:
    def test_string_passthrough(self, engine):
        assert engine._stringify_principle("hello") == "hello"

    def test_dict_to_json(self, engine):
        result = engine._stringify_principle({"b": 2, "a": 1})
        assert '"a"' in result
        assert '"b"' in result

    def test_other_types(self, engine):
        assert engine._stringify_principle(42) == "42"


# ---------------------------------------------------------------------------
# _analyze_dict_principles
# ---------------------------------------------------------------------------


class TestAnalyzeDictPrinciples:
    def test_added_principle(self, engine):
        diff = SemanticDiff(
            from_version="1",
            to_version="2",
            from_version_id="v1",
            to_version_id="v2",
            from_hash="a",
            to_hash="b",
            hash_changed=True,
        )
        engine._analyze_dict_principles(diff, {}, {"new_p": "content"})
        assert len(diff.principle_changes) == 1
        assert diff.principle_changes[0].change_type == "added"

    def test_removed_principle(self, engine):
        diff = SemanticDiff(
            from_version="1",
            to_version="2",
            from_version_id="v1",
            to_version_id="v2",
            from_hash="a",
            to_hash="b",
            hash_changed=True,
        )
        engine._analyze_dict_principles(diff, {"old_p": "content"}, {})
        assert len(diff.principle_changes) == 1
        assert diff.principle_changes[0].change_type == "removed"
        assert diff.principle_changes[0].impact_level == "critical"

    def test_modified_principle(self, engine):
        diff = SemanticDiff(
            from_version="1",
            to_version="2",
            from_version_id="v1",
            to_version_id="v2",
            from_hash="a",
            to_hash="b",
            hash_changed=True,
        )
        engine._analyze_dict_principles(diff, {"p1": "old"}, {"p1": "new"})
        assert len(diff.principle_changes) == 1
        assert diff.principle_changes[0].change_type == "modified"


# ---------------------------------------------------------------------------
# _analyze_list_principles
# ---------------------------------------------------------------------------


class TestAnalyzeListPrinciples:
    def test_added_in_list(self, engine):
        diff = SemanticDiff(
            from_version="1",
            to_version="2",
            from_version_id="v1",
            to_version_id="v2",
            from_hash="a",
            to_hash="b",
            hash_changed=True,
        )
        engine._analyze_list_principles(diff, ["A"], ["A", "B"])
        added = [pc for pc in diff.principle_changes if pc.change_type == "added"]
        assert len(added) == 1

    def test_removed_in_list(self, engine):
        diff = SemanticDiff(
            from_version="1",
            to_version="2",
            from_version_id="v1",
            to_version_id="v2",
            from_hash="a",
            to_hash="b",
            hash_changed=True,
        )
        engine._analyze_list_principles(diff, ["A", "B"], ["A"])
        removed = [pc for pc in diff.principle_changes if pc.change_type == "removed"]
        assert len(removed) == 1


# ---------------------------------------------------------------------------
# compute_diff (integration with storage mock)
# ---------------------------------------------------------------------------


class TestComputeDiff:
    @pytest.mark.asyncio
    async def test_returns_none_when_version_not_found(self):
        storage = _make_storage()
        eng = ConstitutionalDiffEngine(storage=storage)
        result = await eng.compute_diff("v1", "v2")
        assert result is None

    @pytest.mark.asyncio
    async def test_computes_diff_between_versions(self):
        v1 = _make_version("v1", "1.0", {"key": "old"}, "hash-a")
        v2 = _make_version("v2", "2.0", {"key": "new", "added": True}, "hash-b")
        storage = _make_storage({"v1": v1, "v2": v2})
        eng = ConstitutionalDiffEngine(storage=storage)

        diff = await eng.compute_diff("v1", "v2")
        assert diff is not None
        assert diff.hash_changed is True
        assert diff.total_changes >= 2  # 1 modified + 1 added
        assert diff.impact_level == "critical"  # hash changed

    @pytest.mark.asyncio
    async def test_compute_diff_no_principles(self):
        v1 = _make_version("v1", "1.0", {"a": 1}, "h")
        v2 = _make_version("v2", "2.0", {"a": 1}, "h")
        storage = _make_storage({"v1": v1, "v2": v2})
        eng = ConstitutionalDiffEngine(storage=storage)

        diff = await eng.compute_diff("v1", "v2", include_principles=False)
        assert diff is not None
        assert diff.total_changes == 0


# ---------------------------------------------------------------------------
# compute_diff_from_content
# ---------------------------------------------------------------------------


class TestComputeDiffFromContent:
    @pytest.mark.asyncio
    async def test_returns_none_if_source_missing(self):
        storage = _make_storage()
        eng = ConstitutionalDiffEngine(storage=storage)
        result = await eng.compute_diff_from_content("v1", {"new": True})
        assert result is None

    @pytest.mark.asyncio
    async def test_diffs_against_proposed(self):
        v1 = _make_version("v1", "1.0", {"key": "old"}, "hash-a")
        storage = _make_storage({"v1": v1})
        eng = ConstitutionalDiffEngine(storage=storage)

        diff = await eng.compute_diff_from_content("v1", {"key": "new"})
        assert diff is not None
        assert diff.to_version == "proposed"
        assert diff.modifications_count == 1


# ---------------------------------------------------------------------------
# compute_text_diff
# ---------------------------------------------------------------------------


class TestComputeTextDiff:
    @pytest.mark.asyncio
    async def test_returns_none_if_version_missing(self):
        storage = _make_storage()
        eng = ConstitutionalDiffEngine(storage=storage)
        result = await eng.compute_text_diff("v1", "v2")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_unified_diff(self):
        v1 = _make_version("v1", "1.0", {"key": "old"}, "h")
        v2 = _make_version("v2", "2.0", {"key": "new"}, "h")
        storage = _make_storage({"v1": v1, "v2": v2})
        eng = ConstitutionalDiffEngine(storage=storage)

        result = await eng.compute_text_diff("v1", "v2")
        assert result is not None
        assert "---" in result or "++" in result or len(result) >= 0


# ---------------------------------------------------------------------------
# compute_multi_version_diff
# ---------------------------------------------------------------------------


class TestComputeMultiVersionDiff:
    @pytest.mark.asyncio
    async def test_fewer_than_2_versions(self):
        storage = _make_storage()
        eng = ConstitutionalDiffEngine(storage=storage)
        result = await eng.compute_multi_version_diff(["v1"])
        assert result is None

    @pytest.mark.asyncio
    async def test_multi_version_accumulates(self):
        v1 = _make_version("v1", "1.0", {"a": 1}, "h1")
        v2 = _make_version("v2", "2.0", {"a": 2, "b": 1}, "h2")
        v3 = _make_version("v3", "3.0", {"a": 2, "b": 2, "c": 1}, "h3")
        storage = _make_storage({"v1": v1, "v2": v2, "v3": v3})
        eng = ConstitutionalDiffEngine(storage=storage)

        result = await eng.compute_multi_version_diff(["v1", "v2", "v3"])
        assert result is not None
        assert result["version_count"] == 3
        assert result["total_changes"] > 0
        assert len(result["versions"]) == 2  # 2 pairwise diffs
