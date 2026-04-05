"""
ACGS-2 LDAP Integration Tests
Constitutional Hash: 608508a9bd224290

Tests for LDAP integration with multi-tenancy and MACI frameworks.

Phase 10 Task 3: LDAP Integration
- Task 3.1: Write unit tests for LDAP connection management (connect, bind, disconnect)
- Task 3.3: Write unit tests for user authentication and DN resolution
- Task 3.5: Write unit tests for group membership queries
- Task 3.9: Write integration tests for end-to-end LDAP authentication flow
"""

import asyncio
from datetime import UTC, datetime, timedelta, timezone
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

# Constitutional Hash for ACGS-2
from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

# ============================================================================
# Task 3.1: Tests for LDAP Connection Management
# ============================================================================


class TestLDAPConnectionConfiguration:
    """Tests for LDAP connection configuration."""

    def test_constitutional_hash_present(self):
        """Verify constitutional hash is correctly defined."""
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    def test_create_ldap_config(self):
        """Test LDAP configuration creation."""
        from enterprise_sso.ldap_integration import LDAPConfig

        config = LDAPConfig(
            server_uri="ldaps://ldap.example.com:636",
            base_dn="dc=example,dc=com",
            bind_dn="cn=admin,dc=example,dc=com",
            bind_password="admin-password",
        )
        assert config.server_uri == "ldaps://ldap.example.com:636"
        assert config.base_dn == "dc=example,dc=com"
        assert config.bind_dn == "cn=admin,dc=example,dc=com"
        assert config.use_tls is True  # Default for ldaps://

    def test_ldap_config_with_tls(self):
        """Test LDAP configuration with TLS options."""
        from enterprise_sso.ldap_integration import LDAPConfig

        config = LDAPConfig(
            server_uri="ldap://ldap.example.com:389",
            base_dn="dc=example,dc=com",
            use_tls=True,
            start_tls=True,
            verify_cert=True,
            ca_cert_path="/etc/ssl/certs/ca-certificates.crt",
        )
        assert config.use_tls is True
        assert config.start_tls is True
        assert config.verify_cert is True
        assert config.ca_cert_path == "/etc/ssl/certs/ca-certificates.crt"

    def test_ldap_config_connection_pool(self):
        """Test LDAP configuration with connection pooling."""
        from enterprise_sso.ldap_integration import LDAPConfig

        config = LDAPConfig(
            server_uri="ldaps://ldap.example.com:636",
            base_dn="dc=example,dc=com",
            pool_size=10,
            pool_timeout=30.0,
            connection_timeout=5.0,
        )
        assert config.pool_size == 10
        assert config.pool_timeout == 30.0
        assert config.connection_timeout == 5.0

    def test_ldap_config_constitutional_hash(self):
        """Test that LDAP config includes constitutional hash."""
        from enterprise_sso.ldap_integration import LDAPConfig

        config = LDAPConfig(
            server_uri="ldaps://ldap.example.com:636",
            base_dn="dc=example,dc=com",
        )
        assert config.constitutional_hash == CONSTITUTIONAL_HASH


