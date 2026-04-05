"""
ACGS-2 LangGraph Orchestration - State Reducer Tests
Constitutional Hash: 608508a9bd224290
"""

from datetime import datetime, timezone

import pytest

from enhanced_agent_bus.models import CONSTITUTIONAL_HASH, GraphState

from ..state_reducer import (
    AccumulatorStateReducer,
    BaseStateReducer,
    CustomStateReducer,
    ImmutableStateReducer,
    MergeStateReducer,
    OverwriteStateReducer,
    create_state_reducer,
)


class TestMergeStateReducer:
    """Tests for MergeStateReducer."""

    def test_simple_merge(self):
        """Test simple merge of state."""
        reducer = MergeStateReducer()
        state = GraphState(data={"a": 1, "b": 2})
        output = {"c": 3}

        new_state = reducer.reduce(state, output, "node1")

        assert new_state.data == {"a": 1, "b": 2, "c": 3}
        assert new_state.version == 1
        assert new_state.last_node_id == "node1"

    def test_overwrite_existing_key(self):
        """Test merge overwrites existing keys."""
        reducer = MergeStateReducer()
        state = GraphState(data={"a": 1, "b": 2})
        output = {"b": 10, "c": 3}

        new_state = reducer.reduce(state, output, "node1")

        assert new_state.data == {"a": 1, "b": 10, "c": 3}

    def test_deep_merge_disabled(self):
        """Test shallow merge by default."""
        reducer = MergeStateReducer(deep_merge=False)
        state = GraphState(data={"nested": {"a": 1, "b": 2}})
        output = {"nested": {"c": 3}}

        new_state = reducer.reduce(state, output, "node1")

        # Shallow merge replaces nested dict
        assert new_state.data == {"nested": {"c": 3}}

    def test_deep_merge_enabled(self):
        """Test deep merge when enabled."""
        reducer = MergeStateReducer(deep_merge=True)
        state = GraphState(data={"nested": {"a": 1, "b": 2}})
        output = {"nested": {"c": 3}}

        new_state = reducer.reduce(state, output, "node1")

        # Deep merge combines nested dicts
        assert new_state.data == {"nested": {"a": 1, "b": 2, "c": 3}}

    def test_list_merge_disabled(self):
        """Test list replacement by default."""
        reducer = MergeStateReducer(deep_merge=True, merge_lists=False)
        state = GraphState(data={"items": [1, 2, 3]})
        output = {"items": [4, 5]}

        new_state = reducer.reduce(state, output, "node1")

        assert new_state.data == {"items": [4, 5]}

    def test_list_merge_enabled(self):
        """Test list concatenation when enabled."""
        reducer = MergeStateReducer(deep_merge=True, merge_lists=True)
        state = GraphState(data={"items": [1, 2, 3]})
        output = {"items": [4, 5]}

        new_state = reducer.reduce(state, output, "node1")

        assert new_state.data == {"items": [1, 2, 3, 4, 5]}

    def test_mutation_history_tracked(self):
        """Test mutation history is tracked."""
        reducer = MergeStateReducer()
        state = GraphState(data={})
        output = {"key": "value"}

        new_state = reducer.reduce(state, output, "node1")

        assert len(new_state.mutation_history) == 1
        assert new_state.mutation_history[0]["operation"] == "merge"
        assert new_state.mutation_history[0]["node_id"] == "node1"


class TestImmutableStateReducer:
    """Tests for ImmutableStateReducer."""

    def test_replace_state(self):
        """Test state is completely replaced."""
        reducer = ImmutableStateReducer()
        state = GraphState(data={"a": 1, "b": 2})
        output = {"c": 3}

        new_state = reducer.reduce(state, output, "node1")

        assert new_state.data == {"c": 3}
        assert "a" not in new_state.data
        assert "b" not in new_state.data

    def test_version_incremented(self):
        """Test version is incremented."""
        reducer = ImmutableStateReducer()
        state = GraphState(data={"a": 1}, version=5)
        output = {"b": 2}

        new_state = reducer.reduce(state, output, "node1")

        assert new_state.version == 6

    def test_mutation_history_tracked(self):
        """Test mutation history tracks replace operation."""
        reducer = ImmutableStateReducer()
        state = GraphState(data={"a": 1})
        output = {"b": 2}

        new_state = reducer.reduce(state, output, "node1")

        assert len(new_state.mutation_history) == 1
        assert new_state.mutation_history[0]["operation"] == "replace"


