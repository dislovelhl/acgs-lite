# mypy: ignore-errors
"""Tests for enhanced_agent_bus.cognitive.graph_rag module.

Because the module depends on ``src.core.cognitive.graphrag.schema`` which may
not exist at test time, we inject lightweight stub types into ``sys.modules``
before importing the module under test.
"""

from __future__ import annotations

import importlib
import importlib.util
import math
import sys
import types
import warnings
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Stub types for src.core.cognitive.graphrag.schema
# ---------------------------------------------------------------------------


class NodeType(Enum):
    POLICY = "policy"
    PRINCIPLE = "principle"
    RULE = "rule"
    CONSTRAINT = "constraint"


class EdgeType(Enum):
    IMPLEMENTS = "implements"
    REQUIRES = "requires"
    REFERENCES = "references"


@dataclass
class GraphNode:
    node_id: str
    node_type: NodeType
    name: str
    content: str
    tenant_id: str
    metadata: dict = field(default_factory=dict)
    embedding: list[float] | None = None


@dataclass
class GraphEdge:
    edge_id: str
    edge_type: EdgeType
    source_id: str
    target_id: str
    metadata: dict = field(default_factory=dict)


@dataclass
class GraphRAGQuery:
    query: str


@dataclass
class GraphRAGResponse:
    results: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Install stubs into sys.modules so the graph_rag import succeeds.
# Track injected keys so we can clean up after the module's tests run.
# ---------------------------------------------------------------------------

_INJECTED_MODULES: list[str] = []

_schema_mod = types.ModuleType("src.core.cognitive.graphrag.schema")
_schema_mod.GraphRAGQuery = GraphRAGQuery
_schema_mod.GraphRAGResponse = GraphRAGResponse
_schema_mod.GraphNode = GraphNode
_schema_mod.GraphEdge = GraphEdge
_schema_mod.EdgeType = EdgeType
_schema_mod.NodeType = NodeType

# Ensure parent packages exist as well.
for _pkg in (
    "src",
    "src.core",
    "src.core.cognitive",
    "src.core.cognitive.graphrag",
):
    if _pkg not in sys.modules:
        sys.modules[_pkg] = types.ModuleType(_pkg)
        _INJECTED_MODULES.append(_pkg)

sys.modules["src.core.cognitive.graphrag.schema"] = _schema_mod
_INJECTED_MODULES.append("src.core.cognitive.graphrag.schema")

# Now load graph_rag via file location to dodge the cognitive __init__.py
# which tries to import sibling modules (planning, context_inference).
_MOD_NAME = "enhanced_agent_bus.cognitive.graph_rag"
_MOD_PATH = Path(__file__).resolve().parent.parent / "cognitive" / "graph_rag.py"
_spec = importlib.util.spec_from_file_location(_MOD_NAME, _MOD_PATH)
assert _spec and _spec.loader
_graph_rag = importlib.util.module_from_spec(_spec)
sys.modules[_MOD_NAME] = _graph_rag
_INJECTED_MODULES.append(_MOD_NAME)
with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    _spec.loader.exec_module(_graph_rag)


def teardown_module() -> None:
    """Remove stub modules injected into sys.modules to avoid polluting other tests."""
    for mod_key in _INJECTED_MODULES:
        sys.modules.pop(mod_key, None)


GovernanceKnowledgeGraph = _graph_rag.GovernanceKnowledgeGraph
PolicyGraphExtractor = _graph_rag.PolicyGraphExtractor
GraphSimilaritySearch = _graph_rag.GraphSimilaritySearch
SearchResult = _graph_rag.SearchResult
build_governance_context = _graph_rag.build_governance_context

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def graph() -> GovernanceKnowledgeGraph:
    return GovernanceKnowledgeGraph()


@pytest.fixture()
def make_node():
    """Factory for creating GraphNode instances with defaults."""
    _counter = 0

    def _make(
        *,
        node_id: str | None = None,
        node_type: NodeType = NodeType.POLICY,
        name: str = "test-node",
        content: str = "test content",
        tenant_id: str = "tenant-1",
        embedding: list[float] | None = None,
    ) -> GraphNode:
        nonlocal _counter
        _counter += 1
        return GraphNode(
            node_id=node_id or f"node-{_counter}",
            node_type=node_type,
            name=name,
            content=content,
            tenant_id=tenant_id,
            embedding=embedding,
        )

    return _make


