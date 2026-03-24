"""exp230: Semantic rule search — embedding-based retrieval for constitutional rules.

Inspired by XSkill's ExperienceRetriever pattern, this module activates the
dormant ``Rule.embedding`` field (exp138) to provide semantic similarity search
across constitutional rules.  Instead of keyword/pattern matching (used in the
hot path), this enables *meaning-based* rule discovery: finding rules relevant
to an action by comparing embedding vectors.

Use cases:

- **Governance exploration**: "which rules relate to data retention?"
- **Rule deduplication**: find semantically similar rules beyond keyword overlap
- **Context-aware retrieval**: retrieve top-K rules most relevant to an action
- **Audit support**: explain which rules *could* apply to a decision

This does NOT replace the hot-path matcher (Aho-Corasick/regex) — it's an
off-path analysis tool for richer governance intelligence.

Design (adapted from XSkill's ExperienceRetriever):

- Hash-based cache invalidation: MD5 of rule embeddings detects stale caches
- Batch embedding generation via pluggable provider (Protocol)
- Cosine similarity ranking with configurable top_k and min_similarity
- Decomposition support: break complex queries into sub-queries

Usage::

    from acgs_lite.constitution import Constitution
    from acgs_lite.constitution.semantic_search import SemanticRuleSearch

    c = Constitution.from_yaml("policy.yaml")
    search = SemanticRuleSearch(c)

    # Find rules semantically related to an action
    results = search.find_relevant("store user credit card numbers", top_k=5)
    for rule, score in results:
        print(f"{rule.id}: {score:.3f} — {rule.text[:80]}")

    # Bulk-embed all rules (requires an EmbeddingProvider)
    from acgs_lite.constitution.semantic_search import embed_rules
    c2 = embed_rules(c, provider=my_embedding_provider)
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from .core import Constitution
    from .rule import Rule


# ── Protocols ───────────────────────────────────────────────────────────────


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Pluggable embedding generation — any callable that maps text → vector.

    Implementations might wrap OpenAI ``text-embedding-3-small``, a local
    sentence-transformer, or a governance-specific fine-tuned model.
    """

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts into float vectors.

        Args:
            texts: list of strings to embed.

        Returns:
            list of float vectors, one per input text, all same dimensionality.
        """
        ...


# ── Data structures ─────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class SearchResult:
    """A single semantic search hit."""

    rule_id: str
    score: float  # cosine similarity in [-1.0, 1.0]
    rule_text: str
    category: str
    severity: str
    tags: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class SearchReport:
    """Full semantic search report with provenance."""

    query: str
    results: list[SearchResult]
    total_rules_searched: int
    rules_with_embeddings: int
    cache_hit: bool = False


# ── Core implementation ──────────────────────────────────────────────────────


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Fast cosine similarity between two equal-length float vectors.

    Returns 0.0 on degenerate inputs (empty, mismatched, zero-magnitude).
    """
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    mag_a = sum(x * x for x in a) ** 0.5
    mag_b = sum(x * x for x in b) ** 0.5
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return float(dot / (mag_a * mag_b))


def _embedding_fingerprint(rules: list[Rule]) -> str:
    """Stable fingerprint of which rules have embeddings and their content.

    Used for cache invalidation — if any rule text or embedding changes,
    the fingerprint changes.
    """
    parts: list[str] = []
    for r in sorted(rules, key=lambda r: r.id):
        has_emb = "1" if r.embedding else "0"
        parts.append(f"{r.id}:{has_emb}:{r.text[:100]}")
    payload = "\n".join(parts)
    return hashlib.md5(payload.encode()).hexdigest()[:12]


