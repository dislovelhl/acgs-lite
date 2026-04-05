# Constitutional Hash: 608508a9bd224290
"""
Comprehensive tests for ResearchCoordinator.

Targets ≥95% line coverage of coordinators/research_coordinator.py (66 stmts).
All external dependencies (research_integration) are mocked via sys.modules
injection so the coordinator can be tested without the optional dep being
importable.
"""

from __future__ import annotations

import sys
from types import ModuleType
from typing import ClassVar
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

CONSTITUTIONAL_HASH = CONSTITUTIONAL_HASH

# ---------------------------------------------------------------------------
# Helpers — build fake modules for research_integration
# ---------------------------------------------------------------------------


def _make_research_result(
    *,
    title: str = "Test Paper",
    summary: str = "Test summary",
    url: str = "https://arxiv.org/abs/0000.0000",
    relevance_score: float = 0.9,
    stars: int | None = None,
) -> MagicMock:
    """Return a mock research result object."""
    r = MagicMock()
    r.title = title
    r.summary = summary
    r.url = url
    r.relevance_score = relevance_score
    if stars is not None:
        r.stars = stars
    else:
        # No 'stars' attribute — getattr falls back to default 0
        del r.stars
    return r


def _make_synthesis_result(
    *,
    key_findings: list[str] | None = None,
    consensus_points: list[str] | None = None,
    recommendations: list[str] | None = None,
    confidence_score: float = 0.85,
) -> MagicMock:
    """Return a mock synthesis result object."""
    s = MagicMock()
    s.key_findings = key_findings or ["finding1"]
    s.consensus_points = consensus_points or ["consensus1"]
    s.recommendations = recommendations or ["rec1"]
    s.confidence_score = confidence_score
    return s


def _make_research_integration_module(
    *,
    create_raises: Exception | None = None,
    integrator: object | None = None,
) -> ModuleType:
    """Return a fake research_integration module."""
    mod = ModuleType("enhanced_agent_bus.research_integration")

    if create_raises is not None:
        mod.create_research_integrator = MagicMock(side_effect=create_raises)
    else:
        mock_integrator = integrator if integrator is not None else MagicMock()
        mod.create_research_integrator = MagicMock(return_value=mock_integrator)

    # ResearchSource and ResearchType enums (mock-like)
    rs = MagicMock()
    rs.ARXIV = "ARXIV"
    rs.GITHUB = "GITHUB"
    mod.ResearchSource = rs

    rt = MagicMock()
    rt.PAPERS = "PAPERS"
    rt.CODE = "CODE"
    mod.ResearchType = rt

    return mod


def _build_coordinator(
    *,
    integration_available: bool = True,
    create_raises: Exception | None = None,
    integrator: object | None = None,
    sources: list[str] | None = None,
    max_results_per_source: int = 5,
):
    """
    Build a ResearchCoordinator with controlled integration availability.

    If integration_available=False, the research_integration import raises
    ImportError so the coordinator falls back to basic mode.
    """
    # Purge any cached coordinator module so each call gets a fresh class
    for key in list(sys.modules.keys()):
        if "coordinators.research_coordinator" in key or (
            "research_coordinator" in key and "test" not in key
        ):
            del sys.modules[key]

    integration_module_key = "enhanced_agent_bus.research_integration"

    if not integration_available:
        # Cause ImportError on the relative import
        with patch.dict(sys.modules, {integration_module_key: None}):
            from enhanced_agent_bus.coordinators.research_coordinator import (
                ResearchCoordinator,
            )

            coordinator = ResearchCoordinator(
                sources=sources,
                max_results_per_source=max_results_per_source,
            )
        return coordinator

    # Provide a fake module
    fake_mod = _make_research_integration_module(
        create_raises=create_raises,
        integrator=integrator,
    )
    with patch.dict(sys.modules, {integration_module_key: fake_mod}):
        from enhanced_agent_bus.coordinators.research_coordinator import (
            ResearchCoordinator,
        )

        coordinator = ResearchCoordinator(
            sources=sources,
            max_results_per_source=max_results_per_source,
        )

    return coordinator


