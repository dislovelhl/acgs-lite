"""
Tests for Security Headers Middleware
Constitutional Hash: 608508a9bd224290

Tests verify:
- SecurityHeadersConfig dataclass (defaults, custom config, environment-based configs)
- Environment-specific configuration methods (development, production, WebSocket, integration)
- CSP header value generation and custom directives
- HSTS header value generation with various options
- SecurityHeadersMiddleware integration with FastAPI
- All six security headers present in responses
- add_security_headers convenience function
"""

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.shared.security.security_headers import (
    CONSTITUTIONAL_HASH,
    SecurityHeadersConfig,
    SecurityHeadersMiddleware,
    add_security_headers,
)

# ============================================================================
# SecurityHeadersConfig Tests - Defaults and Basic Configuration
# ============================================================================


class TestSecurityHeadersConfigDefaults:
    """Test SecurityHeadersConfig default values."""

    def test_default_config(self):
        """Test default configuration values."""
        config = SecurityHeadersConfig()
        assert config.environment == "production"
        assert config.enable_hsts is True
        assert config.hsts_max_age == 31536000  # 1 year
        assert config.hsts_include_subdomains is True
        assert config.hsts_preload is False
        assert config.custom_csp_directives is None
        assert config.frame_options == "DENY"
        assert config.referrer_policy == "strict-origin-when-cross-origin"
        assert config.enable_xss_protection is True

    def test_custom_config(self):
        """Test custom configuration values."""
        config = SecurityHeadersConfig(
            environment="development",
            enable_hsts=False,
            hsts_max_age=300,
            hsts_include_subdomains=False,
            hsts_preload=True,
            custom_csp_directives={"default-src": ["'self'"]},
            frame_options="SAMEORIGIN",
            referrer_policy="no-referrer",
            enable_xss_protection=False,
        )
        assert config.environment == "development"
        assert config.enable_hsts is False
        assert config.hsts_max_age == 300
        assert config.hsts_include_subdomains is False
        assert config.hsts_preload is True
        assert config.custom_csp_directives == {"default-src": ["'self'"]}
        assert config.frame_options == "SAMEORIGIN"
        assert config.referrer_policy == "no-referrer"
        assert config.enable_xss_protection is False


# ============================================================================
# SecurityHeadersConfig Tests - from_env Method
# ============================================================================