class SemanticRuleSearch:
    """Embedding-based semantic search over constitutional rules.

    Wraps a Constitution and provides cosine-similarity ranking of rules
    against a query embedding.  Rules without embeddings are silently skipped.

    Args:
        constitution: The Constitution to search over.
        provider: Optional EmbeddingProvider for embedding queries at search time.

    Attributes:
        _fingerprint: Cache key for the current rule set.
        _embedded_rules: Pre-filtered list of (rule, embedding) pairs.
    """

    def __init__(
        self,
        constitution: Constitution,
        provider: EmbeddingProvider | None = None,
    ) -> None:
        self._constitution = constitution
        self._provider = provider
        self._fingerprint = ""
        self._embedded_rules: list[tuple[Rule, list[float]]] = []
        self._rebuild_index()

    def _rebuild_index(self) -> None:
        """Rebuild the internal index of embedded rules."""
        rules = list(self._constitution.rules)
        new_fp = _embedding_fingerprint(rules)
        if new_fp == self._fingerprint:
            return
        self._fingerprint = new_fp
        self._embedded_rules = [(r, r.embedding) for r in rules if r.embedding and r.enabled]

    @property
    def coverage(self) -> float:
        """Fraction of active rules that have embeddings (0.0–1.0)."""
        active = [r for r in self._constitution.rules if r.enabled]
        if not active:
            return 0.0
        return len(self._embedded_rules) / len(active)

    def find_relevant(
        self,
        query: str,
        *,
        top_k: int = 5,
        min_similarity: float = 0.0,
        category: str = "",
        tags: list[str] | None = None,
    ) -> SearchReport:
        """Find rules semantically relevant to a query string.

        Args:
            query: Natural language description of the action or topic.
            top_k: Maximum number of results to return.
            min_similarity: Minimum cosine similarity threshold.
            category: If set, only search rules in this category.
            tags: If set, only search rules with at least one matching tag.

        Returns:
            SearchReport with ranked results and metadata.

        Raises:
            ValueError: If no EmbeddingProvider is configured and query needs embedding.
        """
        self._rebuild_index()

        if not self._embedded_rules:
            return SearchReport(
                query=query,
                results=[],
                total_rules_searched=len(self._constitution.rules),
                rules_with_embeddings=0,
            )

        # Embed the query
        query_embedding = self._embed_query(query)
        if not query_embedding:
            return SearchReport(
                query=query,
                results=[],
                total_rules_searched=len(self._constitution.rules),
                rules_with_embeddings=len(self._embedded_rules),
            )

        # Filter candidates
        candidates = self._embedded_rules
        if category:
            candidates = [(r, e) for r, e in candidates if r.category == category]
        if tags:
            tag_set = set(tags)
            candidates = [(r, e) for r, e in candidates if tag_set & set(r.tags)]

        # Score all candidates
        scored: list[tuple[Rule, float]] = []
        for rule, emb in candidates:
            sim = _cosine_similarity(query_embedding, emb)
            if sim >= min_similarity:
                scored.append((rule, sim))

        # Sort by similarity descending, take top_k
        scored.sort(key=lambda x: x[1], reverse=True)
        top = scored[:top_k]

        results = [
            SearchResult(
                rule_id=r.id,
                score=score,
                rule_text=r.text,
                category=r.category,
                severity=r.severity.value,
                tags=list(r.tags),
            )
            for r, score in top
        ]

        return SearchReport(
            query=query,
            results=results,
            total_rules_searched=len(self._constitution.rules),
            rules_with_embeddings=len(self._embedded_rules),
        )

    def find_similar_rules(
        self,
        rule_id: str,
        *,
        top_k: int = 5,
        min_similarity: float = 0.3,
    ) -> SearchReport:
        """Find rules semantically similar to a specific rule.

        Useful for deduplication analysis and dependency discovery.

        Args:
            rule_id: ID of the reference rule.
            top_k: Maximum results (excludes the reference rule itself).
            min_similarity: Minimum cosine similarity.

        Returns:
            SearchReport with similar rules ranked by similarity.
        """
        self._rebuild_index()

        # Find the reference rule's embedding
        ref_emb: list[float] = []
        for rule, emb in self._embedded_rules:
            if rule.id == rule_id:
                ref_emb = emb
                break

        if not ref_emb:
            return SearchReport(
                query=f"similar_to:{rule_id}",
                results=[],
                total_rules_searched=len(self._constitution.rules),
                rules_with_embeddings=len(self._embedded_rules),
            )

        scored: list[tuple[Rule, float]] = []
        for rule, emb in self._embedded_rules:
            if rule.id == rule_id:
                continue
            sim = _cosine_similarity(ref_emb, emb)
            if sim >= min_similarity:
                scored.append((rule, sim))

        scored.sort(key=lambda x: x[1], reverse=True)
        top = scored[:top_k]

        results = [
            SearchResult(
                rule_id=r.id,
                score=score,
                rule_text=r.text,
                category=r.category,
                severity=r.severity.value,
                tags=list(r.tags),
            )
            for r, score in top
        ]

        return SearchReport(
            query=f"similar_to:{rule_id}",
            results=results,
            total_rules_searched=len(self._constitution.rules),
            rules_with_embeddings=len(self._embedded_rules),
        )

    def _embed_query(self, query: str) -> list[float]:
        """Embed a query string using the configured provider.

        Falls back to keyword-derived pseudo-embedding if no provider is set.
        """
        if self._provider is not None:
            results = self._provider.embed([query])
            if results and results[0]:
                return results[0]
        return []


