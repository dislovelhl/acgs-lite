"""
GraphRAG protocols — EmbeddingProvider and VectorStore.
Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Protocol for embedding text into dense vectors."""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text."""
        ...


@runtime_checkable
class VectorStore(Protocol):
    """Protocol for a vector similarity store."""

    async def upsert(
        self,
        ids: list[str],
        vectors: list[list[float]],
        metadata: list[dict],
    ) -> None:
        """Insert or update entries by id."""
        ...

    async def search(
        self,
        query_vector: list[float],
        top_k: int = 5,
    ) -> list:
        """Return up to top_k nearest neighbours."""
        ...
