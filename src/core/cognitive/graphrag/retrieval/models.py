"""
GraphRAG retrieval data models.
Constitutional Hash: cdd01ef066bc6cf2
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GraphNode:
    """A node in the policy knowledge graph."""

    id: str
    labels: list[str] = field(default_factory=list)
    properties: dict = field(default_factory=dict)
    text_content: str = ""
    embedding: list[float] | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class TraversalResult:
    """Result of a graph traversal starting from seed nodes."""

    nodes: list[GraphNode] = field(default_factory=list)
    seed_node_ids: list[str] = field(default_factory=list)
    query: str = ""
