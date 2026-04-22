"""Tests for unified governance memory retrieval."""

from __future__ import annotations

from acgs_lite.constitution.experience_library import GovernanceExperienceLibrary
from acgs_lite.constitution.governance_memory import (
    GovernanceMemoryReport,
    GovernanceMemoryRetriever,
)
from acgs_lite.constitution.rule import Rule, Severity


def _make_rule(
    rule_id: str,
    text: str,
    *,
    embedding: list[float] | None = None,
    category: str = "general",
    severity: Severity = Severity.HIGH,
    tags: list[str] | None = None,
    enabled: bool = True,
) -> Rule:
    return Rule(
        id=rule_id,
        text=text,
        severity=severity,
        keywords=[word for word in text.lower().split()[:3]],
        category=category,
        tags=tags or [],
        embedding=embedding or [],
        enabled=enabled,
    )


def _make_constitution(rules: list[Rule]):
    class FakeConstitution:
        def __init__(self, rules: list[Rule]):
            self.rules = rules

        def model_copy(self, *, update: dict):
            return FakeConstitution(update.get("rules", self.rules))

    return FakeConstitution(rules)


class _StubEmbeddingProvider:
    def __init__(self, embedding: list[float]) -> None:
        self._embedding = embedding

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [list(self._embedding) for _ in texts]


def test_retrieve_without_embeddings_or_precedents_returns_empty_sections():
    constitution = _make_constitution(
        [
            _make_rule("GEN-001", "Log governance decisions"),
            _make_rule("GEN-002", "Escalate risky actions"),
        ]
    )

    report = GovernanceMemoryRetriever(constitution).retrieve("review this action")

    assert isinstance(report, GovernanceMemoryReport)
    assert report.rule_hits == []
    assert report.precedent_hits == []
    assert report.summary.total_rules == 2
    assert report.summary.rules_with_embeddings == 0
    assert report.summary.total_precedents == 0
    assert report.summary.precedents_with_embeddings == 0


def test_retrieve_includes_semantic_rule_hits():
    constitution = _make_constitution(
        [
            _make_rule(
                "PRIV-001",
                "Protect personal data",
                embedding=[1.0, 0.0],
                category="privacy",
            ),
            _make_rule(
                "SEC-001",
                "Rotate service credentials",
                embedding=[0.0, 1.0],
                category="security",
            ),
        ]
    )
    provider = _StubEmbeddingProvider([0.95, 0.05])

    report = GovernanceMemoryRetriever(
        constitution,
        embedding_provider=provider,
    ).retrieve("handle customer data", top_k_rules=2)

    assert [hit.rule_id for hit in report.rule_hits] == ["PRIV-001", "SEC-001"]
    assert report.rule_hits[0].score >= report.rule_hits[1].score
    assert report.summary.rule_hit_count == 2


def test_retrieve_includes_precedent_hits():
    constitution = _make_constitution(
        [
            _make_rule("PRIV-001", "Protect personal data", embedding=[1.0, 0.0]),
        ]
    )
    library = GovernanceExperienceLibrary()
    library.record(
        "share patient records with vendor",
        "deny",
        triggered_rules=["PRIV-001"],
        category="privacy",
        severity="high",
        rationale="Protected health information cannot be shared externally",
        embedding=[1.0, 0.0],
    )
    library.record(
        "rotate service credentials",
        "allow",
        triggered_rules=["SEC-001"],
        category="security",
        severity="medium",
        rationale="Routine maintenance",
        embedding=[0.0, 1.0],
    )
    provider = _StubEmbeddingProvider([0.98, 0.02])

    report = GovernanceMemoryRetriever(
        constitution,
        experience_library=library,
        embedding_provider=provider,
    ).retrieve("email patient records", top_k_precedents=2)

    assert [hit.precedent_id for hit in report.precedent_hits] == ["P0"]
    assert report.precedent_hits[0].decision == "deny"
    assert report.summary.precedent_hit_count == 1


def test_retrieve_applies_category_and_tags_filters_when_available():
    constitution = _make_constitution(
        [
            _make_rule(
                "PRIV-001",
                "Protect customer personal data",
                embedding=[1.0, 0.0],
                category="privacy",
                tags=["gdpr", "pii"],
            ),
            _make_rule(
                "PRIV-002",
                "Encrypt regulated records",
                embedding=[0.9, 0.1],
                category="privacy",
                tags=["hipaa"],
            ),
            _make_rule(
                "SEC-001",
                "Rotate service credentials",
                embedding=[0.0, 1.0],
                category="security",
                tags=["secrets"],
            ),
        ]
    )
    library = GovernanceExperienceLibrary()
    library.record(
        "share patient records",
        "deny",
        category="privacy",
        severity="high",
        embedding=[1.0, 0.0],
    )
    library.record(
        "rotate service credentials",
        "allow",
        category="security",
        severity="medium",
        embedding=[0.0, 1.0],
    )
    provider = _StubEmbeddingProvider([0.97, 0.03])

    report = GovernanceMemoryRetriever(
        constitution,
        experience_library=library,
        embedding_provider=provider,
    ).retrieve("customer records", category="privacy", tags=["gdpr"])

    assert [hit.rule_id for hit in report.rule_hits] == ["PRIV-001"]
    assert [hit.precedent_id for hit in report.precedent_hits] == ["P0"]


def test_retrieve_summary_metadata_reports_counts_and_coverage():
    constitution = _make_constitution(
        [
            _make_rule("PRIV-001", "Protect personal data", embedding=[1.0, 0.0]),
            _make_rule("GEN-001", "Log decisions"),
        ]
    )
    library = GovernanceExperienceLibrary()
    library.record(
        "share patient records",
        "deny",
        category="privacy",
        severity="high",
        embedding=[1.0, 0.0],
    )
    library.record(
        "log decision outcome",
        "allow",
        category="general",
        severity="low",
    )
    provider = _StubEmbeddingProvider([1.0, 0.0])

    report = GovernanceMemoryRetriever(
        constitution,
        experience_library=library,
        embedding_provider=provider,
    ).retrieve("patient data")

    assert report.summary.total_rules == 2
    assert report.summary.rules_with_embeddings == 1
    assert report.summary.rule_embedding_coverage == 0.5
    assert report.summary.total_precedents == 2
    assert report.summary.precedents_with_embeddings == 1
    assert report.summary.precedent_embedding_coverage == 0.5
    assert report.summary.rule_hit_count == 1
    assert report.summary.precedent_hit_count == 1
