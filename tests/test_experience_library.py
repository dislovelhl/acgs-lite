"""Tests for exp231: Governance experience library — precedent accumulation."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from acgs_lite.constitution.experience_library import (
    GovernanceExperienceLibrary,
    GovernancePrecedent,
    _action_fingerprint,
    _cosine_sim,
)

# ── Unit: GovernancePrecedent ────────────────────────────────────────────────


class TestGovernancePrecedent:
    def test_creation(self):
        p = GovernancePrecedent(
            id="P0",
            action="access patient records",
            decision="deny",
            triggered_rules=["PRIV-001"],
            rationale="PII access restricted",
        )
        assert p.id == "P0"
        assert p.decision == "deny"
        assert p.triggered_rules == ["PRIV-001"]

    def test_to_dict(self):
        p = GovernancePrecedent(
            id="P0",
            action="test action",
            decision="allow",
            context={"env": "dev"},
        )
        d = p.to_dict()
        assert d["id"] == "P0"
        assert d["action"] == "test action"
        assert d["context"] == {"env": "dev"}
        # Embeddings excluded from serialization
        assert "embedding" not in d

    def test_from_dict(self):
        data = {
            "id": "P5",
            "action": "deploy to production",
            "decision": "escalate",
            "triggered_rules": ["SEC-001", "SEC-002"],
            "context": {"env": "production"},
            "rationale": "High-risk deployment",
            "category": "security",
            "severity": "critical",
        }
        p = GovernancePrecedent.from_dict(data)
        assert p.id == "P5"
        assert p.decision == "escalate"
        assert p.triggered_rules == ["SEC-001", "SEC-002"]
        assert p.severity == "critical"

    def test_from_dict_defaults(self):
        p = GovernancePrecedent.from_dict({})
        assert p.id == "P0"
        assert p.action == ""
        assert p.decision == "unknown"

    def test_frozen(self):
        import pytest

        p = GovernancePrecedent(id="P0", action="test", decision="allow")
        with pytest.raises(AttributeError):
            p.action = "mutated"  # type: ignore[misc]

    def test_roundtrip(self):
        original = GovernancePrecedent(
            id="P0",
            action="store credit card",
            decision="deny",
            triggered_rules=["PCI-001"],
            context={"env": "prod", "user": "agent-7"},
            rationale="PCI-DSS violation",
            category="security",
            severity="critical",
        )
        restored = GovernancePrecedent.from_dict(original.to_dict())
        assert restored.action == original.action
        assert restored.decision == original.decision
        assert restored.triggered_rules == original.triggered_rules
        assert restored.context == original.context


# ── Unit: fingerprint ────────────────────────────────────────────────────────


class TestActionFingerprint:
    def test_stable(self):
        fp1 = _action_fingerprint("test action", {"env": "prod"})
        fp2 = _action_fingerprint("test action", {"env": "prod"})
        assert fp1 == fp2

    def test_case_insensitive(self):
        fp1 = _action_fingerprint("Test Action", {})
        fp2 = _action_fingerprint("test action", {})
        assert fp1 == fp2

    def test_context_order_independent(self):
        fp1 = _action_fingerprint("test", {"a": 1, "b": 2})
        fp2 = _action_fingerprint("test", {"b": 2, "a": 1})
        assert fp1 == fp2

    def test_different_actions(self):
        fp1 = _action_fingerprint("action one", {})
        fp2 = _action_fingerprint("action two", {})
        assert fp1 != fp2


# ── Unit: cosine similarity ──────────────────────────────────────────────────


class TestCosineSimHelper:
    def test_identical(self):
        assert _cosine_sim([1.0, 0.0], [1.0, 0.0]) == 1.0

    def test_orthogonal(self):
        assert _cosine_sim([1.0, 0.0], [0.0, 1.0]) == 0.0

    def test_empty(self):
        assert _cosine_sim([], [1.0]) == 0.0

    def test_zero_magnitude(self):
        assert _cosine_sim([0.0, 0.0], [1.0, 1.0]) == 0.0


# ── Integration: GovernanceExperienceLibrary ─────────────────────────────────


class TestLibraryBasics:
    def test_empty_library(self):
        lib = GovernanceExperienceLibrary()
        assert len(lib) == 0
        assert lib.precedents == []

    def test_record_precedent(self):
        lib = GovernanceExperienceLibrary()
        p = lib.record("access database", "allow", triggered_rules=["GEN-001"])
        assert p is not None
        assert p.id == "P0"
        assert p.action == "access database"
        assert p.decision == "allow"
        assert len(lib) == 1

    def test_record_multiple(self):
        lib = GovernanceExperienceLibrary()
        lib.record("action one", "allow")
        lib.record("action two", "deny")
        lib.record("action three", "warn")
        assert len(lib) == 3

    def test_auto_increment_ids(self):
        lib = GovernanceExperienceLibrary()
        p1 = lib.record("action 1", "allow")
        p2 = lib.record("action 2", "deny")
        assert p1.id == "P0"
        assert p2.id == "P1"

    def test_timestamp_populated(self):
        lib = GovernanceExperienceLibrary()
        p = lib.record("test", "allow")
        assert p.timestamp  # non-empty ISO string


class TestDeduplication:
    def test_deduplicates_identical(self):
        lib = GovernanceExperienceLibrary()
        p1 = lib.record("same action", "allow", context={"env": "prod"})
        p2 = lib.record("same action", "allow", context={"env": "prod"})
        assert p1 is not None
        assert p2 is None  # deduplicated
        assert len(lib) == 1

    def test_case_insensitive_dedup(self):
        lib = GovernanceExperienceLibrary()
        lib.record("Test Action", "allow")
        p2 = lib.record("test action", "allow")
        assert p2 is None  # same after lowercasing

    def test_different_context_not_deduped(self):
        lib = GovernanceExperienceLibrary()
        lib.record("same action", "allow", context={"env": "dev"})
        p2 = lib.record("same action", "allow", context={"env": "prod"})
        assert p2 is not None  # different context
        assert len(lib) == 2


class TestEviction:
    def test_evicts_oldest(self):
        lib = GovernanceExperienceLibrary(maxsize=3)
        lib.record("action 1", "allow")
        lib.record("action 2", "allow")
        lib.record("action 3", "allow")
        lib.record("action 4", "allow")  # should evict P0

        assert len(lib) == 3
        precedent_ids = [p.id for p in lib.precedents]
        assert "P0" not in precedent_ids
        assert "P3" in precedent_ids


class TestKeywordSearch:
    def test_basic_search(self):
        lib = GovernanceExperienceLibrary()
        lib.record("access patient medical records", "deny")
        lib.record("deploy application to staging", "allow")
        lib.record("query patient billing data", "warn")

        results = lib.find_by_keyword("patient")
        assert len(results) == 2
        actions = [r.action for r in results]
        assert "access patient medical records" in actions
        assert "query patient billing data" in actions

    def test_multi_term_search(self):
        lib = GovernanceExperienceLibrary()
        lib.record("access patient medical records", "deny")
        lib.record("access system logs", "allow")

        results = lib.find_by_keyword("access patient")
        assert len(results) == 1
        assert results[0].action == "access patient medical records"

    def test_decision_filter(self):
        lib = GovernanceExperienceLibrary()
        lib.record("action one", "allow")
        lib.record("action two", "deny")
        lib.record("action three", "allow")

        results = lib.find_by_keyword("action", decision_filter="deny")
        assert len(results) == 1
        assert results[0].decision == "deny"

    def test_top_k_limit(self):
        lib = GovernanceExperienceLibrary()
        for i in range(10):
            lib.record(f"test action {i}", "allow")

        results = lib.find_by_keyword("test", top_k=3)
        assert len(results) == 3

    def test_empty_query(self):
        lib = GovernanceExperienceLibrary()
        lib.record("test", "allow")
        assert lib.find_by_keyword("") == []

    def test_no_matches(self):
        lib = GovernanceExperienceLibrary()
        lib.record("test action", "allow")
        assert lib.find_by_keyword("nonexistent") == []


class TestSimilaritySearch:
    def test_basic_similarity(self):
        lib = GovernanceExperienceLibrary()
        lib.record("data privacy", "deny", embedding=[0.9, 0.1, 0.0])
        lib.record("data security", "deny", embedding=[0.8, 0.2, 0.0])
        lib.record("system logging", "allow", embedding=[0.0, 0.1, 0.9])

        # Query similar to privacy/security
        results = lib.find_similar([0.85, 0.15, 0.0], top_k=2)
        assert len(results) == 2
        # First should be most similar
        assert results[0][1] >= results[1][1]

    def test_min_similarity_threshold(self):
        lib = GovernanceExperienceLibrary()
        lib.record("a", "allow", embedding=[1.0, 0.0])
        lib.record("b", "allow", embedding=[0.0, 1.0])  # orthogonal

        results = lib.find_similar([1.0, 0.0], min_similarity=0.5)
        assert len(results) == 1  # only the similar one

    def test_decision_filter(self):
        lib = GovernanceExperienceLibrary()
        lib.record("a", "allow", embedding=[0.9, 0.1])
        lib.record("b", "deny", embedding=[0.85, 0.15])

        results = lib.find_similar([0.9, 0.1], decision_filter="deny")
        assert len(results) == 1
        assert results[0][0].decision == "deny"

    def test_empty_query_embedding(self):
        lib = GovernanceExperienceLibrary()
        lib.record("a", "allow", embedding=[1.0])
        assert lib.find_similar([]) == []

    def test_skips_unembedded_precedents(self):
        lib = GovernanceExperienceLibrary()
        lib.record("with embedding", "allow", embedding=[1.0, 0.0])
        lib.record("without embedding", "allow")  # no embedding

        results = lib.find_similar([1.0, 0.0])
        assert len(results) == 1


class TestConsistencyCheck:
    def test_detects_inconsistency(self):
        lib = GovernanceExperienceLibrary()
        lib.record("access user data", "allow", embedding=[0.9, 0.1])
        lib.record("access user info", "deny", embedding=[0.88, 0.12])

        issues = lib.consistency_check(similarity_threshold=0.9)
        assert len(issues) >= 1
        assert issues[0]["decision_a"] != issues[0]["decision_b"]
        assert issues[0]["similarity"] >= 0.9

    def test_no_inconsistency_same_decisions(self):
        lib = GovernanceExperienceLibrary()
        lib.record("access data", "deny", embedding=[0.9, 0.1])
        lib.record("access info", "deny", embedding=[0.88, 0.12])

        issues = lib.consistency_check(similarity_threshold=0.9)
        assert issues == []  # same decisions = consistent

    def test_no_inconsistency_dissimilar_actions(self):
        lib = GovernanceExperienceLibrary()
        lib.record("access data", "allow", embedding=[1.0, 0.0])
        lib.record("deploy code", "deny", embedding=[0.0, 1.0])

        issues = lib.consistency_check(similarity_threshold=0.9)
        assert issues == []  # dissimilar actions, different decisions is fine


class TestStats:
    def test_stats_empty(self):
        lib = GovernanceExperienceLibrary()
        s = lib.stats()
        assert s["total_precedents"] == 0
        assert s["embedding_coverage"] == 0.0

    def test_stats_populated(self):
        lib = GovernanceExperienceLibrary()
        lib.record("a", "allow", category="privacy", embedding=[1.0])
        lib.record("b", "deny", category="security")
        lib.record("c", "allow", category="privacy")

        s = lib.stats()
        assert s["total_precedents"] == 3
        assert s["by_decision"]["allow"] == 2
        assert s["by_decision"]["deny"] == 1
        assert s["by_category"]["privacy"] == 2
        assert s["embedded_count"] == 1


# ── Integration: persistence ─────────────────────────────────────────────────


class TestPersistence:
    def test_save_and_load(self):
        lib = GovernanceExperienceLibrary()
        lib.record(
            "access records",
            "deny",
            triggered_rules=["PRIV-001"],
            context={"env": "prod"},
            rationale="PII restricted",
            category="privacy",
            severity="high",
        )
        lib.record("deploy app", "allow", category="general")

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        try:
            lib.save(path)

            # Verify JSON structure
            data = json.loads(Path(path).read_text())
            assert data["version"] == 1
            assert len(data["precedents"]) == 2

            # Load and verify
            lib2 = GovernanceExperienceLibrary.load(path)
            assert len(lib2) == 2

            precedents = lib2.precedents
            assert precedents[0].action == "deploy app"  # newest first
            assert precedents[1].action == "access records"
            assert precedents[1].triggered_rules == ["PRIV-001"]
            assert precedents[1].context == {"env": "prod"}
        finally:
            Path(path).unlink(missing_ok=True)

    def test_load_preserves_dedup(self):
        lib = GovernanceExperienceLibrary()
        lib.record("test action", "allow")

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        try:
            lib.save(path)
            lib2 = GovernanceExperienceLibrary.load(path)

            # Should deduplicate after loading
            p = lib2.record("test action", "allow")
            assert p is None  # already exists
        finally:
            Path(path).unlink(missing_ok=True)

    def test_id_continuity_after_load(self):
        lib = GovernanceExperienceLibrary()
        lib.record("a", "allow")
        lib.record("b", "deny")

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        try:
            lib.save(path)
            lib2 = GovernanceExperienceLibrary.load(path)

            p = lib2.record("c", "warn")
            assert p is not None
            assert p.id == "P2"  # continues from P0, P1
        finally:
            Path(path).unlink(missing_ok=True)
