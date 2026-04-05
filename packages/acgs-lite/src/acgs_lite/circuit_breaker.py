# ACGS - Constitutional AI Governance
# Copyright (C) 2024-2026 ACGS Contributors
# Licensed under Apache-2.0. See LICENSE for details.
# Commercial license: https://acgs.ai

"""Global governance circuit breaker — EU AI Act Article 14 kill-switch.

Article 14 requires that high-risk AI systems allow natural persons to
intervene, halt, or override the system. This module provides a
thread-safe, cross-process mechanism to halt all governed agents.

Usage::

    from acgs_lite import GovernanceCircuitBreaker

    breaker = GovernanceCircuitBreaker(system_id="cv-screener")

    # Trip the breaker (halt all governed agents for this system)
    breaker.trip(reason="Human oversight review required")

    # Check status
    if breaker.is_tripped:
        print(f"HALTED: {breaker.trip_reason}")

    # Resume operations
    breaker.reset()

Cross-process signaling uses a file-based mechanism:
    /tmp/acgs-halt-{system_id}

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import logging
import os
import tempfile
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_SIGNAL_DIR = Path(tempfile.gettempdir())


class GovernanceHaltError(Exception):
    """Raised when a governed operation is attempted while the circuit breaker is tripped."""

    def __init__(self, system_id: str, reason: str = "") -> None:
        self.system_id = system_id
        self.reason = reason
        msg = f"Governance halted for system '{system_id}'"
        if reason:
            msg += f": {reason}"
        super().__init__(msg)


class GovernanceCircuitBreaker:
    """Thread-safe, cross-process governance halt mechanism.

    Supports two modes:
    - **In-process**: Uses a threading.Event for immediate signaling
      within the same process.
    - **Cross-process**: Uses an atomic file signal that other processes
      can detect when calling ``check()``.

    Args:
        system_id: Identifier for the AI system this breaker controls.
        signal_dir: Directory for cross-process signal files.
            Defaults to the system temp directory.
        check_file: If True, also check the file signal on ``is_tripped``
            and ``check()``. Enables cross-process detection.
    """

    def __init__(
        self,
        system_id: str,
        signal_dir: Path | None = None,
        check_file: bool = True,
    ) -> None:
        self.system_id = system_id
        self._signal_dir = signal_dir or _DEFAULT_SIGNAL_DIR
        self._check_file = check_file
        self._event = threading.Event()  # set = tripped
        self._reason = ""
        self._tripped_at: float | None = None
        self._lock = threading.Lock()

    @property
    def _signal_path(self) -> Path:
        """Path to the cross-process signal file."""
        return self._signal_dir / f"acgs-halt-{self.system_id}"

    def trip(self, reason: str = "") -> None:
        """Trip the circuit breaker, halting all governed operations.

        Args:
            reason: Human-readable reason for the halt.
        """
        with self._lock:
            self._reason = reason
            self._tripped_at = time.time()
            self._event.set()

        # Atomic file write for cross-process signaling
        try:
            tmp_path = self._signal_path.with_suffix(".tmp")
            tmp_path.write_text(reason or "halted")
            tmp_path.rename(self._signal_path)
            logger.warning(
                "circuit breaker tripped: system=%s reason=%s",
                self.system_id,
                reason,
            )
        except Exception as exc:
            logger.debug("failed to write signal file: %s", exc, exc_info=True)

    def reset(self) -> None:
        """Reset the circuit breaker, allowing operations to resume."""
        with self._lock:
            self._event.clear()
            self._reason = ""
            self._tripped_at = None

        # Remove signal file
        try:
            self._signal_path.unlink(missing_ok=True)
            logger.info("circuit breaker reset: system=%s", self.system_id)
        except Exception as exc:
            logger.debug("failed to remove signal file: %s", exc, exc_info=True)

    @property
    def is_tripped(self) -> bool:
        """Check if the breaker is tripped (in-process or cross-process)."""
        if self._event.is_set():
            return True
        if self._check_file and self._signal_path.exists():
            return True
        return False

    @property
    def trip_reason(self) -> str:
        """Return the reason the breaker was tripped, or empty string."""
        if self._reason:
            return self._reason
        if self._check_file and self._signal_path.exists():
            try:
                return self._signal_path.read_text().strip()
            except Exception as exc:
                logger.debug("failed to read signal file: %s", exc, exc_info=True)
                return "halted (reason unavailable)"
        return ""

    def check(self) -> None:
        """Check the breaker and raise GovernanceHaltError if tripped.

        Call this at the start of every governed operation.
        """
        if self.is_tripped:
            raise GovernanceHaltError(self.system_id, self.trip_reason)

    def __repr__(self) -> str:
        status = "TRIPPED" if self.is_tripped else "OK"
        return f"GovernanceCircuitBreaker(system={self.system_id!r}, status={status})"