class TestSecurityHeadersConfigFromEnv:
    """Test SecurityHeadersConfig.from_env() method."""

    def test_from_env_defaults_production(self, monkeypatch):
        """Test from_env with production environment (production defaults)."""
        from src.core.shared.config import settings

        monkeypatch.setattr(settings, "env", "production")
        # Clear env vars that would override settings.env (e.g. conftest sets ENVIRONMENT=test)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.delenv("ACGS2_ENV", raising=False)
        for key in ["SECURITY_HSTS_ENABLED", "SECURITY_HSTS_MAX_AGE", "SECURITY_FRAME_OPTIONS"]:
            monkeypatch.delenv(key, raising=False)

        config = SecurityHeadersConfig.from_env()
        assert config.environment == "production"
        assert config.enable_hsts is True
        assert config.hsts_max_age == 31536000  # 1 year

    def test_from_env_development(self, monkeypatch):
        """Test from_env with development environment."""
        from src.core.shared.config import settings

        monkeypatch.setattr(settings, "env", "development")
        # Clear env vars that override settings.env (e.g. EAB conftest sets ENVIRONMENT=test)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.delenv("ACGS2_ENV", raising=False)
        monkeypatch.delenv("SECURITY_HSTS_ENABLED", raising=False)
        monkeypatch.delenv("SECURITY_HSTS_MAX_AGE", raising=False)

        config = SecurityHeadersConfig.from_env()
        assert config.environment == "development"
        assert config.enable_hsts is False  # Disabled by default in dev
        assert config.hsts_max_age == 300  # 5 minutes

    def test_from_env_staging(self, monkeypatch):
        """Test from_env with staging environment."""
        from src.core.shared.config import settings

        monkeypatch.setattr(settings, "env", "staging")
        # Clear env vars that override settings.env (e.g. EAB conftest sets ENVIRONMENT=test)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.delenv("ACGS2_ENV", raising=False)
        monkeypatch.delenv("SECURITY_HSTS_ENABLED", raising=False)
        monkeypatch.delenv("SECURITY_HSTS_MAX_AGE", raising=False)

        config = SecurityHeadersConfig.from_env()
        assert config.environment == "staging"
        assert config.enable_hsts is True
        assert config.hsts_max_age == 86400  # 1 day

    def test_from_env_custom_hsts_enabled(self, monkeypatch):
        """Test from_env with custom HSTS enabled setting."""
        from src.core.shared.config import settings

        monkeypatch.setattr(settings, "env", "development")
        # Clear env vars that override settings.env (e.g. EAB conftest sets ENVIRONMENT=test)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.delenv("ACGS2_ENV", raising=False)
        monkeypatch.setenv("SECURITY_HSTS_ENABLED", "true")

        config = SecurityHeadersConfig.from_env()
        assert config.enable_hsts is True

    def test_from_env_custom_hsts_disabled(self, monkeypatch):
        """Test from_env with custom HSTS disabled setting."""
        from src.core.shared.config import settings

        monkeypatch.setattr(settings, "env", "production")
        # Clear env vars that would override settings.env (e.g. conftest sets ENVIRONMENT=test)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.delenv("ACGS2_ENV", raising=False)
        monkeypatch.setenv("SECURITY_HSTS_ENABLED", "false")

        config = SecurityHeadersConfig.from_env()
        assert config.enable_hsts is False

    def test_from_env_custom_hsts_max_age(self, monkeypatch):
        """Test from_env with custom HSTS max-age."""
        from src.core.shared.config import settings

        monkeypatch.setattr(settings, "env", "production")
        # Clear env vars that would override settings.env (e.g. conftest sets ENVIRONMENT=test)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.delenv("ACGS2_ENV", raising=False)
        monkeypatch.setenv("SECURITY_HSTS_MAX_AGE", "7200")

        config = SecurityHeadersConfig.from_env()
        assert config.hsts_max_age == 7200

    def test_from_env_custom_frame_options(self, monkeypatch):
        """Test from_env with custom frame options."""
        monkeypatch.setenv("SECURITY_FRAME_OPTIONS", "SAMEORIGIN")

        config = SecurityHeadersConfig.from_env()
        assert config.frame_options == "SAMEORIGIN"

    def test_from_env_case_insensitive_environment(self, monkeypatch):
        """Test from_env reflects settings.env when no explicit env vars override it."""
        from src.core.shared.config import settings

        monkeypatch.setattr(settings, "env", "production")
        # Clear env vars that would override settings.env (e.g. conftest sets ENVIRONMENT=test)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.delenv("ACGS2_ENV", raising=False)
        config = SecurityHeadersConfig.from_env()
        assert config.environment == "production"

        monkeypatch.setattr(settings, "env", "development")
        # Clear env vars that override settings.env (e.g. EAB conftest sets ENVIRONMENT=test)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.delenv("ACGS2_ENV", raising=False)
        config = SecurityHeadersConfig.from_env()
        assert config.environment == "development"

    def test_from_env_settings_env_is_canonical_source(self, monkeypatch):
        """Test that settings.env is used when no explicit runtime env vars are set."""
        from src.core.shared.config import settings

        monkeypatch.setattr(settings, "env", "development")
        # Clear env vars that override settings.env (e.g. EAB conftest sets ENVIRONMENT=test)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.delenv("ACGS2_ENV", raising=False)
        config = SecurityHeadersConfig.from_env()
        assert config.environment == "development"

    def test_from_env_fallback_to_environment_when_app_env_unset(self, monkeypatch):
        from src.core.shared.config import settings

        monkeypatch.setattr(settings, "env", "staging")
        # Clear env vars that override settings.env (e.g. EAB conftest sets ENVIRONMENT=test)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.delenv("ACGS2_ENV", raising=False)

        config = SecurityHeadersConfig.from_env()
        assert config.environment == "staging"

    def test_from_env_prefers_environment_over_defaulted_settings_env(self, monkeypatch):
        from src.core.shared.config import settings

        monkeypatch.setattr(settings, "env", "development")
        # Clear env vars that override settings.env (e.g. EAB conftest sets ENVIRONMENT=test)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.delenv("ACGS2_ENV", raising=False)
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.setenv("ENVIRONMENT", "production")

        config = SecurityHeadersConfig.from_env()
        assert config.environment == "production"
        assert config.enable_hsts is True


# ============================================================================
# SecurityHeadersConfig Tests - Environment-Specific Factories
# ============================================================================