@pytest.fixture()
def make_edge():
    """Factory for creating GraphEdge instances."""
    _counter = 0

    def _make(
        *,
        edge_id: str | None = None,
        edge_type: EdgeType = EdgeType.IMPLEMENTS,
        source_id: str = "src",
        target_id: str = "tgt",
    ) -> GraphEdge:
        nonlocal _counter
        _counter += 1
        return GraphEdge(
            edge_id=edge_id or f"edge-{_counter}",
            edge_type=edge_type,
            source_id=source_id,
            target_id=target_id,
        )

    return _make


# ===================================================================
# GovernanceKnowledgeGraph tests
# ===================================================================


class TestGovernanceKnowledgeGraph:
    def test_add_and_get_node(self, graph, make_node):
        node = make_node(node_id="n1")
        graph.add_node(node)
        assert graph.get_node("n1") is node

    def test_get_nonexistent_node_returns_none(self, graph):
        assert graph.get_node("does-not-exist") is None

    def test_node_count_and_edge_count(self, graph, make_node, make_edge):
        assert graph.node_count == 0
        assert graph.edge_count == 0
        graph.add_node(make_node(node_id="a"))
        graph.add_node(make_node(node_id="b"))
        assert graph.node_count == 2
        graph.add_edge(make_edge(source_id="a", target_id="b"))
        assert graph.edge_count == 1

    def test_add_node_with_embedding_provider(self, make_node):
        provider = MagicMock()
        provider.embed.return_value = [0.1, 0.2, 0.3]
        g = GovernanceKnowledgeGraph(embedding_provider=provider)
        node = make_node(node_id="x")
        assert node.embedding is None
        g.add_node(node)
        provider.embed.assert_called_once_with("test content")
        assert node.embedding == [0.1, 0.2, 0.3]

    def test_add_node_skips_embed_when_already_set(self, make_node):
        provider = MagicMock()
        g = GovernanceKnowledgeGraph(embedding_provider=provider)
        node = make_node(node_id="x", embedding=[1.0, 2.0])
        g.add_node(node)
        provider.embed.assert_not_called()

    def test_add_node_delegates_to_storage(self, make_node):
        storage = MagicMock()
        g = GovernanceKnowledgeGraph(storage=storage)
        node = make_node(node_id="s1")
        g.add_node(node)
        storage.add_node.assert_called_once_with(node)

    def test_add_edge_delegates_to_storage(self, make_edge):
        storage = MagicMock()
        g = GovernanceKnowledgeGraph(storage=storage)
        edge = make_edge(source_id="a", target_id="b")
        g.add_edge(edge)
        storage.add_edge.assert_called_once_with(edge)

    def test_get_node_falls_back_to_storage(self):
        node = GraphNode(
            node_id="remote-1",
            node_type=NodeType.POLICY,
            name="remote",
            content="c",
            tenant_id="t",
        )
        storage = MagicMock()
        storage.get_node.return_value = node
        g = GovernanceKnowledgeGraph(storage=storage)
        result = g.get_node("remote-1")
        assert result is node
        storage.get_node.assert_called_once_with("remote-1")
        # Second call should use cache
        result2 = g.get_node("remote-1")
        assert result2 is node
        assert storage.get_node.call_count == 1

    def test_get_node_storage_returns_none(self):
        storage = MagicMock()
        storage.get_node.return_value = None
        g = GovernanceKnowledgeGraph(storage=storage)
        assert g.get_node("missing") is None

    def test_get_neighbors(self, graph, make_node, make_edge):
        a = make_node(node_id="a")
        b = make_node(node_id="b")
        c = make_node(node_id="c")
        graph.add_node(a)
        graph.add_node(b)
        graph.add_node(c)
        graph.add_edge(make_edge(source_id="a", target_id="b", edge_type=EdgeType.IMPLEMENTS))
        graph.add_edge(make_edge(source_id="a", target_id="c", edge_type=EdgeType.REQUIRES))

        # All neighbors
        neighbors = graph.get_neighbors("a")
        assert len(neighbors) == 2

        # Filtered by edge type
        filtered = graph.get_neighbors("a", edge_types=[EdgeType.IMPLEMENTS])
        assert len(filtered) == 1
        assert filtered[0].node_id == "b"

    def test_get_neighbors_empty(self, graph, make_node):
        graph.add_node(make_node(node_id="lonely"))
        assert graph.get_neighbors("lonely") == []
        assert graph.get_neighbors("nonexistent") == []

    def test_get_incoming(self, graph, make_node, make_edge):
        a = make_node(node_id="a")
        b = make_node(node_id="b")
        graph.add_node(a)
        graph.add_node(b)
        graph.add_edge(make_edge(source_id="a", target_id="b", edge_type=EdgeType.IMPLEMENTS))
        incoming = graph.get_incoming("b")
        assert len(incoming) == 1
        assert incoming[0].node_id == "a"

    def test_get_incoming_filtered(self, graph, make_node, make_edge):
        a = make_node(node_id="a")
        b = make_node(node_id="b")
        c = make_node(node_id="c")
        graph.add_node(a)
        graph.add_node(b)
        graph.add_node(c)
        graph.add_edge(make_edge(source_id="a", target_id="c", edge_type=EdgeType.IMPLEMENTS))
        graph.add_edge(make_edge(source_id="b", target_id="c", edge_type=EdgeType.REQUIRES))
        filtered = graph.get_incoming("c", edge_types=[EdgeType.REQUIRES])
        assert len(filtered) == 1
        assert filtered[0].node_id == "b"

    def test_traverse_bfs_basic(self, graph, make_node, make_edge):
        for nid in ("a", "b", "c", "d"):
            graph.add_node(make_node(node_id=nid))
        graph.add_edge(make_edge(source_id="a", target_id="b"))
        graph.add_edge(make_edge(source_id="b", target_id="c"))
        graph.add_edge(make_edge(source_id="c", target_id="d"))

        result = graph.traverse_bfs("a", max_depth=2)
        ids = [n.node_id for n in result]
        assert "a" in ids
        assert "b" in ids
        assert "c" in ids
        assert "d" not in ids  # depth 3, exceeds max_depth=2

    def test_traverse_bfs_with_filter(self, graph, make_node, make_edge):
        graph.add_node(make_node(node_id="p1", node_type=NodeType.POLICY))
        graph.add_node(make_node(node_id="r1", node_type=NodeType.RULE))
        graph.add_edge(make_edge(source_id="p1", target_id="r1"))

        result = graph.traverse_bfs("p1", node_filter=lambda n: n.node_type == NodeType.RULE)
        assert len(result) == 1
        assert result[0].node_id == "r1"

    def test_traverse_bfs_handles_cycles(self, graph, make_node, make_edge):
        graph.add_node(make_node(node_id="x"))
        graph.add_node(make_node(node_id="y"))
        graph.add_edge(make_edge(edge_id="xy", source_id="x", target_id="y"))
        graph.add_edge(make_edge(edge_id="yx", source_id="y", target_id="x"))
        result = graph.traverse_bfs("x", max_depth=10)
        assert len(result) == 2

    def test_find_path_same_node(self, graph, make_node):
        graph.add_node(make_node(node_id="s"))
        assert graph.find_path("s", "s") == ["s"]

    def test_find_path_direct(self, graph, make_node, make_edge):
        graph.add_node(make_node(node_id="a"))
        graph.add_node(make_node(node_id="b"))
        graph.add_edge(make_edge(source_id="a", target_id="b"))
        assert graph.find_path("a", "b") == ["a", "b"]

    def test_find_path_multi_hop(self, graph, make_node, make_edge):
        for nid in ("a", "b", "c"):
            graph.add_node(make_node(node_id=nid))
        graph.add_edge(make_edge(edge_id="e1", source_id="a", target_id="b"))
        graph.add_edge(make_edge(edge_id="e2", source_id="b", target_id="c"))
        assert graph.find_path("a", "c") == ["a", "b", "c"]

    def test_find_path_no_path(self, graph, make_node):
        graph.add_node(make_node(node_id="a"))
        graph.add_node(make_node(node_id="b"))
        assert graph.find_path("a", "b") is None

    def test_find_path_exceeds_max_depth(self, graph, make_node, make_edge):
        # Chain a -> b -> c -> d -> e, max_depth=2 should not find a->e
        for nid in ("a", "b", "c", "d", "e"):
            graph.add_node(make_node(node_id=nid))
        for s, t, eid in [("a", "b", "e1"), ("b", "c", "e2"), ("c", "d", "e3"), ("d", "e", "e4")]:
            graph.add_edge(make_edge(edge_id=eid, source_id=s, target_id=t))
        assert graph.find_path("a", "e", max_depth=2) is None

    def test_get_subgraph_with_edges(self, graph, make_node, make_edge):
        graph.add_node(make_node(node_id="a"))
        graph.add_node(make_node(node_id="b"))
        graph.add_node(make_node(node_id="c"))
        graph.add_edge(make_edge(edge_id="ab", source_id="a", target_id="b"))
        graph.add_edge(make_edge(edge_id="ac", source_id="a", target_id="c"))
        graph.add_edge(make_edge(edge_id="bc", source_id="b", target_id="c"))

        nodes, edges = graph.get_subgraph(["a", "b"])
        assert len(nodes) == 2
        assert len(edges) == 1  # only ab (both endpoints in subgraph)

    def test_get_subgraph_without_edges(self, graph, make_node, make_edge):
        graph.add_node(make_node(node_id="a"))
        graph.add_node(make_node(node_id="b"))
        graph.add_edge(make_edge(source_id="a", target_id="b"))
        nodes, edges = graph.get_subgraph(["a", "b"], include_edges=False)
        assert len(nodes) == 2
        assert edges == []

    def test_get_subgraph_missing_node(self, graph, make_node):
        graph.add_node(make_node(node_id="a"))
        nodes, edges = graph.get_subgraph(["a", "missing"])
        assert len(nodes) == 1
        assert nodes[0].node_id == "a"


