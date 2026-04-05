"""
Research Coordinator - Manages research integration with external sources.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)
_RESEARCH_COORDINATOR_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
)


class ResearchCoordinator:
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def __init__(
        self,
        sources: list[str] | None = None,
        max_results_per_source: int = 5,
    ):
        self._sources = sources or ["arxiv", "github", "huggingface"]
        self._max_results = max_results_per_source
        self._integrator: object | None = None
        self._initialized = False

        self._initialize_integrator()

    def _initialize_integrator(self) -> None:
        try:
            from ..research_integration import create_research_integrator

            self._integrator = create_research_integrator(
                constitutional_hash=self.constitutional_hash,
            )
            self._initialized = True
            logger.info(f"ResearchCoordinator: Initialized with sources={self._sources}")
        except ImportError:
            logger.info("Research integration not available, using basic search")
        except _RESEARCH_COORDINATOR_OPERATION_ERRORS as e:
            logger.warning(f"Research integrator init failed: {e}")

    @property
    def is_available(self) -> bool:
        return self._initialized and self._integrator is not None

    async def search_arxiv(
        self,
        query: str,
        limit: int = 5,
        categories: list[str] | None = None,
    ) -> list[JSONDict]:
        if self._integrator:
            try:
                from ..research_integration import ResearchSource, ResearchType

                results = await self._integrator.search(
                    query=query,
                    sources=[ResearchSource.ARXIV],
                    research_type=ResearchType.PAPERS,
                    max_results=limit,
                )
                return [
                    {
                        "source": "arxiv",
                        "title": r.title,
                        "summary": r.summary,
                        "url": r.url,
                        "relevance_score": r.relevance_score,
                        "constitutional_hash": self.constitutional_hash,
                    }
                    for r in results
                ]
            except _RESEARCH_COORDINATOR_OPERATION_ERRORS as e:
                logger.error(f"arXiv search failed: {e}")

        return [
            {
                "source": "arxiv",
                "title": f"Mock result for: {query}",
                "summary": "Research integration not available",
                "url": f"https://arxiv.org/search/?query={query}",
                "relevance_score": 0.0,
                "constitutional_hash": self.constitutional_hash,
            }
        ]

    async def search_github(
        self,
        query: str,
        limit: int = 5,
        language: str | None = None,
    ) -> list[JSONDict]:
        if self._integrator:
            try:
                from ..research_integration import ResearchSource, ResearchType

                results = await self._integrator.search(
                    query=query,
                    sources=[ResearchSource.GITHUB],
                    research_type=ResearchType.CODE,
                    max_results=limit,
                )
                return [
                    {
                        "source": "github",
                        "title": r.title,
                        "summary": r.summary,
                        "url": r.url,
                        "relevance_score": r.relevance_score,
                        "stars": getattr(r, "stars", 0),
                        "constitutional_hash": self.constitutional_hash,
                    }
                    for r in results
                ]
            except _RESEARCH_COORDINATOR_OPERATION_ERRORS as e:
                logger.error(f"GitHub search failed: {e}")

        return [
            {
                "source": "github",
                "title": f"Mock result for: {query}",
                "summary": "Research integration not available",
                "url": f"https://github.com/search?q={query}",
                "relevance_score": 0.0,
                "constitutional_hash": self.constitutional_hash,
            }
        ]

    async def search_all(
        self,
        query: str,
        limit_per_source: int = 3,
    ) -> JSONDict:
        results: JSONDict = {
            "query": query,
            "sources_searched": [],
            "results": [],
            "constitutional_hash": self.constitutional_hash,
        }

        if "arxiv" in self._sources:
            arxiv_results = await self.search_arxiv(query, limit=limit_per_source)
            results["sources_searched"].append("arxiv")
            results["results"].extend(arxiv_results)

        if "github" in self._sources:
            github_results = await self.search_github(query, limit=limit_per_source)
            results["sources_searched"].append("github")
            results["results"].extend(github_results)

        results["total_results"] = len(results["results"])
        return results

    async def synthesize_research(
        self,
        sources: list[JSONDict],
        focus: str = "key_findings",
    ) -> JSONDict:
        if self._integrator:
            try:
                synthesis = await self._integrator.synthesize(sources=sources)
                return {
                    "key_findings": (
                        synthesis.key_findings if hasattr(synthesis, "key_findings") else []
                    ),
                    "consensus_points": (
                        synthesis.consensus_points if hasattr(synthesis, "consensus_points") else []
                    ),
                    "recommendations": (
                        synthesis.recommendations if hasattr(synthesis, "recommendations") else []
                    ),
                    "confidence_score": getattr(synthesis, "confidence_score", 0.7),
                    "constitutional_hash": self.constitutional_hash,
                }
            except _RESEARCH_COORDINATOR_OPERATION_ERRORS as e:
                logger.error(f"Research synthesis failed: {e}")

        titles = [s.get("title", "") for s in sources[:5]]
        return {
            "key_findings": [f"Analyzed {len(sources)} sources"],
            "consensus_points": [],
            "recommendations": [f"Review: {t}" for t in titles],
            "confidence_score": 0.3,
            "constitutional_hash": self.constitutional_hash,
        }

    def get_stats(self) -> JSONDict:
        return {
            "constitutional_hash": self.constitutional_hash,
            "available": self.is_available,
            "configured_sources": self._sources,
            "max_results_per_source": self._max_results,
        }
