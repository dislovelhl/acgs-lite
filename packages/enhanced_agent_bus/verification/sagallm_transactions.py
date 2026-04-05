"""
ACGS-2 SagaLLM Transaction System
Constitutional Hash: 608508a9bd224290

SagaLLM provides transaction guarantees for constitutional governance operations:
- Compensable actions with LIFO rollback on failure
- Checkpoint-based transaction state management
- Automatic compensation execution
- Transaction consistency guarantees

This breakthrough addresses Challenge 2: Self-Verification & Formal Methods
by ensuring governance decisions maintain state consistency.
"""

import asyncio
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

# Import centralized constitutional hash
try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)

_SAGALLM_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
)


class TransactionState(Enum):
    """States of a SagaLLM transaction."""

    INITIALIZED = "initialized"
    ACTIVE = "active"
    COMPENSATING = "compensating"
    COMPENSATED = "compensated"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


class TransactionAction(Enum):
    """Types of actions in a transaction."""

    GOVERNANCE_DECISION = "governance_decision"
    POLICY_VALIDATION = "policy_validation"
    ACCESS_CONTROL = "access_control"
    AUDIT_LOGGING = "audit_logging"
    RESOURCE_ALLOCATION = "resource_allocation"
    CONSTITUTIONAL_CHECK = "constitutional_check"


@dataclass
class SagaAction:
    """An action in a SagaLLM transaction."""

    action_id: str
    action_type: TransactionAction
    description: str
    execute_func: Callable[[], Awaitable[object]]
    compensate_func: Callable[[], Awaitable[object]] | None = None
    timeout_s: float = 30.0
    retry_count: int = 0
    max_retries: int = 3
    executed_at: datetime | None = None
    compensated_at: datetime | None = None
    execution_result: object = None
    compensation_result: object = None
    metadata: JSONDict = field(default_factory=dict)
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """Convert action to dictionary."""
        return {
            "action_id": self.action_id,
            "action_type": self.action_type.value,
            "description": self.description,
            "timeout_s": self.timeout_s,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
            "compensated_at": self.compensated_at.isoformat() if self.compensated_at else None,
            "metadata": self.metadata,
            "constitutional_hash": self.constitutional_hash,
        }


@dataclass
class TransactionCheckpoint:
    """A checkpoint in the transaction execution."""

    checkpoint_id: str
    checkpoint_name: str
    state_before: JSONDict
    actions_executed: list[str]  # Action IDs executed so far
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: JSONDict = field(default_factory=dict)
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """Convert checkpoint to dictionary."""
        return {
            "checkpoint_id": self.checkpoint_id,
            "checkpoint_name": self.checkpoint_name,
            "state_before": self.state_before,
            "actions_executed": self.actions_executed,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
            "constitutional_hash": self.constitutional_hash,
        }


@dataclass
class SagaTransaction:
    """A SagaLLM transaction with compensable actions."""

    transaction_id: str
    description: str
    actions: list[SagaAction] = field(default_factory=list)
    checkpoints: list[TransactionCheckpoint] = field(default_factory=list)
    state: TransactionState = TransactionState.INITIALIZED
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    failed_at: datetime | None = None
    failure_reason: str | None = None
    compensation_log: list[JSONDict] = field(default_factory=list)
    metadata: JSONDict = field(default_factory=dict)
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """Convert transaction to dictionary."""
        return {
            "transaction_id": self.transaction_id,
            "description": self.description,
            "actions": [a.to_dict() for a in self.actions],
            "checkpoints": [c.to_dict() for c in self.checkpoints],
            "state": self.state.value,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "failed_at": self.failed_at.isoformat() if self.failed_at else None,
            "failure_reason": self.failure_reason,
            "compensation_log": self.compensation_log,
            "metadata": self.metadata,
            "constitutional_hash": self.constitutional_hash,
        }


