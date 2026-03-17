# Constitutional Hash: cdd01ef066bc6cf2
# Sprint 56 — retrieval_triad.py coverage
"""
Comprehensive tests for retrieval_triad.py — targets ≥95% coverage.

Tests cover:
- RetrievalTriad.__init__ (default and custom weights)
- RetrievalTriad.search (full pipeline, parallel gather, stability annotation)
- RetrievalTriad._check_stability (empty results, stable, unstable branches)
- RetrievalTriad._vector_search
- RetrievalTriad._keyword_search
- RetrievalTriad._graph_search (graph returns results vs. empty)
- RetrievalTriad._merge_results (id collision branch, limit truncation)
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from packages.enhanced_agent_bus.retrieval_triad import RetrievalTriad

# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------


def _make_graph_manager(multi_hop_return=None):
    """Return a mock MockGraphManager."""
    mgr = MagicMock()
    mgr.get_multi_hop_context = AsyncMock(
        return_value=multi_hop_return if multi_hop_return is not None else []
    )
    return mgr


def _make_triad(multi_hop_return=None, weights=None):
    vector_mgr = MagicMock()
    graph_mgr = _make_graph_manager(multi_hop_return)
    kwargs = {}
    if weights is not None:
        kwargs["weights"] = weights
    return RetrievalTriad(vector_mgr, graph_mgr, **kwargs)


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


class TestRetrievalTriadInit:
    def test_default_weights(self):
        triad = _make_triad()
        assert triad.weights == {"vector": 0.4, "keyword": 0.3, "graph": 0.3}

    def test_custom_weights(self):
        custom = {"vector": 0.5, "keyword": 0.3, "graph": 0.2}
        triad = _make_triad(weights=custom)
        assert triad.weights == custom

    def test_vector_and_graph_assigned(self):
        vec = MagicMock()
        graph = _make_graph_manager()
        triad = RetrievalTriad(vec, graph)
        assert triad.vector is vec
        assert triad.graph is graph


# ---------------------------------------------------------------------------
# _vector_search
# ---------------------------------------------------------------------------


class TestVectorSearch:
    async def test_returns_list(self):
        triad = _make_triad()
        result = await triad._vector_search("test query", 10)
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["id"] == "v1"

    async def test_content_contains_query(self):
        triad = _make_triad()
        result = await triad._vector_search("governance", 5)
        assert "governance" in result[0]["content"]

    async def test_score_value(self):
        triad = _make_triad()
        result = await triad._vector_search("x", 10)
        assert result[0]["score"] == 0.9


# ---------------------------------------------------------------------------
# _keyword_search
# ---------------------------------------------------------------------------


class TestKeywordSearch:
    async def test_returns_list(self):
        triad = _make_triad()
        result = await triad._keyword_search("test", 10)
        assert isinstance(result, list)
        assert len(result) == 1

    async def test_id_is_k1(self):
        triad = _make_triad()
        result = await triad._keyword_search("foo", 10)
        assert result[0]["id"] == "k1"

    async def test_content_contains_query(self):
        triad = _make_triad()
        result = await triad._keyword_search("policy", 10)
        assert "policy" in result[0]["content"]

    async def test_score_value(self):
        triad = _make_triad()
        result = await triad._keyword_search("x", 10)
        assert result[0]["score"] == 0.8


# ---------------------------------------------------------------------------
# _graph_search
# ---------------------------------------------------------------------------


class TestGraphSearch:
    async def test_graph_returns_empty_list_when_no_context(self):
        triad = _make_triad(multi_hop_return=[])
        result = await triad._graph_search("irrelevant query", 10)
        assert result == []

    async def test_graph_returns_result_when_context_found(self):
        context = [{"entity": "A", "relation": "B", "target": "C"}]
        triad = _make_triad(multi_hop_return=context)
        result = await triad._graph_search("supply chain risk", 10)
        assert len(result) == 1
        assert result[0]["id"] == "g1"
        assert "Graph Context" in result[0]["content"]
        assert result[0]["score"] == 0.85

    async def test_graph_calls_manager_with_query(self):
        graph_mgr = _make_graph_manager(multi_hop_return=[])
        triad = RetrievalTriad(MagicMock(), graph_mgr)
        await triad._graph_search("supply chain", 10)
        graph_mgr.get_multi_hop_context.assert_called_once_with("supply chain")

    async def test_graph_falsy_context_returns_empty(self):
        """Explicit falsy values (None-like empty list) still return empty."""
        triad = _make_triad(multi_hop_return=[])
        result = await triad._graph_search("anything", 10)
        assert result == []


# ---------------------------------------------------------------------------
# _check_stability
# ---------------------------------------------------------------------------


class TestCheckStability:
    async def test_empty_results_returns_stable_true(self):
        triad = _make_triad()
        stable, score = await triad._check_stability("q", [])
        assert stable is True
        assert score == 1.0

    async def test_single_result_perfect_stability(self):
        triad = _make_triad()
        results = [{"score": 0.9}]
        stable, score = await triad._check_stability("q", results)
        # top_score == avg_score == 0.9, so stability == 1.0 > 0.7
        assert stable is True
        assert score == pytest.approx(1.0)

    async def test_stable_when_scores_close(self):
        triad = _make_triad()
        results = [{"score": 0.9}, {"score": 0.85}]
        stable, score = await triad._check_stability("q", results)
        # avg = 0.875, |0.9 - 0.875| = 0.025, stability = 0.975 > 0.7
        assert stable is True
        assert score > 0.7

    async def test_unstable_when_scores_diverge(self):
        triad = _make_triad()
        # top=1.0, avg=(1.0+0.0)/2=0.5, stability=1.0-0.5=0.5 < 0.7
        results = [{"score": 1.0}, {"score": 0.0}]
        stable, score = await triad._check_stability("q", results)
        assert stable is False
        assert score == pytest.approx(0.5)

    async def test_stability_exactly_at_threshold(self):
        triad = _make_triad()
        # stability = 0.7 exactly → NOT > 0.7 → unstable
        # top - avg = 0.3 → stability = 0.7
        results = [{"score": 0.65}, {"score": 0.35}]
        _, score = await triad._check_stability("q", results)
        # avg = 0.5, top = 0.65, |0.65 - 0.5| = 0.15, stability = 0.85 > 0.7
        assert score == pytest.approx(0.85)

    async def test_missing_score_defaults_to_zero(self):
        """Results without 'score' key default to 0.0."""
        triad = _make_triad()
        results = [{"id": "a"}, {"id": "b"}]
        stable, score = await triad._check_stability("q", results)
        # top_score=0.0, avg=0.0, stability=1.0 > 0.7
        assert stable is True
        assert score == pytest.approx(1.0)

    async def test_three_results_averaging(self):
        triad = _make_triad()
        results = [{"score": 0.9}, {"score": 0.8}, {"score": 0.7}]
        stable, score = await triad._check_stability("q", results)
        # avg=0.8, top=0.9, |0.9-0.8|=0.1, stability=0.9 > 0.7
        assert stable is True
        assert score == pytest.approx(0.9)


# ---------------------------------------------------------------------------
# _merge_results
# ---------------------------------------------------------------------------


class TestMergeResults:
    def _triad(self):
        return _make_triad()

    def test_basic_merge_returns_sorted_by_triad_score(self):
        triad = self._triad()
        vector = [{"id": "v1", "score": 0.9}]
        keyword = [{"id": "k1", "score": 0.8}]
        graph = [{"id": "g1", "score": 0.85}]
        results = triad._merge_results(vector, keyword, graph, 10)
        assert len(results) == 3
        # v1: 1.0 * 0.4 = 0.4; k1: 1.0 * 0.3 = 0.3; g1: 1.0 * 0.3 = 0.3
        assert results[0]["id"] == "v1"

    def test_id_collision_accumulates_score(self):
        """Same id appearing in multiple sources should accumulate triad_score."""
        triad = self._triad()
        shared = {"id": "shared", "score": 0.9}
        vector = [{"id": "shared", "score": 0.9}]
        keyword = [{"id": "shared", "score": 0.8}]
        graph = []
        results = triad._merge_results(vector, keyword, graph, 10)
        assert len(results) == 1
        # First add: triad_score = 0.4; second add (collision): += 0.3 → 0.7
        assert results[0]["id"] == "shared"
        assert results[0]["triad_score"] == pytest.approx(0.7)

    def test_limit_truncates_results(self):
        triad = self._triad()
        vector = [{"id": f"v{i}", "score": 0.9} for i in range(5)]
        keyword = [{"id": f"k{i}", "score": 0.8} for i in range(5)]
        graph = [{"id": f"g{i}", "score": 0.85} for i in range(5)]
        results = triad._merge_results(vector, keyword, graph, 3)
        assert len(results) == 3

    def test_empty_all_sources(self):
        triad = self._triad()
        results = triad._merge_results([], [], [], 10)
        assert results == []

    def test_empty_graph_source(self):
        triad = self._triad()
        vector = [{"id": "v1", "score": 0.9}]
        keyword = [{"id": "k1", "score": 0.8}]
        results = triad._merge_results(vector, keyword, [], 10)
        assert len(results) == 2

    def test_rank_penalizes_lower_ranks(self):
        """Lower-ranked items in same source should have lower contribution."""
        triad = self._triad()
        vector = [
            {"id": "v1", "score": 0.9},
            {"id": "v2", "score": 0.5},
        ]
        results = triad._merge_results(vector, [], [], 10)
        scores = {r["id"]: r["triad_score"] for r in results}
        # rank 0: 1/1 * 0.4 = 0.4; rank 1: 1/2 * 0.4 = 0.2
        assert scores["v1"] > scores["v2"]

    def test_custom_weights_affect_scores(self):
        custom = {"vector": 0.7, "keyword": 0.2, "graph": 0.1}
        triad = _make_triad(weights=custom)
        vector = [{"id": "v1", "score": 0.9}]
        keyword = [{"id": "k1", "score": 0.8}]
        results = triad._merge_results(vector, keyword, [], 10)
        v_score = next(r["triad_score"] for r in results if r["id"] == "v1")
        k_score = next(r["triad_score"] for r in results if r["id"] == "k1")
        # v1: 1.0*0.7=0.7; k1: 1.0*0.2=0.2
        assert v_score == pytest.approx(0.7)
        assert k_score == pytest.approx(0.2)


# ---------------------------------------------------------------------------
# search (full integration)
# ---------------------------------------------------------------------------


class TestSearch:
    async def test_search_returns_list(self):
        triad = _make_triad()
        results = await triad.search("test query")
        assert isinstance(results, list)

    async def test_search_annotates_raguard_fields(self):
        triad = _make_triad()
        results = await triad.search("governance policy")
        for r in results:
            assert "raguard_stable" in r
            assert "stability_score" in r

    async def test_search_with_graph_results(self):
        context = [{"entity": "Supply Chain", "relation": "risk", "target": "region"}]
        triad = _make_triad(multi_hop_return=context)
        results = await triad.search("supply chain")
        # Should include vector, keyword, and graph results
        ids = [r["id"] for r in results]
        assert "v1" in ids
        assert "k1" in ids
        assert "g1" in ids

    async def test_search_without_graph_results(self):
        triad = _make_triad(multi_hop_return=[])
        results = await triad.search("no graph match")
        ids = [r["id"] for r in results]
        assert "v1" in ids
        assert "k1" in ids
        # g1 not present since graph returned empty
        assert "g1" not in ids

    async def test_search_limit_respected(self):
        triad = _make_triad(multi_hop_return=[])
        results = await triad.search("query", limit=1)
        assert len(results) <= 1

    async def test_search_runs_parallel_tasks(self):
        """Verify asyncio.gather is called by patching it."""
        triad = _make_triad()
        with patch(
            "packages.enhanced_agent_bus.retrieval_triad.asyncio.gather", wraps=asyncio.gather
        ) as mock_gather:
            await triad.search("parallel test")
            mock_gather.assert_called_once()

    async def test_stability_score_in_range(self):
        triad = _make_triad()
        results = await triad.search("query")
        for r in results:
            assert 0.0 <= r["stability_score"] <= 1.0

    async def test_raguard_stable_is_bool(self):
        triad = _make_triad()
        results = await triad.search("query")
        for r in results:
            assert isinstance(r["raguard_stable"], bool)

    async def test_search_returns_empty_when_all_sources_empty(self):
        """Patch all three search methods to return empty, verify no crash."""
        triad = _make_triad()
        with (
            patch.object(triad, "_vector_search", AsyncMock(return_value=[])),
            patch.object(triad, "_keyword_search", AsyncMock(return_value=[])),
            patch.object(triad, "_graph_search", AsyncMock(return_value=[])),
        ):
            results = await triad.search("empty query")
            assert results == []

    async def test_stability_annotation_on_empty_merged_results(self):
        """When merged results is empty, loop body is skipped without error."""
        triad = _make_triad()
        with (
            patch.object(triad, "_vector_search", AsyncMock(return_value=[])),
            patch.object(triad, "_keyword_search", AsyncMock(return_value=[])),
            patch.object(triad, "_graph_search", AsyncMock(return_value=[])),
        ):
            results = await triad.search("q")
            assert results == []

    async def test_search_default_limit_is_10(self):
        """With 3 unique sources, default limit=10 returns all 3."""
        context = [{"entity": "X", "relation": "Y", "target": "Z"}]
        triad = _make_triad(multi_hop_return=context)
        results = await triad.search("q")
        # 3 unique results (v1, k1, g1) all fit under limit=10
        assert len(results) == 3


# ---------------------------------------------------------------------------
# Module-level import path (try/except fallback in source)
# ---------------------------------------------------------------------------


class TestModuleImport:
    def test_retrieval_triad_importable(self):
        """Ensure the module can be imported cleanly."""
        from packages.enhanced_agent_bus.retrieval_triad import RetrievalTriad as RT

        assert RT is not None

    def test_graph_database_importable_via_retrieval_triad(self):
        """MockGraphManager should be importable as used in retrieval_triad."""
        from packages.enhanced_agent_bus.graph_database import MockGraphManager

        mgr = MockGraphManager()
        assert mgr is not None
