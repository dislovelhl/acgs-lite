"""Shim for src.core.shared.acgs_logging."""

from __future__ import annotations

import logging
from typing import Any

try:
    from src.core.shared.acgs_logging import *  # noqa: F403
except ImportError:

    def get_logger(name: str, **kwargs: Any) -> logging.Logger:
        """Return a stdlib logger as a structlog stand-in."""
        logger = logging.getLogger(name)
        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(
                logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
            )
            logger.addHandler(handler)
        return logger

    def init_service_logging(
        service_name: str = "",
        log_level: str = "INFO",
        **kwargs: Any,
    ) -> None:
        """Configure basic logging for standalone mode."""
        logging.basicConfig(
            level=getattr(logging, log_level.upper(), logging.INFO),
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