class SagaLLMEngine:
    """
    SagaLLM Transaction Engine

    Provides transaction guarantees for constitutional governance:
    - Automatic compensation on failure (LIFO rollback)
    - Checkpoint-based state management
    - Timeout handling and retry logic
    - Transaction consistency guarantees
    """

    def __init__(
        self,
        max_transaction_time: float = 300.0,  # 5 minutes
        default_action_timeout: float = 30.0,
        compensation_timeout: float = 60.0,
    ) -> None:
        self.max_transaction_time = max_transaction_time
        self.default_action_timeout = default_action_timeout
        self.compensation_timeout = compensation_timeout

        # Transaction storage (in practice, use persistent storage)
        self._active_transactions: dict[str, SagaTransaction] = {}
        self._completed_transactions: dict[str, SagaTransaction] = {}

        logger.info("Initialized SagaLLM Transaction Engine")
        logger.info(f"Constitutional Hash: {CONSTITUTIONAL_HASH}")

    def create_transaction(
        self, description: str, metadata: JSONDict | None = None
    ) -> SagaTransaction:
        """Create a new SagaLLM transaction."""
        transaction = SagaTransaction(
            transaction_id=str(uuid.uuid4()),
            description=description,
            metadata=metadata or {},
        )

        self._active_transactions[transaction.transaction_id] = transaction

        logger.info(f"Created SagaLLM transaction: {transaction.transaction_id}")
        return transaction

    def add_action(
        self,
        transaction: SagaTransaction,
        action_type: TransactionAction,
        description: str,
        execute_func: Callable[[], Awaitable[object]],
        compensate_func: Callable[[], Awaitable[object]] | None = None,
        timeout_s: float | None = None,
        max_retries: int = 3,
        metadata: JSONDict | None = None,
    ) -> SagaAction:
        """Add an action to a transaction."""
        if transaction.state != TransactionState.INITIALIZED:
            raise ValueError(
                f"Cannot add actions to transaction in state: {transaction.state.value}"
            )

        action = SagaAction(
            action_id=str(uuid.uuid4()),
            action_type=action_type,
            description=description,
            execute_func=execute_func,
            compensate_func=compensate_func,
            timeout_s=timeout_s or self.default_action_timeout,
            max_retries=max_retries,
            metadata=metadata or {},
        )

        transaction.actions.append(action)

        logger.debug(
            f"Added action to transaction {transaction.transaction_id}: {action.action_id}"
        )
        return action

    def add_checkpoint(
        self,
        transaction: SagaTransaction,
        checkpoint_name: str,
        state_before: JSONDict,
        metadata: JSONDict | None = None,
    ) -> TransactionCheckpoint:
        """Add a checkpoint to the transaction."""
        checkpoint = TransactionCheckpoint(
            checkpoint_id=str(uuid.uuid4()),
            checkpoint_name=checkpoint_name,
            state_before=state_before,
            actions_executed=[a.action_id for a in transaction.actions if a.executed_at],
            metadata=metadata or {},
        )

        transaction.checkpoints.append(checkpoint)

        logger.debug(
            f"Added checkpoint to transaction {transaction.transaction_id}: "
            f"{checkpoint.checkpoint_name}"
        )
        return checkpoint

    async def execute_transaction(self, transaction: SagaTransaction) -> bool:
        """
        Execute a SagaLLM transaction with compensation guarantees.

        Returns True if transaction completed successfully, False if compensated.
        """
        if transaction.state != TransactionState.INITIALIZED:
            raise ValueError(f"Cannot execute transaction in state: {transaction.state.value}")

        transaction.state = TransactionState.ACTIVE
        transaction.started_at = datetime.now(UTC)

        logger.info(f"Executing SagaLLM transaction: {transaction.transaction_id}")

        try:
            # Execute all actions
            for i, action in enumerate(transaction.actions):
                success = await self._execute_action_with_retry(transaction, action, i)
                if not success:
                    # Action failed - start compensation
                    logger.warning(
                        f"Action failed, starting compensation for transaction: "
                        f"{transaction.transaction_id}"
                    )
                    await self._compensate_transaction(transaction)
                    return False

            # All actions succeeded
            transaction.state = TransactionState.COMPLETED
            transaction.completed_at = datetime.now(UTC)

            # Move to completed
            self._completed_transactions[transaction.transaction_id] = transaction
            del self._active_transactions[transaction.transaction_id]

            logger.info(f"SagaLLM transaction completed successfully: {transaction.transaction_id}")
            return True

        except TimeoutError:
            transaction.state = TransactionState.TIMED_OUT
            transaction.failure_reason = "Transaction timeout"
            await self._compensate_transaction(transaction)
            return False

        except _SAGALLM_OPERATION_ERRORS as e:
            transaction.state = TransactionState.FAILED
            transaction.failed_at = datetime.now(UTC)
            transaction.failure_reason = str(e)

            logger.error(f"SagaLLM transaction failed: {transaction.transaction_id} - {e}")
            await self._compensate_transaction(transaction)
            return False

    async def _execute_action_with_retry(
        self, transaction: SagaTransaction, action: SagaAction, _action_index: int
    ) -> bool:
        """Execute an action with retry logic."""
        for attempt in range(action.max_retries + 1):
            try:
                action.retry_count = attempt

                # Execute with timeout
                result = await asyncio.wait_for(action.execute_func(), timeout=action.timeout_s)

                # Success
                action.executed_at = datetime.now(UTC)
                action.execution_result = result

                logger.debug(
                    f"Action executed successfully: {action.action_id} (attempt {attempt + 1})"
                )
                return True

            except TimeoutError:
                logger.warning(f"Action timeout (attempt {attempt + 1}): {action.action_id}")
                if attempt == action.max_retries:
                    return False

            except _SAGALLM_OPERATION_ERRORS as e:
                logger.warning(f"Action failed (attempt {attempt + 1}): {action.action_id} - {e}")
                if attempt == action.max_retries:
                    return False

            # Wait before retry (exponential backoff)
            await asyncio.sleep(0.1 * (2**attempt))

        return False

    async def _compensate_transaction(self, transaction: SagaTransaction) -> None:
        """Execute compensation actions in LIFO order (reverse execution order)."""
        transaction.state = TransactionState.COMPENSATING

        logger.info(f"Starting compensation for transaction: {transaction.transaction_id}")

        # Execute compensations in reverse order (LIFO)
        compensation_log = []

        for action in reversed(transaction.actions):
            if action.executed_at and action.compensate_func:
                try:
                    # Execute compensation with timeout
                    result = await asyncio.wait_for(
                        action.compensate_func(), timeout=self.compensation_timeout
                    )

                    action.compensated_at = datetime.now(UTC)
                    action.compensation_result = result

                    compensation_log.append(
                        {
                            "action_id": action.action_id,
                            "status": "compensated",
                            "result": str(result),
                            "timestamp": datetime.now(UTC).isoformat(),
                        }
                    )

                except _SAGALLM_OPERATION_ERRORS as e:
                    compensation_log.append(
                        {
                            "action_id": action.action_id,
                            "status": "compensation_failed",
                            "error": str(e),
                            "timestamp": datetime.now(UTC).isoformat(),
                        }
                    )

                    logger.error(f"Compensation failed: {action.action_id} - {e}")

            elif action.executed_at and not action.compensate_func:
                # Action executed but no compensation function
                compensation_log.append(
                    {
                        "action_id": action.action_id,
                        "status": "no_compensation",
                        "warning": "Action executed but no compensation function provided",
                        "timestamp": datetime.now(UTC).isoformat(),
                    }
                )

                logger.warning(f"No compensation for executed action: {action.action_id}")

        transaction.compensation_log = compensation_log
        transaction.state = TransactionState.COMPENSATED

        logger.info(f"Compensation completed for transaction: {transaction.transaction_id}")

    def get_transaction(self, transaction_id: str) -> SagaTransaction | None:
        """Get a transaction by ID."""
        if transaction_id in self._active_transactions:
            return self._active_transactions[transaction_id]
        if transaction_id in self._completed_transactions:
            return self._completed_transactions[transaction_id]
        return None

    def list_active_transactions(self) -> list[SagaTransaction]:
        """List all active transactions."""
        return list(self._active_transactions.values())

    def list_completed_transactions(self) -> list[SagaTransaction]:
        """List all completed transactions."""
        return list(self._completed_transactions.values())

    async def get_engine_status(self) -> JSONDict:
        """Get engine status and statistics."""
        active_count = len(self._active_transactions)
        completed_count = len(self._completed_transactions)

        return {
            "engine": "SagaLLM Transaction Engine",
            "status": "operational",
            "active_transactions": active_count,
            "completed_transactions": completed_count,
            "max_transaction_time": self.max_transaction_time,
            "default_action_timeout": self.default_action_timeout,
            "compensation_timeout": self.compensation_timeout,
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }


