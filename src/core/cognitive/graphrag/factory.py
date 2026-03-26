"""
GraphRAG factory — create_embedding_provider and create_vector_store.
Constitutional Hash: cdd01ef066bc6cf2

Provides lightweight in-memory implementations for dev/test use.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# VectorSearchResult
# ---------------------------------------------------------------------------


@dataclass
class VectorSearchResult:
    """Single result returned by VectorStore.search()."""

    id: str
    score: float
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Mock EmbeddingProvider
# ---------------------------------------------------------------------------


class MockEmbeddingProvider:
    """
    Deterministic, dependency-free embedding provider for dev/test.

    Each text is hashed to a stable 64-dimensional unit vector.  Texts that
    share word-level tokens will have higher cosine similarity.
    """

    _DIM = 64

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def _embed_one(self, text: str) -> list[float]:
        # Build a raw vector by accumulating word-level hash contributions.
        raw = [0.0] * self._DIM
        words = text.lower().split()
        if not words:
            # Fall back to character hash for empty / whitespace-only input.
            words = [text]
        for word in words:
            digest = hashlib.sha256(word.encode()).digest()
            for i in range(self._DIM):
                byte_val = digest[i % len(digest)]
                raw[i] += (byte_val / 255.0) * 2 - 1  # map to [-1, 1]
        # L2-normalise so cosine similarity == dot product.
        norm = math.sqrt(sum(v * v for v in raw)) or 1.0
        return [v / norm for v in raw]


# ---------------------------------------------------------------------------
# In-memory VectorStore
# ---------------------------------------------------------------------------


class MemoryVectorStore:
    """Thread-safe (single-event-loop) in-memory vector store for dev/test."""

    def __init__(self) -> None:
        self._entries: dict[str, dict] = {}  # id -> {vector, metadata}

    async def upsert(
        self,
        ids: list[str],
        vectors: list[list[float]],
        metadata: list[dict],
    ) -> None:
        for doc_id, vec, meta in zip(ids, vectors, metadata, strict=True):
            self._entries[doc_id] = {"vector": vec, "metadata": meta}

    async def search(
        self,
        query_vector: list[float],
        top_k: int = 5,
    ) -> list[VectorSearchResult]:
        if not self._entries:
            return []
        scored = []
        for doc_id, entry in self._entries.items():
            score = _dot_product(query_vector, entry["vector"])
            scored.append(
                VectorSearchResult(
                    id=doc_id,
                    score=score,
                    metadata=entry["metadata"],
                )
            )
        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:top_k]


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def create_embedding_provider(backend: str = "mock") -> MockEmbeddingProvider:
    """Return an EmbeddingProvider for the requested backend.

    Currently only ``"mock"`` is supported.
    """
    if backend == "mock":
        return MockEmbeddingProvider()
    raise ValueError(f"Unknown embedding backend: {backend!r}")


def create_vector_store(backend: str = "memory") -> MemoryVectorStore:
    """Return a VectorStore for the requested backend.

    Currently only ``"memory"`` is supported.
    """
    if backend == "memory":
        return MemoryVectorStore()
    raise ValueError(f"Unknown vector store backend: {backend!r}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dot_product(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        min_len = min(len(a), len(b))
        return sum(x * y for x, y in zip(a[:min_len], b[:min_len], strict=False))
    return sum(x * y for x, y in zip(a, b, strict=False))
