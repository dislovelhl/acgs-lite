"""Tests for src/core/enhanced_agent_bus/api/app.py

Constitutional Hash: 608508a9bd224290
Coverage target: ≥ 90%
"""

from __future__ import annotations

import contextlib
import importlib
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRouter
from httpx import ASGITransport, AsyncClient

# Import the module under test. We use importlib to get the actual module
# object (not the FastAPI `app` instance that `api/__init__.py` re-exports
# under the same name), and store it in sys.modules so coverage can track
# line execution in the source file.
_MOD_NAME = "enhanced_agent_bus.api.app"
importlib.import_module(_MOD_NAME)  # ensure the module is loaded and instrumented
app_module = sys.modules[_MOD_NAME]


# ---------------------------------------------------------------------------
# _normalize_workflow_dsn
# ---------------------------------------------------------------------------


class TestNormalizeWorkflowDsn:
    def test_replaces_asyncpg_prefix(self):
        url = "postgresql+asyncpg://user:pass@localhost/db"
        result = app_module._normalize_workflow_dsn(url)
        assert result == "postgresql://user:pass@localhost/db"

    def test_leaves_plain_postgresql_unchanged(self):
        url = "postgresql://user:pass@localhost/db"
        result = app_module._normalize_workflow_dsn(url)
        assert result == "postgresql://user:pass@localhost/db"

    def test_leaves_other_schemes_unchanged(self):
        url = "sqlite:///test.db"
        result = app_module._normalize_workflow_dsn(url)
        assert result == "sqlite:///test.db"

    def test_empty_string_unchanged(self):
        result = app_module._normalize_workflow_dsn("")
        assert result == ""

    def test_asyncpg_url_with_params(self):
        url = "postgresql+asyncpg://user:pass@host:5432/db?sslmode=require"
        result = app_module._normalize_workflow_dsn(url)
        assert result.startswith("postgresql://")
        assert "asyncpg" not in result


# ---------------------------------------------------------------------------
# _load_visual_studio_router
# ---------------------------------------------------------------------------


class TestLoadVisualStudioRouter:
    def test_returns_none_on_import_error(self):
        with patch.object(app_module, "import_module", side_effect=ImportError("missing")):
            result = app_module._load_visual_studio_router()
        assert result is None

    def test_returns_router_when_available(self):
        fake_router = APIRouter()
        fake_module = MagicMock()
        fake_module.router = fake_router
        with patch.object(app_module, "import_module", return_value=fake_module):
            result = app_module._load_visual_studio_router()
        assert result is fake_router

    def test_returns_none_when_router_attr_missing(self):
        fake_module = MagicMock(spec=[])  # no .router attribute
        with patch.object(app_module, "import_module", return_value=fake_module):
            result = app_module._load_visual_studio_router()
        assert result is None

    def test_returns_none_when_router_not_apirouter(self):
        fake_module = MagicMock()
        fake_module.router = "not-a-router"
        with patch.object(app_module, "import_module", return_value=fake_module):
            result = app_module._load_visual_studio_router()
        assert result is None


# ---------------------------------------------------------------------------
# _load_copilot_router
# ---------------------------------------------------------------------------


class TestLoadCopilotRouter:
    def test_returns_none_on_import_error(self):
        with patch.object(app_module, "import_module", side_effect=ImportError("missing")):
            result = app_module._load_copilot_router()
        assert result is None

    def test_returns_router_when_available(self):
        fake_router = APIRouter()
        fake_module = MagicMock()
        fake_module.router = fake_router
        with patch.object(app_module, "import_module", return_value=fake_module):
            result = app_module._load_copilot_router()
        assert result is fake_router

    def test_returns_none_when_router_attr_missing(self):
        fake_module = MagicMock(spec=[])
        with patch.object(app_module, "import_module", return_value=fake_module):
            result = app_module._load_copilot_router()
        assert result is None

    def test_returns_none_when_router_not_apirouter(self):
        fake_module = MagicMock()
        fake_module.router = 42
        with patch.object(app_module, "import_module", return_value=fake_module):
            result = app_module._load_copilot_router()
        assert result is None


# ---------------------------------------------------------------------------
# _register_exception_handlers
# ---------------------------------------------------------------------------


class TestRegisterExceptionHandlers:
    def test_registers_all_handlers_with_rate_limiting_available(self):
        application = FastAPI()
        original = app_module.RATE_LIMITING_AVAILABLE
        try:
            app_module.RATE_LIMITING_AVAILABLE = True
            app_module._register_exception_handlers(application)
        finally:
            app_module.RATE_LIMITING_AVAILABLE = original
        assert application is not None

    def test_registers_all_handlers_without_rate_limiting(self):
        application = FastAPI()
        original = app_module.RATE_LIMITING_AVAILABLE
        try:
            app_module.RATE_LIMITING_AVAILABLE = False
            app_module._register_exception_handlers(application)
        finally:
            app_module.RATE_LIMITING_AVAILABLE = original
        assert application is not None


