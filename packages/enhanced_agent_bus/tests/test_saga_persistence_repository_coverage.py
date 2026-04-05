# Constitutional Hash: 608508a9bd224290
"""
Comprehensive tests for saga_persistence/repository.py

Covers:
- SagaStateRepository abstract interface and constitutional_hash property
- RepositoryError base exception
- SagaNotFoundError
- VersionConflictError (with version fields)
- InvalidStateTransitionError (with state fields)
- LockError
- All error codes, HTTP status codes, inheritance, message formatting
- Edge cases: None saga_id, empty strings, various state transitions
"""

from datetime import UTC, timezone

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.saga_persistence.models import SagaState
from enhanced_agent_bus.saga_persistence.repository import (
    InvalidStateTransitionError,
    LockError,
    RepositoryError,
    SagaNotFoundError,
    SagaStateRepository,
    VersionConflictError,
)

# ---------------------------------------------------------------------------
# Concrete implementation of the abstract base for testing the property
# ---------------------------------------------------------------------------


class _ConcreteRepo(SagaStateRepository):
    """Minimal concrete implementation of SagaStateRepository for testing."""

    async def save(self, saga):
        return True

    async def get(self, saga_id):
        return None

    async def delete(self, saga_id):
        return True

    async def exists(self, saga_id):
        return False

    async def list_by_tenant(self, tenant_id, state=None, limit=100, offset=0):
        return []

    async def list_by_state(self, state, limit=100, offset=0):
        return []

    async def list_pending_compensations(self, limit=100):
        return []

    async def list_timed_out(self, since, limit=100):
        return []

    async def count_by_state(self, state):
        return 0

    async def count_by_tenant(self, tenant_id):
        return 0

    async def update_state(self, saga_id, new_state, failure_reason=None):
        return True

    async def update_step_state(
        self, saga_id, step_id, new_state, output_data=None, error_message=None
    ):
        return True

    async def update_current_step(self, saga_id, step_index):
        return True

    async def save_checkpoint(self, checkpoint):
        return True

    async def get_checkpoints(self, saga_id, limit=100):
        return []

    async def get_latest_checkpoint(self, saga_id):
        return None

    async def delete_checkpoints(self, saga_id):
        return 0

    async def append_compensation_entry(self, saga_id, entry):
        return True

    async def get_compensation_log(self, saga_id):
        return []

    async def acquire_lock(self, saga_id, lock_holder, ttl_seconds=30):
        return True

    async def release_lock(self, saga_id, lock_holder):
        return True

    async def extend_lock(self, saga_id, lock_holder, ttl_seconds=30):
        return True

    async def cleanup_old_sagas(self, older_than, terminal_only=True):
        return 0

    async def get_statistics(self):
        return {}

    async def health_check(self):
        return {"status": "ok"}


class _SuperCallingRepo(SagaStateRepository):
    """
    Concrete implementation that calls super() on every method,
    executing the abstract base's '...' body for coverage purposes.
    """

    async def save(self, saga):
        await super().save(saga)  # type: ignore[misc]
        return True

    async def get(self, saga_id):
        await super().get(saga_id)  # type: ignore[misc]
        return None

    async def delete(self, saga_id):
        await super().delete(saga_id)  # type: ignore[misc]
        return True

    async def exists(self, saga_id):
        await super().exists(saga_id)  # type: ignore[misc]
        return False

    async def list_by_tenant(self, tenant_id, state=None, limit=100, offset=0):
        await super().list_by_tenant(tenant_id, state=state, limit=limit, offset=offset)  # type: ignore[misc]
        return []

    async def list_by_state(self, state, limit=100, offset=0):
        await super().list_by_state(state, limit=limit, offset=offset)  # type: ignore[misc]
        return []

    async def list_pending_compensations(self, limit=100):
        await super().list_pending_compensations(limit=limit)  # type: ignore[misc]
        return []

    async def list_timed_out(self, since, limit=100):
        await super().list_timed_out(since, limit=limit)  # type: ignore[misc]
        return []

    async def count_by_state(self, state):
        await super().count_by_state(state)  # type: ignore[misc]
        return 0

    async def count_by_tenant(self, tenant_id):
        await super().count_by_tenant(tenant_id)  # type: ignore[misc]
        return 0

    async def update_state(self, saga_id, new_state, failure_reason=None):
        await super().update_state(saga_id, new_state, failure_reason=failure_reason)  # type: ignore[misc]
        return True

    async def update_step_state(
        self, saga_id, step_id, new_state, output_data=None, error_message=None
    ):
        await super().update_step_state(  # type: ignore[misc]
            saga_id, step_id, new_state, output_data=output_data, error_message=error_message
        )
        return True

    async def update_current_step(self, saga_id, step_index):
        await super().update_current_step(saga_id, step_index)  # type: ignore[misc]
        return True

    async def save_checkpoint(self, checkpoint):
        await super().save_checkpoint(checkpoint)  # type: ignore[misc]
        return True

    async def get_checkpoints(self, saga_id, limit=100):
        await super().get_checkpoints(saga_id, limit=limit)  # type: ignore[misc]
        return []

    async def get_latest_checkpoint(self, saga_id):
        await super().get_latest_checkpoint(saga_id)  # type: ignore[misc]
        return None

    async def delete_checkpoints(self, saga_id):
        await super().delete_checkpoints(saga_id)  # type: ignore[misc]
        return 0

    async def append_compensation_entry(self, saga_id, entry):
        await super().append_compensation_entry(saga_id, entry)  # type: ignore[misc]
        return True

    async def get_compensation_log(self, saga_id):
        await super().get_compensation_log(saga_id)  # type: ignore[misc]
        return []

    async def acquire_lock(self, saga_id, lock_holder, ttl_seconds=30):
        await super().acquire_lock(saga_id, lock_holder, ttl_seconds=ttl_seconds)  # type: ignore[misc]
        return True

    async def release_lock(self, saga_id, lock_holder):
        await super().release_lock(saga_id, lock_holder)  # type: ignore[misc]
        return True

    async def extend_lock(self, saga_id, lock_holder, ttl_seconds=30):
        await super().extend_lock(saga_id, lock_holder, ttl_seconds=ttl_seconds)  # type: ignore[misc]
        return True

    async def cleanup_old_sagas(self, older_than, terminal_only=True):
        await super().cleanup_old_sagas(older_than, terminal_only=terminal_only)  # type: ignore[misc]
        return 0

    async def get_statistics(self):
        await super().get_statistics()  # type: ignore[misc]
        return {}

    async def health_check(self):
        await super().health_check()  # type: ignore[misc]
        return {"status": "ok"}