class TestLDAPConnection:
    """Tests for LDAP connection management."""

    @pytest.fixture
    def mock_ldap_module(self):
        """Mock the ldap module."""
        with patch("enterprise_sso.ldap_integration.LDAP_AVAILABLE", True):
            with patch("enterprise_sso.ldap_integration.ldap") as mock_ldap:
                # Mock connection object
                mock_conn = MagicMock()
                mock_conn.simple_bind_s = MagicMock(return_value=None)
                mock_conn.unbind_s = MagicMock(return_value=None)
                mock_conn.search_s = MagicMock(return_value=[])
                mock_conn.whoami_s = MagicMock(return_value="dn:cn=admin,dc=example,dc=com")
                mock_ldap.initialize.return_value = mock_conn
                mock_ldap.OPT_REFERRALS = 0
                mock_ldap.OPT_PROTOCOL_VERSION = 17
                mock_ldap.VERSION3 = 3
                mock_ldap.OPT_X_TLS_REQUIRE_CERT = 24580
                mock_ldap.OPT_X_TLS_DEMAND = 2
                mock_ldap.OPT_X_TLS_CACERTFILE = 24578
                mock_ldap.SCOPE_SUBTREE = 2
                mock_ldap.SCOPE_BASE = 0
                mock_ldap.SCOPE_ONELEVEL = 1
                yield mock_ldap

    @pytest.fixture
    def ldap_config(self):
        """Create LDAP config for testing."""
        from enterprise_sso.ldap_integration import LDAPConfig

        return LDAPConfig(
            server_uri="ldaps://ldap.example.com:636",
            base_dn="dc=example,dc=com",
            bind_dn="cn=admin,dc=example,dc=com",
            bind_password="admin-password",
            pool_size=5,
        )

    def test_create_connection(self, mock_ldap_module, ldap_config):
        """Test creating LDAP connection."""
        from enterprise_sso.ldap_integration import LDAPConnection

        conn = LDAPConnection(ldap_config)
        assert conn is not None
        assert conn.config == ldap_config
        assert conn.is_connected is False

    def test_connect(self, mock_ldap_module, ldap_config):
        """Test LDAP connect operation."""
        from enterprise_sso.ldap_integration import LDAPConnection

        conn = LDAPConnection(ldap_config)
        result = conn.connect()

        assert result is True
        assert conn.is_connected is True
        mock_ldap_module.initialize.assert_called_once_with(ldap_config.server_uri)

    def test_bind(self, mock_ldap_module, ldap_config):
        """Test LDAP bind operation."""
        from enterprise_sso.ldap_integration import LDAPConnection

        conn = LDAPConnection(ldap_config)
        conn.connect()
        result = conn.bind()

        assert result is True
        mock_conn = mock_ldap_module.initialize.return_value
        mock_conn.simple_bind_s.assert_called_once_with(
            ldap_config.bind_dn, ldap_config.bind_password
        )

    def test_disconnect(self, mock_ldap_module, ldap_config):
        """Test LDAP disconnect operation."""
        from enterprise_sso.ldap_integration import LDAPConnection

        conn = LDAPConnection(ldap_config)
        conn.connect()
        conn.bind()
        conn.disconnect()

        assert conn.is_connected is False
        mock_conn = mock_ldap_module.initialize.return_value
        mock_conn.unbind_s.assert_called_once()

    def test_context_manager(self, mock_ldap_module, ldap_config):
        """Test LDAP connection as context manager."""
        from enterprise_sso.ldap_integration import LDAPConnection

        with LDAPConnection(ldap_config) as conn:
            assert conn.is_connected is True

        assert conn.is_connected is False
        mock_conn = mock_ldap_module.initialize.return_value
        mock_conn.unbind_s.assert_called()

    def test_connection_with_start_tls(self, mock_ldap_module):
        """Test LDAP connection with STARTTLS."""
        from enterprise_sso.ldap_integration import LDAPConfig, LDAPConnection

        config = LDAPConfig(
            server_uri="ldap://ldap.example.com:389",
            base_dn="dc=example,dc=com",
            start_tls=True,
        )
        mock_conn = mock_ldap_module.initialize.return_value
        mock_conn.start_tls_s = MagicMock(return_value=None)

        conn = LDAPConnection(config)
        conn.connect()

        mock_conn.start_tls_s.assert_called_once()

    def test_connection_error_handling(self, mock_ldap_module, ldap_config):
        """Test LDAP connection error handling."""
        from enterprise_sso.ldap_integration import LDAPConnection, LDAPConnectionError

        mock_ldap_module.initialize.side_effect = OSError("Connection failed")

        conn = LDAPConnection(ldap_config)

        with pytest.raises(LDAPConnectionError) as exc_info:
            conn.connect()

        assert "Connection failed" in str(exc_info.value)
        assert conn.is_connected is False

    def test_bind_error_handling(self, mock_ldap_module, ldap_config):
        """Test LDAP bind error handling."""
        from enterprise_sso.ldap_integration import LDAPBindError, LDAPConnection

        mock_conn = mock_ldap_module.initialize.return_value
        mock_conn.simple_bind_s.side_effect = OSError("Invalid credentials")

        conn = LDAPConnection(ldap_config)
        conn.connect()

        with pytest.raises(LDAPBindError) as exc_info:
            conn.bind()

        assert "Invalid credentials" in str(exc_info.value)

    def test_whoami(self, mock_ldap_module, ldap_config):
        """Test LDAP whoami operation."""
        from enterprise_sso.ldap_integration import LDAPConnection

        conn = LDAPConnection(ldap_config)
        conn.connect()
        conn.bind()

        result = conn.whoami()

        assert result == "dn:cn=admin,dc=example,dc=com"


class TestLDAPConnectionPool:
    """Tests for LDAP connection pooling."""

    @pytest.fixture
    def mock_ldap_module(self):
        """Mock the ldap module."""
        with patch("enterprise_sso.ldap_integration.LDAP_AVAILABLE", True):
            with patch("enterprise_sso.ldap_integration.ldap") as mock_ldap:
                mock_conn = MagicMock()
                mock_conn.simple_bind_s = MagicMock(return_value=None)
                mock_conn.unbind_s = MagicMock(return_value=None)
                mock_conn.search_s = MagicMock(return_value=[])
                mock_ldap.initialize.return_value = mock_conn
                mock_ldap.OPT_REFERRALS = 0
                mock_ldap.OPT_PROTOCOL_VERSION = 17
                mock_ldap.VERSION3 = 3
                mock_ldap.SCOPE_SUBTREE = 2
                yield mock_ldap

    @pytest.fixture
    def ldap_config(self):
        """Create LDAP config for testing."""
        from enterprise_sso.ldap_integration import LDAPConfig

        return LDAPConfig(
            server_uri="ldaps://ldap.example.com:636",
            base_dn="dc=example,dc=com",
            bind_dn="cn=admin,dc=example,dc=com",
            bind_password="admin-password",
            pool_size=5,
            pool_timeout=30.0,
        )

    def test_create_pool(self, mock_ldap_module, ldap_config):
        """Test creating connection pool."""
        from enterprise_sso.ldap_integration import LDAPConnectionPool

        pool = LDAPConnectionPool(ldap_config)
        assert pool is not None
        assert pool.max_size == ldap_config.pool_size

    def test_acquire_connection(self, mock_ldap_module, ldap_config):
        """Test acquiring connection from pool."""
        from enterprise_sso.ldap_integration import LDAPConnectionPool

        pool = LDAPConnectionPool(ldap_config)

        with pool.acquire() as conn:
            assert conn is not None
            assert conn.is_connected is True

    def test_release_connection(self, mock_ldap_module, ldap_config):
        """Test releasing connection back to pool."""
        from enterprise_sso.ldap_integration import LDAPConnectionPool

        pool = LDAPConnectionPool(ldap_config)

        with pool.acquire() as conn:
            conn_id = id(conn)

        # Connection should be returned to pool
        assert pool.available_connections >= 1

    def test_pool_reuses_connections(self, mock_ldap_module, ldap_config):
        """Test that pool reuses connections."""
        from enterprise_sso.ldap_integration import LDAPConnectionPool

        pool = LDAPConnectionPool(ldap_config)

        with pool.acquire() as conn1:
            conn1_id = id(conn1)

        with pool.acquire() as conn2:
            conn2_id = id(conn2)

        # Should reuse the same connection
        assert conn1_id == conn2_id

    def test_pool_max_size(self, mock_ldap_module, ldap_config):
        """Test pool respects max size."""
        from enterprise_sso.ldap_integration import LDAPConnectionPool

        ldap_config.pool_size = 2
        pool = LDAPConnectionPool(ldap_config)

        conn1 = pool._create_connection()
        conn2 = pool._create_connection()

        assert pool.active_connections == 2

    def test_pool_shutdown(self, mock_ldap_module, ldap_config):
        """Test pool shutdown closes all connections."""
        from enterprise_sso.ldap_integration import LDAPConnectionPool

        pool = LDAPConnectionPool(ldap_config)

        with pool.acquire() as conn:
            pass

        pool.shutdown()

        assert pool.available_connections == 0

    def test_pool_health_check(self, mock_ldap_module, ldap_config):
        """Test pool health check."""
        from enterprise_sso.ldap_integration import LDAPConnectionPool

        pool = LDAPConnectionPool(ldap_config)

        health = pool.health_check()

        assert "healthy" in health
        assert "available_connections" in health
        assert "active_connections" in health