class TestSecurityHeadersConfigFactories:
    """Test SecurityHeadersConfig factory methods."""

    def test_for_development(self):
        """Test for_development creates development-friendly config."""
        config = SecurityHeadersConfig.for_development()
        assert config.environment == "development"
        assert config.enable_hsts is False
        assert config.hsts_max_age == 300  # 5 minutes
        assert config.hsts_include_subdomains is False
        assert config.custom_csp_directives is not None
        assert "default-src" in config.custom_csp_directives
        assert "'self'" in config.custom_csp_directives["default-src"]
        assert "script-src" in config.custom_csp_directives
        assert "'unsafe-inline'" in config.custom_csp_directives["script-src"]
        assert "'unsafe-eval'" in config.custom_csp_directives["script-src"]
        assert "connect-src" in config.custom_csp_directives
        assert "localhost:*" in config.custom_csp_directives["connect-src"]

    def test_for_production_default(self):
        """Test for_production creates strict production config."""
        config = SecurityHeadersConfig.for_production()
        assert config.environment == "production"
        assert config.enable_hsts is True
        assert config.hsts_max_age == 31536000  # 1 year
        assert config.hsts_include_subdomains is True
        assert config.hsts_preload is True
        assert config.custom_csp_directives is not None
        assert "default-src" in config.custom_csp_directives
        assert config.custom_csp_directives["default-src"] == ["'self'"]
        assert "script-src" in config.custom_csp_directives
        assert config.custom_csp_directives["script-src"] == ["'self'"]
        assert "frame-ancestors" in config.custom_csp_directives
        assert config.custom_csp_directives["frame-ancestors"] == ["'none'"]
        assert config.frame_options == "DENY"

    def test_for_production_non_strict(self):
        """Test for_production with strict=False."""
        config = SecurityHeadersConfig.for_production(strict=False)
        assert config.environment == "production"
        assert config.enable_hsts is True
        assert config.custom_csp_directives is None

    def test_for_websocket_service(self):
        """Test for_websocket_service creates WebSocket-enabled config."""
        config = SecurityHeadersConfig.for_websocket_service()
        assert config.environment == "production"
        assert config.enable_hsts is True
        assert config.hsts_max_age == 31536000
        assert config.custom_csp_directives is not None
        assert "connect-src" in config.custom_csp_directives
        assert "ws:" in config.custom_csp_directives["connect-src"]
        assert "wss:" in config.custom_csp_directives["connect-src"]
        assert "style-src" in config.custom_csp_directives
        assert "'unsafe-inline'" in config.custom_csp_directives["style-src"]

    def test_for_integration_service(self):
        """Test for_integration_service creates integration-friendly config."""
        config = SecurityHeadersConfig.for_integration_service()
        assert config.environment == "production"
        assert config.enable_hsts is True
        assert config.hsts_max_age == 31536000
        assert config.custom_csp_directives is not None
        assert "connect-src" in config.custom_csp_directives
        assert "https:" in config.custom_csp_directives["connect-src"]
        assert "img-src" in config.custom_csp_directives
        assert "https:" in config.custom_csp_directives["img-src"]


# ============================================================================
# SecurityHeadersConfig Tests - CSP Header Generation
# ============================================================================


