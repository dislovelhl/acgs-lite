"""
Collaboration WebSocket Server.

Socket.io server for real-time collaboration with:
- Room management per document
- Authentication middleware
- Rate limiting
- Connection health monitoring

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Protocol, cast

from enhanced_agent_bus._compat.security.cors_config import get_cors_config
from enhanced_agent_bus._compat.security.rate_limiter import SlidingWindowRateLimiter

try:
    from enhanced_agent_bus._compat.types import (
        JSONDict,
        JSONValue,
    )
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]
    JSONValue = object  # type: ignore[misc,assignment]

from enhanced_agent_bus.collaboration.models import (
    ActivityEventType,
    ChatMessage,
    CollaborationConfig,
    CollaborationValidationError,
    Comment,
    ConflictError,
    CursorPosition,
    EditOperation,
    PermissionDeniedError,
    SessionFullError,
    UserPermissions,
)
from enhanced_agent_bus.collaboration.permissions import PermissionController
from enhanced_agent_bus.collaboration.presence import PresenceManager
from enhanced_agent_bus.collaboration.sync_engine import SyncEngine
from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)

SessionData = dict[str, JSONValue]
EventPayload = dict[str, JSONValue]
COLLABORATION_HANDLER_ERRORS = (
    AttributeError,
    KeyError,
    LookupError,
    RuntimeError,
    TypeError,
    ValueError,
)


class SupportsAuditClient(Protocol):
    """Protocol for audit clients used by collaboration server."""

    async def log_event(self, event_type: str, details: EventPayload) -> None: ...


class SocketServerProtocol(Protocol):
    """Protocol for socket.io async server surface used by this module."""

    def event(self, handler: Callable[..., object]) -> Callable[..., object]: ...

    async def save_session(self, sid: str, session: SessionData) -> None: ...

    async def get_session(self, sid: str) -> SessionData | None: ...

    async def leave_room(self, sid: str, room: str) -> None: ...

    async def enter_room(self, sid: str, room: str) -> None: ...

    async def emit(
        self,
        event: str,
        data: EventPayload,
        room: str | None = None,
        skip_sid: str | None = None,
    ) -> None: ...


class RateLimiter:
    """Compatibility adapter around the canonical shared sliding-window limiter."""

    def __init__(
        self,
        max_requests: int = 100,
        window_seconds: int = 60,
        redis_client: object | None = None,
        key_prefix: str = "collaboration",
    ):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._limiter = SlidingWindowRateLimiter(
            redis_client=redis_client,
            fallback_to_memory=True,
            key_prefix=key_prefix,
        )

    async def is_allowed(self, client_id: str) -> bool:
        """Check if request is within rate limit."""
        result = await self._limiter.is_allowed(
            key=client_id,
            limit=self.max_requests,
            window_seconds=self.window_seconds,
        )
        return result.allowed  # type: ignore[no-any-return]

    async def get_remaining(self, client_id: str) -> int:
        """Get remaining requests in current window."""
        async with self._limiter._lock:
            now = time.time()
            window_start = now - self.window_seconds
            requests = self._limiter.local_windows.get(client_id, [])
            requests = [r for r in requests if r > window_start]
            self._limiter.local_windows[client_id] = requests
            return max(0, self.max_requests - len(requests))

    async def reset_prefix(self, prefix: str) -> None:
        """Remove in-memory limiter state for keys belonging to a disconnected session."""
        async with self._limiter._lock:
            keys_to_remove = [
                key
                for key in self._limiter.local_windows
                if key == prefix or key.startswith(f"{prefix}:")
            ]
            for key in keys_to_remove:
                del self._limiter.local_windows[key]


class CollaborationServer:
    """
    Socket.io server for real-time collaboration.

    Manages WebSocket connections, handles events, and coordinates
    between presence, sync, and permission components.
    """

    def __init__(
        self,
        config: CollaborationConfig | None = None,
        redis_client: object | None = None,
        audit_client: SupportsAuditClient | None = None,
        auth_validator: Callable[[str], SessionData | None] | None = None,
    ):
        self.config = config or CollaborationConfig()
        self.redis = redis_client
        self.audit_client = audit_client
        self.auth_validator = auth_validator

        # Core components
        self.presence = PresenceManager(config, redis_client)
        self.sync = SyncEngine(redis_client)
        self.permissions = PermissionController(audit_client)
        self.rate_limiter = RateLimiter(redis_client=redis_client)

        # Socket.io server (initialized later)
        self.sio: SocketServerProtocol | None = None
        self._started = False

    async def initialize(self) -> None:
        """Initialize the Socket.io server."""
        try:
            import socketio

            cors_origins = get_cors_config(allow_credentials=False).get("allow_origins", [])
            self.sio = socketio.AsyncServer(
                async_mode="asgi",
                cors_allowed_origins=cors_origins,
                logger=False,
                engineio_logger=False,
            )

            # Register event handlers
            self._register_handlers()

            # Start presence manager
            await self.presence.start()

            # Register presence callback
            self.presence.register_callback(self._on_presence_event)

            self._started = True
            logger.info("Collaboration server initialized")

        except ImportError:
            logger.error("python-socketio not installed")
            raise

    async def shutdown(self) -> None:
        """Shutdown the server gracefully."""
        if self._started:
            await self.presence.stop()
            self._started = False
            logger.info("Collaboration server shutdown")

    def _register_handlers(self) -> None:
        """Register all Socket.io event handlers."""
        self._register_connection_handlers()
        self._register_document_handlers()
        self._register_edit_handlers()
        self._register_social_handlers()

    def _register_handlers_from_table(self, handlers: list[tuple[str, Callable]]) -> None:
        """Register handlers from a table of event names and handler functions."""
        for event_name, handler in handlers:
            # Create a wrapper that captures both handler and event_name properly
            def create_wrapper(h, name):
                async def wrapper(sid: str, data: JSONDict | None = None):
                    return await h(sid, data or {})

                wrapper.__name__ = name
                return wrapper

            # Register the wrapper
            self.sio.event(create_wrapper(handler, event_name))

    # ------------------------------------------------------------------
    # Connection handlers (connect / disconnect)
    # ------------------------------------------------------------------

    def _register_connection_handlers(self) -> None:
        """Register connection lifecycle handlers."""

        @self.sio.event
        async def connect(sid: str, environ: JSONDict, auth: JSONDict | None = None) -> bool:
            """Handle new connection."""
            logger.debug(f"Client connecting: {sid}")

            # Validate auth token
            token = auth.get("token") if auth else None
            if not token:
                logger.warning(f"Connection rejected - no auth token: {sid}")
                return False

            if not self.auth_validator:
                logger.warning(f"Connection rejected - no auth_validator configured: {sid}")
                return False

            user_data = self.auth_validator(token)
            if not user_data:
                logger.warning(f"Connection rejected - invalid token: {sid}")
                return False

            # Store user data in session
            await self.sio.save_session(
                sid,
                cast(
                    SessionData,
                    {
                        "user_id": user_data["user_id"],
                        "tenant_id": user_data.get("tenant_id"),
                        "permissions": user_data.get("permissions", []),
                    },
                ),
            )

            logger.info(f"Client connected: {sid}")
            return True

        @self.sio.event
        async def disconnect(sid: str) -> None:
            """Handle disconnection."""
            session = await self.sio.get_session(sid)
            document_id = session.get("document_id") if session else None
            client_id = session.get("client_id") if session else None

            if document_id and client_id:
                await self.presence.leave_session(document_id, client_id)
                await self.sio.leave_room(sid, document_id)

            # Clean up rate limiter entries for this session
            await self._cleanup_rate_limiter(sid)

            logger.info(f"Client disconnected: {sid}")

    # ------------------------------------------------------------------
    # Document handlers (join / leave)
    # ------------------------------------------------------------------

    def _register_document_handlers(self) -> None:
        """Register document lifecycle handlers."""
        handlers = [
            ("join_document", self._handle_join_document),
            ("leave_document", self._handle_leave_document),
        ]
        self._register_handlers_from_table(handlers)

    async def _handle_join_document(self, sid: str, data: JSONDict) -> JSONDict:
        """Handle join document request."""
        try:
            # Rate limit check
            if not await self.rate_limiter.is_allowed(sid):
                return {"error": "Rate limit exceeded", "code": "RATE_LIMITED"}

            # Session validation
            session = await self.sio.get_session(sid)
            if not session:
                return {"error": "Session not found", "code": "NO_SESSION"}

            # Extract and validate request data
            document_id = data.get("document_id")
            document_type = data.get("document_type", "policy")
            if not document_id:
                return {"error": "Document ID required", "code": "MISSING_DOC_ID"}

            # Tenant validation
            tenant_id = session.get("tenant_id")
            user_id = session.get("user_id")
            if not tenant_id:
                return {"error": "Tenant required", "code": "MISSING_TENANT"}

            # Join collaboration session
            try:
                collab_session, collaborator = await self._join_collaboration_session(
                    document_id, document_type, user_id, data, tenant_id
                )
            except SessionFullError as e:
                return {"error": str(e), "code": "SESSION_FULL"}

            # Update WebSocket session and join room
            await self._update_session_and_join_room(sid, session, document_id, collaborator)

            # Get document state and notify participants
            document = await self.sync.get_document(document_id)
            users = await self.presence.get_all_users(document_id)
            await self._notify_user_joined(sid, document_id, collaborator)

            # Log activity
            await self._log_activity(
                ActivityEventType.USER_JOINED,
                user_id,
                document_id,
                {"collaborator": collaborator.to_dict()},
            )

            return {
                "success": True,
                "client_id": collaborator.client_id,
                "color": collaborator.color,
                "document": document,
                "users": [u.to_dict() for u in users],
                "version": collab_session.version,
            }

        except COLLABORATION_HANDLER_ERRORS as e:
            logger.error("Join document error: %s", e, exc_info=True)
            return {"error": "An internal error occurred", "code": "INTERNAL_ERROR"}

    async def _handle_leave_document(self, sid: str, data: JSONDict | None = None) -> JSONDict:
        """Handle leave document request."""
        session = await self.sio.get_session(sid)
        if not session:
            return {"success": False}

        document_id = session.get("document_id")
        client_id = session.get("client_id")

        if document_id and client_id:
            collaborator = await self.presence.leave_session(document_id, client_id)
            await self.sio.leave_room(sid, document_id)

            if collaborator:
                await self.sio.emit(
                    "user-left",
                    {
                        "user_id": collaborator.user_id,
                        "client_id": client_id,
                        "name": collaborator.name,
                    },
                    room=document_id,
                )

        return {"success": True}

    async def _join_collaboration_session(
        self, document_id: str, document_type: str, user_id: str, data: JSONDict, tenant_id: str
    ) -> tuple[object, object]:
        """Join the collaboration session."""
        server_permission = self.permissions.get_document_permissions(document_id).get(
            user_id,
            UserPermissions.READ,
        )
        return await self.presence.join_session(
            document_id=document_id,
            document_type=document_type,
            user_id=user_id,
            user_info={
                "name": data.get("name", "Anonymous"),
                "email": data.get("email"),
                "avatar": data.get("avatar"),
                "color": data.get("color"),
                "permissions": server_permission,
            },
            tenant_id=tenant_id,
        )

    async def _update_session_and_join_room(
        self, sid: str, session: SessionData, document_id: str, collaborator: object
    ) -> None:
        """Update session data and join WebSocket room."""
        await self.sio.save_session(
            sid,
            {
                **session,
                "document_id": document_id,
                "client_id": collaborator.client_id,
            },
        )
        await self.sio.enter_room(sid, document_id)

    async def _notify_user_joined(self, sid: str, document_id: str, collaborator: object) -> None:
        """Notify other users that a user joined."""
        await self.sio.emit(
            "user-joined",
            {
                "user_id": collaborator.user_id,
                "client_id": collaborator.client_id,
                "name": collaborator.name,
                "color": collaborator.color,
                "avatar": collaborator.avatar,
            },
            room=document_id,
            skip_sid=sid,
        )

    # ------------------------------------------------------------------
    # Edit handlers (cursor, edit operations)
    # ------------------------------------------------------------------

    def _register_edit_handlers(self) -> None:
        """Register editing and cursor handlers."""
        handlers = [
            ("cursor_move", self._handle_cursor_move),
            ("edit_operation", self._handle_edit_operation),
        ]
        self._register_handlers_from_table(handlers)

    async def _handle_cursor_move(self, sid: str, data: JSONDict) -> JSONDict:
        """Handle cursor movement."""
        session = await self.sio.get_session(sid)
        if not session:
            return {"error": "No session"}

        document_id = session.get("document_id")
        client_id = session.get("client_id")

        if not document_id or not client_id:
            return {"error": "Not in document"}

        cursor_data = data.get("cursor", {})
        cursor = self._create_cursor_position(cursor_data)

        success = await self.presence.update_cursor(document_id, client_id, cursor)

        if success:
            await self._broadcast_cursor_update(sid, document_id, client_id, cursor_data)

        return {"success": success}

    async def _handle_edit_operation(self, sid: str, data: JSONDict) -> JSONDict:
        """Handle edit operation."""
        try:
            # Session validation
            session = await self.sio.get_session(sid)
            if not session:
                return {"error": "No session", "code": "NO_SESSION"}

            document_id = session.get("document_id")
            client_id = session.get("client_id")
            user_id = session.get("user_id")

            if not document_id or not client_id:
                return {"error": "Not in document", "code": "NOT_IN_DOCUMENT"}

            # Rate limiting and permissions
            rate_limit_error = await self._check_edit_rate_limit(sid)
            if rate_limit_error:
                return rate_limit_error

            permission_error = await self._check_edit_permissions(user_id, document_id)
            if permission_error:
                return permission_error

            # Session and lock validation
            collab_session = await self.presence.get_session(document_id)
            if not collab_session:
                return {"error": "Session not found", "code": "SESSION_NOT_FOUND"}

            lock_error = self._check_document_lock(collab_session, user_id)
            if lock_error:
                return lock_error

            # Create and validate operation
            operation = self._create_edit_operation(data, user_id, client_id, collab_session)

            validation_error = await self._validate_edit_operation(
                user_id, document_id, operation, data
            )
            if validation_error:
                return validation_error

            # Apply operation and broadcast
            try:
                applied_op = await self.sync.apply_operation(document_id, operation, collab_session)
            except ConflictError as e:
                return {"error": str(e), "code": "CONFLICT"}

            await self._broadcast_document_update(
                sid, document_id, applied_op, user_id, client_id, collab_session
            )

            # Log activity
            await self._log_activity(
                ActivityEventType.DOCUMENT_EDITED,
                user_id,
                document_id,
                {"operation_id": applied_op.operation_id},
            )

            return {
                "success": True,
                "operation_id": applied_op.operation_id,
                "version": collab_session.version,
            }

        except COLLABORATION_HANDLER_ERRORS as e:
            logger.error("Edit operation error: %s", e, exc_info=True)
            return {"error": "An internal error occurred", "code": "INTERNAL_ERROR"}

    def _create_cursor_position(self, cursor_data: JSONDict) -> CursorPosition:
        """Create cursor position from data."""
        return CursorPosition(
            x=cursor_data.get("x", 0),
            y=cursor_data.get("y", 0),
            line=cursor_data.get("line"),
            column=cursor_data.get("column"),
            selection_start=cursor_data.get("selection_start"),
            selection_end=cursor_data.get("selection_end"),
            node_id=cursor_data.get("node_id"),
        )

    async def _broadcast_cursor_update(
        self, sid: str, document_id: str, client_id: str, cursor_data: JSONDict
    ) -> None:
        """Broadcast cursor update to other users."""
        collaborator = await self.presence.get_collaborator(document_id, client_id)
        if collaborator:
            await self.sio.emit(
                "cursor-update",
                {
                    "client_id": client_id,
                    "user_id": collaborator.user_id,
                    "name": collaborator.name,
                    "color": collaborator.color,
                    "cursor": cursor_data,
                },
                room=document_id,
                skip_sid=sid,
            )

    async def _check_edit_rate_limit(self, sid: str) -> JSONDict | None:
        """Check edit rate limit."""
        if not await self.rate_limiter.is_allowed(f"{sid}:edit"):
            return {"error": "Edit rate limit exceeded", "code": "RATE_LIMITED"}
        return None

    async def _check_edit_permissions(self, user_id: str, document_id: str) -> JSONDict | None:
        """Check edit permissions."""
        try:
            await self.permissions.require_edit_permission(user_id, document_id)
            return None
        except PermissionDeniedError as e:
            return {"error": str(e), "code": "PERMISSION_DENIED"}

    def _check_document_lock(self, collab_session: object, user_id: str) -> JSONDict | None:
        """Check if document is locked."""
        if collab_session.is_locked and collab_session.locked_by != user_id:
            return {
                "error": "Document is locked",
                "code": "DOCUMENT_LOCKED",
                "locked_by": collab_session.locked_by,
            }
        return None

    def _create_edit_operation(
        self, data: JSONDict, user_id: str, client_id: str, collab_session: object
    ) -> EditOperation:
        """Create edit operation from data."""
        return EditOperation(
            type=data.get("type", "replace"),
            path=data.get("path", ""),
            value=data.get("value"),
            old_value=data.get("old_value"),
            position=data.get("position"),
            length=data.get("length"),
            user_id=user_id,
            client_id=client_id,
            version=data.get("version", collab_session.version),
            parent_version=data.get("parent_version"),
        )

    async def _validate_edit_operation(
        self, user_id: str, document_id: str, operation: EditOperation, data: JSONDict
    ) -> JSONDict | None:
        """Validate edit operation."""
        try:
            await self.permissions.validate_operation(
                user_id, document_id, operation.type.value, data
            )
            return None
        except (PermissionDeniedError, CollaborationValidationError) as e:
            return {"error": str(e), "code": "VALIDATION_FAILED"}

    async def _broadcast_document_update(
        self,
        sid: str,
        document_id: str,
        applied_op: object,
        user_id: str,
        client_id: str,
        collab_session: object,
    ) -> None:
        """Broadcast document update to other users."""
        await self.sio.emit(
            "document-update",
            {
                "operation": applied_op.to_dict(),
                "user_id": user_id,
                "client_id": client_id,
                "version": collab_session.version,
            },
            room=document_id,
            skip_sid=sid,
        )

    # ------------------------------------------------------------------
    # Social handlers (chat, typing, comments, presence)
    # ------------------------------------------------------------------

    def _register_social_handlers(self) -> None:
        """Register chat, typing, comment, and presence handlers."""
        handlers = [
            ("chat_message", self._handle_chat_message),
            ("typing_indicator", self._handle_typing_indicator),
            ("add_comment", self._handle_add_comment),
            ("get_presence", self._handle_get_presence),
        ]
        self._register_handlers_from_table(handlers)

    async def _handle_chat_message(self, sid: str, data: JSONDict) -> JSONDict:
        """Handle chat message."""
        session = await self.sio.get_session(sid)
        if not session:
            return {"error": "No session"}

        document_id = session.get("document_id")
        user_id = session.get("user_id")

        if not document_id:
            return {"error": "Not in document"}

        if not self.config.enable_chat:
            return {"error": "Chat disabled"}

        collaborator = await self.presence.get_collaborator(
            document_id, session.get("client_id", "")
        )

        message = self._create_chat_message(user_id, collaborator, data)

        await self._broadcast_chat_message(document_id, message)

        return {"success": True, "message_id": message.message_id}

    async def _handle_typing_indicator(self, sid: str, data: JSONDict) -> JSONDict:
        """Handle typing indicator."""
        session = await self.sio.get_session(sid)
        if not session:
            return {"error": "No session"}

        document_id = session.get("document_id")
        client_id = session.get("client_id")

        if not document_id or not client_id:
            return {"error": "Not in document"}

        is_typing = data.get("is_typing", False)
        success = await self.presence.set_typing(document_id, client_id, is_typing)

        if success:
            await self._broadcast_typing_update(sid, document_id, client_id, is_typing)

        return {"success": success}

    async def _handle_add_comment(self, sid: str, data: JSONDict) -> JSONDict:
        """Handle add comment."""
        session = await self.sio.get_session(sid)
        if not session:
            return {"error": "No session"}

        document_id = session.get("document_id")
        user_id = session.get("user_id")

        if not document_id:
            return {"error": "Not in document"}

        if not self.config.enable_comments:
            return {"error": "Comments disabled"}

        collaborator = await self.presence.get_collaborator(
            document_id, session.get("client_id", "")
        )

        comment = self._create_comment(user_id, collaborator, data)

        await self._broadcast_comment_added(document_id, comment, data.get("position"))

        await self._log_activity(
            ActivityEventType.COMMENT_ADDED,
            user_id,
            document_id,
            {"comment_id": comment.comment_id},
        )

        return {"success": True, "comment_id": comment.comment_id}

    async def _handle_get_presence(self, sid: str, data: JSONDict | None = None) -> JSONDict:
        """Get current presence state."""
        session = await self.sio.get_session(sid)
        if not session:
            return {"error": "No session"}

        document_id = session.get("document_id")
        if not document_id:
            return {"error": "Not in document"}

        users = await self.presence.get_all_users(document_id)
        return {
            "users": [u.to_dict() for u in users],
        }

    def _create_chat_message(
        self, user_id: str, collaborator: object, data: JSONDict
    ) -> ChatMessage:
        """Create chat message from data."""
        return ChatMessage(
            user_id=user_id,
            user_name=collaborator.name if collaborator else "Unknown",
            user_avatar=collaborator.avatar if collaborator else None,
            text=data.get("text", ""),
            mentions=data.get("mentions", []),
        )

    async def _broadcast_chat_message(self, document_id: str, message: ChatMessage) -> None:
        """Broadcast chat message to room."""
        await self.sio.emit(
            "chat-message",
            {
                "message_id": message.message_id,
                "user_id": message.user_id,
                "user_name": message.user_name,
                "user_avatar": message.user_avatar,
                "text": message.text,
                "timestamp": message.timestamp.isoformat(),
                "mentions": message.mentions,
            },
            room=document_id,
        )

    async def _broadcast_typing_update(
        self, sid: str, document_id: str, client_id: str, is_typing: bool
    ) -> None:
        """Broadcast typing update to room."""
        collaborator = await self.presence.get_collaborator(document_id, client_id)
        if collaborator:
            await self.sio.emit(
                "typing-update",
                {
                    "client_id": client_id,
                    "user_id": collaborator.user_id,
                    "name": collaborator.name,
                    "is_typing": is_typing,
                },
                room=document_id,
                skip_sid=sid,
            )

    def _create_comment(self, user_id: str, collaborator: object, data: JSONDict) -> Comment:
        """Create comment from data."""
        cursor_data = data.get("position")
        position = None
        if cursor_data:
            position = CursorPosition(
                x=cursor_data.get("x", 0),
                y=cursor_data.get("y", 0),
                line=cursor_data.get("line"),
                column=cursor_data.get("column"),
            )

        return Comment(
            user_id=user_id,
            user_name=collaborator.name if collaborator else "Unknown",
            user_avatar=collaborator.avatar if collaborator else None,
            text=data.get("text", ""),
            position=position,
            selection_text=data.get("selection_text"),
            mentions=data.get("mentions", []),
        )

    async def _broadcast_comment_added(
        self, document_id: str, comment: Comment, cursor_data: JSONDict
    ) -> None:
        """Broadcast comment added to room."""
        await self.sio.emit(
            "comment-added",
            {
                "comment_id": comment.comment_id,
                "user_id": comment.user_id,
                "user_name": comment.user_name,
                "text": comment.text,
                "position": cursor_data,
                "timestamp": comment.timestamp.isoformat(),
            },
            room=document_id,
        )

    async def _cleanup_rate_limiter(self, sid: str) -> None:
        """Remove rate limiter entries for a disconnected session."""
        await self.rate_limiter.reset_prefix(sid)

    async def _on_presence_event(self, event_type: str, document_id: str, data: JSONDict) -> None:
        """Handle presence manager events."""
        if event_type == "broadcast":
            # Already handled by individual event emitters
            pass

    async def _log_activity(
        self,
        event_type: ActivityEventType,
        user_id: str,
        document_id: str,
        details: EventPayload,
    ) -> None:
        """Log activity to audit trail."""
        if self.audit_client:
            try:
                await self.audit_client.log_event(
                    event_type=f"collaboration.{event_type.value}",
                    details={
                        "user_id": user_id,
                        "document_id": document_id,
                        **details,
                    },
                )
            except COLLABORATION_HANDLER_ERRORS as e:
                logger.error(f"Failed to log activity: {e}")

    def get_asgi_app(self) -> object:
        """Get ASGI application for mounting."""
        if not self.sio:
            raise RuntimeError("Server not initialized")

        import socketio

        return socketio.ASGIApp(self.sio)

    async def health_check(self) -> JSONDict:
        """Health check endpoint."""
        return {
            "status": "healthy" if self._started else "not_started",
            "active_sessions": len(self.presence._sessions),
            "rate_limit_remaining": await self.rate_limiter.get_remaining("health_check"),
        }