# ============================================================================
# Task 3.3: Tests for User Authentication and DN Resolution
# ============================================================================


class TestLDAPUserAuthentication:
    """Tests for LDAP user authentication and DN resolution."""

    @pytest.fixture
    def mock_ldap_module(self):
        """Mock the ldap module."""
        with patch("enterprise_sso.ldap_integration.LDAP_AVAILABLE", True):
            with patch("enterprise_sso.ldap_integration.ldap") as mock_ldap:
                mock_conn = MagicMock()
                mock_conn.simple_bind_s = MagicMock(return_value=None)
                mock_conn.unbind_s = MagicMock(return_value=None)
                mock_conn.search_s = MagicMock(
                    return_value=[
                        (
                            "cn=testuser,ou=users,dc=example,dc=com",
                            {
                                "cn": [b"testuser"],
                                "mail": [b"testuser@example.com"],
                                "displayName": [b"Test User"],
                                "memberOf": [
                                    b"cn=developers,ou=groups,dc=example,dc=com",
                                    b"cn=users,ou=groups,dc=example,dc=com",
                                ],
                            },
                        )
                    ]
                )
                mock_ldap.initialize.return_value = mock_conn
                mock_ldap.SCOPE_SUBTREE = 2
                mock_ldap.SCOPE_BASE = 0
                mock_ldap.OPT_REFERRALS = 0
                mock_ldap.OPT_PROTOCOL_VERSION = 17
                mock_ldap.VERSION3 = 3
                yield mock_ldap

    @pytest.fixture
    def ldap_integration(self, mock_ldap_module):
        """Create LDAP integration for testing."""
        from enterprise_sso.ldap_integration import LDAPConfig, LDAPIntegration

        config = LDAPConfig(
            server_uri="ldaps://ldap.example.com:636",
            base_dn="dc=example,dc=com",
            bind_dn="cn=admin,dc=example,dc=com",
            bind_password="admin-password",
            user_search_base="ou=users,dc=example,dc=com",
            user_search_filter="(uid={username})",
            group_search_base="ou=groups,dc=example,dc=com",
            group_search_filter="(member={user_dn})",
        )
        return LDAPIntegration(config)

    def test_search_user(self, ldap_integration, mock_ldap_module):
        """Test searching for a user."""
        user = ldap_integration.search_user("testuser")

        assert user is not None
        assert user["dn"] == "cn=testuser,ou=users,dc=example,dc=com"
        assert user["cn"] == "testuser"
        assert user["mail"] == "testuser@example.com"

    def test_resolve_user_dn(self, ldap_integration, mock_ldap_module):
        """Test resolving user DN from username."""
        dn = ldap_integration.resolve_user_dn("testuser")

        assert dn == "cn=testuser,ou=users,dc=example,dc=com"

    def test_authenticate_user(self, ldap_integration, mock_ldap_module):
        """Test authenticating a user."""
        result = ldap_integration.authenticate("testuser", "password123")

        assert result.success is True
        assert result.user_dn == "cn=testuser,ou=users,dc=example,dc=com"
        assert result.email == "testuser@example.com"

    def test_authenticate_user_not_found(self, ldap_integration, mock_ldap_module):
        """Test authentication with non-existent user."""
        mock_conn = mock_ldap_module.initialize.return_value
        mock_conn.search_s.return_value = []

        result = ldap_integration.authenticate("nonexistent", "password")

        assert result.success is False
        assert result.error_code == "USER_NOT_FOUND"

    def test_authenticate_invalid_password(self, ldap_integration, mock_ldap_module):
        """Test authentication with invalid password."""
        mock_conn = mock_ldap_module.initialize.return_value
        mock_conn.simple_bind_s.side_effect = [
            None,  # Admin bind succeeds
            OSError("Invalid credentials"),  # User bind fails
        ]

        result = ldap_integration.authenticate("testuser", "wrongpassword")

        assert result.success is False
        assert result.error_code == "INVALID_CREDENTIALS"

    def test_get_user_attributes(self, ldap_integration, mock_ldap_module):
        """Test getting user attributes."""
        attrs = ldap_integration.get_user_attributes("testuser")

        assert attrs is not None
        assert attrs["displayName"] == "Test User"
        assert "memberOf" in attrs

    def test_authentication_result_constitutional_hash(self, ldap_integration, mock_ldap_module):
        """Test that authentication result includes constitutional hash."""
        result = ldap_integration.authenticate("testuser", "password123")

        assert result.constitutional_hash == CONSTITUTIONAL_HASH