class TestSecurityHeadersConfigCSP:
    """Test CSP header value generation."""

    def test_get_csp_header_value_default(self):
        """Test CSP header generation with default directives."""
        config = SecurityHeadersConfig()
        csp = config.get_csp_header_value()

        assert "default-src 'self'" in csp
        assert "script-src 'self'" in csp
        assert "style-src 'self'" in csp
        assert "img-src 'self' data:" in csp
        assert "font-src 'self'" in csp
        assert "connect-src 'self'" in csp
        assert "frame-ancestors 'none'" in csp
        assert "base-uri 'self'" in csp
        assert "form-action 'self'" in csp

    def test_get_csp_header_value_custom_directives(self):
        """Test CSP header generation with custom directives."""
        config = SecurityHeadersConfig(
            custom_csp_directives={
                "default-src": ["'self'", "https://example.com"],
                "script-src": ["'self'", "'unsafe-inline'"],
                "connect-src": ["'self'", "wss://ws.example.com"],
            }
        )
        csp = config.get_csp_header_value()

        assert "default-src 'self' https://example.com" in csp
        assert "script-src 'self' 'unsafe-inline'" in csp
        assert "connect-src 'self' wss://ws.example.com" in csp
        # Should still have other default directives
        assert "base-uri 'self'" in csp
        assert "form-action 'self'" in csp

    def test_get_csp_header_value_custom_overrides_defaults(self):
        """Test custom CSP directives override defaults."""
        config = SecurityHeadersConfig(
            custom_csp_directives={
                "default-src": ["'none'"],
                "script-src": ["'self'", "https://cdn.example.com"],
            }
        )
        csp = config.get_csp_header_value()

        # Custom directive should override default
        assert "default-src 'none'" in csp
        assert "default-src 'self'" not in csp
        assert "script-src 'self' https://cdn.example.com" in csp

    def test_get_csp_header_value_websocket_config(self):
        """Test CSP header for WebSocket service config."""
        config = SecurityHeadersConfig.for_websocket_service()
        csp = config.get_csp_header_value()

        assert "connect-src 'self' ws: wss:" in csp
        assert "style-src 'self' 'unsafe-inline'" in csp

    def test_get_csp_header_value_development_config(self):
        """Test CSP header for development config."""
        config = SecurityHeadersConfig.for_development()
        csp = config.get_csp_header_value()

        assert "'unsafe-inline'" in csp
        assert "'unsafe-eval'" in csp
        assert "localhost:*" in csp


# ============================================================================
# SecurityHeadersConfig Tests - HSTS Header Generation
# ============================================================================


class TestSecurityHeadersConfigHSTS:
    """Test HSTS header value generation."""

    def test_get_hsts_header_value_default(self):
        """Test HSTS header generation with defaults."""
        config = SecurityHeadersConfig()
        hsts = config.get_hsts_header_value()

        assert hsts is not None
        assert "max-age=31536000" in hsts
        assert "includeSubDomains" in hsts
        assert "preload" not in hsts

    def test_get_hsts_header_value_disabled(self):
        """Test HSTS header generation when disabled."""
        config = SecurityHeadersConfig(enable_hsts=False)
        hsts = config.get_hsts_header_value()
        assert hsts is None

    def test_get_hsts_header_value_with_preload(self):
        """Test HSTS header generation with preload."""
        config = SecurityHeadersConfig(hsts_preload=True)
        hsts = config.get_hsts_header_value()

        assert "max-age=31536000" in hsts
        assert "includeSubDomains" in hsts
        assert "preload" in hsts

    def test_get_hsts_header_value_without_subdomains(self):
        """Test HSTS header generation without subdomains."""
        config = SecurityHeadersConfig(hsts_include_subdomains=False)
        hsts = config.get_hsts_header_value()

        assert "max-age=31536000" in hsts
        assert "includeSubDomains" not in hsts

    def test_get_hsts_header_value_custom_max_age(self):
        """Test HSTS header generation with custom max-age."""
        config = SecurityHeadersConfig(hsts_max_age=7200)
        hsts = config.get_hsts_header_value()
        assert "max-age=7200" in hsts

    def test_get_hsts_header_value_development(self):
        """Test HSTS header for development config."""
        config = SecurityHeadersConfig.for_development()
        hsts = config.get_hsts_header_value()
        assert hsts is None  # Disabled in development

    def test_get_hsts_header_value_production(self):
        """Test HSTS header for production config."""
        config = SecurityHeadersConfig.for_production()
        hsts = config.get_hsts_header_value()

        assert hsts is not None
        assert "max-age=31536000" in hsts
        assert "includeSubDomains" in hsts
        assert "preload" in hsts


# ============================================================================
# SecurityHeadersMiddleware Tests - Basic Functionality
# ============================================================================