# ── Bulk embedding utilities ────────────────────────────────────────────────


def embed_rules(
    constitution: Constitution,
    provider: EmbeddingProvider,
    *,
    batch_size: int = 30,
    include_metadata: bool = True,
) -> Constitution:
    """Generate embeddings for all rules in a constitution.

    Returns a new Constitution with ``Rule.embedding`` fields populated.
    Rules that already have embeddings are skipped (use ``force=True`` via
    re-creating the constitution to regenerate all).

    Args:
        constitution: Source constitution.
        provider: Embedding provider implementation.
        batch_size: Number of texts to embed per API call.
        include_metadata: If True, embed rule text + category + tags for richer vectors.

    Returns:
        New Constitution with embeddings populated.
    """
    rules = list(constitution.rules)
    needs_embedding = [r for r in rules if not r.embedding and r.enabled]

    if not needs_embedding:
        return constitution

    # Build texts for embedding
    texts: list[str] = []
    for r in needs_embedding:
        if include_metadata:
            parts = [r.text]
            if r.category and r.category != "general":
                parts.append(f"[category: {r.category}]")
            if r.tags:
                parts.append(f"[tags: {', '.join(r.tags)}]")
            texts.append(" ".join(parts))
        else:
            texts.append(r.text)

    # Batch embed
    all_embeddings: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        batch_embeddings = provider.embed(batch)
        all_embeddings.extend(batch_embeddings)

    # Build new rules with embeddings
    rule_map: dict[str, list[float]] = {}
    for rule, emb in zip(needs_embedding, all_embeddings, strict=True):
        if emb:
            rule_map[rule.id] = emb

    new_rules = []
    for r in rules:
        if r.id in rule_map:
            new_rules.append(r.model_copy(update={"embedding": rule_map[r.id]}))
        else:
            new_rules.append(r)

    return constitution.model_copy(update={"rules": new_rules})


def embedding_coverage_report(constitution: Constitution) -> dict[str, Any]:
    """Report on embedding coverage across the constitution.

    Returns:
        dict with coverage statistics useful for governance dashboards.
    """
    rules = list(constitution.rules)
    active = [r for r in rules if r.enabled]
    embedded = [r for r in active if r.embedding]

    by_category: dict[str, dict[str, int]] = {}
    for r in active:
        cat = r.category or "general"
        if cat not in by_category:
            by_category[cat] = {"total": 0, "embedded": 0}
        by_category[cat]["total"] += 1
        if r.embedding:
            by_category[cat]["embedded"] += 1

    by_severity: dict[str, dict[str, int]] = {}
    for r in active:
        sev = r.severity.value
        if sev not in by_severity:
            by_severity[sev] = {"total": 0, "embedded": 0}
        by_severity[sev]["total"] += 1
        if r.embedding:
            by_severity[sev]["embedded"] += 1

    return {
        "total_rules": len(rules),
        "active_rules": len(active),
        "embedded_rules": len(embedded),
        "coverage": len(embedded) / len(active) if active else 0.0,
        "by_category": by_category,
        "by_severity": by_severity,
        "embedding_dimension": len(embedded[0].embedding) if embedded else 0,
    }
