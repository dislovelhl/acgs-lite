"""
ACGS-2 Enterprise SSO Integration Tests
Constitutional Hash: 608508a9bd224290

Tests for Enterprise SSO integration with multi-tenancy and MACI frameworks.

Phase 10 Task 2: Enterprise SSO & Identity Management Integration
"""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from enterprise_sso import (
    CONSTITUTIONAL_HASH,
    EnterpriseSSOService,
    TenantIdPConfig,
    TenantSSOConfig,
    TenantSSOConfigManager,
)
from enterprise_sso.middleware import (
    SSOMiddlewareConfig,
    SSOSessionContext,
    clear_sso_session,
    get_current_sso_session,
    require_sso_authentication,
    set_sso_session,
)
from enterprise_sso.tenant_sso_config import (
    AttributeMapping,
    OIDCConfig,
    RoleMappingRule,
    SAMLConfig,
    SSOProtocolType,
    create_azure_ad_idp_config,
    create_google_workspace_idp_config,
    create_okta_idp_config,
)
from enterprise_sso.tenant_sso_config import (
    IdPProviderType as IdPType,
)


class TestConstitutionalHash:
    """Tests for constitutional hash validation."""

    def test_constitutional_hash_present(self):
        """Verify constitutional hash is correctly defined."""
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    def test_hash_in_tenant_sso_config(self):
        """Verify hash is in TenantSSOConfig."""
        config = TenantSSOConfig(
            tenant_id="test-tenant",
            sso_enabled=True,
        )
        assert config.constitutional_hash == CONSTITUTIONAL_HASH

    def test_hash_in_session_context(self):
        """Verify hash is in SSOSessionContext."""
        session = SSOSessionContext(
            session_id="test-session",
            user_id="test-user",
            tenant_id="test-tenant",
            email="test@example.com",
            display_name="Test User",
            maci_roles=["EXECUTIVE"],
            idp_groups=["admins"],
            attributes={},
            authenticated_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        assert session.constitutional_hash == CONSTITUTIONAL_HASH


class TestSAMLConfig:
    """Tests for SAML configuration."""

    def test_create_saml_config(self):
        """Test SAML configuration creation."""
        config = SAMLConfig(
            entity_id="https://idp.example.com",
            sso_url="https://idp.example.com/sso",
            x509_certificate="MIICajCC...",
        )
        assert config.entity_id == "https://idp.example.com"
        assert config.sso_url == "https://idp.example.com/sso"
        assert config.x509_certificate == "MIICajCC..."
        assert config.slo_url is None

    def test_saml_config_with_optional_fields(self):
        """Test SAML configuration with all fields."""
        config = SAMLConfig(
            entity_id="https://idp.example.com",
            sso_url="https://idp.example.com/sso",
            x509_certificate="MIICajCC...",
            slo_url="https://idp.example.com/slo",
            name_id_format="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress",
            authn_request_signed=True,
            want_assertions_signed=True,
        )
        assert config.slo_url == "https://idp.example.com/slo"
        assert config.authn_request_signed is True
        assert config.want_assertions_signed is True


class TestOIDCConfig:
    """Tests for OIDC configuration."""

    def test_create_oidc_config(self):
        """Test OIDC configuration creation."""
        config = OIDCConfig(
            client_id="test-client-id",
            client_secret="test-secret",
            issuer="https://idp.example.com",
            authorization_endpoint="https://idp.example.com/auth",
            token_endpoint="https://idp.example.com/token",
        )
        assert config.client_id == "test-client-id"
        assert config.issuer == "https://idp.example.com"

    def test_oidc_default_scopes(self):
        """Test OIDC default scopes."""
        config = OIDCConfig(
            client_id="test-client-id",
            client_secret="test-secret",
            issuer="https://idp.example.com",
            authorization_endpoint="https://idp.example.com/auth",
            token_endpoint="https://idp.example.com/token",
        )
        assert "openid" in config.scopes
        assert "profile" in config.scopes
        assert "email" in config.scopes


class TestRoleMappingRule:
    """Tests for role mapping rules."""

    def test_group_to_role_mapping(self):
        """Test group-based role mapping."""
        rule = RoleMappingRule(
            idp_group="Administrators",
            maci_role="EXECUTIVE",
        )
        assert rule.idp_group == "Administrators"
        assert rule.maci_role == "EXECUTIVE"

    def test_role_mapping_with_priority(self):
        """Test role mapping with priority."""
        rule = RoleMappingRule(
            idp_group="Developers",
            maci_role="IMPLEMENTER",
            priority=10,
        )
        assert rule.idp_group == "Developers"
        assert rule.maci_role == "IMPLEMENTER"
        assert rule.priority == 10

    def test_role_mapping_matches(self):
        """Test role mapping group matching."""
        rule = RoleMappingRule(
            idp_group="Administrators",
            maci_role="EXECUTIVE",
        )
        assert rule.matches(["Administrators", "Users"]) is True
        assert rule.matches(["Users"]) is False


class TestTenantIdPConfig:
    """Tests for tenant IdP configuration."""

    def test_create_okta_config(self):
        """Test Okta IdP configuration factory."""
        config = create_okta_idp_config(
            tenant_id="test-tenant",
            okta_domain="example.okta.com",
            client_id="okta-client-id",
            client_secret="okta-secret",
        )
        assert config.tenant_id == "test-tenant"
        assert config.provider_type == IdPType.OKTA
        assert config.enabled is True

    def test_create_azure_ad_config(self):
        """Test Azure AD IdP configuration factory."""
        config = create_azure_ad_idp_config(
            tenant_id="test-tenant",
            azure_tenant_id="azure-tenant-id",
            client_id="azure-client-id",
            client_secret="azure-secret",
        )
        assert config.tenant_id == "test-tenant"
        assert config.provider_type == IdPType.AZURE_AD
        assert config.enabled is True

    def test_create_google_workspace_config(self):
        """Test Google Workspace IdP configuration factory."""
        config = create_google_workspace_idp_config(
            tenant_id="test-tenant",
            client_id="google-client-id",
            client_secret="google-secret",
            hosted_domain="example.com",
        )
        assert config.tenant_id == "test-tenant"
        assert config.provider_type == IdPType.GOOGLE_WORKSPACE
        assert config.enabled is True


class TestTenantSSOConfig:
    """Tests for tenant SSO configuration."""

    def test_create_tenant_sso_config(self):
        """Test tenant SSO configuration creation."""
        config = TenantSSOConfig(
            tenant_id="test-tenant",
            sso_enabled=True,
        )
        assert config.tenant_id == "test-tenant"
        assert config.sso_enabled is True
        assert len(config.identity_providers) == 0

    def test_add_identity_provider(self):
        """Test adding IdP to tenant config."""
        config = TenantSSOConfig(
            tenant_id="test-tenant",
            sso_enabled=True,
        )
        idp = create_okta_idp_config(
            tenant_id="test-tenant",
            okta_domain="example.okta.com",
            client_id="client-id",
            client_secret="secret",
        )
        config.identity_providers.append(idp)
        assert len(config.identity_providers) == 1

    def test_get_enabled_identity_providers(self):
        """Test getting enabled IdPs."""
        oidc_config1 = OIDCConfig(
            issuer="https://example1.okta.com",
            client_id="client-1",
        )
        oidc_config2 = OIDCConfig(
            issuer="https://example2.okta.com",
            client_id="client-2",
        )
        idp1 = TenantIdPConfig(
            idp_id="idp-1",
            tenant_id="test-tenant",
            provider_type=IdPType.OKTA,
            protocol=SSOProtocolType.OIDC,
            display_name="Okta",
            enabled=True,
            oidc_config=oidc_config1,
        )
        idp2 = TenantIdPConfig(
            idp_id="idp-2",
            tenant_id="test-tenant",
            provider_type=IdPType.AZURE_AD,
            protocol=SSOProtocolType.OIDC,
            display_name="Azure AD",
            enabled=False,
            oidc_config=oidc_config2,
        )
        config = TenantSSOConfig(
            tenant_id="test-tenant",
            sso_enabled=True,
            identity_providers=[idp1, idp2],
        )

        enabled = config.get_enabled_idps()
        assert len(enabled) == 1
        assert enabled[0].idp_id == "idp-1"

    def test_get_default_idp(self):
        """Test getting default IdP."""
        oidc_config = OIDCConfig(
            issuer="https://example.okta.com",
            client_id="client-id",
        )
        idp = TenantIdPConfig(
            idp_id="idp-1",
            tenant_id="test-tenant",
            provider_type=IdPType.OKTA,
            protocol=SSOProtocolType.OIDC,
            display_name="Okta",
            enabled=True,
            oidc_config=oidc_config,
        )
        config = TenantSSOConfig(
            tenant_id="test-tenant",
            sso_enabled=True,
            identity_providers=[idp],
            default_idp_id="idp-1",
        )

        assert config.default_idp_id == "idp-1"
        assert config.get_default_idp() is not None
        assert config.get_default_idp().idp_id == "idp-1"

    def test_get_idp_not_found(self):
        """Test getting non-existent IdP."""
        config = TenantSSOConfig(
            tenant_id="test-tenant",
            sso_enabled=True,
        )
        result = config.get_idp("non-existent")
        assert result is None


class TestTenantSSOConfigManager:
    """Tests for tenant SSO configuration manager."""

    def test_create_manager(self):
        """Test creating config manager."""
        manager = TenantSSOConfigManager()
        assert len(manager._configs) == 0

    def test_create_and_get_config(self):
        """Test creating and retrieving tenant config."""
        manager = TenantSSOConfigManager()
        config = manager.create_config(
            tenant_id="test-tenant",
            sso_enabled=True,
        )
        assert config is not None
        retrieved = manager.get_config("test-tenant")
        assert retrieved is not None
        assert retrieved.tenant_id == "test-tenant"

    def test_get_nonexistent_config(self):
        """Test getting non-existent config."""
        manager = TenantSSOConfigManager()
        result = manager.get_config("non-existent")
        assert result is None

    def test_delete_config(self):
        """Test deleting tenant config."""
        manager = TenantSSOConfigManager()
        manager.create_config(
            tenant_id="test-tenant",
            sso_enabled=True,
        )
        result = manager.delete_config("test-tenant")
        assert result is True
        assert manager.get_config("test-tenant") is None


class TestSSOSessionContext:
    """Tests for SSO session context."""

    def test_create_session_context(self):
        """Test creating session context."""
        now = datetime.now(UTC)
        session = SSOSessionContext(
            session_id="session-123",
            user_id="user-456",
            tenant_id="tenant-789",
            email="user@example.com",
            display_name="Test User",
            maci_roles=["EXECUTIVE", "MONITOR"],
            idp_groups=["admins", "users"],
            attributes={"department": "Engineering"},
            authenticated_at=now,
            expires_at=now + timedelta(hours=1),
        )
        assert session.session_id == "session-123"
        assert session.user_id == "user-456"
        assert session.email == "user@example.com"

    def test_session_not_expired(self):
        """Test session not expired."""
        now = datetime.now(UTC)
        session = SSOSessionContext(
            session_id="session-123",
            user_id="user-456",
            tenant_id="tenant-789",
            email="user@example.com",
            display_name="Test User",
            maci_roles=["EXECUTIVE"],
            idp_groups=[],
            attributes={},
            authenticated_at=now,
            expires_at=now + timedelta(hours=1),
        )
        assert session.is_expired is False
        assert session.time_until_expiry > 0

    def test_session_expired(self):
        """Test expired session."""
        now = datetime.now(UTC)
        session = SSOSessionContext(
            session_id="session-123",
            user_id="user-456",
            tenant_id="tenant-789",
            email="user@example.com",
            display_name="Test User",
            maci_roles=["EXECUTIVE"],
            idp_groups=[],
            attributes={},
            authenticated_at=now - timedelta(hours=2),
            expires_at=now - timedelta(hours=1),
        )
        assert session.is_expired is True
        assert session.time_until_expiry == 0

    def test_has_role(self):
        """Test role checking."""
        now = datetime.now(UTC)
        session = SSOSessionContext(
            session_id="session-123",
            user_id="user-456",
            tenant_id="tenant-789",
            email="user@example.com",
            display_name="Test User",
            maci_roles=["EXECUTIVE", "MONITOR"],
            idp_groups=[],
            attributes={},
            authenticated_at=now,
            expires_at=now + timedelta(hours=1),
        )
        assert session.has_role("EXECUTIVE") is True
        assert session.has_role("executive") is True  # Case insensitive
        assert session.has_role("JUDICIAL") is False

    def test_has_any_role(self):
        """Test any role checking."""
        now = datetime.now(UTC)
        session = SSOSessionContext(
            session_id="session-123",
            user_id="user-456",
            tenant_id="tenant-789",
            email="user@example.com",
            display_name="Test User",
            maci_roles=["EXECUTIVE"],
            idp_groups=[],
            attributes={},
            authenticated_at=now,
            expires_at=now + timedelta(hours=1),
        )
        assert session.has_any_role(["EXECUTIVE", "JUDICIAL"]) is True
        assert session.has_any_role(["JUDICIAL", "LEGISLATIVE"]) is False

    def test_has_all_roles(self):
        """Test all roles checking."""
        now = datetime.now(UTC)
        session = SSOSessionContext(
            session_id="session-123",
            user_id="user-456",
            tenant_id="tenant-789",
            email="user@example.com",
            display_name="Test User",
            maci_roles=["EXECUTIVE", "MONITOR", "AUDITOR"],
            idp_groups=[],
            attributes={},
            authenticated_at=now,
            expires_at=now + timedelta(hours=1),
        )
        assert session.has_all_roles(["EXECUTIVE", "MONITOR"]) is True
        assert session.has_all_roles(["EXECUTIVE", "JUDICIAL"]) is False

    def test_to_dict(self):
        """Test session to dict conversion."""
        now = datetime.now(UTC)
        session = SSOSessionContext(
            session_id="session-123",
            user_id="user-456",
            tenant_id="tenant-789",
            email="user@example.com",
            display_name="Test User",
            maci_roles=["EXECUTIVE"],
            idp_groups=["admins"],
            attributes={"key": "value"},
            authenticated_at=now,
            expires_at=now + timedelta(hours=1),
        )
        data = session.to_dict()
        assert data["session_id"] == "session-123"
        assert data["user_id"] == "user-456"
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH


class TestSSOSessionContextVars:
    """Tests for SSO session context variables."""

    def test_get_no_session(self):
        """Test getting session when none set."""
        clear_sso_session()
        assert get_current_sso_session() is None

    def test_set_and_get_session(self):
        """Test setting and getting session."""
        now = datetime.now(UTC)
        session = SSOSessionContext(
            session_id="session-123",
            user_id="user-456",
            tenant_id="tenant-789",
            email="user@example.com",
            display_name="Test User",
            maci_roles=["EXECUTIVE"],
            idp_groups=[],
            attributes={},
            authenticated_at=now,
            expires_at=now + timedelta(hours=1),
        )
        set_sso_session(session)
        try:
            retrieved = get_current_sso_session()
            assert retrieved is not None
            assert retrieved.session_id == "session-123"
        finally:
            clear_sso_session()

    def test_clear_session(self):
        """Test clearing session."""
        now = datetime.now(UTC)
        session = SSOSessionContext(
            session_id="session-123",
            user_id="user-456",
            tenant_id="tenant-789",
            email="user@example.com",
            display_name="Test User",
            maci_roles=["EXECUTIVE"],
            idp_groups=[],
            attributes={},
            authenticated_at=now,
            expires_at=now + timedelta(hours=1),
        )
        set_sso_session(session)
        clear_sso_session()
        assert get_current_sso_session() is None


class TestRequireSSOAuthentication:
    """Tests for require_sso_authentication decorator."""

    def test_sync_function_without_session(self):
        """Test sync function fails without session."""
        clear_sso_session()

        @require_sso_authentication()
        def protected_function():
            return "success"

        with pytest.raises(PermissionError, match="SSO authentication required"):
            protected_function()

    def test_sync_function_with_session(self):
        """Test sync function succeeds with session."""
        now = datetime.now(UTC)
        session = SSOSessionContext(
            session_id="session-123",
            user_id="user-456",
            tenant_id="tenant-789",
            email="user@example.com",
            display_name="Test User",
            maci_roles=["EXECUTIVE"],
            idp_groups=[],
            attributes={},
            authenticated_at=now,
            expires_at=now + timedelta(hours=1),
        )
        set_sso_session(session)
        try:

            @require_sso_authentication()
            def protected_function():
                return "success"

            result = protected_function()
            assert result == "success"
        finally:
            clear_sso_session()

    def test_sync_function_with_expired_session(self):
        """Test sync function fails with expired session."""
        now = datetime.now(UTC)
        session = SSOSessionContext(
            session_id="session-123",
            user_id="user-456",
            tenant_id="tenant-789",
            email="user@example.com",
            display_name="Test User",
            maci_roles=["EXECUTIVE"],
            idp_groups=[],
            attributes={},
            authenticated_at=now - timedelta(hours=2),
            expires_at=now - timedelta(hours=1),
        )
        set_sso_session(session)
        try:

            @require_sso_authentication()
            def protected_function():
                return "success"

            with pytest.raises(PermissionError, match="SSO session expired"):
                protected_function()
        finally:
            clear_sso_session()

    def test_sync_function_with_required_role(self):
        """Test sync function with required role."""
        now = datetime.now(UTC)
        session = SSOSessionContext(
            session_id="session-123",
            user_id="user-456",
            tenant_id="tenant-789",
            email="user@example.com",
            display_name="Test User",
            maci_roles=["EXECUTIVE"],
            idp_groups=[],
            attributes={},
            authenticated_at=now,
            expires_at=now + timedelta(hours=1),
        )
        set_sso_session(session)
        try:

            @require_sso_authentication(roles=["EXECUTIVE"])
            def protected_function():
                return "success"

            result = protected_function()
            assert result == "success"
        finally:
            clear_sso_session()

    def test_sync_function_missing_role(self):
        """Test sync function fails with missing role."""
        now = datetime.now(UTC)
        session = SSOSessionContext(
            session_id="session-123",
            user_id="user-456",
            tenant_id="tenant-789",
            email="user@example.com",
            display_name="Test User",
            maci_roles=["MONITOR"],
            idp_groups=[],
            attributes={},
            authenticated_at=now,
            expires_at=now + timedelta(hours=1),
        )
        set_sso_session(session)
        try:

            @require_sso_authentication(roles=["EXECUTIVE", "JUDICIAL"])
            def protected_function():
                return "success"

            with pytest.raises(PermissionError, match="Requires one of roles"):
                protected_function()
        finally:
            clear_sso_session()

    async def test_async_function_with_session(self):
        """Test async function succeeds with session."""
        now = datetime.now(UTC)
        session = SSOSessionContext(
            session_id="session-123",
            user_id="user-456",
            tenant_id="tenant-789",
            email="user@example.com",
            display_name="Test User",
            maci_roles=["EXECUTIVE"],
            idp_groups=[],
            attributes={},
            authenticated_at=now,
            expires_at=now + timedelta(hours=1),
        )
        set_sso_session(session)
        try:

            @require_sso_authentication()
            async def protected_async_function():
                return "success"

            result = await protected_async_function()
            assert result == "success"
        finally:
            clear_sso_session()


class TestSSOMiddlewareConfig:
    """Tests for SSO middleware configuration."""

    def test_default_config(self):
        """Test default middleware config."""
        config = SSOMiddlewareConfig()
        assert "/health" in config.excluded_paths
        assert "/metrics" in config.excluded_paths
        assert config.token_header == "Authorization"
        assert config.token_prefix == "Bearer"
        assert config.require_authentication is True  # Secure default

    def test_custom_config(self):
        """Test custom middleware config."""
        config = SSOMiddlewareConfig(
            excluded_paths={"/custom"},
            token_header="X-Auth-Token",
            require_authentication=True,
        )
        assert "/custom" in config.excluded_paths
        assert config.token_header == "X-Auth-Token"
        assert config.require_authentication is True


class TestEnterpriseSSOService:
    """Tests for Enterprise SSO Service."""

    @pytest.fixture
    def sso_service(self):
        """Create SSO service for testing."""
        return EnterpriseSSOService()

    @pytest.fixture
    def tenant_with_idp(self):
        """Create tenant config with IdP."""
        idp = create_okta_idp_config(
            tenant_id="test-tenant",
            okta_domain="example.okta.com",
            client_id="client-id",
            client_secret="secret",
        )
        config = TenantSSOConfig(
            tenant_id="test-tenant",
            sso_enabled=True,
            identity_providers=[idp],
            default_idp_id=idp.idp_id,
        )
        return config

    def test_create_service(self, sso_service):
        """Test creating SSO service."""
        assert sso_service is not None
        assert sso_service.constitutional_hash == CONSTITUTIONAL_HASH

    def test_configure_tenant(self, sso_service, tenant_with_idp):
        """Test configuring tenant SSO."""
        sso_service.configure_tenant_sso(
            tenant_id="test-tenant",
            sso_enabled=True,
        )
        config = sso_service.get_tenant_sso_config("test-tenant")
        assert config is not None
        assert config.tenant_id == "test-tenant"

    def test_get_nonexistent_tenant_config(self, sso_service):
        """Test getting non-existent tenant config."""
        result = sso_service.get_tenant_sso_config("non-existent")
        assert result is None

    def test_validate_session_not_found(self, sso_service):
        """Test validating non-existent session."""
        result = sso_service.validate_session("non-existent-token")
        assert result is None

    def test_invalidate_session(self, sso_service):
        """Test session invalidation."""
        # Non-existent session should return False
        result = sso_service.invalidate_session("non-existent-session")
        assert result is False

    def test_get_statistics(self, sso_service):
        """Test getting service statistics."""
        stats = sso_service.get_statistics()
        assert "configured_tenants" in stats
        assert "active_sessions" in stats
        assert "constitutional_hash" in stats


class TestMACIRoleIntegration:
    """Tests for MACI role integration with SSO."""

    def test_role_mapping_from_groups(self):
        """Test mapping IdP groups to MACI roles."""
        oidc_config = OIDCConfig(
            issuer="https://example.okta.com",
            client_id="client-id",
        )
        idp_config = TenantIdPConfig(
            idp_id="test-idp",
            tenant_id="test-tenant",
            provider_type=IdPType.OKTA,
            protocol=SSOProtocolType.OIDC,
            display_name="Test IdP",
            enabled=True,
            oidc_config=oidc_config,
            role_mappings=[
                RoleMappingRule(
                    idp_group="Administrators",
                    maci_role="EXECUTIVE",
                ),
                RoleMappingRule(
                    idp_group="Validators",
                    maci_role="JUDICIAL",
                ),
                RoleMappingRule(
                    idp_group="Developers",
                    maci_role="IMPLEMENTER",
                ),
            ],
        )

        # Mock user with groups
        idp_groups = ["Administrators", "Developers"]

        # Map groups to roles
        mapped_roles = idp_config.get_maci_roles(idp_groups)

        assert "EXECUTIVE" in mapped_roles
        assert "IMPLEMENTER" in mapped_roles
        assert "JUDICIAL" not in mapped_roles

    def test_default_role_assignment(self):
        """Test default role assignment from IdP config."""
        oidc_config = OIDCConfig(
            issuer="https://example.okta.com",
            client_id="client-id",
        )
        idp_config = TenantIdPConfig(
            idp_id="test-idp",
            tenant_id="test-tenant",
            provider_type=IdPType.OKTA,
            protocol=SSOProtocolType.OIDC,
            display_name="Test IdP",
            enabled=True,
            oidc_config=oidc_config,
            default_maci_role="MONITOR",
        )
        assert idp_config.default_maci_role == "MONITOR"

    def test_role_priority_ordering(self):
        """Test MACI role priority in session."""
        now = datetime.now(UTC)
        session = SSOSessionContext(
            session_id="session-123",
            user_id="user-456",
            tenant_id="tenant-789",
            email="user@example.com",
            display_name="Test User",
            maci_roles=["JUDICIAL", "EXECUTIVE", "MONITOR"],
            idp_groups=[],
            attributes={},
            authenticated_at=now,
            expires_at=now + timedelta(hours=1),
        )
        # Verify all roles are present
        assert session.has_role("JUDICIAL")
        assert session.has_role("EXECUTIVE")
        assert session.has_role("MONITOR")
        # Verify role checking works with list
        assert len(session.maci_roles) == 3


class TestJITProvisioning:
    """Tests for Just-In-Time user provisioning."""

    @pytest.fixture
    def sso_service(self):
        """Create SSO service with JIT enabled."""
        return EnterpriseSSOService()

    def test_idp_jit_config(self):
        """Test IdP JIT provisioning configuration."""
        oidc_config = OIDCConfig(
            issuer="https://test.okta.com",
            client_id="test-client-id",
        )
        idp_config = TenantIdPConfig(
            idp_id="test-idp",
            tenant_id="test-tenant",
            provider_type=IdPType.OKTA,
            protocol=SSOProtocolType.OIDC,
            display_name="Test IdP",
            enabled=True,
            jit_enabled=True,
            jit_update_on_login=True,
            oidc_config=oidc_config,
        )
        assert idp_config.jit_enabled is True
        assert idp_config.jit_update_on_login is True

    def test_idp_attribute_mapping(self):
        """Test IdP attribute mapping for JIT provisioning."""
        mapping = AttributeMapping(
            email="email",
            display_name="name",
            first_name="given_name",
            last_name="family_name",
            groups="groups",
            custom_attributes={"department": "department"},
        )
        oidc_config = OIDCConfig(
            issuer="https://test.okta.com",
            client_id="test-client-id",
        )
        idp_config = TenantIdPConfig(
            idp_id="test-idp",
            tenant_id="test-tenant",
            provider_type=IdPType.OKTA,
            protocol=SSOProtocolType.OIDC,
            display_name="Test IdP",
            enabled=True,
            attribute_mapping=mapping,
            oidc_config=oidc_config,
        )
        assert idp_config.attribute_mapping.email == "email"
        assert "department" in idp_config.attribute_mapping.custom_attributes


class TestIdentityFederation:
    """Tests for identity federation across tenants."""

    def test_tenant_sso_config_creation(self):
        """Test tenant SSO configuration creation."""
        config = TenantSSOConfig(
            tenant_id="test-tenant",
            sso_enabled=True,
            sso_enforced=False,
        )
        assert config.sso_enabled is True
        assert config.sso_enforced is False

    def test_tenant_multiple_idps(self):
        """Test tenant with multiple identity providers."""
        okta_oidc = OIDCConfig(
            issuer="https://test.okta.com",
            client_id="okta-client-id",
        )
        azure_oidc = OIDCConfig(
            issuer="https://login.microsoftonline.com/tenant-id/v2.0",
            client_id="azure-client-id",
        )
        idp1 = TenantIdPConfig(
            idp_id="okta-idp",
            tenant_id="test-tenant",
            provider_type=IdPType.OKTA,
            protocol=SSOProtocolType.OIDC,
            display_name="Okta",
            enabled=True,
            oidc_config=okta_oidc,
        )
        idp2 = TenantIdPConfig(
            idp_id="azure-idp",
            tenant_id="test-tenant",
            provider_type=IdPType.AZURE_AD,
            protocol=SSOProtocolType.OIDC,
            display_name="Azure AD",
            enabled=True,
            oidc_config=azure_oidc,
        )
        config = TenantSSOConfig(
            tenant_id="test-tenant",
            sso_enabled=True,
            identity_providers=[idp1, idp2],
        )
        assert len(config.identity_providers) == 2
        assert len(config.get_enabled_idps()) == 2


class TestSSOMACISeparationOfPowers:
    """Tests for MACI separation of powers with SSO."""

    def test_executive_cannot_validate_own_output(self):
        """Test that executive role cannot validate own outputs."""
        now = datetime.now(UTC)
        session = SSOSessionContext(
            session_id="session-123",
            user_id="executive-user",
            tenant_id="tenant-789",
            email="exec@example.com",
            display_name="Executive User",
            maci_roles=["EXECUTIVE"],
            idp_groups=["executives"],
            attributes={},
            authenticated_at=now,
            expires_at=now + timedelta(hours=1),
        )
        # Executive should not have JUDICIAL role
        assert session.has_role("EXECUTIVE") is True
        assert session.has_role("JUDICIAL") is False

    def test_judicial_validation_only(self):
        """Test that judicial role is for validation only."""
        now = datetime.now(UTC)
        session = SSOSessionContext(
            session_id="session-123",
            user_id="validator-user",
            tenant_id="tenant-789",
            email="validator@example.com",
            display_name="Validator User",
            maci_roles=["JUDICIAL"],
            idp_groups=["validators"],
            attributes={},
            authenticated_at=now,
            expires_at=now + timedelta(hours=1),
        )
        # Judicial should not have EXECUTIVE role
        assert session.has_role("JUDICIAL") is True
        assert session.has_role("EXECUTIVE") is False


class TestProtocolValidationResult:
    """Tests for ProtocolValidationResult."""

    def test_successful_result(self):
        """Test successful validation result."""
        from enterprise_sso import ProtocolValidationResult

        result = ProtocolValidationResult(
            success=True,
            user_id="user-123",
            email="user@example.com",
            display_name="Test User",
            groups=["admins", "developers"],
        )
        assert result.success is True
        assert result.user_id == "user-123"
        assert result.email == "user@example.com"
        assert "admins" in result.groups

    def test_failed_result(self):
        """Test failed validation result."""
        from enterprise_sso import ProtocolValidationResult

        result = ProtocolValidationResult(
            success=False,
            error="Token expired",
            error_code="TOKEN_EXPIRED",
        )
        assert result.success is False
        assert result.error == "Token expired"
        assert result.error_code == "TOKEN_EXPIRED"

    def test_constitutional_hash_present(self):
        """Test that constitutional hash is present."""
        from enterprise_sso import ProtocolValidationResult

        result = ProtocolValidationResult(success=True, user_id="user-123")
        assert result.constitutional_hash == CONSTITUTIONAL_HASH


class TestAuthorizationRequest:
    """Tests for AuthorizationRequest."""

    def test_create_authorization_request(self):
        """Test creating authorization request."""
        from enterprise_sso import AuthorizationRequest

        now = datetime.now(UTC)
        request = AuthorizationRequest(
            authorization_url="https://idp.example.com/authorize?state=abc123",
            state="abc123",
            nonce="nonce-value",
            expires_at=now + timedelta(minutes=10),
        )
        assert request.state == "abc123"
        assert request.nonce == "nonce-value"
        assert request.is_expired() is False

    def test_expired_request(self):
        """Test expired authorization request."""
        from enterprise_sso import AuthorizationRequest

        request = AuthorizationRequest(
            authorization_url="https://idp.example.com/authorize",
            state="abc123",
            expires_at=datetime.now(UTC) - timedelta(minutes=5),
        )
        assert request.is_expired() is True

    def test_pkce_values(self):
        """Test PKCE code verifier and challenge."""
        from enterprise_sso import AuthorizationRequest

        request = AuthorizationRequest(
            authorization_url="https://idp.example.com/authorize",
            state="abc123",
            code_verifier="verifier-value-abc123",
            code_challenge="challenge-value-xyz",
        )
        assert request.code_verifier == "verifier-value-abc123"
        assert request.code_challenge == "challenge-value-xyz"


class TestSAML2Handler:
    """Tests for SAML 2.0 protocol handler."""

    @pytest.fixture
    def saml_handler(self):
        """Create SAML handler for testing."""
        from enterprise_sso import SAML2Handler

        return SAML2Handler(
            entity_id="https://idp.example.com",
            sso_url="https://idp.example.com/sso",
            x509_certificate="test-certificate",
            sp_entity_id="urn:acgs2:test-sp",
        )

    def test_create_handler(self, saml_handler):
        """Test creating SAML handler."""
        assert saml_handler.entity_id == "https://idp.example.com"
        assert saml_handler.sso_url == "https://idp.example.com/sso"
        assert saml_handler.sp_entity_id == "urn:acgs2:test-sp"

    def test_constitutional_hash_validation(self):
        """Test that invalid constitutional hash raises error."""
        from enterprise_sso import SAML2Handler

        with pytest.raises(ValueError) as exc_info:
            SAML2Handler(
                entity_id="https://idp.example.com",
                sso_url="https://idp.example.com/sso",
                constitutional_hash="invalid-hash",
            )
        assert "Invalid constitutional hash" in str(exc_info.value)

    def test_create_authorization_request(self, saml_handler):
        """Test creating SAML AuthnRequest."""
        request = saml_handler.create_authorization_request(
            redirect_uri="https://sp.example.com/acs",
            state="test-state",
        )
        assert request.state == "test-state"
        assert "SAMLRequest" in request.authorization_url
        assert "RelayState" in request.authorization_url

    def test_generate_state(self, saml_handler):
        """Test state generation."""
        state1 = saml_handler.generate_state()
        state2 = saml_handler.generate_state()
        assert state1 != state2
        assert len(state1) >= 32

    async def test_validate_response_missing_saml_response(self, saml_handler):
        """Test validation with missing SAML response."""
        result = await saml_handler.validate_response({})
        assert result.success is False
        assert result.error_code == "MISSING_RESPONSE"

    async def test_validate_response_state_mismatch(self, saml_handler):
        """Test validation with state mismatch."""
        import base64

        saml_response = base64.b64encode(b"<samlp:Response></samlp:Response>").decode()
        result = await saml_handler.validate_response(
            {"SAMLResponse": saml_response, "RelayState": "wrong-state"},
            expected_state="expected-state",
        )
        assert result.success is False
        assert result.error_code == "STATE_MISMATCH"


class TestOIDCHandler:
    """Tests for OIDC protocol handler."""

    @pytest.fixture
    def oidc_handler(self):
        """Create OIDC handler for testing."""
        from enterprise_sso import OIDCHandler

        return OIDCHandler(
            issuer="https://auth.example.com",
            client_id="test-client-id",
            client_secret="test-client-secret",
            scopes=["openid", "profile", "email", "groups"],
            use_pkce=True,
        )

    def test_create_handler(self, oidc_handler):
        """Test creating OIDC handler."""
        assert oidc_handler.issuer == "https://auth.example.com"
        assert oidc_handler.client_id == "test-client-id"
        assert "openid" in oidc_handler.scopes
        assert oidc_handler.use_pkce is True

    def test_default_endpoints(self, oidc_handler):
        """Test default endpoint derivation from issuer."""
        assert "authorize" in oidc_handler.authorization_endpoint
        assert "token" in oidc_handler.token_endpoint
        assert "userinfo" in oidc_handler.userinfo_endpoint

    def test_constitutional_hash_validation(self):
        """Test that invalid constitutional hash raises error."""
        from enterprise_sso import OIDCHandler

        with pytest.raises(ValueError) as exc_info:
            OIDCHandler(
                issuer="https://auth.example.com",
                client_id="test-client",
                constitutional_hash="invalid-hash",
            )
        assert "Invalid constitutional hash" in str(exc_info.value)

    def test_create_authorization_request(self, oidc_handler):
        """Test creating OIDC authorization request."""
        request = oidc_handler.create_authorization_request(
            redirect_uri="https://app.example.com/callback",
        )
        assert request.state is not None
        assert request.nonce is not None
        assert request.code_verifier is not None  # PKCE enabled
        assert request.code_challenge is not None
        assert "client_id" in request.authorization_url
        assert "code_challenge" in request.authorization_url

    def test_authorization_request_without_pkce(self):
        """Test authorization request without PKCE."""
        from enterprise_sso import OIDCHandler

        handler = OIDCHandler(
            issuer="https://auth.example.com",
            client_id="test-client",
            use_pkce=False,
        )
        request = handler.create_authorization_request(
            redirect_uri="https://app.example.com/callback",
        )
        assert request.code_verifier is None
        assert request.code_challenge is None
        assert "code_challenge" not in request.authorization_url

    def test_generate_nonce(self, oidc_handler):
        """Test nonce generation."""
        nonce1 = oidc_handler.generate_nonce()
        nonce2 = oidc_handler.generate_nonce()
        assert nonce1 != nonce2
        assert len(nonce1) >= 32

    async def test_validate_response_error(self, oidc_handler):
        """Test validation with error response."""
        result = await oidc_handler.validate_response(
            {"error": "access_denied", "error_description": "User denied access"}
        )
        assert result.success is False
        assert result.error == "User denied access"
        assert result.error_code == "access_denied"

    async def test_validate_response_missing_code(self, oidc_handler):
        """Test validation with missing authorization code."""
        result = await oidc_handler.validate_response({"state": "test-state"})
        assert result.success is False
        assert result.error_code == "MISSING_CODE"

    async def test_validate_response_state_mismatch(self, oidc_handler):
        """Test validation with state mismatch."""
        result = await oidc_handler.validate_response(
            {"code": "auth-code", "state": "wrong-state"},
            expected_state="expected-state",
        )
        assert result.success is False
        assert result.error_code == "STATE_MISMATCH"


class TestProtocolHandlerFactory:
    """Tests for ProtocolHandlerFactory."""

    def test_create_saml_handler(self):
        """Test creating SAML handler via factory."""
        from enterprise_sso import ProtocolHandlerFactory, SAML2Handler

        handler = ProtocolHandlerFactory.create_saml_handler(
            entity_id="https://idp.example.com",
            sso_url="https://idp.example.com/sso",
            sp_entity_id="urn:acgs2:test-sp",
        )
        assert isinstance(handler, SAML2Handler)
        assert handler.entity_id == "https://idp.example.com"

    def test_create_oidc_handler(self):
        """Test creating OIDC handler via factory."""
        from enterprise_sso import OIDCHandler, ProtocolHandlerFactory

        handler = ProtocolHandlerFactory.create_oidc_handler(
            issuer="https://auth.example.com",
            client_id="test-client",
            client_secret="test-secret",
            use_pkce=True,
        )
        assert isinstance(handler, OIDCHandler)
        assert handler.issuer == "https://auth.example.com"
        assert handler.use_pkce is True


class TestPKCEGeneration:
    """Tests for PKCE code generation."""

    def test_code_verifier_length(self):
        """Test that code verifier has appropriate length."""
        from enterprise_sso import OIDCHandler

        verifier = OIDCHandler._generate_code_verifier()
        assert 43 <= len(verifier) <= 128

    def test_code_challenge_is_base64url(self):
        """Test that code challenge is base64url encoded."""
        from enterprise_sso import OIDCHandler

        verifier = OIDCHandler._generate_code_verifier()
        challenge = OIDCHandler._generate_code_challenge(verifier)
        # Base64url should not contain + or /
        assert "+" not in challenge
        assert "/" not in challenge

    def test_code_challenge_deterministic(self):
        """Test that same verifier produces same challenge."""
        from enterprise_sso import OIDCHandler

        verifier = "test-verifier-value"
        challenge1 = OIDCHandler._generate_code_challenge(verifier)
        challenge2 = OIDCHandler._generate_code_challenge(verifier)
        assert challenge1 == challenge2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
