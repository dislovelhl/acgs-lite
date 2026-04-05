"""
ACGS-2 Enhanced Agent Bus - Session Governance API Tests
Constitutional Hash: 608508a9bd224290

Comprehensive tests for session governance API endpoints including:
- Session creation with governance configuration
- Session retrieval and tenant isolation
- Governance configuration updates
- Session deletion and TTL management
- Authentication and authorization
- Rate limiting behavior
"""

import asyncio
import uuid
from datetime import UTC, datetime, timezone
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import AsyncClient

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus._compat.types import JSONDict

# =============================================================================
# Mock Classes for Testing
# =============================================================================


class MockSessionGovernanceConfig:
    """Mock governance config for testing."""

    def __init__(
        self,
        session_id: str = "test-session",
        tenant_id: str = "test-tenant",
        user_id: str | None = None,
        risk_level: str = "medium",
        policy_id: str | None = None,
        policy_overrides: JSONDict | None = None,
        enabled_policies: list | None = None,
        disabled_policies: list | None = None,
        require_human_approval: bool = False,
        max_automation_level: str | None = None,
    ):
        self.session_id = session_id
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.risk_level = MagicMock(value=risk_level)
        self.policy_id = policy_id
        self.policy_overrides = policy_overrides or {}
        self.enabled_policies = enabled_policies or []
        self.disabled_policies = disabled_policies or []
        self.require_human_approval = require_human_approval
        self.max_automation_level = max_automation_level


class MockSessionContext:
    """Mock session context for testing."""

    def __init__(
        self,
        session_id: str = "test-session",
        governance_config: MockSessionGovernanceConfig | None = None,
        metadata: JSONDict | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        expires_at: datetime | None = None,
    ):
        self.session_id = session_id
        self.governance_config = governance_config or MockSessionGovernanceConfig(
            session_id=session_id
        )
        self.metadata = metadata or {}
        self.created_at = created_at or datetime.now(UTC)
        self.updated_at = updated_at or datetime.now(UTC)
        self.expires_at = expires_at
        self.constitutional_hash = CONSTITUTIONAL_HASH


class MockSessionContextStore:
    """Mock store for testing."""

    def __init__(self):
        self._sessions: dict[str, MockSessionContext] = {}
        self._ttls: dict[str, int] = {}

    async def get_ttl(self, session_id: str, tenant_id: str | None = None) -> int | None:
        key = (tenant_id or "", session_id)
        return self._ttls.get(key)


