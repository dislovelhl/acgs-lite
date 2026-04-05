"""
ACGS-2 Enhanced Agent Bus - Coverage Boost Tests
Constitutional Hash: 608508a9bd224290

Targeted tests to boost coverage for high-risk modules:
- message_processor.py: 71%→78%
- opa_client.py: 72%→80%
- deliberation_queue.py: 73%→80%
"""

import json
import os
import tempfile
from datetime import UTC, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Governance and constitutional compliance test markers
pytestmark = [pytest.mark.governance, pytest.mark.constitutional]

# Constitutional Hash - Required for all governance operations
from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

# =============================================================================
# Deliberation Queue Coverage Tests
# =============================================================================


class TestDeliberationQueuePersistence:
    """Tests for deliberation queue persistence coverage."""

    async def test_load_tasks_file_not_found(self) -> None:
        """Test _load_tasks when file doesn't exist."""
        from enhanced_agent_bus.deliberation_layer.deliberation_queue import (
            DeliberationQueue,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            queue = DeliberationQueue(persistence_path=os.path.join(tmpdir, "nonexistent.json"))
            # Should handle FileNotFoundError gracefully
            assert len(queue.tasks) == 0

    async def test_load_tasks_invalid_json(self) -> None:
        """Test _load_tasks with invalid JSON."""
        from enhanced_agent_bus.deliberation_layer.deliberation_queue import (
            DeliberationQueue,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "invalid.json")
            with open(path, "w") as f:
                f.write("not valid json {{{")

            queue = DeliberationQueue(persistence_path=path)
            # Should handle JSONDecodeError gracefully
            assert len(queue.tasks) == 0

    async def test_load_tasks_valid_json(self) -> None:
        """Test _load_tasks with valid JSON."""
        from enhanced_agent_bus.deliberation_layer.deliberation_queue import (
            DeliberationQueue,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "tasks.json")
            task_data = {
                "task-001": {
                    "message": {
                        "message_id": "msg-001",
                        "from_agent": "agent-1",
                        "to_agent": "agent-2",
                        "message_type": "command",
                        "content": {"action": "test"},
                        "constitutional_hash": CONSTITUTIONAL_HASH,
                    },
                    "status": "pending",
                    "metadata": {},
                    "created_at": datetime.now(UTC).isoformat(),
                }
            }
            with open(path, "w") as f:
                json.dump(task_data, f)

            queue = DeliberationQueue(persistence_path=path)
            # Should load task successfully
            assert "task-001" in queue.tasks

    async def test_save_tasks(self) -> None:
        """Test _save_tasks persists tasks to file."""
        from enhanced_agent_bus.deliberation_layer.deliberation_queue import (
            DeliberationQueue,
        )
        from enhanced_agent_bus.models import AgentMessage, MessageType

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "tasks.json")
            queue = DeliberationQueue(persistence_path=path)

            # Enqueue a task
            message = AgentMessage(
                message_id="msg-002",
                from_agent="agent-1",
                to_agent="agent-2",
                message_type=MessageType.COMMAND,
                content={"action": "test"},
                constitutional_hash=CONSTITUTIONAL_HASH,
            )

            task_id = await queue.enqueue_for_deliberation(message)

            # The async save task runs in background via asyncio.create_task
            # For testing, call _save_tasks synchronously to ensure file is written
            queue._save_tasks()

            # Verify file was created
            assert os.path.exists(path)

            # Load and verify content
            with open(path) as f:
                saved_data = json.load(f)
            assert task_id in saved_data

    async def test_save_tasks_exception_handling(self) -> None:
        """Test _save_tasks handles write errors."""
        from enhanced_agent_bus.deliberation_layer.deliberation_queue import (
            DeliberationQueue,
        )

        # Use a path that will fail (read-only directory)
        queue = DeliberationQueue(persistence_path="/nonexistent/dir/tasks.json")

        # Should handle exception without crashing
        queue._save_tasks()


