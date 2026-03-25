# Constitutional Hash: 608508a9bd224290
from __future__ import annotations

import hashlib
import sys
import time
from collections.abc import Generator
from contextlib import contextmanager


class ExecutionTimeout(BaseException):
    """Raised when a code block exceeds its allotted execution time."""

    pass


def sha256_hex(text: str) -> str:
    """Return the SHA-256 hex digest of the given UTF-8 text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@contextmanager
def python_execution_time_limit(seconds: float) -> Generator[None, None, None]:
    """Context manager that raises ExecutionTimeout if the block runs longer than seconds."""
    if seconds <= 0:
        yield
        return

    start = time.monotonic()
    prev_trace = sys.gettrace()

    def _trace(frame, event: str, arg):
        if time.monotonic() - start >= seconds:
            raise ExecutionTimeout()
        return _trace

    def _set_stack_trace(trace_fn) -> None:
        frame = sys._getframe()
        while frame is not None:
            frame.f_trace = trace_fn
            frame = frame.f_back

    # Ensure tracing is active globally and for all currently-active frames.
    # This avoids hangs in tight loops within the already-running caller frame.
    _set_stack_trace(_trace)
    sys.settrace(_trace)
    try:
        yield
    finally:
        _set_stack_trace(prev_trace)
        sys.settrace(prev_trace)


__all__ = ["ExecutionTimeout", "python_execution_time_limit", "sha256_hex"]