# ===========================================================================
# SagaStateRepository - abstract class and property tests
# ===========================================================================


class TestSagaStateRepositoryAbstract:
    """Tests for the abstract SagaStateRepository class."""

    def test_cannot_instantiate_abstract_class(self):
        """SagaStateRepository cannot be instantiated directly."""
        with pytest.raises(TypeError):
            SagaStateRepository()  # type: ignore[abstract]

    def test_concrete_subclass_can_be_instantiated(self):
        """A fully-implemented subclass can be instantiated."""
        repo = _ConcreteRepo()
        assert isinstance(repo, SagaStateRepository)

    def test_constitutional_hash_property_value(self):
        """constitutional_hash property returns the global CONSTITUTIONAL_HASH."""
        repo = _ConcreteRepo()
        assert repo.constitutional_hash == CONSTITUTIONAL_HASH

    def test_constitutional_hash_property_exact_value(self):
        """Constitutional hash is the expected literal value."""
        repo = _ConcreteRepo()
        assert repo.constitutional_hash == CONSTITUTIONAL_HASH  # pragma: allowlist secret

    def test_constitutional_hash_is_string(self):
        """Constitutional hash is a string."""
        repo = _ConcreteRepo()
        assert isinstance(repo.constitutional_hash, str)

    def test_constitutional_hash_is_readonly_property(self):
        """constitutional_hash cannot be set."""
        repo = _ConcreteRepo()
        with pytest.raises(AttributeError):
            repo.constitutional_hash = "something_else"  # type: ignore[misc]

    async def test_super_calling_repo_instantiation(self):
        """_SuperCallingRepo (calls super) can be instantiated."""
        repo = _SuperCallingRepo()
        assert isinstance(repo, SagaStateRepository)

    async def test_abstract_save_body_executed_via_super(self):
        """Calling super().save() executes the abstract method body (...)."""
        repo = _SuperCallingRepo()
        result = await repo.save(None)  # type: ignore[arg-type]
        assert result is True

    async def test_abstract_get_body_executed_via_super(self):
        """Calling super().get() executes the abstract method body."""
        repo = _SuperCallingRepo()
        result = await repo.get("saga-1")
        assert result is None

    async def test_abstract_delete_body_executed_via_super(self):
        """Calling super().delete() executes the abstract method body."""
        repo = _SuperCallingRepo()
        result = await repo.delete("saga-1")
        assert result is True

    async def test_abstract_exists_body_executed_via_super(self):
        """Calling super().exists() executes the abstract method body."""
        repo = _SuperCallingRepo()
        result = await repo.exists("saga-1")
        assert result is False

    async def test_abstract_list_by_tenant_body_via_super(self):
        """Calling super().list_by_tenant() executes the abstract method body."""
        repo = _SuperCallingRepo()
        result = await repo.list_by_tenant("tenant-1")
        assert result == []

    async def test_abstract_list_by_tenant_with_state_via_super(self):
        """list_by_tenant with state filter via super()."""
        repo = _SuperCallingRepo()
        result = await repo.list_by_tenant("tenant-1", state=SagaState.RUNNING)
        assert result == []

    async def test_abstract_list_by_state_body_via_super(self):
        """Calling super().list_by_state() executes the abstract method body."""
        repo = _SuperCallingRepo()
        result = await repo.list_by_state(SagaState.RUNNING)
        assert result == []

    async def test_abstract_list_pending_compensations_body_via_super(self):
        """Calling super().list_pending_compensations() executes abstract body."""
        repo = _SuperCallingRepo()
        result = await repo.list_pending_compensations()
        assert result == []

    async def test_abstract_list_timed_out_body_via_super(self):
        """Calling super().list_timed_out() executes abstract body."""
        from datetime import datetime

        repo = _SuperCallingRepo()
        result = await repo.list_timed_out(datetime.now(UTC))
        assert result == []

    async def test_abstract_count_by_state_body_via_super(self):
        """Calling super().count_by_state() executes abstract body."""
        repo = _SuperCallingRepo()
        result = await repo.count_by_state(SagaState.RUNNING)
        assert result == 0

    async def test_abstract_count_by_tenant_body_via_super(self):
        """Calling super().count_by_tenant() executes abstract body."""
        repo = _SuperCallingRepo()
        result = await repo.count_by_tenant("tenant-1")
        assert result == 0

    async def test_abstract_update_state_body_via_super(self):
        """Calling super().update_state() executes abstract body."""
        repo = _SuperCallingRepo()
        result = await repo.update_state("saga-1", SagaState.RUNNING)
        assert result is True

    async def test_abstract_update_state_with_failure_reason_via_super(self):
        """update_state with failure_reason via super()."""
        repo = _SuperCallingRepo()
        result = await repo.update_state("saga-1", SagaState.FAILED, failure_reason="error")
        assert result is True

    async def test_abstract_update_step_state_body_via_super(self):
        """Calling super().update_step_state() executes abstract body."""
        repo = _SuperCallingRepo()
        result = await repo.update_step_state("saga-1", "step-1", None)  # type: ignore[arg-type]
        assert result is True

    async def test_abstract_update_current_step_body_via_super(self):
        """Calling super().update_current_step() executes abstract body."""
        repo = _SuperCallingRepo()
        result = await repo.update_current_step("saga-1", 0)
        assert result is True

    async def test_abstract_save_checkpoint_body_via_super(self):
        """Calling super().save_checkpoint() executes abstract body."""
        repo = _SuperCallingRepo()
        result = await repo.save_checkpoint(None)  # type: ignore[arg-type]
        assert result is True

    async def test_abstract_get_checkpoints_body_via_super(self):
        """Calling super().get_checkpoints() executes abstract body."""
        repo = _SuperCallingRepo()
        result = await repo.get_checkpoints("saga-1")
        assert result == []

    async def test_abstract_get_latest_checkpoint_body_via_super(self):
        """Calling super().get_latest_checkpoint() executes abstract body."""
        repo = _SuperCallingRepo()
        result = await repo.get_latest_checkpoint("saga-1")
        assert result is None

    async def test_abstract_delete_checkpoints_body_via_super(self):
        """Calling super().delete_checkpoints() executes abstract body."""
        repo = _SuperCallingRepo()
        result = await repo.delete_checkpoints("saga-1")
        assert result == 0

    async def test_abstract_append_compensation_entry_body_via_super(self):
        """Calling super().append_compensation_entry() executes abstract body."""
        repo = _SuperCallingRepo()
        result = await repo.append_compensation_entry("saga-1", None)  # type: ignore[arg-type]
        assert result is True

    async def test_abstract_get_compensation_log_body_via_super(self):
        """Calling super().get_compensation_log() executes abstract body."""
        repo = _SuperCallingRepo()
        result = await repo.get_compensation_log("saga-1")
        assert result == []

    async def test_abstract_acquire_lock_body_via_super(self):
        """Calling super().acquire_lock() executes abstract body."""
        repo = _SuperCallingRepo()
        result = await repo.acquire_lock("saga-1", "worker-1")
        assert result is True

    async def test_abstract_release_lock_body_via_super(self):
        """Calling super().release_lock() executes abstract body."""
        repo = _SuperCallingRepo()
        result = await repo.release_lock("saga-1", "worker-1")
        assert result is True

    async def test_abstract_extend_lock_body_via_super(self):
        """Calling super().extend_lock() executes abstract body."""
        repo = _SuperCallingRepo()
        result = await repo.extend_lock("saga-1", "worker-1")
        assert result is True

    async def test_abstract_cleanup_old_sagas_body_via_super(self):
        """Calling super().cleanup_old_sagas() executes abstract body."""
        from datetime import datetime

        repo = _SuperCallingRepo()
        result = await repo.cleanup_old_sagas(datetime.now(UTC))
        assert result == 0

    async def test_abstract_get_statistics_body_via_super(self):
        """Calling super().get_statistics() executes abstract body."""
        repo = _SuperCallingRepo()
        result = await repo.get_statistics()
        assert isinstance(result, dict)

    async def test_abstract_health_check_body_via_super(self):
        """Calling super().health_check() executes abstract body."""
        repo = _SuperCallingRepo()
        result = await repo.health_check()
        assert isinstance(result, dict)

    async def test_concrete_save_returns_true(self):
        """Concrete implementation save() works."""
        repo = _ConcreteRepo()
        result = await repo.save(None)  # type: ignore[arg-type]
        assert result is True

    async def test_concrete_get_returns_none(self):
        """Concrete implementation get() works."""
        repo = _ConcreteRepo()
        result = await repo.get("saga-123")
        assert result is None

    async def test_concrete_delete_returns_true(self):
        """Concrete implementation delete() works."""
        repo = _ConcreteRepo()
        result = await repo.delete("saga-123")
        assert result is True

    async def test_concrete_exists_returns_false(self):
        """Concrete implementation exists() works."""
        repo = _ConcreteRepo()
        result = await repo.exists("saga-123")
        assert result is False

    async def test_concrete_list_by_tenant_returns_empty(self):
        """Concrete implementation list_by_tenant() works."""
        repo = _ConcreteRepo()
        result = await repo.list_by_tenant("tenant-1")
        assert result == []

    async def test_concrete_list_by_state_returns_empty(self):
        """Concrete implementation list_by_state() works."""
        repo = _ConcreteRepo()
        result = await repo.list_by_state(SagaState.RUNNING)
        assert result == []

    async def test_concrete_list_pending_compensations_returns_empty(self):
        """Concrete implementation list_pending_compensations() works."""
        repo = _ConcreteRepo()
        result = await repo.list_pending_compensations()
        assert result == []

    async def test_concrete_list_timed_out_returns_empty(self):
        """Concrete implementation list_timed_out() works."""
        from datetime import datetime

        repo = _ConcreteRepo()
        result = await repo.list_timed_out(datetime.now(UTC))
        assert result == []

    async def test_concrete_count_by_state_returns_zero(self):
        """Concrete implementation count_by_state() works."""
        repo = _ConcreteRepo()
        result = await repo.count_by_state(SagaState.RUNNING)
        assert result == 0

    async def test_concrete_count_by_tenant_returns_zero(self):
        """Concrete implementation count_by_tenant() works."""
        repo = _ConcreteRepo()
        result = await repo.count_by_tenant("tenant-1")
        assert result == 0

    async def test_concrete_update_state_returns_true(self):
        """Concrete implementation update_state() works."""
        repo = _ConcreteRepo()
        result = await repo.update_state("saga-123", SagaState.RUNNING)
        assert result is True

    async def test_concrete_update_state_with_failure_reason(self):
        """Concrete update_state() accepts failure_reason."""
        repo = _ConcreteRepo()
        result = await repo.update_state("saga-123", SagaState.FAILED, "some error")
        assert result is True

    async def test_concrete_update_step_state_returns_true(self):
        """Concrete update_step_state() works."""
        repo = _ConcreteRepo()
        result = await repo.update_step_state("saga-123", "step-1", None)  # type: ignore[arg-type]
        assert result is True

    async def test_concrete_update_current_step_returns_true(self):
        """Concrete update_current_step() works."""
        repo = _ConcreteRepo()
        result = await repo.update_current_step("saga-123", 2)
        assert result is True

    async def test_concrete_save_checkpoint_returns_true(self):
        """Concrete save_checkpoint() works."""
        repo = _ConcreteRepo()
        result = await repo.save_checkpoint(None)  # type: ignore[arg-type]
        assert result is True

    async def test_concrete_get_checkpoints_returns_empty(self):
        """Concrete get_checkpoints() works."""
        repo = _ConcreteRepo()
        result = await repo.get_checkpoints("saga-123")
        assert result == []

    async def test_concrete_get_latest_checkpoint_returns_none(self):
        """Concrete get_latest_checkpoint() works."""
        repo = _ConcreteRepo()
        result = await repo.get_latest_checkpoint("saga-123")
        assert result is None

    async def test_concrete_delete_checkpoints_returns_zero(self):
        """Concrete delete_checkpoints() works."""
        repo = _ConcreteRepo()
        result = await repo.delete_checkpoints("saga-123")
        assert result == 0

    async def test_concrete_append_compensation_entry_returns_true(self):
        """Concrete append_compensation_entry() works."""
        repo = _ConcreteRepo()
        result = await repo.append_compensation_entry("saga-123", None)  # type: ignore[arg-type]
        assert result is True

    async def test_concrete_get_compensation_log_returns_empty(self):
        """Concrete get_compensation_log() works."""
        repo = _ConcreteRepo()
        result = await repo.get_compensation_log("saga-123")
        assert result == []

    async def test_concrete_acquire_lock_returns_true(self):
        """Concrete acquire_lock() works."""
        repo = _ConcreteRepo()
        result = await repo.acquire_lock("saga-123", "worker-1")
        assert result is True

    async def test_concrete_acquire_lock_custom_ttl(self):
        """Concrete acquire_lock() accepts custom ttl."""
        repo = _ConcreteRepo()
        result = await repo.acquire_lock("saga-123", "worker-1", ttl_seconds=60)
        assert result is True

    async def test_concrete_release_lock_returns_true(self):
        """Concrete release_lock() works."""
        repo = _ConcreteRepo()
        result = await repo.release_lock("saga-123", "worker-1")
        assert result is True

    async def test_concrete_extend_lock_returns_true(self):
        """Concrete extend_lock() works."""
        repo = _ConcreteRepo()
        result = await repo.extend_lock("saga-123", "worker-1")
        assert result is True

    async def test_concrete_extend_lock_custom_ttl(self):
        """Concrete extend_lock() accepts custom ttl."""
        repo = _ConcreteRepo()
        result = await repo.extend_lock("saga-123", "worker-1", ttl_seconds=120)
        assert result is True

    async def test_concrete_cleanup_old_sagas_returns_zero(self):
        """Concrete cleanup_old_sagas() works."""
        from datetime import datetime

        repo = _ConcreteRepo()
        result = await repo.cleanup_old_sagas(datetime.now(UTC))
        assert result == 0

    async def test_concrete_cleanup_old_sagas_terminal_false(self):
        """Concrete cleanup_old_sagas() accepts terminal_only=False."""
        from datetime import datetime

        repo = _ConcreteRepo()
        result = await repo.cleanup_old_sagas(datetime.now(UTC), terminal_only=False)
        assert result == 0

    async def test_concrete_get_statistics_returns_dict(self):
        """Concrete get_statistics() returns a dict."""
        repo = _ConcreteRepo()
        result = await repo.get_statistics()
        assert isinstance(result, dict)

    async def test_concrete_health_check_returns_dict(self):
        """Concrete health_check() returns a dict."""
        repo = _ConcreteRepo()
        result = await repo.health_check()
        assert isinstance(result, dict)
        assert result["status"] == "ok"


