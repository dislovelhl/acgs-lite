"""Constitutional hash validator — MACI Validator role only.

Constitutional Hash: 608508a9bd224290

This validator ONLY verifies constitutional compliance.
It does NOT propose, execute, or remediate — those are separate MACI roles.
"""

from __future__ import annotations

import logging
from importlib import import_module
from typing import Any

logger = logging.getLogger(__name__)

try:
    constants_module = import_module("src.core.shared.constants")
    _constitutional_hash_default = str(constants_module.CONSTITUTIONAL_HASH)
except (ImportError, AttributeError):
    _constitutional_hash_default = "608508a9bd224290"

CONSTITUTIONAL_HASH: str = _constitutional_hash_default


class ConstitutionalHashValidator:
    """Independent constitutional hash validator (MACI: Validator role).

    Validates that provided hashes match the expected constitutional hash.
    Does NOT propose actions or execute decisions.
    """

    def __init__(self, expected_hash: str = CONSTITUTIONAL_HASH) -> None:
        self._expected_hash = expected_hash

    async def validate_hash(
        self,
        *,
        provided_hash: str,
        expected_hash: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> tuple[bool, str]:
        """Validate constitutional hash compliance."""
        target = expected_hash or self._expected_hash
        is_valid = provided_hash == target
        if not is_valid:
            msg = f"Constitutional hash mismatch: provided={provided_hash!r}, expected={target!r}"
            logger.warning(
                "constitutional_hash_mismatch",
                extra={"provided": provided_hash, "expected": target, **(context or {})},
            )
            return False, msg
        return True, ""
