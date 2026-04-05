"""Shim for src.core.shared.structured_logging."""
from __future__ import annotations

import logging
from typing import Any

try:
    from src.core.shared.structured_logging import *  # noqa: F403
    from src.core.shared.structured_logging import (
        configure_logging,
        get_correlation_id,
        get_logger,
        get_tenant_id,
        set_correlation_id,
        set_tenant_id,
    )
except ImportError:

    class _KwargsLogger(logging.LoggerAdapter):
        """Logger that accepts and discards extra kwargs (detail=, etc.)."""

        def process(self, msg: str, kwargs: dict) -> tuple[str, dict]:
            # Strip non-stdlib kwargs
            clean = {k: v for k, v in kwargs.items() if k in ("exc_info", "stack_info", "stacklevel", "extra")}
            return msg, clean

    def get_logger(name: str, **kwargs: Any) -> _KwargsLogger:
        """Return a kwargs-tolerant logger as a structlog stand-in."""
        base = logging.getLogger(name)
        if not base.handlers and not base.parent:
            handler = logging.StreamHandler()
            handler.setFormatter(
                logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
            )
            base.addHandler(handler)
        return _KwargsLogger(base, {})

    def configure_logging(**kwargs: Any) -> None:
        pass

    def set_correlation_id(cid: str | None = None) -> str:
        return cid or "standalone"

    def get_correlation_id() -> str:
        return "standalone"

    def set_tenant_id(tid: str) -> None:
        pass

    def get_tenant_id() -> str:
        return "default"

    def log_function_call(logger: Any = None) -> Any:
        """No-op decorator."""
        def decorator(func: Any) -> Any:
            return func
        return decorator
