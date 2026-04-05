"""
ACGS-2 HITL (Human-In-The-Loop) Manager
Constitutional Hash: 608508a9bd224290

Orchestrates human approval workflows for high-risk agent actions.
Integrates with DeliberationLayer and AuditLedger.
"""

import json
import os
from datetime import UTC, datetime, timezone
from importlib import import_module
from typing import TYPE_CHECKING, Protocol, cast

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger


def _load_deliberation_queue_types() -> tuple[object, object]:
    """Load queue/status types from available package paths."""
    candidates = (
        "enhanced_agent_bus.deliberation_layer.deliberation_queue",
        "enhanced_agent_bus.deliberation_layer.deliberation_queue",
        ".deliberation_queue",
        "deliberation_queue",
    )
    for candidate in candidates:
        try:
            module = import_module(candidate, package=__package__)
            return module.DeliberationQueue, module.DeliberationStatus
        except (ImportError, AttributeError):
            continue
    raise ImportError("Unable to load deliberation queue dependencies")


def _load_constitutional_hash() -> str:
    """Load constitutional hash constant from available package paths."""
    candidates = (
        "enhanced_agent_bus.models",
        "enhanced_agent_bus.models",
        "..models",
        "models",
    )
    for candidate in candidates:
        try:
            module = import_module(candidate, package=__package__)
            return str(module.CONSTITUTIONAL_HASH)
        except (ImportError, AttributeError):
            continue
    return CONSTITUTIONAL_HASH  # pragma: allowlist secret


_DeliberationQueue, _DeliberationStatus = _load_deliberation_queue_types()
_CONSTITUTIONAL_HASH = _load_constitutional_hash()

if TYPE_CHECKING:
    from enhanced_agent_bus.deliberation_layer.deliberation_queue import (
        DeliberationQueue,
        DeliberationStatus,
    )
else:
    DeliberationQueue = cast(type[object], _DeliberationQueue)
    DeliberationStatus = cast(type[object], _DeliberationStatus)
CONSTITUTIONAL_HASH = _CONSTITUTIONAL_HASH

# Try to import ValidationResult from canonical source first
try:
    from enhanced_agent_bus.validators import ValidationResult
except ImportError:
    try:
        from enhanced_agent_bus.validators import ValidationResult
    except ImportError:
        try:
            from enhanced_agent_bus.validators import ValidationResult
        except ImportError:
            try:
                from validators import ValidationResult  # type: ignore[import-untyped]
            except ImportError:
                from dataclasses import dataclass, field

                @dataclass
                class ValidationResult:  # type: ignore[no-redef]
                    """Fallback ValidationResult - mirrors validators.ValidationResult interface.

                    Constitutional Hash: 608508a9bd224290
                    """

                    is_valid: bool = True
                    errors: list[str] = field(default_factory=list)
                    warnings: list[str] = field(default_factory=list)
                    metadata: JSONDict = field(default_factory=dict)
                    decision: str = "ALLOW"
                    constitutional_hash: str = CONSTITUTIONAL_HASH

                    def add_error(self, error: str) -> None:
                        """Add an error to the result."""
                        self.errors.append(error)
                        self.is_valid = False

                    def to_dict(self) -> JSONDict:
                        """Convert to dictionary for serialization."""
                        return {
                            "is_valid": self.is_valid,
                            "errors": self.errors,
                            "warnings": self.warnings,
                            "metadata": self.metadata,
                            "decision": self.decision,
                            "constitutional_hash": self.constitutional_hash,
                        }


# Try to import AuditLedger
try:
    from src.core.audit_ledger import AuditLedger
except ImportError:

    class _ValidationResultProtocol(Protocol):
        def to_dict(self) -> JSONDict: ...

    class AuditLedger:  # type: ignore[no-redef]
        """Mock AuditLedger."""

        async def add_validation_result(self, res: _ValidationResultProtocol) -> str:
            """Mock add."""
            logger.debug(f"Mock audit recorded: {res.to_dict()}")
            return "mock_audit_hash"


logger = get_logger(__name__)


class HITLManager:
    """Manages the Human-In-The-Loop lifecycle."""

    def __init__(
        self, deliberation_queue: DeliberationQueue, audit_ledger: AuditLedger | None = None
    ):
        """Initialize HITL Manager."""
        self.queue = deliberation_queue
        self.audit_ledger = audit_ledger or AuditLedger()

    async def request_approval(self, item_id: str, channel: str = "slack") -> None:
        """
        Notify stakeholders about a pending high-risk action.
        Implements Pillar 2: Enterprise messaging integration.
        """
        item = self.queue.queue.get(item_id)
        if not item:
            logger.error(f"Item {item_id} not found in queue")
            return

        msg = item.message
        payload = {
            "text": "🚨 *High-Risk Agent Action Detected*",
            "attachments": [
                {
                    "fields": [
                        {"title": "Agent ID", "value": msg.from_agent, "short": True},
                        {"title": "Impact Score", "value": str(msg.impact_score), "short": True},
                        {"title": "Action type", "value": msg.message_type.value, "short": False},
                        {
                            "title": "Content",
                            "value": str(msg.content)[:100] + "...",
                            "short": False,
                        },
                    ],
                    "callback_id": item_id,
                    "actions": [
                        {
                            "name": "approve",
                            "text": "Approve",
                            "type": "button",
                            "style": "primary",
                        },
                        {"name": "reject", "text": "Reject", "type": "button", "style": "danger"},
                    ],
                }
            ],
        }

        # Simulate sending to Slack/Teams
        logger.info(f"Notification sent to {channel}: {json.dumps(payload, indent=2)}")

        # Update status to under review
        item.status = DeliberationStatus.UNDER_REVIEW

    async def process_approval(
        self, item_id: str, reviewer_id: str, decision: str, reasoning: str
    ) -> bool:
        """
        Process the human decision and record to audit ledger.
        Implements Pillar 2: Immutable audit metadata.
        """
        if decision == "approve":
            status = DeliberationStatus.APPROVED
        else:
            status = DeliberationStatus.REJECTED

        success = await self.queue.submit_human_decision(
            item_id=item_id, reviewer=reviewer_id, decision=status, reasoning=reasoning
        )

        if success:
            # Record to Audit Ledger
            audit_res = ValidationResult(
                is_valid=(status == DeliberationStatus.APPROVED),
                constitutional_hash=CONSTITUTIONAL_HASH,
                metadata={
                    "item_id": item_id,
                    "reviewer": reviewer_id,
                    "decision": decision,
                    "reasoning": reasoning,
                    "timestamp": datetime.now(UTC).isoformat(),
                },
            )
            audit_hash = await self.audit_ledger.add_validation_result(audit_res)
            logger.info(f"Decision for {item_id} recorded. Hash: {audit_hash}")
            return True

        return False


if __name__ == "__main__":
    # Simple test
    import logging as _logging

    _logging.basicConfig(level=_logging.INFO)
    q = DeliberationQueue()
    mgr = HITLManager(q)
    logger.info("HITL Manager initialized.")
