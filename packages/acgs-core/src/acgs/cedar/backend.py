"""CedarBackend — PolicyBackend implementation using embedded Cedar.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from acgs.policy.backend import PolicyBackend, PolicyDecision

logger = logging.getLogger(__name__)

try:
    import cedarpy

    CEDAR_AVAILABLE = True
except ImportError:
    cedarpy = None  # type: ignore[assignment]
    CEDAR_AVAILABLE = False


class CedarBackend(PolicyBackend):
    """Cedar policy evaluation via cedarpy (Rust-backed, in-process).

    Conforms to the PolicyBackend ABC so it can be swapped in for
    HeuristicBackend without changing calling code.
    """

    def __init__(
        self,
        policies: str,
        entities: list[dict[str, Any]] | None = None,
        schema: str | dict[str, Any] | None = None,
    ) -> None:
        if not CEDAR_AVAILABLE:
            raise ImportError("cedarpy required. Install with: pip install acgs[cedar]")
        self._policies = policies
        self._entities = entities or []
        self._stats = {"total": 0, "allowed": 0, "denied": 0, "errors": 0}

        if schema is not None:
            validation = cedarpy.validate_policies(policies, schema)
            if validation.errors:
                raise ValueError(f"Cedar policy validation failed: {validation.errors}")

        try:
            cedarpy.format_policies(policies)
        except Exception as exc:
            raise ValueError(f"Cedar policy parse error: {exc}") from exc

    @classmethod
    def from_policy_dir(cls, path: str | Path) -> CedarBackend:
        """Load all .cedar files from a directory."""
        policy_dir = Path(path)
        if not policy_dir.is_dir():
            raise FileNotFoundError(f"Policy directory not found: {policy_dir}")
        policies = [f.read_text() for f in sorted(policy_dir.glob("*.cedar"))]
        if not policies:
            raise ValueError(f"No .cedar files found in {policy_dir}")
        return cls(policies="\n\n".join(policies))

    @classmethod
    def from_string(cls, policies: str) -> CedarBackend:
        """Create from a Cedar policy string."""
        return cls(policies=policies)

    def evaluate(
        self,
        action: str,
        *,
        agent_id: str = "anonymous",
        context: dict[str, Any] | None = None,
    ) -> PolicyDecision:
        start = time.perf_counter()
        self._stats["total"] += 1

        try:
            request = {
                "principal": f'Agent::"{agent_id}"',
                "action": f'Action::"{action}"',
                "resource": 'Resource::"default"',
            }
            if context:
                request["context"] = context

            result = cedarpy.is_authorized(
                request=request,
                policies=self._policies,
                entities=self._entities,
            )

            latency = (time.perf_counter() - start) * 1000
            allowed = result.decision == cedarpy.Decision.Allow

            if allowed:
                self._stats["allowed"] += 1
            else:
                self._stats["denied"] += 1

            violations = []
            if not allowed and hasattr(result, "diagnostics") and result.diagnostics:
                if hasattr(result.diagnostics, "errors") and result.diagnostics.errors:
                    violations = [
                        {"type": "cedar_deny", "detail": str(e)} for e in result.diagnostics.errors
                    ]

            return PolicyDecision(
                allowed=allowed,
                violations=violations,
                latency_ms=latency,
                backend="cedar",
            )
        except (TypeError, ValueError, RuntimeError, OSError) as exc:
            self._stats["errors"] += 1
            latency = (time.perf_counter() - start) * 1000
            logger.error("Cedar evaluation failed: %s", type(exc).__name__)
            return PolicyDecision(
                allowed=False,
                violations=[{"type": "error", "detail": type(exc).__name__}],
                latency_ms=latency,
                backend="cedar",
            )

    @property
    def name(self) -> str:
        return "cedar"

    @property
    def stats(self) -> dict[str, int]:
        return dict(self._stats)
