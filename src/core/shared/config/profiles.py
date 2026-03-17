"""
ACGS-2 Shared Configuration - Environment Profiles
Constitutional Hash: cdd01ef066bc6cf2

Load dev / staging / production configuration presets from the
``ACGS_ENV`` environment variable.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from src.core.shared.structured_logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class ConfigProfile:
    """Environment-specific configuration preset.

    Attributes:
        name: Profile identifier (dev / staging / production).
        debug: Enable debug mode (verbose logging, stack traces).
        log_level: Python logging level name.
        security_strict: Enforce strict security policies.
        hsts_enabled: Send Strict-Transport-Security header.
        hsts_max_age: HSTS ``max-age`` value in seconds.
        cors_allow_all: Allow all CORS origins (dev only).
        rate_limit_multiplier: Scale factor applied to base rate limits.
        enable_profiling: Attach profiling middleware.
    """

    name: str = "dev"
    debug: bool = True
    log_level: str = "DEBUG"
    security_strict: bool = False
    hsts_enabled: bool = False
    hsts_max_age: int = 0
    cors_allow_all: bool = True
    rate_limit_multiplier: float = 10.0
    enable_profiling: bool = False

    # ------------------------------------------------------------------
    # Factory methods
    # ------------------------------------------------------------------

    @classmethod
    def from_env(cls) -> ConfigProfile:
        """Select profile based on ``ACGS_ENV`` environment variable.

        Recognised values (case-insensitive):
            ``dev`` / ``development`` — local development defaults.
            ``staging`` — staging environment.
            ``prod`` / ``production`` — hardened production settings.

        Falls back to ``dev`` when unset or unrecognised.
        """
        env = os.getenv("ACGS_ENV", "dev").lower().strip()
        if env in ("prod", "production"):
            return cls.production()
        if env == "staging":
            return cls.staging()
        if env not in ("dev", "development"):
            logger.warning("Unrecognised ACGS_ENV=%r, falling back to dev profile", env)
        return cls.dev()

    @classmethod
    def dev(cls) -> ConfigProfile:
        """Local development profile."""
        return cls(
            name="dev",
            debug=True,
            log_level="DEBUG",
            security_strict=False,
            hsts_enabled=False,
            hsts_max_age=0,
            cors_allow_all=True,
            rate_limit_multiplier=10.0,
            enable_profiling=True,
        )

    @classmethod
    def staging(cls) -> ConfigProfile:
        """Staging environment profile."""
        return cls(
            name="staging",
            debug=False,
            log_level="INFO",
            security_strict=True,
            hsts_enabled=True,
            hsts_max_age=86400,  # 1 day
            cors_allow_all=False,
            rate_limit_multiplier=2.0,
            enable_profiling=False,
        )

    @classmethod
    def production(cls) -> ConfigProfile:
        """Production environment profile."""
        return cls(
            name="production",
            debug=False,
            log_level="WARNING",
            security_strict=True,
            hsts_enabled=True,
            hsts_max_age=31536000,  # 1 year
            cors_allow_all=False,
            rate_limit_multiplier=1.0,
            enable_profiling=False,
        )
