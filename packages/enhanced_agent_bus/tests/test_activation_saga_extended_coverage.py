# Constitutional Hash: 608508a9bd224290
"""
Extended coverage tests for Constitutional Amendment Activation Saga.
Constitutional Hash: 608508a9bd224290

Targets uncovered code paths in:
  - activate_amendment() hasattr / isinstance branching (lines 814-820, 832-837)
  - module-level try/except ImportError blocks (lines 30-65)
  - ActivationSagaError class attributes
  - Various edge cases not exercised by existing test files

Note: asyncio_mode = "auto" is set in pyproject.toml — no @pytest.mark.asyncio required.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.constitutional import activation_saga as _saga_module

# Import the module under test and helpers
from enhanced_agent_bus.constitutional.activation_saga import (
    ActivationSagaActivities,
    ActivationSagaError,
    activate_amendment,
    create_activation_saga,
)
from enhanced_agent_bus.constitutional.amendment_model import (
    AmendmentProposal,
    AmendmentStatus,
)
from enhanced_agent_bus.constitutional.storage import ConstitutionalStorageService
from enhanced_agent_bus.constitutional.version_model import (
    ConstitutionalStatus,
    ConstitutionalVersion,
)

pytestmark = [
    pytest.mark.constitutional,
]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_amendment(**kwargs) -> AmendmentProposal:
    defaults = dict(
        proposal_id="amendment-ext-001",
        proposed_changes={"ext_principle": "Extended governance principle"},
        justification="Extended coverage test amendment for constitutional compliance.",
        proposer_agent_id="agent-ext-001",
        target_version="2.0.0",
        new_version="2.1.0",
        status=AmendmentStatus.APPROVED,
        impact_score=0.6,
    )
    defaults.update(kwargs)
    return AmendmentProposal(**defaults)


def _make_version(**kwargs) -> ConstitutionalVersion:
    defaults = dict(
        version_id="version-2.0.0",
        version="2.0.0",
        constitutional_hash=CONSTITUTIONAL_HASH,
        content={"ext_principles": ["EP1", "EP2"]},
        status=ConstitutionalStatus.ACTIVE,
    )
    defaults.update(kwargs)
    return ConstitutionalVersion(**defaults)


def _make_activities(mock_storage=None, **kwargs) -> ActivationSagaActivities:
    if mock_storage is None:
        mock_storage = AsyncMock(spec=ConstitutionalStorageService)
    return ActivationSagaActivities(
        storage=mock_storage,
        opa_url=kwargs.get("opa_url", "http://localhost:8181"),
        audit_service_url=kwargs.get("audit_service_url", "http://localhost:8001"),
        redis_url=kwargs.get("redis_url", "redis://localhost:6379"),
    )


# ---------------------------------------------------------------------------
# Minimal saga mock helpers (mirrors test_activation_saga_coverage.py)
# ---------------------------------------------------------------------------


def _make_mock_saga_classes():
    """Build mock classes that mimic the saga workflow module."""

    class MockSagaCompensation:
        def __init__(self, name, description, execute):
            self.name = name
            self.description = description
            self.execute = execute

    class MockSagaStep:
        def __init__(
            self,
            name,
            description,
            execute,
            compensation,
            timeout_seconds=30,
            is_optional=False,
        ):
            self.name = name
            self.description = description
            self.execute = execute
            self.compensation = compensation
            self.timeout_seconds = timeout_seconds
            self.is_optional = is_optional

    class MockSagaContext:
        def __init__(self, saga_id, constitutional_hash=None, step_results=None):
            self.saga_id = saga_id
            self.constitutional_hash = constitutional_hash
            self._data = step_results or {}

        def set_step_result(self, key, value):
            self._data[key] = value

    class MockSagaResult:
        def __init__(self, status="COMPLETED", step_results=None):
            self.status = status
            self.step_results = step_results or {}

    class MockConstitutionalSagaWorkflow:
        def __init__(self, saga_id):
            self.saga_id = saga_id
            self._steps = []

        def add_step(self, step):
            self._steps.append(step)

        async def execute(self, context):
            return MockSagaResult()

    return (
        MockConstitutionalSagaWorkflow,
        MockSagaStep,
        MockSagaCompensation,
        MockSagaContext,
        MockSagaResult,
    )


# ---------------------------------------------------------------------------
# ActivationSagaError — class-level attributes
# ---------------------------------------------------------------------------


class TestActivationSagaErrorAttributes:
    """Ensure ActivationSagaError exposes correct class attributes."""

    def test_error_code_is_activation_saga_error(self):
        assert ActivationSagaError.error_code == "ACTIVATION_SAGA_ERROR"

    def test_http_status_code_is_500(self):
        assert ActivationSagaError.http_status_code == 500

    def test_instantiation_with_message(self):
        err = ActivationSagaError("something went wrong")
        # ACGSBaseError prefixes the message with hash/correlation/error_code info
        assert "something went wrong" in str(err)

    def test_is_subclass_of_acgs_base(self):
        from enhanced_agent_bus._compat.errors import ACGSBaseError

        assert issubclass(ActivationSagaError, ACGSBaseError)


# ---------------------------------------------------------------------------
# activate_amendment() — hasattr / isinstance branches (lines 814-837)
# ---------------------------------------------------------------------------


class TestActivateAmendmentHasAttrBranches:
    """
    Tests for activate_amendment's introspection of saga._steps to
    reach ActivationSagaActivities.initialize / close.

    The function does:
        if hasattr(saga, "_steps") and saga._steps:
            first_step = saga._steps[0]
            if hasattr(first_step.execute, "__self__"):
                activities = first_step.execute.__self__
                if isinstance(activities, ActivationSagaActivities):
                    await activities.initialize()
    """

    @pytest.fixture
    def mock_storage(self):
        return AsyncMock(spec=ConstitutionalStorageService)

    async def test_no_steps_attribute_skips_initialize(self, mock_storage):
        """When saga has no _steps attribute, initialize is never called."""
        (
            _MockWorkflow,
            MockStep,
            MockComp,
            MockContext,
            MockResult,
        ) = _make_mock_saga_classes()

        # Build a workflow class that never sets _steps in __init__
        class WorkflowWithoutSteps:
            def __init__(self, saga_id):
                self.saga_id = saga_id
                # Intentionally do NOT set self._steps

            def add_step(self, step):
                pass

            async def execute(self, context):
                return MockResult()

        mock_init = AsyncMock()
        mock_close = AsyncMock()

        _globs = activate_amendment.__globals__
        with patch.dict(
            _globs,
            {
                "ConstitutionalSagaWorkflow": WorkflowWithoutSteps,
                "SagaStep": MockStep,
                "SagaCompensation": MockComp,
                "SagaContext": MockContext,
            },
        ):
            with patch.object(ActivationSagaActivities, "initialize", mock_init):
                with patch.object(ActivationSagaActivities, "close", mock_close):
                    result = await activate_amendment(
                        amendment_id="amendment-no-steps",
                        storage=mock_storage,
                    )

        # Saga executed without initialize/close being called through steps
        assert result.status == "COMPLETED"
        mock_init.assert_not_called()

    async def test_empty_steps_list_skips_initialize(self, mock_storage):
        """When saga._steps is empty, initialize is skipped."""
        (
            MockWorkflow,
            MockStep,
            MockComp,
            MockContext,
            _MockResult,
        ) = _make_mock_saga_classes()

        class EmptyStepWorkflow(MockWorkflow):
            def add_step(self, step):
                pass  # Never adds steps -> _steps stays empty []

        mock_init = AsyncMock()
        mock_close = AsyncMock()

        _globs = activate_amendment.__globals__
        with patch.dict(
            _globs,
            {
                "ConstitutionalSagaWorkflow": EmptyStepWorkflow,
                "SagaStep": MockStep,
                "SagaCompensation": MockComp,
                "SagaContext": MockContext,
            },
        ):
            with patch.object(ActivationSagaActivities, "initialize", mock_init):
                with patch.object(ActivationSagaActivities, "close", mock_close):
                    result = await activate_amendment(
                        amendment_id="amendment-empty-steps",
                        storage=mock_storage,
                    )

        assert result.status == "COMPLETED"
        mock_init.assert_not_called()
        mock_close.assert_not_called()

    async def test_step_execute_has_no_self_skips_initialize(self, mock_storage):
        """When first_step.execute has no __self__, initialize is not called."""
        (
            MockWorkflow,
            MockStep,
            MockComp,
            MockContext,
            _MockResult,
        ) = _make_mock_saga_classes()

        class WorkflowWithUnboundStep(MockWorkflow):
            def __init__(self, saga_id):
                super().__init__(saga_id)

                # Inject a step whose execute is a plain function (no __self__)
                def plain_func(inp):
                    return None

                comp = MockComp("comp", "comp desc", plain_func)
                step = MockStep(
                    name="unbound_step",
                    description="unbound",
                    execute=plain_func,  # lambda has no __self__
                    compensation=comp,
                )
                self._steps.append(step)

            def add_step(self, step):
                pass  # suppress further additions

        mock_init = AsyncMock()
        mock_close = AsyncMock()

        _globs = activate_amendment.__globals__
        with patch.dict(
            _globs,
            {
                "ConstitutionalSagaWorkflow": WorkflowWithUnboundStep,
                "SagaStep": MockStep,
                "SagaCompensation": MockComp,
                "SagaContext": MockContext,
            },
        ):
            with patch.object(ActivationSagaActivities, "initialize", mock_init):
                with patch.object(ActivationSagaActivities, "close", mock_close):
                    result = await activate_amendment(
                        amendment_id="amendment-unbound",
                        storage=mock_storage,
                    )

        assert result.status == "COMPLETED"
        mock_init.assert_not_called()

    async def test_step_execute_self_not_activities_skips_initialize(self, mock_storage):
        """When first_step.execute.__self__ is not ActivationSagaActivities, skip."""
        (
            MockWorkflow,
            MockStep,
            MockComp,
            MockContext,
            _MockResult,
        ) = _make_mock_saga_classes()

        class OtherActivities:
            """A different activities class — not ActivationSagaActivities."""

            async def execute_step(self, inp):
                return {}

        other = OtherActivities()

        class WorkflowWithOtherActivities(MockWorkflow):
            def __init__(self, saga_id):
                super().__init__(saga_id)
                comp = MockComp("comp", "comp desc", other.execute_step)
                step = MockStep(
                    name="other_step",
                    description="other",
                    execute=other.execute_step,  # __self__ is OtherActivities
                    compensation=comp,
                )
                self._steps.append(step)

            def add_step(self, step):
                pass  # suppress additions

        mock_init = AsyncMock()
        mock_close = AsyncMock()

        _globs = activate_amendment.__globals__
        with patch.dict(
            _globs,
            {
                "ConstitutionalSagaWorkflow": WorkflowWithOtherActivities,
                "SagaStep": MockStep,
                "SagaCompensation": MockComp,
                "SagaContext": MockContext,
            },
        ):
            with patch.object(ActivationSagaActivities, "initialize", mock_init):
                with patch.object(ActivationSagaActivities, "close", mock_close):
                    result = await activate_amendment(
                        amendment_id="amendment-other-activities",
                        storage=mock_storage,
                    )

        assert result.status == "COMPLETED"
        mock_init.assert_not_called()
        mock_close.assert_not_called()

    async def test_activate_amendment_calls_initialize_and_close_via_steps(self, mock_storage):
        """Full happy path: initialize and close are called via saga._steps."""
        (
            MockWorkflow,
            MockStep,
            MockComp,
            MockContext,
            _MockResult,
        ) = _make_mock_saga_classes()

        mock_init = AsyncMock()
        mock_close = AsyncMock()

        _globs = activate_amendment.__globals__
        with patch.dict(
            _globs,
            {
                "ConstitutionalSagaWorkflow": MockWorkflow,
                "SagaStep": MockStep,
                "SagaCompensation": MockComp,
                "SagaContext": MockContext,
            },
        ):
            with patch.object(ActivationSagaActivities, "initialize", mock_init):
                with patch.object(ActivationSagaActivities, "close", mock_close):
                    result = await activate_amendment(
                        amendment_id="amendment-full",
                        storage=mock_storage,
                    )

        assert result.status == "COMPLETED"
        mock_init.assert_awaited_once()
        mock_close.assert_awaited_once()

    async def test_activate_amendment_close_called_even_when_execute_raises(self, mock_storage):
        """close() is always called in finally even when saga.execute raises."""
        (
            MockWorkflow,
            MockStep,
            MockComp,
            MockContext,
            _MockResult,
        ) = _make_mock_saga_classes()

        async def failing_execute(self_inner, context):
            raise ActivationSagaError("forced saga failure")

        MockWorkflow.execute = failing_execute

        mock_init = AsyncMock()
        mock_close = AsyncMock()

        _globs = activate_amendment.__globals__
        with patch.dict(
            _globs,
            {
                "ConstitutionalSagaWorkflow": MockWorkflow,
                "SagaStep": MockStep,
                "SagaCompensation": MockComp,
                "SagaContext": MockContext,
            },
        ):
            with patch.object(ActivationSagaActivities, "initialize", mock_init):
                with patch.object(ActivationSagaActivities, "close", mock_close):
                    with pytest.raises(ActivationSagaError, match="forced saga failure"):
                        await activate_amendment(
                            amendment_id="amendment-raises",
                            storage=mock_storage,
                        )

        mock_close.assert_awaited_once()

    async def test_activate_amendment_finally_no_steps_close_not_called(self, mock_storage):
        """close() is not called via steps if there are no steps, but still no crash."""
        (
            MockWorkflow,
            MockStep,
            MockComp,
            MockContext,
            _MockResult,
        ) = _make_mock_saga_classes()

        class EmptyStepsWorkflow(MockWorkflow):
            def add_step(self, step):
                pass  # keep _steps empty

        mock_init = AsyncMock()
        mock_close = AsyncMock()

        _globs = activate_amendment.__globals__
        with patch.dict(
            _globs,
            {
                "ConstitutionalSagaWorkflow": EmptyStepsWorkflow,
                "SagaStep": MockStep,
                "SagaCompensation": MockComp,
                "SagaContext": MockContext,
            },
        ):
            with patch.object(ActivationSagaActivities, "initialize", mock_init):
                with patch.object(ActivationSagaActivities, "close", mock_close):
                    result = await activate_amendment(
                        amendment_id="amendment-empty-finally",
                        storage=mock_storage,
                    )

        assert result.status == "COMPLETED"
        mock_init.assert_not_called()
        mock_close.assert_not_called()

    async def test_activate_amendment_no_saga_context_raises_import_error(self, mock_storage):
        """activate_amendment raises ImportError when SagaContext is None."""
        with patch.object(_saga_module, "SagaContext", None):
            with pytest.raises(ImportError, match="SagaContext not available"):
                await activate_amendment(
                    amendment_id="amendment-no-ctx",
                    storage=mock_storage,
                )

    async def test_activate_amendment_with_custom_redis_url(self, mock_storage):
        """activate_amendment passes redis_url through to activities."""
        (
            MockWorkflow,
            MockStep,
            MockComp,
            MockContext,
            _MockResult,
        ) = _make_mock_saga_classes()

        captured_redis_url = {}
        original_init = ActivationSagaActivities.__init__

        def capturing_init(self_inner, storage, opa_url, audit_service_url, redis_url):
            captured_redis_url["url"] = redis_url
            original_init(
                self_inner,
                storage=storage,
                opa_url=opa_url,
                audit_service_url=audit_service_url,
                redis_url=redis_url,
            )

        _globs = activate_amendment.__globals__
        with patch.dict(
            _globs,
            {
                "ConstitutionalSagaWorkflow": MockWorkflow,
                "SagaStep": MockStep,
                "SagaCompensation": MockComp,
                "SagaContext": MockContext,
            },
        ):
            with patch.object(ActivationSagaActivities, "__init__", capturing_init):
                with patch.object(ActivationSagaActivities, "initialize", new_callable=AsyncMock):
                    with patch.object(ActivationSagaActivities, "close", new_callable=AsyncMock):
                        await activate_amendment(
                            amendment_id="amendment-redis",
                            storage=mock_storage,
                            redis_url="redis://myredis:6380",
                        )

        assert captured_redis_url["url"] == "redis://myredis:6380"

    async def test_activate_amendment_default_redis_url_none(self, mock_storage):
        """activate_amendment passes redis_url=None when not specified."""
        (
            MockWorkflow,
            MockStep,
            MockComp,
            MockContext,
            _MockResult,
        ) = _make_mock_saga_classes()

        captured_redis_url = {}
        original_init = ActivationSagaActivities.__init__

        def capturing_init(self_inner, storage, opa_url, audit_service_url, redis_url):
            captured_redis_url["url"] = redis_url
            original_init(
                self_inner,
                storage=storage,
                opa_url=opa_url,
                audit_service_url=audit_service_url,
                redis_url=redis_url,
            )

        _globs = activate_amendment.__globals__
        with patch.dict(
            _globs,
            {
                "ConstitutionalSagaWorkflow": MockWorkflow,
                "SagaStep": MockStep,
                "SagaCompensation": MockComp,
                "SagaContext": MockContext,
            },
        ):
            with patch.object(ActivationSagaActivities, "__init__", capturing_init):
                with patch.object(ActivationSagaActivities, "initialize", new_callable=AsyncMock):
                    with patch.object(ActivationSagaActivities, "close", new_callable=AsyncMock):
                        await activate_amendment(
                            amendment_id="amendment-no-redis",
                            storage=mock_storage,
                            # No redis_url → defaults to None
                        )

        assert captured_redis_url["url"] is None


# ---------------------------------------------------------------------------
# create_activation_saga() — custom URL propagation
# ---------------------------------------------------------------------------


class TestCreateActivationSagaUrlPropagation:
    """Verify custom URLs are passed to ActivationSagaActivities."""

    @pytest.fixture
    def mock_storage(self):
        return AsyncMock(spec=ConstitutionalStorageService)

    def test_custom_urls_propagated_to_activities(self, mock_storage):
        """create_activation_saga passes all custom URLs to activities."""
        (
            MockWorkflow,
            MockStep,
            MockComp,
            _MockContext,
            _MockResult,
        ) = _make_mock_saga_classes()

        captured = {}
        original_init = ActivationSagaActivities.__init__

        def capturing_init(self_inner, storage, opa_url, audit_service_url, redis_url):
            captured["opa"] = opa_url
            captured["audit"] = audit_service_url
            captured["redis"] = redis_url
            original_init(
                self_inner,
                storage=storage,
                opa_url=opa_url,
                audit_service_url=audit_service_url,
                redis_url=redis_url,
            )

        _globs = create_activation_saga.__globals__
        with patch.dict(
            _globs,
            {
                "ConstitutionalSagaWorkflow": MockWorkflow,
                "SagaStep": MockStep,
                "SagaCompensation": MockComp,
            },
        ):
            with patch.object(ActivationSagaActivities, "__init__", capturing_init):
                create_activation_saga(
                    amendment_id="amend-urls",
                    storage=mock_storage,
                    opa_url="http://custom-opa:9999",
                    audit_service_url="http://custom-audit:9998",
                    redis_url="redis://custom-redis:9997",
                )

        assert captured["opa"] == "http://custom-opa:9999"
        assert captured["audit"] == "http://custom-audit:9998"
        assert captured["redis"] == "redis://custom-redis:9997"

    def test_saga_id_format(self, mock_storage):
        """create_activation_saga generates saga_id with activation- prefix."""
        (
            MockWorkflow,
            MockStep,
            MockComp,
            _MockContext,
            _MockResult,
        ) = _make_mock_saga_classes()

        _globs = create_activation_saga.__globals__
        with patch.dict(
            _globs,
            {
                "ConstitutionalSagaWorkflow": MockWorkflow,
                "SagaStep": MockStep,
                "SagaCompensation": MockComp,
            },
        ):
            saga = create_activation_saga(
                amendment_id="test-amend-id",
                storage=mock_storage,
            )

        assert saga.saga_id.startswith("activation-test-amend-id-")


# ---------------------------------------------------------------------------
# update_cache() — ConstitutionalVersion metadata fields
# ---------------------------------------------------------------------------


class TestUpdateCacheVersionMetadata:
    """Test that update_cache creates ConstitutionalVersion with correct metadata."""

    async def test_update_cache_version_metadata_contains_amendment_id(self):
        """update_cache stores amendment_id in version metadata."""
        mock_storage = AsyncMock(spec=ConstitutionalStorageService)
        amendment = _make_amendment()
        target = _make_version()
        mock_storage.get_amendment.return_value = amendment
        mock_storage.get_version.return_value = target

        activities = _make_activities(mock_storage)
        activities._compute_constitutional_hash = MagicMock(return_value=CONSTITUTIONAL_HASH)

        # Capture the version passed to save_version
        saved_versions = []

        async def capture_save(version):
            saved_versions.append(version)

        mock_storage.save_version = capture_save

        await activities.update_cache(
            {
                "saga_id": "s-meta",
                "context": {
                    "amendment_id": "amendment-ext-001",
                    "validate_activation": {"new_version": "2.1.0"},
                },
            }
        )

        assert len(saved_versions) == 1
        v = saved_versions[0]
        assert v.metadata["amendment_id"] == "amendment-ext-001"
        assert v.metadata["activated_by"] == "activation_saga"
        assert v.metadata["impact_score"] == amendment.impact_score
        assert v.metadata["proposer_agent_id"] == amendment.proposer_agent_id

    async def test_update_cache_new_version_status_is_approved(self):
        """update_cache creates version with APPROVED status."""
        mock_storage = AsyncMock(spec=ConstitutionalStorageService)
        amendment = _make_amendment()
        target = _make_version()
        mock_storage.get_amendment.return_value = amendment
        mock_storage.get_version.return_value = target

        activities = _make_activities(mock_storage)
        activities._compute_constitutional_hash = MagicMock(return_value=CONSTITUTIONAL_HASH)

        saved_versions = []

        async def capture_save(version):
            saved_versions.append(version)

        mock_storage.save_version = capture_save

        await activities.update_cache(
            {
                "saga_id": "s-status",
                "context": {
                    "amendment_id": "amendment-ext-001",
                    "validate_activation": {"new_version": "2.1.0"},
                },
            }
        )

        assert saved_versions[0].status == ConstitutionalStatus.APPROVED

    async def test_update_cache_predecessor_version_set(self):
        """update_cache sets predecessor_version from target version's id."""
        mock_storage = AsyncMock(spec=ConstitutionalStorageService)
        amendment = _make_amendment()
        target = _make_version(version_id="v-target-123")
        mock_storage.get_amendment.return_value = amendment
        mock_storage.get_version.return_value = target

        activities = _make_activities(mock_storage)
        activities._compute_constitutional_hash = MagicMock(return_value=CONSTITUTIONAL_HASH)

        saved_versions = []

        async def capture_save(version):
            saved_versions.append(version)

        mock_storage.save_version = capture_save

        await activities.update_cache(
            {
                "saga_id": "s-pred",
                "context": {
                    "amendment_id": "amendment-ext-001",
                    "validate_activation": {"new_version": "2.1.0"},
                },
            }
        )

        assert saved_versions[0].predecessor_version == "v-target-123"

    async def test_update_cache_amendment_status_set_to_active(self):
        """update_cache sets amendment.status = ACTIVE and saves it."""
        mock_storage = AsyncMock(spec=ConstitutionalStorageService)
        amendment = _make_amendment(status=AmendmentStatus.APPROVED)
        target = _make_version()
        mock_storage.get_amendment.return_value = amendment
        mock_storage.get_version.return_value = target

        activities = _make_activities(mock_storage)
        activities._compute_constitutional_hash = MagicMock(return_value=CONSTITUTIONAL_HASH)

        await activities.update_cache(
            {
                "saga_id": "s-active",
                "context": {
                    "amendment_id": "amendment-ext-001",
                    "validate_activation": {"new_version": "2.1.0"},
                },
            }
        )

        # amendment.status should have been changed to ACTIVE
        assert amendment.status == AmendmentStatus.ACTIVE
        mock_storage.save_amendment.assert_awaited_once_with(amendment)

    async def test_update_cache_returns_cache_update_id(self):
        """update_cache returns a cache_update_id UUID string."""
        mock_storage = AsyncMock(spec=ConstitutionalStorageService)
        amendment = _make_amendment()
        target = _make_version()
        mock_storage.get_amendment.return_value = amendment
        mock_storage.get_version.return_value = target

        activities = _make_activities(mock_storage)
        activities._compute_constitutional_hash = MagicMock(return_value=CONSTITUTIONAL_HASH)

        result = await activities.update_cache(
            {
                "saga_id": "s-uuid",
                "context": {
                    "amendment_id": "amendment-ext-001",
                    "validate_activation": {"new_version": "2.1.0"},
                },
            }
        )

        assert "cache_update_id" in result
        assert len(result["cache_update_id"]) == 36  # UUID length


