"""
Tests for Session Extraction Middleware
Constitutional Hash: 608508a9bd224290

Comprehensive tests for session context extraction and management middleware.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request

# Constitutional compliance
from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH


class TestExtractSessionId:
    """Tests for extract_session_id_from_request function."""

    def test_extract_from_header(self):
        """Test extracting session ID from X-Session-ID header."""
        from middlewares.session_extraction import extract_session_id_from_request

        request = MagicMock(spec=Request)
        request.headers = {"X-Session-ID": "session-123"}
        request.path_params = {}
        request.query_params = {}
        request.cookies = {}

        result = extract_session_id_from_request(request)
        assert result == "session-123"

    def test_extract_from_path_param(self):
        """Test extracting session ID from path parameter."""
        from middlewares.session_extraction import extract_session_id_from_request

        request = MagicMock(spec=Request)
        request.headers = {}
        request.path_params = {"session_id": "session-456"}
        request.query_params = {}
        request.cookies = {}

        result = extract_session_id_from_request(request)
        assert result == "session-456"

    def test_extract_from_query_param(self):
        """Test extracting session ID from query parameter."""
        from middlewares.session_extraction import extract_session_id_from_request

        request = MagicMock(spec=Request)
        request.headers = {}
        request.path_params = {}
        request.query_params = {"session_id": "session-789"}
        request.cookies = {}

        result = extract_session_id_from_request(request)
        assert result == "session-789"

    def test_extract_from_cookie(self):
        """Test extracting session ID from cookie."""
        from middlewares.session_extraction import extract_session_id_from_request

        request = MagicMock(spec=Request)
        request.headers = {}
        request.path_params = {}
        request.query_params = {}
        request.cookies = {"acgs_session_id": "session-abc"}

        result = extract_session_id_from_request(request)
        assert result == "session-abc"

    def test_header_takes_priority(self):
        """Test that header takes priority over other sources."""
        from middlewares.session_extraction import extract_session_id_from_request

        request = MagicMock(spec=Request)
        request.headers = {"X-Session-ID": "from-header"}
        request.path_params = {"session_id": "from-path"}
        request.query_params = {"session_id": "from-query"}
        request.cookies = {"acgs_session_id": "from-cookie"}

        result = extract_session_id_from_request(request)
        assert result == "from-header"

    def test_no_session_id_returns_none(self):
        """Test that None is returned when no session ID found."""
        from middlewares.session_extraction import extract_session_id_from_request

        request = MagicMock(spec=Request)
        request.headers = {}
        request.path_params = {}
        request.query_params = {}
        request.cookies = {}

        result = extract_session_id_from_request(request)
        assert result is None


class TestExtractTenantId:
    """Tests for extract_tenant_id_from_request function."""

    def test_extract_from_header(self):
        """Test extracting tenant ID from X-Tenant-ID header."""
        from middlewares.session_extraction import extract_tenant_id_from_request

        request = MagicMock(spec=Request)
        request.headers = {"X-Tenant-ID": "tenant-123"}
        request.path_params = {}
        request.query_params = {}

        # Mock state without tenant_context
        request.state = MagicMock()
        delattr(request.state, "tenant_context")

        result = extract_tenant_id_from_request(request)
        assert result == "tenant-123"

    def test_extract_from_tenant_context(self):
        """Test extracting tenant ID from tenant context in state."""
        from middlewares.session_extraction import extract_tenant_id_from_request

        request = MagicMock(spec=Request)
        request.headers = {}
        request.path_params = {}
        request.query_params = {}

        # Mock tenant context
        tenant_context = MagicMock()
        tenant_context.tenant_id = "tenant-456"
        request.state = MagicMock()
        request.state.tenant_context = tenant_context

        result = extract_tenant_id_from_request(request)
        assert result == "tenant-456"


class TestSessionContext:
    """Tests for SessionContext class."""

    def test_create_context(self):
        """Test creating session context."""
        from middlewares.session_extraction import SessionContext

        ctx = SessionContext(
            session_id="session-123",
            tenant_id="tenant-456",
            governance_config={
                "risk_level": "high",
                "automation_level": "partial",
                "enabled_policies": ["policy-1", "policy-2"],
                "policy_id": "active-policy",
            },
            session_data={
                "agent_type": "executive",
                "operation_type": "proposal",
            },
        )

        assert ctx.session_id == "session-123"
        assert ctx.tenant_id == "tenant-456"
        assert ctx.risk_level == "high"
        assert ctx.automation_level == "partial"
        assert ctx.enabled_policies == ["policy-1", "policy-2"]
        assert ctx.policy_id == "active-policy"
        assert ctx.agent_type == "executive"
        assert ctx.operation_type == "proposal"
        assert ctx.constitutional_hash == CONSTITUTIONAL_HASH

    def test_default_values(self):
        """Test default values for session context."""
        from middlewares.session_extraction import SessionContext

        ctx = SessionContext(
            session_id="session-123",
            tenant_id="tenant-456",
        )

        assert ctx.risk_level == "low"
        assert ctx.automation_level == "full"
        assert ctx.enabled_policies == []
        assert ctx.policy_id is None
        assert ctx.agent_type is None
        assert ctx.operation_type is None

    def test_validate_valid_context(self):
        """Test validation of valid context."""
        from middlewares.session_extraction import SessionContext

        ctx = SessionContext(
            session_id="session-123",
            tenant_id="tenant-456",
        )

        assert ctx.validate() is True

    def test_validate_missing_session_id(self):
        """Test validation fails without session ID."""
        from middlewares.session_extraction import SessionContext

        ctx = SessionContext(
            session_id="",
            tenant_id="tenant-456",
        )

        assert ctx.validate() is False

    def test_validate_missing_tenant_id(self):
        """Test validation fails without tenant ID."""
        from middlewares.session_extraction import SessionContext

        ctx = SessionContext(
            session_id="session-123",
            tenant_id="",
        )

        assert ctx.validate() is False

    def test_validate_wrong_constitutional_hash(self):
        """Test validation fails with wrong constitutional hash."""
        from middlewares.session_extraction import SessionContext

        ctx = SessionContext(
            session_id="session-123",
            tenant_id="tenant-456",
            constitutional_hash="wrong-hash",
        )

        assert ctx.validate() is False

    def test_to_dict(self):
        """Test converting context to dictionary."""
        from middlewares.session_extraction import SessionContext

        ctx = SessionContext(
            session_id="session-123",
            tenant_id="tenant-456",
            governance_config={
                "risk_level": "medium",
                "automation_level": "partial",
                "enabled_policies": ["policy-1"],
                "policy_id": "active-policy",
            },
            session_data={
                "agent_type": "judicial",
                "operation_type": "validation",
            },
        )

        result = ctx.to_dict()

        assert result["session_id"] == "session-123"
        assert result["tenant_id"] == "tenant-456"
        assert result["risk_level"] == "medium"
        assert result["automation_level"] == "partial"
        assert result["enabled_policies"] == ["policy-1"]
        assert result["policy_id"] == "active-policy"
        assert result["agent_type"] == "judicial"
        assert result["operation_type"] == "validation"
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH


class TestSessionExtractionMiddleware:
    """Tests for SessionExtractionMiddleware class."""

    @pytest.fixture
    def app_with_middleware(self):
        """Create FastAPI app with session extraction middleware."""
        from middlewares.session_extraction import (
            SessionContext,
            SessionExtractionMiddleware,
        )

        app = FastAPI()

        # Mock session manager
        session_manager = AsyncMock()
        session_manager.get_session = AsyncMock(
            return_value={
                "session_id": "session-123",
                "tenant_id": "test-tenant",
                "governance_config": {
                    "risk_level": "medium",
                    "automation_level": "partial",
                },
                "agent_type": "executive",
            }
        )

        app.add_middleware(
            SessionExtractionMiddleware,
            session_manager=session_manager,
            require_session=True,
        )

        @app.get("/protected")
        async def protected_endpoint(request: Request):
            ctx = getattr(request.state, "session_context", None)
            if ctx:
                return {
                    "session_id": ctx.session_id,
                    "tenant_id": ctx.tenant_id,
                    "risk_level": ctx.risk_level,
                }
            return {"error": "No session context"}

        @app.get("/health")
        async def health_endpoint():
            return {"status": "healthy"}

        return app, session_manager

    def test_public_path_bypasses_middleware(self, app_with_middleware):
        """Test that public paths bypass session requirement."""
        app, _ = app_with_middleware
        client = TestClient(app)

        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_missing_session_id_returns_400(self, app_with_middleware):
        """Test that missing session ID returns 400 when required."""
        app, _ = app_with_middleware
        client = TestClient(app)

        response = client.get(
            "/protected",
            headers={"X-Tenant-ID": "test-tenant"},
        )
        assert response.status_code == 400
        assert response.json()["error"] == "session_required"
        assert response.json()["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_missing_tenant_id_returns_400(self, app_with_middleware):
        """Test that missing tenant ID returns 400."""
        app, _ = app_with_middleware
        client = TestClient(app)

        response = client.get(
            "/protected",
            headers={"X-Session-ID": "session-123"},
        )
        assert response.status_code == 400
        assert response.json()["error"] == "tenant_required"

    def test_session_not_found_returns_404(self, app_with_middleware):
        """Test that session not found returns 404 when required."""
        app, session_manager = app_with_middleware
        session_manager.get_session.return_value = None
        client = TestClient(app)

        response = client.get(
            "/protected",
            headers={
                "X-Session-ID": "nonexistent-session",
                "X-Tenant-ID": "test-tenant",
            },
        )
        assert response.status_code == 404
        assert response.json()["error"] == "session_not_found"

    def test_tenant_mismatch_returns_403(self, app_with_middleware):
        """Test that tenant mismatch returns 403."""
        app, session_manager = app_with_middleware
        session_manager.get_session.return_value = {
            "session_id": "session-123",
            "tenant_id": "different-tenant",
            "governance_config": {},
        }
        client = TestClient(app)

        response = client.get(
            "/protected",
            headers={
                "X-Session-ID": "session-123",
                "X-Tenant-ID": "test-tenant",
            },
        )
        assert response.status_code == 403
        assert response.json()["error"] == "tenant_mismatch"

    def test_invalid_constitutional_hash_returns_403(self, app_with_middleware):
        """Test that invalid constitutional hash returns 403."""
        app, _ = app_with_middleware
        client = TestClient(app)

        response = client.get(
            "/protected",
            headers={
                "X-Session-ID": "session-123",
                "X-Tenant-ID": "test-tenant",
                "X-Constitutional-Hash": "wrong-hash",
            },
        )
        assert response.status_code == 403
        assert response.json()["error"] == "constitutional_hash_mismatch"

    def test_successful_session_extraction(self, app_with_middleware):
        """Test successful session extraction."""
        app, _ = app_with_middleware
        client = TestClient(app)

        response = client.get(
            "/protected",
            headers={
                "X-Session-ID": "session-123",
                "X-Tenant-ID": "test-tenant",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "session-123"
        assert data["tenant_id"] == "test-tenant"
        assert data["risk_level"] == "medium"

        # Check response headers
        assert response.headers["X-Session-ID"] == "session-123"
        assert response.headers["X-Constitutional-Hash"] == CONSTITUTIONAL_HASH


class TestSessionExtractionMiddlewareOptional:
    """Tests for SessionExtractionMiddleware with optional session."""

    @pytest.fixture
    def app_optional_session(self):
        """Create FastAPI app with optional session middleware."""
        from middlewares.session_extraction import SessionExtractionMiddleware

        app = FastAPI()

        session_manager = AsyncMock()
        session_manager.get_session = AsyncMock(return_value=None)

        app.add_middleware(
            SessionExtractionMiddleware,
            session_manager=session_manager,
            require_session=False,  # Session is optional
        )

        @app.get("/endpoint")
        async def endpoint(request: Request):
            ctx = getattr(request.state, "session_context", None)
            if ctx:
                return {"has_session": True, "session_id": ctx.session_id}
            return {"has_session": False}

        return app

    def test_optional_session_without_headers(self, app_optional_session):
        """Test endpoint works without session when optional."""
        client = TestClient(app_optional_session)

        response = client.get("/endpoint")
        assert response.status_code == 200
        assert response.json()["has_session"] is False

    def test_optional_session_not_found(self, app_optional_session):
        """Test endpoint works when session not found and optional."""
        client = TestClient(app_optional_session)

        response = client.get(
            "/endpoint",
            headers={
                "X-Session-ID": "nonexistent",
                "X-Tenant-ID": "test-tenant",
            },
        )
        assert response.status_code == 200
        assert response.json()["has_session"] is False


class TestSessionContextDependency:
    """Tests for SessionContextDependency class."""

    @pytest.fixture
    def app_with_dependency(self):
        """Create FastAPI app with session context dependency."""
        from middlewares.session_extraction import (
            SessionContext,
            SessionContextDependency,
        )

        app = FastAPI()
        get_session = SessionContextDependency(required=True)
        get_optional_session = SessionContextDependency(required=False)

        @app.get("/required")
        async def required_endpoint(ctx: SessionContext = Depends(get_session)):
            return {"session_id": ctx.session_id}

        @app.get("/optional")
        async def optional_endpoint(ctx=Depends(get_optional_session)):
            if ctx:
                return {"has_session": True}
            return {"has_session": False}

        return app

    def test_required_dependency_missing_session(self, app_with_dependency):
        """Test required dependency fails without session."""
        client = TestClient(app_with_dependency, raise_server_exceptions=False)

        response = client.get("/required")
        assert response.status_code == 400

    def test_optional_dependency_missing_session(self, app_with_dependency):
        """Test optional dependency returns None without session."""
        client = TestClient(app_with_dependency)

        response = client.get("/optional")
        assert response.status_code == 200
        assert response.json()["has_session"] is False


class TestSessionGovernanceDependency:
    """Tests for SessionGovernanceDependency class."""

    @pytest.fixture
    def app_with_governance(self):
        """Create FastAPI app with governance dependency."""
        from middlewares.session_extraction import (
            SessionExtractionMiddleware,
            SessionGovernanceDependency,
        )

        app = FastAPI()

        session_manager = AsyncMock()
        session_manager.get_session = AsyncMock(
            return_value={
                "session_id": "session-123",
                "tenant_id": "test-tenant",
                "governance_config": {
                    "risk_level": "high",
                    "automation_level": "none",
                    "enabled_policies": ["policy-1"],
                    "policy_id": "active-policy",
                    "policy_overrides": {"max_actions": 10},
                },
            }
        )

        app.add_middleware(
            SessionExtractionMiddleware,
            session_manager=session_manager,
            require_session=False,
        )

        get_governance = SessionGovernanceDependency()

        @app.get("/governance")
        async def governance_endpoint(governance: dict = Depends(get_governance)):
            return governance

        return app

    def test_get_governance_from_session(self, app_with_governance):
        """Test getting governance config from session."""
        client = TestClient(app_with_governance)

        response = client.get(
            "/governance",
            headers={
                "X-Session-ID": "session-123",
                "X-Tenant-ID": "test-tenant",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["risk_level"] == "high"
        assert data["automation_level"] == "none"
        assert data["enabled_policies"] == ["policy-1"]
        assert data["policy_id"] == "active-policy"
        assert data["policy_overrides"] == {"max_actions": 10}
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_get_default_governance_without_session(self, app_with_governance):
        """Test getting default governance config without session."""
        client = TestClient(app_with_governance)

        response = client.get("/governance")
        assert response.status_code == 200
        data = response.json()
        assert data["risk_level"] == "low"
        assert data["automation_level"] == "full"
        assert data["enabled_policies"] == []
        assert data["policy_id"] is None
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH


class TestConstitutionalCompliance:
    """Tests for constitutional compliance in middleware."""

    def test_middleware_includes_constitutional_hash(self):
        """Test that middleware includes constitutional hash in responses."""
        from middlewares.session_extraction import SessionExtractionMiddleware

        app = FastAPI()
        session_manager = AsyncMock()
        session_manager.get_session = AsyncMock(
            return_value={
                "session_id": "session-123",
                "tenant_id": "test-tenant",
                "governance_config": {},
            }
        )

        app.add_middleware(
            SessionExtractionMiddleware,
            session_manager=session_manager,
        )

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get(
            "/test",
            headers={
                "X-Session-ID": "session-123",
                "X-Tenant-ID": "test-tenant",
            },
        )

        assert response.headers["X-Constitutional-Hash"] == CONSTITUTIONAL_HASH

    def test_context_validates_constitutional_hash(self):
        """Test that context validates constitutional hash."""
        from middlewares.session_extraction import SessionContext

        # Valid hash
        ctx1 = SessionContext(
            session_id="s1",
            tenant_id="t1",
            constitutional_hash=CONSTITUTIONAL_HASH,
        )
        assert ctx1.validate() is True

        # Invalid hash
        ctx2 = SessionContext(
            session_id="s2",
            tenant_id="t2",
            constitutional_hash="invalid",
        )
        assert ctx2.validate() is False

    def test_error_responses_include_constitutional_hash(self):
        """Test that error responses include constitutional hash."""
        from middlewares.session_extraction import SessionExtractionMiddleware

        app = FastAPI()
        app.add_middleware(
            SessionExtractionMiddleware,
            require_session=True,
        )

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        client = TestClient(app)

        # Test missing session error
        response = client.get(
            "/test",
            headers={"X-Tenant-ID": "test-tenant"},
        )
        assert response.json()["constitutional_hash"] == CONSTITUTIONAL_HASH

        # Test missing tenant error
        response = client.get(
            "/test",
            headers={"X-Session-ID": "session-123"},
        )
        assert response.json()["constitutional_hash"] == CONSTITUTIONAL_HASH


class TestModuleExports:
    """Tests for module exports."""

    def test_all_exports_available(self):
        """Test that all expected exports are available."""
        from middlewares.session_extraction import (
            CONSTITUTIONAL_HASH,
            SESSION_ID_HEADER,
            TENANT_ID_HEADER,
            SessionContext,
            SessionContextDependency,
            SessionExtractionMiddleware,
            SessionGovernanceDependency,
            extract_session_id_from_request,
            extract_tenant_id_from_request,
            get_optional_session_context,
            get_session_context,
            get_session_governance,
        )

        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH
        assert SESSION_ID_HEADER == "X-Session-ID"
        assert TENANT_ID_HEADER == "X-Tenant-ID"
        assert callable(extract_session_id_from_request)
        assert callable(extract_tenant_id_from_request)
        assert SessionContext is not None
        assert SessionExtractionMiddleware is not None
        assert SessionContextDependency is not None
        assert SessionGovernanceDependency is not None
        assert get_session_context is not None
        assert get_optional_session_context is not None
        assert get_session_governance is not None

    def test_package_exports(self):
        """Test that package __init__ exports correctly."""
        from middleware import (
            CONSTITUTIONAL_HASH,
            SessionContext,
            SessionContextDependency,
            SessionExtractionMiddleware,
            SessionGovernanceDependency,
        )

        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH
        assert SessionContext is not None
        assert SessionExtractionMiddleware is not None
        assert SessionContextDependency is not None
        assert SessionGovernanceDependency is not None