# ===========================================================================
# RepositoryError
# ===========================================================================


class TestRepositoryError:
    """Tests for RepositoryError exception class."""

    def test_basic_instantiation(self):
        """RepositoryError can be raised with just a message."""
        err = RepositoryError("storage failure")
        assert "storage failure" in str(err)

    def test_message_stored(self):
        """message attribute is set correctly."""
        err = RepositoryError("some message")
        assert err.message == "some message"

    def test_default_saga_id_none(self):
        """saga_id defaults to None when not provided."""
        err = RepositoryError("msg")
        assert err.saga_id is None

    def test_saga_id_stored(self):
        """saga_id is stored when provided."""
        err = RepositoryError("msg", saga_id="saga-abc")
        assert err.saga_id == "saga-abc"

    def test_http_status_code(self):
        """RepositoryError has HTTP 500 status."""
        err = RepositoryError("msg")
        assert err.http_status_code == 500

    def test_error_code(self):
        """RepositoryError has REPOSITORY_ERROR code."""
        err = RepositoryError("msg")
        assert err.error_code == "REPOSITORY_ERROR"

    def test_is_acgs_base_error(self):
        """RepositoryError inherits from ACGSBaseError."""
        from enhanced_agent_bus._compat.errors import ACGSBaseError

        err = RepositoryError("msg")
        assert isinstance(err, ACGSBaseError)

    def test_is_exception(self):
        """RepositoryError is catchable as Exception."""
        err = RepositoryError("msg")
        assert isinstance(err, RepositoryError)

    def test_can_be_raised(self):
        """RepositoryError can be raised and caught."""
        with pytest.raises(RepositoryError):
            raise RepositoryError("database down")

    def test_details_contain_saga_id(self):
        """details dict includes saga_id."""
        err = RepositoryError("msg", saga_id="saga-xyz")
        assert err.details.get("saga_id") == "saga-xyz"

    def test_details_with_none_saga_id(self):
        """details dict includes None saga_id."""
        err = RepositoryError("msg")
        assert "saga_id" in err.details
        assert err.details["saga_id"] is None

    def test_empty_message(self):
        """RepositoryError works with empty message."""
        err = RepositoryError("")
        assert err.message == ""

    def test_long_message(self):
        """RepositoryError works with long message."""
        long_msg = "x" * 1000
        err = RepositoryError(long_msg)
        assert err.message == long_msg

    def test_to_dict_contains_error_code(self):
        """to_dict() includes REPOSITORY_ERROR error code."""
        err = RepositoryError("msg")
        d = err.to_dict()
        assert d["error"] == "REPOSITORY_ERROR"

    def test_to_dict_contains_message(self):
        """to_dict() includes the error message."""
        err = RepositoryError("specific failure")
        d = err.to_dict()
        assert d["message"] == "specific failure"

    def test_constitutional_hash_in_error(self):
        """RepositoryError carries the constitutional hash."""
        err = RepositoryError("msg")
        assert err.constitutional_hash == CONSTITUTIONAL_HASH

    def test_saga_id_with_special_characters(self):
        """saga_id handles special characters."""
        err = RepositoryError("msg", saga_id="saga-123_abc.xyz")
        assert err.saga_id == "saga-123_abc.xyz"