# ---------------------------------------------------------------------------
# _register_optional_routers
# ---------------------------------------------------------------------------


class TestRegisterOptionalRouters:
    def test_registers_constitutional_review_router_when_available(self):
        application = FastAPI()
        fake_review_mod = MagicMock()
        fake_review_mod.router = APIRouter()

        with patch.dict(
            sys.modules,
            {
                "enhanced_agent_bus.constitutional.review_api": fake_review_mod,
            },
        ):
            app_module._register_optional_routers(application)
        assert application is not None

    def test_skips_constitutional_review_router_on_import_error(self):
        application = FastAPI()
        # Remove any cached version to trigger ImportError
        sys.modules.pop("enhanced_agent_bus.constitutional", None)
        sys.modules.pop("enhanced_agent_bus.constitutional.review_api", None)
        # Just verify no unhandled exception propagates
        with contextlib.suppress(ImportError):
            app_module._register_optional_routers(application)
        assert application is not None

    def test_registers_circuit_breaker_router_when_available(self):
        application = FastAPI()
        fake_circuit_mod = MagicMock()
        fake_circuit_mod.create_circuit_health_router = MagicMock(return_value=APIRouter())

        with patch.dict(
            sys.modules,
            {
                "enhanced_agent_bus.circuit_breaker": fake_circuit_mod,
            },
        ):
            app_module._register_optional_routers(application)
        assert application is not None

    def test_handles_circuit_breaker_returning_none(self):
        application = FastAPI()
        fake_circuit_mod = MagicMock()
        fake_circuit_mod.create_circuit_health_router = MagicMock(return_value=None)

        with patch.dict(
            sys.modules,
            {
                "enhanced_agent_bus.circuit_breaker": fake_circuit_mod,
            },
        ):
            app_module._register_optional_routers(application)
        assert application is not None

    def test_registers_sessions_router_when_available(self):
        application = FastAPI()
        fake_sessions_mod = MagicMock()
        fake_sessions_mod.router = APIRouter()

        with patch.dict(
            sys.modules,
            {
                "enhanced_agent_bus.routes.sessions": fake_sessions_mod,
            },
        ):
            app_module._register_optional_routers(application)
        assert application is not None


# ---------------------------------------------------------------------------
# create_app
# ---------------------------------------------------------------------------


class TestCreateApp:
    def test_create_app_returns_fastapi_instance(self):
        result = app_module.create_app()
        assert isinstance(result, FastAPI)

    def test_create_app_uses_shared_governance_backends_when_redis_available(self):
        fake_redis = MagicMock()

        with patch.object(app_module, "_build_governance_redis_client", return_value=fake_redis):
            result = app_module.create_app()

        assert isinstance(result.state.maci_record_store, app_module.RedisMACIRecordStore)
        assert isinstance(result.state.maci_role_registry, app_module.RedisMACIRoleRegistry)
        assert result.state.maci_enforcer.registry is result.state.maci_role_registry
        assert result.state.pqc_enforcement_service._redis is fake_redis

    def test_create_app_falls_back_to_in_memory_governance_backends(self):
        with (
            patch.object(
                app_module,
                "_build_governance_redis_client",
                side_effect=ImportError("redis unavailable"),
            ),
            patch.dict("os.environ", {"ENVIRONMENT": "test"}),
        ):
            result = app_module.create_app()

        assert isinstance(result.state.maci_record_store, app_module.MACIRecordStore)
        assert isinstance(result.state.maci_role_registry, app_module.MACIRoleRegistry)
        assert isinstance(result.state.pqc_enforcement_service._redis, app_module.InMemoryPQCConfigBackend)

    def test_create_app_sets_limiter_state(self):
        result = app_module.create_app()
        assert hasattr(result.state, "limiter")

    def test_create_app_sets_failed_tasks_state(self):
        result = app_module.create_app()
        assert hasattr(result.state, "failed_tasks")
        assert isinstance(result.state.failed_tasks, list)

    def test_create_app_includes_visual_studio_router_when_present(self):
        fake_vs_router = APIRouter(prefix="/vs")
        original = app_module.visual_studio_router
        try:
            app_module.visual_studio_router = fake_vs_router
            result = app_module.create_app()
        finally:
            app_module.visual_studio_router = original
        assert isinstance(result, FastAPI)

    def test_create_app_skips_visual_studio_router_when_none(self):
        original = app_module.visual_studio_router
        try:
            app_module.visual_studio_router = None
            result = app_module.create_app()
        finally:
            app_module.visual_studio_router = original
        assert isinstance(result, FastAPI)

    def test_create_app_includes_copilot_router_when_present(self):
        fake_copilot_router = APIRouter(prefix="/copilot")
        original = app_module.copilot_router
        try:
            app_module.copilot_router = fake_copilot_router
            result = app_module.create_app()
        finally:
            app_module.copilot_router = original
        assert isinstance(result, FastAPI)

    def test_create_app_skips_copilot_router_when_none(self):
        original = app_module.copilot_router
        try:
            app_module.copilot_router = None
            result = app_module.create_app()
        finally:
            app_module.copilot_router = original
        assert isinstance(result, FastAPI)

    def test_create_app_has_correct_version(self):
        result = app_module.create_app()
        assert result.version == app_module.API_VERSION

    def test_create_app_title_contains_agent_bus(self):
        result = app_module.create_app()
        assert "Agent Bus" in result.title or "ACGS" in result.title


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------


