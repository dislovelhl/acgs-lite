"""Embedded Cedar policy evaluation engine.

Constitutional Hash: 608508a9bd224290

Replaces external OPA server with in-process Cedar evaluation via cedarpy.
Sub-millisecond latency, no network overhead, no circuit breaker needed.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

try:
    import cedarpy

    CEDAR_AVAILABLE = True
except ImportError:
    cedarpy = None  # type: ignore[assignment]
    CEDAR_AVAILABLE = False
    logger.info("cedarpy not installed — Cedar policy engine unavailable")

CONSTITUTIONAL_HASH = "608508a9bd224290"


@dataclass(frozen=True)
class AuthzRequest:
    """Authorization request for Cedar evaluation."""

    principal: str
    action: str
    resource: str
    context: dict[str, Any] = field(default_factory=dict)

    def to_cedar_request(self) -> dict[str, str]:
        return {
            "principal": self.principal,
            "action": self.action,
            "resource": self.resource,
            "context": self.context,
        }


@dataclass(frozen=True)
class AuthzResult:
    """Result of Cedar policy evaluation."""

    allowed: bool
    decision: str
    diagnostics: dict[str, Any] = field(default_factory=dict)
    latency_ms: float = 0.0
    policies_evaluated: int = 0
    constitutional_hash: str = CONSTITUTIONAL_HASH


class CedarPolicyEngine:
    """Embedded Cedar policy engine using cedarpy.

    Loads Cedar policies from files or strings and evaluates authorization
    requests in-process. No external server required.

    Usage::

        engine = CedarPolicyEngine.from_policy_dir("policies/cedar/")
        result = engine.authorize(
            principal='Agent::"alpha"',
            action='Action::"propose"',
            resource='Resource::"draft-123"',
        )
        assert result.allowed
    """

    def __init__(
        self,
        policies: str,
        entities: list[dict[str, Any]] | None = None,
        schema: str | dict[str, Any] | None = None,
    ) -> None:
        if not CEDAR_AVAILABLE:
            raise ImportError(
                "cedarpy is required for Cedar policy engine. Install with: pip install cedarpy"
            )
        self._policies = policies
        self._entities = entities or []
        self._schema = schema
        self._stats = {"total": 0, "allowed": 0, "denied": 0, "errors": 0}

        # Validate policies against schema when provided
        if schema is not None:
            validation = cedarpy.validate_policies(policies, schema)
            if validation.errors:
                raise ValueError(f"Cedar policy validation failed: {validation.errors}")
            if validation.warnings:
                for w in validation.warnings:
                    logger.warning("Cedar policy warning: %s", w)

        # Verify policies parse correctly (no schema needed)
        try:
            cedarpy.format_policies(policies)
        except Exception as exc:
            raise ValueError(f"Cedar policy parse error: {exc}") from exc

    @classmethod
    def from_policy_dir(cls, path: str | Path) -> CedarPolicyEngine:
        """Load all .cedar files from a directory."""
        policy_dir = Path(path)
        if not policy_dir.is_dir():
            raise FileNotFoundError(f"Policy directory not found: {policy_dir}")

        policies: list[str] = []
        for cedar_file in sorted(policy_dir.glob("*.cedar")):
            policies.append(cedar_file.read_text())

        if not policies:
            raise ValueError(f"No .cedar files found in {policy_dir}")

        return cls(policies="\n\n".join(policies))

    @classmethod
    def from_policy_string(cls, policies: str) -> CedarPolicyEngine:
        """Create engine from a Cedar policy string."""
        return cls(policies=policies)

    def authorize(
        self,
        principal: str,
        action: str,
        resource: str,
        context: dict[str, Any] | None = None,
    ) -> AuthzResult:
        """Evaluate a single authorization request.

        Args:
            principal: Cedar principal (e.g., 'Agent::"alpha"')
            action: Cedar action (e.g., 'Action::"propose"')
            resource: Cedar resource (e.g., 'Resource::"draft-123"')
            context: Optional context dict for policy conditions

        Returns:
            AuthzResult with decision, diagnostics, and latency
        """
        start = time.perf_counter()
        self._stats["total"] += 1

        try:
            request = {
                "principal": principal,
                "action": action,
                "resource": resource,
            }
            if context:
                request["context"] = context

            result = cedarpy.is_authorized(
                request=request,
                policies=self._policies,
                entities=self._entities,
            )

            latency_ms = (time.perf_counter() - start) * 1000
            allowed = result.decision == cedarpy.Decision.Allow

            if allowed:
                self._stats["allowed"] += 1
            else:
                self._stats["denied"] += 1

            diagnostics = {}
            if hasattr(result, "diagnostics") and result.diagnostics:
                diag = result.diagnostics
                if hasattr(diag, "reason"):
                    diagnostics["reason"] = list(diag.reason) if diag.reason else []
                if hasattr(diag, "errors"):
                    diagnostics["errors"] = list(diag.errors) if diag.errors else []

            return AuthzResult(
                allowed=allowed,
                decision=result.decision.value
                if hasattr(result.decision, "value")
                else str(result.decision),
                diagnostics=diagnostics,
                latency_ms=latency_ms,
            )

        except Exception as exc:
            self._stats["errors"] += 1
            latency_ms = (time.perf_counter() - start) * 1000
            logger.error("Cedar evaluation failed: %s", type(exc).__name__)
            # Fail closed: deny on error
            return AuthzResult(
                allowed=False,
                decision="Deny",
                diagnostics={"error": type(exc).__name__},
                latency_ms=latency_ms,
            )

    def authorize_batch(
        self,
        requests: list[AuthzRequest],
    ) -> list[AuthzResult]:
        """Evaluate multiple authorization requests efficiently.

        Uses cedarpy.is_authorized_batch for ~10x throughput vs individual calls.
        """
        if not requests:
            return []

        start = time.perf_counter()
        cedar_requests = [r.to_cedar_request() for r in requests]

        try:
            results = cedarpy.is_authorized_batch(
                requests=cedar_requests,
                policies=self._policies,
                entities=self._entities,
            )

            batch_latency = (time.perf_counter() - start) * 1000
            per_request_latency = batch_latency / len(requests) if requests else 0

            authz_results = []
            for result in results:
                allowed = result.decision == cedarpy.Decision.Allow
                self._stats["total"] += 1
                if allowed:
                    self._stats["allowed"] += 1
                else:
                    self._stats["denied"] += 1

                authz_results.append(
                    AuthzResult(
                        allowed=allowed,
                        decision=result.decision.value
                        if hasattr(result.decision, "value")
                        else str(result.decision),
                        latency_ms=per_request_latency,
                    )
                )

            return authz_results

        except Exception as exc:
            self._stats["errors"] += len(requests)
            logger.error("Cedar batch evaluation failed: %s", type(exc).__name__)
            return [
                AuthzResult(
                    allowed=False, decision="Deny", diagnostics={"error": type(exc).__name__}
                )
                for _ in requests
            ]

    @property
    def stats(self) -> dict[str, int]:
        return dict(self._stats)
