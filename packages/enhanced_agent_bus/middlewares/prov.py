"""
PROV Provenance Middleware for ACGS-2 Pipeline.

Stamps a W3C PROV provenance label on the PipelineContext after each
governance decision point, building a full lineage chain for the message.

Design:
- fail_closed=False — provenance failures are logged but never block processing.
- The middleware stamps AFTER calling _call_next() so the label records
  what downstream stages decided, not what they were about to decide.
- Stage name is derived from ctx.middleware_path[-2] (the entry added just
  before ProvMiddleware registered itself).
- Timestamps bracket the downstream call for accurate activity duration.

Constitutional Hash: 608508a9bd224290
NIST 800-53 AU-2, AU-9 — Audit Events, Protection of Audit Information
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from enhanced_agent_bus.observability.structured_logging import get_logger

from ..pipeline.context import PipelineContext
from ..pipeline.middleware import BaseMiddleware, MiddlewareConfig
from ..prov.labels import ProvLabel, build_prov_label

logger = get_logger(__name__)


def _utc_now_iso() -> str:
    """Return current timezone.utc time as ISO 8601 string."""
    return datetime.now(tz=UTC).isoformat()


# Maps middleware class names to PROV stage names.
_MIDDLEWARE_STAGE_MAP: dict[str, str] = {
    "SecurityMiddleware": "security_scan",
    "ConstitutionalValidationMiddleware": "constitutional_validation",
    "MACIEnforcementMiddleware": "maci_enforcement",
    "ImpactScorerMiddleware": "impact_scoring",
    "HITLMiddleware": "hitl_review",
    "TemporalPolicyMiddleware": "temporal_policy",
    "ToolPrivilegeMiddleware": "tool_privilege",
    "StrategyMiddleware": "strategy",
    "IFCMiddleware": "ifc_check",
}


def _middleware_name_to_stage(middleware_name: str) -> str:
    """Map a middleware class name to a PROV stage name.

    Falls back to the middleware name lowercased if no mapping is found.

    Args:
        middleware_name: The string name as added to ``ctx.middleware_path``.

    Returns:
        Snake_case stage name suitable for PROV type map lookup.
    """
    if middleware_name in _MIDDLEWARE_STAGE_MAP:
        return _MIDDLEWARE_STAGE_MAP[middleware_name]
    # Generic fallback: strip "Middleware" suffix and convert PascalCase → snake
    name = middleware_name.removesuffix("Middleware")
    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
    return snake or "unknown_stage"


class ProvMiddleware(BaseMiddleware):
    """
    Middleware that stamps a W3C PROV provenance label on PipelineContext
    after each governance decision point.

    Reads:
        ctx.middleware_path         — determines stage name from last entry
        ctx.message.message_id      — used in entity label for traceability

    Writes:
        ctx.prov_lineage            — appends one ProvLabel per invocation

    Fail behaviour:
        fail_closed=False — any exception during stamping is caught, logged,
        and silently dropped. Message processing continues unimpeded.

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(self, config: MiddlewareConfig | None = None) -> None:
        super().__init__(config or MiddlewareConfig(timeout_ms=50, fail_closed=False))

    async def process(self, context: PipelineContext) -> PipelineContext:
        context.add_middleware("ProvMiddleware")

        started_at = _utc_now_iso()

        # Call downstream middleware chain first.
        context = await self._call_next(context)

        ended_at = _utc_now_iso()

        # Determine which stage just ran from the middleware path.
        # path[-1] == "ProvMiddleware", path[-2] == the most recent prior stage.
        stage_name = self._resolve_stage_name(context)

        try:
            label: ProvLabel = build_prov_label(
                stage_name=stage_name,
                started_at=started_at,
                ended_at=ended_at,
            )
            context.record_prov_label(label)
            logger.debug(
                "ProvMiddleware: stamped provenance for stage=%r entity=%r",
                stage_name,
                label.entity.id,
            )
        except (OSError, ValueError, TypeError, KeyError) as exc:
            # Fail-open: provenance errors must never block governance.
            logger.warning(
                "ProvMiddleware: failed to stamp provenance for stage=%r — continuing: %s",
                stage_name,
                exc,
            )

        return context

    def _resolve_stage_name(self, context: PipelineContext) -> str:
        """Derive a stage name from the middleware execution path.

        Returns the second-to-last path entry (the stage that ran just
        before ProvMiddleware registered itself), falling back to
        ``"unknown_stage"`` if the path is too short.

        Args:
            context: The current pipeline context.

        Returns:
            A snake_case stage name string.
        """
        path = context.middleware_path
        # path[-1] == "ProvMiddleware" (just added above).
        # path[-2] == the entry immediately before it.
        if len(path) < 2:
            return "unknown_stage"
        return _middleware_name_to_stage(path[-2])