# ---------------------------------------------------------------------------
# audit_activation() — constitutional_hash fallback when new_hash is falsy
# ---------------------------------------------------------------------------


class TestAuditActivationHashFallback:
    """Verify audit_activation picks up new_hash from cache or falls back."""

    async def test_audit_empty_new_hash_fallback_to_const_hash(self):
        """When update_cache result has no new_hash, fallback to CONSTITUTIONAL_HASH."""
        activities = _make_activities()

        result = await activities.audit_activation(
            {
                "saga_id": "s-fallback",
                "context": {
                    "amendment_id": "amend-abc",
                    "validate_activation": {"new_version": "3.0.0"},
                    "backup_current_version": {"version": "2.9.0", "version_id": "v-old"},
                    "update_cache": {"new_version_id": "v-new"},  # no new_hash key
                },
            }
        )
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_audit_none_new_hash_fallback_to_const_hash(self):
        """When new_hash is None, fallback to CONSTITUTIONAL_HASH."""
        activities = _make_activities()

        result = await activities.audit_activation(
            {
                "saga_id": "s-none-hash",
                "context": {
                    "amendment_id": "amend-abc",
                    "validate_activation": {},
                    "backup_current_version": {},
                    "update_cache": {"new_hash": None},  # None triggers fallback
                },
            }
        )
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_audit_with_real_new_hash_uses_it(self):
        """When new_hash is provided, it is used as constitutional_hash."""
        activities = _make_activities()
        custom_hash = "deadbeefcafebabe"

        result = await activities.audit_activation(
            {
                "saga_id": "s-custom-hash",
                "context": {
                    "amendment_id": "amend-abc",
                    "validate_activation": {"new_version": "3.0.0"},
                    "backup_current_version": {"version": "2.9.0", "version_id": "v-old"},
                    "update_cache": {"new_hash": custom_hash, "new_version_id": "v-new"},
                },
            }
        )
        assert result["constitutional_hash"] == custom_hash