# ---------------------------------------------------------------------------
# __init__ / _initialize_integrator
# ---------------------------------------------------------------------------


class TestInitialization:
    """Tests for __init__ and _initialize_integrator."""

    def test_default_sources(self):
        coordinator = _build_coordinator(integration_available=False)
        assert coordinator._sources == ["arxiv", "github", "huggingface"]

    def test_custom_sources(self):
        coordinator = _build_coordinator(sources=["arxiv"], integration_available=False)
        assert coordinator._sources == ["arxiv"]

    def test_default_max_results(self):
        coordinator = _build_coordinator(integration_available=False)
        assert coordinator._max_results == 5

    def test_custom_max_results(self):
        coordinator = _build_coordinator(max_results_per_source=10, integration_available=False)
        assert coordinator._max_results == 10

    def test_not_initialized_when_import_error(self):
        coordinator = _build_coordinator(integration_available=False)
        assert coordinator._initialized is False
        assert coordinator._integrator is None

    def test_initialized_when_integration_available(self):
        mock_integrator = MagicMock()
        coordinator = _build_coordinator(integrator=mock_integrator)
        assert coordinator._initialized is True
        assert coordinator._integrator is mock_integrator

    def test_not_initialized_when_create_raises_runtime_error(self):
        coordinator = _build_coordinator(create_raises=RuntimeError("something broke"))
        assert coordinator._initialized is False

    def test_not_initialized_when_create_raises_value_error(self):
        coordinator = _build_coordinator(create_raises=ValueError("bad value"))
        assert coordinator._initialized is False

    def test_not_initialized_when_create_raises_type_error(self):
        coordinator = _build_coordinator(create_raises=TypeError("type error"))
        assert coordinator._initialized is False

    def test_not_initialized_when_create_raises_attribute_error(self):
        coordinator = _build_coordinator(create_raises=AttributeError("attr error"))
        assert coordinator._initialized is False

    def test_not_initialized_when_create_raises_lookup_error(self):
        coordinator = _build_coordinator(create_raises=LookupError("lookup"))
        assert coordinator._initialized is False

    def test_not_initialized_when_create_raises_os_error(self):
        coordinator = _build_coordinator(create_raises=OSError("os error"))
        assert coordinator._initialized is False

    def test_not_initialized_when_create_raises_timeout_error(self):
        coordinator = _build_coordinator(create_raises=TimeoutError("timeout"))
        assert coordinator._initialized is False

    def test_not_initialized_when_create_raises_connection_error(self):
        coordinator = _build_coordinator(create_raises=ConnectionError("connection"))
        assert coordinator._initialized is False

    def test_constitutional_hash(self):
        coordinator = _build_coordinator(integration_available=False)
        assert coordinator.constitutional_hash == CONSTITUTIONAL_HASH

    def test_none_sources_uses_default(self):
        """Passing sources=None triggers the 'or' branch."""
        coordinator = _build_coordinator(sources=None, integration_available=False)
        assert coordinator._sources == ["arxiv", "github", "huggingface"]


# ---------------------------------------------------------------------------
# is_available property
# ---------------------------------------------------------------------------


class TestIsAvailable:
    def test_not_available_when_not_initialized(self):
        coordinator = _build_coordinator(integration_available=False)
        assert coordinator.is_available is False

    def test_available_when_initialized(self):
        coordinator = _build_coordinator(integrator=MagicMock())
        assert coordinator.is_available is True

    def test_not_available_when_integrator_none(self):
        """Force _initialized=True but _integrator=None."""
        coordinator = _build_coordinator(integration_available=False)
        coordinator._initialized = True
        coordinator._integrator = None
        assert coordinator.is_available is False

    def test_not_available_when_initialized_false_integrator_set(self):
        """Force _initialized=False even with integrator present."""
        coordinator = _build_coordinator(integration_available=False)
        coordinator._initialized = False
        coordinator._integrator = MagicMock()
        assert coordinator.is_available is False


