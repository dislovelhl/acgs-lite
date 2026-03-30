"""Constitutional audit logging for Token Vault access.

Every token retrieval, denial, and step-up approval is recorded with the
MACI role, agent ID, scopes, outcome, and constitutional hash so that the
governance record is immutable and auditable.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CONSTITUTIONAL_HASH = "608508a9bd224290"


class TokenAccessOutcome(str, Enum):
    """Outcome of a token access attempt."""

    GRANTED = "granted"
    DENIED_SCOPE_VIOLATION = "denied_scope_violation"
    DENIED_ROLE_NOT_PERMITTED = "denied_role_not_permitted"
    STEP_UP_INITIATED = "step_up_initiated"
    STEP_UP_APPROVED = "step_up_approved"
    STEP_UP_DENIED = "step_up_denied"
    ERROR = "error"


@dataclass
class TokenAccessAuditEntry:
    """Immutable audit record for a single Token Vault access attempt.

    Attributes:
        agent_id: Identifier of the requesting agent.
        role: MACI role of the agent.
        connection: External provider connection name.
        requested_scopes: OAuth scopes the agent requested.
        granted_scopes: Scopes that were actually granted (empty on denial).
        outcome: Classification of the access result.
        constitutional_hash: Hash of the governing constitution.
        user_id: Auth0 user ID whose tokens are being accessed.
        tool_name: LangChain tool name that triggered the access.
        step_up_binding_message: CIBA binding message if step-up was triggered.
        error_message: Error detail if outcome is DENIED or ERROR.
        timestamp: UTC time of the access attempt.
        extra: Arbitrary metadata for extension points.
    """

    agent_id: str
    role: str
    connection: str
    requested_scopes: list[str]
    granted_scopes: list[str]
    outcome: TokenAccessOutcome
    constitutional_hash: str = CONSTITUTIONAL_HASH
    user_id: str | None = None
    tool_name: str | None = None
    step_up_binding_message: str | None = None
    error_message: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dictionary suitable for JSON logging."""
        d = asdict(self)
        d["outcome"] = self.outcome.value
        d["timestamp"] = self.timestamp.isoformat()
        return d

    def to_json(self) -> str:
        """Serialize to a JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str)


class TokenAuditLog:
    """In-memory (and optionally file-backed) audit log for token access events.

    Thread-safe.  In production, replace the append() method with a call to
    your organisation's SIEM or structured logging pipeline.

    Usage::

        log = TokenAuditLog()
        log.record_granted(agent_id="planner", role="EXECUTIVE",
                           connection="github", scopes=["repo:read"], user_id="u1")
        log.record_denied(agent_id="planner", role="EXECUTIVE",
                          connection="github", scopes=["repo:write"],
                          reason="scope_violation", error_message="...")
        entries = log.get_entries(agent_id="planner")
    """

    def __init__(
        self,
        *,
        file_path: str | Path | None = None,
        emit_structlog: bool = False,
    ) -> None:
        self._entries: list[TokenAccessAuditEntry] = []
        self._lock = threading.Lock()
        self._file_path = Path(file_path) if file_path else None
        self._emit_structlog = emit_structlog

        if emit_structlog:
            try:
                import structlog  # noqa: F401

                self._structlog_available = True
            except ImportError:
                self._structlog_available = False
                logger.warning(
                    "structlog not installed — falling back to stdlib logging for audit"
                )
        else:
            self._structlog_available = False

    # ------------------------------------------------------------------
    # Recording helpers
    # ------------------------------------------------------------------

    def record_granted(
        self,
        *,
        agent_id: str,
        role: str,
        connection: str,
        scopes: list[str],
        user_id: str | None = None,
        tool_name: str | None = None,
    ) -> TokenAccessAuditEntry:
        """Record a successful token grant."""
        return self._append(
            TokenAccessAuditEntry(
                agent_id=agent_id,
                role=role,
                connection=connection,
                requested_scopes=scopes,
                granted_scopes=scopes,
                outcome=TokenAccessOutcome.GRANTED,
                user_id=user_id,
                tool_name=tool_name,
            )
        )

    def record_denied(
        self,
        *,
        agent_id: str,
        role: str,
        connection: str,
        scopes: list[str],
        reason: str,
        error_message: str | None = None,
        user_id: str | None = None,
        tool_name: str | None = None,
    ) -> TokenAccessAuditEntry:
        """Record a token access denial."""
        outcome_map = {
            "scope_violation": TokenAccessOutcome.DENIED_SCOPE_VIOLATION,
            "role_not_permitted": TokenAccessOutcome.DENIED_ROLE_NOT_PERMITTED,
        }
        outcome = outcome_map.get(reason, TokenAccessOutcome.ERROR)
        return self._append(
            TokenAccessAuditEntry(
                agent_id=agent_id,
                role=role,
                connection=connection,
                requested_scopes=scopes,
                granted_scopes=[],
                outcome=outcome,
                error_message=error_message,
                user_id=user_id,
                tool_name=tool_name,
            )
        )

    def record_step_up_initiated(
        self,
        *,
        agent_id: str,
        role: str,
        connection: str,
        scopes: list[str],
        binding_message: str,
        user_id: str | None = None,
        tool_name: str | None = None,
    ) -> TokenAccessAuditEntry:
        """Record the initiation of a CIBA step-up request."""
        return self._append(
            TokenAccessAuditEntry(
                agent_id=agent_id,
                role=role,
                connection=connection,
                requested_scopes=scopes,
                granted_scopes=[],
                outcome=TokenAccessOutcome.STEP_UP_INITIATED,
                user_id=user_id,
                tool_name=tool_name,
                step_up_binding_message=binding_message,
            )
        )

    def record_step_up(
        self,
        *,
        agent_id: str,
        role: str,
        connection: str,
        scopes: list[str],
        binding_message: str,
        approved: bool,
        user_id: str | None = None,
        tool_name: str | None = None,
    ) -> TokenAccessAuditEntry:
        """Record a CIBA step-up completion (approved or denied)."""
        outcome = (
            TokenAccessOutcome.STEP_UP_APPROVED
            if approved
            else TokenAccessOutcome.STEP_UP_DENIED
        )
        return self._append(
            TokenAccessAuditEntry(
                agent_id=agent_id,
                role=role,
                connection=connection,
                requested_scopes=scopes,
                granted_scopes=scopes if approved else [],
                outcome=outcome,
                step_up_binding_message=binding_message,
                user_id=user_id,
                tool_name=tool_name,
            )
        )

    # ------------------------------------------------------------------
    # Query API
    # ------------------------------------------------------------------

    def get_entries(
        self,
        *,
        agent_id: str | None = None,
        connection: str | None = None,
        outcome: TokenAccessOutcome | None = None,
    ) -> list[TokenAccessAuditEntry]:
        """Return audit entries optionally filtered by agent, connection, or outcome."""
        with self._lock:
            entries = list(self._entries)
        if agent_id:
            entries = [e for e in entries if e.agent_id == agent_id]
        if connection:
            entries = [e for e in entries if e.connection == connection]
        if outcome:
            entries = [e for e in entries if e.outcome == outcome]
        return entries

    def to_jsonl(self) -> str:
        """Serialize all entries to newline-delimited JSON."""
        with self._lock:
            entries = list(self._entries)
        return "\n".join(e.to_json() for e in entries)

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _append(self, entry: TokenAccessAuditEntry) -> TokenAccessAuditEntry:
        with self._lock:
            self._entries.append(entry)

        # Emit to structlog if configured
        if self._emit_structlog and self._structlog_available:
            import structlog

            structlog.get_logger("acgs_auth0.audit").info(
                "token_vault_access",
                **entry.to_dict(),
            )
        else:
            logger.info(
                "token_vault_access agent=%s role=%s connection=%s outcome=%s",
                entry.agent_id,
                entry.role,
                entry.connection,
                entry.outcome.value,
            )

        # Append to JSONL file if configured
        if self._file_path:
            try:
                with self._file_path.open("a") as fh:
                    fh.write(entry.to_json() + "\n")
            except OSError as exc:
                logger.error("Failed to write audit entry to %s: %s", self._file_path, exc)

        return entry