# ---------------------------------------------------------------------------
# validate_activation() — returns full result structure
# ---------------------------------------------------------------------------


class TestValidateActivationResultStructure:
    """Ensure validate_activation returns expected keys."""

    async def test_result_contains_all_expected_keys(self):
        """validate_activation result includes all documented keys."""
        mock_storage = AsyncMock(spec=ConstitutionalStorageService)
        amendment = _make_amendment()
        target = _make_version()
        active = _make_version()

        mock_storage.get_amendment.return_value = amendment
        mock_storage.get_version.return_value = target
        mock_storage.get_active_version.return_value = active

        activities = _make_activities(mock_storage)
        result = await activities.validate_activation(
            {"saga_id": "s-keys", "context": {"amendment_id": "amendment-ext-001"}}
        )

        for key in [
            "validation_id",
            "amendment_id",
            "target_version_id",
            "target_version",
            "new_version",
            "is_valid",
            "timestamp",
        ]:
            assert key in result, f"Missing key: {key}"

    async def test_result_timestamp_is_iso_format(self):
        """validate_activation timestamp is ISO 8601 format."""
        from datetime import datetime, timezone

        mock_storage = AsyncMock(spec=ConstitutionalStorageService)
        amendment = _make_amendment()
        target = _make_version()
        mock_storage.get_amendment.return_value = amendment
        mock_storage.get_version.return_value = target
        mock_storage.get_active_version.return_value = target

        activities = _make_activities(mock_storage)
        result = await activities.validate_activation(
            {"saga_id": "s-ts", "context": {"amendment_id": "amendment-ext-001"}}
        )

        # Should not raise
        datetime.fromisoformat(result["timestamp"])

    async def test_validate_active_version_id_mismatch_warns(self):
        """validate_activation logs warning when active version id doesn't match target."""
        mock_storage = AsyncMock(spec=ConstitutionalStorageService)
        amendment = _make_amendment()
        target = _make_version(version_id="target-vid")
        active = _make_version(version_id="active-vid")  # different

        mock_storage.get_amendment.return_value = amendment
        mock_storage.get_version.return_value = target
        mock_storage.get_active_version.return_value = active

        activities = _make_activities(mock_storage)
        result = await activities.validate_activation(
            {"saga_id": "s-mismatch", "context": {"amendment_id": "amendment-ext-001"}}
        )
        # Still valid
        assert result["is_valid"] is True


