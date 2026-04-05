try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

"""
Long-Context Inference - Context window management and multi-turn reasoning.

Constitutional Hash: 608508a9bd224290
"""

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Protocol


class ChunkType(Enum):
    SYSTEM = "system"
    POLICY = "policy"
    PRINCIPLE = "principle"
    HISTORY = "history"
    USER_INPUT = "user_input"
    AGENT_OUTPUT = "agent_output"
    TOOL_RESULT = "tool_result"
    CONTEXT = "context"


class ChunkPriority(Enum):
    CRITICAL = 0
    HIGH = 1
    MEDIUM = 2
    LOW = 3
    EVICTABLE = 4


@dataclass
class ContextChunk:
    chunk_id: str
    chunk_type: ChunkType
    content: str
    token_count: int
    priority: ChunkPriority
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_accessed: datetime = field(default_factory=lambda: datetime.now(UTC))
    access_count: int = 0
    metadata: dict = field(default_factory=dict)
    embedding: list[float] | None = None
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "chunk_type": self.chunk_type.value,
            "content": self.content,
            "token_count": self.token_count,
            "priority": self.priority.value,
            "created_at": self.created_at.isoformat(),
            "last_accessed": self.last_accessed.isoformat(),
            "access_count": self.access_count,
            "metadata": self.metadata,
            "constitutional_hash": self.constitutional_hash,
        }

    def touch(self) -> None:
        self.last_accessed = datetime.now(UTC)
        self.access_count += 1


@dataclass
class ContextWindow:
    window_id: str
    max_tokens: int
    chunks: list[ContextChunk] = field(default_factory=list)
    total_tokens: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def add_chunk(self, chunk: ContextChunk) -> bool:
        if self.total_tokens + chunk.token_count > self.max_tokens:
            return False

        self.chunks.append(chunk)
        self.total_tokens += chunk.token_count
        return True

    def remove_chunk(self, chunk_id: str) -> bool:
        for i, chunk in enumerate(self.chunks):
            if chunk.chunk_id == chunk_id:
                self.total_tokens -= chunk.token_count
                self.chunks.pop(i)
                return True
        return False

    def get_chunk(self, chunk_id: str) -> ContextChunk | None:
        for chunk in self.chunks:
            if chunk.chunk_id == chunk_id:
                chunk.touch()
                return chunk
        return None

    def available_tokens(self) -> int:
        return self.max_tokens - self.total_tokens

    def to_text(self) -> str:
        return "\n\n".join(chunk.content for chunk in self.chunks)

    def get_chunks_by_type(self, chunk_type: ChunkType) -> list[ContextChunk]:
        return [c for c in self.chunks if c.chunk_type == chunk_type]


class TokenCounter(Protocol):
    def count(self, text: str) -> int: ...


class SimpleTokenCounter:
    def count(self, text: str) -> int:
        return int(len(text.split()) * 1.3)