# ===========================================================================
# SagaNotFoundError
# ===========================================================================


class TestSagaNotFoundError:
    """Tests for SagaNotFoundError exception class."""

    def test_basic_instantiation(self):
        """SagaNotFoundError can be raised."""
        err = SagaNotFoundError("saga not found")
        assert "saga not found" in str(err)

    def test_http_status_code(self):
        """SagaNotFoundError has HTTP 404 status."""
        err = SagaNotFoundError("not found")
        assert err.http_status_code == 404

    def test_error_code(self):
        """SagaNotFoundError has SAGA_NOT_FOUND error code."""
        err = SagaNotFoundError("not found")
        assert err.error_code == "SAGA_NOT_FOUND"

    def test_inherits_from_repository_error(self):
        """SagaNotFoundError inherits from RepositoryError."""
        err = SagaNotFoundError("not found")
        assert isinstance(err, RepositoryError)

    def test_saga_id_stored(self):
        """saga_id is stored when provided."""
        err = SagaNotFoundError("not found", saga_id="saga-missing")
        assert err.saga_id == "saga-missing"

    def test_saga_id_default_none(self):
        """saga_id defaults to None."""
        err = SagaNotFoundError("not found")
        assert err.saga_id is None

    def test_can_be_raised_and_caught(self):
        """SagaNotFoundError can be raised and caught as RepositoryError."""
        with pytest.raises(RepositoryError):
            raise SagaNotFoundError("saga not found", saga_id="saga-abc")

    def test_can_be_raised_and_caught_as_not_found(self):
        """SagaNotFoundError can be caught as SagaNotFoundError."""
        with pytest.raises(SagaNotFoundError):
            raise SagaNotFoundError("missing")

    def test_message_stored(self):
        """message attribute is stored."""
        err = SagaNotFoundError("saga-123 does not exist")
        assert err.message == "saga-123 does not exist"

    def test_to_dict_error_code(self):
        """to_dict() returns SAGA_NOT_FOUND code."""
        err = SagaNotFoundError("not found")
        d = err.to_dict()
        assert d["error"] == "SAGA_NOT_FOUND"

    def test_details_with_saga_id(self):
        """details contain saga_id."""
        err = SagaNotFoundError("not found", saga_id="saga-404")
        assert err.details.get("saga_id") == "saga-404"

    def test_constitutional_hash_present(self):
        """SagaNotFoundError includes constitutional hash."""
        err = SagaNotFoundError("not found")
        assert err.constitutional_hash == CONSTITUTIONAL_HASH

    def test_is_also_exception(self):
        """SagaNotFoundError can be caught as Exception."""
        with pytest.raises(SagaNotFoundError):
            raise SagaNotFoundError("not found")


