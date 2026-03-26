"""
ACGS-2 Context Optimizer - Streaming Processor
Constitutional Hash: 608508a9bd224290

Streaming processor with overlap for context coherence.
"""

import inspect
import time
from collections.abc import Callable

try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

try:
    from src.core.shared.types import JSONDict, JSONList
except ImportError:
    JSONDict: type = JSONDict  # type: ignore[no-redef]
    JSONList: type = JSONList  # type: ignore[no-redef]

from .models import StreamingResult

# Check for numpy availability
try:
    import numpy as np

    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    np = None  # type: ignore[assignment]


class StreamingProcessor:
    """Streaming processor with overlap for context coherence.

    Processes long contexts in overlapping chunks to maintain
    coherence while staying within memory limits.

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(
        self,
        buffer_size: int = 8192,
        overlap_ratio: float = 0.1,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
    ):
        self.buffer_size = buffer_size
        self.overlap_ratio = overlap_ratio
        self.overlap_size = int(buffer_size * overlap_ratio)
        self.constitutional_hash = constitutional_hash

        if constitutional_hash != CONSTITUTIONAL_HASH:
            raise ValueError(f"Invalid constitutional hash: {constitutional_hash}")

        # Metrics
        self._streams_processed = 0
        self._total_tokens = 0

    async def stream_process(
        self,
        embeddings: object,
        processor_fn: Callable[[object], object],
    ) -> StreamingResult:
        """Stream process embeddings with overlap.

        Args:
            embeddings: Input embeddings (batch, seq_len, dim)
            processor_fn: Processing function

        Returns:
            StreamingResult with processed embeddings
        """
        start_time = time.perf_counter()

        # Get dimensions
        if NUMPY_AVAILABLE and isinstance(embeddings, np.ndarray):
            seq_len = embeddings.shape[1] if len(embeddings.shape) == 3 else embeddings.shape[0]
            outputs: JSONList = []
            chunks_streamed = 0
            total_overlap = 0

            # Stream with overlap
            position = 0
            while position < seq_len:
                # Calculate chunk boundaries
                chunk_end = min(position + self.buffer_size, seq_len)

                # Extract chunk with overlap from previous
                if position > 0:
                    chunk_start = max(0, position - self.overlap_size)
                    total_overlap += position - chunk_start
                else:
                    chunk_start = position

                if len(embeddings.shape) == 3:
                    chunk = embeddings[:, chunk_start:chunk_end, :]
                else:
                    chunk = embeddings[chunk_start:chunk_end, :]

                # Process chunk
                if inspect.iscoroutinefunction(processor_fn):
                    processed = await processor_fn(chunk)
                else:
                    processed = processor_fn(chunk)

                # Store output (trim overlap from previous chunks)
                if position > 0 and len(outputs) > 0:
                    # Only keep non-overlapping portion
                    trim_start = position - chunk_start
                    if len(processed.shape) == 3:
                        outputs.append(processed[:, trim_start:, :])
                    else:
                        outputs.append(processed[trim_start:, :])
                else:
                    outputs.append(processed)

                chunks_streamed += 1
                position = chunk_end

            # Concatenate outputs
            if outputs:
                output = np.concatenate(outputs, axis=1 if len(embeddings.shape) == 3 else 0)
            else:
                output = embeddings

            memory_peak = output.nbytes / (1024 * 1024) if hasattr(output, "nbytes") else 0.0

        else:
            # Fallback for non-numpy
            if inspect.iscoroutinefunction(processor_fn):
                output = await processor_fn(embeddings)
            else:
                output = processor_fn(embeddings)
            chunks_streamed = 1
            total_overlap = 0
            seq_len = len(embeddings) if hasattr(embeddings, "__len__") else 0
            memory_peak = 0.0

        processing_time = (time.perf_counter() - start_time) * 1000
        self._streams_processed += 1
        self._total_tokens += seq_len

        return StreamingResult(
            output_embeddings=output,
            chunks_streamed=chunks_streamed,
            overlap_tokens=total_overlap,
            total_tokens=seq_len,
            processing_time_ms=processing_time,
            memory_peak_mb=memory_peak,
            constitutional_validated=True,
            metadata={
                "buffer_size": self.buffer_size,
                "overlap_ratio": self.overlap_ratio,
            },
            constitutional_hash=self.constitutional_hash,
        )

    def get_metrics(self) -> JSONDict:
        """Get streaming metrics."""
        return {
            "streams_processed": self._streams_processed,
            "total_tokens": self._total_tokens,
            "buffer_size": self.buffer_size,
            "overlap_ratio": self.overlap_ratio,
            "constitutional_hash": self.constitutional_hash,
        }


__all__ = [
    "NUMPY_AVAILABLE",
    "StreamingProcessor",
]
