"""
Presence Manager for Real-time Collaboration.

Tracks active users per document, cursor positions, user activity status,
and "user is editing" indicators.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.collaboration.models import (
    CollaborationConfig,
    CollaborationSession,
    Collaborator,
    CursorPosition,
    PresenceStatus,
    SessionFullError,
    UserPermissions,
)
from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)

PRESENCE_CALLBACK_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
)
CLEANUP_LOOP_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    ConnectionError,
    OSError,
)


class PresenceManager:
    """
    Manages user presence in collaborative sessions.

    Handles:
    - User join/leave events
    - Cursor position tracking
    - Activity status updates
    - Idle timeout management
    """

    def __init__(
        self,
        config: CollaborationConfig | None = None,
        redis_client: object | None = None,
    ):
        self.config = config or CollaborationConfig()
        self.redis = redis_client
        self._sessions: dict[str, CollaborationSession] = {}
        self._user_sessions: dict[str, set[str]] = {}  # user_id -> set of session_ids
        self._lock = asyncio.Lock()
        self._callbacks: list[Callable[[str, str, JSONDict], None]] = []
        self._cleanup_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the presence manager background tasks."""
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("Presence manager started")

    async def stop(self) -> None:
        """Stop the presence manager."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        logger.info("Presence manager stopped")

    async def join_session(
        self,
        document_id: str,
        document_type: str,
        user_id: str,
        user_info: JSONDict,
        tenant_id: str,
    ) -> tuple[CollaborationSession, Collaborator]:
        """
        Add a user to a collaborative session.

        Args:
            document_id: Document being edited
            document_type: Type of document
            user_id: User joining
            user_info: User metadata (name, avatar, etc.)
            tenant_id: Tenant for isolation

        Returns:
            Tuple of (session, collaborator)

        Raises:
            SessionFullError: If session is at capacity
        """
        async with self._lock:
            # Get or create session
            session = self._sessions.get(document_id)
            if not session:
                from enhanced_agent_bus.collaboration.models import DocumentType

                session = CollaborationSession(
                    document_id=document_id,
                    document_type=DocumentType(document_type),
                    tenant_id=tenant_id,
                    max_users=self.config.max_users_per_document,
                )
                self._sessions[document_id] = session
                logger.info(
                    "New collaboration session created",
                    extra={"document_id": document_id, "tenant_id": tenant_id},
                )

            # Check capacity
            if not session.can_join():
                raise SessionFullError(
                    f"Session for {document_id} is at capacity ({session.max_users} users)"
                )

            # Check tenant isolation
            if session.tenant_id != tenant_id:
                logger.error(
                    "Tenant isolation violation",
                    extra={
                        "document_id": document_id,
                        "session_tenant": session.tenant_id,
                        "user_tenant": tenant_id,
                    },
                )
                raise PermissionError("Tenant mismatch")

            # Create collaborator
            collaborator = Collaborator(
                user_id=user_id,
                name=user_info.get("name", "Anonymous"),
                email=user_info.get("email"),
                avatar=user_info.get("avatar"),
                color=user_info.get("color", self._assign_color(session)),
                permissions=user_info.get("permissions", UserPermissions.READ),
                tenant_id=tenant_id,
                is_anonymous=user_info.get("is_anonymous", False),
            )

            # Add to session
            session.users[collaborator.client_id] = collaborator
            session.update_activity()

            # Track user's sessions
            if user_id not in self._user_sessions:
                self._user_sessions[user_id] = set()
            self._user_sessions[user_id].add(document_id)

            # Notify callbacks
            await self._notify_callbacks(
                "user_joined",
                document_id,
                {
                    "user_id": user_id,
                    "client_id": collaborator.client_id,
                    "name": collaborator.name,
                    "color": collaborator.color,
                },
            )

            logger.info(
                "User joined session",
                extra={
                    "document_id": document_id,
                    "user_id": user_id,
                    "client_id": collaborator.client_id,
                    "total_users": len(session.users),
                },
            )

            return session, collaborator

    async def leave_session(self, document_id: str, client_id: str) -> Collaborator | None:
        """
        Remove a user from a collaborative session.

        Args:
            document_id: Document being edited
            client_id: Client session ID

        Returns:
            The removed collaborator, or None if not found
        """
        async with self._lock:
            session = self._sessions.get(document_id)
            if not session:
                return None

            collaborator = session.users.pop(client_id, None)
            if collaborator:
                # Remove from user sessions tracking
                user_id = collaborator.user_id
                if user_id in self._user_sessions:
                    self._user_sessions[user_id].discard(document_id)
                    if not self._user_sessions[user_id]:
                        del self._user_sessions[user_id]

                # Notify callbacks
                await self._notify_callbacks(
                    "user_left",
                    document_id,
                    {
                        "user_id": user_id,
                        "client_id": client_id,
                        "name": collaborator.name,
                    },
                )

                logger.info(
                    "User left session",
                    extra={
                        "document_id": document_id,
                        "user_id": user_id,
                        "client_id": client_id,
                        "remaining_users": len(session.users),
                    },
                )

                # Clean up empty sessions
                if not session.users:
                    del self._sessions[document_id]
                    logger.info(
                        "Empty session removed",
                        extra={"document_id": document_id},
                    )

            return collaborator

    async def update_cursor(
        self,
        document_id: str,
        client_id: str,
        cursor: CursorPosition,
    ) -> bool:
        """
        Update cursor position for a user.

        Args:
            document_id: Document being edited
            client_id: Client session ID
            cursor: New cursor position

        Returns:
            True if updated
        """
        async with self._lock:
            session = self._sessions.get(document_id)
            if not session:
                return False

            collaborator = session.users.get(client_id)
            if not collaborator:
                return False

            collaborator.cursor = cursor
            collaborator.last_activity = datetime.now(UTC)
            session.update_activity()

            # Notify callbacks (throttled in production)
            await self._notify_callbacks(
                "cursor_moved",
                document_id,
                {
                    "client_id": client_id,
                    "user_id": collaborator.user_id,
                    "cursor": cursor.model_dump(),
                },
            )

            return True

    async def update_status(
        self,
        document_id: str,
        client_id: str,
        status: PresenceStatus,
    ) -> bool:
        """
        Update user activity status.

        Args:
            document_id: Document being edited
            client_id: Client session ID
            status: New status

        Returns:
            True if updated
        """
        async with self._lock:
            session = self._sessions.get(document_id)
            if not session:
                return False

            collaborator = session.users.get(client_id)
            if not collaborator:
                return False

            old_status = collaborator.status
            collaborator.status = status
            collaborator.last_activity = datetime.now(UTC)

            if old_status != status:
                await self._notify_callbacks(
                    "status_changed",
                    document_id,
                    {
                        "client_id": client_id,
                        "user_id": collaborator.user_id,
                        "old_status": old_status.value,
                        "new_status": status.value,
                    },
                )

            return True

    async def set_typing(self, document_id: str, client_id: str, is_typing: bool) -> bool:
        """
        Set typing indicator for a user.

        Args:
            document_id: Document being edited
            client_id: Client session ID
            is_typing: Whether user is typing

        Returns:
            True if updated
        """
        status = PresenceStatus.TYPING if is_typing else PresenceStatus.ACTIVE
        return await self.update_status(document_id, client_id, status)

    async def get_session(self, document_id: str) -> CollaborationSession | None:
        """Get session by document ID."""
        return self._sessions.get(document_id)

    async def get_collaborator(self, document_id: str, client_id: str) -> Collaborator | None:
        """Get collaborator by client ID."""
        session = self._sessions.get(document_id)
        if session:
            return session.users.get(client_id)
        return None

    async def get_active_users(self, document_id: str) -> list[Collaborator]:
        """Get list of active (non-away) users in a session."""
        session = self._sessions.get(document_id)
        if not session:
            return []
        return session.get_active_users()

    async def get_all_users(self, document_id: str) -> list[Collaborator]:
        """Get all users in a session."""
        session = self._sessions.get(document_id)
        if not session:
            return []
        return list(session.users.values())

    async def get_user_sessions(self, user_id: str) -> list[str]:
        """Get all document IDs where user is active."""
        return list(self._user_sessions.get(user_id, set()))

    def register_callback(self, callback: Callable[[str, str, JSONDict], None]) -> None:
        """
        Register a callback for presence events.

        Args:
            callback: Function called with (event_type, document_id, data)
        """
        self._callbacks.append(callback)

    def unregister_callback(self, callback: Callable[[str, str, JSONDict], None]) -> None:
        """Unregister a callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    async def _notify_callbacks(self, event_type: str, document_id: str, data: JSONDict) -> None:
        """Notify all registered callbacks."""
        for callback in self._callbacks:
            try:
                if inspect.iscoroutinefunction(callback):
                    await callback(event_type, document_id, data)
                else:
                    callback(event_type, document_id, data)
            except PRESENCE_CALLBACK_ERRORS as e:
                logger.error(f"Callback error: {e}")

    def _assign_color(self, session: CollaborationSession) -> str:
        """Assign a unique color to a new collaborator."""
        # Predefined collaboration colors
        colors = [
            "#FF6B6B",  # Red
            "#4ECDC4",  # Teal
            "#45B7D1",  # Blue
            "#96CEB4",  # Green
            "#FFEEAD",  # Yellow
            "#D4A5A5",  # Pink
            "#9B59B6",  # Purple
            "#3498DB",  # Blue
            "#E67E22",  # Orange
            "#1ABC9C",  # Turquoise
        ]

        used_colors = {u.color for u in session.users.values()}
        available = [c for c in colors if c not in used_colors]

        if available:
            return available[0]

        # If all colors used, cycle through
        index = len(session.users) % len(colors)
        return colors[index]

    async def _cleanup_loop(self) -> None:
        """Background task to clean up idle users."""
        while True:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds
                await self._check_idle_users()
            except asyncio.CancelledError:
                break
            except CLEANUP_LOOP_ERRORS as e:
                logger.error(f"Cleanup loop error: {e}")

    async def _check_idle_users(self) -> None:
        """Check for and mark idle users."""
        now = datetime.now(UTC)
        idle_timeout = timedelta(seconds=self.config.idle_timeout_seconds)
        away_timeout = timedelta(seconds=self.config.away_timeout_seconds)

        async with self._lock:
            for document_id, session in self._sessions.items():
                for client_id, collaborator in list(session.users.items()):
                    inactive_time = now - collaborator.last_activity

                    if inactive_time > away_timeout:
                        # Mark as away
                        if collaborator.status != PresenceStatus.AWAY:
                            collaborator.status = PresenceStatus.AWAY
                            await self._notify_callbacks(
                                "status_changed",
                                document_id,
                                {
                                    "client_id": client_id,
                                    "user_id": collaborator.user_id,
                                    "new_status": PresenceStatus.AWAY.value,
                                },
                            )
                    elif inactive_time > idle_timeout:
                        # Mark as idle
                        if collaborator.status == PresenceStatus.ACTIVE:
                            collaborator.status = PresenceStatus.IDLE
                            await self._notify_callbacks(
                                "status_changed",
                                document_id,
                                {
                                    "client_id": client_id,
                                    "user_id": collaborator.user_id,
                                    "new_status": PresenceStatus.IDLE.value,
                                },
                            )

    async def broadcast_to_session(
        self,
        document_id: str,
        message_type: str,
        data: JSONDict,
        exclude_client: str | None = None,
    ) -> int:
        """
        Broadcast a message to all users in a session.

        Args:
            document_id: Target session
            message_type: Type of message
            data: Message payload
            exclude_client: Optional client ID to exclude

        Returns:
            Number of recipients
        """
        session = self._sessions.get(document_id)
        if not session:
            return 0

        recipients = 0
        for client_id in session.users:
            if client_id != exclude_client:
                recipients += 1

        await self._notify_callbacks(
            "broadcast",
            document_id,
            {
                "type": message_type,
                "data": data,
                "exclude_client": exclude_client,
                "recipients": recipients,
            },
        )

        return recipients

    async def is_user_active(self, user_id: str, document_id: str) -> bool:
        """Check if a user is active in a specific document session."""
        session = self._sessions.get(document_id)
        if not session:
            return False

        for collaborator in session.users.values():
            if collaborator.user_id == user_id:
                return collaborator.status != PresenceStatus.AWAY

        return False

    async def get_session_stats(self, document_id: str) -> JSONDict:
        """Get statistics for a session."""
        session = self._sessions.get(document_id)
        if not session:
            return {"exists": False}

        status_counts = {}
        for collaborator in session.users.values():
            status = collaborator.status.value
            status_counts[status] = status_counts.get(status, 0) + 1

        return {
            "exists": True,
            "document_id": document_id,
            "total_users": len(session.users),
            "status_counts": status_counts,
            "version": session.version,
            "is_locked": session.is_locked,
            "locked_by": session.locked_by,
            "created_at": session.created_at.isoformat(),
            "last_activity": session.last_activity.isoformat(),
        }

    async def get_all_sessions(self) -> list[JSONDict]:
        """Get stats for all active sessions."""
        return [await self.get_session_stats(doc_id) for doc_id in self._sessions.keys()]