# ===========================================================================
# VersionConflictError
# ===========================================================================


class TestVersionConflictError:
    """Tests for VersionConflictError exception class."""

    def test_basic_instantiation(self):
        """VersionConflictError can be instantiated."""
        err = VersionConflictError("saga-1", expected_version=2, actual_version=3)
        assert err is not None

    def test_http_status_code(self):
        """VersionConflictError has HTTP 409 status."""
        err = VersionConflictError("saga-1", 2, 3)
        assert err.http_status_code == 409

    def test_error_code(self):
        """VersionConflictError has VERSION_CONFLICT error code."""
        err = VersionConflictError("saga-1", 2, 3)
        assert err.error_code == "VERSION_CONFLICT"

    def test_inherits_from_repository_error(self):
        """VersionConflictError inherits from RepositoryError."""
        err = VersionConflictError("saga-1", 2, 3)
        assert isinstance(err, RepositoryError)

    def test_expected_version_stored(self):
        """expected_version is stored."""
        err = VersionConflictError("saga-1", expected_version=5, actual_version=7)
        assert err.expected_version == 5

    def test_actual_version_stored(self):
        """actual_version is stored."""
        err = VersionConflictError("saga-1", expected_version=5, actual_version=7)
        assert err.actual_version == 7

    def test_saga_id_stored(self):
        """saga_id is stored."""
        err = VersionConflictError("my-saga-id", 1, 2)
        assert err.saga_id == "my-saga-id"

    def test_message_contains_saga_id(self):
        """Generated message contains saga_id."""
        err = VersionConflictError("saga-abc", 1, 2)
        assert "saga-abc" in err.message

    def test_message_contains_expected_version(self):
        """Generated message contains expected_version."""
        err = VersionConflictError("saga-abc", expected_version=10, actual_version=12)
        assert "10" in err.message

    def test_message_contains_actual_version(self):
        """Generated message contains actual_version."""
        err = VersionConflictError("saga-abc", expected_version=10, actual_version=12)
        assert "12" in err.message

    def test_message_format(self):
        """Message matches the expected format."""
        err = VersionConflictError("saga-xyz", 3, 5)
        assert "Version conflict for saga saga-xyz" in err.message
        assert "expected 3" in err.message
        assert "got 5" in err.message

    def test_can_be_raised(self):
        """VersionConflictError can be raised."""
        with pytest.raises(VersionConflictError):
            raise VersionConflictError("saga-1", 1, 2)

    def test_can_be_caught_as_repository_error(self):
        """VersionConflictError can be caught as RepositoryError."""
        with pytest.raises(RepositoryError):
            raise VersionConflictError("saga-1", 1, 2)

    def test_version_zero(self):
        """VersionConflictError handles version 0."""
        err = VersionConflictError("saga-1", expected_version=0, actual_version=1)
        assert err.expected_version == 0
        assert err.actual_version == 1

    def test_large_version_numbers(self):
        """VersionConflictError handles large version numbers."""
        err = VersionConflictError("saga-1", expected_version=999999, actual_version=1000000)
        assert err.expected_version == 999999
        assert err.actual_version == 1000000

    def test_negative_version(self):
        """VersionConflictError handles negative version numbers."""
        err = VersionConflictError("saga-1", expected_version=-1, actual_version=0)
        assert err.expected_version == -1

    def test_to_dict_error_code(self):
        """to_dict() includes VERSION_CONFLICT code."""
        err = VersionConflictError("saga-1", 2, 3)
        d = err.to_dict()
        assert d["error"] == "VERSION_CONFLICT"

    def test_to_dict_message(self):
        """to_dict() includes the message."""
        err = VersionConflictError("saga-1", 2, 3)
        d = err.to_dict()
        assert "saga-1" in d["message"]

    def test_constitutional_hash_present(self):
        """VersionConflictError includes constitutional hash."""
        err = VersionConflictError("saga-1", 1, 2)
        assert err.constitutional_hash == CONSTITUTIONAL_HASH

    def test_details_contain_saga_id(self):
        """details dict includes saga_id."""
        err = VersionConflictError("saga-v1", 1, 2)
        assert err.details.get("saga_id") == "saga-v1"

    def test_same_version_numbers(self):
        """VersionConflictError can have same expected and actual (unusual but valid)."""
        err = VersionConflictError("saga-1", expected_version=5, actual_version=5)
        assert err.expected_version == 5
        assert err.actual_version == 5