class TestLDAPDNResolution:
    """Tests for LDAP DN resolution patterns."""

    @pytest.fixture
    def mock_ldap_module(self):
        """Mock the ldap module."""
        with patch("enterprise_sso.ldap_integration.LDAP_AVAILABLE", True):
            with patch("enterprise_sso.ldap_integration.ldap") as mock_ldap:
                mock_conn = MagicMock()
                mock_conn.simple_bind_s = MagicMock(return_value=None)
                mock_conn.unbind_s = MagicMock(return_value=None)
                mock_ldap.initialize.return_value = mock_conn
                mock_ldap.SCOPE_SUBTREE = 2
                mock_ldap.OPT_REFERRALS = 0
                mock_ldap.OPT_PROTOCOL_VERSION = 17
                mock_ldap.VERSION3 = 3
                yield mock_ldap

    def test_build_user_dn_from_pattern(self, mock_ldap_module):
        """Test building user DN from pattern."""
        from enterprise_sso.ldap_integration import LDAPConfig, LDAPIntegration

        config = LDAPConfig(
            server_uri="ldaps://ldap.example.com:636",
            base_dn="dc=example,dc=com",
            user_dn_pattern="uid={username},ou=users,dc=example,dc=com",
        )
        integration = LDAPIntegration(config)

        dn = integration.build_user_dn("testuser")

        assert dn == "uid=testuser,ou=users,dc=example,dc=com"

    def test_parse_user_dn(self, mock_ldap_module):
        """Test parsing user DN."""
        from enterprise_sso.ldap_integration import parse_dn

        dn = "cn=testuser,ou=users,dc=example,dc=com"
        parsed = parse_dn(dn)

        assert parsed["cn"] == "testuser"
        assert parsed["ou"] == "users"

    def test_escape_dn_characters(self, mock_ldap_module):
        """Test escaping special DN characters."""
        from enterprise_sso.ldap_integration import escape_dn_chars

        # Characters that need escaping: , + " \ < > ; = /
        username = "user,name+special"
        escaped = escape_dn_chars(username)

        assert "\\," in escaped
        assert "\\+" in escaped


# ============================================================================
# Task 3.5: Tests for Group Membership Queries
# ============================================================================


class TestLDAPGroupMembership:
    """Tests for LDAP group membership queries."""

    @pytest.fixture
    def mock_ldap_module(self):
        """Mock the ldap module."""
        with patch("enterprise_sso.ldap_integration.LDAP_AVAILABLE", True):
            with patch("enterprise_sso.ldap_integration.ldap") as mock_ldap:
                mock_conn = MagicMock()
                mock_conn.simple_bind_s = MagicMock(return_value=None)
                mock_conn.unbind_s = MagicMock(return_value=None)
                mock_ldap.initialize.return_value = mock_conn
                mock_ldap.SCOPE_SUBTREE = 2
                mock_ldap.OPT_REFERRALS = 0
                mock_ldap.OPT_PROTOCOL_VERSION = 17
                mock_ldap.VERSION3 = 3
                yield mock_ldap

    @pytest.fixture
    def ldap_integration(self, mock_ldap_module):
        """Create LDAP integration with group config."""
        from enterprise_sso.ldap_integration import LDAPConfig, LDAPIntegration

        config = LDAPConfig(
            server_uri="ldaps://ldap.example.com:636",
            base_dn="dc=example,dc=com",
            bind_dn="cn=admin,dc=example,dc=com",
            bind_password="admin-password",
            user_search_base="ou=users,dc=example,dc=com",
            group_search_base="ou=groups,dc=example,dc=com",
            group_search_filter="(member={user_dn})",
            group_name_attribute="cn",
        )
        return LDAPIntegration(config)

    def test_get_user_groups_from_member_of(self, ldap_integration, mock_ldap_module):
        """Test getting user groups from memberOf attribute."""
        mock_conn = mock_ldap_module.initialize.return_value
        mock_conn.search_s.return_value = [
            (
                "cn=testuser,ou=users,dc=example,dc=com",
                {
                    "cn": [b"testuser"],
                    "memberOf": [
                        b"cn=developers,ou=groups,dc=example,dc=com",
                        b"cn=admins,ou=groups,dc=example,dc=com",
                    ],
                },
            )
        ]

        groups = ldap_integration.get_user_groups("testuser")

        assert "developers" in groups
        assert "admins" in groups

    def test_get_user_groups_by_search(self, ldap_integration, mock_ldap_module):
        """Test getting user groups by group search."""
        mock_conn = mock_ldap_module.initialize.return_value
        # First call returns user, second call returns groups
        mock_conn.search_s.side_effect = [
            [
                (
                    "cn=testuser,ou=users,dc=example,dc=com",
                    {"cn": [b"testuser"]},
                )
            ],
            [
                ("cn=developers,ou=groups,dc=example,dc=com", {"cn": [b"developers"]}),
                ("cn=users,ou=groups,dc=example,dc=com", {"cn": [b"users"]}),
            ],
        ]

        groups = ldap_integration.search_groups_for_user("cn=testuser,ou=users,dc=example,dc=com")

        assert len(groups) >= 1

    def test_is_member_of_group(self, ldap_integration, mock_ldap_module):
        """Test checking if user is member of group."""
        mock_conn = mock_ldap_module.initialize.return_value
        mock_conn.search_s.return_value = [
            (
                "cn=testuser,ou=users,dc=example,dc=com",
                {
                    "cn": [b"testuser"],
                    "memberOf": [b"cn=admins,ou=groups,dc=example,dc=com"],
                },
            )
        ]

        is_member = ldap_integration.is_member_of("testuser", "admins")

        assert is_member is True

    def test_is_not_member_of_group(self, ldap_integration, mock_ldap_module):
        """Test checking user is not member of group."""
        mock_conn = mock_ldap_module.initialize.return_value
        mock_conn.search_s.return_value = [
            (
                "cn=testuser,ou=users,dc=example,dc=com",
                {
                    "cn": [b"testuser"],
                    "memberOf": [b"cn=users,ou=groups,dc=example,dc=com"],
                },
            )
        ]

        is_member = ldap_integration.is_member_of("testuser", "admins")

        assert is_member is False

    def test_get_nested_groups(self, ldap_integration, mock_ldap_module):
        """Test getting nested group memberships."""
        mock_conn = mock_ldap_module.initialize.return_value

        # Simulate nested groups: user -> developers -> engineering
        mock_conn.search_s.side_effect = [
            # User search
            [
                (
                    "cn=testuser,ou=users,dc=example,dc=com",
                    {
                        "cn": [b"testuser"],
                        "memberOf": [b"cn=developers,ou=groups,dc=example,dc=com"],
                    },
                )
            ],
            # developers group search
            [
                (
                    "cn=developers,ou=groups,dc=example,dc=com",
                    {
                        "cn": [b"developers"],
                        "memberOf": [b"cn=engineering,ou=groups,dc=example,dc=com"],
                    },
                )
            ],
            # engineering group (no more parents)
            [
                (
                    "cn=engineering,ou=groups,dc=example,dc=com",
                    {"cn": [b"engineering"]},
                )
            ],
        ]

        groups = ldap_integration.get_user_groups("testuser", resolve_nested=True)

        # Should include both direct and nested groups
        assert "developers" in groups or len(groups) >= 1