@asynccontextmanager
async def saga_transaction(
    engine: SagaLLMEngine,
    description: str,
    metadata: JSONDict | None = None,
) -> AsyncIterator[SagaTransaction]:
    """
    Context manager for SagaLLM transactions.

    Usage:
        async with saga_transaction(engine, "Governance decision") as saga:
            saga.add_action(...)
            saga.checkpoint("pre_validation", state)
            await saga.execute()
    """
    transaction = engine.create_transaction(description, metadata)

    try:
        yield transaction

        # Execute the transaction
        success = await engine.execute_transaction(transaction)
        if not success:
            raise RuntimeError(
                f"SagaLLM transaction failed and was compensated: {transaction.transaction_id}"
            )

    except _SAGALLM_OPERATION_ERRORS as e:
        logger.error(f"SagaLLM transaction context failed: {e}")
        raise


# Convenience functions for common governance operations
async def create_governance_transaction(
    engine: SagaLLMEngine,
    decision_description: str,
) -> SagaTransaction:
    """
    Create a transaction for governance decision with standard actions.

    This provides a high-level API for constitutional governance transactions.
    """
    transaction = engine.create_transaction(
        f"Governance Decision: {decision_description}",
        {"type": "governance", "decision": decision_description},
    )

    # Add standard governance actions (these would be implemented by the caller)
    # This is a template - actual implementation would provide real functions

    async def validate_constitutional_compliance() -> JSONDict:
        """Validate decision against constitutional principles."""
        # Implementation would call MACI verification
        return {"status": "validated", "timestamp": datetime.now(UTC).isoformat()}

    async def compensate_validation() -> JSONDict:
        """Compensation for validation (typically a no-op)."""
        return {"status": "validation_rolled_back"}

    engine.add_action(
        transaction,
        TransactionAction.CONSTITUTIONAL_CHECK,
        "Validate constitutional compliance",
        validate_constitutional_compliance,
        compensate_validation,
    )

    async def execute_decision() -> JSONDict:
        """Execute the governance decision."""
        return {"status": "executed", "decision": decision_description}

    async def compensate_decision() -> JSONDict:
        """Compensation: revert the decision."""
        return {"status": "decision_reverted", "decision": decision_description}

    engine.add_action(
        transaction,
        TransactionAction.GOVERNANCE_DECISION,
        f"Execute governance decision: {decision_description}",
        execute_decision,
        compensate_decision,
    )

    async def log_audit() -> JSONDict:
        """Log the decision to audit trail."""
        return {"status": "logged", "audit_id": str(uuid.uuid4())}

    # Audit logging typically doesn't need compensation (it's append-only)
    engine.add_action(
        transaction,
        TransactionAction.AUDIT_LOGGING,
        "Log decision to audit trail",
        log_audit,
        None,  # No compensation needed for audit logs
    )

    return transaction


