"""
ACGS-2 Context & Memory - Long Term Memory Store
Constitutional Hash: cdd01ef066bc6cf2

Persistent memory management for multi-day autonomous governance.
Implements episodic and semantic memory with consolidation.

Key Features:
- Cross-session persistence with SQLite backend
- Memory consolidation for efficient storage
- Episodic memory for case-based reasoning
- Semantic memory for policy knowledge
- Constitutional compliance audit trail
"""

import sqlite3
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path

try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH  # noqa: E402
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
from src.core.shared.json_utils import dumps as json_dumps
from src.core.shared.json_utils import loads as json_loads

try:
    from src.core.shared.types import (
        JSONDict,
        JSONList,
    )  # noqa: E402
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]
    JSONList = list  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from .models import (
    EpisodicMemoryEntry,
    MemoryConsolidationResult,
    MemoryOperation,
    MemoryOperationType,
    SemanticMemoryEntry,
)

logger = get_logger(__name__)
_LTM_PERSISTENCE_ERRORS = (
    sqlite3.Error,
    OSError,
    ValueError,
    TypeError,
    RuntimeError,
)


class MemoryTier(str, Enum):  # noqa: UP042
    """Memory storage tiers."""

    WORKING = "working"  # Fast, volatile memory
    SHORT_TERM = "short_term"  # Recent interactions
    LONG_TERM = "long_term"  # Persistent knowledge
    ARCHIVAL = "archival"  # Historical data


class ConsolidationStrategy(str, Enum):  # noqa: UP042
    """Strategies for memory consolidation."""

    TIME_BASED = "time_based"  # Consolidate based on age
    ACCESS_BASED = "access_based"  # Consolidate based on access patterns
    RELEVANCE_BASED = "relevance_based"  # Consolidate based on relevance
    SIMILARITY_BASED = "similarity_based"  # Merge similar memories


@dataclass
class LongTermMemoryConfig:
    """Configuration for long-term memory store.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    db_path: str = ".acgs2_ltm.db"
    max_episodic_entries: int = 100_000
    max_semantic_entries: int = 50_000
    consolidation_interval_hours: int = 24
    retention_days: int = 365
    similarity_threshold: float = 0.85
    enable_compression: bool = True
    enable_persistence: bool = True
    enable_audit_trail: bool = True
    working_memory_size: int = 1000
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def __post_init__(self) -> None:
        if self.constitutional_hash != CONSTITUTIONAL_HASH:
            raise ValueError(f"Invalid constitutional hash: {self.constitutional_hash}")


@dataclass
class MemorySearchResult:
    """Result of memory search operation.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    entries: JSONList
    total_count: int
    search_time_ms: float
    relevance_scores: dict[str, float] = field(default_factory=dict)
    metadata: JSONDict = field(default_factory=dict)
    constitutional_hash: str = CONSTITUTIONAL_HASH