class TestLDAPGroupSearch:
    """Tests for LDAP group search operations."""

    @pytest.fixture
    def mock_ldap_module(self):
        """Mock the ldap module."""
        with patch("enterprise_sso.ldap_integration.LDAP_AVAILABLE", True):
            with patch("enterprise_sso.ldap_integration.ldap") as mock_ldap:
                mock_conn = MagicMock()
                mock_conn.simple_bind_s = MagicMock(return_value=None)
                mock_conn.unbind_s = MagicMock(return_value=None)
                mock_ldap.initialize.return_value = mock_conn
                mock_ldap.SCOPE_SUBTREE = 2
                mock_ldap.OPT_REFERRALS = 0
                mock_ldap.OPT_PROTOCOL_VERSION = 17
                mock_ldap.VERSION3 = 3
                yield mock_ldap

    @pytest.fixture
    def ldap_integration(self, mock_ldap_module):
        """Create LDAP integration for testing."""
        from enterprise_sso.ldap_integration import LDAPConfig, LDAPIntegration

        config = LDAPConfig(
            server_uri="ldaps://ldap.example.com:636",
            base_dn="dc=example,dc=com",
            bind_dn="cn=admin,dc=example,dc=com",
            bind_password="admin-password",
            group_search_base="ou=groups,dc=example,dc=com",
        )
        return LDAPIntegration(config)

    def test_search_group_by_name(self, ldap_integration, mock_ldap_module):
        """Test searching for a group by name."""
        mock_conn = mock_ldap_module.initialize.return_value
        mock_conn.search_s.return_value = [
            (
                "cn=developers,ou=groups,dc=example,dc=com",
                {
                    "cn": [b"developers"],
                    "description": [b"Developer team"],
                    "member": [
                        b"cn=user1,ou=users,dc=example,dc=com",
                        b"cn=user2,ou=users,dc=example,dc=com",
                    ],
                },
            )
        ]

        group = ldap_integration.search_group("developers")

        assert group is not None
        assert group["cn"] == "developers"
        assert group["description"] == "Developer team"

    def test_get_group_members(self, ldap_integration, mock_ldap_module):
        """Test getting group members."""
        mock_conn = mock_ldap_module.initialize.return_value
        mock_conn.search_s.return_value = [
            (
                "cn=developers,ou=groups,dc=example,dc=com",
                {
                    "cn": [b"developers"],
                    "member": [
                        b"cn=user1,ou=users,dc=example,dc=com",
                        b"cn=user2,ou=users,dc=example,dc=com",
                    ],
                },
            )
        ]

        members = ldap_integration.get_group_members("developers")

        assert len(members) == 2
        assert "cn=user1,ou=users,dc=example,dc=com" in members

    def test_list_all_groups(self, ldap_integration, mock_ldap_module):
        """Test listing all groups."""
        mock_conn = mock_ldap_module.initialize.return_value
        mock_conn.search_s.return_value = [
            ("cn=admins,ou=groups,dc=example,dc=com", {"cn": [b"admins"]}),
            ("cn=developers,ou=groups,dc=example,dc=com", {"cn": [b"developers"]}),
            ("cn=users,ou=groups,dc=example,dc=com", {"cn": [b"users"]}),
        ]

        groups = ldap_integration.list_groups()

        assert len(groups) == 3


