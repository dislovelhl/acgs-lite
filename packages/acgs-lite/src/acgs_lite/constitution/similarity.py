"""Similarity and dead-rule detection helpers for constitutions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .rule import _cosine_sim

if TYPE_CHECKING:
    from .constitution import Constitution


def find_similar_rules(
    constitution: Constitution,
    *,
    threshold: float = 0.7,
    include_disabled: bool = False,
) -> list[dict[str, Any]]:
    """exp136: Find pairs of rules with high keyword overlap (near-duplicates).

    Uses Jaccard similarity on lowercased keyword sets.  High-similarity
    pairs may indicate redundant rules that could be consolidated, or
    conflicting rules that cover the same scenarios with different actions.

    A similarity of 1.0 means the two rules share *all* keywords
    (identical detection surface).  A similarity >= 0.7 typically indicates
    the rules overlap significantly and should be reviewed.

    Args:
        constitution: The constitution instance to analyse.
        threshold: Minimum Jaccard similarity to include a pair (0.0-1.0).
            Default 0.7.
        include_disabled: If True, include disabled rules in the analysis.
            Default False (only active rules).

    Returns:
        List of similarity records, each a dict with:

        - ``rule_a``: ID of first rule
        - ``rule_b``: ID of second rule
        - ``similarity``: Jaccard coefficient (0.0-1.0)
        - ``shared_keywords``: sorted list of shared lowercased keywords
        - ``severity_match``: True if both rules have the same severity
        - ``category_match``: True if both rules are in the same category
        - ``recommendation``: "consolidate" if severity+category both match,
          else "review"

    Sorted by similarity descending.

    Example::

        pairs = find_similar_rules(constitution, threshold=0.8)
        for pair in pairs:
            print(f"{pair['rule_a']} <-> {pair['rule_b']}: {pair['similarity']:.2f}")
    """
    candidates = constitution.rules if include_disabled else constitution.active_rules()

    # Only consider rules with at least one keyword
    keyed = [
        (r, frozenset(kw.lower() for kw in r.keywords)) for r in candidates if r.keywords
    ]

    results: list[dict[str, Any]] = []
    n = len(keyed)
    for i in range(n):
        rule_a, kws_a = keyed[i]
        for j in range(i + 1, n):
            rule_b, kws_b = keyed[j]
            union = kws_a | kws_b
            if not union:
                continue
            intersection = kws_a & kws_b
            similarity = len(intersection) / len(union)
            if similarity < threshold:
                continue
            severity_match = rule_a.severity == rule_b.severity
            category_match = rule_a.category == rule_b.category
            recommendation = (
                "consolidate" if (severity_match and category_match) else "review"
            )
            results.append(
                {
                    "rule_a": rule_a.id,
                    "rule_b": rule_b.id,
                    "similarity": round(similarity, 4),
                    "shared_keywords": sorted(intersection),
                    "severity_match": severity_match,
                    "category_match": category_match,
                    "recommendation": recommendation,
                }
            )

    return results


def cosine_similar_rules(
    constitution: Constitution,
    threshold: float = 0.8,
    min_dim: int = 4,
) -> list[dict[str, Any]]:
    """exp138: Find similar rule pairs using cosine similarity on stored embeddings.

    When rules have :attr:`Rule.embedding` vectors set, uses cosine similarity for
    semantically-aware deduplication -- catching rules that are equivalent in meaning
    but differ in wording (false negatives in pure keyword matching).

    Falls back to Jaccard keyword overlap (like :func:`find_similar_rules`) for rules
    without embeddings.

    Args:
        constitution: The constitution instance to analyse.
        threshold: Minimum cosine similarity (or Jaccard for fallback) to include.
                   Typical values: 0.8-0.95 for semantic, 0.6-0.8 for keyword.
        min_dim:   Minimum embedding dimension required to use cosine path.

    Returns:
        List of dicts, each with keys:
        - ``rule_a``: First rule ID
        - ``rule_b``: Second rule ID
        - ``similarity``: Float similarity score (cosine or Jaccard)
        - ``method``: ``"cosine"`` or ``"jaccard"``
        - ``severity_match``: Whether both rules share the same severity
        - ``category_match``: Whether both rules share the same category
        - ``recommendation``: ``"consolidate"`` or ``"review"``

    Example::

        # After setting embeddings externally:
        for r in constitution.rules:
            r.embedding = my_embed_fn(r.text)  # pre-compute with external model
        pairs = cosine_similar_rules(constitution, threshold=0.85)
    """
    results: list[dict[str, Any]] = []
    rules = constitution.active_rules()

    for i, rule_a in enumerate(rules):
        for rule_b in rules[i + 1 :]:
            # --- cosine path: both rules have sufficient-dimension embeddings ---
            sim_cos = rule_a.cosine_similarity(rule_b)
            if sim_cos is not None and len(rule_a.embedding) >= min_dim:
                if sim_cos < threshold:
                    continue
                method = "cosine"
                similarity = round(sim_cos, 4)
            else:
                # --- fallback: Jaccard on keyword sets ---
                kw_a = set(k.lower() for k in rule_a.keywords)
                kw_b = set(k.lower() for k in rule_b.keywords)
                if not kw_a or not kw_b:
                    continue
                intersection = len(kw_a & kw_b)
                union = len(kw_a | kw_b)
                jaccard = intersection / union if union else 0.0
                if jaccard < threshold:
                    continue
                method = "jaccard"
                similarity = round(jaccard, 4)

            severity_match = rule_a.severity == rule_b.severity
            category_match = rule_a.category == rule_b.category
            rec = "consolidate" if (severity_match and category_match) else "review"
            results.append(
                {
                    "rule_a": rule_a.id,
                    "rule_b": rule_b.id,
                    "similarity": similarity,
                    "method": method,
                    "severity_match": severity_match,
                    "category_match": category_match,
                    "recommendation": rec,
                }
            )

    results.sort(key=lambda x: x["similarity"], reverse=True)
    return results


def semantic_search(
    constitution: Constitution,
    query_embedding: list[float],
    top_k: int = 5,
    threshold: float = 0.5,
) -> list[dict[str, Any]]:
    """exp138: Retrieve the most semantically relevant rules for a query embedding.

    Enables LLM-powered governance lookup: embed a natural-language query (e.g., an
    agent action description) and retrieve the most relevant rules without exact keyword
    overlap -- directly addressing false negative reduction.

    Args:
        constitution: The constitution instance to search.
        query_embedding: Pre-computed query vector (must match rule embedding dimension).
        top_k:           Maximum number of rules to return (default 5).
        threshold:       Minimum cosine similarity to include (default 0.5).

    Returns:
        List of dicts (up to *top_k*), sorted by similarity descending:
        - ``rule_id``: Rule ID
        - ``similarity``: Cosine similarity score [0, 1]
        - ``severity``: Rule severity string
        - ``category``: Rule category
        - ``text``: Rule text (for display/logging)

    Example::

        query_vec = embed_fn("agent is uploading private data to external endpoint")
        hits = semantic_search(constitution, query_vec, top_k=3, threshold=0.7)
        # -> [{"rule_id": "DATA-001", "similarity": 0.91, ...}, ...]
    """
    if not query_embedding:
        return []

    hits: list[dict[str, Any]] = []
    for rule in constitution.active_non_deprecated():
        sim = _cosine_sim(query_embedding, rule.embedding)
        if sim is None or sim < threshold:
            continue

        hits.append(
            {
                "rule_id": rule.id,
                "similarity": round(sim, 4),
                "severity": rule.severity.value
                if hasattr(rule.severity, "value")
                else str(rule.severity),
                "category": rule.category,
                "text": rule.text,
            }
        )

    hits.sort(key=lambda x: x["similarity"], reverse=True)
    return hits[:top_k]


def dead_rules(
    constitution: Constitution,
    corpus: list[str],
    *,
    include_deprecated: bool = False,
) -> dict[str, Any]:
    """exp168: Detect rules that never fire against a corpus of actions.

    Evaluates every active rule against every action in *corpus* and
    identifies rules with zero keyword or pattern matches. Dead rules add
    cognitive overhead to governance review without catching anything --
    they are candidates for removal or keyword tuning.

    Args:
        constitution: The constitution instance to analyse.
        corpus: List of action strings to evaluate rules against.
                A representative sample of real agent actions works best.
        include_deprecated: If True, also check deprecated rules.
                Defaults to False (check only active rules).

    Returns:
        dict with:
            - ``total_rules``: number of rules checked
            - ``dead_count``: number of rules that never fired
            - ``live_count``: number of rules that fired at least once
            - ``dead_rules``: list of dicts for rules with zero hits
                - ``rule_id``, ``text``, ``severity``, ``keywords``,
                  ``patterns``, ``recommendation``
            - ``live_rules``: list of dicts with hit counts
                - ``rule_id``, ``text``, ``hits``, ``coverage_pct``
            - ``corpus_size``: number of actions evaluated
            - ``coverage_pct``: fraction of rules that fired (0-1)

    Example::

        corpus = ["delete all records", "read user profile", "deploy to prod"]
        report = dead_rules(constitution, corpus)
        for r in report["dead_rules"]:
            print(f"{r['rule_id']}: never fires -- consider removing")
    """
    if include_deprecated:
        rules_to_check = list(constitution.rules)
    else:
        rules_to_check = [r for r in constitution.rules if not r.deprecated]

    # Count hits per rule
    hit_counts: dict[str, int] = {r.id: 0 for r in rules_to_check}
    for action in corpus:
        for rule in rules_to_check:
            if rule.matches(action):
                hit_counts[rule.id] += 1

    corpus_size = len(corpus)
    dead: list[dict[str, Any]] = []
    live: list[dict[str, Any]] = []

    for rule in rules_to_check:
        hits = hit_counts[rule.id]
        if hits == 0:
            dead.append(
                {
                    "rule_id": rule.id,
                    "text": rule.text[:120],
                    "severity": rule.severity.value
                    if hasattr(rule.severity, "value")
                    else str(rule.severity),
                    "keywords": list(rule.keywords),
                    "patterns": list(rule.patterns),
                    "recommendation": (
                        "Remove or broaden keywords — rule never matched any corpus action."
                        if rule.keywords or rule.patterns
                        else "Rule has no keywords or patterns — cannot match any action."
                    ),
                }
            )
        else:
            coverage_pct = (hits / corpus_size * 100) if corpus_size else 0.0
            live.append(
                {
                    "rule_id": rule.id,
                    "text": rule.text[:120],
                    "hits": hits,
                    "coverage_pct": round(coverage_pct, 2),
                }
            )

    total = len(rules_to_check)
    live_count = len(live)
    dead_count = len(dead)
    coverage = live_count / total if total else 1.0

    return {
        "total_rules": total,
        "dead_count": dead_count,
        "live_count": live_count,
        "dead_rules": sorted(dead, key=lambda x: x["rule_id"]),
        "live_rules": sorted(live, key=lambda x: x["hits"], reverse=True),
        "corpus_size": corpus_size,
        "coverage_pct": round(coverage * 100, 2),
    }