class MockSessionContextManager:
    """Mock session context manager for testing."""

    def __init__(self):
        self._sessions: dict[str, MockSessionContext] = {}
        self._ttls: dict[str, int] = {}
        self.store = MockSessionContextStore()
        self._metrics = {
            "cache_hits": 0,
            "cache_misses": 0,
            "creates": 0,
            "reads": 0,
            "updates": 0,
            "deletes": 0,
            "errors": 0,
            "cache_hit_rate": 0.0,
            "cache_size": 0,
            "cache_capacity": 1000,
        }

    async def connect(self) -> bool:
        return True

    async def disconnect(self) -> None:
        pass

    async def create(
        self,
        governance_config: Any,
        session_id: str | None = None,
        tenant_id: str | None = None,
        metadata: JSONDict | None = None,
        ttl: int | None = None,
    ) -> MockSessionContext:
        sid = session_id or str(uuid.uuid4())
        effective_tenant_id = tenant_id or governance_config.tenant_id
        key = (effective_tenant_id, sid)
        if key in self._sessions:
            raise ValueError(f"Session {sid} already exists")

        session = MockSessionContext(
            session_id=sid,
            governance_config=MockSessionGovernanceConfig(
                session_id=sid,
                tenant_id=effective_tenant_id,
                user_id=governance_config.user_id,
                risk_level=(
                    governance_config.risk_level.value
                    if hasattr(governance_config.risk_level, "value")
                    else str(governance_config.risk_level)
                ),
                policy_id=governance_config.policy_id,
                policy_overrides=governance_config.policy_overrides,
                enabled_policies=governance_config.enabled_policies,
                disabled_policies=governance_config.disabled_policies,
                require_human_approval=governance_config.require_human_approval,
                max_automation_level=governance_config.max_automation_level,
            ),
            metadata=metadata or {},
        )
        self._sessions[key] = session
        self._ttls[key] = ttl or 3600
        self.store._ttls[key] = ttl or 3600
        self._metrics["creates"] += 1
        return session

    async def get(self, session_id: str, tenant_id: str | None = None) -> MockSessionContext | None:
        key = (tenant_id or "", session_id)
        self._metrics["reads"] += 1
        session = self._sessions.get(key)
        if session is None:
            for (_stored_tenant, stored_id), candidate in self._sessions.items():
                if stored_id == session_id:
                    session = candidate
                    break
        if session:
            self._metrics["cache_hits"] += 1
        else:
            self._metrics["cache_misses"] += 1
        return session

    async def update(
        self,
        session_id: str,
        tenant_id: str | None = None,
        governance_config: Any | None = None,
        metadata: JSONDict | None = None,
        ttl: int | None = None,
    ) -> MockSessionContext | None:
        key = (tenant_id or "", session_id)
        session = self._sessions.get(key)
        if not session:
            return None

        if governance_config:
            session.governance_config = MockSessionGovernanceConfig(
                session_id=session_id,
                tenant_id=governance_config.tenant_id,
                user_id=governance_config.user_id,
                risk_level=(
                    governance_config.risk_level.value
                    if hasattr(governance_config.risk_level, "value")
                    else str(governance_config.risk_level)
                ),
                policy_id=governance_config.policy_id,
                policy_overrides=governance_config.policy_overrides,
                enabled_policies=governance_config.enabled_policies,
                disabled_policies=governance_config.disabled_policies,
                require_human_approval=governance_config.require_human_approval,
                max_automation_level=governance_config.max_automation_level,
            )
        if metadata:
            session.metadata.update(metadata)
        if ttl:
            self._ttls[key] = ttl
            self.store._ttls[key] = ttl

        session.updated_at = datetime.now(UTC)
        self._metrics["updates"] += 1
        return session

    async def delete(self, session_id: str, tenant_id: str | None = None) -> bool:
        key = (tenant_id or "", session_id)
        if key in self._sessions:
            del self._sessions[key]
            if key in self._ttls:
                del self._ttls[key]
            if key in self.store._ttls:
                del self.store._ttls[key]
            self._metrics["deletes"] += 1
            return True
        return False

    async def exists(self, session_id: str, tenant_id: str | None = None) -> bool:
        key = (tenant_id or "", session_id)
        return key in self._sessions

    async def extend_ttl(
        self,
        session_id: str,
        tenant_id: str | None,
        ttl: int,
    ) -> bool:
        key = (tenant_id or "", session_id)
        if key in self._sessions:
            self._ttls[key] = ttl
            self.store._ttls[key] = ttl
            return True
        return False

    def get_metrics(self) -> JSONDict:
        return self._metrics.copy()


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_manager() -> MockSessionContextManager:
    """Create a mock session context manager."""
    return MockSessionContextManager()


@pytest.fixture
def app_with_sessions(mock_manager: MockSessionContextManager) -> FastAPI:
    """Create a FastAPI app with session routes for testing."""
    import time

    from fastapi import FastAPI

    from enhanced_agent_bus._compat.security.auth import UserClaims, get_current_user

    app = FastAPI()

    # Import the router
    try:
        from enhanced_agent_bus.routes.sessions import get_session_manager, router
    except ImportError:
        from routes.sessions import get_session_manager, router

    # Override the dependency
    app.dependency_overrides[get_session_manager] = lambda: mock_manager

    # Override auth so tests don't need real JWT tokens
    now = int(time.time())

    def _override_auth() -> UserClaims:
        return UserClaims(
            sub="test-user",
            tenant_id="test-tenant",
            roles=["user"],
            permissions=[],
            exp=now + 3600,
            iat=now,
        )

    app.dependency_overrides[get_current_user] = _override_auth

    # Include the router
    app.include_router(router)

    return app


@pytest.fixture
def client(app_with_sessions: FastAPI) -> TestClient:
    """Create a test client."""
    return TestClient(app_with_sessions)


# =============================================================================
# Session Creation Tests
# =============================================================================


