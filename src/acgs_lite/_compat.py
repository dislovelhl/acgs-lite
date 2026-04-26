"""Python version compatibility helpers.

Polyfills for stdlib features added after Python 3.10.
"""

from __future__ import annotations

import sys

if sys.version_info >= (3, 11):
    from enum import StrEnum as StrEnum  # noqa: PLC0414
else:
    from enum import Enum

    class StrEnum(str, Enum):  # type: ignore[no-redef]
        """str + Enum mixin — available natively in Python 3.11+."""


__all__ = ["StrEnum"]
