"""
ACGS-2 Context & Memory - Cognee Long-Term Memory Adapter
Constitutional Hash: 608508a9bd224290

Drop-in adapter that implements the existing memory interface using
Cognee's knowledge graph as the backend. Replaces SQLite-based
episodic/semantic memory with graph-based storage and retrieval.

Key Advantages over SQLite LTM:
- Multi-hop graph traversal for compliance queries
- Automatic entity/relationship extraction
- Self-improving memory via Cognee's memify cycle
- Shared persistent memory across all agents
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

from enhanced_agent_bus.observability.structured_logging import get_logger

from .cognee_memory import (
    HAS_COGNEE,
    CogneeConfig,
    ConstitutionalKnowledgeGraph,
)
from .models import (
    EpisodicMemoryEntry,
    MemoryConsolidationResult,
    MemoryOperation,
    MemoryOperationType,
    MemoryQuery,
    SemanticMemoryEntry,
)

logger = get_logger(__name__)


@dataclass
class CogneeLTMConfig:
    """Configuration for the Cognee LTM adapter."""

    cognee_config: CogneeConfig = field(default_factory=CogneeConfig)
    default_search_mode: str = "graph_completion"
    max_results: int = 10
    enable_audit_trail: bool = True
    constitutional_hash: str = CONSTITUTIONAL_HASH


class CogneeLongTermMemory:
    """Long-term memory backed by Cognee knowledge graph.

    Provides the same interface as LongTermMemoryStore but uses
    Cognee for storage and retrieval. Episodic memories become
    governance precedents in the graph; semantic memories become
    constitutional knowledge entities.

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(self, config: CogneeLTMConfig | None = None) -> None:
        if not HAS_COGNEE:
            raise RuntimeError("cognee is not installed. Install with: pip install cognee")
        self._config = config or CogneeLTMConfig()
        self._graph = ConstitutionalKnowledgeGraph(config=self._config.cognee_config)
        self._operations: list[MemoryOperation] = []
        self._stats = {
            "episodic_stored": 0,
            "semantic_stored": 0,
            "queries": 0,
            "consolidations": 0,
        }

    @property
    def is_initialized(self) -> bool:
        return self._graph.is_initialized

    @property
    def stats(self) -> dict[str, int]:
        return dict(self._stats)

    async def initialize(self) -> None:
        """Initialize the Cognee knowledge graph backend."""
        await self._graph.initialize()
        logger.info("cognee_ltm_initialized")

    async def store_episodic(
        self,
        entry: EpisodicMemoryEntry,
        *,
        tenant_id: str | None = None,
    ) -> None:
        """Store an episodic memory as a governance precedent.

        Maps episodic memory fields to Cognee's precedent format:
        - entry_id -> decision id
        - event_type -> action type
        - content -> reasoning
        - outcome -> verdict
        """
        start = time.monotonic()
        tenant = tenant_id or entry.tenant_id

        await self._graph.ingest_precedents(
            [
                {
                    "id": entry.entry_id,
                    "action": entry.event_type,
                    "verdict": entry.outcome or "unknown",
                    "reasoning": entry.content,
                    "principle_ids": entry.context.get("principle_ids", []),
                }
            ]
        )

        latency = (time.monotonic() - start) * 1000
        self._stats["episodic_stored"] += 1
        self._record_operation(
            op_type=MemoryOperationType.STORE,
            tenant_id=tenant,
            session_id=entry.session_id,
            entry_id=entry.entry_id,
            success=True,
            latency_ms=latency,
        )

    async def store_semantic(
        self,
        entry: SemanticMemoryEntry,
        *,
        tenant_id: str | None = None,
    ) -> None:
        """Store semantic knowledge in the graph.

        Maps semantic memory fields to Cognee's principle format:
        - entry_id -> principle id
        - knowledge_type -> category
        - content -> text
        - confidence -> weight
        """
        start = time.monotonic()

        await self._graph.ingest_principles(
            [
                {
                    "id": entry.entry_id,
                    "category": entry.knowledge_type,
                    "text": entry.content,
                    "weight": entry.confidence,
                }
            ]
        )

        latency = (time.monotonic() - start) * 1000
        self._stats["semantic_stored"] += 1
        self._record_operation(
            op_type=MemoryOperationType.STORE,
            tenant_id=tenant_id or "system",
            session_id=None,
            entry_id=entry.entry_id,
            success=True,
            latency_ms=latency,
        )

    async def recall(
        self,
        query: MemoryQuery,
    ) -> list[dict[str, Any]]:
        """Recall memories via graph traversal.

        Uses Cognee's search modes:
        - "graph_completion" for multi-hop reasoning (default)
        - "insights" for fast vector similarity
        - "graph_summary" for summarized context
        """
        start = time.monotonic()

        mode = self._config.default_search_mode
        if query.query_type == "episodic":
            mode = "graph_completion"
        elif query.query_type == "semantic":
            mode = "insights"

        results = await self._graph.search(
            query_text=query.query_text,
            mode=mode,
            max_results=query.max_results,
        )

        latency = (time.monotonic() - start) * 1000
        self._stats["queries"] += 1
        self._record_operation(
            op_type=MemoryOperationType.RETRIEVE,
            tenant_id=query.tenant_id or "system",
            session_id=query.session_id,
            entry_id=None,
            success=True,
            latency_ms=latency,
            details={"results_count": len(results), "mode": mode},
        )

        return results

    async def query_compliance(
        self,
        action_description: str,
    ) -> dict[str, Any]:
        """Query constitutional compliance via knowledge graph.

        This is the key advantage over flat SQLite storage:
        multi-hop graph traversal across principles, amendments,
        and precedents.
        """
        result = await self._graph.query_compliance(action_description)
        return {
            "query": result.query,
            "findings": result.findings,
            "is_compliant": result.is_compliant,
            "latency_ms": result.latency_ms,
        }

    async def consolidate(self) -> MemoryConsolidationResult:
        """Trigger Cognee's memify cycle for memory consolidation.

        Cognee's memify:
        - Prunes stale nodes
        - Strengthens frequently accessed connections
        - Reweights edges based on usage signals
        - Adds derived facts
        """
        start = time.monotonic()
        # Cognee handles consolidation internally via cognify/memify
        # We trigger a re-cognify to rebuild the graph
        try:
            import cognee

            await cognee.cognify()
        except Exception:
            logger.exception("cognee_consolidation_failed")

        latency = (time.monotonic() - start) * 1000
        self._stats["consolidations"] += 1

        return MemoryConsolidationResult(
            entries_processed=self._stats["episodic_stored"] + self._stats["semantic_stored"],
            entries_consolidated=0,
            entries_archived=0,
            entries_deleted=0,
            consolidation_time_ms=latency,
            memory_freed_bytes=0,
            new_semantic_entries=0,
        )

    def get_operations(self) -> list[MemoryOperation]:
        """Return audit trail of memory operations."""
        return list(self._operations)

    def _record_operation(
        self,
        *,
        op_type: MemoryOperationType,
        tenant_id: str,
        session_id: str | None,
        entry_id: str | None,
        success: bool,
        latency_ms: float,
        details: dict[str, Any] | None = None,
    ) -> None:
        if not self._config.enable_audit_trail:
            return
        self._operations.append(
            MemoryOperation(
                operation_id=str(uuid.uuid4()),
                operation_type=op_type,
                timestamp=datetime.now(UTC),
                tenant_id=tenant_id,
                session_id=session_id,
                entry_id=entry_id,
                success=success,
                latency_ms=latency_ms,
                details=details or {},
            )
        )