class TestOverwriteStateReducer:
    """Tests for OverwriteStateReducer."""

    def test_overwrite_specified_keys(self):
        """Test only specified keys are overwritten."""
        reducer = OverwriteStateReducer(overwrite_keys=["b"])
        state = GraphState(data={"a": 1, "b": 2})
        output = {"a": 10, "b": 20, "c": 30}

        new_state = reducer.reduce(state, output, "node1")

        assert new_state.data["a"] == 10  # Merged
        assert new_state.data["b"] == 20  # Overwritten
        assert new_state.data["c"] == 30  # Added

    def test_preserve_keys(self):
        """Test preserved keys are not modified."""
        reducer = OverwriteStateReducer(preserve_keys=["a"])
        state = GraphState(data={"a": 1, "b": 2})
        output = {"a": 10, "b": 20}

        new_state = reducer.reduce(state, output, "node1")

        assert new_state.data["a"] == 1  # Preserved
        assert new_state.data["b"] == 20  # Updated

    def test_remove_keys(self):
        """Test specified keys are removed."""
        reducer = OverwriteStateReducer(remove_keys=["b"])
        state = GraphState(data={"a": 1, "b": 2})
        output = {"c": 3}

        new_state = reducer.reduce(state, output, "node1")

        assert "a" in new_state.data
        assert "b" not in new_state.data
        assert "c" in new_state.data


class TestAccumulatorStateReducer:
    """Tests for AccumulatorStateReducer."""

    def test_accumulate_values(self):
        """Test values are accumulated in list."""
        reducer = AccumulatorStateReducer(accumulate_keys=["results"])
        state = GraphState(data={"results": ["first"]})
        output = {"results": "second"}

        new_state = reducer.reduce(state, output, "node1")

        assert new_state.data["results"] == ["first", "second"]

    def test_accumulate_creates_list(self):
        """Test accumulation creates list if not exists."""
        reducer = AccumulatorStateReducer(accumulate_keys=["results"])
        state = GraphState(data={})
        output = {"results": "first"}

        new_state = reducer.reduce(state, output, "node1")

        assert new_state.data["results"] == ["first"]

    def test_non_accumulate_keys_merged(self):
        """Test non-accumulate keys are merged normally."""
        reducer = AccumulatorStateReducer(accumulate_keys=["results"])
        state = GraphState(data={"status": "pending"})
        output = {"status": "complete", "results": "data"}

        new_state = reducer.reduce(state, output, "node1")

        assert new_state.data["status"] == "complete"
        assert new_state.data["results"] == ["data"]

    def test_max_accumulate_size(self):
        """Test accumulation respects max size."""
        reducer = AccumulatorStateReducer(
            accumulate_keys=["items"],
            max_accumulate_size=3,
        )
        state = GraphState(data={"items": [1, 2, 3]})
        output = {"items": 4}

        new_state = reducer.reduce(state, output, "node1")

        assert len(new_state.data["items"]) == 3
        assert new_state.data["items"] == [2, 3, 4]


class TestCustomStateReducer:
    """Tests for CustomStateReducer."""

    def test_custom_reducer(self):
        """Test custom reducer function."""

        def custom_fn(current, output, node_id):
            return {
                **current,
                **output,
                "custom_field": f"processed_by_{node_id}",
            }

        reducer = CustomStateReducer(reduce_fn=custom_fn)
        state = GraphState(data={"a": 1})
        output = {"b": 2}

        new_state = reducer.reduce(state, output, "node1")

        assert new_state.data == {
            "a": 1,
            "b": 2,
            "custom_field": "processed_by_node1",
        }

    def test_custom_reducer_isolation(self):
        """Test custom reducer doesn't modify original."""

        def custom_fn(current, output, node_id):
            current["modified"] = True
            return current

        reducer = CustomStateReducer(reduce_fn=custom_fn)
        original_data = {"a": 1}
        state = GraphState(data=original_data)
        output = {}

        new_state = reducer.reduce(state, output, "node1")

        # Original should be unchanged (deep copy)
        assert "modified" not in original_data


