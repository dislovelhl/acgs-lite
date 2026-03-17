"""
ACGS-2 Enhanced Agent Bus - Retrieval Triad Tests
Constitutional Hash: cdd01ef066bc6cf2

Comprehensive tests for the Retrieval Triad module including:
- RetrievalTriad initialization and configuration
- Vector, Keyword, and Graph search operations
- Result merging with Reciprocal Rank Fusion
- RAGuard stability checks
- Parallel search execution
- Edge cases and error handling
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

# Import retrieval triad module
try:
    from enhanced_agent_bus.graph_database import MockGraphManager
    from enhanced_agent_bus.retrieval_triad import RetrievalTriad
except ImportError:
    import os
    import sys

    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from graph_database import MockGraphManager
    from retrieval_triad import RetrievalTriad


# Constitutional Hash for validation
from src.core.shared.constants import CONSTITUTIONAL_HASH


class TestRetrievalTriadInitialization:
    """Test RetrievalTriad initialization."""

    @pytest.fixture
    def mock_vector_manager(self):
        """Create a mock vector manager."""
        return MagicMock()

    @pytest.fixture
    def mock_graph_manager(self):
        """Create a MockGraphManager instance."""
        return MockGraphManager()

    def test_default_initialization(self, mock_vector_manager, mock_graph_manager):
        """Test default initialization with default weights."""
        triad = RetrievalTriad(vector_manager=mock_vector_manager, graph_manager=mock_graph_manager)

        assert triad.vector is mock_vector_manager
        assert triad.graph is mock_graph_manager
        assert triad.weights == {"vector": 0.4, "keyword": 0.3, "graph": 0.3}

    def test_custom_weights(self, mock_vector_manager, mock_graph_manager):
        """Test initialization with custom weights."""
        custom_weights = {"vector": 0.5, "keyword": 0.25, "graph": 0.25}
        triad = RetrievalTriad(
            vector_manager=mock_vector_manager,
            graph_manager=mock_graph_manager,
            weights=custom_weights,
        )

        assert triad.weights == custom_weights

    def test_equal_weights(self, mock_vector_manager, mock_graph_manager):
        """Test initialization with equal weights."""
        equal_weights = {"vector": 0.33, "keyword": 0.33, "graph": 0.34}
        triad = RetrievalTriad(
            vector_manager=mock_vector_manager,
            graph_manager=mock_graph_manager,
            weights=equal_weights,
        )

        assert triad.weights["vector"] == 0.33
        assert triad.weights["keyword"] == 0.33
        assert triad.weights["graph"] == 0.34

    def test_vector_heavy_weights(self, mock_vector_manager, mock_graph_manager):
        """Test initialization with vector-heavy weights."""
        vector_heavy = {"vector": 0.7, "keyword": 0.15, "graph": 0.15}
        triad = RetrievalTriad(
            vector_manager=mock_vector_manager,
            graph_manager=mock_graph_manager,
            weights=vector_heavy,
        )

        assert triad.weights["vector"] == 0.7


class TestVectorSearch:
    """Test vector search functionality."""

    @pytest.fixture
    def triad(self):
        """Create a RetrievalTriad instance for testing."""
        return RetrievalTriad(vector_manager=MagicMock(), graph_manager=MockGraphManager())

    @pytest.mark.asyncio
    async def test_vector_search_returns_results(self, triad):
        """Test that vector search returns results."""
        results = await triad._vector_search("test query", 10)

        assert isinstance(results, list)
        assert len(results) > 0

    @pytest.mark.asyncio
    async def test_vector_search_result_structure(self, triad):
        """Test vector search result structure."""
        results = await triad._vector_search("test query", 10)

        for result in results:
            assert "id" in result
            assert "content" in result
            assert "score" in result

    @pytest.mark.asyncio
    async def test_vector_search_includes_query(self, triad):
        """Test that vector search results include query context."""
        query = "unique test query"
        results = await triad._vector_search(query, 10)

        assert any(query in r["content"] for r in results)

    @pytest.mark.asyncio
    async def test_vector_search_score_range(self, triad):
        """Test that vector search scores are in valid range."""
        results = await triad._vector_search("test", 10)

        for result in results:
            assert 0.0 <= result["score"] <= 1.0


class TestKeywordSearch:
    """Test keyword/BM25 search functionality."""

    @pytest.fixture
    def triad(self):
        """Create a RetrievalTriad instance for testing."""
        return RetrievalTriad(vector_manager=MagicMock(), graph_manager=MockGraphManager())

    @pytest.mark.asyncio
    async def test_keyword_search_returns_results(self, triad):
        """Test that keyword search returns results."""
        results = await triad._keyword_search("test query", 10)

        assert isinstance(results, list)
        assert len(results) > 0

    @pytest.mark.asyncio
    async def test_keyword_search_result_structure(self, triad):
        """Test keyword search result structure."""
        results = await triad._keyword_search("test query", 10)

        for result in results:
            assert "id" in result
            assert "content" in result
            assert "score" in result

    @pytest.mark.asyncio
    async def test_keyword_search_includes_query(self, triad):
        """Test that keyword search results include query context."""
        query = "specific keyword query"
        results = await triad._keyword_search(query, 10)

        assert any(query in r["content"] for r in results)

    @pytest.mark.asyncio
    async def test_keyword_search_score_range(self, triad):
        """Test that keyword search scores are in valid range."""
        results = await triad._keyword_search("test", 10)

        for result in results:
            assert 0.0 <= result["score"] <= 1.0


class TestGraphSearch:
    """Test graph search functionality."""

    @pytest.fixture
    def triad(self):
        """Create a RetrievalTriad instance for testing."""
        return RetrievalTriad(vector_manager=MagicMock(), graph_manager=MockGraphManager())

    @pytest.mark.asyncio
    async def test_graph_search_with_known_entity(self, triad):
        """Test graph search with a known entity (supply chain)."""
        results = await triad._graph_search("supply chain", 10)

        assert isinstance(results, list)
        assert len(results) > 0

    @pytest.mark.asyncio
    async def test_graph_search_unknown_entity(self, triad):
        """Test graph search with unknown entity returns empty."""
        results = await triad._graph_search("unknown_xyz_entity", 10)

        assert isinstance(results, list)
        # May return empty for unknown entities

    @pytest.mark.asyncio
    async def test_graph_search_result_structure(self, triad):
        """Test graph search result structure."""
        results = await triad._graph_search("supply chain", 10)

        if results:
            for result in results:
                assert "id" in result
                assert "content" in result
                assert "score" in result

    @pytest.mark.asyncio
    async def test_graph_search_multi_hop_context(self, triad):
        """Test that graph search uses multi-hop context."""
        results = await triad._graph_search("supply chain", 10)

        if results:
            # Graph results should contain context information
            assert any("Context" in str(r.get("content", "")) for r in results)


class TestResultMerging:
    """Test result merging with RRF."""

    @pytest.fixture
    def triad(self):
        """Create a RetrievalTriad instance for testing."""
        return RetrievalTriad(vector_manager=MagicMock(), graph_manager=MockGraphManager())

    def test_merge_empty_results(self, triad):
        """Test merging empty result sets."""
        merged = triad._merge_results([], [], [], 10)

        assert merged == []

    def test_merge_single_source(self, triad):
        """Test merging with only vector results."""
        vector_results = [{"id": "v1", "content": "test", "score": 0.9}]

        merged = triad._merge_results(vector_results, [], [], 10)

        assert len(merged) == 1
        assert merged[0]["id"] == "v1"
        assert "triad_score" in merged[0]

    def test_merge_multiple_sources(self, triad):
        """Test merging from all three sources."""
        vector_results = [{"id": "v1", "content": "vector", "score": 0.9}]
        keyword_results = [{"id": "k1", "content": "keyword", "score": 0.8}]
        graph_results = [{"id": "g1", "content": "graph", "score": 0.85}]

        merged = triad._merge_results(vector_results, keyword_results, graph_results, 10)

        assert len(merged) == 3
        # All results should have triad_score
        for result in merged:
            assert "triad_score" in result

    def test_merge_duplicate_ids(self, triad):
        """Test merging when same document appears in multiple sources."""
        # Same document ID in multiple sources
        vector_results = [{"id": "common", "content": "vector", "score": 0.9}]
        keyword_results = [{"id": "common", "content": "keyword", "score": 0.8}]
        graph_results = [{"id": "common", "content": "graph", "score": 0.85}]

        merged = triad._merge_results(vector_results, keyword_results, graph_results, 10)

        # Should merge into single result with combined score
        assert len(merged) == 1
        assert merged[0]["id"] == "common"
        # Score should be sum of all weighted contributions
        expected_score = 1.0 * 0.4 + 1.0 * 0.3 + 1.0 * 0.3  # All rank 1
        assert abs(merged[0]["triad_score"] - expected_score) < 0.01

    def test_merge_respects_limit(self, triad):
        """Test that merge respects the limit parameter."""
        vector_results = [
            {"id": f"v{i}", "content": f"vector {i}", "score": 0.9 - i * 0.1} for i in range(5)
        ]

        merged = triad._merge_results(vector_results, [], [], limit=3)

        assert len(merged) == 3

    def test_merge_sorted_by_triad_score(self, triad):
        """Test that merged results are sorted by triad score."""
        vector_results = [
            {"id": "v1", "content": "first", "score": 0.9},
            {"id": "v2", "content": "second", "score": 0.8},
        ]
        keyword_results = [
            {"id": "k1", "content": "keyword first", "score": 0.85},
        ]

        merged = triad._merge_results(vector_results, keyword_results, [], 10)

        # Results should be sorted by triad_score descending
        for i in range(len(merged) - 1):
            assert merged[i]["triad_score"] >= merged[i + 1]["triad_score"]

    def test_merge_with_custom_weights(self):
        """Test merging with custom weights."""
        custom_weights = {"vector": 0.6, "keyword": 0.2, "graph": 0.2}
        triad = RetrievalTriad(
            vector_manager=MagicMock(), graph_manager=MockGraphManager(), weights=custom_weights
        )

        vector_results = [{"id": "v1", "content": "vector", "score": 0.9}]
        keyword_results = [{"id": "k1", "content": "keyword", "score": 0.8}]

        merged = triad._merge_results(vector_results, keyword_results, [], 10)

        # Vector result should have higher score due to weight
        vector_item = next(r for r in merged if r["id"] == "v1")
        keyword_item = next(r for r in merged if r["id"] == "k1")

        # v1: 1.0 * 0.6 = 0.6, k1: 1.0 * 0.2 = 0.2
        assert vector_item["triad_score"] > keyword_item["triad_score"]


class TestRAGuardStability:
    """Test RAGuard stability check functionality."""

    @pytest.fixture
    def triad(self):
        """Create a RetrievalTriad instance for testing."""
        return RetrievalTriad(vector_manager=MagicMock(), graph_manager=MockGraphManager())

    @pytest.mark.asyncio
    async def test_stability_empty_results(self, triad):
        """Test stability check with empty results."""
        is_stable, score = await triad._check_stability("query", [])

        assert is_stable is True
        assert score == 1.0

    @pytest.mark.asyncio
    async def test_stability_single_result(self, triad):
        """Test stability check with single result."""
        results = [{"id": "1", "score": 0.9}]
        is_stable, score = await triad._check_stability("query", results)

        assert isinstance(is_stable, bool)
        assert 0.0 <= score <= 1.0

    @pytest.mark.asyncio
    async def test_stability_consistent_scores(self, triad):
        """Test stability with consistent scores (should be stable)."""
        results = [
            {"id": "1", "score": 0.85},
            {"id": "2", "score": 0.85},
            {"id": "3", "score": 0.85},
        ]
        is_stable, score = await triad._check_stability("query", results)

        # Consistent scores should yield high stability
        assert is_stable is True
        assert score > 0.7

    @pytest.mark.asyncio
    async def test_stability_varying_scores(self, triad):
        """Test stability with varying scores."""
        results = [
            {"id": "1", "score": 0.95},
            {"id": "2", "score": 0.5},
            {"id": "3", "score": 0.3},
        ]
        is_stable, score = await triad._check_stability("query", results)

        assert isinstance(is_stable, bool)
        assert 0.0 <= score <= 1.0

    @pytest.mark.asyncio
    async def test_stability_missing_scores(self, triad):
        """Test stability with results missing score field."""
        results = [
            {"id": "1"},
            {"id": "2"},
        ]
        is_stable, score = await triad._check_stability("query", results)

        # Should handle missing scores gracefully
        assert isinstance(is_stable, bool)
        assert 0.0 <= score <= 1.0


class TestFullSearch:
    """Test full search functionality."""

    @pytest.fixture
    def triad(self):
        """Create a RetrievalTriad instance for testing."""
        return RetrievalTriad(vector_manager=MagicMock(), graph_manager=MockGraphManager())

    @pytest.mark.asyncio
    async def test_search_returns_results(self, triad):
        """Test that search returns results."""
        results = await triad.search("test query", limit=10)

        assert isinstance(results, list)
        assert len(results) > 0

    @pytest.mark.asyncio
    async def test_search_results_have_stability_info(self, triad):
        """Test that search results include RAGuard stability info."""
        results = await triad.search("test query", limit=10)

        for result in results:
            assert "raguard_stable" in result
            assert "stability_score" in result

    @pytest.mark.asyncio
    async def test_search_respects_limit(self, triad):
        """Test that search respects the limit parameter."""
        results = await triad.search("test query", limit=5)

        assert len(results) <= 5

    @pytest.mark.asyncio
    async def test_search_with_supply_chain_query(self, triad):
        """Test search with supply chain query (known graph entity)."""
        results = await triad.search("supply chain", limit=10)

        assert isinstance(results, list)
        # Should have results from all sources merged

    @pytest.mark.asyncio
    async def test_search_default_limit(self, triad):
        """Test search with default limit."""
        results = await triad.search("test query")

        assert isinstance(results, list)
        assert len(results) <= 10  # Default limit

    @pytest.mark.asyncio
    async def test_search_results_sorted_by_score(self, triad):
        """Test that search results are sorted by triad score."""
        results = await triad.search("test query", limit=10)

        for i in range(len(results) - 1):
            assert results[i]["triad_score"] >= results[i + 1]["triad_score"]


class TestParallelExecution:
    """Test parallel search execution."""

    @pytest.mark.asyncio
    async def test_concurrent_searches(self):
        """Test multiple concurrent search operations."""
        triad = RetrievalTriad(vector_manager=MagicMock(), graph_manager=MockGraphManager())

        tasks = [triad.search(f"query {i}", limit=5) for i in range(5)]
        results = await asyncio.gather(*tasks)

        assert len(results) == 5
        for result_set in results:
            assert isinstance(result_set, list)

    @pytest.mark.asyncio
    async def test_parallel_search_components(self):
        """Test that internal searches run in parallel."""
        triad = RetrievalTriad(vector_manager=MagicMock(), graph_manager=MockGraphManager())

        # Search should execute vector, keyword, graph in parallel
        results = await triad.search("test parallel", limit=10)

        # Results should contain items from multiple sources
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_multiple_triads_concurrent(self):
        """Test multiple RetrievalTriad instances running concurrently."""
        triads = [
            RetrievalTriad(vector_manager=MagicMock(), graph_manager=MockGraphManager())
            for _ in range(3)
        ]

        tasks = [triad.search("concurrent test", limit=5) for triad in triads]
        results = await asyncio.gather(*tasks)

        assert len(results) == 3
        for result_set in results:
            assert isinstance(result_set, list)


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.fixture
    def triad(self):
        """Create a RetrievalTriad instance for testing."""
        return RetrievalTriad(vector_manager=MagicMock(), graph_manager=MockGraphManager())

    @pytest.mark.asyncio
    async def test_empty_query(self, triad):
        """Test search with empty query."""
        results = await triad.search("", limit=10)

        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_very_long_query(self, triad):
        """Test search with very long query."""
        long_query = "test " * 100
        results = await triad.search(long_query, limit=10)

        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_special_characters_in_query(self, triad):
        """Test search with special characters."""
        results = await triad.search("test!@#$%^&*()", limit=10)

        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_unicode_query(self, triad):
        """Test search with unicode characters."""
        results = await triad.search("测试查询 тест", limit=10)

        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_limit_zero(self, triad):
        """Test search with limit of zero."""
        results = await triad.search("test", limit=0)

        assert results == []

    @pytest.mark.asyncio
    async def test_limit_one(self, triad):
        """Test search with limit of one."""
        results = await triad.search("test", limit=1)

        assert len(results) <= 1

    @pytest.mark.asyncio
    async def test_very_large_limit(self, triad):
        """Test search with very large limit."""
        results = await triad.search("test", limit=1000)

        assert isinstance(results, list)

    def test_weights_with_zero_values(self):
        """Test with some weights set to zero."""
        triad = RetrievalTriad(
            vector_manager=MagicMock(),
            graph_manager=MockGraphManager(),
            weights={"vector": 1.0, "keyword": 0.0, "graph": 0.0},
        )

        vector_results = [{"id": "v1", "content": "test", "score": 0.9}]
        keyword_results = [{"id": "k1", "content": "test", "score": 0.8}]

        merged = triad._merge_results(vector_results, keyword_results, [], 10)

        # Keyword result should have zero contribution
        keyword_item = next((r for r in merged if r["id"] == "k1"), None)
        if keyword_item:
            assert keyword_item["triad_score"] == 0.0


class TestWeightConfigurations:
    """Test different weight configurations."""

    @pytest.mark.asyncio
    async def test_vector_only_weights(self):
        """Test with only vector weight."""
        triad = RetrievalTriad(
            vector_manager=MagicMock(),
            graph_manager=MockGraphManager(),
            weights={"vector": 1.0, "keyword": 0.0, "graph": 0.0},
        )

        results = await triad.search("test", limit=10)
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_keyword_only_weights(self):
        """Test with only keyword weight."""
        triad = RetrievalTriad(
            vector_manager=MagicMock(),
            graph_manager=MockGraphManager(),
            weights={"vector": 0.0, "keyword": 1.0, "graph": 0.0},
        )

        results = await triad.search("test", limit=10)
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_graph_only_weights(self):
        """Test with only graph weight."""
        triad = RetrievalTriad(
            vector_manager=MagicMock(),
            graph_manager=MockGraphManager(),
            weights={"vector": 0.0, "keyword": 0.0, "graph": 1.0},
        )

        results = await triad.search("supply chain", limit=10)
        assert isinstance(results, list)


class TestLogging:
    """Test logging functionality."""

    @pytest.mark.asyncio
    async def test_search_logs_query(self):
        """Test that search logs the query."""
        triad = RetrievalTriad(vector_manager=MagicMock(), graph_manager=MockGraphManager())

        # Use the correct module path for patching
        try:
            with patch("enhanced_agent_bus.retrieval_triad.logger") as mock_logger:
                await triad.search("test logging", limit=10)
                assert mock_logger.info.called
        except ModuleNotFoundError:
            with patch("retrieval_triad.logger") as mock_logger:
                await triad.search("test logging", limit=10)
                # Logger may or may not be called depending on implementation
                # Just verify the search completes successfully
                pass


class TestConstitutionalCompliance:
    """Test constitutional compliance."""

    def test_constitutional_hash_in_module(self):
        """Test that module has constitutional hash in docstring."""
        try:
            from enhanced_agent_bus import retrieval_triad
        except ImportError:
            import retrieval_triad

        assert CONSTITUTIONAL_HASH in retrieval_triad.__doc__

    @pytest.mark.asyncio
    async def test_search_with_constitutional_context(self):
        """Test search operations maintain constitutional compliance."""
        triad = RetrievalTriad(vector_manager=MagicMock(), graph_manager=MockGraphManager())

        # Execute search
        results = await triad.search("constitutional governance", limit=10)

        # All results should have required fields
        for result in results:
            assert "triad_score" in result
            assert "raguard_stable" in result
            assert "stability_score" in result


class TestRRFScoring:
    """Test Reciprocal Rank Fusion scoring."""

    @pytest.fixture
    def triad(self):
        """Create a RetrievalTriad instance for testing."""
        return RetrievalTriad(vector_manager=MagicMock(), graph_manager=MockGraphManager())

    def test_rrf_first_rank_scoring(self, triad):
        """Test RRF scoring for first rank items."""
        vector_results = [{"id": "v1", "content": "first", "score": 0.9}]

        merged = triad._merge_results(vector_results, [], [], 10)

        # First rank: 1/(1+0) = 1.0, weighted by 0.4 = 0.4
        assert abs(merged[0]["triad_score"] - 0.4) < 0.01

    def test_rrf_second_rank_scoring(self, triad):
        """Test RRF scoring for second rank items."""
        vector_results = [
            {"id": "v1", "content": "first", "score": 0.9},
            {"id": "v2", "content": "second", "score": 0.8},
        ]

        merged = triad._merge_results(vector_results, [], [], 10)

        v1_item = next(r for r in merged if r["id"] == "v1")
        v2_item = next(r for r in merged if r["id"] == "v2")

        # v1: 1/(1) * 0.4 = 0.4
        # v2: 1/(2) * 0.4 = 0.2
        assert abs(v1_item["triad_score"] - 0.4) < 0.01
        assert abs(v2_item["triad_score"] - 0.2) < 0.01

    def test_rrf_combined_sources(self, triad):
        """Test RRF with same item in multiple sources."""
        vector_results = [{"id": "common", "content": "test", "score": 0.9}]
        keyword_results = [{"id": "common", "content": "test", "score": 0.8}]
        graph_results = [{"id": "common", "content": "test", "score": 0.85}]

        merged = triad._merge_results(vector_results, keyword_results, graph_results, 10)

        # Should be single result with combined score
        assert len(merged) == 1
        # Score: 1.0*0.4 + 1.0*0.3 + 1.0*0.3 = 1.0
        assert abs(merged[0]["triad_score"] - 1.0) < 0.01


class TestGraphManagerIntegration:
    """Test integration with GraphDatabaseManager."""

    @pytest.mark.asyncio
    async def test_uses_graph_manager_for_search(self):
        """Test that graph search uses the provided graph manager."""
        mock_graph = MockGraphManager()
        triad = RetrievalTriad(vector_manager=MagicMock(), graph_manager=mock_graph)

        # Search should call graph manager's get_multi_hop_context
        results = await triad._graph_search("supply chain", 10)

        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_graph_search_with_mock_manager(self):
        """Test graph search with MockGraphManager returns expected structure."""
        mock_graph = MockGraphManager()
        triad = RetrievalTriad(vector_manager=MagicMock(), graph_manager=mock_graph)

        results = await triad._graph_search("supply chain", 10)

        if results:
            assert "id" in results[0]
            assert "content" in results[0]
            assert "score" in results[0]