# ===================================================================
# PolicyGraphExtractor tests
# ===================================================================


class TestPolicyGraphExtractor:
    SAMPLE_REGO = """\
package governance.safety

deny[msg] {
    input.action == "harm"
    msg := "harmful action blocked"
}

allow {
    input.role == "admin"
}
"""

    @pytest.fixture()
    def extractor(self, graph):
        return PolicyGraphExtractor(graph, tenant_id="t1")

    def test_extract_from_rego_creates_policy_node(self, extractor, graph):
        nodes = extractor.extract_from_rego("safety-v1", self.SAMPLE_REGO)
        policy = graph.get_node("policy:safety-v1")
        assert policy is not None
        assert policy.node_type == NodeType.POLICY
        assert policy.content == self.SAMPLE_REGO
        assert policy.metadata["source"] == "rego"
        assert policy.metadata["line_count"] > 0

    def test_extract_from_rego_creates_rule_nodes(self, extractor, graph):
        nodes = extractor.extract_from_rego("safety-v1", self.SAMPLE_REGO)
        # Should find deny and allow rules (not package/import)
        rule_nodes = [n for n in nodes if n.node_type == NodeType.RULE]
        assert len(rule_nodes) >= 1
        # All returned nodes should be in the graph
        for n in nodes:
            assert graph.get_node(n.node_id) is not None

    def test_extract_from_rego_creates_edges(self, extractor, graph):
        extractor.extract_from_rego("safety-v1", self.SAMPLE_REGO)
        assert graph.edge_count > 0

    def test_extract_from_rego_empty_content(self, extractor, graph):
        nodes = extractor.extract_from_rego("empty", "")
        # At least the policy node itself
        assert len(nodes) >= 1
        assert graph.get_node("policy:empty") is not None

    def test_extract_from_principle(self, extractor, graph):
        node = extractor.extract_from_principle(
            "fairness", "All decisions must be fair and unbiased"
        )
        assert node.node_id == "principle:fairness"
        assert node.node_type == NodeType.PRINCIPLE
        assert node.metadata["word_count"] == 7
        assert graph.get_node("principle:fairness") is not None

    def test_extract_from_principle_with_related_policies(self, extractor, graph):
        # First add a policy so the related link can be created
        extractor.extract_from_rego("safety-v1", self.SAMPLE_REGO)
        node = extractor.extract_from_principle(
            "safety",
            "Safety first principle",
            related_policies=["safety-v1"],
        )
        # Should have created an edge from the policy to the principle
        assert graph.edge_count > 1  # rego edges + principle link

    def test_extract_from_principle_with_missing_related_policy(self, extractor, graph):
        """Related policy that doesn't exist in the graph should be silently skipped."""
        node = extractor.extract_from_principle(
            "orphan",
            "Orphaned principle",
            related_policies=["nonexistent"],
        )
        assert node is not None
        # Only the principle node, no edge for the missing policy
        assert graph.edge_count == 0

    def test_extract_constraints(self, extractor, graph):
        extractor.extract_from_rego("safety-v1", self.SAMPLE_REGO)
        constraints = extractor.extract_constraints("safety-v1", self.SAMPLE_REGO)
        assert len(constraints) >= 1
        for c in constraints:
            assert c.node_type == NodeType.CONSTRAINT
            assert c.metadata["type"] == "deny"
            assert graph.get_node(c.node_id) is not None

    def test_extract_constraints_no_deny_blocks(self, extractor, graph):
        rego = "package test\nallow { true }\n"
        constraints = extractor.extract_constraints("no-deny", rego)
        assert constraints == []