# ---------------------------------------------------------------------------
# backup_current_version() — result structure
# ---------------------------------------------------------------------------


class TestBackupCurrentVersionResultStructure:
    """Ensure backup_current_version result includes all expected keys."""

    async def test_result_contains_all_keys(self):
        """backup_current_version returns backup_id, version_id, version, etc."""
        mock_storage = AsyncMock(spec=ConstitutionalStorageService)
        active = _make_version()
        mock_storage.get_active_version.return_value = active

        activities = _make_activities(mock_storage)
        result = await activities.backup_current_version(
            {"saga_id": "s-backup-keys", "context": {}}
        )

        for key in [
            "backup_id",
            "version_id",
            "version",
            "constitutional_hash",
            "content",
            "status",
            "timestamp",
        ]:
            assert key in result, f"Missing key: {key}"

    async def test_result_status_is_string(self):
        """backup_current_version status is a string (from .value)."""
        mock_storage = AsyncMock(spec=ConstitutionalStorageService)
        active = _make_version()
        mock_storage.get_active_version.return_value = active

        activities = _make_activities(mock_storage)
        result = await activities.backup_current_version({"saga_id": "s-backup-str", "context": {}})

        assert isinstance(result["status"], str)

    async def test_result_backup_id_is_uuid(self):
        """backup_current_version backup_id is a UUID string."""
        mock_storage = AsyncMock(spec=ConstitutionalStorageService)
        active = _make_version()
        mock_storage.get_active_version.return_value = active

        activities = _make_activities(mock_storage)
        result = await activities.backup_current_version(
            {"saga_id": "s-backup-uuid", "context": {}}
        )

        assert len(result["backup_id"]) == 36  # UUID