class LongTermMemoryStore:
    """Persistent memory store for multi-day autonomous governance.

    Manages episodic and semantic memory with consolidation
    and constitutional compliance tracking.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def __init__(
        self,
        config: LongTermMemoryConfig | None = None,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
    ):
        self.config = config or LongTermMemoryConfig()
        self.constitutional_hash = constitutional_hash

        if constitutional_hash != CONSTITUTIONAL_HASH:
            raise ValueError(f"Invalid constitutional hash: {constitutional_hash}")

        # In-memory caches
        self._working_memory: JSONDict = {}
        self._episodic_cache: dict[str, EpisodicMemoryEntry] = {}
        self._semantic_cache: dict[str, SemanticMemoryEntry] = {}

        # Audit trail
        self._audit_log: list[MemoryOperation] = []

        # Database connection
        self._db_connection: sqlite3.Connection | None = None

        # Metrics
        self._metrics = {
            "episodic_writes": 0,
            "episodic_reads": 0,
            "semantic_writes": 0,
            "semantic_reads": 0,
            "consolidations": 0,
            "cache_hits": 0,
            "cache_misses": 0,
        }

        # Initialize persistence if enabled
        if self.config.enable_persistence:
            self._init_persistence()

        logger.info(
            f"Initialized LongTermMemoryStore (persistence={self.config.enable_persistence})"
        )

    def _init_persistence(self) -> None:
        """Initialize SQLite persistence layer."""
        try:
            db_path = Path(self.config.db_path)
            self._db_connection = sqlite3.connect(str(db_path), check_same_thread=False)

            cursor = self._db_connection.cursor()

            # Episodic memory table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS episodic_memory (
                    entry_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    outcome TEXT,
                    context TEXT,
                    relevance_decay REAL DEFAULT 1.0,
                    access_count INTEGER DEFAULT 0,
                    last_accessed TEXT,
                    embedding BLOB,
                    constitutional_hash TEXT NOT NULL
                )
            """)

            # Semantic memory table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS semantic_memory (
                    entry_id TEXT PRIMARY KEY,
                    knowledge_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    source TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    embedding BLOB,
                    related_entries TEXT,
                    access_count INTEGER DEFAULT 0,
                    validation_status TEXT DEFAULT 'pending',
                    metadata TEXT,
                    constitutional_hash TEXT NOT NULL
                )
            """)

            # Audit trail table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS memory_audit (
                    operation_id TEXT PRIMARY KEY,
                    operation_type TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    session_id TEXT,
                    entry_id TEXT,
                    success INTEGER NOT NULL,
                    latency_ms REAL NOT NULL,
                    details TEXT,
                    constitutional_hash TEXT NOT NULL
                )
            """)

            # Create indices
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_episodic_session
                ON episodic_memory(session_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_episodic_tenant
                ON episodic_memory(tenant_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_semantic_type
                ON semantic_memory(knowledge_type)
            """)

            self._db_connection.commit()
            logger.info(f"Initialized LTM persistence at {db_path}")

        except _LTM_PERSISTENCE_ERRORS as e:
            logger.error(f"Failed to initialize persistence: {e}")
            self._db_connection = None

    async def store_episodic(
        self,
        session_id: str,
        tenant_id: str,
        event_type: str,
        content: str,
        outcome: str | None = None,
        context: JSONDict | None = None,
        embedding: list[float] | None = None,
    ) -> str:
        """Store an episodic memory entry.

        Args:
            session_id: Session identifier
            tenant_id: Tenant identifier
            event_type: Type of event
            content: Event content
            outcome: Event outcome
            context: Additional context
            embedding: Vector embedding

        Returns:
            Entry ID
        """
        import uuid

        start_time = time.perf_counter()

        entry = EpisodicMemoryEntry(
            entry_id=str(uuid.uuid4()),
            session_id=session_id,
            tenant_id=tenant_id,
            timestamp=datetime.now(UTC),
            event_type=event_type,
            content=content,
            outcome=outcome,
            context=context or {},
            embedding=embedding,
            constitutional_hash=self.constitutional_hash,
        )

        # Store in cache
        self._episodic_cache[entry.entry_id] = entry

        # Persist if enabled
        if self.config.enable_persistence and self._db_connection:
            await self._persist_episodic(entry)

        # Audit
        latency = (time.perf_counter() - start_time) * 1000
        self._log_operation(
            operation_type=MemoryOperationType.STORE,
            tenant_id=tenant_id,
            session_id=session_id,
            entry_id=entry.entry_id,
            success=True,
            latency_ms=latency,
        )

        self._metrics["episodic_writes"] += 1
        return entry.entry_id

    async def _persist_episodic(self, entry: EpisodicMemoryEntry) -> None:
        """Persist episodic entry to database."""
        if not self._db_connection:
            return

        try:
            cursor = self._db_connection.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO episodic_memory
                (entry_id, session_id, tenant_id, timestamp, event_type,
                 content, outcome, context, relevance_decay, access_count,
                 last_accessed, embedding, constitutional_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    entry.entry_id,
                    entry.session_id,
                    entry.tenant_id,
                    entry.timestamp.isoformat(),
                    entry.event_type,
                    entry.content,
                    entry.outcome,
                    json_dumps(entry.context),
                    entry.relevance_decay,
                    entry.access_count,
                    entry.last_accessed.isoformat() if entry.last_accessed else None,
                    json_dumps(entry.embedding) if entry.embedding else None,
                    entry.constitutional_hash,
                ),
            )
            self._db_connection.commit()
        except _LTM_PERSISTENCE_ERRORS as e:
            logger.error(f"Failed to persist episodic entry: {e}")

    async def retrieve_episodic(
        self,
        entry_id: str | None = None,
        session_id: str | None = None,
        tenant_id: str | None = None,
        event_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[EpisodicMemoryEntry]:
        """Retrieve episodic memory entries.

        Args:
            entry_id: Specific entry ID
            session_id: Filter by session
            tenant_id: Filter by tenant
            event_type: Filter by event type
            limit: Maximum entries

        Returns:
            List of matching entries
        """
        time.perf_counter()

        # Check cache first
        if entry_id and entry_id in self._episodic_cache:
            self._metrics["cache_hits"] += 1
            entry = self._episodic_cache[entry_id]
            entry.record_access()
            return [entry]

        self._metrics["cache_misses"] += 1

        # Query from persistence
        entries = []
        if self.config.enable_persistence and self._db_connection:
            entries = await self._query_episodic(
                session_id=session_id,
                tenant_id=tenant_id,
                event_type=event_type,
                limit=limit,
            )

        # Update cache
        for entry in entries:
            self._episodic_cache[entry.entry_id] = entry

        self._metrics["episodic_reads"] += 1
        return entries

    async def _query_episodic(
        self,
        session_id: str | None,
        tenant_id: str | None,
        event_type: str | None,
        limit: int,
        offset: int = 0,
    ) -> list[EpisodicMemoryEntry]:
        """Query episodic entries from database."""
        if not self._db_connection:
            return []

        try:
            cursor = self._db_connection.cursor()

            query = "SELECT * FROM episodic_memory WHERE 1=1"
            params: JSONList = []

            if session_id:
                query += " AND session_id = ?"
                params.append(session_id)
            if tenant_id:
                query += " AND tenant_id = ?"
                params.append(tenant_id)
            if event_type:
                query += " AND event_type = ?"
                params.append(event_type)

            query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            cursor.execute(query, params)
            rows = cursor.fetchall()

            entries = []
            for row in rows:
                entry = EpisodicMemoryEntry(
                    entry_id=row[0],
                    session_id=row[1],
                    tenant_id=row[2],
                    timestamp=datetime.fromisoformat(row[3]),
                    event_type=row[4],
                    content=row[5],
                    outcome=row[6],
                    context=json_loads(row[7]) if row[7] else {},
                    relevance_decay=row[8],
                    access_count=row[9],
                    last_accessed=datetime.fromisoformat(row[10]) if row[10] else None,
                    embedding=json_loads(row[11]) if row[11] else None,
                    constitutional_hash=row[12],
                )
                entries.append(entry)

            return entries

        except _LTM_PERSISTENCE_ERRORS as e:
            logger.error(f"Failed to query episodic memory: {e}")
            return []

    async def store_semantic(
        self,
        knowledge_type: str,
        content: str,
        confidence: float,
        source: str,
        embedding: list[float] | None = None,
        related_entries: list[str] | None = None,
        metadata: JSONDict | None = None,
    ) -> str:
        """Store a semantic memory entry.

        Args:
            knowledge_type: Type of knowledge
            content: Knowledge content
            confidence: Confidence score
            source: Source of knowledge
            embedding: Vector embedding
            related_entries: Related entry IDs
            metadata: Additional metadata

        Returns:
            Entry ID
        """
        import uuid

        start_time = time.perf_counter()
        now = datetime.now(UTC)

        entry = SemanticMemoryEntry(
            entry_id=str(uuid.uuid4()),
            knowledge_type=knowledge_type,
            content=content,
            confidence=confidence,
            source=source,
            created_at=now,
            updated_at=now,
            embedding=embedding,
            related_entries=related_entries or [],
            metadata=metadata or {},
            constitutional_hash=self.constitutional_hash,
        )

        # Store in cache
        self._semantic_cache[entry.entry_id] = entry

        # Persist if enabled
        if self.config.enable_persistence and self._db_connection:
            await self._persist_semantic(entry)

        # Audit
        latency = (time.perf_counter() - start_time) * 1000
        self._log_operation(
            operation_type=MemoryOperationType.STORE,
            tenant_id="system",
            session_id=None,
            entry_id=entry.entry_id,
            success=True,
            latency_ms=latency,
        )

        self._metrics["semantic_writes"] += 1
        return entry.entry_id

    async def _persist_semantic(self, entry: SemanticMemoryEntry) -> None:
        """Persist semantic entry to database."""
        if not self._db_connection:
            return

        try:
            cursor = self._db_connection.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO semantic_memory
                (entry_id, knowledge_type, content, confidence, source,
                 created_at, updated_at, embedding, related_entries,
                 access_count, validation_status, metadata, constitutional_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    entry.entry_id,
                    entry.knowledge_type,
                    entry.content,
                    entry.confidence,
                    entry.source,
                    entry.created_at.isoformat(),
                    entry.updated_at.isoformat(),
                    json_dumps(entry.embedding) if entry.embedding else None,
                    json_dumps(entry.related_entries),
                    entry.access_count,
                    entry.validation_status,
                    json_dumps(entry.metadata),
                    entry.constitutional_hash,
                ),
            )
            self._db_connection.commit()
        except _LTM_PERSISTENCE_ERRORS as e:
            logger.error(f"Failed to persist semantic entry: {e}")

    async def search_semantic(
        self,
        query: str,
        knowledge_type: str | None = None,
        min_confidence: float = 0.5,
        limit: int = 10,
    ) -> MemorySearchResult:
        """Search semantic memory.

        Args:
            query: Search query
            knowledge_type: Filter by knowledge type
            min_confidence: Minimum confidence threshold
            limit: Maximum results

        Returns:
            MemorySearchResult with matching entries
        """
        start_time = time.perf_counter()

        # Simple text-based search (would use embeddings in production)
        query_lower = query.lower()
        results = []
        relevance_scores = {}

        for entry_id, entry in self._semantic_cache.items():
            if entry.confidence < min_confidence:
                continue
            if knowledge_type and entry.knowledge_type != knowledge_type:
                continue

            # Simple relevance scoring
            content_lower = entry.content.lower()
            if query_lower in content_lower:
                score = min(1.0, 0.5 + entry.confidence * 0.5)
                results.append(entry)
                relevance_scores[entry_id] = score

        # Sort by relevance
        results.sort(key=lambda e: relevance_scores.get(e.entry_id, 0), reverse=True)
        results = results[:limit]

        self._metrics["semantic_reads"] += 1

        return MemorySearchResult(
            entries=results,
            total_count=len(results),
            search_time_ms=(time.perf_counter() - start_time) * 1000,
            relevance_scores=relevance_scores,
            constitutional_hash=self.constitutional_hash,
        )

    async def consolidate(
        self,
        strategy: ConsolidationStrategy = ConsolidationStrategy.TIME_BASED,
    ) -> MemoryConsolidationResult:
        """Consolidate memory to optimize storage.

        Args:
            strategy: Consolidation strategy to use

        Returns:
            MemoryConsolidationResult with stats
        """
        start_time = time.perf_counter()
        errors: list[str] = []

        # Dispatch to strategy-specific handler
        result = self._execute_consolidation_strategy(strategy)

        # Calculate memory freed (estimate)
        memory_freed = result["entries_deleted"] * 1024  # Rough estimate

        self._metrics["consolidations"] += 1

        return MemoryConsolidationResult(
            entries_processed=result["entries_processed"],
            entries_consolidated=result["entries_consolidated"],
            entries_archived=result["entries_archived"],
            entries_deleted=result["entries_deleted"],
            consolidation_time_ms=(time.perf_counter() - start_time) * 1000,
            memory_freed_bytes=memory_freed,
            new_semantic_entries=result["new_semantic"],
            errors=errors,
            constitutional_hash=self.constitutional_hash,
        )

    def _execute_consolidation_strategy(self, strategy: ConsolidationStrategy) -> JSONDict:
        """Execute the appropriate consolidation strategy.

        Returns:
            Dictionary with consolidation statistics
        """
        strategy_handlers = {
            ConsolidationStrategy.TIME_BASED: self._consolidate_time_based,
            ConsolidationStrategy.ACCESS_BASED: self._consolidate_access_based,
            ConsolidationStrategy.RELEVANCE_BASED: self._consolidate_relevance_based,
        }

        handler = strategy_handlers.get(strategy)
        if handler:
            return handler()

        # Default: no consolidation
        return {
            "entries_processed": 0,
            "entries_consolidated": 0,
            "entries_archived": 0,
            "entries_deleted": 0,
            "new_semantic": 0,
        }

    def _consolidate_time_based(self) -> JSONDict:
        """Consolidate entries based on age."""
        entries_processed = 0
        entries_archived = 0
        entries_deleted = 0

        cutoff = datetime.now(UTC) - timedelta(days=self.config.retention_days)

        for entry_id, entry in list(self._episodic_cache.items()):
            entries_processed += 1
            if entry.timestamp < cutoff:
                # Archive or delete based on access
                if entry.access_count > 5:
                    entries_archived += 1
                else:
                    del self._episodic_cache[entry_id]
                    entries_deleted += 1

        return {
            "entries_processed": entries_processed,
            "entries_consolidated": 0,
            "entries_archived": entries_archived,
            "entries_deleted": entries_deleted,
            "new_semantic": 0,
        }

    def _consolidate_access_based(self) -> JSONDict:
        """Consolidate entries based on access patterns."""
        entries_processed = 0
        entries_deleted = 0

        for entry_id, entry in list(self._episodic_cache.items()):
            entries_processed += 1
            if entry.access_count == 0:
                # Check age
                age = datetime.now(UTC) - entry.timestamp
                if age.days > 7:
                    del self._episodic_cache[entry_id]
                    entries_deleted += 1

        return {
            "entries_processed": entries_processed,
            "entries_consolidated": 0,
            "entries_archived": 0,
            "entries_deleted": entries_deleted,
            "new_semantic": 0,
        }

    def _consolidate_relevance_based(self) -> JSONDict:
        """Consolidate entries based on relevance decay."""
        entries_processed = 0
        entries_deleted = 0

        for entry_id, entry in list(self._episodic_cache.items()):
            entries_processed += 1
            entry.decay_relevance()
            if entry.relevance_decay < 0.2:
                del self._episodic_cache[entry_id]
                entries_deleted += 1

        return {
            "entries_processed": entries_processed,
            "entries_consolidated": 0,
            "entries_archived": 0,
            "entries_deleted": entries_deleted,
            "new_semantic": 0,
        }

    def _log_operation(
        self,
        operation_type: MemoryOperationType,
        tenant_id: str,
        session_id: str | None,
        entry_id: str | None,
        success: bool,
        latency_ms: float,
        details: JSONDict | None = None,
    ) -> None:
        """Log a memory operation for audit."""
        if not self.config.enable_audit_trail:
            return

        import uuid

        operation = MemoryOperation(
            operation_id=str(uuid.uuid4()),
            operation_type=operation_type,
            timestamp=datetime.now(UTC),
            tenant_id=tenant_id,
            session_id=session_id,
            entry_id=entry_id,
            success=success,
            latency_ms=latency_ms,
            details=details or {},
            constitutional_hash=self.constitutional_hash,
        )

        self._audit_log.append(operation)

        # Keep audit log bounded
        if len(self._audit_log) > 10000:
            self._audit_log = self._audit_log[-5000:]

    def get_metrics(self) -> JSONDict:
        """Get memory store metrics."""
        return {
            **self._metrics,
            "episodic_cache_size": len(self._episodic_cache),
            "semantic_cache_size": len(self._semantic_cache),
            "working_memory_size": len(self._working_memory),
            "audit_log_size": len(self._audit_log),
            "persistence_enabled": self.config.enable_persistence,
            "constitutional_hash": self.constitutional_hash,
        }

    async def shutdown(self) -> None:
        """Gracefully shutdown the memory store."""
        logger.info("Shutting down LongTermMemoryStore")

        if self._db_connection:
            self._db_connection.close()
            self._db_connection = None

        logger.info("LongTermMemoryStore shutdown complete")


__all__ = [
    "CONSTITUTIONAL_HASH",
    "ConsolidationStrategy",
    "LongTermMemoryConfig",
    "LongTermMemoryStore",
    "MemorySearchResult",
    "MemoryTier",
]