# ===================================================================
# GraphSimilaritySearch tests
# ===================================================================


class TestGraphSimilaritySearch:
    @pytest.fixture()
    def populated_graph(self, graph, make_node):
        """Graph with several embedded nodes."""
        nodes = [
            make_node(
                node_id="p1",
                node_type=NodeType.POLICY,
                content="safety policy",
                tenant_id="t1",
                embedding=[1.0, 0.0, 0.0],
            ),
            make_node(
                node_id="p2",
                node_type=NodeType.POLICY,
                content="fairness policy",
                tenant_id="t1",
                embedding=[0.0, 1.0, 0.0],
            ),
            make_node(
                node_id="r1",
                node_type=NodeType.RULE,
                content="safety rule body",
                tenant_id="t1",
                embedding=[0.9, 0.1, 0.0],
            ),
            make_node(
                node_id="other-tenant",
                node_type=NodeType.POLICY,
                content="other tenant policy",
                tenant_id="t2",
                embedding=[1.0, 0.0, 0.0],
            ),
            make_node(
                node_id="no-embed",
                node_type=NodeType.POLICY,
                content="no embedding node",
                tenant_id="t1",
                embedding=None,
            ),
        ]
        for n in nodes:
            graph.add_node(n)
        return graph

    def test_search_by_embedding(self, populated_graph):
        search = GraphSimilaritySearch(populated_graph)
        results = search.search_by_embedding([1.0, 0.0, 0.0], tenant_id="t1")
        assert len(results) >= 1
        # p1 should be the best match (identical vector)
        assert results[0].node.node_id == "p1"
        assert results[0].score == pytest.approx(1.0)

    def test_search_by_embedding_filters_tenant(self, populated_graph):
        search = GraphSimilaritySearch(populated_graph)
        results = search.search_by_embedding([1.0, 0.0, 0.0], tenant_id="t2")
        assert all(r.node.tenant_id == "t2" for r in results)

    def test_search_by_embedding_filters_node_types(self, populated_graph):
        search = GraphSimilaritySearch(populated_graph)
        results = search.search_by_embedding(
            [1.0, 0.0, 0.0],
            tenant_id="t1",
            node_types=[NodeType.RULE],
        )
        assert all(r.node.node_type == NodeType.RULE for r in results)

    def test_search_by_embedding_min_score(self, populated_graph):
        search = GraphSimilaritySearch(populated_graph)
        results = search.search_by_embedding(
            [1.0, 0.0, 0.0],
            tenant_id="t1",
            min_score=0.999,
        )
        assert len(results) == 1
        assert results[0].node.node_id == "p1"

    def test_search_by_embedding_top_k(self, populated_graph):
        search = GraphSimilaritySearch(populated_graph)
        results = search.search_by_embedding(
            [1.0, 0.0, 0.0],
            tenant_id="t1",
            top_k=1,
        )
        assert len(results) == 1

    def test_search_by_embedding_skips_none_embeddings(self, populated_graph):
        search = GraphSimilaritySearch(populated_graph)
        results = search.search_by_embedding([1.0, 0.0, 0.0], tenant_id="t1")
        result_ids = {r.node.node_id for r in results}
        assert "no-embed" not in result_ids

    def test_search_by_text_uses_provider(self, populated_graph):
        provider = MagicMock()
        provider.embed.return_value = [1.0, 0.0, 0.0]
        search = GraphSimilaritySearch(populated_graph, embedding_provider=provider)
        results = search.search_by_text("safety", tenant_id="t1")
        provider.embed.assert_called_once_with("safety")
        assert len(results) >= 1

    def test_search_by_text_fallback_without_provider(self, populated_graph):
        search = GraphSimilaritySearch(populated_graph)
        results = search.search_by_text("safety", tenant_id="t1")
        # Fallback text search: nodes containing "safety"
        assert len(results) >= 1
        assert any("safety" in r.node.content for r in results)

    def test_fallback_text_search_no_matches(self, populated_graph):
        search = GraphSimilaritySearch(populated_graph)
        results = search.search_by_text("zzzznotfound", tenant_id="t1")
        assert results == []

    def test_fallback_text_search_respects_tenant(self, populated_graph):
        search = GraphSimilaritySearch(populated_graph)
        results = search.search_by_text("policy", tenant_id="t2")
        assert all(r.node.tenant_id == "t2" for r in results)

    def test_fallback_text_search_respects_node_types(self, populated_graph):
        search = GraphSimilaritySearch(populated_graph)
        results = search.search_by_text("safety", tenant_id="t1", node_types=[NodeType.RULE])
        assert all(r.node.node_type == NodeType.RULE for r in results)

    def test_search_with_context(self, graph, make_node, make_edge):
        # Build a small graph with connected nodes
        p = make_node(
            node_id="p1",
            node_type=NodeType.POLICY,
            content="safety policy",
            tenant_id="t1",
        )
        r = make_node(
            node_id="r1",
            node_type=NodeType.RULE,
            content="safety rule",
            tenant_id="t1",
        )
        graph.add_node(p)
        graph.add_node(r)
        graph.add_edge(make_edge(source_id="p1", target_id="r1"))

        search = GraphSimilaritySearch(graph)
        results = search.search_with_context("safety", tenant_id="t1")
        assert len(results) >= 1
        # At least one result should have context nodes
        has_context = any(len(r.context_nodes) > 0 for r in results)
        assert has_context

    def test_find_related_policies(self, graph, make_node, make_edge):
        graph.add_node(make_node(node_id="r1", node_type=NodeType.RULE))
        graph.add_node(make_node(node_id="p1", node_type=NodeType.POLICY))
        graph.add_edge(make_edge(source_id="r1", target_id="p1"))
        search = GraphSimilaritySearch(graph)
        policies = search.find_related_policies("r1")
        assert any(n.node_type == NodeType.POLICY for n in policies)

    def test_find_implementing_rules(self, graph, make_node, make_edge):
        # principle <- IMPLEMENTS - policy -> IMPLEMENTS -> rule
        graph.add_node(make_node(node_id="principle:fair", node_type=NodeType.PRINCIPLE))
        graph.add_node(make_node(node_id="policy:p1", node_type=NodeType.POLICY))
        graph.add_node(make_node(node_id="rule:r1", node_type=NodeType.RULE))
        graph.add_edge(
            make_edge(
                edge_id="e1",
                source_id="policy:p1",
                target_id="principle:fair",
                edge_type=EdgeType.IMPLEMENTS,
            )
        )
        graph.add_edge(
            make_edge(
                edge_id="e2",
                source_id="policy:p1",
                target_id="rule:r1",
                edge_type=EdgeType.IMPLEMENTS,
            )
        )
        search = GraphSimilaritySearch(graph)
        rules = search.find_implementing_rules("fair")
        assert len(rules) == 1
        assert rules[0].node_id == "rule:r1"


