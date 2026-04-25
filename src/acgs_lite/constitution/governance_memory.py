"""Unified governance memory retrieval over rules and precedents."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .experience_library import GovernanceExperienceLibrary, GovernancePrecedent
from .semantic_search import EmbeddingProvider, SearchResult, SemanticRuleSearch


@dataclass(frozen=True, slots=True)
class GovernanceMemoryPrecedentHit:
    """A precedent retrieved from the governance experience library."""

    precedent_id: str
    score: float
    action: str
    decision: str
    category: str
    severity: str
    triggered_rules: list[str] = field(default_factory=list)
    rationale: str = ""
    timestamp: str = ""


@dataclass(frozen=True, slots=True)
class GovernanceMemorySummary:
    """Retrieval coverage and hit-count metadata."""

    total_rules: int
    rules_with_embeddings: int
    rule_embedding_coverage: float
    rule_hit_count: int
    total_precedents: int
    precedents_with_embeddings: int
    precedent_embedding_coverage: float
    precedent_hit_count: int


@dataclass(frozen=True, slots=True)
class GovernanceMemoryReport:
    """Structured governance memory retrieval result."""

    query: str
    rule_hits: list[SearchResult]
    precedent_hits: list[GovernanceMemoryPrecedentHit]
    summary: GovernanceMemorySummary


class GovernanceMemoryRetriever:
    """Fuse constitutional semantic search with precedent retrieval."""

    def __init__(
        self,
        constitution: Any,
        *,
        experience_library: GovernanceExperienceLibrary | None = None,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self._constitution = constitution
        self._experience_library = experience_library
        self._embedding_provider = embedding_provider

    def retrieve(
        self,
        query: str,
        *,
        top_k_rules: int = 5,
        top_k_precedents: int = 5,
        min_rule_similarity: float = 0.0,
        min_precedent_similarity: float = 0.3,
        category: str = "",
        tags: list[str] | None = None,
        decision_filter: str = "",
    ) -> GovernanceMemoryReport:
        """Retrieve semantically relevant rules and precedents for a query."""
        rule_search = SemanticRuleSearch(self._constitution, provider=self._embedding_provider)
        rule_report = rule_search.find_relevant(
            query,
            top_k=top_k_rules,
            min_similarity=min_rule_similarity,
            category=category,
            tags=tags,
        )

        total_precedents = 0
        precedents_with_embeddings = 0
        precedent_embedding_coverage = 0.0
        precedent_hits: list[GovernanceMemoryPrecedentHit] = []

        if self._experience_library is not None:
            stats = self._experience_library.stats()
            total_precedents = int(stats["total_precedents"])
            precedents_with_embeddings = int(stats["embedded_count"])
            precedent_embedding_coverage = float(stats["embedding_coverage"])

            query_embedding = self._embed_query(query)
            if query_embedding:
                precedent_hits = self._retrieve_precedents(
                    query_embedding,
                    top_k=top_k_precedents,
                    min_similarity=min_precedent_similarity,
                    category=category,
                    decision_filter=decision_filter,
                )

        return GovernanceMemoryReport(
            query=query,
            rule_hits=rule_report.results,
            precedent_hits=precedent_hits,
            summary=GovernanceMemorySummary(
                total_rules=rule_report.total_rules_searched,
                rules_with_embeddings=rule_report.rules_with_embeddings,
                rule_embedding_coverage=rule_search.coverage,
                rule_hit_count=len(rule_report.results),
                total_precedents=total_precedents,
                precedents_with_embeddings=precedents_with_embeddings,
                precedent_embedding_coverage=precedent_embedding_coverage,
                precedent_hit_count=len(precedent_hits),
            ),
        )

    def _embed_query(self, query: str) -> list[float]:
        if self._embedding_provider is None:
            return []
        embeddings = self._embedding_provider.embed([query])
        if not embeddings:
            return []
        return list(embeddings[0])

    def _retrieve_precedents(
        self,
        query_embedding: list[float],
        *,
        top_k: int,
        min_similarity: float,
        category: str,
        decision_filter: str,
    ) -> list[GovernanceMemoryPrecedentHit]:
        if self._experience_library is None:
            return []

        candidate_limit = max(top_k, len(self._experience_library.precedents))
        similar = self._experience_library.find_similar(
            query_embedding,
            top_k=candidate_limit,
            min_similarity=min_similarity,
            decision_filter=decision_filter,
        )
        if category:
            similar = [
                (precedent, score) for precedent, score in similar if precedent.category == category
            ]

        return [self._make_precedent_hit(precedent, score) for precedent, score in similar[:top_k]]

    @staticmethod
    def _make_precedent_hit(
        precedent: GovernancePrecedent,
        score: float,
    ) -> GovernanceMemoryPrecedentHit:
        return GovernanceMemoryPrecedentHit(
            precedent_id=precedent.id,
            score=score,
            action=precedent.action,
            decision=precedent.decision,
            category=precedent.category,
            severity=precedent.severity,
            triggered_rules=list(precedent.triggered_rules),
            rationale=precedent.rationale,
            timestamp=precedent.timestamp,
        )
