"""
ACGS-2 Context & Memory - Cognee Knowledge Graph Integration
Constitutional Hash: 608508a9bd224290

Knowledge graph memory for constitutional governance using Cognee.
Provides graph-based reasoning over principles, amendments, and precedents.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)

try:
    import cognee

    HAS_COGNEE = True
except ImportError:
    HAS_COGNEE = False


@dataclass
class CogneeConfig:
    """Configuration for Cognee knowledge graph integration."""

    llm_api_key: str | None = None
    graph_backend: str = "networkx"  # networkx, neo4j, falkordb
    vector_backend: str = "lancedb"  # lancedb, qdrant, weaviate
    auto_cognify: bool = True
    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass
class ComplianceResult:
    """Result of a constitutional compliance query."""

    query: str
    findings: list[dict[str, Any]] = field(default_factory=list)
    is_compliant: bool | None = None
    relevant_principles: list[str] = field(default_factory=list)
    relevant_precedents: list[str] = field(default_factory=list)
    reasoning: str = ""
    latency_ms: float = 0.0
    constitutional_hash: str = CONSTITUTIONAL_HASH


class ConstitutionalKnowledgeGraph:
    """Knowledge graph memory for constitutional governance using Cognee.

    Provides:
    - Ingestion of constitutional principles as graph entities
    - Ingestion of governance precedents (past decisions)
    - Graph-based compliance queries with multi-hop reasoning
    - Amendment tracking with supersession relationships

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(self, config: CogneeConfig | None = None) -> None:
        if not HAS_COGNEE:
            raise RuntimeError("cognee is not installed. Install with: pip install cognee")
        self._config = config or CogneeConfig()
        self._initialized = False
        self._stats = {
            "principles_ingested": 0,
            "precedents_ingested": 0,
            "amendments_ingested": 0,
            "queries_executed": 0,
        }

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    @property
    def stats(self) -> dict[str, int]:
        return dict(self._stats)

    async def initialize(self) -> None:
        """Initialize Cognee with governance-specific configuration."""
        if self._initialized:
            return
        self._initialized = True
        logger.info(
            "cognee_knowledge_graph_initialized",
            graph_backend=self._config.graph_backend,
            vector_backend=self._config.vector_backend,
        )

    async def ingest_principles(self, principles: list[dict[str, Any]]) -> int:
        """Load constitutional principles into the knowledge graph.

        Args:
            principles: List of dicts with keys: id, category, text, weight, hash (optional)

        Returns:
            Number of principles ingested.
        """
        self._ensure_initialized()

        for principle in principles:
            text = (
                f"Constitutional Principle [{principle['id']}]: "
                f"{principle['category']} — {principle['text']}. "
                f"Weight: {principle.get('weight', 1.0)}. "
                f"Hash: {principle.get('hash', 'none')}."
            )
            await cognee.add(text, dataset_name="constitutional_principles")

        if self._config.auto_cognify:
            await cognee.cognify()

        count = len(principles)
        self._stats["principles_ingested"] += count
        logger.info("principles_ingested", count=count)
        return count

    async def ingest_precedents(self, decisions: list[dict[str, Any]]) -> int:
        """Load past governance decisions as episodic precedents.

        Args:
            decisions: List of dicts with keys: id, action, verdict, reasoning, principle_ids

        Returns:
            Number of precedents ingested.
        """
        self._ensure_initialized()

        for decision in decisions:
            text = (
                f"Governance Decision [{decision['id']}]: "
                f"Action '{decision.get('action', 'unknown')}' was {decision['verdict']}. "
                f"Reasoning: {decision.get('reasoning', 'none')}. "
                f"Principles applied: {decision.get('principle_ids', [])}."
            )
            await cognee.add(text, dataset_name="governance_precedents")

        if self._config.auto_cognify:
            await cognee.cognify()

        count = len(decisions)
        self._stats["precedents_ingested"] += count
        logger.info("precedents_ingested", count=count)
        return count

    async def add_amendment(
        self,
        amendment_text: str,
        supersedes_ids: list[str] | None = None,
    ) -> None:
        """Record a constitutional amendment with graph relationships.

        Args:
            amendment_text: The amendment content.
            supersedes_ids: IDs of principles this amendment supersedes.
        """
        self._ensure_initialized()

        text = (
            f"Constitutional Amendment: {amendment_text}. "
            f"This amendment supersedes principles: {supersedes_ids or []}."
        )
        await cognee.add(text, dataset_name="constitutional_amendments")

        if self._config.auto_cognify:
            await cognee.cognify()

        self._stats["amendments_ingested"] += 1
        logger.info("amendment_ingested", supersedes=supersedes_ids or [])

    async def query_compliance(
        self,
        action_description: str,
        *,
        mode: str = "graph_completion",
    ) -> ComplianceResult:
        """Query the knowledge graph for constitutional compliance.

        Args:
            action_description: Description of the action to check.
            mode: Cognee search mode. One of:
                - "graph_completion": Multi-hop graph traversal (best for compliance)
                - "insights": Vector similarity search (fast, less precise)
                - "graph_summary": Summarized graph context

        Returns:
            ComplianceResult with findings, relevant principles, and reasoning.
        """
        self._ensure_initialized()

        query = (
            f"Does the following action comply with constitutional principles? "
            f"Identify any violations or relevant precedents. "
            f"Action: {action_description}"
        )

        start = time.monotonic()
        results = await cognee.search(
            query_type=mode,
            query_text=query,
        )
        latency = (time.monotonic() - start) * 1000

        findings = [
            {
                "content": str(r),
                "relevance": getattr(r, "score", None),
            }
            for r in results
        ]
        is_compliant, reasoning = self._derive_compliance_verdict(findings)

        self._stats["queries_executed"] += 1
        logger.info(
            "compliance_query_executed",
            mode=mode,
            results_count=len(findings),
            latency_ms=round(latency, 2),
        )

        return ComplianceResult(
            query=action_description,
            findings=findings,
            is_compliant=is_compliant,
            reasoning=reasoning,
            latency_ms=latency,
            constitutional_hash=self._config.constitutional_hash,
        )

    async def search(
        self,
        query_text: str,
        *,
        mode: str = "insights",
        max_results: int = 10,
    ) -> list[dict[str, Any]]:
        """General-purpose search across the knowledge graph.

        Args:
            query_text: Search query.
            mode: Search mode (insights, graph_completion, graph_summary).
            max_results: Maximum results to return.

        Returns:
            List of result dicts with content and relevance.
        """
        self._ensure_initialized()

        results = await cognee.search(
            query_type=mode,
            query_text=query_text,
        )

        return [
            {
                "content": str(r),
                "relevance": getattr(r, "score", None),
            }
            for r in results[:max_results]
        ]

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            raise RuntimeError(
                "ConstitutionalKnowledgeGraph not initialized. Call await initialize() first."
            )

    @staticmethod
    def _derive_compliance_verdict(findings: list[dict[str, Any]]) -> tuple[bool | None, str]:
        if not findings:
            return None, ""

        negative_markers = (
            "violation",
            "violates",
            "non-compliant",
            "not compliant",
            "does not comply",
            "forbidden",
            "blocked",
            "denied",
            "reject",
        )
        positive_markers = (
            "compliant",
            "complies",
            "approved",
            "allowed",
            "permit",
            "permitted",
            "no violation",
        )

        relevant_snippets: list[str] = []
        saw_positive = False
        for finding in findings:
            content = str(finding.get("content", ""))
            content_lower = content.lower()
            if any(marker in content_lower for marker in negative_markers):
                return False, content
            if any(marker in content_lower for marker in positive_markers):
                saw_positive = True
                relevant_snippets.append(content)

        if saw_positive:
            return True, relevant_snippets[0]

        return None, ""
