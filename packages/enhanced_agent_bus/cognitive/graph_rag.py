# mypy: ignore-errors
# Backward-compat facade: uses dynamic getattr() imports. Canonical module:
# src.core.cognitive.graphrag — use that for new code.
"""GraphRAG Governance Context — backward-compatibility facade.

Canonical types now live in ``src.core.cognitive.graphrag.schema``.
Canonical async protocols live in ``src.core.cognitive.graphrag.protocols``.

This module re-exports the canonical types and keeps the sync-only
``GovernanceKnowledgeGraph``, ``PolicyGraphExtractor``,
``GraphSimilaritySearch``, ``SearchResult`` and ``build_governance_context``
implementations that depend on sync ``GraphStorage`` / ``EmbeddingProvider``
protocols.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

# ── Canonical re-exports ────────────────────────────────────────────
import importlib
import math
import re
import warnings
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

try:
    _schema = importlib.import_module("src.core.cognitive.graphrag.schema")
    GraphRAGQuery = getattr(_schema, "GraphRAGQuery", None)
    GraphRAGResponse = getattr(_schema, "GraphRAGResponse", None)
    GraphNode = getattr(_schema, "GraphNode", None)
    GraphEdge = getattr(_schema, "GraphEdge", None)
    EdgeType = getattr(_schema, "EdgeType", None)
    NodeType = getattr(_schema, "NodeType", None)
except (ImportError, ModuleNotFoundError):
    GraphRAGQuery = None
    GraphRAGResponse = None
    GraphNode = None
    GraphEdge = None
    EdgeType = None
    NodeType = None

warnings.warn(
    "Import from src.core.cognitive.graphrag instead of "
    "enhanced_agent_bus.cognitive.graph_rag. "
    "This facade will be removed in a future release.",
    DeprecationWarning,
    stacklevel=2,
)


# ── Sync protocols (kept for backward compat) ──────────────────────
# The canonical *async* protocols live in
# ``src.core.cognitive.graphrag.protocols``.


class EmbeddingProvider(Protocol):
    """Sync embedding provider used by GovernanceKnowledgeGraph."""

    def embed(self, text: str) -> list[float]: ...

    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


class GraphStorage(Protocol):
    """Sync graph storage used by GovernanceKnowledgeGraph."""

    def add_node(self, node: GraphNode) -> None: ...

    def get_node(self, node_id: str) -> GraphNode | None: ...

    def update_node(self, node: GraphNode) -> None: ...

    def delete_node(self, node_id: str) -> None: ...

    def add_edge(self, edge: GraphEdge) -> None: ...

    def get_edges(self, node_id: str) -> list[GraphEdge]: ...

    def delete_edge(self, edge_id: str) -> None: ...

    def get_nodes_by_type(self, node_type: NodeType, tenant_id: str) -> list[GraphNode]: ...


# ── Search result ───────────────────────────────────────────────────


@dataclass
class SearchResult:
    """Search result from GraphSimilaritySearch."""

    node: GraphNode
    score: float
    path: list[str] = field(default_factory=list)
    context_nodes: list[GraphNode] = field(default_factory=list)


# ── GovernanceKnowledgeGraph ────────────────────────────────────────


class GovernanceKnowledgeGraph:
    """In-memory governance knowledge graph with optional external storage."""

    def __init__(
        self,
        storage: GraphStorage | None = None,
        embedding_provider: EmbeddingProvider | None = None,
    ):
        self._storage = storage
        self._embedding_provider = embedding_provider
        self._nodes: dict[str, GraphNode] = {}
        self._edges: dict[str, GraphEdge] = {}
        self._adjacency: dict[str, list[str]] = {}
        self._reverse_adjacency: dict[str, list[str]] = {}

    def add_node(self, node: GraphNode) -> None:
        if self._embedding_provider and node.embedding is None:
            node.embedding = self._embedding_provider.embed(node.content)

        self._nodes[node.node_id] = node
        if node.node_id not in self._adjacency:
            self._adjacency[node.node_id] = []
        if node.node_id not in self._reverse_adjacency:
            self._reverse_adjacency[node.node_id] = []

        if self._storage:
            self._storage.add_node(node)

    def add_edge(self, edge: GraphEdge) -> None:
        self._edges[edge.edge_id] = edge

        if edge.source_id not in self._adjacency:
            self._adjacency[edge.source_id] = []
        self._adjacency[edge.source_id].append(edge.edge_id)

        if edge.target_id not in self._reverse_adjacency:
            self._reverse_adjacency[edge.target_id] = []
        self._reverse_adjacency[edge.target_id].append(edge.edge_id)

        if self._storage:
            self._storage.add_edge(edge)

    def get_node(self, node_id: str) -> GraphNode | None:
        if node_id in self._nodes:
            return self._nodes[node_id]
        if self._storage:
            node = self._storage.get_node(node_id)
            if node:
                self._nodes[node_id] = node
            return node
        return None

    def get_neighbors(
        self, node_id: str, edge_types: list[EdgeType] | None = None
    ) -> list[GraphNode]:
        neighbors = []
        edge_ids = self._adjacency.get(node_id, [])

        for edge_id in edge_ids:
            edge = self._edges.get(edge_id)
            if edge and (edge_types is None or edge.edge_type in edge_types):
                target = self.get_node(edge.target_id)
                if target:
                    neighbors.append(target)

        return neighbors

    def get_incoming(
        self, node_id: str, edge_types: list[EdgeType] | None = None
    ) -> list[GraphNode]:
        incoming = []
        edge_ids = self._reverse_adjacency.get(node_id, [])

        for edge_id in edge_ids:
            edge = self._edges.get(edge_id)
            if edge and (edge_types is None or edge.edge_type in edge_types):
                source = self.get_node(edge.source_id)
                if source:
                    incoming.append(source)

        return incoming

    def traverse_bfs(
        self,
        start_id: str,
        max_depth: int = 3,
        node_filter: Callable[[GraphNode], bool] | None = None,
    ) -> list[GraphNode]:
        visited: set[str] = set()
        result: list[GraphNode] = []
        queue: list[tuple[str, int]] = [(start_id, 0)]

        while queue:
            current_id, depth = queue.pop(0)

            if current_id in visited or depth > max_depth:
                continue

            visited.add(current_id)
            node = self.get_node(current_id)

            if node and (node_filter is None or node_filter(node)):
                result.append(node)

            if depth < max_depth:
                for edge_id in self._adjacency.get(current_id, []):
                    edge = self._edges.get(edge_id)
                    if edge and edge.target_id not in visited:
                        queue.append((edge.target_id, depth + 1))

        return result

    def find_path(self, start_id: str, end_id: str, max_depth: int = 5) -> list[str] | None:
        if start_id == end_id:
            return [start_id]

        visited: set[str] = set()
        queue: list[tuple[str, list[str]]] = [(start_id, [start_id])]

        while queue:
            current_id, path = queue.pop(0)

            if current_id in visited:
                continue

            visited.add(current_id)

            for edge_id in self._adjacency.get(current_id, []):
                edge = self._edges.get(edge_id)
                if not edge:
                    continue

                if edge.target_id == end_id:
                    return [*path, end_id]

                if edge.target_id not in visited and len(path) < max_depth:
                    queue.append((edge.target_id, [*path, edge.target_id]))

        return None

    def get_subgraph(
        self, node_ids: list[str], include_edges: bool = True
    ) -> tuple[list[GraphNode], list[GraphEdge]]:
        nodes = [self.get_node(nid) for nid in node_ids]
        nodes = [n for n in nodes if n is not None]

        edges: list[GraphEdge] = []
        if include_edges:
            node_set = set(node_ids)
            for edge in self._edges.values():
                if edge.source_id in node_set and edge.target_id in node_set:
                    edges.append(edge)

        return nodes, edges

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    @property
    def edge_count(self) -> int:
        return len(self._edges)


# ── PolicyGraphExtractor ────────────────────────────────────────────


class PolicyGraphExtractor:
    """Extract governance graph nodes from Rego policies."""

    def __init__(self, graph: GovernanceKnowledgeGraph, tenant_id: str):
        self._graph = graph
        self._tenant_id = tenant_id

    def extract_from_rego(self, policy_id: str, rego_content: str) -> list[GraphNode]:
        nodes: list[GraphNode] = []

        policy_node = GraphNode(
            node_id=f"policy:{policy_id}",
            node_type=NodeType.POLICY,
            name=policy_id,
            content=rego_content,
            tenant_id=self._tenant_id,
            metadata={
                "source": "rego",
                "line_count": rego_content.count("\n") + 1,
            },
        )
        nodes.append(policy_node)
        self._graph.add_node(policy_node)

        rules = self._extract_rego_rules(policy_id, rego_content)
        for rule in rules:
            nodes.append(rule)
            self._graph.add_node(rule)
            self._graph.add_edge(
                GraphEdge(
                    edge_id=f"edge:{policy_node.node_id}:{rule.node_id}",
                    edge_type=EdgeType.IMPLEMENTS,
                    source_id=policy_node.node_id,
                    target_id=rule.node_id,
                )
            )

        return nodes

    def extract_from_principle(
        self,
        principle_id: str,
        content: str,
        related_policies: list[str] | None = None,
    ) -> GraphNode:
        principle_node = GraphNode(
            node_id=f"principle:{principle_id}",
            node_type=NodeType.PRINCIPLE,
            name=principle_id,
            content=content,
            tenant_id=self._tenant_id,
            metadata={"word_count": len(content.split())},
        )
        self._graph.add_node(principle_node)

        if related_policies:
            for pid in related_policies:
                policy_node_id = f"policy:{pid}"
                if self._graph.get_node(policy_node_id):
                    self._graph.add_edge(
                        GraphEdge(
                            edge_id=(f"edge:{policy_node_id}:{principle_node.node_id}"),
                            edge_type=EdgeType.IMPLEMENTS,
                            source_id=policy_node_id,
                            target_id=principle_node.node_id,
                        )
                    )

        return principle_node

    def extract_constraints(self, policy_id: str, rego_content: str) -> list[GraphNode]:
        constraints: list[GraphNode] = []
        deny_pattern = re.compile(
            r"deny\s*(?:\[.*?\])?\s*{([^}]+)}",
            re.MULTILINE | re.DOTALL,
        )

        for i, match in enumerate(deny_pattern.finditer(rego_content)):
            constraint_content = match.group(1).strip()
            constraint_node = GraphNode(
                node_id=f"constraint:{policy_id}:deny:{i}",
                node_type=NodeType.CONSTRAINT,
                name=f"{policy_id}_deny_{i}",
                content=constraint_content,
                tenant_id=self._tenant_id,
                metadata={"type": "deny", "index": i},
            )
            constraints.append(constraint_node)
            self._graph.add_node(constraint_node)

            policy_node_id = f"policy:{policy_id}"
            self._graph.add_edge(
                GraphEdge(
                    edge_id=(f"edge:{policy_node_id}:{constraint_node.node_id}"),
                    edge_type=EdgeType.REQUIRES,
                    source_id=policy_node_id,
                    target_id=constraint_node.node_id,
                )
            )

        return constraints

    def _extract_rego_rules(self, policy_id: str, rego_content: str) -> list[GraphNode]:
        rules: list[GraphNode] = []
        rule_pattern = re.compile(
            r"^(\w+)\s*(?:\[.*?\])?\s*(?:=\s*\w+)?\s*{([^}]+)}",
            re.MULTILINE,
        )

        for i, match in enumerate(rule_pattern.finditer(rego_content)):
            rule_name = match.group(1)
            rule_body = match.group(2).strip()

            if rule_name in ("package", "import"):
                continue

            rule_node = GraphNode(
                node_id=f"rule:{policy_id}:{rule_name}:{i}",
                node_type=NodeType.RULE,
                name=f"{policy_id}.{rule_name}",
                content=rule_body,
                tenant_id=self._tenant_id,
                metadata={"rule_name": rule_name, "index": i},
            )
            rules.append(rule_node)

        return rules


# ── GraphSimilaritySearch ───────────────────────────────────────────


class GraphSimilaritySearch:
    """Cosine-similarity search over an in-memory governance graph."""

    def __init__(
        self,
        graph: GovernanceKnowledgeGraph,
        embedding_provider: EmbeddingProvider | None = None,
    ):
        self._graph = graph
        self._embedding_provider = embedding_provider

    def search_by_embedding(
        self,
        query_embedding: list[float],
        tenant_id: str,
        node_types: list[NodeType] | None = None,
        top_k: int = 10,
        min_score: float = 0.0,
    ) -> list[SearchResult]:
        results: list[SearchResult] = []

        for node in self._graph._nodes.values():
            if node.tenant_id != tenant_id:
                continue
            if node_types and node.node_type not in node_types:
                continue
            if node.embedding is None:
                continue

            score = self._cosine_similarity(query_embedding, node.embedding)
            if score >= min_score:
                results.append(SearchResult(node=node, score=score))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    def search_by_text(
        self,
        query: str,
        tenant_id: str,
        node_types: list[NodeType] | None = None,
        top_k: int = 10,
        min_score: float = 0.0,
    ) -> list[SearchResult]:
        if not self._embedding_provider:
            return self._fallback_text_search(query, tenant_id, node_types, top_k)

        query_embedding = self._embedding_provider.embed(query)
        return self.search_by_embedding(query_embedding, tenant_id, node_types, top_k, min_score)

    def search_with_context(
        self,
        query: str,
        tenant_id: str,
        node_types: list[NodeType] | None = None,
        top_k: int = 5,
        context_depth: int = 2,
    ) -> list[SearchResult]:
        base_results = self.search_by_text(query, tenant_id, node_types, top_k)

        for result in base_results:
            node_id = result.node.node_id
            context_nodes = self._graph.traverse_bfs(
                node_id,
                max_depth=context_depth,
                node_filter=lambda n, nid=node_id: n.node_id != nid,  # type: ignore[misc]
            )
            result.context_nodes = context_nodes[:10]

        return base_results

    def find_related_policies(self, node_id: str, max_depth: int = 3) -> list[GraphNode]:
        return self._graph.traverse_bfs(
            node_id,
            max_depth=max_depth,
            node_filter=lambda n: n.node_type == NodeType.POLICY,
        )

    def find_implementing_rules(self, principle_id: str) -> list[GraphNode]:
        principle_node_id = f"principle:{principle_id}"
        incoming = self._graph.get_incoming(principle_node_id, edge_types=[EdgeType.IMPLEMENTS])
        rules: list[GraphNode] = []

        for policy_node in incoming:
            policy_rules = self._graph.get_neighbors(
                policy_node.node_id,
                edge_types=[EdgeType.IMPLEMENTS],
            )
            rules.extend(r for r in policy_rules if r.node_type == NodeType.RULE)

        return rules

    def _cosine_similarity(self, vec1: list[float], vec2: list[float]) -> float:
        if len(vec1) != len(vec2):
            return 0.0

        dot_product = sum(a * b for a, b in zip(vec1, vec2, strict=False))
        norm1 = math.sqrt(sum(a * a for a in vec1))
        norm2 = math.sqrt(sum(b * b for b in vec2))

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)

    def _fallback_text_search(
        self,
        query: str,
        tenant_id: str,
        node_types: list[NodeType] | None,
        top_k: int,
    ) -> list[SearchResult]:
        query_terms = set(query.lower().split())
        results: list[SearchResult] = []

        for node in self._graph._nodes.values():
            if node.tenant_id != tenant_id:
                continue
            if node_types and node.node_type not in node_types:
                continue

            content_terms = set(node.content.lower().split())
            overlap = len(query_terms & content_terms)
            if overlap > 0:
                score = overlap / max(len(query_terms), len(content_terms))
                results.append(SearchResult(node=node, score=score))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]


# ── build_governance_context ────────────────────────────────────────


def build_governance_context(
    graph: GovernanceKnowledgeGraph,
    query_results: list[SearchResult],
    max_tokens: int = 4000,
) -> str:
    """Assemble a text context from graph search results."""
    context_parts: list[str] = []
    estimated_tokens: float = 0.0

    for result in query_results:
        node_context = (
            f"[{result.node.node_type.value}] {result.node.name}:\n{result.node.content}\n"
        )
        node_tokens = len(node_context.split()) * 1.3

        if estimated_tokens + node_tokens > max_tokens:
            break

        context_parts.append(node_context)
        estimated_tokens += node_tokens

        for ctx_node in result.context_nodes[:3]:
            ctx_text = f"  - Related {ctx_node.node_type.value}: {ctx_node.name}\n"
            ctx_tokens = len(ctx_text.split()) * 1.3

            if estimated_tokens + ctx_tokens > max_tokens:
                break

            context_parts.append(ctx_text)
            estimated_tokens += ctx_tokens

    return "\n".join(context_parts)
