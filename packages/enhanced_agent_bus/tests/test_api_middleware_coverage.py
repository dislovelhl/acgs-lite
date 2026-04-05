# Constitutional Hash: 608508a9bd224290
# Sprint 56 — api/middleware.py coverage
"""
Comprehensive tests for src/core/enhanced_agent_bus/api/middleware.py
targeting ≥95% coverage.

Covers all branches:
- setup_cors_middleware
- setup_tenant_context_middleware (production vs development ENVIRONMENT)
- setup_security_headers_middleware (SECURITY_HEADERS_AVAILABLE=True/False, dev/prod env)
- setup_api_versioning_middleware (API_VERSIONING_AVAILABLE=True/False)
- setup_correlation_id_middleware (create_correlation_middleware=None, returns None, returns callable)
- setup_all_middleware (orchestration)
- Module-level imports (SECURITY_HEADERS_AVAILABLE, API_VERSIONING_AVAILABLE)
- correlation_id_middleware re-export from api_exceptions
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi import FastAPI

import enhanced_agent_bus.api.middleware as mw_mod

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_app() -> MagicMock:
    """Return a MagicMock that quacks like a FastAPI application."""
    app = MagicMock(spec=FastAPI)
    return app


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------


class TestModuleLevelConstants:
    """Verify module-level flags are exported."""

    def test_security_headers_available_is_bool(self) -> None:
        assert isinstance(mw_mod.SECURITY_HEADERS_AVAILABLE, bool)

    def test_api_versioning_available_is_bool(self) -> None:
        assert isinstance(mw_mod.API_VERSIONING_AVAILABLE, bool)

    def test_correlation_id_middleware_is_callable(self) -> None:
        assert callable(mw_mod.correlation_id_middleware)

    def test_logger_exists(self) -> None:
        assert mw_mod.logger is not None

    def test_all_exports_present(self) -> None:
        for name in mw_mod.__all__:
            assert hasattr(mw_mod, name), f"Missing export: {name}"


# ---------------------------------------------------------------------------
# setup_cors_middleware
# ---------------------------------------------------------------------------


class TestSetupCorsMiddleware:
    def test_adds_cors_middleware(self) -> None:
        app = _make_app()
        mock_config = {
            "allow_origins": ["*"],
            "allow_credentials": True,
            "allow_methods": ["*"],
            "allow_headers": ["*"],
        }
        with patch.object(mw_mod, "get_cors_config", return_value=mock_config):
            mw_mod.setup_cors_middleware(app)

        app.add_middleware.assert_called_once()
        call_args = app.add_middleware.call_args
        # First positional arg should be CORSMiddleware
        from fastapi.middleware.cors import CORSMiddleware

        assert call_args[0][0] is CORSMiddleware

    def test_cors_config_kwargs_forwarded(self) -> None:
        app = _make_app()
        mock_config = {"allow_origins": ["https://example.com"], "allow_credentials": False}
        with patch.object(mw_mod, "get_cors_config", return_value=mock_config):
            mw_mod.setup_cors_middleware(app)

        _, kwargs = app.add_middleware.call_args
        assert kwargs["allow_origins"] == ["https://example.com"]
        assert kwargs["allow_credentials"] is False


# ---------------------------------------------------------------------------
# setup_tenant_context_middleware
# ---------------------------------------------------------------------------


class TestSetupTenantContextMiddleware:
    def test_production_env_required_stays_true(self) -> None:
        app = _make_app()
        fake_config = MagicMock()
        fake_config.required = True
        fake_config.exempt_paths = ["/health"]

        with (
            patch.dict("os.environ", {"ENVIRONMENT": "production"}),
            patch.object(mw_mod, "TenantContextConfig") as MockConfig,
            patch.object(mw_mod, "TenantContextMiddleware") as MockMw,
        ):
            MockConfig.from_env.return_value = fake_config
            mw_mod.setup_tenant_context_middleware(app)

        # required must NOT have been set to False
        assert fake_config.required is True
        app.add_middleware.assert_called_once_with(MockMw, config=fake_config)

    def test_development_env_sets_required_false(self) -> None:
        app = _make_app()
        fake_config = MagicMock()
        fake_config.required = True
        fake_config.exempt_paths = []

        with (
            patch.dict("os.environ", {"ENVIRONMENT": "development"}),
            patch.object(mw_mod, "TenantContextConfig") as MockConfig,
            patch.object(mw_mod, "TenantContextMiddleware"),
        ):
            MockConfig.from_env.return_value = fake_config
            mw_mod.setup_tenant_context_middleware(app)

        # The function must have set required=False for development
        assert fake_config.required is False

    def test_no_environment_var_does_not_set_required_false(self) -> None:
        """When ENVIRONMENT is absent, required must not be altered."""
        app = _make_app()
        fake_config = MagicMock()
        fake_config.required = True
        fake_config.exempt_paths = []

        with (
            patch.dict("os.environ", {}, clear=False),
            patch.object(mw_mod, "TenantContextConfig") as MockConfig,
            patch.object(mw_mod, "TenantContextMiddleware"),
        ):
            # Ensure ENVIRONMENT is not set
            import os

            os.environ.pop("ENVIRONMENT", None)
            MockConfig.from_env.return_value = fake_config
            mw_mod.setup_tenant_context_middleware(app)

        # required should remain True
        assert fake_config.required is True

    def test_logs_info_with_config_details(self) -> None:
        app = _make_app()
        fake_config = MagicMock()
        fake_config.required = True
        fake_config.exempt_paths = ["/health", "/metrics"]

        with (
            patch.dict("os.environ", {"ENVIRONMENT": "staging"}),
            patch.object(mw_mod, "TenantContextConfig") as MockConfig,
            patch.object(mw_mod, "TenantContextMiddleware"),
            patch.object(mw_mod.logger, "info") as mock_log,
        ):
            MockConfig.from_env.return_value = fake_config
            mw_mod.setup_tenant_context_middleware(app)

        mock_log.assert_called_once()
        call_kwargs = mock_log.call_args[1]
        assert "required" in call_kwargs["extra"]
        assert "exempt_paths" in call_kwargs["extra"]


# ---------------------------------------------------------------------------
# setup_security_headers_middleware
# ---------------------------------------------------------------------------


class TestSetupSecurityHeadersMiddleware:
    def test_skips_when_not_available(self) -> None:
        app = _make_app()
        with patch.dict(mw_mod.__dict__, {"SECURITY_HEADERS_AVAILABLE": False}):
            mw_mod.setup_security_headers_middleware(app)

        app.add_middleware.assert_not_called()

    def test_skips_logs_warning_when_not_available(self) -> None:
        app = _make_app()
        with (
            patch.dict(mw_mod.__dict__, {"SECURITY_HEADERS_AVAILABLE": False}),
            patch.object(mw_mod.logger, "warning") as mock_warn,
        ):
            mw_mod.setup_security_headers_middleware(app)

        mock_warn.assert_called_once()
        assert "not available" in mock_warn.call_args[0][0].lower()

    def test_development_uses_for_development(self) -> None:
        app = _make_app()
        mock_config = MagicMock()

        with (
            patch.dict(mw_mod.__dict__, {"SECURITY_HEADERS_AVAILABLE": True}),
            patch.dict("os.environ", {"ENVIRONMENT": "development"}),
            patch.object(mw_mod, "SecurityHeadersConfig") as MockCfg,
            patch.object(mw_mod, "SecurityHeadersMiddleware") as MockMw,
        ):
            MockCfg.for_development.return_value = mock_config
            mw_mod.setup_security_headers_middleware(app)

        MockCfg.for_development.assert_called_once()
        MockCfg.for_production.assert_not_called()
        app.add_middleware.assert_called_once_with(MockMw, config=mock_config)

    def test_production_uses_for_production(self) -> None:
        app = _make_app()
        mock_config = MagicMock()

        with (
            patch.dict(mw_mod.__dict__, {"SECURITY_HEADERS_AVAILABLE": True}),
            patch.dict("os.environ", {"ENVIRONMENT": "production"}),
            patch.object(mw_mod, "SecurityHeadersConfig") as MockCfg,
            patch.object(mw_mod, "SecurityHeadersMiddleware") as MockMw,
        ):
            MockCfg.for_production.return_value = mock_config
            mw_mod.setup_security_headers_middleware(app)

        MockCfg.for_production.assert_called_once()
        MockCfg.for_development.assert_not_called()
        app.add_middleware.assert_called_once_with(MockMw, config=mock_config)

    def test_no_environment_defaults_to_production(self) -> None:
        """When ENVIRONMENT is absent, defaults to 'production'."""
        app = _make_app()
        mock_config = MagicMock()

        import os

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ENVIRONMENT", None)

            with (
                patch.dict(mw_mod.__dict__, {"SECURITY_HEADERS_AVAILABLE": True}),
                patch.object(mw_mod, "SecurityHeadersConfig") as MockCfg,
                patch.object(mw_mod, "SecurityHeadersMiddleware"),
            ):
                MockCfg.for_production.return_value = mock_config
                mw_mod.setup_security_headers_middleware(app)

            MockCfg.for_production.assert_called_once()

    def test_logs_info_when_available(self) -> None:
        app = _make_app()
        mock_config = MagicMock()

        with (
            patch.dict(mw_mod.__dict__, {"SECURITY_HEADERS_AVAILABLE": True}),
            patch.dict("os.environ", {"ENVIRONMENT": "staging"}),
            patch.object(mw_mod, "SecurityHeadersConfig") as MockCfg,
            patch.object(mw_mod, "SecurityHeadersMiddleware"),
            patch.object(mw_mod.logger, "info") as mock_log,
        ):
            MockCfg.for_production.return_value = mock_config
            mw_mod.setup_security_headers_middleware(app)

        mock_log.assert_called_once()
        assert "environment" in mock_log.call_args[1]["extra"]


# ---------------------------------------------------------------------------
# setup_api_versioning_middleware
# ---------------------------------------------------------------------------


class TestSetupApiVersioningMiddleware:
    def test_skips_when_not_available(self) -> None:
        app = _make_app()
        with patch.dict(
            mw_mod.__dict__,
            {"API_VERSIONING_AVAILABLE": False, "APIVersioningMiddleware": None},
        ):
            mw_mod.setup_api_versioning_middleware(app)

        app.add_middleware.assert_not_called()

    def test_skips_when_middleware_is_none(self) -> None:
        """Even if API_VERSIONING_AVAILABLE=True but class is None, skip."""
        app = _make_app()
        with patch.dict(
            mw_mod.__dict__,
            {"API_VERSIONING_AVAILABLE": True, "APIVersioningMiddleware": None},
        ):
            mw_mod.setup_api_versioning_middleware(app)

        app.add_middleware.assert_not_called()

    def test_logs_warning_when_not_available(self) -> None:
        app = _make_app()
        with (
            patch.dict(
                mw_mod.__dict__,
                {"API_VERSIONING_AVAILABLE": False, "APIVersioningMiddleware": None},
            ),
            patch.object(mw_mod.logger, "warning") as mock_warn,
        ):
            mw_mod.setup_api_versioning_middleware(app)

        mock_warn.assert_called_once()
        assert "not available" in mock_warn.call_args[0][0].lower()

    def test_adds_middleware_when_available(self) -> None:
        app = _make_app()

        MockVersioningConfig = MagicMock()
        mock_versioning_instance = MagicMock()
        MockVersioningConfig.return_value = mock_versioning_instance
        mock_versioning_instance.default_version = "v1"
        mock_versioning_instance.supported_versions = {"v1", "v2"}
        MockApiVersioningMiddleware = MagicMock()

        with patch.dict(
            mw_mod.__dict__,
            {
                "API_VERSIONING_AVAILABLE": True,
                "APIVersioningMiddleware": MockApiVersioningMiddleware,
                "VersioningConfig": MockVersioningConfig,
            },
        ):
            mw_mod.setup_api_versioning_middleware(app)

        app.add_middleware.assert_called_once_with(
            MockApiVersioningMiddleware, config=mock_versioning_instance
        )

    def test_versioning_config_created_with_correct_defaults(self) -> None:
        app = _make_app()

        captured_configs = []

        def capture_config(**kwargs):
            captured_configs.append(kwargs)
            m = MagicMock()
            m.default_version = kwargs.get("default_version", "v1")
            m.supported_versions = kwargs.get("supported_versions", set())
            return m

        MockVersioningConfig = MagicMock(side_effect=capture_config)
        MockApiVersioningMiddleware = MagicMock()

        with patch.dict(
            mw_mod.__dict__,
            {
                "API_VERSIONING_AVAILABLE": True,
                "APIVersioningMiddleware": MockApiVersioningMiddleware,
                "VersioningConfig": MockVersioningConfig,
            },
        ):
            mw_mod.setup_api_versioning_middleware(app)

        assert len(captured_configs) == 1
        cfg = captured_configs[0]
        assert cfg["default_version"] == "v1"
        assert "v1" in cfg["supported_versions"]
        assert "v2" in cfg["supported_versions"]
        assert "/health" in cfg["exempt_paths"]
        assert "/metrics" in cfg["exempt_paths"]
        assert "/docs" in cfg["exempt_paths"]
        assert cfg["enable_metrics"] is True
        assert cfg["strict_versioning"] is False
        assert cfg["log_version_usage"] is True

    def test_logs_info_when_added(self) -> None:
        app = _make_app()
        mock_versioning_instance = MagicMock()
        mock_versioning_instance.default_version = "v1"
        mock_versioning_instance.supported_versions = {"v1", "v2"}
        MockVersioningConfig = MagicMock(return_value=mock_versioning_instance)
        MockApiVersioningMiddleware = MagicMock()

        with (
            patch.dict(
                mw_mod.__dict__,
                {
                    "API_VERSIONING_AVAILABLE": True,
                    "APIVersioningMiddleware": MockApiVersioningMiddleware,
                    "VersioningConfig": MockVersioningConfig,
                },
            ),
            patch.object(mw_mod.logger, "info") as mock_log,
        ):
            mw_mod.setup_api_versioning_middleware(app)

        mock_log.assert_called_once()
        call_kwargs = mock_log.call_args[1]
        assert "default_version" in call_kwargs["extra"]
        assert "supported_versions" in call_kwargs["extra"]


# ---------------------------------------------------------------------------
# setup_correlation_id_middleware
# ---------------------------------------------------------------------------


class TestSetupCorrelationIdMiddleware:
    def test_does_nothing_when_create_correlation_middleware_is_none(self) -> None:
        app = _make_app()
        with patch.dict(mw_mod.__dict__, {"create_correlation_middleware": None}):
            mw_mod.setup_correlation_id_middleware(app)

        app.middleware.assert_not_called()

    def test_does_nothing_when_factory_returns_none(self) -> None:
        app = _make_app()
        mock_factory = MagicMock(return_value=None)
        with patch.dict(mw_mod.__dict__, {"create_correlation_middleware": mock_factory}):
            mw_mod.setup_correlation_id_middleware(app)

        app.middleware.assert_not_called()

    def test_registers_middleware_when_factory_returns_callable(self) -> None:
        app = _make_app()
        fake_mw = MagicMock()
        mock_factory = MagicMock(return_value=fake_mw)

        # app.middleware("http") returns a decorator; we need it to accept a callable
        mock_decorator = MagicMock()
        app.middleware.return_value = mock_decorator

        with patch.dict(mw_mod.__dict__, {"create_correlation_middleware": mock_factory}):
            mw_mod.setup_correlation_id_middleware(app)

        app.middleware.assert_called_once_with("http")
        mock_decorator.assert_called_once_with(fake_mw)

    def test_factory_called_once(self) -> None:
        app = _make_app()
        fake_mw = MagicMock()
        mock_factory = MagicMock(return_value=fake_mw)
        app.middleware.return_value = MagicMock()

        with patch.dict(mw_mod.__dict__, {"create_correlation_middleware": mock_factory}):
            mw_mod.setup_correlation_id_middleware(app)

        mock_factory.assert_called_once_with()


# ---------------------------------------------------------------------------
# setup_all_middleware
# ---------------------------------------------------------------------------


class TestSetupAllMiddleware:
    def test_calls_all_setup_functions(self) -> None:
        app = _make_app()

        with (
            patch.object(mw_mod, "setup_correlation_id_middleware") as mock_corr,
            patch.object(mw_mod, "setup_cors_middleware") as mock_cors,
            patch.object(mw_mod, "setup_tenant_context_middleware") as mock_tenant,
            patch.object(mw_mod, "setup_security_headers_middleware") as mock_sec,
            patch.object(mw_mod, "setup_api_versioning_middleware") as mock_ver,
        ):
            mw_mod.setup_all_middleware(app)

        mock_corr.assert_called_once_with(app)
        mock_cors.assert_called_once_with(app)
        mock_tenant.assert_called_once_with(app)
        mock_sec.assert_called_once_with(app)
        mock_ver.assert_called_once_with(app)

    def test_order_of_calls(self) -> None:
        """Correlation ID → CORS → Tenant → Security Headers → API Versioning."""
        app = _make_app()
        call_order = []

        with (
            patch.object(
                mw_mod,
                "setup_correlation_id_middleware",
                side_effect=lambda a: call_order.append("correlation"),
            ),
            patch.object(
                mw_mod,
                "setup_cors_middleware",
                side_effect=lambda a: call_order.append("cors"),
            ),
            patch.object(
                mw_mod,
                "setup_tenant_context_middleware",
                side_effect=lambda a: call_order.append("tenant"),
            ),
            patch.object(
                mw_mod,
                "setup_security_headers_middleware",
                side_effect=lambda a: call_order.append("security"),
            ),
            patch.object(
                mw_mod,
                "setup_api_versioning_middleware",
                side_effect=lambda a: call_order.append("versioning"),
            ),
        ):
            mw_mod.setup_all_middleware(app)

        assert call_order == ["correlation", "cors", "tenant", "security", "versioning"]


# ---------------------------------------------------------------------------
# Integration-style: run setup_all_middleware with real FastAPI app
# ---------------------------------------------------------------------------


class TestIntegrationWithRealFastAPI:
    """Smoke tests that call setup helpers on a real FastAPI instance."""

    def test_setup_cors_with_real_app(self) -> None:
        app = FastAPI()
        # Should not raise
        mw_mod.setup_cors_middleware(app)

    def test_setup_tenant_context_with_real_app_development(self) -> None:
        import os

        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            app = FastAPI()
            mw_mod.setup_tenant_context_middleware(app)

    def test_setup_tenant_context_with_real_app_production(self) -> None:
        import os

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ENVIRONMENT", None)
            app = FastAPI()
            mw_mod.setup_tenant_context_middleware(app)

    def test_setup_security_headers_available(self) -> None:
        app = FastAPI()
        # Either path (available or not) must not raise
        mw_mod.setup_security_headers_middleware(app)

    def test_setup_api_versioning_not_available(self) -> None:
        app = FastAPI()
        with patch.dict(
            mw_mod.__dict__,
            {"API_VERSIONING_AVAILABLE": False, "APIVersioningMiddleware": None},
        ):
            mw_mod.setup_api_versioning_middleware(app)

    def test_setup_correlation_id_none_factory(self) -> None:
        app = FastAPI()
        with patch.dict(mw_mod.__dict__, {"create_correlation_middleware": None}):
            mw_mod.setup_correlation_id_middleware(app)

    def test_setup_all_middleware_real_app(self) -> None:
        app = FastAPI()
        # Should complete without exception regardless of which optionals are present
        mw_mod.setup_all_middleware(app)


# ---------------------------------------------------------------------------
# correlation_id_middleware re-export
# ---------------------------------------------------------------------------


class TestCorrelationIdMiddlewareReExport:
    """Verify that correlation_id_middleware is re-exported from api_exceptions."""

    def test_is_same_as_api_exceptions_export(self) -> None:
        from enhanced_agent_bus.api_exceptions import (
            correlation_id_middleware as orig,
        )

        assert mw_mod.correlation_id_middleware is orig

    async def test_middleware_adds_correlation_header(self) -> None:
        """Smoke-test the actual middleware callable."""
        request = MagicMock()
        request.headers = {}
        response = MagicMock()
        response.headers = {}

        async def call_next(req):
            return response

        result = await mw_mod.correlation_id_middleware(request, call_next)
        assert "X-Correlation-ID" in result.headers

    async def test_middleware_preserves_existing_correlation_id(self) -> None:
        existing_id = "existing-correlation-123"
        request = MagicMock()
        request.headers = {"X-Correlation-ID": existing_id}
        response = MagicMock()
        response.headers = {}

        async def call_next(req):
            return response

        result = await mw_mod.correlation_id_middleware(request, call_next)
        assert result.headers["X-Correlation-ID"] == existing_id