class TestSecurityHeadersMiddlewareBasic:
    """Test SecurityHeadersMiddleware basic functionality."""

    def create_test_app(self, config: SecurityHeadersConfig = None) -> FastAPI:
        """Create a test FastAPI app with security headers middleware."""
        app = FastAPI()
        if config:
            app.add_middleware(SecurityHeadersMiddleware, config=config)
        else:
            app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/")
        async def root():
            return {"message": "Hello World"}

        @app.get("/api/data")
        async def api_data():
            return {"data": [1, 2, 3]}

        @app.post("/api/create")
        async def api_create(data: dict):
            return {"created": True, "data": data}

        return app

    def test_middleware_initialization_default_config(self):
        """Test middleware initializes with default config."""
        app = FastAPI()
        with patch.dict(os.environ, {}, clear=False):
            app.add_middleware(SecurityHeadersMiddleware)
        # Should not raise an exception
        assert True

    def test_middleware_initialization_custom_config(self):
        """Test middleware initializes with custom config."""
        app = FastAPI()
        config = SecurityHeadersConfig.for_development()
        app.add_middleware(SecurityHeadersMiddleware, config=config)
        # Should not raise an exception
        assert True

    def test_middleware_adds_all_security_headers(self):
        """Test middleware adds all required security headers."""
        # Use production config so HSTS is enabled (dev config disables HSTS).
        app = self.create_test_app(config=SecurityHeadersConfig.for_production())
        client = TestClient(app)

        response = client.get("/")
        assert response.status_code == 200

        # Check all 6 security headers are present
        assert "Content-Security-Policy" in response.headers
        assert "X-Content-Type-Options" in response.headers
        assert "X-Frame-Options" in response.headers
        assert "Strict-Transport-Security" in response.headers
        assert "X-XSS-Protection" in response.headers
        assert "Referrer-Policy" in response.headers

    def test_middleware_content_security_policy_header(self):
        """Test Content-Security-Policy header."""
        app = self.create_test_app()
        client = TestClient(app)

        response = client.get("/")
        csp = response.headers.get("Content-Security-Policy")

        assert csp is not None
        assert "default-src 'self'" in csp
        assert "script-src 'self'" in csp

    def test_middleware_x_content_type_options_header(self):
        """Test X-Content-Type-Options header."""
        app = self.create_test_app()
        client = TestClient(app)

        response = client.get("/")
        assert response.headers.get("X-Content-Type-Options") == "nosniff"

    def test_middleware_x_frame_options_header(self):
        """Test X-Frame-Options header."""
        app = self.create_test_app()
        client = TestClient(app)

        response = client.get("/")
        assert response.headers.get("X-Frame-Options") == "DENY"

    def test_middleware_strict_transport_security_header(self):
        """Test Strict-Transport-Security header."""
        # Use production config — HSTS is disabled in development.
        app = self.create_test_app(config=SecurityHeadersConfig.for_production())
        client = TestClient(app)

        response = client.get("/")
        hsts = response.headers.get("Strict-Transport-Security")

        assert hsts is not None
        assert "max-age=31536000" in hsts
        assert "includeSubDomains" in hsts

    def test_middleware_x_xss_protection_header(self):
        """Test X-XSS-Protection header."""
        app = self.create_test_app()
        client = TestClient(app)

        response = client.get("/")
        assert response.headers.get("X-XSS-Protection") == "1; mode=block"

    def test_middleware_referrer_policy_header(self):
        """Test Referrer-Policy header."""
        app = self.create_test_app()
        client = TestClient(app)

        response = client.get("/")
        assert response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"

    def test_middleware_applies_to_all_endpoints(self):
        """Test middleware applies headers to all endpoints."""
        app = self.create_test_app()
        client = TestClient(app)

        # Test GET endpoints
        response1 = client.get("/")
        response2 = client.get("/api/data")

        for response in [response1, response2]:
            assert "Content-Security-Policy" in response.headers
            assert "X-Content-Type-Options" in response.headers
            assert "X-Frame-Options" in response.headers

    def test_middleware_applies_to_post_requests(self):
        """Test middleware applies headers to POST requests."""
        app = self.create_test_app()
        client = TestClient(app)

        response = client.post("/api/create", json={"name": "test"})
        assert response.status_code == 200

        # Check security headers are present
        assert "Content-Security-Policy" in response.headers
        assert "X-Content-Type-Options" in response.headers
        assert "X-Frame-Options" in response.headers


# ============================================================================
# SecurityHeadersMiddleware Tests - Custom Configurations
# ============================================================================