class TestCreateSession:
    """Tests for POST /api/v1/sessions endpoint."""

    def test_create_session_basic(
        self, client: TestClient, mock_manager: MockSessionContextManager
    ):
        """Test creating a session with minimal configuration."""
        response = client.post(
            "/api/v1/sessions",
            json={
                "risk_level": "medium",
            },
            headers={"X-Tenant-ID": "test-tenant"},
        )

        assert response.status_code == 201
        data = response.json()
        assert "session_id" in data
        assert data["tenant_id"] == "test-tenant"
        assert data["risk_level"] == "medium"
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_create_session_with_custom_id(
        self, client: TestClient, mock_manager: MockSessionContextManager
    ):
        """Test creating a session with a custom session ID."""
        custom_id = "my-custom-session-id"
        response = client.post(
            "/api/v1/sessions",
            json={
                "session_id": custom_id,
                "risk_level": "high",
                "policy_id": "strict-policy-v1",
            },
            headers={"X-Tenant-ID": "test-tenant"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["session_id"] == custom_id
        assert data["risk_level"] == "high"
        assert data["policy_id"] == "strict-policy-v1"

    def test_create_session_with_full_config(
        self, client: TestClient, mock_manager: MockSessionContextManager
    ):
        """Test creating a session with full governance configuration."""
        response = client.post(
            "/api/v1/sessions",
            json={
                "tenant_id": "acme-corp",
                "user_id": "user-12345",
                "risk_level": "critical",
                "policy_id": "security-first-v2",
                "policy_overrides": {"max_tokens": 1000},
                "enabled_policies": ["audit-logging", "rate-limiting"],
                "disabled_policies": ["experimental-features"],
                "require_human_approval": True,
                "max_automation_level": "partial",
                "metadata": {"source": "web-app", "region": "us-east-1"},
                "ttl_seconds": 7200,
            },
            headers={"X-Tenant-ID": "acme-corp"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["tenant_id"] == "acme-corp"
        assert data["user_id"] == "user-12345"
        assert data["risk_level"] == "critical"
        assert data["require_human_approval"] is True
        assert data["max_automation_level"] == "partial"
        assert "source" in data["metadata"]

    def test_create_session_invalid_risk_level(
        self, client: TestClient, mock_manager: MockSessionContextManager
    ):
        """Test creating a session with invalid risk level."""
        response = client.post(
            "/api/v1/sessions",
            json={
                "risk_level": "ultra-high",  # Invalid
            },
            headers={"X-Tenant-ID": "test-tenant"},
        )

        assert response.status_code == 422  # Validation error

    def test_create_session_duplicate_id(
        self, client: TestClient, mock_manager: MockSessionContextManager
    ):
        """Test creating a session with duplicate ID returns 409."""
        session_id = "duplicate-session"

        # Create first session
        response1 = client.post(
            "/api/v1/sessions",
            json={"session_id": session_id, "risk_level": "low"},
            headers={"X-Tenant-ID": "test-tenant"},
        )
        assert response1.status_code == 201

        # Try to create duplicate
        response2 = client.post(
            "/api/v1/sessions",
            json={"session_id": session_id, "risk_level": "low"},
            headers={"X-Tenant-ID": "test-tenant"},
        )
        assert response2.status_code == 409


# =============================================================================
# Session Retrieval Tests
# =============================================================================


class TestGetSession:
    """Tests for GET /api/v1/sessions/{session_id} endpoint."""

    def test_get_session_success(self, client: TestClient, mock_manager: MockSessionContextManager):
        """Test retrieving an existing session."""
        # Create session first
        create_response = client.post(
            "/api/v1/sessions",
            json={"risk_level": "medium"},
            headers={"X-Tenant-ID": "test-tenant"},
        )
        session_id = create_response.json()["session_id"]

        # Get session
        get_response = client.get(
            f"/api/v1/sessions/{session_id}",
            headers={"X-Tenant-ID": "test-tenant"},
        )

        assert get_response.status_code == 200
        data = get_response.json()
        assert data["session_id"] == session_id
        assert data["tenant_id"] == "test-tenant"
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_get_session_not_found(
        self, client: TestClient, mock_manager: MockSessionContextManager
    ):
        """Test retrieving a non-existent session returns 404."""
        response = client.get(
            "/api/v1/sessions/non-existent-session",
            headers={"X-Tenant-ID": "test-tenant"},
        )

        assert response.status_code == 404

    def test_get_session_wrong_tenant(
        self, client: TestClient, mock_manager: MockSessionContextManager
    ):
        """Test tenant isolation - cannot access other tenant's session."""
        # Create session for tenant-a
        create_response = client.post(
            "/api/v1/sessions",
            json={"risk_level": "medium"},
            headers={"X-Tenant-ID": "tenant-a"},
        )
        session_id = create_response.json()["session_id"]

        # Try to access from tenant-b
        get_response = client.get(
            f"/api/v1/sessions/{session_id}",
            headers={"X-Tenant-ID": "tenant-b"},
        )

        assert get_response.status_code == 403


# =============================================================================
# Session Update Tests
# =============================================================================


class TestUpdateSessionGovernance:
    """Tests for PUT /api/v1/sessions/{session_id}/governance endpoint."""

    def test_update_governance_success(
        self, client: TestClient, mock_manager: MockSessionContextManager
    ):
        """Test updating session governance configuration."""
        # Create session
        create_response = client.post(
            "/api/v1/sessions",
            json={"risk_level": "low", "require_human_approval": False},
            headers={"X-Tenant-ID": "test-tenant"},
        )
        session_id = create_response.json()["session_id"]

        # Update governance
        update_response = client.put(
            f"/api/v1/sessions/{session_id}/governance",
            json={
                "risk_level": "high",
                "require_human_approval": True,
            },
            headers={"X-Tenant-ID": "test-tenant"},
        )

        assert update_response.status_code == 200
        data = update_response.json()
        assert data["risk_level"] == "high"
        assert data["require_human_approval"] is True

    def test_update_governance_partial(
        self, client: TestClient, mock_manager: MockSessionContextManager
    ):
        """Test partial update of governance configuration."""
        # Create session with specific config
        create_response = client.post(
            "/api/v1/sessions",
            json={
                "risk_level": "medium",
                "policy_id": "original-policy",
                "require_human_approval": False,
            },
            headers={"X-Tenant-ID": "test-tenant"},
        )
        session_id = create_response.json()["session_id"]

        # Update only risk_level
        update_response = client.put(
            f"/api/v1/sessions/{session_id}/governance",
            json={"risk_level": "high"},
            headers={"X-Tenant-ID": "test-tenant"},
        )

        assert update_response.status_code == 200
        data = update_response.json()
        # Updated field
        assert data["risk_level"] == "high"
        # Unchanged fields should retain original values
        assert data["require_human_approval"] is False

    def test_update_governance_not_found(
        self, client: TestClient, mock_manager: MockSessionContextManager
    ):
        """Test updating non-existent session returns 404."""
        response = client.put(
            "/api/v1/sessions/non-existent-session/governance",
            json={"risk_level": "high"},
            headers={"X-Tenant-ID": "test-tenant"},
        )

        assert response.status_code == 404

    def test_update_governance_wrong_tenant(
        self, client: TestClient, mock_manager: MockSessionContextManager
    ):
        """Test tenant isolation on update."""
        # Create session for tenant-a
        create_response = client.post(
            "/api/v1/sessions",
            json={"risk_level": "medium"},
            headers={"X-Tenant-ID": "tenant-a"},
        )
        session_id = create_response.json()["session_id"]

        # Try to update from tenant-b
        update_response = client.put(
            f"/api/v1/sessions/{session_id}/governance",
            json={"risk_level": "high"},
            headers={"X-Tenant-ID": "tenant-b"},
        )

        assert update_response.status_code == 403


# =============================================================================
# Session Deletion Tests
# =============================================================================


class TestDeleteSession:
    """Tests for DELETE /api/v1/sessions/{session_id} endpoint."""

    def test_delete_session_success(
        self, client: TestClient, mock_manager: MockSessionContextManager
    ):
        """Test deleting an existing session."""
        # Create session
        create_response = client.post(
            "/api/v1/sessions",
            json={"risk_level": "medium"},
            headers={"X-Tenant-ID": "test-tenant"},
        )
        session_id = create_response.json()["session_id"]

        # Delete session
        delete_response = client.delete(
            f"/api/v1/sessions/{session_id}",
            headers={"X-Tenant-ID": "test-tenant"},
        )

        assert delete_response.status_code == 204

        # Verify session is gone
        get_response = client.get(
            f"/api/v1/sessions/{session_id}",
            headers={"X-Tenant-ID": "test-tenant"},
        )
        assert get_response.status_code == 404

    def test_delete_session_not_found(
        self, client: TestClient, mock_manager: MockSessionContextManager
    ):
        """Test deleting non-existent session returns 404."""
        response = client.delete(
            "/api/v1/sessions/non-existent-session",
            headers={"X-Tenant-ID": "test-tenant"},
        )

        assert response.status_code == 404

    def test_delete_session_wrong_tenant(
        self, client: TestClient, mock_manager: MockSessionContextManager
    ):
        """Test tenant isolation on delete."""
        # Create session for tenant-a
        create_response = client.post(
            "/api/v1/sessions",
            json={"risk_level": "medium"},
            headers={"X-Tenant-ID": "tenant-a"},
        )
        session_id = create_response.json()["session_id"]

        # Try to delete from tenant-b
        delete_response = client.delete(
            f"/api/v1/sessions/{session_id}",
            headers={"X-Tenant-ID": "tenant-b"},
        )

        assert delete_response.status_code == 403

        # Verify session still exists for tenant-a
        get_response = client.get(
            f"/api/v1/sessions/{session_id}",
            headers={"X-Tenant-ID": "tenant-a"},
        )
        assert get_response.status_code == 200


# =============================================================================
# TTL Extension Tests
# =============================================================================


class TestExtendSessionTTL:
    """Tests for POST /api/v1/sessions/{session_id}/extend endpoint."""

    def test_extend_ttl_success(self, client: TestClient, mock_manager: MockSessionContextManager):
        """Test extending session TTL."""
        # Create session
        create_response = client.post(
            "/api/v1/sessions",
            json={"risk_level": "medium", "ttl_seconds": 3600},
            headers={"X-Tenant-ID": "test-tenant"},
        )
        session_id = create_response.json()["session_id"]

        # Extend TTL
        extend_response = client.post(
            f"/api/v1/sessions/{session_id}/extend",
            params={"ttl_seconds": 7200},
            headers={"X-Tenant-ID": "test-tenant"},
        )

        assert extend_response.status_code == 200
        data = extend_response.json()
        assert data["session_id"] == session_id

    def test_extend_ttl_not_found(
        self, client: TestClient, mock_manager: MockSessionContextManager
    ):
        """Test extending TTL for non-existent session."""
        response = client.post(
            "/api/v1/sessions/non-existent-session/extend",
            params={"ttl_seconds": 7200},
            headers={"X-Tenant-ID": "test-tenant"},
        )

        assert response.status_code == 404

    def test_extend_ttl_wrong_tenant(
        self, client: TestClient, mock_manager: MockSessionContextManager
    ):
        """Test tenant isolation on TTL extension."""
        # Create session for tenant-a
        create_response = client.post(
            "/api/v1/sessions",
            json={"risk_level": "medium"},
            headers={"X-Tenant-ID": "tenant-a"},
        )
        session_id = create_response.json()["session_id"]

        # Try to extend from tenant-b
        extend_response = client.post(
            f"/api/v1/sessions/{session_id}/extend",
            params={"ttl_seconds": 7200},
            headers={"X-Tenant-ID": "tenant-b"},
        )

        assert extend_response.status_code == 403


# =============================================================================
# Metrics Tests
# =============================================================================


class TestSessionMetrics:
    """Tests for GET /api/v1/sessions endpoint (metrics)."""

    def test_get_metrics_success(self, client: TestClient, mock_manager: MockSessionContextManager):
        """Test retrieving session manager metrics."""
        # Create and access some sessions to generate metrics
        for _i in range(3):
            client.post(
                "/api/v1/sessions",
                json={"risk_level": "medium"},
                headers={"X-Tenant-ID": "test-tenant"},
            )

        # Get metrics
        response = client.get("/api/v1/sessions")

        assert response.status_code == 200
        data = response.json()
        assert "cache_hits" in data
        assert "cache_misses" in data
        assert "creates" in data
        assert data["creates"] == 3
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH


# =============================================================================
# Policy Selection Tests
# =============================================================================


class TestPolicySelection:
    """Tests for POST /api/v1/sessions/{session_id}/policies/select endpoint."""

    def test_select_policies_basic(
        self, client: TestClient, mock_manager: MockSessionContextManager
    ):
        """Test basic policy selection for a session."""
        # Create session with policy override
        create_response = client.post(
            "/api/v1/sessions",
            json={
                "risk_level": "medium",
                "policy_overrides": {"policy_id": "test-policy-001"},
            },
            headers={"X-Tenant-ID": "test-tenant"},
        )
        assert create_response.status_code == 201
        session_id = create_response.json()["session_id"]

        # Select policies
        response = client.post(
            f"/api/v1/sessions/{session_id}/policies/select",
            headers={"X-Tenant-ID": "test-tenant"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == session_id
        assert data["tenant_id"] == "test-tenant"
        assert data["risk_level"] == "medium"
        assert "selected_policy" in data
        assert "candidate_policies" in data
        assert "enabled_policies" in data
        assert "disabled_policies" in data
        assert "selection_metadata" in data
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_select_policies_with_policy_override(
        self, client: TestClient, mock_manager: MockSessionContextManager
    ):
        """Test policy selection returns session override as highest priority."""
        # Create session with explicit policy_id override
        create_response = client.post(
            "/api/v1/sessions",
            json={
                "risk_level": "high",
                "policy_overrides": {"policy_id": "override-policy-123"},
            },
            headers={"X-Tenant-ID": "test-tenant"},
        )
        session_id = create_response.json()["session_id"]

        # Select policies
        response = client.post(
            f"/api/v1/sessions/{session_id}/policies/select",
            headers={"X-Tenant-ID": "test-tenant"},
        )

        assert response.status_code == 200
        data = response.json()

        # Selected policy should be from session override
        assert data["selected_policy"] is not None
        assert data["selected_policy"]["source"] == "session"
        assert data["selected_policy"]["priority"] == 95  # policy_overrides.policy_id gets 95
        assert "policy_overrides" in data["selected_policy"]["reasoning"]

    def test_select_policies_with_enabled_policies(
        self, client: TestClient, mock_manager: MockSessionContextManager
    ):
        """Test policy selection with enabled_policies list."""
        # Create session with enabled policies
        create_response = client.post(
            "/api/v1/sessions",
            json={
                "risk_level": "medium",
                "enabled_policies": ["policy-a", "policy-b", "policy-c"],
            },
            headers={"X-Tenant-ID": "test-tenant"},
        )
        session_id = create_response.json()["session_id"]

        # Select policies
        response = client.post(
            f"/api/v1/sessions/{session_id}/policies/select",
            headers={"X-Tenant-ID": "test-tenant"},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["enabled_policies"]) == 3
        assert "policy-a" in data["enabled_policies"]

    def test_select_policies_with_policy_name_filter(
        self, client: TestClient, mock_manager: MockSessionContextManager
    ):
        """Test policy selection with policy name filter."""
        # Create session
        create_response = client.post(
            "/api/v1/sessions",
            json={"risk_level": "medium"},
            headers={"X-Tenant-ID": "test-tenant"},
        )
        session_id = create_response.json()["session_id"]

        # Select policies with filter
        response = client.post(
            f"/api/v1/sessions/{session_id}/policies/select",
            json={"policy_name_filter": "strict-governance"},
            headers={"X-Tenant-ID": "test-tenant"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["selection_metadata"]["policy_name_filter"] == "strict-governance"

    def test_select_policies_with_risk_level_override(
        self, client: TestClient, mock_manager: MockSessionContextManager
    ):
        """Test policy selection with risk level override."""
        # Create session with medium risk
        create_response = client.post(
            "/api/v1/sessions",
            json={"risk_level": "medium"},
            headers={"X-Tenant-ID": "test-tenant"},
        )
        session_id = create_response.json()["session_id"]

        # Select policies with critical risk override
        response = client.post(
            f"/api/v1/sessions/{session_id}/policies/select",
            json={"risk_level_override": "critical"},
            headers={"X-Tenant-ID": "test-tenant"},
        )

        assert response.status_code == 200
        data = response.json()
        # Risk level should be overridden to critical
        assert data["risk_level"] == "critical"

    def test_select_policies_include_all_candidates(
        self, client: TestClient, mock_manager: MockSessionContextManager
    ):
        """Test policy selection with include_all_candidates option."""
        # Create session with multiple policy sources
        create_response = client.post(
            "/api/v1/sessions",
            json={
                "risk_level": "high",
                "enabled_policies": ["policy-1", "policy-2"],
                "policy_overrides": {"policy_id": "override-policy"},
            },
            headers={"X-Tenant-ID": "test-tenant"},
        )
        session_id = create_response.json()["session_id"]

        # Select policies with all candidates
        response = client.post(
            f"/api/v1/sessions/{session_id}/policies/select",
            json={"include_all_candidates": True},
            headers={"X-Tenant-ID": "test-tenant"},
        )

        assert response.status_code == 200
        data = response.json()
        # Should include all candidate policies
        assert len(data["candidate_policies"]) >= 1

    def test_select_policies_session_not_found(
        self, client: TestClient, mock_manager: MockSessionContextManager
    ):
        """Test policy selection for non-existent session."""
        response = client.post(
            "/api/v1/sessions/non-existent-session-id/policies/select",
            headers={"X-Tenant-ID": "test-tenant"},
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_select_policies_wrong_tenant(
        self, client: TestClient, mock_manager: MockSessionContextManager
    ):
        """Test tenant isolation on policy selection."""
        # Create session for tenant-a
        create_response = client.post(
            "/api/v1/sessions",
            json={"risk_level": "medium"},
            headers={"X-Tenant-ID": "tenant-a"},
        )
        session_id = create_response.json()["session_id"]

        # Try to select policies from tenant-b
        response = client.post(
            f"/api/v1/sessions/{session_id}/policies/select",
            headers={"X-Tenant-ID": "tenant-b"},
        )

        assert response.status_code == 403

    def test_select_policies_missing_tenant_header(
        self, client: TestClient, mock_manager: MockSessionContextManager
    ):
        """Test policy selection fails without tenant header."""
        response = client.post(
            "/api/v1/sessions/some-session/policies/select",
        )

        # Should fail with 400 (missing tenant header)
        assert response.status_code in [400, 422]

    def test_select_policies_with_disabled_policies(
        self, client: TestClient, mock_manager: MockSessionContextManager
    ):
        """Test policy selection with disabled policies."""
        # Create session with disabled policies
        create_response = client.post(
            "/api/v1/sessions",
            json={
                "risk_level": "medium",
                "enabled_policies": ["policy-a"],
                "disabled_policies": ["policy-x", "policy-y"],
            },
            headers={"X-Tenant-ID": "test-tenant"},
        )
        session_id = create_response.json()["session_id"]

        # Select policies
        response = client.post(
            f"/api/v1/sessions/{session_id}/policies/select",
            headers={"X-Tenant-ID": "test-tenant"},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["disabled_policies"]) == 2
        assert "policy-x" in data["disabled_policies"]

    def test_select_policies_timestamp_format(
        self, client: TestClient, mock_manager: MockSessionContextManager
    ):
        """Test policy selection response includes valid timestamp."""
        # Create session
        create_response = client.post(
            "/api/v1/sessions",
            json={"risk_level": "low"},
            headers={"X-Tenant-ID": "test-tenant"},
        )
        session_id = create_response.json()["session_id"]

        # Select policies
        response = client.post(
            f"/api/v1/sessions/{session_id}/policies/select",
            headers={"X-Tenant-ID": "test-tenant"},
        )

        assert response.status_code == 200
        data = response.json()
        # Timestamp should be ISO format
        assert "timestamp" in data
        assert "T" in data["timestamp"]  # ISO format includes T separator

    def test_select_policies_constitutional_hash(
        self, client: TestClient, mock_manager: MockSessionContextManager
    ):
        """Test policy selection response includes constitutional hash."""
        # Create session
        create_response = client.post(
            "/api/v1/sessions",
            json={"risk_level": "medium"},
            headers={"X-Tenant-ID": "test-tenant"},
        )
        session_id = create_response.json()["session_id"]

        # Select policies
        response = client.post(
            f"/api/v1/sessions/{session_id}/policies/select",
            headers={"X-Tenant-ID": "test-tenant"},
        )

        assert response.status_code == 200
        assert response.json()["constitutional_hash"] == CONSTITUTIONAL_HASH


# =============================================================================
# Constitutional Compliance Tests
# =============================================================================


class TestConstitutionalCompliance:
    """Tests for constitutional hash enforcement."""

    def test_session_includes_constitutional_hash(
        self, client: TestClient, mock_manager: MockSessionContextManager
    ):
        """Test that all session responses include constitutional hash."""
        # Create session
        create_response = client.post(
            "/api/v1/sessions",
            json={"risk_level": "medium"},
            headers={"X-Tenant-ID": "test-tenant"},
        )

        assert create_response.status_code == 201
        assert create_response.json()["constitutional_hash"] == CONSTITUTIONAL_HASH

        session_id = create_response.json()["session_id"]

        # Get session
        get_response = client.get(
            f"/api/v1/sessions/{session_id}",
            headers={"X-Tenant-ID": "test-tenant"},
        )

        assert get_response.json()["constitutional_hash"] == CONSTITUTIONAL_HASH

        # Update session
        update_response = client.put(
            f"/api/v1/sessions/{session_id}/governance",
            json={"risk_level": "high"},
            headers={"X-Tenant-ID": "test-tenant"},
        )

        assert update_response.json()["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_metrics_include_constitutional_hash(
        self, client: TestClient, mock_manager: MockSessionContextManager
    ):
        """Test that metrics response includes constitutional hash."""
        response = client.get("/api/v1/sessions")

        assert response.status_code == 200
        assert response.json()["constitutional_hash"] == CONSTITUTIONAL_HASH


# =============================================================================
# Risk Level Tests
# =============================================================================


class TestRiskLevelHandling:
    """Tests for session risk level handling."""

    @pytest.mark.parametrize(
        "risk_level,expected",
        [
            ("low", "low"),
            ("medium", "medium"),
            ("high", "high"),
            ("critical", "critical"),
            ("LOW", "low"),  # Case insensitivity
            ("CRITICAL", "critical"),
        ],
    )
    def test_valid_risk_levels(
        self,
        client: TestClient,
        mock_manager: MockSessionContextManager,
        risk_level: str,
        expected: str,
    ):
        """Test all valid risk levels are accepted."""
        response = client.post(
            "/api/v1/sessions",
            json={"risk_level": risk_level},
            headers={"X-Tenant-ID": "test-tenant"},
        )

        assert response.status_code == 201
        assert response.json()["risk_level"] == expected

    @pytest.mark.parametrize(
        "invalid_risk_level",
        ["ultra-high", "maximum", "none", "invalid", "1", ""],
    )
    def test_invalid_risk_levels(
        self,
        client: TestClient,
        mock_manager: MockSessionContextManager,
        invalid_risk_level: str,
    ):
        """Test invalid risk levels are rejected."""
        response = client.post(
            "/api/v1/sessions",
            json={"risk_level": invalid_risk_level},
            headers={"X-Tenant-ID": "test-tenant"},
        )

        assert response.status_code == 422


# =============================================================================
# Automation Level Tests
# =============================================================================


class TestAutomationLevelHandling:
    """Tests for max automation level handling."""

    @pytest.mark.parametrize(
        "automation_level,expected",
        [
            ("full", "full"),
            ("partial", "partial"),
            ("none", "none"),
            ("FULL", "full"),  # Case insensitivity
            (None, None),  # Not specified
        ],
    )
    def test_valid_automation_levels(
        self,
        client: TestClient,
        mock_manager: MockSessionContextManager,
        automation_level: str | None,
        expected: str | None,
    ):
        """Test valid automation levels are accepted."""
        request_data = {"risk_level": "medium"}
        if automation_level is not None:
            request_data["max_automation_level"] = automation_level

        response = client.post(
            "/api/v1/sessions",
            json=request_data,
            headers={"X-Tenant-ID": "test-tenant"},
        )

        assert response.status_code == 201
        assert response.json()["max_automation_level"] == expected


# =============================================================================
# Policy Configuration Tests
# =============================================================================


class TestPolicyConfiguration:
    """Tests for policy configuration handling."""

    def test_session_with_enabled_policies(
        self, client: TestClient, mock_manager: MockSessionContextManager
    ):
        """Test creating session with enabled policies list."""
        enabled_policies = ["audit-logging", "rate-limiting", "security-headers"]

        response = client.post(
            "/api/v1/sessions",
            json={
                "risk_level": "high",
                "enabled_policies": enabled_policies,
            },
            headers={"X-Tenant-ID": "test-tenant"},
        )

        assert response.status_code == 201
        assert response.json()["enabled_policies"] == enabled_policies

    def test_session_with_disabled_policies(
        self, client: TestClient, mock_manager: MockSessionContextManager
    ):
        """Test creating session with disabled policies list."""
        disabled_policies = ["experimental-features", "beta-testing"]

        response = client.post(
            "/api/v1/sessions",
            json={
                "risk_level": "medium",
                "disabled_policies": disabled_policies,
            },
            headers={"X-Tenant-ID": "test-tenant"},
        )

        assert response.status_code == 201
        assert response.json()["disabled_policies"] == disabled_policies

    def test_session_with_policy_overrides(
        self, client: TestClient, mock_manager: MockSessionContextManager
    ):
        """Test creating session with policy overrides."""
        policy_overrides = {
            "max_tokens": 2000,
            "temperature": 0.7,
            "timeout_seconds": 30,
        }

        response = client.post(
            "/api/v1/sessions",
            json={
                "risk_level": "medium",
                "policy_overrides": policy_overrides,
            },
            headers={"X-Tenant-ID": "test-tenant"},
        )

        assert response.status_code == 201
        assert response.json()["policy_overrides"] == policy_overrides


# Allow running tests directly
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
