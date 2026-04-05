"""Shim for src.core.shared.structured_logging."""
from __future__ import annotations

import logging
from typing import Any

try:
    from src.core.shared.structured_logging import *  # noqa: F403
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

    def init_logging(**kwargs: Any) -> None:
        """No-op logging initialisation."""

    def configure_structlog(**kwargs: Any) -> None:
        """No-op structlog configuration."""
