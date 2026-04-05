"""Shim for src.core.shared.config.security."""

from __future__ import annotations

from typing import Any

try:
    from src.core.shared.config.security import *  # noqa: F403
except ImportError:

    class SecuritySettings:
        jwt_secret: str = ""
        jwt_algorithm: str = "HS256"
        jwt_expiry_seconds: int = 3600
        cors_origins: list[str] = ["*"]
        rate_limit_requests: int = 100
        rate_limit_window: int = 60
        enable_pqc: bool = False

        def __init__(self, **kwargs: Any) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)

    class OPASettings:
        url: str = "http://localhost:8181"
        policy_path: str = "/v1/data/acgs"
        enabled: bool = False

        def __init__(self, **kwargs: Any) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)

    class TLSSettings:
        enabled: bool = False
        cert_path: str = ""
        key_path: str = ""

        def __init__(self, **kwargs: Any) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)
