"""
ACGS-2 Context & Memory - Hybrid Context Manager
Constitutional Hash: 608508a9bd224290

Manages the hybrid Mamba-2 SSM + Attention architecture for optimal
context processing. Combines O(n) SSM processing with attention for
critical constitutional reasoning sections.

Key Features:
- Automatic routing between SSM and attention based on content
- Constitutional context always processed with attention
- Smart batching and caching for performance
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

from enhanced_agent_bus.bus_types import JSONDict
from enhanced_agent_bus.observability.structured_logging import get_logger

from .mamba_processor import NUMPY_AVAILABLE, TORCH_AVAILABLE, MambaProcessor, MambaProcessorConfig
from .models import (
    ContextType,
    ContextWindow,
)

logger = get_logger(__name__)
# Import attention components if torch available
if TORCH_AVAILABLE:
    import torch
    import torch.nn.functional as F


class ProcessingMode(str, Enum):
    """Processing mode for context."""

    SSM_ONLY = "ssm_only"  # Pure Mamba-2 SSM processing
    ATTENTION_ONLY = "attention_only"  # Pure attention processing
    HYBRID = "hybrid"  # Combined SSM + Attention
    AUTO = "auto"  # Automatic selection based on content


@dataclass
class HybridContextConfig:
    """Configuration for hybrid context manager.

    Constitutional Hash: 608508a9bd224290
    """

    # Mamba-2 SSM settings
    mamba_d_model: int = 256
    mamba_d_state: int = 128
    mamba_num_layers: int = 6
    mamba_expand_factor: int = 2

    # Attention settings
    attention_num_heads: int = 8
    attention_dropout: float = 0.1
    attention_max_seq_len: int = 8192

    # Hybrid routing settings
    ssm_threshold_tokens: int = 4096  # Use SSM for sequences longer than this
    critical_attention_boost: float = 0.3  # Boost for critical content in attention
    constitutional_always_attention: bool = True  # Always use attention for constitutional

    # Performance settings
    max_context_length: int = 4_000_000
    chunk_size: int = 8192
    enable_caching: bool = True
    cache_ttl_seconds: int = 300

    # Processing mode
    default_mode: ProcessingMode = ProcessingMode.AUTO

    # Constitutional
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def __post_init__(self) -> None:
        if self.constitutional_hash != CONSTITUTIONAL_HASH:
            raise ValueError(f"Invalid constitutional hash: {self.constitutional_hash}")


@dataclass
class HybridProcessingResult:
    """Result of hybrid context processing.

    Constitutional Hash: 608508a9bd224290
    """

    output_embeddings: object
    processing_mode: ProcessingMode
    ssm_processed_tokens: int = 0
    attention_processed_tokens: int = 0
    total_processing_time_ms: float = 0.0
    ssm_time_ms: float = 0.0
    attention_time_ms: float = 0.0
    constitutional_validated: bool = True
    critical_sections_count: int = 0
    cache_hit: bool = False
    metadata: JSONDict = field(default_factory=dict)
    constitutional_hash: str = CONSTITUTIONAL_HASH


class SharedAttentionProcessor:
    """Shared attention layer for critical reasoning.

    Processes constitutional and high-priority content with full attention.

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(
        self,
        d_model: int = 256,
        num_heads: int = 8,
        dropout: float = 0.1,
        max_seq_len: int = 8192,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
    ):
        self.d_model = d_model
        self.num_heads = num_heads
        self.head_dim = d_model // num_heads
        self.dropout = dropout
        self.max_seq_len = max_seq_len
        self.constitutional_hash = constitutional_hash

        if constitutional_hash != CONSTITUTIONAL_HASH:
            raise ValueError(f"Invalid constitutional hash: {constitutional_hash}")

        # Initialize attention weights if torch available
        if TORCH_AVAILABLE:
            self.q_proj = torch.randn(d_model, d_model) * 0.02
            self.k_proj = torch.randn(d_model, d_model) * 0.02
            self.v_proj = torch.randn(d_model, d_model) * 0.02
            self.o_proj = torch.randn(d_model, d_model) * 0.02

    def forward(
        self,
        x: object,
        attention_mask: object | None = None,
        critical_positions: list[int] | None = None,
    ) -> object:
        """Forward pass through attention layer.

        Args:
            x: Input tensor (batch, seq_len, d_model)
            attention_mask: Optional attention mask
            critical_positions: Positions to boost attention

        Returns:
            Output tensor with attention applied
        """
        if TORCH_AVAILABLE and isinstance(x, torch.Tensor):
            return self._forward_torch(x, attention_mask, critical_positions)
        elif NUMPY_AVAILABLE:
            import numpy as np

            if isinstance(x, np.ndarray):
                return self._forward_numpy(x, attention_mask, critical_positions)
        return x

    def _forward_torch(
        self,
        x: "torch.Tensor",
        mask: "torch.Tensor" | None,
        critical_positions: list[int] | None,
    ) -> "torch.Tensor":
        """PyTorch attention forward pass."""
        batch, seq_len, _ = x.shape

        # Truncate if too long
        if seq_len > self.max_seq_len:
            x = x[:, : self.max_seq_len, :]
            seq_len = self.max_seq_len

        # Project to Q, K, V
        q = torch.matmul(x, self.q_proj.T)
        k = torch.matmul(x, self.k_proj.T)
        v = torch.matmul(x, self.v_proj.T)

        # Reshape for multi-head attention
        q = q.view(batch, seq_len, self.num_heads, self.head_dim).transpose(1, 2)
        k = k.view(batch, seq_len, self.num_heads, self.head_dim).transpose(1, 2)
        v = v.view(batch, seq_len, self.num_heads, self.head_dim).transpose(1, 2)

        # Compute attention scores
        scale = 1.0 / (self.head_dim**0.5)
        attn_weights = torch.matmul(q, k.transpose(-2, -1)) * scale

        # Boost critical positions if specified
        if critical_positions:
            for pos in critical_positions:
                if pos < seq_len:
                    attn_weights[:, :, :, pos] += 0.3  # Boost

        # Apply mask if provided
        if mask is not None:
            attn_weights = attn_weights.masked_fill(mask == 0, float("-inf"))

        # Softmax and apply to values
        attn_weights = F.softmax(attn_weights, dim=-1)
        attn_output = torch.matmul(attn_weights, v)

        # Reshape and project output
        attn_output = attn_output.transpose(1, 2).contiguous().view(batch, seq_len, self.d_model)
        output = torch.matmul(attn_output, self.o_proj.T)

        return output

    def _forward_numpy(
        self,
        x: object,
        mask: object | None,
        critical_positions: list[int] | None,
    ) -> object:
        """NumPy attention forward pass (simplified)."""
        import numpy as np

        # Simple weighted average as attention approximation
        if len(x.shape) == 3:
            _batch, seq_len, d_model = x.shape
        else:
            seq_len, d_model = x.shape
            x = x.reshape(1, seq_len, d_model)

        # Create simple attention weights
        weights = np.ones((seq_len, seq_len)) / seq_len

        # Boost critical positions
        if critical_positions:
            for pos in critical_positions:
                if pos < seq_len:
                    weights[:, pos] += 0.3

        # Normalize
        weights = weights / weights.sum(axis=-1, keepdims=True)

        # Apply attention
        output = np.matmul(weights, x.squeeze(0)).reshape(1, seq_len, d_model)

        return output