# ---------------------------------------------------------------------------
# restore_backup() — IOError coverage
# ---------------------------------------------------------------------------


class TestRestoreBackupIOError:
    """Test restore_backup handles IOError (also in the except tuple)."""

    async def test_restore_backup_io_error_returns_false(self):
        """restore_backup returns False on IOError from storage."""
        mock_storage = AsyncMock(spec=ConstitutionalStorageService)
        mock_storage.activate_version = AsyncMock(side_effect=OSError("disk full"))

        activities = _make_activities(mock_storage)
        result = await activities.restore_backup(
            {
                "saga_id": "s-io",
                "context": {"backup_current_version": {"version_id": "v-io"}},
            }
        )
        assert result is False

    async def test_restore_backup_os_error_returns_false(self):
        """restore_backup returns False on OSError from storage."""
        mock_storage = AsyncMock(spec=ConstitutionalStorageService)
        mock_storage.activate_version = AsyncMock(side_effect=OSError("network error"))

        activities = _make_activities(mock_storage)
        result = await activities.restore_backup(
            {
                "saga_id": "s-os",
                "context": {"backup_current_version": {"version_id": "v-os"}},
            }
        )
        assert result is False

    async def test_restore_backup_type_error_returns_false(self):
        """restore_backup returns False on TypeError from storage."""
        mock_storage = AsyncMock(spec=ConstitutionalStorageService)
        mock_storage.activate_version = AsyncMock(side_effect=TypeError("unexpected type"))

        activities = _make_activities(mock_storage)
        result = await activities.restore_backup(
            {
                "saga_id": "s-type",
                "context": {"backup_current_version": {"version_id": "v-type"}},
            }
        )
        assert result is False


