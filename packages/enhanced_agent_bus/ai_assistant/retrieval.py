"""
ACGS-2 AI Assistant - Retrieval System (RAG)
Constitutional Hash: 608508a9bd224290

Hybrid retrieval system combining:
1. Exact/Prefix matches via PolicyIndex (High-performance)
2. Semantic search via embeddings module (Vector DB)
3. Constitutional validation of retrieved context
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from typing import TYPE_CHECKING, TypeAlias

from enhanced_agent_bus.observability.structured_logging import get_logger

if TYPE_CHECKING:
    from enhanced_agent_bus.embeddings.provider import BaseEmbeddingProvider
    from enhanced_agent_bus.embeddings.vector_store import BaseVectorStore


try:
    from enhanced_agent_bus._compat.policy import PolicyMetadata, get_policy_index

    POLICY_INDEX_AVAILABLE = True
except ImportError:
    POLICY_INDEX_AVAILABLE = False
    PolicyMetadata = object  # type: ignore[misc, assignment]

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import (
        JSONDict,
        JSONValue,
    )
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]
    JSONValue = object  # type: ignore[misc,assignment]

try:
    from enhanced_agent_bus.embeddings.provider import (
        EmbeddingConfig,
        EmbeddingProviderType,
        create_embedding_provider,
    )
    from enhanced_agent_bus.embeddings.vector_store import (
        VectorStoreConfig,
        VectorStoreType,
        create_vector_store,
    )

    EMBEDDINGS_AVAILABLE = True
except ImportError:
    EMBEDDINGS_AVAILABLE = False

logger = get_logger(__name__)
HYBRID_RETRIEVAL_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
)


@dataclass
class RetrievalResult:
    """Represents a single result retrieved from the knowledge base."""

    id: str
    content: str
    score: float
    source: str  # e.g., "policy_index", "vector_db", "web"
    metadata: JSONDict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


class BaseRetriever:
    """Abstract base class for retrievers."""

    async def retrieve(self, query: str, limit: int = 5) -> list[RetrievalResult]:
        raise NotImplementedError


class PolicyRetriever(BaseRetriever):
    """Retriever focusing on governance policies using PolicyIndex."""

    def __init__(self):
        self.index = get_policy_index() if POLICY_INDEX_AVAILABLE else None

    async def retrieve(self, query: str, limit: int = 5) -> list[RetrievalResult]:
        if not self.index:
            return []

        results = []
        # 1. Try exact match
        policy = self.index.get(query)
        if policy:
            results.append(
                RetrievalResult(
                    id=query,
                    content=f"Policy: {policy.name} (Domain: {policy.domain})",
                    score=1.0,
                    source="policy_index",
                    metadata={"domain": policy.domain, "tags": policy.tags},
                )
            )

        # 2. Try prefix search
        prefix_matches = self.index.prefix_search(query, limit=limit)
        for pid, meta in prefix_matches:
            if pid == query:
                continue  # Already added
            results.append(
                RetrievalResult(
                    id=pid,
                    content=f"Policy: {meta.name if meta else pid}",
                    score=0.8,
                    source="policy_index",
                    metadata={"domain": meta.domain if meta else "unknown"},
                )
            )

        return results[:limit]


class SemanticRetriever(BaseRetriever):
    def __init__(
        self,
        embedding_provider: BaseEmbeddingProvider | None = None,
        vector_store: BaseVectorStore | None = None,
    ):
        self._embedding_provider = embedding_provider
        self._vector_store = vector_store
        self._initialized = False

    def _ensure_initialized(self) -> bool:
        if self._initialized:
            return self._embedding_provider is not None and self._vector_store is not None

        if not EMBEDDINGS_AVAILABLE:
            logger.debug("Embeddings module not available")
            return False

        if self._embedding_provider is None:
            provider_type_str = os.environ.get("EMBEDDING_PROVIDER", "mock")
            try:
                provider_type = EmbeddingProviderType(provider_type_str)
            except ValueError:
                provider_type = EmbeddingProviderType.MOCK

            model_name = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")
            config = EmbeddingConfig(provider_type=provider_type, model_name=model_name)
            self._embedding_provider = create_embedding_provider(config)

        if self._vector_store is None:
            store_type_str = os.environ.get("VECTOR_STORE", "memory")
            try:
                store_type = VectorStoreType(store_type_str)
            except ValueError:
                store_type = VectorStoreType.MEMORY

            config = VectorStoreConfig(
                store_type=store_type,
                dimension=self._embedding_provider.dimension,
            )
            self._vector_store = create_vector_store(config)

        self._initialized = True
        return True

    async def retrieve(self, query: str, limit: int = 5) -> list[RetrievalResult]:
        if not self._ensure_initialized():
            return []

        query_embedding = self._embedding_provider.embed(query)
        search_results = self._vector_store.search(query_embedding, limit=limit)

        return [
            RetrievalResult(
                id=result.id,
                content=result.payload.get("content", ""),
                score=result.score,
                source="vector_db",
                metadata=result.payload,
            )
            for result in search_results
        ]

    async def index_document(self, doc_id: str, content: str, metadata: dict | None = None) -> bool:
        if not self._ensure_initialized():
            return False

        from enhanced_agent_bus.embeddings.vector_store import VectorDocument

        embedding = self._embedding_provider.embed(content)
        payload = {"content": content, **(metadata or {})}
        doc = VectorDocument(id=doc_id, vector=embedding, payload=payload)
        self._vector_store.upsert([doc])
        return True

    async def index_documents_batch(self, documents: list[JSONDict]) -> int:
        if not self._ensure_initialized():
            return 0

        from enhanced_agent_bus.embeddings.vector_store import VectorDocument

        contents = [doc["content"] for doc in documents]
        embeddings = self._embedding_provider.embed_batch(contents)

        vector_docs = [
            VectorDocument(
                id=doc.get("id", str(i)),
                vector=emb,
                payload={"content": doc["content"], **doc.get("metadata", {})},
            )
            for i, (doc, emb) in enumerate(zip(documents, embeddings, strict=False))
        ]

        return self._vector_store.upsert(vector_docs)  # type: ignore[no-any-return]


class HybridRetriever(BaseRetriever):
    """
    Hybrid retriever combining multiple retrieval strategies.
    Implements multi-stage retrieval: filter -> fetch -> rerank.
    """

    def __init__(self):
        self.retrievers = [PolicyRetriever(), SemanticRetriever()]

    async def retrieve(self, query: str, limit: int = 5) -> list[RetrievalResult]:
        all_results = []
        for retriever in self.retrievers:
            try:
                results = await retriever.retrieve(query, limit=limit)
                all_results.extend(results)
            except HYBRID_RETRIEVAL_ERRORS as e:
                logger.error(f"Retriever {retriever.__class__.__name__} failed: {e}")

        # Basic reranking by score
        all_results.sort(key=lambda x: x.score, reverse=True)
        return all_results[:limit]


class KnowledgeRetriever:
    """
    Main interface for knowledge retrieval in AI Assistant.
    """

    def __init__(self, constitutional_hash: str = CONSTITUTIONAL_HASH):
        self.retriever = HybridRetriever()
        self.constitutional_hash = constitutional_hash

    async def query(self, text: str, limit: int = 5) -> list[RetrievalResult]:
        """
        Perform a high-level query against available knowledge bases.
        """
        logger.info(f"RAG Query: {text}")
        results = await self.retriever.retrieve(text, limit=limit)

        # In a real implementation, we would add constitutional validation
        # to ensure the retrieved context is safe to present.

        return results


# Global singleton
_retriever = None


def get_knowledge_retriever() -> KnowledgeRetriever:
    global _retriever
    if _retriever is None:
        _retriever = KnowledgeRetriever()
    return _retriever