class TestCreateStateReducer:
    """Tests for create_state_reducer factory."""

    def test_create_merge_reducer(self):
        """Test creating merge reducer."""
        reducer = create_state_reducer(strategy="merge")
        assert isinstance(reducer, MergeStateReducer)

    def test_create_merge_with_options(self):
        """Test creating merge reducer with options."""
        reducer = create_state_reducer(
            strategy="merge",
            deep_merge=True,
            merge_lists=True,
        )
        assert isinstance(reducer, MergeStateReducer)
        assert reducer.deep_merge is True
        assert reducer.merge_lists is True

    def test_create_overwrite_reducer(self):
        """Test creating overwrite reducer."""
        reducer = create_state_reducer(
            strategy="overwrite",
            overwrite_keys=["key1"],
            preserve_keys=["key2"],
        )
        assert isinstance(reducer, OverwriteStateReducer)
        assert "key1" in reducer.overwrite_keys
        assert "key2" in reducer.preserve_keys

    def test_create_immutable_reducer(self):
        """Test creating immutable reducer."""
        reducer = create_state_reducer(strategy="immutable")
        assert isinstance(reducer, ImmutableStateReducer)

    def test_create_accumulate_reducer(self):
        """Test creating accumulate reducer."""
        reducer = create_state_reducer(
            strategy="accumulate",
            accumulate_keys=["results"],
        )
        assert isinstance(reducer, AccumulatorStateReducer)
        assert "results" in reducer.accumulate_keys

    def test_create_custom_reducer(self):
        """Test creating custom reducer."""

        def custom_fn(current, output, node_id):
            return {**current, **output}

        reducer = create_state_reducer(
            strategy="custom",
            reduce_fn=custom_fn,
        )
        assert isinstance(reducer, CustomStateReducer)

    def test_create_custom_without_fn_raises(self):
        """Test creating custom reducer without function raises."""
        with pytest.raises(ValueError, match="reduce_fn"):
            create_state_reducer(strategy="custom")

    def test_unknown_strategy_raises(self):
        """Test unknown strategy raises."""
        with pytest.raises(ValueError, match="Unknown"):
            create_state_reducer(strategy="unknown")


class TestStateDelta:
    """Tests for state delta computation."""

    def test_compute_delta_add(self):
        """Test computing delta for added keys."""
        reducer = MergeStateReducer()
        old_state = GraphState(data={"a": 1})
        new_state = GraphState(data={"a": 1, "b": 2}, version=1)

        delta = reducer.compute_delta(old_state, new_state, "node1")

        assert delta.from_version == 0
        assert delta.to_version == 1
        assert len(delta.changes) == 1
        assert delta.changes[0]["operation"] == "add"
        assert delta.changes[0]["key"] == "b"

    def test_compute_delta_modify(self):
        """Test computing delta for modified keys."""
        reducer = MergeStateReducer()
        old_state = GraphState(data={"a": 1})
        new_state = GraphState(data={"a": 2}, version=1)

        delta = reducer.compute_delta(old_state, new_state, "node1")

        assert len(delta.changes) == 1
        assert delta.changes[0]["operation"] == "modify"
        assert delta.changes[0]["old_value"] == 1
        assert delta.changes[0]["new_value"] == 2

    def test_compute_delta_remove(self):
        """Test computing delta for removed keys."""
        reducer = MergeStateReducer()
        old_state = GraphState(data={"a": 1, "b": 2})
        new_state = GraphState(data={"a": 1}, version=1)

        delta = reducer.compute_delta(old_state, new_state, "node1")

        assert any(c["operation"] == "remove" and c["key"] == "b" for c in delta.changes)


class TestReducerOutputValidation:
    """Tests for output validation."""

    def test_validate_valid_output(self):
        """Test validation passes for dict output."""
        reducer = MergeStateReducer()
        errors = reducer.validate_output({"key": "value"})
        assert len(errors) == 0

    def test_validate_invalid_output(self):
        """Test validation fails for non-dict output."""
        reducer = MergeStateReducer()
        errors = reducer.validate_output("not a dict")
        assert len(errors) > 0
        assert "dict" in errors[0].lower()
