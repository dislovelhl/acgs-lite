"""Shim for src.core.shared.api_versioning."""

from __future__ import annotations

from typing import Any

try:
    from src.core.shared.api_versioning import *  # noqa: F403
except ImportError:
    DEFAULT_API_VERSION = "v1"

    class APIVersion:
        def __init__(self, version: str = DEFAULT_API_VERSION) -> None:
            self.version = version
            self.major = int(version.lstrip("v").split(".")[0]) if version else 1

        def __str__(self) -> str:
            return self.version

        def __repr__(self) -> str:
            return f"APIVersion({self.version!r})"

    def get_api_version() -> str:
        return DEFAULT_API_VERSION

    def version_prefix(version: str = DEFAULT_API_VERSION) -> str:
        return f"/api/{version}"

    class VersionedRouter:
        """Stub versioned router."""

        def __init__(self, version: str = DEFAULT_API_VERSION, **kwargs: Any) -> None:
            self.version = version
            self.prefix = f"/api/{version}"
