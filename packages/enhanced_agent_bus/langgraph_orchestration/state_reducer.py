"""
ACGS-2 LangGraph Orchestration - State Reducers
Constitutional Hash: cdd01ef066bc6cf2

State reducers implement the core LangGraph pattern:
    All nodes are pure functions: (CurrentState) -> NewState

State reducers define how node outputs merge with existing state.
"""

import copy
from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import UTC, datetime

try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH  # noqa: E402
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from src.core.shared.types import JSONDict  # noqa: E402
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from .models import GraphState, StateDelta

logger = get_logger(__name__)


def safe_copy(value: object) -> object:
    """Efficiently copy values, only deepcopying mutable types.

    This function optimizes performance by avoiding unnecessary deepcopies
    of immutable types (str, int, float, bool, None, tuples) which don't
    need copying since they can't be modified in place.

    Args:
        value: The value to copy

    Returns:
        A deep copy for mutable types (dict, list), the original value
        for immutable types (str, int, float, bool, None, tuple)
    """
    if isinstance(value, (dict, list)):
        return copy.deepcopy(value)
    return value


class BaseStateReducer(ABC):
    """Abstract base class for state reducers.

    State reducers implement the Memory Object Protocol for
    strictly typed JSON state mutations.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def __init__(self, constitutional_hash: str = CONSTITUTIONAL_HASH):
        self.constitutional_hash = constitutional_hash

    @abstractmethod
    def reduce(
        self,
        current_state: GraphState,
        node_output: JSONDict,
        node_id: str,
    ) -> GraphState:
        """Apply node output to current state.

        Args:
            current_state: Current graph state
            node_output: Output from node execution
            node_id: ID of the node that produced output

        Returns:
            New state with applied changes
        """
        ...

    def validate_output(self, node_output: JSONDict) -> list[str]:
        """Validate node output before reduction.

        Args:
            node_output: Output to validate

        Returns:
            List of validation errors (empty if valid)
        """
        errors: list[str] = []
        if not isinstance(node_output, dict):
            errors.append(f"Node output must be dict, got {type(node_output).__name__}")
        return errors

    def compute_delta(
        self,
        old_state: GraphState,
        new_state: GraphState,
        node_id: str,
    ) -> StateDelta:
        """Compute the delta between two states.

        Args:
            old_state: State before reduction
            new_state: State after reduction
            node_id: Node that caused the change

        Returns:
            StateDelta representing the changes
        """
        changes = []
        old_data = old_state.data
        new_data = new_state.data

        # Find added/modified keys
        for key, new_value in new_data.items():
            old_value = old_data.get(key)
            if key not in old_data:
                changes.append(
                    {
                        "operation": "add",
                        "key": key,
                        "value": new_value,
                    }
                )
            elif old_value != new_value:
                changes.append(
                    {
                        "operation": "modify",
                        "key": key,
                        "old_value": old_value,
                        "new_value": new_value,
                    }
                )

        # Find removed keys
        for key in old_data:
            if key not in new_data:
                changes.append(
                    {
                        "operation": "remove",
                        "key": key,
                        "value": old_data[key],
                    }
                )

        return StateDelta(
            from_version=old_state.version,
            to_version=new_state.version,
            changes=changes,
            node_id=node_id,
            timestamp=datetime.now(UTC),
            constitutional_hash=self.constitutional_hash,
        )


class ImmutableStateReducer(BaseStateReducer):
    """State reducer that creates completely new state from node output.

    This reducer replaces the entire state with node output,
    preserving only metadata and version tracking.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def reduce(
        self,
        current_state: GraphState,
        node_output: JSONDict,
        node_id: str,
    ) -> GraphState:
        """Replace state data entirely with node output."""
        return GraphState(
            data=safe_copy(node_output),
            version=current_state.version + 1,
            last_updated=datetime.now(UTC),
            last_node_id=node_id,
            constitutional_hash=self.constitutional_hash,
            mutation_history=current_state.mutation_history  # noqa: RUF005
            + [
                {
                    "operation": "replace",
                    "node_id": node_id,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "version": current_state.version + 1,
                }
            ],
            max_history_size=current_state.max_history_size,
        )


