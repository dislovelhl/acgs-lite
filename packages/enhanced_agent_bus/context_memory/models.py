"""
ACGS-2 Context & Memory - Data Models
Constitutional Hash: 608508a9bd224290

Pydantic models and dataclasses for the Context & Memory layer.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from enum import Enum
from typing import TypeAlias

from pydantic import BaseModel, Field, field_validator

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

from enhanced_agent_bus.bus_types import JSONDict, JSONValue


class ContextType(str, Enum):
    """Types of context in the system."""

    CONSTITUTIONAL = "constitutional"  # Core constitutional principles
    POLICY = "policy"  # Policy rules and constraints
    GOVERNANCE = "governance"  # Governance decisions and history
    SEMANTIC = "semantic"  # Semantic knowledge
    EPISODIC = "episodic"  # Episode/session history
    WORKING = "working"  # Active working memory
    SYSTEM = "system"  # System prompts and instructions


class ContextPriority(int, Enum):
    """Priority levels for context injection."""

    CRITICAL = 4  # Constitutional context - always present
    HIGH = 3  # Policy context - present when relevant
    MEDIUM = 2  # Governance context
    LOW = 1  # General context
    BACKGROUND = 0  # Optional background context


class MemoryOperationType(str, Enum):
    """Types of memory operations for audit."""

    STORE = "store"
    RETRIEVE = "retrieve"
    UPDATE = "update"
    DELETE = "delete"
    CONSOLIDATE = "consolidate"
    SEARCH = "search"
    CACHE_HIT = "cache_hit"
    CACHE_MISS = "cache_miss"


class MambaConfig(BaseModel):
    """Configuration for Mamba-2 processor.

    Constitutional Hash: 608508a9bd224290
    """

    d_model: int = Field(default=256, ge=64, le=4096, description="Model dimension")
    d_state: int = Field(default=128, ge=32, le=512, description="State dimension")
    num_layers: int = Field(default=6, ge=1, le=24, description="Number of Mamba SSM layers")
    expand_factor: int = Field(default=2, ge=1, le=4, description="Expansion factor")
    max_context_length: int = Field(
        default=4_000_000, ge=1024, le=16_000_000, description="Maximum context length in tokens"
    )
    precision: str = Field(
        default="float32", description="Computation precision (float32, float16, bfloat16)"
    )
    enable_quantization: bool = Field(
        default=False, description="Enable dynamic quantization for memory efficiency"
    )
    constitutional_hash: str = Field(
        default=CONSTITUTIONAL_HASH, description="Constitutional hash for compliance"
    )

    @field_validator("precision")
    @classmethod
    def validate_precision(cls, v: str) -> str:
        valid = {"float32", "float16", "bfloat16"}
        if v not in valid:
            raise ValueError(f"Precision must be one of {valid}")
        return v

    @field_validator("constitutional_hash")
    @classmethod
    def validate_hash(cls, v: str) -> str:
        if v != CONSTITUTIONAL_HASH:
            raise ValueError(f"Invalid constitutional hash: {v}")
        return v

    model_config = {"from_attributes": True}


class JRTConfig(BaseModel):
    """Configuration for Just-in-Time Retrieval.

    Constitutional Hash: 608508a9bd224290
    """

    repetition_factor: int = Field(
        default=3, ge=1, le=10, description="Times to repeat critical sections for better recall"
    )
    context_window_size: int = Field(
        default=8192, ge=1024, le=131072, description="Size of context window for retrieval"
    )
    relevance_threshold: float = Field(
        default=0.7, ge=0.0, le=1.0, description="Minimum relevance score for context inclusion"
    )
    max_critical_sections: int = Field(
        default=10, ge=1, le=100, description="Maximum number of critical sections to mark"
    )
    constitutional_priority_boost: float = Field(
        default=0.3, ge=0.0, le=1.0, description="Priority boost for constitutional context"
    )
    enable_smart_windowing: bool = Field(
        default=True, description="Enable relevance-based smart windowing"
    )
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH)

    model_config = {"from_attributes": True}


@dataclass
class ContextChunk:
    """A chunk of context with metadata.

    Constitutional Hash: 608508a9bd224290
    """

    content: str
    context_type: ContextType
    priority: ContextPriority
    token_count: int
    relevance_score: float = 1.0
    is_critical: bool = False
    chunk_id: str = ""
    source_id: str | None = None
    embedding: list[float] | None = None
    metadata: JSONDict = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def __post_init__(self) -> None:
        if not self.chunk_id:
            import uuid

            self.chunk_id = str(uuid.uuid4())


@dataclass
class ContextWindow:
    """A context window containing multiple chunks.

    Constitutional Hash: 608508a9bd224290
    """

    chunks: list[ContextChunk] = field(default_factory=list)
    total_tokens: int = 0
    max_tokens: int = 4_000_000
    window_id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def __post_init__(self) -> None:
        if not self.window_id:
            import uuid

            self.window_id = str(uuid.uuid4())
        self._recalculate_tokens()

    def _recalculate_tokens(self) -> None:
        """Recalculate total token count."""
        self.total_tokens = sum(chunk.token_count for chunk in self.chunks)

    def add_chunk(self, chunk: ContextChunk) -> bool:
        """Add a chunk if it fits within the window."""
        if self.total_tokens + chunk.token_count > self.max_tokens:
            return False
        self.chunks.append(chunk)
        self.total_tokens += chunk.token_count
        return True

    def get_by_type(self, context_type: ContextType) -> list[ContextChunk]:
        """Get all chunks of a specific type."""
        return [c for c in self.chunks if c.context_type == context_type]

    def get_critical_chunks(self) -> list[ContextChunk]:
        """Get all critical chunks."""
        return [c for c in self.chunks if c.is_critical]

    def to_text(self) -> str:
        """Combine all chunks into text."""
        sorted_chunks = sorted(
            self.chunks, key=lambda c: (c.priority.value, c.relevance_score), reverse=True
        )
        return "\n\n".join(c.content for c in sorted_chunks)


@dataclass
class ContextRetrievalResult:
    """Result of context retrieval operation.

    Constitutional Hash: 608508a9bd224290
    """

    window: ContextWindow
    retrieval_time_ms: float
    relevance_scores: dict[str, float] = field(default_factory=dict)
    cache_hit: bool = False
    source_count: int = 0
    constitutional_validated: bool = True
    warnings: list[str] = field(default_factory=list)
    metadata: JSONDict = field(default_factory=dict)
    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass
class EpisodicMemoryEntry:
    """Entry in episodic memory (interaction history).

    Constitutional Hash: 608508a9bd224290
    """

    entry_id: str
    session_id: str
    tenant_id: str
    timestamp: datetime
    event_type: str
    content: str
    outcome: str | None = None
    context: JSONDict = field(default_factory=dict)
    relevance_decay: float = 1.0
    access_count: int = 0
    last_accessed: datetime | None = None
    embedding: list[float] | None = None
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def decay_relevance(self, decay_rate: float = 0.01) -> None:
        """Apply time-based relevance decay."""
        age_hours = (datetime.now(UTC) - self.timestamp).total_seconds() / 3600
        self.relevance_decay = max(0.1, 1.0 - (decay_rate * age_hours))

    def record_access(self) -> None:
        """Record an access to this memory."""
        self.access_count += 1
        self.last_accessed = datetime.now(UTC)


@dataclass
class SemanticMemoryEntry:
    """Entry in semantic memory (factual knowledge).

    Constitutional Hash: 608508a9bd224290
    """

    entry_id: str
    knowledge_type: str
    content: str
    confidence: float
    source: str
    created_at: datetime
    updated_at: datetime
    embedding: list[float] | None = None
    related_entries: list[str] = field(default_factory=list)
    access_count: int = 0
    validation_status: str = "pending"
    metadata: JSONDict = field(default_factory=dict)
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def update_confidence(self, feedback: float) -> None:
        """Update confidence based on feedback."""
        # Exponential moving average
        alpha = 0.3
        self.confidence = alpha * feedback + (1 - alpha) * self.confidence
        self.updated_at = datetime.now(UTC)


@dataclass
class MemoryQuery:
    """Query for memory retrieval.

    Constitutional Hash: 608508a9bd224290
    """

    query_text: str
    query_type: str = "semantic"  # semantic, episodic, hybrid
    tenant_id: str | None = None
    session_id: str | None = None
    context_types: list[ContextType] = field(default_factory=list)
    min_relevance: float = 0.5
    max_results: int = 10
    time_range_hours: int | None = None
    include_embeddings: bool = False
    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass
class MemoryConsolidationResult:
    """Result of memory consolidation operation.

    Constitutional Hash: 608508a9bd224290
    """

    entries_processed: int
    entries_consolidated: int
    entries_archived: int
    entries_deleted: int
    consolidation_time_ms: float
    memory_freed_bytes: int
    new_semantic_entries: int
    errors: list[str] = field(default_factory=list)
    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass
class MemoryOperation:
    """Audit record for a memory operation.

    Constitutional Hash: 608508a9bd224290
    """

    operation_id: str
    operation_type: MemoryOperationType
    timestamp: datetime
    tenant_id: str
    session_id: str | None
    entry_id: str | None
    success: bool
    latency_ms: float
    details: JSONDict = field(default_factory=dict)
    constitutional_hash: str = CONSTITUTIONAL_HASH


__all__ = [
    "CONSTITUTIONAL_HASH",
    "ContextChunk",
    "ContextPriority",
    "ContextRetrievalResult",
    "ContextType",
    "ContextWindow",
    "EpisodicMemoryEntry",
    "JRTConfig",
    "MambaConfig",
    "MemoryConsolidationResult",
    "MemoryOperation",
    "MemoryOperationType",
    "MemoryQuery",
    "SemanticMemoryEntry",
]