# ---------------------------------------------------------------------------
# get_stats
# ---------------------------------------------------------------------------


class TestGetStats:
    def test_stats_unavailable(self):
        coordinator = _build_coordinator(integration_available=False)
        stats = coordinator.get_stats()
        assert stats["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert stats["available"] is False
        assert stats["configured_sources"] == ["arxiv", "github", "huggingface"]
        assert stats["max_results_per_source"] == 5

    def test_stats_available(self):
        coordinator = _build_coordinator(integrator=MagicMock())
        stats = coordinator.get_stats()
        assert stats["available"] is True

    def test_stats_custom_sources(self):
        coordinator = _build_coordinator(sources=["arxiv"], integration_available=False)
        stats = coordinator.get_stats()
        assert stats["configured_sources"] == ["arxiv"]

    def test_stats_custom_max_results(self):
        coordinator = _build_coordinator(max_results_per_source=20, integration_available=False)
        stats = coordinator.get_stats()
        assert stats["max_results_per_source"] == 20


# ---------------------------------------------------------------------------
# search_arxiv
# ---------------------------------------------------------------------------


class TestSearchArxiv:
    async def test_fallback_when_no_integrator(self):
        coordinator = _build_coordinator(integration_available=False)
        results = await coordinator.search_arxiv("machine learning")
        assert len(results) == 1
        r = results[0]
        assert r["source"] == "arxiv"
        assert "machine learning" in r["title"]
        assert r["relevance_score"] == 0.0
        assert r["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert "https://arxiv.org" in r["url"]

    async def test_uses_integrator_when_available(self):
        mock_result = _make_research_result(
            title="Neural Networks",
            summary="About NNs",
            url="https://arxiv.org/abs/1234.5678",
            relevance_score=0.95,
        )
        mock_integrator = MagicMock()
        mock_integrator.search = AsyncMock(return_value=[mock_result])

        # We need the coordinator to have a live integrator and also
        # have the ResearchSource/ResearchType available during the method call.
        integration_key = "enhanced_agent_bus.research_integration"
        fake_mod = _make_research_integration_module(integrator=mock_integrator)

        coordinator = _build_coordinator(integrator=mock_integrator)

        with patch.dict(sys.modules, {integration_key: fake_mod}):
            results = await coordinator.search_arxiv("neural networks", limit=3)

        assert len(results) == 1
        assert results[0]["source"] == "arxiv"
        assert results[0]["title"] == "Neural Networks"
        assert results[0]["summary"] == "About NNs"
        assert results[0]["relevance_score"] == 0.95
        assert results[0]["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_fallback_on_integrator_runtime_error(self):
        mock_integrator = MagicMock()
        mock_integrator.search = AsyncMock(side_effect=RuntimeError("boom"))
        integration_key = "enhanced_agent_bus.research_integration"
        fake_mod = _make_research_integration_module(integrator=mock_integrator)

        coordinator = _build_coordinator(integrator=mock_integrator)

        with patch.dict(sys.modules, {integration_key: fake_mod}):
            results = await coordinator.search_arxiv("ai safety")

        # Falls back to mock result
        assert len(results) == 1
        assert results[0]["source"] == "arxiv"
        assert results[0]["relevance_score"] == 0.0

    async def test_fallback_on_integrator_timeout_error(self):
        mock_integrator = MagicMock()
        mock_integrator.search = AsyncMock(side_effect=TimeoutError("timeout"))
        integration_key = "enhanced_agent_bus.research_integration"
        fake_mod = _make_research_integration_module(integrator=mock_integrator)

        coordinator = _build_coordinator(integrator=mock_integrator)

        with patch.dict(sys.modules, {integration_key: fake_mod}):
            results = await coordinator.search_arxiv("ai safety")

        assert len(results) == 1
        assert results[0]["relevance_score"] == 0.0

    async def test_fallback_on_integrator_connection_error(self):
        mock_integrator = MagicMock()
        mock_integrator.search = AsyncMock(side_effect=ConnectionError("network"))
        integration_key = "enhanced_agent_bus.research_integration"
        fake_mod = _make_research_integration_module(integrator=mock_integrator)

        coordinator = _build_coordinator(integrator=mock_integrator)

        with patch.dict(sys.modules, {integration_key: fake_mod}):
            results = await coordinator.search_arxiv("test")

        assert len(results) == 1
        assert results[0]["source"] == "arxiv"

    async def test_fallback_on_integrator_os_error(self):
        mock_integrator = MagicMock()
        mock_integrator.search = AsyncMock(side_effect=OSError("io error"))
        integration_key = "enhanced_agent_bus.research_integration"
        fake_mod = _make_research_integration_module(integrator=mock_integrator)

        coordinator = _build_coordinator(integrator=mock_integrator)

        with patch.dict(sys.modules, {integration_key: fake_mod}):
            results = await coordinator.search_arxiv("test")

        assert results[0]["relevance_score"] == 0.0

    async def test_default_limit_parameter(self):
        coordinator = _build_coordinator(integration_available=False)
        # Default limit should not cause errors
        results = await coordinator.search_arxiv("test")
        assert isinstance(results, list)

    async def test_categories_parameter_accepted(self):
        coordinator = _build_coordinator(integration_available=False)
        results = await coordinator.search_arxiv("test", categories=["cs.AI"])
        assert isinstance(results, list)

    async def test_multiple_results_from_integrator(self):
        results_data = [
            _make_research_result(title=f"Paper {i}", relevance_score=0.9 - i * 0.1)
            for i in range(3)
        ]
        mock_integrator = MagicMock()
        mock_integrator.search = AsyncMock(return_value=results_data)
        integration_key = "enhanced_agent_bus.research_integration"
        fake_mod = _make_research_integration_module(integrator=mock_integrator)

        coordinator = _build_coordinator(integrator=mock_integrator)

        with patch.dict(sys.modules, {integration_key: fake_mod}):
            results = await coordinator.search_arxiv("deep learning", limit=3)

        assert len(results) == 3
        assert results[0]["title"] == "Paper 0"
        assert results[1]["title"] == "Paper 1"

    async def test_url_contains_query_in_fallback(self):
        coordinator = _build_coordinator(integration_available=False)
        results = await coordinator.search_arxiv("reinforcement learning")
        assert "reinforcement learning" in results[0]["url"]


# ---------------------------------------------------------------------------
# search_github
# ---------------------------------------------------------------------------


class TestSearchGithub:
    async def test_fallback_when_no_integrator(self):
        coordinator = _build_coordinator(integration_available=False)
        results = await coordinator.search_github("pytorch")
        assert len(results) == 1
        r = results[0]
        assert r["source"] == "github"
        assert "pytorch" in r["title"]
        assert r["relevance_score"] == 0.0
        assert r["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert "https://github.com" in r["url"]

    async def test_uses_integrator_when_available_with_stars(self):
        mock_result = _make_research_result(
            title="awesome-pytorch",
            summary="PyTorch tools",
            url="https://github.com/pytorch/pytorch",
            relevance_score=0.88,
            stars=10000,
        )
        mock_integrator = MagicMock()
        mock_integrator.search = AsyncMock(return_value=[mock_result])
        integration_key = "enhanced_agent_bus.research_integration"
        fake_mod = _make_research_integration_module(integrator=mock_integrator)

        coordinator = _build_coordinator(integrator=mock_integrator)

        with patch.dict(sys.modules, {integration_key: fake_mod}):
            results = await coordinator.search_github("pytorch", limit=2)

        assert len(results) == 1
        assert results[0]["source"] == "github"
        assert results[0]["title"] == "awesome-pytorch"
        assert results[0]["stars"] == 10000
        assert results[0]["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_uses_integrator_without_stars_attribute(self):
        """When result has no 'stars', getattr falls back to 0."""
        mock_result = _make_research_result(
            title="some-repo",
            relevance_score=0.7,
            # stars=None means no .stars attribute set
        )
        mock_integrator = MagicMock()
        mock_integrator.search = AsyncMock(return_value=[mock_result])
        integration_key = "enhanced_agent_bus.research_integration"
        fake_mod = _make_research_integration_module(integrator=mock_integrator)

        coordinator = _build_coordinator(integrator=mock_integrator)

        with patch.dict(sys.modules, {integration_key: fake_mod}):
            results = await coordinator.search_github("repo")

        assert results[0]["stars"] == 0

    async def test_fallback_on_runtime_error(self):
        mock_integrator = MagicMock()
        mock_integrator.search = AsyncMock(side_effect=RuntimeError("net"))
        integration_key = "enhanced_agent_bus.research_integration"
        fake_mod = _make_research_integration_module(integrator=mock_integrator)

        coordinator = _build_coordinator(integrator=mock_integrator)

        with patch.dict(sys.modules, {integration_key: fake_mod}):
            results = await coordinator.search_github("tensorflow")

        assert len(results) == 1
        assert results[0]["relevance_score"] == 0.0

    async def test_fallback_on_value_error(self):
        mock_integrator = MagicMock()
        mock_integrator.search = AsyncMock(side_effect=ValueError("bad"))
        integration_key = "enhanced_agent_bus.research_integration"
        fake_mod = _make_research_integration_module(integrator=mock_integrator)

        coordinator = _build_coordinator(integrator=mock_integrator)

        with patch.dict(sys.modules, {integration_key: fake_mod}):
            results = await coordinator.search_github("test")

        assert results[0]["source"] == "github"

    async def test_language_parameter_accepted(self):
        coordinator = _build_coordinator(integration_available=False)
        results = await coordinator.search_github("pytorch", language="python")
        assert isinstance(results, list)

    async def test_url_contains_query_in_fallback(self):
        coordinator = _build_coordinator(integration_available=False)
        results = await coordinator.search_github("machine-learning")
        assert "machine-learning" in results[0]["url"]

    async def test_multiple_results_from_integrator(self):
        results_data = [_make_research_result(title=f"Repo {i}", stars=i * 100) for i in range(4)]
        mock_integrator = MagicMock()
        mock_integrator.search = AsyncMock(return_value=results_data)
        integration_key = "enhanced_agent_bus.research_integration"
        fake_mod = _make_research_integration_module(integrator=mock_integrator)

        coordinator = _build_coordinator(integrator=mock_integrator)

        with patch.dict(sys.modules, {integration_key: fake_mod}):
            results = await coordinator.search_github("ml frameworks", limit=4)

        assert len(results) == 4


# ---------------------------------------------------------------------------
# search_all
# ---------------------------------------------------------------------------


class TestSearchAll:
    async def test_searches_arxiv_and_github_by_default(self):
        coordinator = _build_coordinator(integration_available=False)
        result = await coordinator.search_all("transformers")
        assert "arxiv" in result["sources_searched"]
        assert "github" in result["sources_searched"]
        assert result["query"] == "transformers"
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert "total_results" in result

    async def test_total_results_count(self):
        coordinator = _build_coordinator(integration_available=False)
        result = await coordinator.search_all("ai", limit_per_source=1)
        # 1 arxiv result + 1 github result = 2
        assert result["total_results"] == len(result["results"])

    async def test_only_arxiv_source(self):
        coordinator = _build_coordinator(sources=["arxiv"], integration_available=False)
        result = await coordinator.search_all("quantum computing")
        assert result["sources_searched"] == ["arxiv"]
        # Only arxiv results
        for r in result["results"]:
            assert r["source"] == "arxiv"

    async def test_only_github_source(self):
        coordinator = _build_coordinator(sources=["github"], integration_available=False)
        result = await coordinator.search_all("rust async")
        assert result["sources_searched"] == ["github"]
        for r in result["results"]:
            assert r["source"] == "github"

    async def test_unknown_source_skipped(self):
        coordinator = _build_coordinator(sources=["huggingface"], integration_available=False)
        result = await coordinator.search_all("bert")
        # Neither arxiv nor github in sources
        assert result["sources_searched"] == []
        assert result["total_results"] == 0

    async def test_empty_sources(self):
        """Empty sources list means neither arxiv nor github will be searched."""
        coordinator = _build_coordinator(sources=["huggingface"], integration_available=False)
        result = await coordinator.search_all("test")
        assert result["sources_searched"] == []
        assert result["total_results"] == 0

    async def test_results_combined_from_both_sources(self):
        coordinator = _build_coordinator(integration_available=False)
        result = await coordinator.search_all("deep learning")
        # At least one result from each source
        sources = {r["source"] for r in result["results"]}
        assert "arxiv" in sources
        assert "github" in sources

    async def test_limit_per_source_parameter(self):
        coordinator = _build_coordinator(integration_available=False)
        result = await coordinator.search_all("test", limit_per_source=2)
        # With fallback, each source returns exactly 1 result
        assert result["total_results"] >= 1

    async def test_returns_query_in_result(self):
        coordinator = _build_coordinator(integration_available=False)
        result = await coordinator.search_all("constitutional ai")
        assert result["query"] == "constitutional ai"

    async def test_with_live_integrator(self):
        arxiv_result = _make_research_result(title="arXiv paper")
        github_result = _make_research_result(title="GitHub repo")

        mock_integrator = MagicMock()

        async def mock_search(query, sources, research_type, max_results):
            # Return appropriate results based on source
            s = sources[0]
            if hasattr(s, "value"):
                src_val = s.value
            else:
                src_val = str(s)
            if "ARXIV" in src_val.upper():
                return [arxiv_result]
            return [github_result]

        mock_integrator.search = mock_search
        integration_key = "enhanced_agent_bus.research_integration"
        fake_mod = _make_research_integration_module(integrator=mock_integrator)

        coordinator = _build_coordinator(sources=["arxiv", "github"], integrator=mock_integrator)

        with patch.dict(sys.modules, {integration_key: fake_mod}):
            result = await coordinator.search_all("transformers", limit_per_source=1)

        assert result["total_results"] == len(result["results"])
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH


# ---------------------------------------------------------------------------
# synthesize_research
# ---------------------------------------------------------------------------


class TestSynthesizeResearch:
    async def test_fallback_when_no_integrator(self):
        coordinator = _build_coordinator(integration_available=False)
        sources = [
            {"title": "Paper A", "summary": "About AI"},
            {"title": "Paper B", "summary": "About ML"},
        ]
        result = await coordinator.synthesize_research(sources)
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert result["confidence_score"] == 0.3
        assert "Analyzed 2 sources" in result["key_findings"]
        assert result["consensus_points"] == []
        assert len(result["recommendations"]) == 2
        assert "Paper A" in result["recommendations"][0]

    async def test_fallback_with_empty_sources(self):
        coordinator = _build_coordinator(integration_available=False)
        result = await coordinator.synthesize_research([])
        assert "Analyzed 0 sources" in result["key_findings"]
        assert result["recommendations"] == []

    async def test_fallback_truncates_to_5_titles(self):
        coordinator = _build_coordinator(integration_available=False)
        sources = [{"title": f"Paper {i}"} for i in range(10)]
        result = await coordinator.synthesize_research(sources)
        # Only first 5 titles used for recommendations
        assert len(result["recommendations"]) == 5

    async def test_fallback_handles_missing_title(self):
        coordinator = _build_coordinator(integration_available=False)
        sources = [{"summary": "No title here"}]
        result = await coordinator.synthesize_research(sources)
        # title defaults to empty string via .get("title", "")
        assert len(result["recommendations"]) == 1

    async def test_uses_integrator_when_available(self):
        synthesis = _make_synthesis_result(
            key_findings=["finding A"],
            consensus_points=["consensus A"],
            recommendations=["rec A"],
            confidence_score=0.92,
        )
        mock_integrator = MagicMock()
        mock_integrator.synthesize = AsyncMock(return_value=synthesis)

        coordinator = _build_coordinator(integrator=mock_integrator)
        sources = [{"title": "Paper", "summary": "Content"}]
        result = await coordinator.synthesize_research(sources)

        assert result["key_findings"] == ["finding A"]
        assert result["consensus_points"] == ["consensus A"]
        assert result["recommendations"] == ["rec A"]
        assert result["confidence_score"] == 0.92
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_integrator_synthesis_without_key_findings_attr(self):
        """synthesis has no key_findings / consensus_points / recommendations attrs."""

        class MinimalSynthesis:
            """Only has confidence_score — no list attributes."""

            confidence_score = 0.5

        mock_integrator = MagicMock()
        mock_integrator.synthesize = AsyncMock(return_value=MinimalSynthesis())

        coordinator = _build_coordinator(integrator=mock_integrator)
        result = await coordinator.synthesize_research([{"title": "T"}])

        assert result["key_findings"] == []
        assert result["consensus_points"] == []
        assert result["recommendations"] == []
        assert result["confidence_score"] == 0.5

    async def test_integrator_synthesis_without_confidence_score(self):
        """synthesis has no confidence_score — getattr falls back to 0.7."""

        class SynthesisNoScore:
            key_findings: ClassVar[list] = ["f"]
            consensus_points: ClassVar[list] = ["c"]
            recommendations: ClassVar[list] = ["r"]

        mock_integrator = MagicMock()
        mock_integrator.synthesize = AsyncMock(return_value=SynthesisNoScore())

        coordinator = _build_coordinator(integrator=mock_integrator)
        result = await coordinator.synthesize_research([{"title": "T"}])

        assert result["confidence_score"] == 0.7

    async def test_fallback_on_integrator_runtime_error(self):
        mock_integrator = MagicMock()
        mock_integrator.synthesize = AsyncMock(side_effect=RuntimeError("err"))

        coordinator = _build_coordinator(integrator=mock_integrator)
        sources = [{"title": "Paper X"}]
        result = await coordinator.synthesize_research(sources)

        # Falls back to basic synthesis
        assert result["confidence_score"] == 0.3
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_fallback_on_integrator_timeout_error(self):
        mock_integrator = MagicMock()
        mock_integrator.synthesize = AsyncMock(side_effect=TimeoutError("timeout"))

        coordinator = _build_coordinator(integrator=mock_integrator)
        result = await coordinator.synthesize_research([{"title": "T"}])

        assert result["confidence_score"] == 0.3

    async def test_fallback_on_integrator_connection_error(self):
        mock_integrator = MagicMock()
        mock_integrator.synthesize = AsyncMock(side_effect=ConnectionError("net"))

        coordinator = _build_coordinator(integrator=mock_integrator)
        result = await coordinator.synthesize_research([])

        assert result["key_findings"] == ["Analyzed 0 sources"]

    async def test_focus_parameter_accepted(self):
        coordinator = _build_coordinator(integration_available=False)
        result = await coordinator.synthesize_research([{"title": "P"}], focus="trends")
        assert isinstance(result, dict)

    async def test_synthesis_result_structure_keys(self):
        coordinator = _build_coordinator(integration_available=False)
        result = await coordinator.synthesize_research([])
        assert "key_findings" in result
        assert "consensus_points" in result
        assert "recommendations" in result
        assert "confidence_score" in result
        assert "constitutional_hash" in result


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------


class TestProtocolCompliance:
    def test_satisfies_research_coordinator_protocol(self):
        from enhanced_agent_bus.coordinators import (
            ResearchCoordinatorProtocol,
        )

        coordinator = _build_coordinator(integration_available=False)
        assert isinstance(coordinator, ResearchCoordinatorProtocol)

    def test_constitutional_hash_class_attribute(self):
        from enhanced_agent_bus.coordinators.research_coordinator import (
            ResearchCoordinator,
        )

        assert ResearchCoordinator.constitutional_hash == CONSTITUTIONAL_HASH

    def test_can_import_from_coordinators_package(self):
        from enhanced_agent_bus.coordinators import ResearchCoordinator

        assert ResearchCoordinator is not None


# ---------------------------------------------------------------------------
# Error tuple coverage
# ---------------------------------------------------------------------------


class TestErrorTupleCoverage:
    """Ensure all exception types in _RESEARCH_COORDINATOR_OPERATION_ERRORS
    are exercised through the integration init path."""

    @pytest.mark.parametrize(
        "exc",
        [
            RuntimeError("r"),
            ValueError("v"),
            TypeError("t"),
            AttributeError("a"),
            LookupError("l"),
            OSError("o"),
            TimeoutError("to"),
            ConnectionError("c"),
        ],
    )
    def test_init_error_types_are_caught(self, exc):
        coordinator = _build_coordinator(create_raises=exc)
        assert coordinator._initialized is False
        assert coordinator._integrator is None

    @pytest.mark.parametrize(
        "exc",
        [
            RuntimeError("r"),
            ValueError("v"),
            TypeError("t"),
            AttributeError("a"),
            LookupError("l"),
            OSError("o"),
            TimeoutError("to"),
            ConnectionError("c"),
        ],
    )
    async def test_arxiv_search_error_types_are_caught(self, exc):
        mock_integrator = MagicMock()
        mock_integrator.search = AsyncMock(side_effect=exc)
        integration_key = "enhanced_agent_bus.research_integration"
        fake_mod = _make_research_integration_module(integrator=mock_integrator)

        coordinator = _build_coordinator(integrator=mock_integrator)
        with patch.dict(sys.modules, {integration_key: fake_mod}):
            results = await coordinator.search_arxiv("test")

        assert results[0]["relevance_score"] == 0.0

    @pytest.mark.parametrize(
        "exc",
        [
            RuntimeError("r"),
            ValueError("v"),
            TypeError("t"),
            AttributeError("a"),
            LookupError("l"),
            OSError("o"),
            TimeoutError("to"),
            ConnectionError("c"),
        ],
    )
    async def test_github_search_error_types_are_caught(self, exc):
        mock_integrator = MagicMock()
        mock_integrator.search = AsyncMock(side_effect=exc)
        integration_key = "enhanced_agent_bus.research_integration"
        fake_mod = _make_research_integration_module(integrator=mock_integrator)

        coordinator = _build_coordinator(integrator=mock_integrator)
        with patch.dict(sys.modules, {integration_key: fake_mod}):
            results = await coordinator.search_github("test")

        assert results[0]["relevance_score"] == 0.0

    @pytest.mark.parametrize(
        "exc",
        [
            RuntimeError("r"),
            ValueError("v"),
            TypeError("t"),
            AttributeError("a"),
            LookupError("l"),
            OSError("o"),
            TimeoutError("to"),
            ConnectionError("c"),
        ],
    )
    async def test_synthesis_error_types_are_caught(self, exc):
        mock_integrator = MagicMock()
        mock_integrator.synthesize = AsyncMock(side_effect=exc)

        coordinator = _build_coordinator(integrator=mock_integrator)
        result = await coordinator.synthesize_research([{"title": "T"}])

        assert result["confidence_score"] == 0.3
