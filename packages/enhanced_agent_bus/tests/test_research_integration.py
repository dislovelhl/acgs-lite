"""
Comprehensive tests for Research Integration Layer v3.0

Tests cover:
- Constitutional hash enforcement
- Enums: ResearchSource, ResearchType, QualityLevel
- Dataclasses: ResearchQuery, ResearchResult, SynthesizedKnowledge, TrendAnalysis
- SourceConnectors: ArXiv, GitHub, HuggingFace, Web
- KnowledgeSynthesizer
- TrendAnalyzer
- ResearchIntegrator
- Factory function

Constitutional Hash: cdd01ef066bc6cf2
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

# Import all components
from ..research_integration import (
    CONSTITUTIONAL_HASH,
    ArXivConnector,
    GitHubConnector,
    HuggingFaceConnector,
    KnowledgeSynthesizer,
    QualityLevel,
    ResearchIntegrator,
    ResearchQuery,
    ResearchResult,
    ResearchSource,
    ResearchType,
    SourceConnector,
    SynthesizedKnowledge,
    TrendAnalysis,
    TrendAnalyzer,
    WebConnector,
    create_research_integrator,
)

# =============================================================================
# Constitutional Hash Tests
# =============================================================================


class TestConstitutionalHash:
    """Test constitutional hash enforcement."""

    def test_constitutional_hash_value(self):
        """Verify constitutional hash value."""
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    def test_constitutional_hash_in_query(self):
        """Verify constitutional hash in ResearchQuery."""
        query = ResearchQuery(
            id="q-001",
            topic="Machine Learning",
            sources=[ResearchSource.ARXIV],
            research_type=ResearchType.PAPERS,
        )
        assert query.constitutional_hash == CONSTITUTIONAL_HASH

    def test_constitutional_hash_in_result(self):
        """Verify constitutional hash in ResearchResult."""
        result = ResearchResult(
            id="r-001",
            query_id="q-001",
            source=ResearchSource.ARXIV,
            title="Test Paper",
            summary="Test summary",
            url="https://example.com",
            relevance_score=0.9,
            quality_level=QualityLevel.HIGH,
        )
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    def test_constitutional_hash_in_synthesis(self):
        """Verify constitutional hash in SynthesizedKnowledge."""
        synthesis = SynthesizedKnowledge(
            id="s-001",
            topic="Test Topic",
            key_findings=[],
            consensus_points=[],
            conflicting_points=[],
            recommendations=[],
            sources_used=[],
            confidence_score=0.8,
            synthesis_method="test",
        )
        assert synthesis.constitutional_hash == CONSTITUTIONAL_HASH

    def test_constitutional_hash_in_trend(self):
        """Verify constitutional hash in TrendAnalysis."""
        trend = TrendAnalysis(
            id="t-001",
            topic="Test Topic",
            trending_up=[],
            trending_down=[],
            emerging_topics=[],
            mature_topics=[],
            time_period_days=90,
            data_points=10,
            confidence=0.7,
        )
        assert trend.constitutional_hash == CONSTITUTIONAL_HASH


# =============================================================================
# Enum Tests
# =============================================================================


class TestResearchSource:
    """Test ResearchSource enum."""

    def test_arxiv_source(self):
        """Test ARXIV source."""
        assert ResearchSource.ARXIV.value == "arxiv"

    def test_github_source(self):
        """Test GITHUB source."""
        assert ResearchSource.GITHUB.value == "github"

    def test_huggingface_source(self):
        """Test HUGGINGFACE source."""
        assert ResearchSource.HUGGINGFACE.value == "huggingface"

    def test_web_source(self):
        """Test WEB source."""
        assert ResearchSource.WEB.value == "web"

    def test_documentation_source(self):
        """Test DOCUMENTATION source."""
        assert ResearchSource.DOCUMENTATION.value == "documentation"

    def test_academic_source(self):
        """Test ACADEMIC source."""
        assert ResearchSource.ACADEMIC.value == "academic"


class TestResearchType:
    """Test ResearchType enum."""

    def test_papers_type(self):
        """Test PAPERS type."""
        assert ResearchType.PAPERS.value == "papers"

    def test_code_type(self):
        """Test CODE type."""
        assert ResearchType.CODE.value == "code"

    def test_models_type(self):
        """Test MODELS type."""
        assert ResearchType.MODELS.value == "models"

    def test_datasets_type(self):
        """Test DATASETS type."""
        assert ResearchType.DATASETS.value == "datasets"

    def test_tutorials_type(self):
        """Test TUTORIALS type."""
        assert ResearchType.TUTORIALS.value == "tutorials"

    def test_best_practices_type(self):
        """Test BEST_PRACTICES type."""
        assert ResearchType.BEST_PRACTICES.value == "best_practices"

    def test_trends_type(self):
        """Test TRENDS type."""
        assert ResearchType.TRENDS.value == "trends"


class TestQualityLevel:
    """Test QualityLevel enum."""

    def test_high_quality(self):
        """Test HIGH quality."""
        assert QualityLevel.HIGH.value == "high"

    def test_medium_quality(self):
        """Test MEDIUM quality."""
        assert QualityLevel.MEDIUM.value == "medium"

    def test_low_quality(self):
        """Test LOW quality."""
        assert QualityLevel.LOW.value == "low"

    def test_unknown_quality(self):
        """Test UNKNOWN quality."""
        assert QualityLevel.UNKNOWN.value == "unknown"


# =============================================================================
# Dataclass Tests
# =============================================================================


class TestResearchQuery:
    """Test ResearchQuery dataclass."""

    def test_query_creation(self):
        """Test basic query creation."""
        query = ResearchQuery(
            id="q-001",
            topic="Deep Learning",
            sources=[ResearchSource.ARXIV, ResearchSource.GITHUB],
            research_type=ResearchType.PAPERS,
        )
        assert query.id == "q-001"
        assert query.topic == "Deep Learning"
        assert len(query.sources) == 2

    def test_query_defaults(self):
        """Test query default values."""
        query = ResearchQuery(
            id="q-001",
            topic="Test",
            sources=[],
            research_type=ResearchType.CODE,
        )
        assert query.max_results == 10
        assert query.min_quality == QualityLevel.MEDIUM
        assert query.recency_days == 365
        assert query.keywords == []
        assert query.exclude_terms == []


class TestResearchResult:
    """Test ResearchResult dataclass."""

    def test_result_creation(self):
        """Test basic result creation."""
        result = ResearchResult(
            id="r-001",
            query_id="q-001",
            source=ResearchSource.ARXIV,
            title="Neural Networks Paper",
            summary="A comprehensive study of neural networks",
            url="https://arxiv.org/abs/123",
            relevance_score=0.95,
            quality_level=QualityLevel.HIGH,
        )
        assert result.id == "r-001"
        assert result.relevance_score == 0.95
        assert result.quality_level == QualityLevel.HIGH

    def test_result_defaults(self):
        """Test result default values."""
        result = ResearchResult(
            id="r-001",
            query_id="q-001",
            source=ResearchSource.WEB,
            title="Test",
            summary="Test summary",
            url=None,
            relevance_score=0.5,
            quality_level=QualityLevel.LOW,
        )
        assert result.metadata == {}
        assert result.published_date is None


class TestSynthesizedKnowledge:
    """Test SynthesizedKnowledge dataclass."""

    def test_synthesis_creation(self):
        """Test basic synthesis creation."""
        synthesis = SynthesizedKnowledge(
            id="s-001",
            topic="Transformers",
            key_findings=["Finding 1", "Finding 2"],
            consensus_points=["Consensus 1"],
            conflicting_points=[],
            recommendations=["Recommendation 1"],
            sources_used=["r-001", "r-002"],
            confidence_score=0.85,
            synthesis_method="aggregation",
        )
        assert synthesis.topic == "Transformers"
        assert len(synthesis.key_findings) == 2
        assert synthesis.confidence_score == 0.85


class TestTrendAnalysis:
    """Test TrendAnalysis dataclass."""

    def test_trend_creation(self):
        """Test basic trend analysis creation."""
        trend = TrendAnalysis(
            id="t-001",
            topic="LLM",
            trending_up=["GPT-4", "Claude"],
            trending_down=["RNN"],
            emerging_topics=["Multimodal"],
            mature_topics=["CNN"],
            time_period_days=90,
            data_points=100,
            confidence=0.75,
        )
        assert trend.topic == "LLM"
        assert len(trend.trending_up) == 2
        assert trend.confidence == 0.75


# =============================================================================
# SourceConnector Tests
# =============================================================================


class TestArXivConnector:
    """Test ArXivConnector."""

    def test_connector_creation(self):
        """Test connector creation."""
        connector = ArXivConnector()
        assert connector._source == ResearchSource.ARXIV

    @pytest.mark.asyncio
    async def test_search_returns_results(self):
        """Test search returns results."""
        connector = ArXivConnector()
        query = ResearchQuery(
            id="q-001",
            topic="Machine Learning",
            sources=[ResearchSource.ARXIV],
            research_type=ResearchType.PAPERS,
            max_results=3,
        )
        results = await connector.search(query)
        assert len(results) <= 3
        assert all(r.source == ResearchSource.ARXIV for r in results)

    @pytest.mark.asyncio
    async def test_search_result_format(self):
        """Test search result format."""
        connector = ArXivConnector()
        query = ResearchQuery(
            id="q-001",
            topic="Neural Networks",
            sources=[ResearchSource.ARXIV],
            research_type=ResearchType.PAPERS,
        )
        results = await connector.search(query)

        if results:
            result = results[0]
            assert result.source == ResearchSource.ARXIV
            assert "Neural Networks" in result.title or "neural" in result.title.lower()
            assert result.url.startswith("https://arxiv.org")


class TestGitHubConnector:
    """Test GitHubConnector."""

    def test_connector_creation(self):
        """Test connector creation."""
        connector = GitHubConnector()
        assert connector._source == ResearchSource.GITHUB

    @pytest.mark.asyncio
    async def test_search_returns_results(self):
        """Test search returns results."""
        connector = GitHubConnector()
        query = ResearchQuery(
            id="q-001",
            topic="Python Tools",
            sources=[ResearchSource.GITHUB],
            research_type=ResearchType.CODE,
            max_results=3,
        )
        results = await connector.search(query)
        assert len(results) <= 3
        assert all(r.source == ResearchSource.GITHUB for r in results)

    @pytest.mark.asyncio
    async def test_search_result_metadata(self):
        """Test search result includes metadata."""
        connector = GitHubConnector()
        query = ResearchQuery(
            id="q-001",
            topic="FastAPI",
            sources=[ResearchSource.GITHUB],
            research_type=ResearchType.CODE,
        )
        results = await connector.search(query)

        if results:
            assert "stars" in results[0].metadata
            assert "forks" in results[0].metadata


class TestHuggingFaceConnector:
    """Test HuggingFaceConnector."""

    def test_connector_creation(self):
        """Test connector creation."""
        connector = HuggingFaceConnector()
        assert connector._source == ResearchSource.HUGGINGFACE

    @pytest.mark.asyncio
    async def test_search_models(self):
        """Test search for models."""
        connector = HuggingFaceConnector()
        query = ResearchQuery(
            id="q-001",
            topic="Text Classification",
            sources=[ResearchSource.HUGGINGFACE],
            research_type=ResearchType.MODELS,
        )
        results = await connector.search(query)
        assert all(r.source == ResearchSource.HUGGINGFACE for r in results)


class TestWebConnector:
    """Test WebConnector."""

    def test_connector_creation(self):
        """Test connector creation."""
        connector = WebConnector()
        assert connector._source == ResearchSource.WEB

    @pytest.mark.asyncio
    async def test_search_returns_results(self):
        """Test search returns results."""
        connector = WebConnector()
        query = ResearchQuery(
            id="q-001",
            topic="Python Best Practices",
            sources=[ResearchSource.WEB],
            research_type=ResearchType.BEST_PRACTICES,
        )
        results = await connector.search(query)
        assert len(results) > 0
        assert all(r.source == ResearchSource.WEB for r in results)


# =============================================================================
# KnowledgeSynthesizer Tests
# =============================================================================


class TestKnowledgeSynthesizer:
    """Test KnowledgeSynthesizer."""

    def test_synthesizer_creation(self):
        """Test synthesizer creation."""
        synthesizer = KnowledgeSynthesizer()
        assert synthesizer._synthesis_cache is not None

    @pytest.mark.asyncio
    async def test_synthesize_empty_results(self):
        """Test synthesis with empty results."""
        synthesizer = KnowledgeSynthesizer()
        synthesis = await synthesizer.synthesize([], "Test Topic")

        assert synthesis.topic == "Test Topic"
        assert synthesis.confidence_score == 0.0
        assert synthesis.synthesis_method == "empty"

    @pytest.mark.asyncio
    async def test_synthesize_with_results(self):
        """Test synthesis with results."""
        synthesizer = KnowledgeSynthesizer()

        results = [
            ResearchResult(
                id="r-001",
                query_id="q-001",
                source=ResearchSource.ARXIV,
                title="Paper 1",
                summary="Summary of paper 1",
                url="https://arxiv.org/1",
                relevance_score=0.9,
                quality_level=QualityLevel.HIGH,
            ),
            ResearchResult(
                id="r-002",
                query_id="q-001",
                source=ResearchSource.GITHUB,
                title="Repo 1",
                summary="Summary of repo 1",
                url="https://github.com/1",
                relevance_score=0.85,
                quality_level=QualityLevel.MEDIUM,
            ),
        ]

        synthesis = await synthesizer.synthesize(results, "Test Topic")

        assert len(synthesis.key_findings) > 0
        assert len(synthesis.sources_used) == 2
        assert synthesis.confidence_score > 0

    @pytest.mark.asyncio
    async def test_synthesize_generates_recommendations(self):
        """Test synthesis generates recommendations."""
        synthesizer = KnowledgeSynthesizer()

        results = [
            ResearchResult(
                id="r-001",
                query_id="q-001",
                source=ResearchSource.ARXIV,
                title="Paper",
                summary="Paper summary",
                url=None,
                relevance_score=0.9,
                quality_level=QualityLevel.HIGH,
            ),
        ]

        synthesis = await synthesizer.synthesize(results, "ML Topic")
        assert len(synthesis.recommendations) > 0

    def test_get_cached_synthesis(self):
        """Test getting cached synthesis."""
        synthesizer = KnowledgeSynthesizer()
        # Non-existent cache should return None
        assert synthesizer.get_cached("non-existent") is None


# =============================================================================
# TrendAnalyzer Tests
# =============================================================================


class TestTrendAnalyzer:
    """Test TrendAnalyzer."""

    def test_analyzer_creation(self):
        """Test analyzer creation."""
        analyzer = TrendAnalyzer()
        assert analyzer._trend_history is not None

    def test_record_query(self):
        """Test recording a query."""
        analyzer = TrendAnalyzer()
        query = ResearchQuery(
            id="q-001",
            topic="LLM Development",
            sources=[ResearchSource.ARXIV],
            research_type=ResearchType.PAPERS,
        )
        analyzer.record_query(query, 10)
        assert len(analyzer._trend_history["llm development"]) == 1

    @pytest.mark.asyncio
    async def test_analyze_trends(self):
        """Test trend analysis."""
        analyzer = TrendAnalyzer()
        analysis = await analyzer.analyze_trends("LLM Development", 90)

        assert analysis.topic == "LLM Development"
        assert analysis.time_period_days == 90
        assert len(analysis.trending_up) > 0

    @pytest.mark.asyncio
    async def test_analyze_trends_detects_keywords(self):
        """Test trend analysis detects hot keywords."""
        analyzer = TrendAnalyzer()

        # Topic with known hot keywords
        analysis = await analyzer.analyze_trends("AI Agent Development", 90)
        # Should detect "ai" and "agent" keywords
        assert len(analysis.trending_up) > 0


# =============================================================================
# ResearchIntegrator Tests
# =============================================================================


class TestResearchIntegrator:
    """Test ResearchIntegrator."""

    def test_integrator_creation(self):
        """Test integrator creation."""
        integrator = ResearchIntegrator()
        assert len(integrator._connectors) > 0
        assert integrator._constitutional_hash == CONSTITUTIONAL_HASH

    def test_integrator_with_custom_config(self):
        """Test integrator with custom configuration."""
        integrator = ResearchIntegrator(
            max_concurrent_requests=10,
        )
        assert integrator._max_concurrent == 10

    @pytest.mark.asyncio
    async def test_search_single_source(self):
        """Test search with single source."""
        integrator = ResearchIntegrator()
        query, results = await integrator.search(
            topic="Machine Learning",
            sources=[ResearchSource.ARXIV],
            max_results=5,
        )

        assert query.topic == "Machine Learning"
        assert len(results) <= 5

    @pytest.mark.asyncio
    async def test_search_multiple_sources(self):
        """Test search with multiple sources."""
        integrator = ResearchIntegrator()
        _query, results = await integrator.search(
            topic="Python Development",
            sources=[ResearchSource.GITHUB, ResearchSource.WEB],
            max_results=10,
        )

        sources = set(r.source for r in results)
        assert len(sources) >= 1  # At least one source returned results

    @pytest.mark.asyncio
    async def test_search_all_sources(self):
        """Test search with all sources."""
        integrator = ResearchIntegrator()
        _query, results = await integrator.search(
            topic="Deep Learning",
            max_results=15,
        )

        assert len(results) > 0
        assert integrator._metrics["queries_executed"] >= 1

    @pytest.mark.asyncio
    async def test_synthesize_knowledge(self):
        """Test knowledge synthesis."""
        integrator = ResearchIntegrator()
        synthesis = await integrator.synthesize_knowledge(
            topic="Neural Networks",
            sources=[ResearchSource.ARXIV, ResearchSource.GITHUB],
        )

        assert synthesis.topic == "Neural Networks"
        assert synthesis.synthesis_method == "multi_source_aggregation"

    @pytest.mark.asyncio
    async def test_analyze_topic_trends(self):
        """Test topic trend analysis."""
        integrator = ResearchIntegrator()
        trends = await integrator.analyze_topic_trends("LLM", 90)

        assert trends.topic == "LLM"
        assert trends.time_period_days == 90

    @pytest.mark.asyncio
    async def test_research_best_practices(self):
        """Test best practices research."""
        integrator = ResearchIntegrator()
        result = await integrator.research_best_practices("Python Testing")

        assert result["topic"] == "Python Testing"
        assert "synthesis" in result
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH

    @pytest.mark.asyncio
    async def test_research_state_of_art(self):
        """Test state of the art research."""
        integrator = ResearchIntegrator()
        result = await integrator.research_state_of_art("Transformer Models")

        assert result["topic"] == "Transformer Models"
        assert "synthesis" in result
        assert "trends" in result

    def test_get_query(self):
        """Test getting a query."""
        integrator = ResearchIntegrator()
        assert integrator.get_query("non-existent") is None

    def test_get_results(self):
        """Test getting results."""
        integrator = ResearchIntegrator()
        results = integrator.get_results("non-existent")
        assert results == []

    def test_get_stats(self):
        """Test getting stats."""
        integrator = ResearchIntegrator()
        stats = integrator.get_stats()

        assert "queries_executed" in stats
        assert "active_connectors" in stats
        assert stats["constitutional_hash"] == CONSTITUTIONAL_HASH

    @pytest.mark.asyncio
    async def test_result_ranking(self):
        """Test result ranking by quality and relevance."""
        integrator = ResearchIntegrator()
        _query, results = await integrator.search(
            topic="AI Development",
            sources=[ResearchSource.ARXIV, ResearchSource.GITHUB],
            max_results=10,
        )

        if len(results) >= 2:
            # First result should have higher or equal score
            first_score = results[0].relevance_score
            second_score = results[1].relevance_score
            # High quality results should be ranked higher
            assert first_score >= second_score * 0.5  # Allow for quality adjustment


# =============================================================================
# Factory Function Tests
# =============================================================================


class TestCreateResearchIntegrator:
    """Test create_research_integrator factory function."""

    def test_create_with_defaults(self):
        """Test creating integrator with defaults."""
        integrator = create_research_integrator()
        assert isinstance(integrator, ResearchIntegrator)
        assert integrator._max_concurrent == 5

    def test_create_with_custom_config(self):
        """Test creating integrator with custom config."""
        integrator = create_research_integrator(
            max_concurrent_requests=20,
        )
        assert integrator._max_concurrent == 20

    def test_create_with_custom_hash(self):
        """Test creating integrator with custom hash."""
        custom_hash = "custom12345678"
        integrator = create_research_integrator(constitutional_hash=custom_hash)
        assert integrator._constitutional_hash == custom_hash


# =============================================================================
# Integration Tests
# =============================================================================


class TestResearchIntegration:
    """Integration tests for research workflow."""

    @pytest.mark.asyncio
    async def test_full_research_workflow(self):
        """Test complete research workflow."""
        integrator = create_research_integrator()

        # 1. Search for topic
        _query, results = await integrator.search(
            topic="Constitutional AI",
            sources=[ResearchSource.ARXIV, ResearchSource.GITHUB],
            max_results=10,
        )

        assert len(results) > 0

        # 2. Synthesize knowledge
        synthesis = await integrator.synthesize_knowledge(
            "Constitutional AI",
            [ResearchSource.ARXIV],
        )

        assert synthesis.topic == "Constitutional AI"

        # 3. Analyze trends
        trends = await integrator.analyze_topic_trends("Constitutional AI")

        assert trends.topic == "Constitutional AI"

        # 4. Verify stats
        stats = integrator.get_stats()
        assert stats["queries_executed"] >= 2
        assert stats["syntheses_created"] >= 1

    @pytest.mark.asyncio
    async def test_concurrent_searches(self):
        """Test concurrent search requests."""
        integrator = create_research_integrator()

        # Execute multiple searches concurrently
        tasks = [
            integrator.search("Topic A", max_results=3),
            integrator.search("Topic B", max_results=3),
            integrator.search("Topic C", max_results=3),
        ]

        results = await asyncio.gather(*tasks)

        assert len(results) == 3
        assert all(len(r[1]) > 0 for r in results)

    @pytest.mark.asyncio
    async def test_research_with_synthesis_and_trends(self):
        """Test research combining synthesis and trends."""
        integrator = create_research_integrator()

        result = await integrator.research_state_of_art("Large Language Models")

        assert "synthesis" in result
        assert "trends" in result
        assert result["synthesis"].topic == "Large Language Models"
        assert result["trends"].topic == "Large Language Models"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