class LongContextManager:
    def __init__(
        self,
        max_tokens: int = 128000,
        token_counter: TokenCounter | None = None,
        eviction_threshold: float = 0.9,
    ):
        self._max_tokens = max_tokens
        self._token_counter = token_counter or SimpleTokenCounter()
        self._eviction_threshold = eviction_threshold
        self._windows: dict[str, ContextWindow] = {}

    def create_window(self, window_id: str | None = None) -> ContextWindow:
        wid = window_id or hashlib.sha256(datetime.now(UTC).isoformat().encode()).hexdigest()[:16]

        window = ContextWindow(window_id=wid, max_tokens=self._max_tokens)
        self._windows[wid] = window
        return window

    def get_window(self, window_id: str) -> ContextWindow | None:
        return self._windows.get(window_id)

    def add_to_window(
        self,
        window_id: str,
        content: str,
        chunk_type: ChunkType,
        priority: ChunkPriority = ChunkPriority.MEDIUM,
        metadata: dict | None = None,
    ) -> ContextChunk | None:
        window = self._windows.get(window_id)
        if not window:
            return None

        token_count = self._token_counter.count(content)
        chunk_id = hashlib.sha256(
            f"{window_id}:{datetime.now(UTC).isoformat()}:{content[:100]}".encode()
        ).hexdigest()[:16]

        chunk = ContextChunk(
            chunk_id=chunk_id,
            chunk_type=chunk_type,
            content=content,
            token_count=token_count,
            priority=priority,
            metadata=metadata or {},
        )

        if window.total_tokens + token_count > window.max_tokens * self._eviction_threshold:
            self._evict_chunks(window, token_count)

        if window.add_chunk(chunk):
            return chunk
        return None

    def _evict_chunks(self, window: ContextWindow, needed_tokens: int) -> int:
        evicted = 0
        evictable = [c for c in window.chunks if c.priority.value >= ChunkPriority.LOW.value]

        evictable.sort(key=lambda c: (c.priority.value, -c.access_count, c.last_accessed))

        for chunk in evictable:
            if window.available_tokens() >= needed_tokens:
                break

            window.remove_chunk(chunk.chunk_id)
            evicted += chunk.token_count

        return evicted

    def compact_window(self, window_id: str) -> int:
        window = self._windows.get(window_id)
        if not window:
            return 0

        history_chunks = window.get_chunks_by_type(ChunkType.HISTORY)
        if len(history_chunks) <= 5:
            return 0

        to_summarize = history_chunks[:-3]
        summary_content = self._summarize_chunks(to_summarize)

        removed_tokens = 0
        for chunk in to_summarize:
            window.remove_chunk(chunk.chunk_id)
            removed_tokens += chunk.token_count

        self.add_to_window(
            window_id,
            summary_content,
            ChunkType.HISTORY,
            ChunkPriority.MEDIUM,
            {"summarized_from": [c.chunk_id for c in to_summarize]},
        )

        return removed_tokens

    def _summarize_chunks(self, chunks: list[ContextChunk]) -> str:
        summaries = []
        for chunk in chunks:
            content = chunk.content
            if len(content) > 200:
                content = content[:200] + "..."
            summaries.append(f"[{chunk.chunk_type.value}] {content}")

        return "Summary of previous context:\n" + "\n".join(summaries)


@dataclass
class ContextDelta:
    delta_id: str
    operation: str
    chunk_id: str | None
    content: str | None
    metadata: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


class IncrementalContextUpdater:
    def __init__(self, context_manager: LongContextManager):
        self._context_manager = context_manager
        self._deltas: dict[str, list[ContextDelta]] = {}

    def apply_delta(
        self,
        window_id: str,
        operation: str,
        content: str | None = None,
        chunk_type: ChunkType = ChunkType.CONTEXT,
        chunk_id: str | None = None,
    ) -> ContextDelta:
        delta_id = hashlib.sha256(
            f"{window_id}:{datetime.now(UTC).isoformat()}".encode()
        ).hexdigest()[:16]

        delta = ContextDelta(
            delta_id=delta_id,
            operation=operation,
            chunk_id=chunk_id,
            content=content,
        )

        if operation == "add" and content:
            chunk = self._context_manager.add_to_window(window_id, content, chunk_type)
            if chunk:
                delta.chunk_id = chunk.chunk_id

        elif operation == "remove" and chunk_id:
            window = self._context_manager.get_window(window_id)
            if window:
                window.remove_chunk(chunk_id)

        elif operation == "update" and chunk_id and content:
            window = self._context_manager.get_window(window_id)
            if window:
                old_chunk = window.get_chunk(chunk_id)
                if old_chunk:
                    window.remove_chunk(chunk_id)
                    new_chunk = self._context_manager.add_to_window(
                        window_id, content, old_chunk.chunk_type, old_chunk.priority
                    )
                    if new_chunk:
                        delta.chunk_id = new_chunk.chunk_id

        if window_id not in self._deltas:
            self._deltas[window_id] = []
        self._deltas[window_id].append(delta)

        return delta

    def get_deltas(self, window_id: str, since: datetime | None = None) -> list[ContextDelta]:
        deltas = self._deltas.get(window_id, [])
        if since:
            deltas = [d for d in deltas if d.timestamp > since]
        return deltas

    def replay_deltas(self, window_id: str, deltas: list[ContextDelta]) -> list[ContextDelta]:
        results = []
        for delta in deltas:
            result = self.apply_delta(
                window_id,
                delta.operation,
                delta.content,
                chunk_id=delta.chunk_id,
            )
            results.append(result)
        return results