class MergeStateReducer(BaseStateReducer):
    """State reducer that merges node output into existing state.

    This is the default reducer, performing shallow merge of
    node output keys into current state.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def __init__(
        self,
        deep_merge: bool = False,
        merge_lists: bool = False,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
    ):
        super().__init__(constitutional_hash)
        self.deep_merge = deep_merge
        self.merge_lists = merge_lists

    def reduce(
        self,
        current_state: GraphState,
        node_output: JSONDict,
        node_id: str,
    ) -> GraphState:
        """Merge node output into current state."""
        if self.deep_merge:
            new_data = self._deep_merge(
                safe_copy(current_state.data),
                node_output,
            )
        else:
            new_data = current_state.data.copy()
            new_data.update(node_output)

        mutation = {
            "operation": "merge",
            "keys": list(node_output.keys()),
            "node_id": node_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "version": current_state.version + 1,
        }

        new_history = current_state.mutation_history.copy()
        new_history.append(mutation)
        if len(new_history) > current_state.max_history_size:
            new_history = new_history[-current_state.max_history_size :]

        return GraphState(
            data=new_data,
            version=current_state.version + 1,
            last_updated=datetime.now(UTC),
            last_node_id=node_id,
            constitutional_hash=self.constitutional_hash,
            mutation_history=new_history,
            max_history_size=current_state.max_history_size,
        )

    def _deep_merge(self, base: JSONDict, updates: JSONDict) -> JSONDict:
        """Recursively merge dictionaries."""
        result = base.copy()
        for key, value in updates.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            elif key in result and isinstance(result[key], list) and isinstance(value, list):
                if self.merge_lists:
                    result[key] = result[key] + value
                else:
                    result[key] = value
            else:
                result[key] = safe_copy(value)
        return result


class OverwriteStateReducer(BaseStateReducer):
    """State reducer that selectively overwrites specified keys.

    Allows fine-grained control over which keys are updated,
    preserved, or removed.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def __init__(
        self,
        overwrite_keys: list[str] | None = None,
        preserve_keys: list[str] | None = None,
        remove_keys: list[str] | None = None,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
    ):
        super().__init__(constitutional_hash)
        self.overwrite_keys = overwrite_keys or []
        self.preserve_keys = preserve_keys or []
        self.remove_keys = remove_keys or []

    def reduce(
        self,
        current_state: GraphState,
        node_output: JSONDict,
        node_id: str,
    ) -> GraphState:
        """Selectively overwrite state keys."""
        new_data = current_state.data.copy()

        # Process overwrite keys
        for key in self.overwrite_keys:
            if key in node_output:
                new_data[key] = safe_copy(node_output[key])

        # Process non-specified keys (merge by default)
        for key, value in node_output.items():
            if key not in self.overwrite_keys and key not in self.preserve_keys:
                new_data[key] = safe_copy(value)

        # Process remove keys
        for key in self.remove_keys:
            new_data.pop(key, None)

        mutation = {
            "operation": "selective_overwrite",
            "overwritten": [k for k in self.overwrite_keys if k in node_output],
            "preserved": self.preserve_keys,
            "removed": self.remove_keys,
            "node_id": node_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "version": current_state.version + 1,
        }

        new_history = current_state.mutation_history.copy()
        new_history.append(mutation)
        if len(new_history) > current_state.max_history_size:
            new_history = new_history[-current_state.max_history_size :]

        return GraphState(
            data=new_data,
            version=current_state.version + 1,
            last_updated=datetime.now(UTC),
            last_node_id=node_id,
            constitutional_hash=self.constitutional_hash,
            mutation_history=new_history,
            max_history_size=current_state.max_history_size,
        )