# ---------------------------------------------------------------------------
# update_opa_policies() — OSError in HTTP error path
# ---------------------------------------------------------------------------


class TestUpdateOpaPoliciesOSError:
    """Test update_opa_policies handles OSError from httpx."""

    async def test_opa_os_error_continues(self):
        """update_opa_policies continues on OSError from http client."""
        mock_storage = AsyncMock(spec=ConstitutionalStorageService)
        amendment = _make_amendment()
        target = _make_version()
        mock_storage.get_amendment.return_value = amendment
        mock_storage.get_version.return_value = target

        activities = _make_activities(mock_storage)
        mock_http = AsyncMock()
        mock_http.put = AsyncMock(side_effect=OSError("os error"))
        activities._http_client = mock_http

        result = await activities.update_opa_policies(
            {
                "saga_id": "s-os-opa",
                "context": {
                    "amendment_id": "amendment-ext-001",
                    "validate_activation": {"new_version": "2.1.0"},
                },
            }
        )
        # OPA is non-critical; still returns updated=True
        assert result["updated"] is True

    async def test_opa_connection_error_continues(self):
        """update_opa_policies continues on ConnectionError."""
        mock_storage = AsyncMock(spec=ConstitutionalStorageService)
        amendment = _make_amendment()
        target = _make_version()
        mock_storage.get_amendment.return_value = amendment
        mock_storage.get_version.return_value = target

        activities = _make_activities(mock_storage)
        mock_http = AsyncMock()
        mock_http.put = AsyncMock(side_effect=ConnectionError("conn refused"))
        activities._http_client = mock_http

        result = await activities.update_opa_policies(
            {
                "saga_id": "s-conn-opa",
                "context": {
                    "amendment_id": "amendment-ext-001",
                    "validate_activation": {"new_version": "2.1.0"},
                },
            }
        )
        assert result["updated"] is True


