"""
GraphRAG Context Enricher for Deliberation Layer
Constitutional Hash: cdd01ef066bc6cf2

Enriches deliberation context with relevant policy documents retrieved from a
GraphRAG knowledge base using vector similarity search.

Design goals:
- Dependency-injectable: all backends optional; in-memory defaults for dev/test
- Async-first with a hard timeout so fast-lane P99 is never impacted
- LRU cache keyed on (query_hash, tenant_id) to avoid re-embedding identical queries
- Graceful degradation: returns {} on timeout, store error, or import failure
- Constitutional hash embedded in every retrieved result for governance traceability
- Optional full GraphRAGRetriever pipeline for relevance ranking + context assembly
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from collections import OrderedDict
from typing import TYPE_CHECKING

try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

from enhanced_agent_bus.observability.structured_logging import get_logger

if TYPE_CHECKING:
    from src.core.cognitive.graphrag.protocols import EmbeddingProvider, VectorStore
    from src.core.cognitive.graphrag.retrieval.retriever import GraphRAGRetriever
    from src.core.shared.types import JSONDict

logger = get_logger(__name__)

# Default retrieval settings
_DEFAULT_TOP_K = 3
_DEFAULT_MAX_CHARS = 2000
_DEFAULT_CACHE_SIZE = 256
_DEFAULT_TIMEOUT = 0.05  # 50 ms — preserves P99 < 5 ms via graceful fallback


class _LRUCache:
    """Bounded LRU cache for async retrieval results."""

    def __init__(self, maxsize: int) -> None:
        self._cache: OrderedDict[str, JSONDict] = OrderedDict()
        self._maxsize = maxsize

    def get(self, key: str) -> JSONDict | None:
        if key not in self._cache:
            return None
        self._cache.move_to_end(key)
        return self._cache[key]

    def put(self, key: str, value: JSONDict) -> None:
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = value
        if len(self._cache) > self._maxsize:
            self._cache.popitem(last=False)

    def clear(self) -> None:
        self._cache.clear()

    def __len__(self) -> int:
        return len(self._cache)


class GraphRAGContextEnricher:
    """
    Enriches deliberation context with policy documents via vector similarity search.

    Usage (dependency injection into DeliberationLayer)::

        enricher = GraphRAGContextEnricher()
        await enricher.seed_policy(
            text="Agents must not exceed rate limits without HITL approval.",
            policy_id="pol-001",
            tenant_id="tenant-a",
        )
        layer = DeliberationLayer(graphrag_enricher=enricher)

    All backends default to lightweight in-memory implementations.  Swap in
    production backends (Neo4j, FAISS, OpenAI) via constructor parameters.

    Optional full retrieval pipeline::

        from src.core.cognitive.graphrag.retrieval.retriever import GraphRAGRetriever
        enricher = GraphRAGContextEnricher(retriever=GraphRAGRetriever())

    When ``retriever`` is set, retrieved policies are passed through the full
    ``GraphRAGRetriever`` pipeline (relevance ranking + context assembly) instead
    of the raw vector-similarity path.  The timeout guard and graceful-degradation
    behaviour are unchanged.
    """

    def __init__(
        self,
        embedding_provider: EmbeddingProvider | None = None,
        vector_store: VectorStore | None = None,
        retriever: GraphRAGRetriever | None = None,
        top_k: int = _DEFAULT_TOP_K,
        max_context_chars: int = _DEFAULT_MAX_CHARS,
        cache_size: int = _DEFAULT_CACHE_SIZE,
        timeout_seconds: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self._embedding_provider = embedding_provider
        self._vector_store = vector_store
        self._retriever = retriever
        self._top_k = top_k
        self._max_context_chars = max_context_chars
        self._timeout = timeout_seconds
        self._cache: _LRUCache = _LRUCache(cache_size)
        self._seeded_ids: set[str] = set()
        # Per-policy metadata for TraversalResult construction when retriever is set
        self._seeded_metadata: dict[str, dict] = {}
        self.constitutional_hash: str = CONSTITUTIONAL_HASH

    # ------------------------------------------------------------------
    # Backend initialisation (lazy, on first use)
    # ------------------------------------------------------------------

    async def _get_embedding_provider(self) -> EmbeddingProvider:
        if self._embedding_provider is None:
            from src.core.cognitive.graphrag.factory import create_embedding_provider

            self._embedding_provider = create_embedding_provider("mock")
        return self._embedding_provider

    async def _get_vector_store(self) -> VectorStore:
        if self._vector_store is None:
            from src.core.cognitive.graphrag.factory import create_vector_store

            self._vector_store = create_vector_store("memory")
        return self._vector_store

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def seed_policy(self, text: str, policy_id: str, tenant_id: str) -> None:
        """
        Add a governance policy document to the vector knowledge base.

        Call this at startup to pre-populate the enricher with known policies.
        Idempotent: re-seeding the same ``policy_id`` replaces the previous entry.

        Args:
            text: Policy text to embed and store.
            policy_id: Unique identifier for the policy document.
            tenant_id: Tenant the policy belongs to (used for scoped retrieval).
        """
        embedder = await self._get_embedding_provider()
        store = await self._get_vector_store()

        snippet = text[: self._max_context_chars]
        vector = (await embedder.embed([text]))[0]
        meta: dict = {
            "text": snippet,
            "policy_id": policy_id,
            "tenant_id": tenant_id,
            "constitutional_hash": self.constitutional_hash,
            "seeded_at": time.time(),
        }
        await store.upsert(
            ids=[policy_id],
            vectors=[vector],
            metadata=[meta],
        )
        self._seeded_ids.add(policy_id)
        self._seeded_metadata[policy_id] = {**meta, "embedding": vector}
        logger.debug(
            "Seeded policy into GraphRAG knowledge base",
            policy_id=policy_id,
            tenant_id=tenant_id,
        )

    async def seed_policies_batch(
        self,
        items: list[tuple[str, str, str]],
    ) -> None:
        """
        Bulk-seed multiple governance policies in a single embedding call.

        Significantly faster than calling ``seed_policy()`` in a loop when
        seeding 10+ policies at startup, because embeddings are computed in
        one batched ``embedder.embed()`` call.

        Args:
            items: Sequence of ``(text, policy_id, tenant_id)`` tuples.
        """
        if not items:
            return

        embedder = await self._get_embedding_provider()
        store = await self._get_vector_store()

        texts = [text for text, _, _ in items]
        vectors = await embedder.embed(texts)

        ids: list[str] = []
        all_vectors: list[list[float]] = []
        all_metadata: list[dict] = []

        for (text, policy_id, tenant_id), vector in zip(items, vectors, strict=True):
            snippet = text[: self._max_context_chars]
            meta: dict = {
                "text": snippet,
                "policy_id": policy_id,
                "tenant_id": tenant_id,
                "constitutional_hash": self.constitutional_hash,
                "seeded_at": time.time(),
            }
            ids.append(policy_id)
            all_vectors.append(vector)
            all_metadata.append(meta)
            self._seeded_ids.add(policy_id)
            self._seeded_metadata[policy_id] = {**meta, "embedding": vector}

        await store.upsert(ids=ids, vectors=all_vectors, metadata=all_metadata)
        logger.debug(
            "Bulk-seeded policies into GraphRAG knowledge base",
            count=len(ids),
        )

    async def enrich(
        self,
        query: str,
        tenant_id: str,
        timeout: float | None = None,
    ) -> JSONDict:
        """
        Retrieve relevant policy context for a message query.

        Returns a ``JSONDict`` with keys ``retrieved_policies``,
        ``retrieval_time_ms``, and ``constitutional_hash``; or an empty dict
        on timeout, backend error, or empty knowledge base (graceful degradation).

        Args:
            query: Message content or action string to retrieve context for.
            tenant_id: Tenant identifier; results are scoped to this tenant.
            timeout: Override the instance-level timeout (seconds).
        """
        if not query or not query.strip():
            return {}

        cache_key = _cache_key(query, tenant_id)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return {**cached, "cache_hit": True}

        deadline = timeout if timeout is not None else self._timeout
        try:
            result = await asyncio.wait_for(
                self._retrieve(query, tenant_id),
                timeout=deadline,
            )
        except TimeoutError:
            logger.debug(
                "GraphRAG enrichment timed out",
                timeout_s=deadline,
                tenant_id=tenant_id,
            )
            return {}
        except Exception:
            logger.warning("GraphRAG enrichment failed; continuing without context")
            return {}

        if result:
            self._cache.put(cache_key, result)
        return result

    # ------------------------------------------------------------------
    # Internal retrieval
    # ------------------------------------------------------------------

    async def _retrieve(self, query: str, tenant_id: str) -> JSONDict:
        """Embed query, search vector store, format and return top-k results."""
        t0 = time.perf_counter()

        embedder = await self._get_embedding_provider()
        store = await self._get_vector_store()

        if not self._seeded_ids:
            return {}

        query_vector = (await embedder.embed([query]))[0]
        raw_results = await store.search(query_vector, top_k=self._top_k * 2)

        # Filter to requested tenant (store may not support native filtering)
        results = [r for r in raw_results if r.metadata.get("tenant_id") == tenant_id]
        results = results[: self._top_k]

        if not results:
            return {}

        # -------------------------------------------------------------------
        # Optional: pipe through full GraphRAGRetriever for ranked + assembled
        # context.  Falls back to raw path if retriever raises or is absent.
        # -------------------------------------------------------------------
        if self._retriever is not None:
            retriever_result = await self._retrieve_via_pipeline(
                query=query,
                query_vector=query_vector,
                raw_results=results,
                t0=t0,
            )
            if retriever_result:
                return retriever_result
            # Fall through to raw path on pipeline failure

        # -------------------------------------------------------------------
        # Raw path: format vector-search results as policy snippets
        # -------------------------------------------------------------------
        policies = []
        total_chars = 0
        for r in results:
            text: str = r.metadata.get("text", "")
            remaining = self._max_context_chars - total_chars
            if remaining <= 0:
                break
            snippet = text[:remaining]
            total_chars += len(snippet)
            policies.append(
                {
                    "policy_id": r.metadata.get("policy_id", r.id),
                    "score": round(r.score, 4),
                    "snippet": snippet,
                    "constitutional_hash": r.metadata.get(
                        "constitutional_hash", self.constitutional_hash
                    ),
                }
            )

        retrieval_ms = (time.perf_counter() - t0) * 1000
        logger.debug(
            "GraphRAG policy retrieval complete (raw path)",
            tenant_id=tenant_id,
            results=len(policies),
            retrieval_ms=round(retrieval_ms, 2),
        )

        return {
            "retrieved_policies": policies,
            "retrieval_time_ms": round(retrieval_ms, 3),
            "constitutional_hash": self.constitutional_hash,
        }

    async def _retrieve_via_pipeline(
        self,
        query: str,
        query_vector: list[float],
        raw_results: list,
        t0: float,
    ) -> JSONDict:
        """
        Run vector-search results through the full GraphRAGRetriever pipeline.

        Converts raw VectorSearchResult objects into a ``TraversalResult``
        (GraphNode list), then calls ``GraphRAGRetriever.retrieve()`` which
        applies ``RelevanceRanker`` and ``ContextAssembler`` on top.

        Returns empty dict on any error so the caller can fall back to raw path.
        """
        try:
            from src.core.cognitive.graphrag.retrieval.models import (
                GraphNode,
                TraversalResult,
            )

            nodes = []
            for r in raw_results:
                meta = r.metadata or {}
                embedding = self._seeded_metadata.get(r.id, {}).get("embedding")
                node = GraphNode(
                    id=r.id,
                    labels=["GovernancePolicy"],
                    properties={
                        "policy_id": meta.get("policy_id", r.id),
                        "tenant_id": meta.get("tenant_id", ""),
                        "constitutional_hash": meta.get(
                            "constitutional_hash", self.constitutional_hash
                        ),
                        "score": r.score,
                    },
                    text_content=meta.get("text", ""),
                    embedding=list(embedding) if embedding is not None else None,
                    metadata=meta,
                )
                nodes.append(node)

            traversal = TraversalResult(
                nodes=nodes,
                seed_node_ids=[r.id for r in raw_results[:1]],
                query=query,
            )

            assert self._retriever is not None  # guarded by caller
            rag_result = await self._retriever.retrieve(
                query=query,
                graph_results=traversal,
                query_embedding=query_vector,
            )

            retrieval_ms = (time.perf_counter() - t0) * 1000

            # Format citations as policy list for downstream consumers
            policies = []
            for ctx in rag_result.ranked_contexts[: self._top_k]:
                node = ctx.node
                snippet = node.text_content[: self._max_context_chars]
                policies.append(
                    {
                        "policy_id": node.properties.get("policy_id", node.id),
                        "score": round(ctx.score.total_score, 4),
                        "snippet": snippet,
                        "constitutional_hash": node.properties.get(
                            "constitutional_hash", self.constitutional_hash
                        ),
                        "retrieval_path": "pipeline",
                    }
                )

            assembled_text = rag_result.assembled_context.text if policies else ""
            logger.debug(
                "GraphRAG policy retrieval complete (pipeline path)",
                query=query[:40],
                results=len(policies),
                retrieval_ms=round(retrieval_ms, 2),
            )

            return {
                "retrieved_policies": policies,
                "assembled_context": assembled_text[: self._max_context_chars],
                "retrieval_time_ms": round(retrieval_ms, 3),
                "constitutional_hash": self.constitutional_hash,
                "retrieval_path": "pipeline",
            }

        except Exception:
            logger.debug("GraphRAG pipeline retrieval failed; falling back to raw path")
            return {}

    # ------------------------------------------------------------------
    # Introspection helpers
    # ------------------------------------------------------------------

    @property
    def seeded_policy_count(self) -> int:
        """Number of policies currently in the knowledge base."""
        return len(self._seeded_ids)

    @property
    def cache_size(self) -> int:
        """Number of cached retrieval results."""
        return len(self._cache)

    def clear_cache(self) -> None:
        """Flush the LRU cache (useful in tests or after bulk re-seeding)."""
        self._cache.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cache_key(query: str, tenant_id: str) -> str:
    """Deterministic cache key from query text + tenant."""
    digest = hashlib.sha256(f"{tenant_id}:{query}".encode()).hexdigest()[:16]
    return digest