class HybridContextManager:
    """Manages hybrid Mamba-2 SSM + Attention context processing.

    Automatically routes content to the appropriate processing mode
    based on content type, length, and constitutional requirements.

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(
        self,
        config: HybridContextConfig | None = None,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
    ):
        self.config = config or HybridContextConfig()
        self.constitutional_hash = constitutional_hash

        if constitutional_hash != CONSTITUTIONAL_HASH:
            raise ValueError(f"Invalid constitutional hash: {constitutional_hash}")

        # Initialize Mamba processor
        mamba_config = MambaProcessorConfig(
            d_model=self.config.mamba_d_model,
            d_state=self.config.mamba_d_state,
            num_layers=self.config.mamba_num_layers,
            expand_factor=self.config.mamba_expand_factor,
            max_context_length=self.config.max_context_length,
            chunk_size=self.config.chunk_size,
            constitutional_hash=constitutional_hash,
        )
        self.mamba_processor = MambaProcessor(
            config=mamba_config,
            constitutional_hash=constitutional_hash,
        )

        # Initialize attention processor
        self.attention_processor = SharedAttentionProcessor(
            d_model=self.config.mamba_d_model,
            num_heads=self.config.attention_num_heads,
            dropout=self.config.attention_dropout,
            max_seq_len=self.config.attention_max_seq_len,
            constitutional_hash=constitutional_hash,
        )

        # Processing cache
        self._cache: dict[str, tuple[object, datetime]] = {}

        # Metrics
        self._metrics = {
            "ssm_calls": 0,
            "attention_calls": 0,
            "hybrid_calls": 0,
            "total_tokens": 0,
            "cache_hits": 0,
            "cache_misses": 0,
        }

        logger.info(f"Initialized HybridContextManager (mode={self.config.default_mode.value})")

    async def process_context_window(
        self,
        window: ContextWindow,
        mode: ProcessingMode | None = None,
    ) -> HybridProcessingResult:
        """Process a context window with hybrid architecture.

        Args:
            window: ContextWindow containing chunks to process
            mode: Processing mode (defaults to config default)

        Returns:
            HybridProcessingResult with processed embeddings
        """
        start_time = time.perf_counter()
        mode = mode or self.config.default_mode

        # Check cache
        cache_key = f"{window.window_id}:{mode.value}"
        if self.config.enable_caching and cache_key in self._cache:
            cached, cached_time = self._cache[cache_key]
            age = (datetime.now(UTC) - cached_time).total_seconds()
            if age < self.config.cache_ttl_seconds:
                self._metrics["cache_hits"] += 1
                return HybridProcessingResult(
                    output_embeddings=cached,
                    processing_mode=mode,
                    cache_hit=True,
                    constitutional_hash=self.constitutional_hash,
                )
        self._metrics["cache_misses"] += 1

        # Determine actual processing mode
        if mode == ProcessingMode.AUTO:
            mode = self._auto_select_mode(window)

        # Process based on mode
        if mode == ProcessingMode.SSM_ONLY:
            result = await self._process_ssm_only(window)
        elif mode == ProcessingMode.ATTENTION_ONLY:
            result = await self._process_attention_only(window)
        else:  # HYBRID
            result = await self._process_hybrid(window)

        # Update cache
        if self.config.enable_caching:
            self._cache[cache_key] = (result.output_embeddings, datetime.now(UTC))

        # Update metrics
        result.total_processing_time_ms = (time.perf_counter() - start_time) * 1000
        self._metrics["total_tokens"] += window.total_tokens

        return result

    def _auto_select_mode(self, window: ContextWindow) -> ProcessingMode:
        """Automatically select processing mode based on window content."""
        # Check for constitutional content
        constitutional_chunks = window.get_by_type(ContextType.CONSTITUTIONAL)
        if constitutional_chunks and self.config.constitutional_always_attention:
            return ProcessingMode.HYBRID

        # Check for critical chunks
        critical_chunks = window.get_critical_chunks()
        if critical_chunks:
            return ProcessingMode.HYBRID

        # Check length threshold
        if window.total_tokens > self.config.ssm_threshold_tokens:
            return ProcessingMode.SSM_ONLY

        # Default to attention for short sequences
        if window.total_tokens <= self.config.attention_max_seq_len:
            return ProcessingMode.ATTENTION_ONLY

        return ProcessingMode.HYBRID

    async def _process_ssm_only(self, window: ContextWindow) -> HybridProcessingResult:
        """Process entirely with Mamba-2 SSM."""
        self._metrics["ssm_calls"] += 1
        time.perf_counter()

        result = self.mamba_processor.process_context_chunks(window.chunks)

        return HybridProcessingResult(
            output_embeddings=result.output_embeddings,
            processing_mode=ProcessingMode.SSM_ONLY,
            ssm_processed_tokens=result.tokens_processed,
            attention_processed_tokens=0,
            ssm_time_ms=result.processing_time_ms,
            attention_time_ms=0,
            constitutional_validated=True,
            critical_sections_count=len(window.get_critical_chunks()),
            metadata=result.metadata,
            constitutional_hash=self.constitutional_hash,
        )

    async def _process_attention_only(self, window: ContextWindow) -> HybridProcessingResult:
        """Process entirely with attention."""
        self._metrics["attention_calls"] += 1
        start_time = time.perf_counter()

        # Create embeddings
        combined_text = window.to_text()
        embeddings = self.mamba_processor._simple_embed(combined_text)

        # Get critical positions
        critical_positions: list[int] = []
        position = 0
        for chunk in window.chunks:
            if chunk.is_critical:
                critical_positions.extend(range(position, position + chunk.token_count))
            position += chunk.token_count

        # Process with attention
        output = self.attention_processor.forward(
            embeddings,
            critical_positions=critical_positions,
        )

        attention_time = (time.perf_counter() - start_time) * 1000

        return HybridProcessingResult(
            output_embeddings=output,
            processing_mode=ProcessingMode.ATTENTION_ONLY,
            ssm_processed_tokens=0,
            attention_processed_tokens=window.total_tokens,
            ssm_time_ms=0,
            attention_time_ms=attention_time,
            constitutional_validated=True,
            critical_sections_count=len(window.get_critical_chunks()),
            metadata={"critical_positions": len(critical_positions)},
            constitutional_hash=self.constitutional_hash,
        )

    async def _process_hybrid(self, window: ContextWindow) -> HybridProcessingResult:
        """Process with hybrid SSM + Attention architecture."""
        self._metrics["hybrid_calls"] += 1

        # Separate chunks by priority
        critical_chunks = []
        regular_chunks = []

        for chunk in window.chunks:
            if chunk.is_critical or chunk.context_type == ContextType.CONSTITUTIONAL:
                critical_chunks.append(chunk)
            else:
                regular_chunks.append(chunk)

        # Process regular chunks with SSM
        ssm_start = time.perf_counter()
        ssm_tokens = 0
        ssm_output = None

        if regular_chunks:
            ssm_result = self.mamba_processor.process_context_chunks(regular_chunks)
            ssm_output = ssm_result.output_embeddings
            ssm_tokens = ssm_result.tokens_processed

        ssm_time = (time.perf_counter() - ssm_start) * 1000

        # Process critical chunks with attention
        attn_start = time.perf_counter()
        attn_tokens = 0
        attn_output = None

        if critical_chunks:
            critical_text = "\n".join(c.content for c in critical_chunks)
            critical_embeddings = self.mamba_processor._simple_embed(critical_text)
            attn_output = self.attention_processor.forward(critical_embeddings)
            attn_tokens = sum(c.token_count for c in critical_chunks)

        attn_time = (time.perf_counter() - attn_start) * 1000

        # Combine outputs
        if ssm_output is not None and attn_output is not None:
            if TORCH_AVAILABLE:
                import torch

                combined_output = torch.cat([attn_output, ssm_output], dim=1)
            elif NUMPY_AVAILABLE:
                import numpy as np

                combined_output = np.concatenate([attn_output, ssm_output], axis=1)
            else:
                combined_output = attn_output
        elif attn_output is not None:
            combined_output = attn_output
        else:
            combined_output = ssm_output

        return HybridProcessingResult(
            output_embeddings=combined_output,
            processing_mode=ProcessingMode.HYBRID,
            ssm_processed_tokens=ssm_tokens,
            attention_processed_tokens=attn_tokens,
            ssm_time_ms=ssm_time,
            attention_time_ms=attn_time,
            constitutional_validated=True,
            critical_sections_count=len(critical_chunks),
            metadata={
                "regular_chunks": len(regular_chunks),
                "critical_chunks": len(critical_chunks),
            },
            constitutional_hash=self.constitutional_hash,
        )

    def clear_cache(self) -> int:
        """Clear the processing cache."""
        count = len(self._cache)
        self._cache.clear()
        return count

    def get_metrics(self) -> JSONDict:
        """Get processing metrics."""
        return {
            **self._metrics,
            "mamba_metrics": self.mamba_processor.get_metrics(),
            "cache_size": len(self._cache),
            "constitutional_hash": self.constitutional_hash,
        }

    def reset_state(self) -> None:
        """Reset all processor states."""
        self.mamba_processor.reset_state()
        self._cache.clear()


__all__ = [
    "CONSTITUTIONAL_HASH",
    "HybridContextConfig",
    "HybridContextManager",
    "HybridProcessingResult",
    "ProcessingMode",
    "SharedAttentionProcessor",
]
