"""
ACGS-2 Context Optimizer - Parallel Batch Processor
Constitutional Hash: 608508a9bd224290

Parallel batch processor for context chunks with concurrency control.
"""

import asyncio
import inspect
import time
from collections.abc import Callable

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

try:
    from enhanced_agent_bus._compat.types import JSONDict, JSONList
except ImportError:
    JSONDict: type = JSONDict  # type: ignore[no-redef]
    JSONList: type = JSONList  # type: ignore[no-redef]

from enhanced_agent_bus.context_memory.models import ContextChunk

from .models import BatchProcessingResult


class ParallelBatchProcessor:
    """Parallel batch processor for context chunks.

    Processes multiple chunks concurrently for improved throughput.

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(
        self,
        max_parallel: int = 32,
        batch_size: int = 64,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
    ):
        self.max_parallel = max_parallel
        self.batch_size = batch_size
        self.constitutional_hash = constitutional_hash

        if constitutional_hash != CONSTITUTIONAL_HASH:
            raise ValueError(f"Invalid constitutional hash: {constitutional_hash}")

        # Semaphore for concurrency control
        self._semaphore = asyncio.Semaphore(max_parallel)

        # Metrics
        self._batches_processed = 0
        self._total_chunks = 0
        self._total_time_ms = 0.0

    async def process_batch(
        self,
        chunks: list[ContextChunk],
        processor_fn: Callable[[ContextChunk], object],
        fail_fast: bool = False,
    ) -> BatchProcessingResult:
        """Process chunks in parallel batches.

        Args:
            chunks: Chunks to process
            processor_fn: Function to apply to each chunk
            fail_fast: Stop on first error

        Returns:
            BatchProcessingResult with outputs
        """
        start_time = time.perf_counter()
        outputs: JSONList = []
        errors: list[str] = []
        successful = 0
        failed = 0

        # Process in batches
        for i in range(0, len(chunks), self.batch_size):
            batch = chunks[i : i + self.batch_size]

            # Create tasks for parallel processing
            tasks = [self._process_chunk(chunk, processor_fn) for chunk in batch]

            # Gather results
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for j, result in enumerate(results):
                if isinstance(result, Exception):
                    failed += 1
                    errors.append(f"Chunk {i + j}: {result!s}")
                    if fail_fast:
                        break
                else:
                    successful += 1
                    outputs.append(result)

            if fail_fast and errors:
                break

        processing_time = (time.perf_counter() - start_time) * 1000

        # Update metrics
        self._batches_processed += 1
        self._total_chunks += len(chunks)
        self._total_time_ms += processing_time

        return BatchProcessingResult(
            chunks_processed=len(chunks),
            successful_chunks=successful,
            failed_chunks=failed,
            processing_time_ms=processing_time,
            parallel_factor=min(self.max_parallel, len(chunks)),
            outputs=outputs,
            errors=errors,
            constitutional_validated=True,
            metadata={
                "batch_size": self.batch_size,
                "num_batches": (len(chunks) + self.batch_size - 1) // self.batch_size,
            },
            constitutional_hash=self.constitutional_hash,
        )

    async def _process_chunk(
        self,
        chunk: ContextChunk,
        processor_fn: Callable[[ContextChunk], object],
    ) -> object:
        """Process a single chunk with semaphore control."""
        async with self._semaphore:
            # Support both sync and async processor functions
            if inspect.iscoroutinefunction(processor_fn):
                return await processor_fn(chunk)
            else:
                return processor_fn(chunk)

    def get_metrics(self) -> JSONDict:
        """Get processor metrics."""
        avg_time = self._total_time_ms / max(1, self._batches_processed)
        return {
            "batches_processed": self._batches_processed,
            "total_chunks": self._total_chunks,
            "total_time_ms": self._total_time_ms,
            "average_batch_time_ms": avg_time,
            "max_parallel": self.max_parallel,
            "batch_size": self.batch_size,
            "constitutional_hash": self.constitutional_hash,
        }


__all__ = [
    "ParallelBatchProcessor",
]