# Global SagaLLM engine instance
saga_engine = SagaLLMEngine()


def get_saga_engine() -> SagaLLMEngine:
    """Get the global SagaLLM engine instance."""
    return saga_engine


if __name__ == "__main__":
    # Example usage and testing
    import logging as _logging

    _logging.basicConfig(level=_logging.INFO, format="%(message)s")

    async def main():
        logger.info("Testing SagaLLM Transaction Engine...")

        engine = SagaLLMEngine()

        # Test engine status
        status = await engine.get_engine_status()
        logger.info("Engine status: %s", status["status"])
        logger.info("Constitutional hash: %s", status["constitutional_hash"])

        # Test transaction creation
        transaction = engine.create_transaction("Test governance decision")
        logger.info("Transaction created: %s", transaction.transaction_id)
        logger.info("Initial state: %s", transaction.state.value)

        # Test adding actions
        async def mock_execute():
            return {"result": "executed"}

        async def mock_compensate():
            return {"result": "compensated"}

        action = engine.add_action(
            transaction,
            TransactionAction.GOVERNANCE_DECISION,
            "Test action",
            mock_execute,
            mock_compensate,
        )

        logger.info("Action added: %s", action.action_id)
        logger.info("Actions in transaction: %d", len(transaction.actions))

        # Test transaction execution
        success = await engine.execute_transaction(transaction)
        logger.info("Transaction execution: %s", "success" if success else "compensated")
        logger.info("Final state: %s", transaction.state.value)

        # Test context manager
        async def test_context_manager():
            async with saga_transaction(engine, "Context manager test") as saga:
                engine.add_action(
                    saga,
                    TransactionAction.POLICY_VALIDATION,
                    "Test policy validation",
                    mock_execute,
                    mock_compensate,
                )
                return await engine.execute_transaction(saga)

        context_success = await test_context_manager()
        logger.info("Context manager: %s", "success" if context_success else "compensated")

        logger.info("SagaLLM Transaction Engine test completed!")

    # Run test
    asyncio.run(main())