class TestSecurityHeadersMiddlewareCustomConfig:
    """Test SecurityHeadersMiddleware with custom configurations."""

    def test_middleware_development_config(self):
        """Test middleware with development configuration."""
        app = FastAPI()
        config = SecurityHeadersConfig.for_development()
        app.add_middleware(SecurityHeadersMiddleware, config=config)

        @app.get("/")
        async def root():
            return {"message": "Dev"}

        client = TestClient(app)
        response = client.get("/")

        # HSTS should be disabled in development
        assert "Strict-Transport-Security" not in response.headers

        # CSP should allow unsafe-inline and unsafe-eval
        csp = response.headers.get("Content-Security-Policy")
        assert "'unsafe-inline'" in csp
        assert "'unsafe-eval'" in csp

    def test_middleware_production_config(self):
        """Test middleware with production configuration."""
        app = FastAPI()
        config = SecurityHeadersConfig.for_production()
        app.add_middleware(SecurityHeadersMiddleware, config=config)

        @app.get("/")
        async def root():
            return {"message": "Prod"}

        client = TestClient(app)
        response = client.get("/")

        # HSTS should be enabled with preload
        hsts = response.headers.get("Strict-Transport-Security")
        assert "max-age=31536000" in hsts
        assert "includeSubDomains" in hsts
        assert "preload" in hsts

        # CSP should be strict
        csp = response.headers.get("Content-Security-Policy")
        assert "script-src 'self'" in csp
        assert "'unsafe-inline'" not in csp
        assert "'unsafe-eval'" not in csp

    def test_middleware_websocket_config(self):
        """Test middleware with WebSocket configuration."""
        app = FastAPI()
        config = SecurityHeadersConfig.for_websocket_service()
        app.add_middleware(SecurityHeadersMiddleware, config=config)

        @app.get("/")
        async def root():
            return {"message": "WebSocket Service"}

        client = TestClient(app)
        response = client.get("/")

        # CSP should allow WebSocket connections
        csp = response.headers.get("Content-Security-Policy")
        assert "connect-src 'self' ws: wss:" in csp

    def test_middleware_integration_service_config(self):
        """Test middleware with integration service configuration."""
        app = FastAPI()
        config = SecurityHeadersConfig.for_integration_service()
        app.add_middleware(SecurityHeadersMiddleware, config=config)

        @app.get("/")
        async def root():
            return {"message": "Integration Service"}

        client = TestClient(app)
        response = client.get("/")

        # CSP should allow HTTPS external connections
        csp = response.headers.get("Content-Security-Policy")
        assert "connect-src 'self' https:" in csp

    def test_middleware_custom_frame_options(self):
        """Test middleware with custom frame options."""
        app = FastAPI()
        config = SecurityHeadersConfig(frame_options="SAMEORIGIN")
        app.add_middleware(SecurityHeadersMiddleware, config=config)

        @app.get("/")
        async def root():
            return {"message": "Custom Frame Options"}

        client = TestClient(app)
        response = client.get("/")
        assert response.headers.get("X-Frame-Options") == "SAMEORIGIN"

    def test_middleware_custom_referrer_policy(self):
        """Test middleware with custom referrer policy."""
        app = FastAPI()
        config = SecurityHeadersConfig(referrer_policy="no-referrer")
        app.add_middleware(SecurityHeadersMiddleware, config=config)

        @app.get("/")
        async def root():
            return {"message": "Custom Referrer Policy"}

        client = TestClient(app)
        response = client.get("/")
        assert response.headers.get("Referrer-Policy") == "no-referrer"

    def test_middleware_xss_protection_disabled(self):
        """Test middleware with XSS protection disabled."""
        app = FastAPI()
        config = SecurityHeadersConfig(enable_xss_protection=False)
        app.add_middleware(SecurityHeadersMiddleware, config=config)

        @app.get("/")
        async def root():
            return {"message": "No XSS Protection"}

        client = TestClient(app)
        response = client.get("/")
        assert "X-XSS-Protection" not in response.headers

    def test_middleware_hsts_disabled(self):
        """Test middleware with HSTS disabled."""
        app = FastAPI()
        config = SecurityHeadersConfig(enable_hsts=False)
        app.add_middleware(SecurityHeadersMiddleware, config=config)

        @app.get("/")
        async def root():
            return {"message": "No HSTS"}

        client = TestClient(app)
        response = client.get("/")
        assert "Strict-Transport-Security" not in response.headers


# ============================================================================
# add_security_headers Function Tests
# ============================================================================