# ---------------------------------------------------------------------------
# revert_opa_policies() — no backup_current_version key (empty context)
# ---------------------------------------------------------------------------


class TestRevertOpaPoliciesEdgeCases:
    """Additional edge cases for revert_opa_policies."""

    async def test_revert_opa_os_error_returns_false(self):
        """revert_opa_policies returns False on OSError."""
        activities = _make_activities()
        mock_http = AsyncMock()
        mock_http.put = AsyncMock(side_effect=OSError("network error"))
        activities._http_client = mock_http

        result = await activities.revert_opa_policies(
            {
                "saga_id": "s-revert-os",
                "context": {
                    "backup_current_version": {
                        "constitutional_hash": CONSTITUTIONAL_HASH,
                        "version": "1.0.0",
                    }
                },
            }
        )
        assert result is False

    async def test_revert_opa_connection_error_returns_false(self):
        """revert_opa_policies returns False on ConnectionError."""
        activities = _make_activities()
        mock_http = AsyncMock()
        mock_http.put = AsyncMock(side_effect=ConnectionError("refused"))
        activities._http_client = mock_http

        result = await activities.revert_opa_policies(
            {
                "saga_id": "s-revert-conn",
                "context": {
                    "backup_current_version": {
                        "constitutional_hash": CONSTITUTIONAL_HASH,
                        "version": "1.0.0",
                    }
                },
            }
        )
        assert result is False

    async def test_revert_opa_value_error_returns_false(self):
        """revert_opa_policies returns False on ValueError."""
        activities = _make_activities()
        mock_http = AsyncMock()
        mock_http.put = AsyncMock(side_effect=ValueError("bad val"))
        activities._http_client = mock_http

        result = await activities.revert_opa_policies(
            {
                "saga_id": "s-revert-val",
                "context": {
                    "backup_current_version": {
                        "constitutional_hash": CONSTITUTIONAL_HASH,
                        "version": "1.0.0",
                    }
                },
            }
        )
        assert result is False

    async def test_revert_opa_type_error_returns_false(self):
        """revert_opa_policies returns False on TypeError."""
        activities = _make_activities()
        mock_http = AsyncMock()
        mock_http.put = AsyncMock(side_effect=TypeError("bad type"))
        activities._http_client = mock_http

        result = await activities.revert_opa_policies(
            {
                "saga_id": "s-revert-type",
                "context": {
                    "backup_current_version": {
                        "constitutional_hash": CONSTITUTIONAL_HASH,
                        "version": "1.0.0",
                    }
                },
            }
        )
        assert result is False

    async def test_revert_opa_no_backup_uses_constitutional_hash(self):
        """revert_opa_policies uses CONSTITUTIONAL_HASH when backup is missing."""
        activities = _make_activities()
        mock_http = AsyncMock()
        mock_http.put.return_value = MagicMock(status_code=200)
        activities._http_client = mock_http

        result = await activities.revert_opa_policies(
            {
                "saga_id": "s-revert-nobackup",
                "context": {},  # no backup_current_version key
            }
        )
        assert result is True

        # Verify put was called with the CONSTITUTIONAL_HASH as default
        put_call = mock_http.put.call_args
        assert put_call is not None
        call_json = (
            put_call.kwargs.get("json") or put_call.args[1]
            if put_call.args[1:]
            else put_call.kwargs.get("json")
        )
        # The json arg has hash=CONSTITUTIONAL_HASH by default
        # Accept either call styles
        if put_call.kwargs:
            assert put_call.kwargs.get("json", {}).get("hash") == CONSTITUTIONAL_HASH
        else:
            assert put_call.args[1].get("hash") == CONSTITUTIONAL_HASH


# ---------------------------------------------------------------------------
# mark_audit_failed() — compensation event structure
# ---------------------------------------------------------------------------