class AccumulatorStateReducer(BaseStateReducer):
    """State reducer that accumulates values in lists.

    Useful for collecting results from multiple nodes
    without overwriting previous outputs.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def __init__(
        self,
        accumulate_keys: list[str] | None = None,
        max_accumulate_size: int = 1000,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
    ):
        super().__init__(constitutional_hash)
        self.accumulate_keys = accumulate_keys or []
        self.max_accumulate_size = max_accumulate_size

    def reduce(
        self,
        current_state: GraphState,
        node_output: JSONDict,
        node_id: str,
    ) -> GraphState:
        """Accumulate values for specified keys."""
        new_data = current_state.data.copy()

        for key, value in node_output.items():
            if key in self.accumulate_keys:
                if key not in new_data:
                    new_data[key] = []
                if isinstance(new_data[key], list):
                    new_data[key] = new_data[key] + [value]
                    if len(new_data[key]) > self.max_accumulate_size:
                        new_data[key] = new_data[key][-self.max_accumulate_size :]
                else:
                    new_data[key] = [new_data[key], value]
            else:
                new_data[key] = safe_copy(value)

        mutation = {
            "operation": "accumulate",
            "accumulated_keys": [k for k in self.accumulate_keys if k in node_output],
            "node_id": node_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "version": current_state.version + 1,
        }

        new_history = current_state.mutation_history.copy()
        new_history.append(mutation)
        if len(new_history) > current_state.max_history_size:
            new_history = new_history[-current_state.max_history_size :]

        return GraphState(
            data=new_data,
            version=current_state.version + 1,
            last_updated=datetime.now(UTC),
            last_node_id=node_id,
            constitutional_hash=self.constitutional_hash,
            mutation_history=new_history,
            max_history_size=current_state.max_history_size,
        )


class CustomStateReducer(BaseStateReducer):
    """State reducer with custom reduction function.

    Allows injection of custom state reduction logic
    while maintaining constitutional compliance.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def __init__(
        self,
        reduce_fn: Callable[[JSONDict, JSONDict, str], JSONDict],
        constitutional_hash: str = CONSTITUTIONAL_HASH,
    ):
        """
        Args:
            reduce_fn: Custom function (current_data, output, node_id) -> new_data
        """
        super().__init__(constitutional_hash)
        self.reduce_fn = reduce_fn

    def reduce(
        self,
        current_state: GraphState,
        node_output: JSONDict,
        node_id: str,
    ) -> GraphState:
        """Apply custom reduction function."""
        new_data = self.reduce_fn(
            safe_copy(current_state.data),
            node_output,
            node_id,
        )

        mutation = {
            "operation": "custom",
            "node_id": node_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "version": current_state.version + 1,
        }

        new_history = current_state.mutation_history.copy()
        new_history.append(mutation)
        if len(new_history) > current_state.max_history_size:
            new_history = new_history[-current_state.max_history_size :]

        return GraphState(
            data=new_data,
            version=current_state.version + 1,
            last_updated=datetime.now(UTC),
            last_node_id=node_id,
            constitutional_hash=self.constitutional_hash,
            mutation_history=new_history,
            max_history_size=current_state.max_history_size,
        )


def create_state_reducer(
    strategy: str = "merge",
    **kwargs: object,
) -> BaseStateReducer:
    """Factory function to create state reducers.

    Args:
        strategy: Reducer strategy (merge, overwrite, immutable, accumulate, custom)
        **kwargs: Additional arguments for the reducer

    Returns:
        Configured state reducer

    Constitutional Hash: cdd01ef066bc6cf2
    """
    constitutional_hash = kwargs.pop("constitutional_hash", CONSTITUTIONAL_HASH)

    if strategy == "merge":
        return MergeStateReducer(
            deep_merge=kwargs.get("deep_merge", False),
            merge_lists=kwargs.get("merge_lists", False),
            constitutional_hash=constitutional_hash,
        )
    elif strategy == "overwrite":
        return OverwriteStateReducer(
            overwrite_keys=kwargs.get("overwrite_keys"),
            preserve_keys=kwargs.get("preserve_keys"),
            remove_keys=kwargs.get("remove_keys"),
            constitutional_hash=constitutional_hash,
        )
    elif strategy == "immutable":
        return ImmutableStateReducer(constitutional_hash=constitutional_hash)
    elif strategy == "accumulate":
        return AccumulatorStateReducer(
            accumulate_keys=kwargs.get("accumulate_keys"),
            max_accumulate_size=kwargs.get("max_accumulate_size", 1000),
            constitutional_hash=constitutional_hash,
        )
    elif strategy == "custom":
        reduce_fn = kwargs.get("reduce_fn")
        if not reduce_fn:
            raise ValueError("custom strategy requires reduce_fn argument")
        return CustomStateReducer(
            reduce_fn=reduce_fn,
            constitutional_hash=constitutional_hash,
        )
    else:
        raise ValueError(f"Unknown reducer strategy: {strategy}")


__all__ = [
    "AccumulatorStateReducer",
    "BaseStateReducer",
    "CustomStateReducer",
    "ImmutableStateReducer",
    "MergeStateReducer",
    "OverwriteStateReducer",
    "create_state_reducer",
    "safe_copy",
]
