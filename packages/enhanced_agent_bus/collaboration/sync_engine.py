"""
Document Sync Engine with Operational Transform.

Handles conflict resolution for concurrent edits using Operational Transform (OT)
algorithms. Ensures consistency across all clients while maintaining low latency.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import asyncio
import json
from copy import deepcopy

try:
    from enhanced_agent_bus._compat.types import (
        JSONDict,
        JSONValue,
    )
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]
    JSONValue = object  # type: ignore[misc,assignment]

from enhanced_agent_bus.collaboration.models import (
    CollaborationSession,
    CollaborationValidationError,
    ConflictError,
    EditOperation,
    EditOperationType,
)
from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)

_SYNC_ENGINE_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
    json.JSONDecodeError,
)


class OperationalTransform:
    """
    Operational Transform implementation for conflict-free collaborative editing.

    Transforms concurrent operations so they can be applied in sequence
    while preserving user intent.
    """

    @staticmethod
    def transform_operations(
        op1: EditOperation, op2: EditOperation
    ) -> tuple[EditOperation, EditOperation]:
        """
        Transform two concurrent operations against each other.

        Args:
            op1: First operation (will be applied first)
            op2: Second operation (concurrent with op1)

        Returns:
            Tuple of (transformed_op1, transformed_op2)
            transformed_op2 can be applied after op1
        """
        # If operations target different paths, no transformation needed
        if op1.path != op2.path:
            return op1, op2

        # Transform based on operation types
        if op1.type == EditOperationType.INSERT and op2.type == EditOperationType.INSERT:
            return OperationalTransform._transform_insert_insert(op1, op2)
        elif op1.type == EditOperationType.INSERT and op2.type == EditOperationType.DELETE:
            return OperationalTransform._transform_insert_delete(op1, op2)
        elif op1.type == EditOperationType.DELETE and op2.type == EditOperationType.INSERT:
            op2_t, op1_t = OperationalTransform._transform_insert_delete(op2, op1)
            return op1_t, op2_t
        elif op1.type == EditOperationType.DELETE and op2.type == EditOperationType.DELETE:
            return OperationalTransform._transform_delete_delete(op1, op2)
        elif op1.type == EditOperationType.REPLACE or op2.type == EditOperationType.REPLACE:
            return OperationalTransform._transform_replace(op1, op2)

        # Default: return unchanged
        return op1, op2

    @staticmethod
    def _transform_insert_insert(
        op1: EditOperation, op2: EditOperation
    ) -> tuple[EditOperation, EditOperation]:
        """Transform two concurrent insert operations."""
        if op1.position is None or op2.position is None:
            return op1, op2

        op1_copy = deepcopy(op1)
        op2_copy = deepcopy(op2)

        if op1.position < op2.position:
            # op1 is before op2, adjust op2's position
            value_len = len(str(op1.value)) if op1.value else 1
            op2_copy.position = op2.position + value_len
        elif op1.position > op2.position:
            # op2 is before op1, adjust op1's position
            value_len = len(str(op2.value)) if op2.value else 1
            op1_copy.position = op1.position + value_len
        else:
            # Same position - use timestamp to break tie
            if op1.timestamp <= op2.timestamp:
                value_len = len(str(op1.value)) if op1.value else 1
                op2_copy.position = op2.position + value_len
            else:
                value_len = len(str(op2.value)) if op2.value else 1
                op1_copy.position = op1.position + value_len

        return op1_copy, op2_copy

    @staticmethod
    def _transform_insert_delete(
        op1: EditOperation, op2: EditOperation
    ) -> tuple[EditOperation, EditOperation]:
        """Transform concurrent insert and delete operations."""
        if op1.position is None or op2.position is None:
            return op1, op2

        op1_copy = deepcopy(op1)
        op2_copy = deepcopy(op2)

        if op1.position <= op2.position:
            # Insert is before or at delete position, adjust delete
            value_len = len(str(op1.value)) if op1.value else 1
            op2_copy.position = op2.position + value_len
        else:
            # Delete is before insert, adjust insert
            op1_copy.position = max(0, op1.position - (op2.length or 1))

        return op1_copy, op2_copy

    @staticmethod
    def _transform_delete_delete(
        op1: EditOperation, op2: EditOperation
    ) -> tuple[EditOperation, EditOperation]:
        """Transform two concurrent delete operations."""
        if op1.position is None or op2.position is None:
            return op1, op2

        op1_copy = deepcopy(op1)
        op2_copy = deepcopy(op2)

        len1 = op1.length or 1
        len2 = op2.length or 1

        if op1.position + len1 <= op2.position:
            # op1 is entirely before op2
            op2_copy.position = op2.position - len1
        elif op2.position + len2 <= op1.position:
            # op2 is entirely before op1
            op1_copy.position = op1.position - len2
        else:
            # Overlapping deletes - adjust lengths
            overlap_start = max(op1.position, op2.position)
            overlap_end = min(op1.position + len1, op2.position + len2)
            overlap_len = max(0, overlap_end - overlap_start)

            op1_copy.length = len1 - overlap_len
            op2_copy.length = len2 - overlap_len

        return op1_copy, op2_copy

    @staticmethod
    def _transform_replace(
        op1: EditOperation, op2: EditOperation
    ) -> tuple[EditOperation, EditOperation]:
        """Transform replace operations - replace wins over other ops."""
        # Replace operations typically conflict - use last-write-wins
        if op1.timestamp > op2.timestamp:
            # op1 is newer, op2 becomes no-op
            op2_copy = deepcopy(op2)
            op2_copy.type = EditOperationType.INSERT  # Convert to no-op
            op2_copy.value = None
            return op1, op2_copy
        else:
            # op2 is newer, op1 becomes no-op
            op1_copy = deepcopy(op1)
            op1_copy.type = EditOperationType.INSERT
            op1_copy.value = None
            return op1_copy, op2


class SyncEngine:
    """
    Document synchronization engine.

    Manages document state, applies operations, and ensures consistency
    across all connected clients.
    """

    def __init__(self, redis_client: object | None = None):
        self.redis = redis_client
        self._lock = asyncio.Lock()
        self._documents: dict[str, JSONDict] = {}  # document_id -> content
        self._operation_history: dict[str, list[EditOperation]] = {}  # document_id -> ops
        self._pending_operations: dict[str, list[EditOperation]] = {}  # document_id -> pending
        self.ot = OperationalTransform()

    async def initialize_document(self, document_id: str, initial_content: JSONDict) -> None:
        """Initialize document with initial content."""
        async with self._lock:
            self._documents[document_id] = deepcopy(initial_content)
            self._operation_history[document_id] = []
            self._pending_operations[document_id] = []

            if self.redis:
                await self._persist_to_redis(document_id)

    async def get_document(self, document_id: str) -> JSONDict | None:
        """Get current document content."""
        async with self._lock:
            if document_id in self._documents:
                return deepcopy(self._documents[document_id])

            # Try to load from Redis
            if self.redis:
                return await self._load_from_redis(document_id)

            return None

    async def apply_operation(
        self,
        document_id: str,
        operation: EditOperation,
        session: CollaborationSession,
    ) -> EditOperation:
        """
        Apply an edit operation to the document.

        Args:
            document_id: Target document
            operation: Edit operation to apply
            session: Current collaboration session

        Returns:
            Transformed operation that was applied

        Raises:
            ConflictError: If operation cannot be applied
            CollaborationValidationError: If operation is invalid
        """
        async with self._lock:
            if document_id not in self._documents:
                raise CollaborationValidationError(f"Document {document_id} not found")

            # Transform against concurrent operations
            transformed_op = await self._transform_against_history(document_id, operation)

            # Apply to document
            try:
                self._apply_to_document(document_id, transformed_op)
            except _SYNC_ENGINE_OPERATION_ERRORS as e:
                logger.error(
                    "Failed to apply operation",
                    extra={
                        "document_id": document_id,
                        "operation": operation.operation_id,
                        "error": str(e),
                    },
                )
                raise ConflictError(f"Failed to apply operation: {e}") from e

            # Update history
            self._operation_history[document_id].append(transformed_op)
            session.version += 1

            # Persist
            if self.redis:
                await self._persist_operation(document_id, transformed_op)

            logger.debug(
                "Operation applied",
                extra={
                    "document_id": document_id,
                    "operation_id": transformed_op.operation_id,
                    "version": session.version,
                },
            )

            return transformed_op

    async def _transform_against_history(
        self, document_id: str, operation: EditOperation
    ) -> EditOperation:
        """Transform operation against all operations since its base version."""
        history = self._operation_history.get(document_id, [])

        # Find operations that came after this operation's base version
        concurrent_ops = [
            op for op in history if op.version >= (operation.parent_version or operation.version)
        ]

        transformed = operation
        for concurrent_op in concurrent_ops:
            _, transformed = self.ot.transform_operations(concurrent_op, transformed)

        # Update version
        transformed.version = len(history) + 1
        return transformed

    def _apply_to_document(self, document_id: str, operation: EditOperation) -> None:
        """Apply operation to document content."""
        doc = self._documents[document_id]

        if operation.type == EditOperationType.SET_PROPERTY:
            self._set_property(doc, operation.path, operation.value)
        elif operation.type == EditOperationType.DELETE_PROPERTY:
            self._delete_property(doc, operation.path)
        elif operation.type == EditOperationType.INSERT:
            self._insert_at_path(doc, operation.path, operation.position, operation.value)
        elif operation.type == EditOperationType.DELETE:
            self._delete_at_path(doc, operation.path, operation.position, operation.length)
        elif operation.type == EditOperationType.REPLACE:
            self._set_property(doc, operation.path, operation.value)
        elif operation.type == EditOperationType.MOVE:
            self._move_property(doc, operation.path, operation.value)

    def _set_property(self, doc: JSONDict, path: str, value: JSONValue) -> None:
        """Set a property at a JSON path."""
        parts = path.strip("/").split("/")
        current = doc

        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]

        if parts:
            current[parts[-1]] = deepcopy(value)

    def _delete_property(self, doc: JSONDict, path: str) -> None:
        """Delete a property at a JSON path."""
        parts = path.strip("/").split("/")
        current = doc

        for part in parts[:-1]:
            if part not in current:
                return
            current = current[part]

        if parts and parts[-1] in current:
            del current[parts[-1]]

    def _insert_at_path(
        self, doc: JSONDict, path: str, position: int | None, value: JSONValue
    ) -> None:
        """Insert value at a position within an array."""
        parts = path.strip("/").split("/")
        current = doc

        for part in parts:
            if part not in current:
                current[part] = []
            current = current[part]

        if isinstance(current, list) and position is not None:
            current.insert(min(position, len(current)), deepcopy(value))
        elif isinstance(current, dict):
            if isinstance(value, dict) and "key" in value:
                current[value["key"]] = value.get("value")
            else:
                current[str(len(current))] = deepcopy(value)

    def _delete_at_path(
        self,
        doc: JSONDict,
        path: str,
        position: int | None,
        length: int | None,
    ) -> None:
        """Delete from a position within an array or string."""
        parts = path.strip("/").split("/")
        current = doc

        for part in parts:
            if part not in current:
                return
            current = current[part]

        if isinstance(current, list) and position is not None:
            del_count = length or 1
            for _ in range(del_count):
                if position < len(current):
                    del current[position]

    def _move_property(self, doc: JSONDict, from_path: str, to_path: str | JSONDict) -> None:
        """Move a property from one path to another."""
        value = self._get_property(doc, from_path)
        self._delete_property(doc, from_path)

        if isinstance(to_path, str):
            self._set_property(doc, to_path, value)
        elif isinstance(to_path, dict) and "path" in to_path:
            self._set_property(doc, to_path["path"], value)

    def _get_property(self, doc: JSONDict, path: str) -> JSONValue | None:
        """Get a property at a JSON path."""
        parts = path.strip("/").split("/")
        current = doc

        for part in parts:
            if part not in current:
                return None
            current = current[part]

        return current

    async def batch_apply_operations(
        self,
        document_id: str,
        operations: list[EditOperation],
        session: CollaborationSession,
    ) -> list[EditOperation]:
        """Apply multiple operations atomically."""
        applied = []

        for op in operations:
            try:
                transformed = await self.apply_operation(document_id, op, session)
                applied.append(transformed)
            except _SYNC_ENGINE_OPERATION_ERRORS as e:
                logger.error(
                    "Batch operation failed",
                    extra={
                        "document_id": document_id,
                        "operation_id": op.operation_id,
                        "error": str(e),
                    },
                )
                # Continue with remaining operations

        return applied

    async def undo_last_operation(
        self, document_id: str, session: CollaborationSession
    ) -> EditOperation | None:
        """Undo the last operation."""
        async with self._lock:
            history = self._operation_history.get(document_id, [])
            if not history:
                return None

            last_op = history.pop()

            # Create inverse operation
            inverse = self._create_inverse_operation(last_op)

            # Apply inverse
            self._apply_to_document(document_id, inverse)
            session.version -= 1

            if self.redis:
                await self._persist_to_redis(document_id)

            return last_op

    def _create_inverse_operation(self, operation: EditOperation) -> EditOperation:
        """Create the inverse of an operation for undo."""
        if operation.type == EditOperationType.INSERT:
            return EditOperation(
                type=EditOperationType.DELETE,
                path=operation.path,
                position=operation.position,
                length=len(str(operation.value)) if operation.value else 1,
                user_id=operation.user_id,
                client_id=operation.client_id,
                version=operation.version,
            )
        elif operation.type == EditOperationType.DELETE:
            return EditOperation(
                type=EditOperationType.INSERT,
                path=operation.path,
                position=operation.position,
                value=operation.old_value,
                user_id=operation.user_id,
                client_id=operation.client_id,
                version=operation.version,
            )
        elif operation.type == EditOperationType.SET_PROPERTY:
            if operation.old_value is not None:
                return EditOperation(
                    type=EditOperationType.SET_PROPERTY,
                    path=operation.path,
                    value=operation.old_value,
                    old_value=operation.value,
                    user_id=operation.user_id,
                    client_id=operation.client_id,
                    version=operation.version,
                )
            else:
                return EditOperation(
                    type=EditOperationType.DELETE_PROPERTY,
                    path=operation.path,
                    user_id=operation.user_id,
                    client_id=operation.client_id,
                    version=operation.version,
                )
        elif operation.type == EditOperationType.REPLACE:
            return EditOperation(
                type=EditOperationType.REPLACE,
                path=operation.path,
                value=operation.old_value,
                old_value=operation.value,
                user_id=operation.user_id,
                client_id=operation.client_id,
                version=operation.version,
            )
        else:
            return operation

    async def get_operation_history(
        self, document_id: str, since_version: int = 0
    ) -> list[EditOperation]:
        """Get operation history since a specific version."""
        history = self._operation_history.get(document_id, [])
        return [op for op in history if op.version > since_version]

    async def _persist_to_redis(self, document_id: str) -> None:
        """Persist document state to Redis."""
        if not self.redis:
            return

        try:
            doc = self._documents.get(document_id)
            if doc:
                await self.redis.set(
                    f"collab:doc:{document_id}",
                    json.dumps(doc),
                )
        except _SYNC_ENGINE_OPERATION_ERRORS as e:
            logger.error(f"Failed to persist document to Redis: {e}")

    async def _load_from_redis(self, document_id: str) -> JSONDict | None:
        """Load document state from Redis."""
        if not self.redis:
            return None

        try:
            data = await self.redis.get(f"collab:doc:{document_id}")
            if data:
                return json.loads(data)
        except _SYNC_ENGINE_OPERATION_ERRORS as e:
            logger.error(f"Failed to load document from Redis: {e}")

        return None

    async def _persist_operation(self, document_id: str, operation: EditOperation) -> None:
        """Persist operation to Redis for durability."""
        if not self.redis:
            return

        try:
            await self.redis.lpush(
                f"collab:ops:{document_id}",
                json.dumps(operation.to_dict()),
            )
            # Trim to keep only recent operations
            await self.redis.ltrim(f"collab:ops:{document_id}", 0, 999)
        except _SYNC_ENGINE_OPERATION_ERRORS as e:
            logger.error(f"Failed to persist operation to Redis: {e}")

    async def compact_history(self, document_id: str) -> None:
        """Compact operation history by creating a new snapshot."""
        async with self._lock:
            if document_id not in self._documents:
                return

            # Clear old operations, keeping only recent ones
            history = self._operation_history.get(document_id, [])
            if len(history) > 100:
                self._operation_history[document_id] = history[-50:]

                if self.redis:
                    await self._persist_to_redis(document_id)