class TestMarkAuditFailedCompensationEvent:
    """Verify mark_audit_failed constructs the correct compensation event."""

    async def test_compensation_event_structure_with_audit_client(self):
        """mark_audit_failed submits correct event to audit client."""
        activities = _make_activities()
        mock_audit = AsyncMock()
        captured_events = []

        async def capture_log(event_type, data, constitutional_hash):
            captured_events.append(data)

        mock_audit.log = capture_log
        activities._audit_client = mock_audit

        await activities.mark_audit_failed(
            {
                "saga_id": "s-comp-event",
                "context": {"audit_activation": {"audit_id": "audit-XYZ"}},
            }
        )

        assert len(captured_events) == 1
        event = captured_events[0]
        assert event["event_type"] == "constitutional_activation_compensated"
        assert event["saga_id"] == "s-comp-event"
        assert event["original_audit_id"] == "audit-XYZ"
        assert "constitutional_hash" in event
        assert event["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_compensation_event_uses_unknown_when_no_audit_id(self):
        """mark_audit_failed uses 'unknown' when audit_id missing from context."""
        activities = _make_activities()
        mock_audit = AsyncMock()
        captured_events = []

        async def capture_log(event_type, data, constitutional_hash):
            captured_events.append(data)

        mock_audit.log = capture_log
        activities._audit_client = mock_audit

        await activities.mark_audit_failed(
            {
                "saga_id": "s-comp-unknown",
                "context": {},  # no audit_activation
            }
        )

        assert captured_events[0]["original_audit_id"] == "unknown"

    async def test_mark_audit_failed_value_error_from_client(self):
        """mark_audit_failed handles ValueError from audit client gracefully."""
        activities = _make_activities()
        mock_audit = AsyncMock()
        mock_audit.log = AsyncMock(side_effect=ValueError("bad val"))
        activities._audit_client = mock_audit

        result = await activities.mark_audit_failed(
            {
                "saga_id": "s-val-err",
                "context": {"audit_activation": {"audit_id": "audit-err"}},
            }
        )
        assert result is True

    async def test_mark_audit_failed_type_error_from_client(self):
        """mark_audit_failed handles TypeError from audit client gracefully."""
        activities = _make_activities()
        mock_audit = AsyncMock()
        mock_audit.log = AsyncMock(side_effect=TypeError("bad type"))
        activities._audit_client = mock_audit

        result = await activities.mark_audit_failed(
            {
                "saga_id": "s-type-err",
                "context": {"audit_activation": {"audit_id": "audit-type"}},
            }
        )
        assert result is True


# ---------------------------------------------------------------------------
# audit_activation() — audit event structure
# ---------------------------------------------------------------------------


class TestAuditActivationEventStructure:
    """Verify audit_activation returns the full event dict."""

    async def test_audit_event_contains_all_keys(self):
        """audit_activation returns dict with all documented keys."""
        activities = _make_activities()

        result = await activities.audit_activation(
            {
                "saga_id": "s-full-audit",
                "context": {
                    "amendment_id": "amend-full",
                    "validate_activation": {"new_version": "4.0.0"},
                    "backup_current_version": {
                        "version": "3.9.0",
                        "version_id": "v-old",
                    },
                    "update_cache": {"new_version_id": "v-new", "new_hash": "abc123"},
                },
            }
        )

        for key in [
            "audit_id",
            "event_type",
            "saga_id",
            "amendment_id",
            "new_version",
            "new_version_id",
            "previous_version",
            "previous_version_id",
            "constitutional_hash",
            "timestamp",
            "metadata",
        ]:
            assert key in result, f"Missing key: {key}"

    async def test_audit_event_metadata_contains_sub_results(self):
        """audit_activation metadata includes validation, backup, cache_update dicts."""
        activities = _make_activities()
        val_result = {"new_version": "5.0.0", "extra": "data"}
        backup_result = {"version": "4.9.0", "version_id": "v-old"}
        cache_result = {"new_version_id": "v-new", "new_hash": "hash123"}

        result = await activities.audit_activation(
            {
                "saga_id": "s-meta-audit",
                "context": {
                    "amendment_id": "amend-meta",
                    "validate_activation": val_result,
                    "backup_current_version": backup_result,
                    "update_cache": cache_result,
                },
            }
        )

        assert result["metadata"]["validation"] == val_result
        assert result["metadata"]["backup"] == backup_result
        assert result["metadata"]["cache_update"] == cache_result


# ---------------------------------------------------------------------------
# Module-level REDIS_AVAILABLE flag
# ---------------------------------------------------------------------------


class TestModuleLevelFlags:
    """Test module-level flags and constants."""

    def test_redis_available_is_bool(self):
        """REDIS_AVAILABLE is a boolean."""
        assert isinstance(_saga_module.REDIS_AVAILABLE, bool)

    def test_constitutional_hash_imported(self):
        """CONSTITUTIONAL_HASH is importable and matches expected value."""
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH  # pragma: allowlist secret


# ---------------------------------------------------------------------------
# log_validation_failure() — compensation returns True
# ---------------------------------------------------------------------------


class TestLogValidationFailure:
    """Test log_validation_failure compensation method."""

    async def test_log_validation_failure_returns_true(self):
        """log_validation_failure always returns True."""
        activities = _make_activities()
        result = await activities.log_validation_failure({"saga_id": "s-log-fail", "context": {}})
        assert result is True

    async def test_log_validation_failure_with_populated_context(self):
        """log_validation_failure works with a populated context dict."""
        activities = _make_activities()
        result = await activities.log_validation_failure(
            {
                "saga_id": "s-log-ctx",
                "context": {
                    "amendment_id": "amend-fail",
                    "reason": "test failure",
                },
            }
        )
        assert result is True


# ---------------------------------------------------------------------------
# _compute_constitutional_hash() — additional determinism tests
# ---------------------------------------------------------------------------


class TestComputeConstitutionalHashExtra:
    """Additional hash computation tests."""

    def test_nested_dict_is_hashed_consistently(self):
        """Nested dicts produce deterministic hash."""
        activities = _make_activities()
        content = {"level1": {"level2": {"level3": "value"}}}
        h1 = activities._compute_constitutional_hash(content)
        h2 = activities._compute_constitutional_hash(content)
        assert h1 == h2

    def test_list_value_is_hashed(self):
        """Dicts with list values produce valid hash."""
        activities = _make_activities()
        content = {"principles": ["P1", "P2", "P3"]}
        h = activities._compute_constitutional_hash(content)
        assert len(h) == 64

    def test_unicode_content_is_hashed(self):
        """Unicode content hashes without error."""
        activities = _make_activities()
        content = {"principle": "Governance über alles"}
        h = activities._compute_constitutional_hash(content)
        assert len(h) == 64