# ===========================================================================
# InvalidStateTransitionError
# ===========================================================================


class TestInvalidStateTransitionError:
    """Tests for InvalidStateTransitionError exception class."""

    def test_basic_instantiation(self):
        """InvalidStateTransitionError can be instantiated."""
        err = InvalidStateTransitionError("saga-1", SagaState.RUNNING, SagaState.INITIALIZED)
        assert err is not None

    def test_http_status_code(self):
        """InvalidStateTransitionError has HTTP 400 status."""
        err = InvalidStateTransitionError("saga-1", SagaState.RUNNING, SagaState.INITIALIZED)
        assert err.http_status_code == 400

    def test_error_code(self):
        """InvalidStateTransitionError has INVALID_STATE_TRANSITION error code."""
        err = InvalidStateTransitionError("saga-1", SagaState.RUNNING, SagaState.INITIALIZED)
        assert err.error_code == "INVALID_STATE_TRANSITION"

    def test_inherits_from_repository_error(self):
        """InvalidStateTransitionError inherits from RepositoryError."""
        err = InvalidStateTransitionError("saga-1", SagaState.RUNNING, SagaState.INITIALIZED)
        assert isinstance(err, RepositoryError)

    def test_current_state_stored(self):
        """current_state attribute is stored."""
        err = InvalidStateTransitionError("saga-1", SagaState.COMPLETED, SagaState.RUNNING)
        assert err.current_state == SagaState.COMPLETED

    def test_target_state_stored(self):
        """target_state attribute is stored."""
        err = InvalidStateTransitionError("saga-1", SagaState.COMPLETED, SagaState.RUNNING)
        assert err.target_state == SagaState.RUNNING

    def test_saga_id_stored(self):
        """saga_id attribute is stored."""
        err = InvalidStateTransitionError("my-saga", SagaState.RUNNING, SagaState.INITIALIZED)
        assert err.saga_id == "my-saga"

    def test_message_contains_saga_id(self):
        """Message includes saga_id."""
        err = InvalidStateTransitionError("saga-abc", SagaState.RUNNING, SagaState.INITIALIZED)
        assert "saga-abc" in err.message

    def test_message_contains_current_state_value(self):
        """Message includes the current state value."""
        err = InvalidStateTransitionError("saga-1", SagaState.RUNNING, SagaState.INITIALIZED)
        assert "RUNNING" in err.message

    def test_message_contains_target_state_value(self):
        """Message includes the target state value."""
        err = InvalidStateTransitionError("saga-1", SagaState.RUNNING, SagaState.INITIALIZED)
        assert "INITIALIZED" in err.message

    def test_message_format(self):
        """Message matches expected format."""
        err = InvalidStateTransitionError("saga-xyz", SagaState.COMPLETED, SagaState.RUNNING)
        assert "Invalid state transition for saga saga-xyz" in err.message
        assert "COMPLETED -> RUNNING" in err.message

    def test_all_state_combinations_can_be_created(self):
        """InvalidStateTransitionError can be created for all state combinations."""
        states = list(SagaState)
        for current in states:
            for target in states:
                err = InvalidStateTransitionError("saga-1", current, target)
                assert err.current_state == current
                assert err.target_state == target

    def test_can_be_raised(self):
        """InvalidStateTransitionError can be raised."""
        with pytest.raises(InvalidStateTransitionError):
            raise InvalidStateTransitionError("saga-1", SagaState.COMPLETED, SagaState.RUNNING)

    def test_can_be_caught_as_repository_error(self):
        """InvalidStateTransitionError can be caught as RepositoryError."""
        with pytest.raises(RepositoryError):
            raise InvalidStateTransitionError("saga-1", SagaState.COMPLETED, SagaState.RUNNING)

    def test_to_dict_error_code(self):
        """to_dict() includes INVALID_STATE_TRANSITION code."""
        err = InvalidStateTransitionError("saga-1", SagaState.RUNNING, SagaState.INITIALIZED)
        d = err.to_dict()
        assert d["error"] == "INVALID_STATE_TRANSITION"

    def test_to_dict_message(self):
        """to_dict() includes the message."""
        err = InvalidStateTransitionError("saga-1", SagaState.RUNNING, SagaState.INITIALIZED)
        d = err.to_dict()
        assert "saga-1" in d["message"]

    def test_details_contain_saga_id(self):
        """details dict includes saga_id."""
        err = InvalidStateTransitionError("saga-detail", SagaState.RUNNING, SagaState.COMPLETED)
        assert err.details.get("saga_id") == "saga-detail"

    def test_constitutional_hash_present(self):
        """InvalidStateTransitionError includes constitutional hash."""
        err = InvalidStateTransitionError("saga-1", SagaState.RUNNING, SagaState.INITIALIZED)
        assert err.constitutional_hash == CONSTITUTIONAL_HASH

    def test_initialized_to_failed_transition(self):
        """INITIALIZED to FAILED transition can be represented."""
        err = InvalidStateTransitionError("saga-1", SagaState.INITIALIZED, SagaState.FAILED)
        assert err.current_state == SagaState.INITIALIZED
        assert err.target_state == SagaState.FAILED

    def test_compensating_to_completed_transition(self):
        """COMPENSATING to COMPLETED transition can be represented."""
        err = InvalidStateTransitionError("saga-1", SagaState.COMPENSATING, SagaState.COMPLETED)
        assert err.current_state == SagaState.COMPENSATING
        assert err.target_state == SagaState.COMPLETED

    def test_terminal_to_running_transition(self):
        """COMPLETED to RUNNING (terminal -> active) can be represented."""
        err = InvalidStateTransitionError("saga-1", SagaState.COMPLETED, SagaState.RUNNING)
        assert err.current_state == SagaState.COMPLETED
        assert err.target_state == SagaState.RUNNING

    def test_is_exception(self):
        """InvalidStateTransitionError is catchable as Exception."""
        with pytest.raises(InvalidStateTransitionError):
            raise InvalidStateTransitionError("saga-1", SagaState.RUNNING, SagaState.INITIALIZED)