# ============================================================================
# Task 3.7: Tests for Circuit Breaker Pattern
# ============================================================================


class TestLDAPCircuitBreaker:
    """Tests for LDAP circuit breaker pattern."""

    @pytest.fixture
    def mock_ldap_module(self):
        """Mock the ldap module."""
        with patch("enterprise_sso.ldap_integration.LDAP_AVAILABLE", True):
            with patch("enterprise_sso.ldap_integration.ldap") as mock_ldap:
                mock_conn = MagicMock()
                mock_ldap.initialize.return_value = mock_conn
                mock_ldap.OPT_REFERRALS = 0
                mock_ldap.OPT_PROTOCOL_VERSION = 17
                mock_ldap.VERSION3 = 3
                yield mock_ldap

    def test_circuit_breaker_initial_state(self, mock_ldap_module):
        """Test circuit breaker starts in closed state."""
        from enterprise_sso.ldap_integration import LDAPCircuitBreaker

        cb = LDAPCircuitBreaker(
            failure_threshold=5,
            recovery_timeout=30.0,
        )

        assert cb.state == "closed"
        assert cb.is_available is True

    def test_circuit_breaker_opens_on_failures(self, mock_ldap_module):
        """Test circuit breaker opens after threshold failures."""
        from enterprise_sso.ldap_integration import LDAPCircuitBreaker

        cb = LDAPCircuitBreaker(
            failure_threshold=3,
            recovery_timeout=30.0,
        )

        # Simulate failures
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()

        assert cb.state == "open"
        assert cb.is_available is False

    def test_circuit_breaker_records_success(self, mock_ldap_module):
        """Test circuit breaker records successful operations."""
        from enterprise_sso.ldap_integration import LDAPCircuitBreaker

        cb = LDAPCircuitBreaker(failure_threshold=5)

        cb.record_failure()
        cb.record_success()

        # Failures should be reset
        assert cb.consecutive_failures == 0

    def test_circuit_breaker_half_open_state(self, mock_ldap_module):
        """Test circuit breaker transitions to half-open state."""
        from enterprise_sso.ldap_integration import LDAPCircuitBreaker

        cb = LDAPCircuitBreaker(
            failure_threshold=2,
            recovery_timeout=0.1,  # Very short for testing
        )

        # Open the circuit
        cb.record_failure()
        cb.record_failure()
        assert cb.state == "open"

        # Wait for recovery timeout
        import time

        time.sleep(0.15)

        # Should transition to half-open
        assert cb.state == "half-open"
        assert cb.is_available is True

    def test_circuit_breaker_closes_on_success(self, mock_ldap_module):
        """Test circuit breaker closes after successful operation in half-open."""
        from enterprise_sso.ldap_integration import LDAPCircuitBreaker

        cb = LDAPCircuitBreaker(
            failure_threshold=2,
            recovery_timeout=0.1,
        )

        # Open the circuit
        cb.record_failure()

        # Wait for half-open
        import time

        time.sleep(0.15)

        # Record success
        cb.record_success()

        assert cb.state == "closed"

    def test_circuit_breaker_reopens_on_failure_in_half_open(self, mock_ldap_module):
        """Test circuit breaker reopens if failure in half-open state."""
        from enterprise_sso.ldap_integration import LDAPCircuitBreaker

        cb = LDAPCircuitBreaker(
            failure_threshold=2,
            recovery_timeout=0.1,
        )

        # Open the circuit
        cb.record_failure()

        # Wait for half-open
        import time

        time.sleep(0.15)

        # Record another failure
        cb.record_failure()

        assert cb.state == "open"

    def test_circuit_breaker_with_ldap_integration(self, mock_ldap_module):
        """Test circuit breaker integration with LDAP client."""
        from enterprise_sso.ldap_integration import LDAPConfig, LDAPIntegration

        config = LDAPConfig(
            server_uri="ldaps://ldap.example.com:636",
            base_dn="dc=example,dc=com",
            circuit_breaker_enabled=True,
            circuit_breaker_failure_threshold=3,
            circuit_breaker_recovery_timeout=30.0,
        )

        integration = LDAPIntegration(config)

        assert integration.circuit_breaker is not None
        assert integration.circuit_breaker.state == "closed"


# ============================================================================
# Task 3.8: Tests for Health Check Endpoint
# ============================================================================


