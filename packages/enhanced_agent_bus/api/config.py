"""
ACGS-2 Enhanced Agent Bus API Configuration
Constitutional Hash: 608508a9bd224290

This module contains all configuration constants for the API layer,
including rate limits, size limits, and server configuration.
"""

from __future__ import annotations

import os

from enhanced_agent_bus.observability.structured_logging import get_logger

_logger = get_logger(__name__)


def _env_positive_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        _logger.warning("Invalid value for %s=%r, using default %d", name, raw, default)
        return default
    if value <= 0:
        _logger.warning("%s must be > 0, got %d, using default %d", name, value, default)
        return default
    return value


# ===== Environment-Configured Rate Limits =====
RATE_LIMIT_REQUESTS_PER_MINUTE = _env_positive_int("RATE_LIMIT_REQUESTS_PER_MINUTE", 60)
BATCH_RATE_LIMIT_BASE = _env_positive_int("BATCH_RATE_LIMIT_BASE", 100)
MAX_ITEM_CONTENT_SIZE = _env_positive_int("MAX_ITEM_CONTENT_SIZE", 1048576)

# ===== Configuration Constants (Phase 3B: Magic Number Extraction) =====
# Constitutional Hash: 608508a9bd224290

# Default values for environment variables
DEFAULT_RATE_LIMIT_REQUESTS_PER_MINUTE = 60
DEFAULT_BATCH_RATE_LIMIT_BASE = 100
DEFAULT_MAX_ITEM_CONTENT_SIZE_BYTES = 1048576  # 1 MB

# Rate limit calculation settings
RATE_LIMIT_COST_DIVISOR = 10  # batch_size / 10 = token cost
RATE_LIMIT_WINDOW_CLEANUP_MINUTES = 2  # Cleanup old rate limit windows
RATE_LIMIT_WINDOW_DURATION_MINUTES = 1  # Rate limit window duration

# Size conversion constants
BYTES_PER_MB = 1024 * 1024  # 1 MB = 1,048,576 bytes

# Display limits for error messages
MAX_VIOLATIONS_TO_DISPLAY = 5  # Show first N oversized items in error

# Circuit breaker settings
CIRCUIT_BREAKER_FAIL_MAX = 5  # Max failures before opening circuit
CIRCUIT_BREAKER_RESET_TIMEOUT_SECONDS = 60  # Seconds before retrying

# API rate limit decorator value
API_RATE_LIMIT_PER_MINUTE = "10/minute"

# Batch processor initialization defaults
BATCH_PROCESSOR_MAX_CONCURRENCY = 100
BATCH_PROCESSOR_ITEM_TIMEOUT_SECONDS = 30.0
BATCH_PROCESSOR_SLOW_ITEM_THRESHOLD_SECONDS = 5.0

# Cache warming settings
CACHE_WARMING_RATE_LIMIT = 100  # Keys per second during cache warming

# API version
API_VERSION = "1.0.0"

# Server configuration
DEFAULT_API_PORT = 8000
DEFAULT_WORKERS = 1

# Milliseconds conversion
MS_PER_SECOND = 1000

__all__ = [
    "API_RATE_LIMIT_PER_MINUTE",
    "API_VERSION",
    "BATCH_PROCESSOR_ITEM_TIMEOUT_SECONDS",
    "BATCH_PROCESSOR_MAX_CONCURRENCY",
    "BATCH_PROCESSOR_SLOW_ITEM_THRESHOLD_SECONDS",
    "BATCH_RATE_LIMIT_BASE",
    "BYTES_PER_MB",
    "CACHE_WARMING_RATE_LIMIT",
    "CIRCUIT_BREAKER_FAIL_MAX",
    "CIRCUIT_BREAKER_RESET_TIMEOUT_SECONDS",
    "DEFAULT_API_PORT",
    "DEFAULT_BATCH_RATE_LIMIT_BASE",
    "DEFAULT_MAX_ITEM_CONTENT_SIZE_BYTES",
    "DEFAULT_RATE_LIMIT_REQUESTS_PER_MINUTE",
    "DEFAULT_WORKERS",
    "MAX_ITEM_CONTENT_SIZE",
    "MAX_VIOLATIONS_TO_DISPLAY",
    "MS_PER_SECOND",
    "RATE_LIMIT_COST_DIVISOR",
    "RATE_LIMIT_REQUESTS_PER_MINUTE",
    "RATE_LIMIT_WINDOW_CLEANUP_MINUTES",
    "RATE_LIMIT_WINDOW_DURATION_MINUTES",
]