# ===========================================================================
# LockError
# ===========================================================================


class TestLockError:
    """Tests for LockError exception class."""

    def test_basic_instantiation(self):
        """LockError can be instantiated."""
        err = LockError("lock acquisition failed")
        assert err is not None

    def test_http_status_code(self):
        """LockError has HTTP 423 status (Locked)."""
        err = LockError("lock failed")
        assert err.http_status_code == 423

    def test_error_code(self):
        """LockError has LOCK_ERROR error code."""
        err = LockError("lock failed")
        assert err.error_code == "LOCK_ERROR"

    def test_inherits_from_repository_error(self):
        """LockError inherits from RepositoryError."""
        err = LockError("lock failed")
        assert isinstance(err, RepositoryError)

    def test_saga_id_stored(self):
        """saga_id can be stored."""
        err = LockError("lock failed", saga_id="saga-locked")
        assert err.saga_id == "saga-locked"

    def test_saga_id_default_none(self):
        """saga_id defaults to None."""
        err = LockError("lock failed")
        assert err.saga_id is None

    def test_message_stored(self):
        """message is stored."""
        err = LockError("cannot acquire distributed lock")
        assert err.message == "cannot acquire distributed lock"

    def test_can_be_raised(self):
        """LockError can be raised."""
        with pytest.raises(LockError):
            raise LockError("lock already held")

    def test_can_be_caught_as_repository_error(self):
        """LockError can be caught as RepositoryError."""
        with pytest.raises(RepositoryError):
            raise LockError("lock failed")

    def test_to_dict_error_code(self):
        """to_dict() includes LOCK_ERROR code."""
        err = LockError("lock failed")
        d = err.to_dict()
        assert d["error"] == "LOCK_ERROR"

    def test_to_dict_message(self):
        """to_dict() includes the message."""
        err = LockError("lock contention")
        d = err.to_dict()
        assert d["message"] == "lock contention"

    def test_details_with_saga_id(self):
        """details include saga_id."""
        err = LockError("lock failed", saga_id="saga-lock-test")
        assert err.details.get("saga_id") == "saga-lock-test"

    def test_constitutional_hash_present(self):
        """LockError includes constitutional hash."""
        err = LockError("lock failed")
        assert err.constitutional_hash == CONSTITUTIONAL_HASH

    def test_is_exception(self):
        """LockError is catchable as Exception."""
        with pytest.raises(LockError):
            raise LockError("lock failed")


# ===========================================================================
# Exception hierarchy tests
# ===========================================================================


class TestExceptionHierarchy:
    """Tests verifying the correct exception hierarchy."""

    def test_all_errors_inherit_from_repository_error(self):
        """All custom exceptions inherit from RepositoryError."""
        assert issubclass(SagaNotFoundError, RepositoryError)
        assert issubclass(VersionConflictError, RepositoryError)
        assert issubclass(InvalidStateTransitionError, RepositoryError)
        assert issubclass(LockError, RepositoryError)

    def test_repository_error_inherits_from_acgs_base(self):
        """RepositoryError inherits from ACGSBaseError."""
        from enhanced_agent_bus._compat.errors import ACGSBaseError

        assert issubclass(RepositoryError, ACGSBaseError)

    def test_all_errors_inherit_from_acgs_base(self):
        """All errors indirectly inherit from ACGSBaseError."""
        from enhanced_agent_bus._compat.errors import ACGSBaseError

        for cls in [
            SagaNotFoundError,
            VersionConflictError,
            InvalidStateTransitionError,
            LockError,
        ]:
            assert issubclass(cls, ACGSBaseError)

    def test_all_errors_are_exceptions(self):
        """All errors can be caught as Exception."""
        for cls in [
            RepositoryError,
            SagaNotFoundError,
            VersionConflictError,
            InvalidStateTransitionError,
            LockError,
        ]:
            assert issubclass(cls, Exception)

    def test_http_status_codes_correct(self):
        """HTTP status codes match expected values."""
        assert RepositoryError.http_status_code == 500
        assert SagaNotFoundError.http_status_code == 404
        assert VersionConflictError.http_status_code == 409
        assert InvalidStateTransitionError.http_status_code == 400
        assert LockError.http_status_code == 423

    def test_error_codes_correct(self):
        """Error codes match expected values."""
        assert RepositoryError.error_code == "REPOSITORY_ERROR"
        assert SagaNotFoundError.error_code == "SAGA_NOT_FOUND"
        assert VersionConflictError.error_code == "VERSION_CONFLICT"
        assert InvalidStateTransitionError.error_code == "INVALID_STATE_TRANSITION"
        assert LockError.error_code == "LOCK_ERROR"

    def test_catching_as_repository_error(self):
        """All subclasses can be caught as RepositoryError."""
        errors = [
            SagaNotFoundError("not found"),
            VersionConflictError("saga-1", 1, 2),
            InvalidStateTransitionError("saga-1", SagaState.RUNNING, SagaState.INITIALIZED),
            LockError("lock failed"),
        ]
        for err in errors:
            with pytest.raises(RepositoryError):
                raise err

    def test_distinct_http_status_codes(self):
        """Each exception class has a distinct HTTP status code."""
        codes = {
            RepositoryError.http_status_code,
            SagaNotFoundError.http_status_code,
            VersionConflictError.http_status_code,
            InvalidStateTransitionError.http_status_code,
            LockError.http_status_code,
        }
        assert len(codes) == 5  # all distinct