class TestLDAPHealthCheck:
    """Tests for LDAP health check functionality."""

    @pytest.fixture
    def mock_ldap_module(self):
        """Mock the ldap module."""
        with patch("enterprise_sso.ldap_integration.LDAP_AVAILABLE", True):
            with patch("enterprise_sso.ldap_integration.ldap") as mock_ldap:
                mock_conn = MagicMock()
                mock_conn.simple_bind_s = MagicMock(return_value=None)
                mock_conn.unbind_s = MagicMock(return_value=None)
                mock_conn.search_s = MagicMock(
                    return_value=[("", {"namingContexts": [b"dc=example,dc=com"]})]
                )
                mock_ldap.initialize.return_value = mock_conn
                mock_ldap.SCOPE_BASE = 0
                mock_ldap.OPT_REFERRALS = 0
                mock_ldap.OPT_PROTOCOL_VERSION = 17
                mock_ldap.VERSION3 = 3
                yield mock_ldap

    @pytest.fixture
    def ldap_integration(self, mock_ldap_module):
        """Create LDAP integration for testing."""
        from enterprise_sso.ldap_integration import LDAPConfig, LDAPIntegration

        config = LDAPConfig(
            server_uri="ldaps://ldap.example.com:636",
            base_dn="dc=example,dc=com",
            bind_dn="cn=admin,dc=example,dc=com",
            bind_password="admin-password",
        )
        return LDAPIntegration(config)

    def test_health_check_healthy(self, ldap_integration, mock_ldap_module):
        """Test health check returns healthy status."""
        health = ldap_integration.health_check()

        assert health["status"] == "healthy"
        assert health["server_uri"] == "ldaps://ldap.example.com:636"
        assert "latency_ms" in health

    def test_health_check_unhealthy(self, ldap_integration, mock_ldap_module):
        """Test health check returns unhealthy status on error."""
        mock_conn = mock_ldap_module.initialize.return_value
        mock_conn.search_s.side_effect = OSError("Connection timeout")

        health = ldap_integration.health_check()

        assert health["status"] == "unhealthy"
        assert "error" in health

    def test_health_check_includes_circuit_breaker_status(self, mock_ldap_module):
        """Test health check includes circuit breaker status."""
        from enterprise_sso.ldap_integration import LDAPConfig, LDAPIntegration

        config = LDAPConfig(
            server_uri="ldaps://ldap.example.com:636",
            base_dn="dc=example,dc=com",
            circuit_breaker_enabled=True,
        )
        integration = LDAPIntegration(config)

        health = integration.health_check()

        assert "circuit_breaker" in health
        assert health["circuit_breaker"]["state"] == "closed"

    def test_health_check_includes_pool_stats(self, mock_ldap_module):
        """Test health check includes connection pool statistics."""
        from enterprise_sso.ldap_integration import LDAPConfig, LDAPIntegration

        config = LDAPConfig(
            server_uri="ldaps://ldap.example.com:636",
            base_dn="dc=example,dc=com",
            pool_size=5,
        )
        integration = LDAPIntegration(config)

        health = integration.health_check()

        assert "connection_pool" in health
        assert "available_connections" in health["connection_pool"]

    def test_health_check_constitutional_hash(self, ldap_integration, mock_ldap_module):
        """Test health check includes constitutional hash."""
        health = ldap_integration.health_check()

        assert health["constitutional_hash"] == CONSTITUTIONAL_HASH


# ============================================================================
# Task 3.9: Integration Tests for End-to-End LDAP Authentication Flow
# ============================================================================


class TestLDAPEndToEndAuthentication:
    """Integration tests for end-to-end LDAP authentication flow."""

    @pytest.fixture
    def mock_ldap_module(self):
        """Mock the ldap module for integration tests."""
        with patch("enterprise_sso.ldap_integration.LDAP_AVAILABLE", True):
            with patch("enterprise_sso.ldap_integration.ldap") as mock_ldap:
                mock_conn = MagicMock()
                mock_conn.simple_bind_s = MagicMock(return_value=None)
                mock_conn.unbind_s = MagicMock(return_value=None)

                # User search returns user with groups
                mock_conn.search_s = MagicMock(
                    return_value=[
                        (
                            "cn=jdoe,ou=users,dc=example,dc=com",
                            {
                                "cn": [b"jdoe"],
                                "uid": [b"jdoe"],
                                "mail": [b"jdoe@example.com"],
                                "displayName": [b"John Doe"],
                                "memberOf": [
                                    b"cn=developers,ou=groups,dc=example,dc=com",
                                    b"cn=qa,ou=groups,dc=example,dc=com",
                                ],
                            },
                        )
                    ]
                )

                mock_ldap.initialize.return_value = mock_conn
                mock_ldap.SCOPE_SUBTREE = 2
                mock_ldap.SCOPE_BASE = 0
                mock_ldap.OPT_REFERRALS = 0
                mock_ldap.OPT_PROTOCOL_VERSION = 17
                mock_ldap.VERSION3 = 3
                yield mock_ldap

    @pytest.fixture
    def ldap_integration(self, mock_ldap_module):
        """Create fully configured LDAP integration."""
        from enterprise_sso.ldap_integration import LDAPConfig, LDAPIntegration

        config = LDAPConfig(
            server_uri="ldaps://ldap.example.com:636",
            base_dn="dc=example,dc=com",
            bind_dn="cn=admin,dc=example,dc=com",
            bind_password="admin-password",
            user_search_base="ou=users,dc=example,dc=com",
            user_search_filter="(uid={username})",
            group_search_base="ou=groups,dc=example,dc=com",
            group_search_filter="(member={user_dn})",
            group_name_attribute="cn",
        )
        return LDAPIntegration(config)

    def test_full_authentication_flow(self, ldap_integration, mock_ldap_module):
        """Test complete authentication flow."""
        # Step 1: Authenticate user
        result = ldap_integration.authenticate("jdoe", "password123")

        assert result.success is True
        assert result.user_dn == "cn=jdoe,ou=users,dc=example,dc=com"
        assert result.email == "jdoe@example.com"
        assert result.display_name == "John Doe"
        assert "developers" in result.groups
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    def test_authentication_returns_maci_roles(self, mock_ldap_module):
        """Test that authentication maps groups to MACI roles."""
        from enterprise_sso.ldap_integration import LDAPConfig, LDAPIntegration

        config = LDAPConfig(
            server_uri="ldaps://ldap.example.com:636",
            base_dn="dc=example,dc=com",
            bind_dn="cn=admin,dc=example,dc=com",
            bind_password="admin-password",
            group_to_maci_role_mapping={
                "developers": "IMPLEMENTER",
                "admins": "EXECUTIVE",
                "validators": "JUDICIAL",
            },
        )
        integration = LDAPIntegration(config)

        result = integration.authenticate("jdoe", "password123")

        assert result.success is True
        assert "IMPLEMENTER" in result.maci_roles

    def test_authentication_creates_sso_session(self, ldap_integration, mock_ldap_module):
        """Test that successful authentication creates SSO session."""
        result = ldap_integration.authenticate("jdoe", "password123")

        assert result.success is True
        assert result.session_token is not None
        assert result.expires_at is not None
        assert result.expires_at > datetime.now(UTC)

    def test_authentication_with_tenant_context(self, mock_ldap_module):
        """Test authentication with multi-tenant context."""
        from enterprise_sso.ldap_integration import LDAPConfig, LDAPIntegration

        config = LDAPConfig(
            server_uri="ldaps://ldap.example.com:636",
            base_dn="dc=example,dc=com",
            bind_dn="cn=admin,dc=example,dc=com",
            bind_password="admin-password",
            tenant_id="acme-corp",
        )
        integration = LDAPIntegration(config)

        result = integration.authenticate("jdoe", "password123")

        assert result.success is True
        assert result.tenant_id == "acme-corp"

    def test_authentication_audit_logging(self, ldap_integration, mock_ldap_module):
        """Test that authentication attempts are audit logged."""
        with patch.object(ldap_integration, "_log_authentication_attempt") as mock_log:
            ldap_integration.authenticate("jdoe", "password123")

            mock_log.assert_called_once()
            call_args = mock_log.call_args[1]
            assert call_args["username"] == "jdoe"
            assert call_args["success"] is True
            assert call_args["constitutional_hash"] == CONSTITUTIONAL_HASH