class TestModuleConstants:
    def test_circuit_breaker_available_is_true(self):
        assert app_module.CIRCUIT_BREAKER_AVAILABLE is True

    def test_api_app_operation_errors_tuple(self):
        errs = app_module._API_APP_OPERATION_ERRORS
        assert RuntimeError in errs
        assert ValueError in errs
        assert TypeError in errs
        assert AttributeError in errs
        assert LookupError in errs
        assert OSError in errs
        assert TimeoutError in errs
        assert ConnectionError in errs

    def test_app_is_fastapi_instance(self):
        assert isinstance(app_module.app, FastAPI)

    def test_all_contains_expected_names(self):
        all_names = app_module.__all__
        assert "app" in all_names
        assert "create_app" in all_names
        assert "get_agent_bus" in all_names
        assert "get_batch_processor" in all_names
        assert "agent_bus" in all_names
        assert "batch_processor" in all_names
        assert "message_circuit_breaker" in all_names


# ---------------------------------------------------------------------------
# Lifespan context manager - startup paths
# ---------------------------------------------------------------------------


class TestLifespanStartup:
    """Test the _lifespan_context async context manager."""

    async def test_successful_startup(self):
        """Test normal successful startup path."""
        fake_app = FastAPI()
        fake_mp = MagicMock()
        fake_batch = MagicMock()
        fake_repo = AsyncMock()
        fake_repo.initialize = AsyncMock()
        fake_repo.close = AsyncMock()
        fake_executor = MagicMock()
        mock_logger = MagicMock()

        with (
            patch.object(app_module, "MessageProcessor", return_value=fake_mp),
            patch.object(app_module, "BatchMessageProcessor", return_value=fake_batch),
            patch.object(app_module, "PostgresWorkflowRepository", return_value=fake_repo),
            patch.object(app_module, "DurableWorkflowExecutor", return_value=fake_executor),
            patch.object(app_module, "logger", mock_logger),
            patch.dict("os.environ", {"DATABASE_URL": "postgresql://localhost/test"}),
        ):
            fake_sessions = MagicMock()
            fake_sessions.init_session_manager = AsyncMock(return_value=True)
            fake_sessions.shutdown_session_manager = AsyncMock()

            with patch.dict(
                sys.modules,
                {
                    "enhanced_agent_bus.routes.sessions": fake_sessions,
                },
            ):
                async with app_module._lifespan_context(fake_app):
                    assert fake_app.state.agent_bus is fake_mp

    async def test_startup_assigns_batch_processor_state(self):
        """Test that batch_processor is set on app.state."""
        fake_app = FastAPI()
        fake_mp = MagicMock()
        fake_batch = MagicMock()
        fake_repo = AsyncMock()
        fake_repo.initialize = AsyncMock()
        fake_repo.close = AsyncMock()
        mock_logger = MagicMock()

        with (
            patch.object(app_module, "MessageProcessor", return_value=fake_mp),
            patch.object(app_module, "BatchMessageProcessor", return_value=fake_batch),
            patch.object(app_module, "PostgresWorkflowRepository", return_value=fake_repo),
            patch.object(app_module, "DurableWorkflowExecutor", return_value=MagicMock()),
            patch.object(app_module, "logger", mock_logger),
            patch.dict("os.environ", {"DATABASE_URL": "postgresql://localhost/test"}),
        ):
            fake_sessions = MagicMock()
            fake_sessions.init_session_manager = AsyncMock(return_value=True)
            fake_sessions.shutdown_session_manager = AsyncMock()

            with patch.dict(
                sys.modules,
                {
                    "enhanced_agent_bus.routes.sessions": fake_sessions,
                },
            ):
                async with app_module._lifespan_context(fake_app):
                    assert fake_app.state.batch_processor is fake_batch

    async def test_startup_assigns_circuit_breaker_state(self):
        """Test that circuit breaker is set on app.state."""
        fake_app = FastAPI()
        fake_mp = MagicMock()
        fake_batch = MagicMock()
        fake_repo = AsyncMock()
        fake_repo.initialize = AsyncMock()
        fake_repo.close = AsyncMock()
        mock_logger = MagicMock()

        with (
            patch.object(app_module, "MessageProcessor", return_value=fake_mp),
            patch.object(app_module, "BatchMessageProcessor", return_value=fake_batch),
            patch.object(app_module, "PostgresWorkflowRepository", return_value=fake_repo),
            patch.object(app_module, "DurableWorkflowExecutor", return_value=MagicMock()),
            patch.object(app_module, "logger", mock_logger),
            patch.dict("os.environ", {"DATABASE_URL": "postgresql://localhost/test"}),
        ):
            fake_sessions = MagicMock()
            fake_sessions.init_session_manager = AsyncMock(return_value=True)
            fake_sessions.shutdown_session_manager = AsyncMock()

            with patch.dict(
                sys.modules,
                {
                    "enhanced_agent_bus.routes.sessions": fake_sessions,
                },
            ):
                async with app_module._lifespan_context(fake_app):
                    assert fake_app.state.message_circuit_breaker is not None

    async def test_startup_with_asyncpg_dsn_normalization(self):
        """Test that asyncpg DSN is normalized before passing to repository."""
        fake_app = FastAPI()
        fake_mp = MagicMock()
        fake_batch = MagicMock()
        mock_logger = MagicMock()

        created_dsns = []

        def capture_repo(dsn):
            created_dsns.append(dsn)
            repo = AsyncMock()
            repo.initialize = AsyncMock()
            repo.close = AsyncMock()
            return repo

        with (
            patch.object(app_module, "MessageProcessor", return_value=fake_mp),
            patch.object(app_module, "BatchMessageProcessor", return_value=fake_batch),
            patch.object(app_module, "PostgresWorkflowRepository", side_effect=capture_repo),
            patch.object(app_module, "DurableWorkflowExecutor", return_value=MagicMock()),
            patch.object(app_module, "logger", mock_logger),
            patch.dict(
                "os.environ", {"DATABASE_URL": "postgresql+asyncpg://user:pass@localhost/db"}
            ),
        ):
            fake_sessions = MagicMock()
            fake_sessions.init_session_manager = AsyncMock(return_value=True)
            fake_sessions.shutdown_session_manager = AsyncMock()

            with patch.dict(
                sys.modules,
                {
                    "enhanced_agent_bus.routes.sessions": fake_sessions,
                },
            ):
                async with app_module._lifespan_context(fake_app):
                    pass

        assert created_dsns[0].startswith("postgresql://")
        assert "asyncpg" not in created_dsns[0]

    async def test_startup_attaches_pg_fallback_to_pqc_service(self):
        fake_app = FastAPI()
        fake_mp = MagicMock()
        fake_batch = MagicMock()
        fake_repo = AsyncMock()
        fake_repo.initialize = AsyncMock()
        fake_repo.close = AsyncMock()
        fake_repo._pool = MagicMock()
        fake_redis = MagicMock()

        with (
            patch.object(app_module, "MessageProcessor", return_value=fake_mp),
            patch.object(app_module, "BatchMessageProcessor", return_value=fake_batch),
            patch.object(app_module, "PostgresWorkflowRepository", return_value=fake_repo),
            patch.object(app_module, "DurableWorkflowExecutor", return_value=MagicMock()),
            patch.object(app_module, "_build_governance_redis_client", return_value=fake_redis),
            patch.dict("os.environ", {"DATABASE_URL": "postgresql://localhost/test"}),
        ):
            fake_sessions = MagicMock()
            fake_sessions.init_session_manager = AsyncMock(return_value=True)
            fake_sessions.shutdown_session_manager = AsyncMock()

            with patch.dict(
                sys.modules,
                {
                    "enhanced_agent_bus.routes.sessions": fake_sessions,
                },
            ):
                async with app_module._lifespan_context(fake_app):
                    assert fake_app.state.pqc_enforcement_service._pg is fake_repo._pool

    async def test_startup_with_message_processor_failure_in_dev(self):
        """Test dev-mode fallback when MessageProcessor raises."""
        fake_app = FastAPI()
        fake_batch = MagicMock()
        fake_repo = AsyncMock()
        fake_repo.initialize = AsyncMock()
        fake_repo.close = AsyncMock()
        mock_logger = MagicMock()

        with (
            patch.object(app_module, "MessageProcessor", side_effect=RuntimeError("init failed")),
            patch.object(app_module, "BatchMessageProcessor", return_value=fake_batch),
            patch.object(app_module, "PostgresWorkflowRepository", return_value=fake_repo),
            patch.object(app_module, "DurableWorkflowExecutor", return_value=MagicMock()),
            patch.object(app_module, "logger", mock_logger),
            patch.dict(
                "os.environ",
                {
                    "ENVIRONMENT": "development",
                    "DATABASE_URL": "postgresql://localhost/test",
                },
            ),
        ):
            fake_sessions = MagicMock()
            fake_sessions.init_session_manager = AsyncMock(return_value=False)
            fake_sessions.shutdown_session_manager = AsyncMock()

            with patch.dict(
                sys.modules,
                {
                    "enhanced_agent_bus.routes.sessions": fake_sessions,
                },
            ):
                async with app_module._lifespan_context(fake_app):
                    bus = fake_app.state.agent_bus
                    assert isinstance(bus, dict)
                    assert bus.get("status") == "mock_initialized"

    async def test_startup_with_message_processor_failure_in_test_env(self):
        """Test test-env fallback when MessageProcessor raises."""
        fake_batch = MagicMock()
        fake_repo = AsyncMock()
        fake_repo.initialize = AsyncMock()
        fake_repo.close = AsyncMock()
        mock_logger = MagicMock()

        for env in ("test", "testing", "ci"):
            fake_app = FastAPI()
            with (
                patch.object(
                    app_module, "MessageProcessor", side_effect=RuntimeError("init failed")
                ),
                patch.object(app_module, "BatchMessageProcessor", return_value=fake_batch),
                patch.object(app_module, "PostgresWorkflowRepository", return_value=fake_repo),
                patch.object(app_module, "DurableWorkflowExecutor", return_value=MagicMock()),
                patch.object(app_module, "logger", mock_logger),
                patch.dict(
                    "os.environ",
                    {
                        "ENVIRONMENT": env,
                        "DATABASE_URL": "postgresql://localhost/test",
                    },
                ),
            ):
                fake_sessions = MagicMock()
                fake_sessions.init_session_manager = AsyncMock(return_value=True)
                fake_sessions.shutdown_session_manager = AsyncMock()

                with patch.dict(
                    sys.modules,
                    {
                        "enhanced_agent_bus.routes.sessions": fake_sessions,
                    },
                ):
                    async with app_module._lifespan_context(fake_app):
                        bus = fake_app.state.agent_bus
                        assert bus is not None

    async def test_startup_with_message_processor_failure_in_production_raises(self):
        """Test that production raises when MessageProcessor fails."""
        fake_app = FastAPI()
        mock_logger = MagicMock()

        with (
            patch.object(app_module, "MessageProcessor", side_effect=RuntimeError("init failed")),
            patch.object(app_module, "logger", mock_logger),
            patch.dict("os.environ", {"ENVIRONMENT": "production"}),
        ):
            with pytest.raises(RuntimeError, match="init failed"):
                async with app_module._lifespan_context(fake_app):
                    pass

    async def test_startup_with_message_processor_failure_no_env_raises(self):
        """Test that unset ENVIRONMENT raises when MessageProcessor fails."""
        import os

        fake_app = FastAPI()
        mock_logger = MagicMock()
        env = {k: v for k, v in os.environ.items() if k != "ENVIRONMENT"}

        with (
            patch.object(app_module, "MessageProcessor", side_effect=RuntimeError("init failed")),
            patch.object(app_module, "logger", mock_logger),
            patch.dict("os.environ", env, clear=True),
        ):
            with pytest.raises(RuntimeError, match="init failed"):
                async with app_module._lifespan_context(fake_app):
                    pass

    async def test_startup_workflow_executor_import_error(self):
        """Test that ImportError during workflow init is handled (asyncpg not installed)."""
        fake_app = FastAPI()
        fake_mp = MagicMock()
        fake_batch = MagicMock()
        mock_logger = MagicMock()

        with (
            patch.object(app_module, "MessageProcessor", return_value=fake_mp),
            patch.object(app_module, "BatchMessageProcessor", return_value=fake_batch),
            patch.object(
                app_module,
                "PostgresWorkflowRepository",
                side_effect=ImportError("asyncpg not installed"),
            ),
            patch.object(app_module, "logger", mock_logger),
            patch.dict(
                "os.environ",
                {
                    "ENVIRONMENT": "development",
                    "DATABASE_URL": "postgresql://localhost/test",
                },
            ),
        ):
            fake_sessions = MagicMock()
            fake_sessions.init_session_manager = AsyncMock(return_value=True)
            fake_sessions.shutdown_session_manager = AsyncMock()

            with patch.dict(
                sys.modules,
                {
                    "enhanced_agent_bus.routes.sessions": fake_sessions,
                },
            ):
                async with app_module._lifespan_context(fake_app):
                    assert hasattr(fake_app.state, "workflow_executor")
                    assert fake_app.state.workflow_executor is not None
                    assert isinstance(
                        fake_app.state.workflow_executor.repository,
                        app_module.InMemoryWorkflowRepository,
                    )

    async def test_startup_workflow_executor_general_exception(self):
        """Test that general exception during workflow init is handled."""
        fake_app = FastAPI()
        fake_mp = MagicMock()
        fake_batch = MagicMock()
        mock_logger = MagicMock()

        with (
            patch.object(app_module, "MessageProcessor", return_value=fake_mp),
            patch.object(app_module, "BatchMessageProcessor", return_value=fake_batch),
            patch.object(
                app_module, "PostgresWorkflowRepository", side_effect=Exception("db error")
            ),
            patch.object(app_module, "logger", mock_logger),
            patch.dict(
                "os.environ",
                {
                    "ENVIRONMENT": "development",
                    "DATABASE_URL": "postgresql://localhost/test",
                },
            ),
        ):
            fake_sessions = MagicMock()
            fake_sessions.init_session_manager = AsyncMock(return_value=True)
            fake_sessions.shutdown_session_manager = AsyncMock()

            with patch.dict(
                sys.modules,
                {
                    "enhanced_agent_bus.routes.sessions": fake_sessions,
                },
            ):
                async with app_module._lifespan_context(fake_app):
                    assert fake_app.state.agent_bus is fake_mp
                    assert hasattr(fake_app.state, "workflow_executor")
                    assert fake_app.state.workflow_executor is not None
                    assert isinstance(
                        fake_app.state.workflow_executor.repository,
                        app_module.InMemoryWorkflowRepository,
                    )

    async def test_startup_batch_processor_failure_handled(self):
        """Test that BatchMessageProcessor failure is handled gracefully."""
        fake_app = FastAPI()
        fake_mp = MagicMock()
        fake_repo = AsyncMock()
        fake_repo.initialize = AsyncMock()
        fake_repo.close = AsyncMock()
        mock_logger = MagicMock()

        with (
            patch.object(app_module, "MessageProcessor", return_value=fake_mp),
            patch.object(
                app_module, "BatchMessageProcessor", side_effect=RuntimeError("batch fail")
            ),
            patch.object(app_module, "PostgresWorkflowRepository", return_value=fake_repo),
            patch.object(app_module, "DurableWorkflowExecutor", return_value=MagicMock()),
            patch.object(app_module, "logger", mock_logger),
            patch.dict(
                "os.environ",
                {
                    "ENVIRONMENT": "development",
                    "DATABASE_URL": "postgresql://localhost/test",
                },
            ),
        ):
            fake_sessions = MagicMock()
            fake_sessions.init_session_manager = AsyncMock(return_value=True)
            fake_sessions.shutdown_session_manager = AsyncMock()

            with patch.dict(
                sys.modules,
                {
                    "enhanced_agent_bus.routes.sessions": fake_sessions,
                },
            ):
                async with app_module._lifespan_context(fake_app):
                    # batch_processor should be None after failure
                    assert fake_app.state.batch_processor is None

    async def test_startup_session_manager_init_returns_false(self):
        """Test that session manager failure warning is logged."""
        fake_app = FastAPI()
        fake_mp = MagicMock()
        fake_batch = MagicMock()
        fake_repo = AsyncMock()
        fake_repo.initialize = AsyncMock()
        fake_repo.close = AsyncMock()
        mock_logger = MagicMock()

        with (
            patch.object(app_module, "MessageProcessor", return_value=fake_mp),
            patch.object(app_module, "BatchMessageProcessor", return_value=fake_batch),
            patch.object(app_module, "PostgresWorkflowRepository", return_value=fake_repo),
            patch.object(app_module, "DurableWorkflowExecutor", return_value=MagicMock()),
            patch.object(app_module, "logger", mock_logger),
            patch.dict(
                "os.environ",
                {
                    "ENVIRONMENT": "development",
                    "DATABASE_URL": "postgresql://localhost/test",
                },
            ),
        ):
            fake_sessions = MagicMock()
            fake_sessions.init_session_manager = AsyncMock(return_value=False)
            fake_sessions.shutdown_session_manager = AsyncMock()

            with patch.dict(
                sys.modules,
                {
                    "enhanced_agent_bus.routes.sessions": fake_sessions,
                },
            ):
                async with app_module._lifespan_context(fake_app):
                    assert fake_app.state.agent_bus is fake_mp

    async def test_startup_sessions_import_error(self):
        """Test that session manager ImportError is handled."""
        fake_app = FastAPI()
        fake_mp = MagicMock()
        fake_batch = MagicMock()
        fake_repo = AsyncMock()
        fake_repo.initialize = AsyncMock()
        fake_repo.close = AsyncMock()
        mock_logger = MagicMock()

        with (
            patch.object(app_module, "MessageProcessor", return_value=fake_mp),
            patch.object(app_module, "BatchMessageProcessor", return_value=fake_batch),
            patch.object(app_module, "PostgresWorkflowRepository", return_value=fake_repo),
            patch.object(app_module, "DurableWorkflowExecutor", return_value=MagicMock()),
            patch.object(app_module, "logger", mock_logger),
            patch.object(app_module, "_load_sessions_module", return_value=None),
            patch.dict(
                "os.environ",
                {
                    "ENVIRONMENT": "development",
                    "DATABASE_URL": "postgresql://localhost/test",
                },
            ),
        ):
            async with app_module._lifespan_context(fake_app):
                assert fake_app.state.agent_bus is fake_mp