# ===========================================================================
# __all__ export list
# ===========================================================================


class TestModuleExports:
    """Tests verifying the module's __all__ export list."""

    def test_all_exports_defined(self):
        """All names in __all__ are importable."""
        import importlib

        mod = importlib.import_module("enhanced_agent_bus.saga_persistence.repository")
        for name in mod.__all__:
            assert hasattr(mod, name), f"{name} not found in module"

    def test_all_contains_expected_names(self):
        """__all__ contains all expected names."""
        from enhanced_agent_bus.saga_persistence import repository

        expected = {
            "SagaStateRepository",
            "RepositoryError",
            "SagaNotFoundError",
            "VersionConflictError",
            "InvalidStateTransitionError",
            "LockError",
        }
        assert expected.issubset(set(repository.__all__))


# ===========================================================================
# Additional edge-case and integration tests
# ===========================================================================


class TestEdgeCases:
    """Edge cases and corner-case tests."""

    def test_repository_error_empty_saga_id(self):
        """RepositoryError accepts empty string saga_id."""
        err = RepositoryError("msg", saga_id="")
        assert err.saga_id == ""

    def test_version_conflict_version_one_to_two(self):
        """VersionConflictError common version bump scenario."""
        err = VersionConflictError("saga-1", expected_version=1, actual_version=2)
        assert err.expected_version == 1
        assert err.actual_version == 2
        assert "expected 1" in err.message
        assert "got 2" in err.message

    def test_invalid_state_transition_all_terminal_states(self):
        """InvalidStateTransitionError covers all terminal source states."""
        for terminal in [SagaState.COMPLETED, SagaState.COMPENSATED, SagaState.FAILED]:
            err = InvalidStateTransitionError("saga-1", terminal, SagaState.RUNNING)
            assert err.current_state == terminal
            assert terminal.value in err.message

    def test_lock_error_with_empty_saga_id(self):
        """LockError handles empty saga_id."""
        err = LockError("lock failed", saga_id="")
        assert err.saga_id == ""

    def test_saga_not_found_with_uuid_style_id(self):
        """SagaNotFoundError with UUID-style saga_id."""
        import uuid

        saga_id = str(uuid.uuid4())
        err = SagaNotFoundError(f"Saga {saga_id} not found", saga_id=saga_id)
        assert err.saga_id == saga_id

    def test_repository_error_to_dict_has_constitutional_hash(self):
        """to_dict() always includes the constitutional hash."""
        for err in [
            RepositoryError("msg"),
            SagaNotFoundError("not found"),
            LockError("lock"),
        ]:
            d = err.to_dict()
            assert "constitutional_hash" in d
            assert d["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_version_conflict_to_dict_constitutional_hash(self):
        """VersionConflictError.to_dict() includes constitutional hash."""
        err = VersionConflictError("saga-1", 1, 2)
        d = err.to_dict()
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_invalid_transition_to_dict_constitutional_hash(self):
        """InvalidStateTransitionError.to_dict() includes constitutional hash."""
        err = InvalidStateTransitionError("saga-1", SagaState.RUNNING, SagaState.INITIALIZED)
        d = err.to_dict()
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_multiple_repository_errors_independent(self):
        """Multiple RepositoryError instances are independent."""
        err1 = RepositoryError("first", saga_id="saga-1")
        err2 = RepositoryError("second", saga_id="saga-2")
        assert err1.saga_id != err2.saga_id
        assert err1.message != err2.message

    def test_version_conflict_symmetric_constructor(self):
        """VersionConflictError stores both positional args."""
        err = VersionConflictError("saga-sym", 100, 200)
        assert err.expected_version == 100
        assert err.actual_version == 200

    def test_concrete_repo_isinstance_check(self):
        """_ConcreteRepo is an instance of SagaStateRepository."""
        repo = _ConcreteRepo()
        assert isinstance(repo, SagaStateRepository)
        assert issubclass(_ConcreteRepo, SagaStateRepository)

    def test_saga_state_all_values_accessible(self):
        """All SagaState enum values are accessible and work in errors."""
        for state in SagaState:
            err = InvalidStateTransitionError("saga-1", state, SagaState.FAILED)
            assert err.current_state == state

    def test_repository_error_timestamp_present(self):
        """RepositoryError includes a timestamp in to_dict()."""
        err = RepositoryError("msg")
        d = err.to_dict()
        assert "timestamp" in d

    def test_repository_error_correlation_id_present(self):
        """RepositoryError includes a correlation_id in to_dict()."""
        err = RepositoryError("msg")
        d = err.to_dict()
        assert "correlation_id" in d
        assert d["correlation_id"]  # non-empty