# ===================================================================
# Cosine similarity edge cases
# ===================================================================


class TestCosineSimilarity:
    def _sim(self, v1, v2):
        search = GraphSimilaritySearch(GovernanceKnowledgeGraph())
        return search._cosine_similarity(v1, v2)

    def test_identical_vectors(self):
        assert self._sim([1, 0, 0], [1, 0, 0]) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        assert self._sim([1, 0, 0], [0, 1, 0]) == pytest.approx(0.0)

    def test_opposite_vectors(self):
        assert self._sim([1, 0], [-1, 0]) == pytest.approx(-1.0)

    def test_different_length_returns_zero(self):
        assert self._sim([1, 0], [1, 0, 0]) == 0.0

    def test_zero_vector_returns_zero(self):
        assert self._sim([0, 0, 0], [1, 0, 0]) == 0.0

    def test_both_zero_vectors(self):
        assert self._sim([0, 0], [0, 0]) == 0.0


# ===================================================================
# build_governance_context tests
# ===================================================================


class TestBuildGovernanceContext:
    def test_basic_output(self, make_node):
        node = make_node(
            node_id="p1",
            node_type=NodeType.POLICY,
            name="safety-v1",
            content="Do no harm",
        )
        result = SearchResult(node=node, score=0.95)
        ctx = build_governance_context(GovernanceKnowledgeGraph(), [result])
        assert "safety-v1" in ctx
        assert "Do no harm" in ctx
        assert "[policy]" in ctx

    def test_includes_context_nodes(self, make_node):
        main_node = make_node(
            node_id="p1",
            node_type=NodeType.POLICY,
            name="main",
            content="main content",
        )
        ctx_node = make_node(
            node_id="r1",
            node_type=NodeType.RULE,
            name="related-rule",
            content="rule content",
        )
        result = SearchResult(node=main_node, score=0.9, context_nodes=[ctx_node])
        ctx = build_governance_context(GovernanceKnowledgeGraph(), [result])
        assert "related-rule" in ctx
        assert "Related" in ctx

    def test_respects_max_tokens(self, make_node):
        results = []
        for i in range(50):
            n = make_node(
                node_id=f"n{i}",
                node_type=NodeType.POLICY,
                name=f"policy-{i}",
                content="word " * 100,
            )
            results.append(SearchResult(node=n, score=0.5))
        ctx = build_governance_context(GovernanceKnowledgeGraph(), results, max_tokens=50)
        # Should truncate before including all 50
        assert ctx.count("policy-") < 50

    def test_empty_results(self):
        ctx = build_governance_context(GovernanceKnowledgeGraph(), [])
        assert ctx == ""

    def test_context_nodes_limited_to_three(self, make_node):
        main = make_node(node_id="m", node_type=NodeType.POLICY, name="main", content="c")
        ctx_nodes = [
            make_node(node_id=f"c{i}", node_type=NodeType.RULE, name=f"ctx-{i}", content="x")
            for i in range(10)
        ]
        result = SearchResult(node=main, score=0.9, context_nodes=ctx_nodes)
        ctx = build_governance_context(GovernanceKnowledgeGraph(), [result], max_tokens=10000)
        # Only first 3 context nodes should appear
        for i in range(3):
            assert f"ctx-{i}" in ctx
        assert "ctx-5" not in ctx


# ===================================================================
# SearchResult dataclass
# ===================================================================


class TestSearchResult:
    def test_defaults(self, make_node):
        node = make_node()
        r = SearchResult(node=node, score=0.8)
        assert r.path == []
        assert r.context_nodes == []
        assert r.score == 0.8