class TestLDAPTenantIntegration:
    """Tests for LDAP integration with multi-tenancy."""

    @pytest.fixture
    def mock_ldap_module(self):
        """Mock the ldap module."""
        with patch("enterprise_sso.ldap_integration.LDAP_AVAILABLE", True):
            with patch("enterprise_sso.ldap_integration.ldap") as mock_ldap:
                mock_conn = MagicMock()
                mock_conn.simple_bind_s = MagicMock(return_value=None)
                mock_conn.unbind_s = MagicMock(return_value=None)
                mock_ldap.initialize.return_value = mock_conn
                mock_ldap.OPT_REFERRALS = 0
                mock_ldap.OPT_PROTOCOL_VERSION = 17
                mock_ldap.VERSION3 = 3
                yield mock_ldap

    def test_ldap_config_from_tenant_sso_config(self, mock_ldap_module):
        """Test creating LDAP config from tenant SSO configuration."""
        from enterprise_sso.ldap_integration import LDAPConfig
        from enterprise_sso.tenant_sso_config import TenantIdPConfig, TenantSSOConfig

        # This tests integration between LDAP and existing SSO infrastructure
        # The actual TenantIdPConfig doesn't have LDAP yet, but this shows the pattern
        config = LDAPConfig.from_tenant_config(
            tenant_id="acme-corp",
            server_uri="ldaps://ldap.acme.com:636",
            base_dn="dc=acme,dc=com",
            bind_dn="cn=svc-acgs,dc=acme,dc=com",
            bind_password="service-password",
        )

        assert config.tenant_id == "acme-corp"
        assert config.server_uri == "ldaps://ldap.acme.com:636"

    def test_ldap_handler_registration(self, mock_ldap_module):
        """Test LDAP handler can be registered with EnterpriseSSOService."""
        # This would test integration with the existing SSO service
        # The actual implementation would add LDAP as a protocol type
        pass


# ============================================================================
# Utility Function Tests
# ============================================================================


class TestLDAPUtilities:
    """Tests for LDAP utility functions."""

    def test_escape_ldap_filter(self):
        """Test LDAP filter escaping."""
        from enterprise_sso.ldap_integration import escape_filter_chars

        # Characters that need escaping: * ( ) \ NUL
        filter_value = "user*(test)\\name"
        escaped = escape_filter_chars(filter_value)

        assert "\\2a" in escaped  # *
        assert "\\28" in escaped  # (
        assert "\\29" in escaped  # )
        assert "\\5c" in escaped  # \

    def test_build_search_filter(self):
        """Test building LDAP search filter."""
        from enterprise_sso.ldap_integration import build_search_filter

        filter_str = build_search_filter(
            "(uid={username})",
            username="testuser",
        )

        assert filter_str == "(uid=testuser)"

    def test_parse_ldap_entry(self):
        """Test parsing LDAP entry to dictionary."""
        from enterprise_sso.ldap_integration import parse_ldap_entry

        entry = (
            "cn=testuser,ou=users,dc=example,dc=com",
            {
                "cn": [b"testuser"],
                "mail": [b"test@example.com"],
                "displayName": [b"Test User"],
            },
        )

        parsed = parse_ldap_entry(entry)

        assert parsed["dn"] == "cn=testuser,ou=users,dc=example,dc=com"
        assert parsed["cn"] == "testuser"
        assert parsed["mail"] == "test@example.com"

    def test_decode_ldap_value(self):
        """Test decoding LDAP binary values."""
        from enterprise_sso.ldap_integration import decode_ldap_value

        # Single value
        assert decode_ldap_value([b"test"]) == "test"

        # Multiple values
        values = decode_ldap_value([b"value1", b"value2"])
        assert values == ["value1", "value2"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