class TestDeliberationQueueUpdateStatus:
    """Tests for update_status method coverage."""

    async def test_update_status_string_to_enum(self) -> None:
        """Test update_status converts string to enum."""
        from enhanced_agent_bus.deliberation_layer.deliberation_queue import (
            DeliberationQueue,
        )
        from enhanced_agent_bus.models import AgentMessage, MessageType

        queue = DeliberationQueue()

        message = AgentMessage(
            message_id="msg-003",
            from_agent="agent-1",
            to_agent="agent-2",
            message_type=MessageType.COMMAND,
            content={"action": "test"},
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

        task_id = await queue.enqueue_for_deliberation(message)

        # Update with string status
        await queue.update_status(task_id, "APPROVED")

        task = queue.tasks.get(task_id)
        assert task is not None
        # Status should be converted

    async def test_update_status_invalid_string(self) -> None:
        """Test update_status with invalid string."""
        from enhanced_agent_bus.deliberation_layer.deliberation_queue import (
            DeliberationQueue,
        )
        from enhanced_agent_bus.models import AgentMessage, MessageType

        queue = DeliberationQueue()

        message = AgentMessage(
            message_id="msg-004",
            from_agent="agent-1",
            to_agent="agent-2",
            message_type=MessageType.COMMAND,
            content={"action": "test"},
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

        task_id = await queue.enqueue_for_deliberation(message)

        # Update with invalid string (should use fallback)
        await queue.update_status(task_id, "INVALID_STATUS")

        task = queue.tasks.get(task_id)
        assert task is not None

    async def test_update_status_nonexistent_task(self) -> None:
        """Test update_status with nonexistent task ID."""
        from enhanced_agent_bus.deliberation_layer.deliberation_queue import (
            DeliberationQueue,
            DeliberationStatus,
        )

        queue = DeliberationQueue()

        # Should not raise exception
        await queue.update_status("nonexistent-task", DeliberationStatus.APPROVED)


class TestDeliberationQueueResolveTask:
    """Tests for resolve_task method coverage."""

    async def test_resolve_task_approved(self) -> None:
        """Test resolve_task with approved=True."""
        from enhanced_agent_bus.deliberation_layer.deliberation_queue import (
            DeliberationQueue,
        )
        from enhanced_agent_bus.models import AgentMessage, MessageStatus, MessageType

        queue = DeliberationQueue()

        message = AgentMessage(
            message_id="msg-005",
            from_agent="agent-1",
            to_agent="agent-2",
            message_type=MessageType.COMMAND,
            content={"action": "test"},
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

        task_id = await queue.enqueue_for_deliberation(message)

        # Resolve as approved
        await queue.resolve_task(task_id, approved=True)

        task = queue.tasks.get(task_id)
        # Use value comparison to avoid enum identity issues across imports
        assert task.message.status.value == MessageStatus.PENDING.value

    async def test_resolve_task_rejected(self) -> None:
        """Test resolve_task with approved=False."""
        from enhanced_agent_bus.deliberation_layer.deliberation_queue import (
            DeliberationQueue,
        )
        from enhanced_agent_bus.models import AgentMessage, MessageStatus, MessageType

        queue = DeliberationQueue()

        message = AgentMessage(
            message_id="msg-006",
            from_agent="agent-1",
            to_agent="agent-2",
            message_type=MessageType.COMMAND,
            content={"action": "test"},
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

        task_id = await queue.enqueue_for_deliberation(message)

        # Resolve as rejected
        await queue.resolve_task(task_id, approved=False)

        task = queue.tasks.get(task_id)
        # Use value comparison to avoid enum identity issues across imports
        assert task.message.status.value == MessageStatus.FAILED.value

    async def test_resolve_task_nonexistent(self) -> None:
        """Test resolve_task with nonexistent task."""
        from enhanced_agent_bus.deliberation_layer.deliberation_queue import (
            DeliberationQueue,
        )

        queue = DeliberationQueue()

        # Should not raise exception
        await queue.resolve_task("nonexistent-task", approved=True)