@dataclass
class ReasoningStep:
    step_id: str
    step_type: str
    input_context: str
    output: str
    confidence: float
    token_usage: int
    metadata: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class ReasoningChain:
    chain_id: str
    window_id: str
    steps: list[ReasoningStep] = field(default_factory=list)
    final_output: str | None = None
    total_tokens: int = 0
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def add_step(self, step: ReasoningStep) -> None:
        self.steps.append(step)
        self.total_tokens += step.token_usage


class InferenceProvider(Protocol):
    def infer(self, context: str, prompt: str) -> tuple[str, int]: ...


class MultiTurnReasoner:
    def __init__(
        self,
        context_manager: LongContextManager,
        inference_provider: InferenceProvider | None = None,
    ):
        self._context_manager = context_manager
        self._inference_provider = inference_provider
        self._chains: dict[str, ReasoningChain] = {}

    def start_chain(self, window_id: str) -> ReasoningChain:
        chain_id = hashlib.sha256(
            f"{window_id}:{datetime.now(UTC).isoformat()}".encode()
        ).hexdigest()[:16]

        chain = ReasoningChain(chain_id=chain_id, window_id=window_id)
        self._chains[chain_id] = chain
        return chain

    def reason_step(
        self,
        chain_id: str,
        prompt: str,
        step_type: str = "inference",
    ) -> ReasoningStep | None:
        chain = self._chains.get(chain_id)
        if not chain:
            return None

        window = self._context_manager.get_window(chain.window_id)
        if not window:
            return None

        context = window.to_text()

        if self._inference_provider:
            output, tokens = self._inference_provider.infer(context, prompt)
        else:
            output = f"[Mock inference for: {prompt[:50]}...]"
            tokens = len(output.split())

        step_id = hashlib.sha256(
            f"{chain_id}:{len(chain.steps)}:{datetime.now(UTC).isoformat()}".encode()
        ).hexdigest()[:16]

        step = ReasoningStep(
            step_id=step_id,
            step_type=step_type,
            input_context=context[:500] + "..." if len(context) > 500 else context,
            output=output,
            confidence=0.85,
            token_usage=tokens,
        )

        chain.add_step(step)

        self._context_manager.add_to_window(
            chain.window_id,
            f"Reasoning ({step_type}): {output}",
            ChunkType.AGENT_OUTPUT,
            ChunkPriority.MEDIUM,
        )

        return step

    def finalize_chain(self, chain_id: str) -> ReasoningChain | None:
        chain = self._chains.get(chain_id)
        if not chain or not chain.steps:
            return None

        chain.final_output = chain.steps[-1].output
        return chain

    def get_chain(self, chain_id: str) -> ReasoningChain | None:
        return self._chains.get(chain_id)

    def deliberate(
        self,
        chain_id: str,
        question: str,
        max_steps: int = 3,
        confidence_threshold: float = 0.9,
    ) -> ReasoningChain | None:
        chain = self._chains.get(chain_id)
        if not chain:
            return None

        step = self.reason_step(chain_id, f"Initial analysis: {question}", "analyze")
        if not step:
            return None

        for _ in range(max_steps - 1):
            if step and step.confidence >= confidence_threshold:
                break

            critique_prompt = (
                f"Critique the previous response: {step.output[:200] if step else ''}..."
            )
            step = self.reason_step(chain_id, critique_prompt, "critique")

            if step:
                refine_prompt = f"Refine based on critique: {step.output[:200]}..."
                step = self.reason_step(chain_id, refine_prompt, "refine")

        return self.finalize_chain(chain_id)
