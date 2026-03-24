"""Backward-compatible contract API layered on the shared execution model."""

from constitutional_swarm.execution import (
    ContractStatus,
    ExecutionStatus,
    TaskContract,
    WorkReceipt,
)

__all__ = [
    "ContractStatus",
    "ExecutionStatus",
    "TaskContract",
    "WorkReceipt",
]