class TestAddSecurityHeadersFunction:
    """Test add_security_headers convenience function."""

    def test_add_security_headers_default(self):
        """Test add_security_headers with defaults."""
        app = FastAPI()

        with patch.dict(os.environ, {"APP_ENV": "production"}, clear=False):
            add_security_headers(app)

        @app.get("/")
        async def root():
            return {"message": "Test"}

        client = TestClient(app)
        response = client.get("/")

        assert "Content-Security-Policy" in response.headers
        assert "X-Content-Type-Options" in response.headers

    def test_add_security_headers_development_environment(self):
        """Test add_security_headers with development environment."""
        app = FastAPI()
        add_security_headers(app, environment="development")

        @app.get("/")
        async def root():
            return {"message": "Dev"}

        client = TestClient(app)
        response = client.get("/")

        # HSTS should be disabled in development
        assert "Strict-Transport-Security" not in response.headers

        # CSP should allow unsafe directives
        csp = response.headers.get("Content-Security-Policy")
        assert "'unsafe-inline'" in csp

    def test_add_security_headers_production_environment(self):
        """Test add_security_headers with production environment."""
        app = FastAPI()
        add_security_headers(app, environment="production")

        @app.get("/")
        async def root():
            return {"message": "Prod"}

        client = TestClient(app)
        response = client.get("/")

        # HSTS should be enabled
        hsts = response.headers.get("Strict-Transport-Security")
        assert hsts is not None
        assert "preload" in hsts

    def test_add_security_headers_custom_config(self):
        """Test add_security_headers with custom config."""
        app = FastAPI()
        config = SecurityHeadersConfig(
            frame_options="SAMEORIGIN",
            referrer_policy="no-referrer",
        )
        add_security_headers(app, config=config)

        @app.get("/")
        async def root():
            return {"message": "Custom"}

        client = TestClient(app)
        response = client.get("/")

        assert response.headers.get("X-Frame-Options") == "SAMEORIGIN"
        assert response.headers.get("Referrer-Policy") == "no-referrer"

    def test_add_security_headers_config_overrides_environment(self):
        """Test custom config parameter overrides environment parameter."""
        app = FastAPI()
        config = SecurityHeadersConfig(frame_options="SAMEORIGIN")
        add_security_headers(app, environment="development", config=config)

        @app.get("/")
        async def root():
            return {"message": "Override"}

        client = TestClient(app)
        response = client.get("/")

        # Custom config should be used
        assert response.headers.get("X-Frame-Options") == "SAMEORIGIN"


# ============================================================================
# Integration Tests
# ============================================================================


class TestSecurityHeadersIntegration:
    """Integration tests for security headers middleware."""

    def test_all_headers_present_in_real_app(self):
        """Test all six security headers are present in a real app."""
        app = FastAPI()
        add_security_headers(app, environment="production")

        @app.get("/health")
        async def health():
            return {"status": "healthy"}

        @app.get("/api/users")
        async def users():
            return {"users": []}

        @app.post("/api/users")
        async def create_user(user: dict):
            return {"created": True}

        client = TestClient(app)

        # Test multiple endpoints
        endpoints = [
            ("GET", "/health"),
            ("GET", "/api/users"),
            ("POST", "/api/users", {"name": "test"}),
        ]

        for method, path, *args in endpoints:
            if method == "GET":
                response = client.get(path)
            elif method == "POST":
                response = client.post(path, json=args[0])

            # Verify all 6 headers
            assert "Content-Security-Policy" in response.headers
            assert "X-Content-Type-Options" in response.headers
            assert "X-Frame-Options" in response.headers
            assert "Strict-Transport-Security" in response.headers
            assert "X-XSS-Protection" in response.headers
            assert "Referrer-Policy" in response.headers

    def test_headers_work_with_cors_middleware(self):
        """Test security headers work alongside CORS middleware."""
        from starlette.middleware.cors import CORSMiddleware

        app = FastAPI()

        # Add CORS first (as documented in implementation notes)
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Add security headers after CORS
        add_security_headers(app, environment="production")

        @app.get("/api/data")
        async def data():
            return {"data": "test"}

        client = TestClient(app)
        # CORS headers are only sent when the request includes an Origin header.
        response = client.get("/api/data", headers={"Origin": "http://example.com"})

        # Both CORS and security headers should be present
        assert "access-control-allow-origin" in response.headers
        assert "Content-Security-Policy" in response.headers
        assert "X-Content-Type-Options" in response.headers

    def test_environment_specific_behavior(self):
        """Test different behaviors across environments."""
        environments = {
            "development": SecurityHeadersConfig.for_development(),
            "production": SecurityHeadersConfig.for_production(),
        }

        for env_name, config in environments.items():
            app = FastAPI()
            app.add_middleware(SecurityHeadersMiddleware, config=config)

            @app.get("/")
            async def root(env_val=env_name):
                return {"env": env_val}

            client = TestClient(app)
            response = client.get("/")

            if env_name == "development":
                # Development should not have HSTS
                assert "Strict-Transport-Security" not in response.headers
                # Development should have relaxed CSP
                csp = response.headers.get("Content-Security-Policy")
                assert "'unsafe-inline'" in csp
            elif env_name == "production":
                # Production should have strict HSTS
                hsts = response.headers.get("Strict-Transport-Security")
                assert "max-age=31536000" in hsts
                assert "preload" in hsts
                # Production should have strict CSP
                csp = response.headers.get("Content-Security-Policy")
                assert "'unsafe-inline'" not in csp or "style-src" not in csp


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================


class TestSecurityHeadersEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_custom_csp_directives(self):
        """Test config with empty custom CSP directives."""
        config = SecurityHeadersConfig(custom_csp_directives={})
        csp = config.get_csp_header_value()

        # Should still have default directives
        assert "default-src 'self'" in csp
        assert "script-src 'self'" in csp

    def test_very_long_csp_directive_list(self):
        """Test CSP with many sources in a directive."""
        sources = ["'self'"] + [f"https://cdn{i}.example.com" for i in range(50)]
        config = SecurityHeadersConfig(custom_csp_directives={"script-src": sources})
        csp = config.get_csp_header_value()

        # Should contain all sources
        assert "'self'" in csp
        assert "https://cdn0.example.com" in csp
        assert "https://cdn49.example.com" in csp

    def test_hsts_max_age_zero(self):
        """Test HSTS with max-age of zero."""
        config = SecurityHeadersConfig(hsts_max_age=0)
        hsts = config.get_hsts_header_value()
        assert "max-age=0" in hsts

    def test_hsts_all_options_disabled(self):
        """Test HSTS with only max-age."""
        config = SecurityHeadersConfig(
            hsts_include_subdomains=False,
            hsts_preload=False,
        )
        hsts = config.get_hsts_header_value()

        assert "max-age=31536000" in hsts
        assert "includeSubDomains" not in hsts
        assert "preload" not in hsts

    def test_middleware_preserves_existing_headers(self):
        """Test middleware preserves existing response headers."""
        app = FastAPI()
        add_security_headers(app, environment="production")

        @app.get("/")
        async def root():
            from fastapi.responses import JSONResponse

            return JSONResponse(
                content={"message": "test"},
                headers={"X-Custom-Header": "custom-value"},
            )

        client = TestClient(app)
        response = client.get("/")

        # Custom header should be preserved
        assert response.headers.get("X-Custom-Header") == "custom-value"
        # Security headers should also be present
        assert "Content-Security-Policy" in response.headers


# ============================================================================
# Constitutional Compliance Tests
# ============================================================================


class TestConstitutionalCompliance:
    """Test constitutional hash compliance."""

    def test_constitutional_hash_present(self):
        """Constitutional hash should be defined."""
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    def test_constitutional_hash_in_module_docstring(self):
        """Constitutional hash should be in module docstring."""
        from src.core.shared.security import security_headers

        assert CONSTITUTIONAL_HASH in security_headers.__doc__


# ============================================================================
# Logging Tests
# ============================================================================


class TestSecurityHeadersLogging:
    """Test logging functionality."""

    def test_middleware_logs_initialization(self):
        """Test middleware logs initialization."""
        with patch("src.core.shared.security.security_headers.logger") as mock_logger:
            app = FastAPI()
            config = SecurityHeadersConfig.for_production()
            app.add_middleware(SecurityHeadersMiddleware, config=config)

            @app.get("/")
            async def root():
                return {"ok": True}

            # Starlette defers middleware construction until first request.
            client = TestClient(app)
            client.get("/")

            mock_logger.info.assert_called()
            # Find the initialization log among all info calls.
            # logger.info uses %s formatting, so args are separate from the
            # format string.  Search the string representation of each call.
            init_calls = [c for c in mock_logger.info.call_args_list if "initialized" in str(c)]
            assert len(init_calls) >= 1
            call_repr = str(init_calls[0])
            assert "Security headers middleware initialized" in call_repr
            assert "production" in call_repr

    def test_add_security_headers_logs(self):
        """Test add_security_headers logs addition."""
        with patch("src.core.shared.security.security_headers.logger") as mock_logger:
            app = FastAPI()
            add_security_headers(app, environment="production")

            mock_logger.info.assert_called()
            call_args = mock_logger.info.call_args[0][0]
            assert "Added security headers middleware" in call_args


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