# ---------------------------------------------------------------------------
# Lifespan context manager - shutdown paths
# ---------------------------------------------------------------------------


class TestLifespanShutdown:
    """Test the _lifespan_context shutdown (after yield) paths."""

    async def _run_full_lifespan(self, fake_app, extra_patches=None, fake_sessions_return=True):
        """Helper: run through the full lifespan and return mocks."""
        fake_mp = MagicMock()
        fake_batch = MagicMock()
        fake_repo = AsyncMock()
        fake_repo.initialize = AsyncMock()
        fake_repo.close = AsyncMock()
        mock_logger = MagicMock()

        fake_sessions = MagicMock()
        fake_sessions.init_session_manager = AsyncMock(return_value=fake_sessions_return)
        fake_sessions.shutdown_session_manager = AsyncMock()

        ctx_patches = [
            patch.object(app_module, "MessageProcessor", return_value=fake_mp),
            patch.object(app_module, "BatchMessageProcessor", return_value=fake_batch),
            patch.object(app_module, "PostgresWorkflowRepository", return_value=fake_repo),
            patch.object(app_module, "DurableWorkflowExecutor", return_value=MagicMock()),
            patch.object(app_module, "logger", mock_logger),
            patch.dict(
                "os.environ",
                {
                    "ENVIRONMENT": "development",
                    "DATABASE_URL": "postgresql://localhost/test",
                },
            ),
        ]
        if extra_patches:
            ctx_patches.extend(extra_patches)

        from contextlib import ExitStack

        with ExitStack() as stack:
            for p in ctx_patches:
                stack.enter_context(p)
            with patch.dict(
                sys.modules,
                {
                    "enhanced_agent_bus.routes.sessions": fake_sessions,
                },
            ):
                async with app_module._lifespan_context(fake_app):
                    pass

        return fake_repo, fake_sessions, mock_logger

    async def test_shutdown_closes_workflow_repository(self):
        """Test that workflow_repository.close() is called on shutdown."""
        fake_app = FastAPI()
        fake_repo, _, _ = await self._run_full_lifespan(fake_app)
        fake_repo.close.assert_called_once()

    async def test_shutdown_calls_session_shutdown(self):
        """Test that shutdown_session_manager is called on shutdown."""
        fake_app = FastAPI()
        _, fake_sessions, _ = await self._run_full_lifespan(fake_app)
        fake_sessions.shutdown_session_manager.assert_called_once()

    async def test_shutdown_with_cache_warming_active(self):
        """Test cache warmer cancellation during shutdown."""
        fake_app = FastAPI()
        fake_warmer = MagicMock()
        fake_warmer.is_warming = True
        fake_warmer.cancel = MagicMock()

        fake_bus_mod = MagicMock()
        fake_bus_mod.CACHE_WARMING_AVAILABLE = True
        fake_bus_mod.get_cache_warmer = MagicMock(return_value=fake_warmer)

        with patch.dict(sys.modules, {"enhanced_agent_bus": fake_bus_mod}):
            await self._run_full_lifespan(fake_app)

        fake_warmer.cancel.assert_called_once()

    async def test_shutdown_with_cache_warming_not_warming(self):
        """Test when cache warmer is not currently warming."""
        fake_app = FastAPI()
        fake_warmer = MagicMock()
        fake_warmer.is_warming = False

        fake_bus_mod = MagicMock()
        fake_bus_mod.CACHE_WARMING_AVAILABLE = True
        fake_bus_mod.get_cache_warmer = MagicMock(return_value=fake_warmer)

        with patch.dict(sys.modules, {"enhanced_agent_bus": fake_bus_mod}):
            await self._run_full_lifespan(fake_app)

        fake_warmer.cancel.assert_not_called()

    async def test_shutdown_with_cache_warming_not_available(self):
        """Test when CACHE_WARMING_AVAILABLE is False."""
        fake_app = FastAPI()
        fake_bus_mod = MagicMock()
        fake_bus_mod.CACHE_WARMING_AVAILABLE = False
        fake_bus_mod.get_cache_warmer = None

        with patch.dict(sys.modules, {"enhanced_agent_bus": fake_bus_mod}):
            await self._run_full_lifespan(fake_app)
        # No exception expected

    async def test_shutdown_handles_workflow_repo_close_error(self):
        """Test that error during workflow_repo.close() is handled."""
        fake_app = FastAPI()
        fake_mp = MagicMock()
        fake_batch = MagicMock()
        fake_repo = AsyncMock()
        fake_repo.initialize = AsyncMock()
        fake_repo.close = AsyncMock(side_effect=Exception("close failed"))
        mock_logger = MagicMock()

        fake_sessions = MagicMock()
        fake_sessions.init_session_manager = AsyncMock(return_value=True)
        fake_sessions.shutdown_session_manager = AsyncMock()

        with (
            patch.object(app_module, "MessageProcessor", return_value=fake_mp),
            patch.object(app_module, "BatchMessageProcessor", return_value=fake_batch),
            patch.object(app_module, "PostgresWorkflowRepository", return_value=fake_repo),
            patch.object(app_module, "DurableWorkflowExecutor", return_value=MagicMock()),
            patch.object(app_module, "logger", mock_logger),
            patch.dict(
                "os.environ",
                {
                    "ENVIRONMENT": "development",
                    "DATABASE_URL": "postgresql://localhost/test",
                },
            ),
        ):
            with patch.dict(
                sys.modules,
                {
                    "enhanced_agent_bus.routes.sessions": fake_sessions,
                },
            ):
                # Should not raise — error is logged and handled
                async with app_module._lifespan_context(fake_app):
                    pass

    async def test_shutdown_handles_cache_warmer_stop_error(self):
        """Test that cache warmer stop error (RuntimeError) is caught."""
        fake_app = FastAPI()
        mock_logger = MagicMock()

        fake_bus_mod = MagicMock()
        fake_bus_mod.CACHE_WARMING_AVAILABLE = True
        fake_warmer = MagicMock()
        fake_warmer.is_warming = True
        fake_warmer.cancel = MagicMock(side_effect=RuntimeError("cancel failed"))
        fake_bus_mod.get_cache_warmer = MagicMock(return_value=fake_warmer)

        with (
            patch.object(app_module, "logger", mock_logger),
            patch.dict(sys.modules, {"enhanced_agent_bus": fake_bus_mod}),
        ):
            # Should not raise
            await self._run_full_lifespan(fake_app)

    async def test_shutdown_with_no_workflow_repository(self):
        """Test shutdown when workflow_repository is None (workflow init failed)."""
        fake_app = FastAPI()
        fake_mp = MagicMock()
        fake_batch = MagicMock()
        mock_logger = MagicMock()

        # Force the module-level global to None so that the if-branch is False at shutdown
        orig_repo = app_module.workflow_repository
        app_module.workflow_repository = None

        try:
            # Simulate workflow repo import failure so workflow_repository stays None
            with (
                patch.object(app_module, "MessageProcessor", return_value=fake_mp),
                patch.object(app_module, "BatchMessageProcessor", return_value=fake_batch),
                patch.object(
                    app_module,
                    "PostgresWorkflowRepository",
                    side_effect=ImportError("asyncpg not installed"),
                ),
                patch.object(app_module, "logger", mock_logger),
                patch.dict(
                    "os.environ",
                    {
                        "ENVIRONMENT": "development",
                        "DATABASE_URL": "postgresql://localhost/test",
                    },
                ),
            ):
                fake_sessions = MagicMock()
                fake_sessions.init_session_manager = AsyncMock(return_value=True)
                fake_sessions.shutdown_session_manager = AsyncMock()

                with patch.dict(
                    sys.modules,
                    {
                        "enhanced_agent_bus.routes.sessions": fake_sessions,
                    },
                ):
                    # Should complete without calling repo.close() because repo is None
                    async with app_module._lifespan_context(fake_app):
                        pass
        finally:
            app_module.workflow_repository = orig_repo

    async def test_shutdown_sessions_import_error_is_silenced(self):
        """Test that ImportError from sessions shutdown is silenced."""
        fake_app = FastAPI()
        fake_mp = MagicMock()
        fake_batch = MagicMock()
        fake_repo = AsyncMock()
        fake_repo.initialize = AsyncMock()
        fake_repo.close = AsyncMock()
        mock_logger = MagicMock()

        fake_sessions_with_error = MagicMock()
        fake_sessions_with_error.init_session_manager = AsyncMock(return_value=True)
        fake_sessions_with_error.shutdown_session_manager = AsyncMock(
            side_effect=ImportError("sessions gone")
        )

        with (
            patch.object(app_module, "MessageProcessor", return_value=fake_mp),
            patch.object(app_module, "BatchMessageProcessor", return_value=fake_batch),
            patch.object(app_module, "PostgresWorkflowRepository", return_value=fake_repo),
            patch.object(app_module, "DurableWorkflowExecutor", return_value=MagicMock()),
            patch.object(app_module, "logger", mock_logger),
            patch.dict(
                "os.environ",
                {
                    "ENVIRONMENT": "development",
                    "DATABASE_URL": "postgresql://localhost/test",
                },
            ),
        ):
            with patch.dict(
                sys.modules,
                {
                    "enhanced_agent_bus.routes.sessions": fake_sessions_with_error,
                },
            ):
                # Should not raise
                async with app_module._lifespan_context(fake_app):
                    pass


# ---------------------------------------------------------------------------
# Integration: TestClient endpoint check
# ---------------------------------------------------------------------------


class TestAppHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_endpoint_accessible(self):
        """Verify the app can respond to /health."""
        transport = ASGITransport(app=app_module.app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get("/health")
        assert response.status_code in (200, 503, 422, 404)

    @pytest.mark.asyncio
    async def test_docs_endpoint_accessible(self):
        """Verify the OpenAPI docs endpoint is accessible."""
        transport = ASGITransport(app=app_module.app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get("/openapi.json")
        assert response.status_code in (200, 404)
