"""Shim for src.core.shared.feature_flags."""

from __future__ import annotations

from typing import Any

try:
    from src.core.shared.feature_flags import *  # noqa: F403
except ImportError:
    FEATURES: dict[str, bool] = {}

    def is_enabled(flag: str, default: bool = False) -> bool:
        return FEATURES.get(flag, default)

    def set_flag(flag: str, value: bool) -> None:
        FEATURES[flag] = value

    def get_all_flags() -> dict[str, bool]:
        return dict(FEATURES)

    class FeatureFlagService:
        def __init__(self, **kwargs: Any) -> None:
            self._flags: dict[str, bool] = {}

        def is_enabled(self, flag: str, default: bool = False) -> bool:
            return self._flags.get(flag, default)

        def set_flag(self, flag: str, value: bool) -> None:
            self._flags[flag] = value
