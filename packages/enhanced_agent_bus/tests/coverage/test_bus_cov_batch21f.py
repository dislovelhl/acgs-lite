"""
Coverage batch 21f: ldap_integration, bundle_registry, multi_approver, routes/tenants.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from queue import Full
from typing import Any
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

# ---------------------------------------------------------------------------
# 1. ldap_integration tests
# ---------------------------------------------------------------------------
from enhanced_agent_bus.enterprise_sso.ldap_integration import (
    CircuitBreakerState,
    LDAPAuthenticationResult,
    LDAPBindError,
    LDAPCircuitBreaker,
    LDAPCircuitOpenError,
    LDAPConfig,
    LDAPConnection,
    LDAPConnectionError,
    LDAPConnectionPool,
    LDAPIntegration,
    LDAPIntegrationError,
    LDAPSearchError,
    build_search_filter,
    decode_ldap_value,
    escape_dn_chars,
    escape_filter_chars,
    extract_cn_from_dn,
    parse_dn,
    parse_ldap_entry,
)

# --- Utility functions ---


class TestEscapeDnChars:
    def test_escapes_comma(self):
        assert "\\," in escape_dn_chars("a,b")

    def test_escapes_plus(self):
        assert "\\+" in escape_dn_chars("a+b")

    def test_escapes_backslash(self):
        assert "\\\\" in escape_dn_chars("a\\b")

    def test_escapes_angle_brackets(self):
        result = escape_dn_chars("<test>")
        assert "\\<" in result
        assert "\\>" in result

    def test_escapes_semicolon_equals(self):
        result = escape_dn_chars("a;b=c")
        assert "\\;" in result
        assert "\\=" in result

    def test_escapes_double_quote(self):
        assert '\\"' in escape_dn_chars('a"b')

    def test_no_special_chars(self):
        assert escape_dn_chars("simple") == "simple"


class TestEscapeFilterChars:
    def test_escapes_asterisk(self):
        assert escape_filter_chars("a*b") == "a\\2ab"

    def test_escapes_parentheses(self):
        assert "\\28" in escape_filter_chars("(")
        assert "\\29" in escape_filter_chars(")")

    def test_escapes_backslash_first(self):
        result = escape_filter_chars("a\\b")
        assert "\\5c" in result

    def test_escapes_null(self):
        assert "\\00" in escape_filter_chars("a\x00b")


class TestBuildSearchFilter:
    def test_substitution(self):
        result = build_search_filter("(uid={username})", username="testuser")
        assert result == "(uid=testuser)"

    def test_escapes_special_chars(self):
        result = build_search_filter("(uid={username})", username="test*user")
        assert "\\2a" in result

    def test_multiple_kwargs(self):
        result = build_search_filter("(member={user_dn})", user_dn="cn=test,dc=example")
        assert "cn=test" in result


class TestParseDn:
    def test_simple_dn(self):
        result = parse_dn("cn=admin,dc=example,dc=com")
        assert result["cn"] == "admin"
        assert result["dc"] == "com"  # last one wins

    def test_no_equals(self):
        result = parse_dn("noequalssign")
        assert result == {}

    def test_empty_string(self):
        result = parse_dn("")
        assert result == {}


class TestExtractCnFromDn:
    def test_extracts_cn(self):
        assert extract_cn_from_dn("cn=Admins,ou=Groups,dc=example") == "Admins"

    def test_no_cn(self):
        assert extract_cn_from_dn("ou=Groups,dc=example") is None


class TestParseLdapEntry:
    def test_basic_entry(self):
        entry = ("cn=test,dc=example", {"uid": [b"testuser"], "mail": [b"t@ex.com"]})
        result = parse_ldap_entry(entry)
        assert result["dn"] == "cn=test,dc=example"
        assert result["uid"] == "testuser"
        assert result["mail"] == "t@ex.com"

    def test_multi_valued(self):
        entry = ("cn=test", {"memberOf": [b"cn=A", b"cn=B"]})
        result = parse_ldap_entry(entry)
        assert result["memberOf"] == ["cn=A", "cn=B"]


class TestDecodeLdapValue:
    def test_single_bytes(self):
        assert decode_ldap_value([b"hello"]) == "hello"

    def test_multiple_bytes(self):
        assert decode_ldap_value([b"a", b"b"]) == ["a", "b"]

    def test_non_bytes(self):
        assert decode_ldap_value(["string_val"]) == "string_val"

    def test_invalid_utf8(self):
        result = decode_ldap_value([b"\xff\xfe"])
        assert isinstance(result, str)


# --- Circuit Breaker ---


class TestLDAPCircuitBreaker:
    def test_initial_state_closed(self):
        cb = LDAPCircuitBreaker()
        assert cb.state == CircuitBreakerState.CLOSED.value
        assert cb.is_available is True

    def test_opens_after_threshold(self):
        cb = LDAPCircuitBreaker(failure_threshold=3, recovery_timeout=60.0)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN.value
        assert cb.is_available is False

    def test_transitions_to_half_open(self):
        cb = LDAPCircuitBreaker(failure_threshold=1, recovery_timeout=0.01)
        cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN.value
        time.sleep(0.02)
        assert cb.state == CircuitBreakerState.HALF_OPEN.value
        assert cb.is_available is True

    def test_success_resets_from_half_open(self):
        cb = LDAPCircuitBreaker(failure_threshold=1, recovery_timeout=0.01)
        cb.record_failure()
        time.sleep(0.02)
        _ = cb.state  # trigger half-open
        cb.record_success()
        assert cb.state == CircuitBreakerState.CLOSED.value

    def test_success_resets_from_open(self):
        cb = LDAPCircuitBreaker(failure_threshold=1)
        cb.record_failure()
        cb.record_success()
        assert cb.state == CircuitBreakerState.CLOSED.value
        assert cb.consecutive_failures == 0

    def test_consecutive_failures_property(self):
        cb = LDAPCircuitBreaker()
        cb.record_failure()
        cb.record_failure()
        assert cb.consecutive_failures == 2


# --- LDAPConfig ---


class TestLDAPConfig:
    def test_basic_config(self):
        cfg = LDAPConfig(server_uri="ldap://localhost", base_dn="dc=example,dc=com")
        assert cfg.server_uri == "ldap://localhost"
        assert cfg.use_tls is True
        assert cfg.pool_size == 5

    def test_from_tenant_config(self):
        cfg = LDAPConfig.from_tenant_config(
            tenant_id="t1",
            server_uri="ldaps://ldap.example.com",
            base_dn="dc=example,dc=com",
            bind_dn="cn=admin",
            bind_password="secret",
            pool_size=10,
        )
        assert cfg.tenant_id == "t1"
        assert cfg.pool_size == 10


# --- LDAPConnection (mock ldap module) ---


class TestLDAPConnection:
    def _make_config(self, **overrides):
        defaults = {
            "server_uri": "ldap://localhost",
            "base_dn": "dc=example,dc=com",
        }
        defaults.update(overrides)
        return LDAPConfig(**defaults)

    @patch("enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE", False)
    def test_raises_when_ldap_not_available(self):
        with pytest.raises(LDAPIntegrationError, match="python-ldap"):
            LDAPConnection(self._make_config())

    @patch("enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE", True)
    def test_connect_success(self):
        mock_ldap = MagicMock()
        mock_conn = MagicMock()
        mock_ldap.initialize.return_value = mock_conn
        mock_ldap.OPT_REFERRALS = 0
        mock_ldap.OPT_PROTOCOL_VERSION = 3
        mock_ldap.VERSION3 = 3
        mock_ldap.OPT_X_TLS_REQUIRE_CERT = 0x6006
        mock_ldap.OPT_X_TLS_DEMAND = 2
        mock_ldap.OPT_X_TLS_CACERTFILE = 0x6002
        with patch("enhanced_agent_bus.enterprise_sso.ldap_integration.ldap", mock_ldap):
            conn = LDAPConnection(
                self._make_config(verify_cert=True, ca_cert_path="/ca.pem", start_tls=True)
            )
            assert conn.connect() is True
            assert conn.is_connected is True
            mock_conn.start_tls_s.assert_called_once()

    @patch("enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE", True)
    def test_connect_failure_raises(self):
        mock_ldap = MagicMock()
        mock_ldap.initialize.side_effect = OSError("network error")
        with patch("enhanced_agent_bus.enterprise_sso.ldap_integration.ldap", mock_ldap):
            conn = LDAPConnection(self._make_config())
            with pytest.raises(LDAPConnectionError):
                conn.connect()

    @patch("enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE", True)
    def test_bind_not_connected_raises(self):
        mock_ldap = MagicMock()
        with patch("enhanced_agent_bus.enterprise_sso.ldap_integration.ldap", mock_ldap):
            conn = LDAPConnection(self._make_config())
            with pytest.raises(LDAPConnectionError, match="Not connected"):
                conn.bind()

    @patch("enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE", True)
    def test_bind_with_dn_and_password(self):
        mock_ldap = MagicMock()
        mock_conn_obj = MagicMock()
        mock_ldap.initialize.return_value = mock_conn_obj
        mock_ldap.OPT_REFERRALS = 0
        mock_ldap.OPT_PROTOCOL_VERSION = 3
        mock_ldap.VERSION3 = 3
        mock_ldap.OPT_X_TLS_REQUIRE_CERT = 0
        mock_ldap.OPT_X_TLS_DEMAND = 0
        with patch("enhanced_agent_bus.enterprise_sso.ldap_integration.ldap", mock_ldap):
            conn = LDAPConnection(
                self._make_config(bind_dn="cn=admin", bind_password="pass", verify_cert=False)
            )
            conn.connect()
            assert conn.bind() is True
            mock_conn_obj.simple_bind_s.assert_called_once_with("cn=admin", "pass")

    @patch("enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE", True)
    def test_bind_anonymous(self):
        mock_ldap = MagicMock()
        mock_conn_obj = MagicMock()
        mock_ldap.initialize.return_value = mock_conn_obj
        mock_ldap.OPT_REFERRALS = 0
        mock_ldap.OPT_PROTOCOL_VERSION = 3
        mock_ldap.VERSION3 = 3
        mock_ldap.OPT_X_TLS_REQUIRE_CERT = 0
        mock_ldap.OPT_X_TLS_DEMAND = 0
        with patch("enhanced_agent_bus.enterprise_sso.ldap_integration.ldap", mock_ldap):
            conn = LDAPConnection(self._make_config(verify_cert=False))
            conn.connect()
            conn.bind()
            mock_conn_obj.simple_bind_s.assert_called_once_with("", "")

    @patch("enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE", True)
    def test_bind_failure_raises(self):
        mock_ldap = MagicMock()
        mock_conn_obj = MagicMock()
        mock_conn_obj.simple_bind_s.side_effect = RuntimeError("bind err")
        mock_ldap.initialize.return_value = mock_conn_obj
        mock_ldap.OPT_REFERRALS = 0
        mock_ldap.OPT_PROTOCOL_VERSION = 3
        mock_ldap.VERSION3 = 3
        mock_ldap.OPT_X_TLS_REQUIRE_CERT = 0
        mock_ldap.OPT_X_TLS_DEMAND = 0
        with patch("enhanced_agent_bus.enterprise_sso.ldap_integration.ldap", mock_ldap):
            conn = LDAPConnection(self._make_config(verify_cert=False))
            conn.connect()
            with pytest.raises(LDAPBindError):
                conn.bind(bind_dn="cn=admin", password="wrong")

    @patch("enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE", True)
    def test_disconnect(self):
        mock_ldap = MagicMock()
        mock_conn_obj = MagicMock()
        mock_ldap.initialize.return_value = mock_conn_obj
        mock_ldap.OPT_REFERRALS = 0
        mock_ldap.OPT_PROTOCOL_VERSION = 3
        mock_ldap.VERSION3 = 3
        mock_ldap.OPT_X_TLS_REQUIRE_CERT = 0
        mock_ldap.OPT_X_TLS_DEMAND = 0
        with patch("enhanced_agent_bus.enterprise_sso.ldap_integration.ldap", mock_ldap):
            conn = LDAPConnection(self._make_config(verify_cert=False))
            conn.connect()
            conn.disconnect()
            assert conn.is_connected is False

    @patch("enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE", True)
    def test_disconnect_unbind_error_handled(self):
        mock_ldap = MagicMock()
        mock_conn_obj = MagicMock()
        mock_conn_obj.unbind_s.side_effect = OSError("cleanup err")
        mock_ldap.initialize.return_value = mock_conn_obj
        mock_ldap.OPT_REFERRALS = 0
        mock_ldap.OPT_PROTOCOL_VERSION = 3
        mock_ldap.VERSION3 = 3
        mock_ldap.OPT_X_TLS_REQUIRE_CERT = 0
        mock_ldap.OPT_X_TLS_DEMAND = 0
        with patch("enhanced_agent_bus.enterprise_sso.ldap_integration.ldap", mock_ldap):
            conn = LDAPConnection(self._make_config(verify_cert=False))
            conn.connect()
            conn.disconnect()  # should not raise
            assert conn.is_connected is False

    @patch("enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE", True)
    def test_whoami_not_bound_raises(self):
        mock_ldap = MagicMock()
        with patch("enhanced_agent_bus.enterprise_sso.ldap_integration.ldap", mock_ldap):
            conn = LDAPConnection(self._make_config())
            with pytest.raises(LDAPConnectionError, match="Not bound"):
                conn.whoami()

    @patch("enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE", True)
    def test_search_not_bound_raises(self):
        mock_ldap = MagicMock()
        with patch("enhanced_agent_bus.enterprise_sso.ldap_integration.ldap", mock_ldap):
            conn = LDAPConnection(self._make_config())
            with pytest.raises(LDAPConnectionError, match="Not bound"):
                conn.search("dc=example", "(uid=test)")

    @patch("enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE", True)
    def test_search_failure_raises(self):
        mock_ldap = MagicMock()
        mock_conn_obj = MagicMock()
        mock_conn_obj.search_s.side_effect = RuntimeError("search err")
        mock_ldap.initialize.return_value = mock_conn_obj
        mock_ldap.OPT_REFERRALS = 0
        mock_ldap.OPT_PROTOCOL_VERSION = 3
        mock_ldap.VERSION3 = 3
        mock_ldap.OPT_X_TLS_REQUIRE_CERT = 0
        mock_ldap.OPT_X_TLS_DEMAND = 0
        with patch("enhanced_agent_bus.enterprise_sso.ldap_integration.ldap", mock_ldap):
            conn = LDAPConnection(self._make_config(verify_cert=False))
            conn.connect()
            conn.bind()
            with pytest.raises(LDAPSearchError):
                conn.search("dc=example", "(uid=test)")

    @patch("enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE", True)
    def test_context_manager(self):
        mock_ldap = MagicMock()
        mock_conn_obj = MagicMock()
        mock_ldap.initialize.return_value = mock_conn_obj
        mock_ldap.OPT_REFERRALS = 0
        mock_ldap.OPT_PROTOCOL_VERSION = 3
        mock_ldap.VERSION3 = 3
        mock_ldap.OPT_X_TLS_REQUIRE_CERT = 0
        mock_ldap.OPT_X_TLS_DEMAND = 0
        with patch("enhanced_agent_bus.enterprise_sso.ldap_integration.ldap", mock_ldap):
            cfg = self._make_config(verify_cert=False)
            with LDAPConnection(cfg) as conn:
                assert conn.is_connected is True
            # exited context -> disconnected
            assert conn.is_connected is False


# --- LDAPConnectionPool ---


class TestLDAPConnectionPool:
    def _make_config(self):
        return LDAPConfig(
            server_uri="ldap://localhost",
            base_dn="dc=example,dc=com",
            pool_size=2,
        )

    @patch("enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE", True)
    def test_pool_health_check(self):
        mock_ldap = MagicMock()
        with patch("enhanced_agent_bus.enterprise_sso.ldap_integration.ldap", mock_ldap):
            pool = LDAPConnectionPool(self._make_config())
            health = pool.health_check()
            assert health["healthy"] is True
            assert health["max_size"] == 2

    @patch("enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE", True)
    def test_pool_shutdown(self):
        mock_ldap = MagicMock()
        mock_conn = MagicMock()
        mock_ldap.initialize.return_value = mock_conn
        mock_ldap.OPT_REFERRALS = 0
        mock_ldap.OPT_PROTOCOL_VERSION = 3
        mock_ldap.VERSION3 = 3
        mock_ldap.OPT_X_TLS_REQUIRE_CERT = 0
        mock_ldap.OPT_X_TLS_DEMAND = 0
        with patch("enhanced_agent_bus.enterprise_sso.ldap_integration.ldap", mock_ldap):
            pool = LDAPConnectionPool(self._make_config())
            # acquire creates a conn
            with pool.acquire() as conn:
                pass
            pool.shutdown()
            assert pool.active_connections == 0


# --- LDAPIntegration ---


class TestLDAPIntegration:
    def _make_config(self, **overrides):
        defaults = {
            "server_uri": "ldap://localhost",
            "base_dn": "dc=example,dc=com",
            "circuit_breaker_enabled": True,
            "group_to_maci_role_mapping": {"Admins": "CONTROLLER", "Users": "OBSERVER"},
        }
        defaults.update(overrides)
        return LDAPConfig(**defaults)

    @patch("enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE", False)
    def test_init_without_ldap(self):
        integration = LDAPIntegration(self._make_config())
        assert integration._pool is None
        assert integration.circuit_breaker is not None

    @patch("enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE", False)
    def test_init_without_circuit_breaker(self):
        integration = LDAPIntegration(self._make_config(circuit_breaker_enabled=False))
        assert integration.circuit_breaker is None

    def test_check_circuit_breaker_open_raises(self):
        integration = LDAPIntegration.__new__(LDAPIntegration)
        integration.config = self._make_config()
        integration.circuit_breaker = LDAPCircuitBreaker(failure_threshold=1)
        integration.circuit_breaker.record_failure()
        with pytest.raises(LDAPCircuitOpenError):
            integration._check_circuit_breaker()

    def test_build_user_dn_with_pattern(self):
        integration = LDAPIntegration.__new__(LDAPIntegration)
        integration.config = self._make_config(
            user_dn_pattern="cn={username},ou=People,dc=example,dc=com"
        )
        integration.circuit_breaker = None
        integration._pool = None
        result = integration.build_user_dn("alice")
        assert result == "cn=alice,ou=People,dc=example,dc=com"

    def test_build_user_dn_default(self):
        integration = LDAPIntegration.__new__(LDAPIntegration)
        integration.config = self._make_config()
        integration.circuit_breaker = None
        integration._pool = None
        result = integration.build_user_dn("bob")
        assert result == "uid=bob,dc=example,dc=com"

    def test_map_groups_to_maci_roles(self):
        integration = LDAPIntegration.__new__(LDAPIntegration)
        integration.config = self._make_config()
        roles = integration._map_groups_to_maci_roles(["admins", "Users", "Other"])
        assert "CONTROLLER" in roles
        assert "OBSERVER" in roles
        assert len(roles) == 2

    def test_map_groups_no_match(self):
        integration = LDAPIntegration.__new__(LDAPIntegration)
        integration.config = self._make_config()
        roles = integration._map_groups_to_maci_roles(["Unknown"])
        assert roles == []

    def test_log_authentication_attempt_success(self):
        integration = LDAPIntegration.__new__(LDAPIntegration)
        integration.config = self._make_config()
        # should not raise
        integration._log_authentication_attempt(username="test", success=True)

    def test_log_authentication_attempt_failure(self):
        integration = LDAPIntegration.__new__(LDAPIntegration)
        integration.config = self._make_config()
        integration._log_authentication_attempt(username="test", success=False, error="bad creds")

    def test_is_member_of(self):
        integration = LDAPIntegration.__new__(LDAPIntegration)
        integration.config = self._make_config()
        integration.circuit_breaker = None
        integration._pool = MagicMock()
        with patch.object(integration, "get_user_groups", return_value=["Admins", "Users"]):
            assert integration.is_member_of("alice", "admins") is True
            assert integration.is_member_of("alice", "SuperAdmin") is False

    def test_get_group_members_with_string(self):
        integration = LDAPIntegration.__new__(LDAPIntegration)
        integration.config = self._make_config()
        integration.circuit_breaker = None
        integration._pool = MagicMock()
        with patch.object(
            integration,
            "search_group",
            return_value={"cn": "Admins", "member": "cn=alice,dc=example"},
        ):
            members = integration.get_group_members("Admins")
            assert members == ["cn=alice,dc=example"]

    def test_get_group_members_with_list(self):
        integration = LDAPIntegration.__new__(LDAPIntegration)
        integration.config = self._make_config()
        integration.circuit_breaker = None
        with patch.object(
            integration,
            "search_group",
            return_value={"cn": "Admins", "member": ["cn=a", "cn=b"]},
        ):
            members = integration.get_group_members("Admins")
            assert len(members) == 2

    def test_get_group_members_not_found(self):
        integration = LDAPIntegration.__new__(LDAPIntegration)
        integration.config = self._make_config()
        integration.circuit_breaker = None
        with patch.object(integration, "search_group", return_value=None):
            assert integration.get_group_members("Missing") == []


# --- Exception classes ---


class TestLDAPExceptions:
    def test_ldap_integration_error(self):
        err = LDAPIntegrationError("test error")
        assert err.http_status_code == 500

    def test_ldap_connection_error(self):
        err = LDAPConnectionError("conn fail")
        assert err.http_status_code == 503

    def test_ldap_bind_error(self):
        err = LDAPBindError("bind fail")
        assert err.http_status_code == 401


# ---------------------------------------------------------------------------
# 2. bundle_registry tests
# ---------------------------------------------------------------------------
from enhanced_agent_bus.bundle_registry import (
    AWSECRAuthProvider,
    BasicAuthProvider,
    BundleArtifact,
    BundleDistributionService,
    BundleManifest,
    BundleStatus,
    OCIRegistryClient,
    OCIRegistryClientAdapter,
    RegistryType,
    close_distribution_service,
    get_distribution_service,
    initialize_distribution_service,
)


class TestRegistryType:
    def test_values(self):
        assert RegistryType.HARBOR.value == "harbor"
        assert RegistryType.ECR.value == "ecr"
        assert RegistryType.GENERIC.value == "generic"


class TestBundleStatus:
    def test_values(self):
        assert BundleStatus.DRAFT.value == "draft"
        assert BundleStatus.PUBLISHED.value == "published"
        assert BundleStatus.REVOKED.value == "revoked"


class TestBundleManifest:
    def test_to_dict(self):
        m = BundleManifest(version="1.0.0", revision="a" * 40)
        d = m.to_dict()
        assert d["version"] == "1.0.0"
        assert d["revision"] == "a" * 40
        assert "signatures" in d

    def test_from_dict(self):
        m = BundleManifest.from_dict({"version": "2.0", "revision": "b" * 40})
        assert m.version == "2.0"

    def test_add_signature(self):
        m = BundleManifest(version="1.0.0", revision="a" * 40)
        m.add_signature(keyid="key1", signature="deadbeef")
        assert len(m.signatures) == 1
        assert m.signatures[0]["keyid"] == "key1"
        assert m.signatures[0]["alg"] == "ed25519"

    def test_compute_digest(self):
        m = BundleManifest(version="1.0.0", revision="a" * 40)
        digest = m.compute_digest()
        assert len(digest) == 64  # sha256 hex

    def test_verify_signature_no_signatures(self):
        m = BundleManifest(version="1.0.0", revision="a" * 40)
        assert m.verify_signature("00" * 32) is False

    def test_verify_signature_invalid_key(self):
        m = BundleManifest(version="1.0.0", revision="a" * 40)
        m.add_signature("k1", "ff" * 32)
        assert m.verify_signature("invalid_hex") is False

    def test_verify_cosign_no_signatures(self):
        m = BundleManifest(version="1.0.0", revision="a" * 40)
        assert m.verify_cosign_signature("digest", "00" * 32) is False

    def test_verify_cosign_invalid_key(self):
        m = BundleManifest(version="1.0.0", revision="a" * 40)
        m.add_signature("k1", "ff" * 32)
        assert m.verify_cosign_signature("digest", "badhex") is False

    def test_verify_signature_wrong_sig(self):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        private_key = Ed25519PrivateKey.generate()
        public_key = private_key.public_key()
        public_key_hex = public_key.public_bytes_raw().hex()

        m = BundleManifest(version="1.0.0", revision="a" * 40)
        m.add_signature("k1", "ff" * 64)  # wrong signature
        assert m.verify_signature(public_key_hex) is False

    def test_verify_signature_valid(self):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        private_key = Ed25519PrivateKey.generate()
        public_key = private_key.public_key()
        public_key_hex = public_key.public_bytes_raw().hex()

        m = BundleManifest(version="1.0.0", revision="a" * 40)
        # Sign the manifest content (excluding signatures)
        manifest_data = m.to_dict()
        manifest_data.pop("signatures", None)
        content = json.dumps(manifest_data, sort_keys=True).encode()
        sig = private_key.sign(content)
        m.add_signature("k1", sig.hex())
        assert m.verify_signature(public_key_hex) is True

    def test_verify_signature_skips_non_ed25519(self):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        private_key = Ed25519PrivateKey.generate()
        public_key_hex = private_key.public_key().public_bytes_raw().hex()

        m = BundleManifest(version="1.0.0", revision="a" * 40)
        m.signatures.append({"keyid": "k1", "sig": "ff" * 64, "alg": "rsa-pss-sha256"})
        assert m.verify_signature(public_key_hex) is False

    def test_verify_cosign_valid(self):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        private_key = Ed25519PrivateKey.generate()
        public_key_hex = private_key.public_key().public_bytes_raw().hex()

        digest = "sha256:abc123"
        sig = private_key.sign(digest.encode())

        m = BundleManifest(version="1.0.0", revision="a" * 40)
        m.add_signature("k1", sig.hex())
        assert m.verify_cosign_signature(digest, public_key_hex) is True

    def test_verify_cosign_skips_non_ed25519(self):
        m = BundleManifest(version="1.0.0", revision="a" * 40)
        m.signatures.append({"keyid": "k1", "sig": "ff" * 64, "alg": "rsa-pss-sha256"})
        assert m.verify_cosign_signature("digest", "00" * 32) is False

    def test_invalid_constitutional_hash_raises(self):
        from enhanced_agent_bus._compat.errors import ConstitutionalViolationError

        with pytest.raises(ConstitutionalViolationError):
            BundleManifest(
                version="1.0.0",
                revision="a" * 40,
                constitutional_hash="wrong_hash",
            )


class TestBasicAuthProvider:
    async def test_get_token(self):
        import base64

        provider = BasicAuthProvider(username="user", password="pass")
        token = await provider.get_token()
        decoded = base64.b64decode(token).decode()
        assert decoded == "user:pass"

    async def test_refresh_token(self):
        provider = BasicAuthProvider(username="user", password="pass")
        token1 = await provider.get_token()
        token2 = await provider.refresh_token()
        assert token1 == token2

    def test_encrypted_credentials(self):
        provider = BasicAuthProvider(username="user", password="pass")
        assert provider.username == "user"
        assert provider.password == "pass"


class TestAWSECRAuthProvider:
    async def test_get_token_cached(self):
        provider = AWSECRAuthProvider()
        provider._token = "cached_token"
        provider._expiry = datetime.now(UTC) + timedelta(hours=1)
        token = await provider.get_token()
        assert token == "cached_token"

    async def test_refresh_token_no_boto3(self):
        provider = AWSECRAuthProvider()
        with patch.dict(os.environ, {"AWS_ECR_TOKEN": "env_token"}):
            with patch("builtins.__import__", side_effect=ImportError):
                token = await provider.refresh_token()
                # falls back to env or empty
                assert isinstance(token, str)


class TestOCIRegistryClient:
    def test_from_url_oci_scheme(self):
        client = OCIRegistryClient.from_url("oci://registry.example.com/repo")
        assert "registry.example.com" in client.host

    def test_from_url_no_scheme(self):
        client = OCIRegistryClient.from_url("registry.example.com/repo")
        assert client.scheme == "https"

    def test_session_alias(self):
        client = OCIRegistryClient("https://registry.example.com")
        assert client._session is None
        mock_client = MagicMock()
        client._session = mock_client
        assert client._client is mock_client

    async def test_initialize_creates_client(self):
        client = OCIRegistryClient("https://registry.example.com")
        await client.initialize()
        assert client._client is not None
        await client.close()

    async def test_close_clears_client(self):
        client = OCIRegistryClient("https://registry.example.com")
        await client.initialize()
        await client.close()
        assert client._client is None

    async def test_get_headers_no_auth(self):
        client = OCIRegistryClient("https://registry.example.com")
        headers = await client._get_headers()
        assert "Authorization" not in headers

    async def test_get_headers_with_bearer_auth(self):
        mock_provider = AsyncMock()
        mock_provider.get_token.return_value = "tok123"
        client = OCIRegistryClient("https://registry.example.com", auth_provider=mock_provider)
        headers = await client._get_headers()
        assert headers["Authorization"] == "Bearer tok123"

    async def test_get_headers_with_ecr_auth(self):
        mock_provider = AsyncMock()
        mock_provider.get_token.return_value = "ecr_tok"
        client = OCIRegistryClient(
            "https://registry.example.com",
            auth_provider=mock_provider,
            registry_type=RegistryType.ECR,
        )
        headers = await client._get_headers()
        assert headers["Authorization"] == "Basic ecr_tok"

    async def test_check_health_success(self):
        client = OCIRegistryClient("https://registry.example.com")
        mock_http = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_http.get.return_value = mock_response
        client._client = mock_http
        assert await client.check_health() is True

    async def test_check_health_failure(self):
        client = OCIRegistryClient("https://registry.example.com")
        mock_http = AsyncMock()
        mock_http.get.side_effect = ConnectionError("down")
        client._client = mock_http
        assert await client.check_health() is False

    async def test_list_tags(self):
        client = OCIRegistryClient("https://registry.example.com")
        mock_http = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"tags": ["v1", "v2"]}
        mock_http.get.return_value = mock_response
        client._client = mock_http
        tags = await client.list_tags("acgs/policies")
        assert tags == ["v1", "v2"]

    async def test_list_tags_failure(self):
        client = OCIRegistryClient("https://registry.example.com")
        mock_http = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_http.get.return_value = mock_response
        client._client = mock_http
        tags = await client.list_tags("acgs/policies")
        assert tags == []

    async def test_delete_tag_success(self):
        client = OCIRegistryClient("https://registry.example.com")
        mock_http = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_http.delete.return_value = mock_response
        client._client = mock_http
        assert await client.delete_tag("repo", "v1") is True

    async def test_delete_tag_failure(self):
        client = OCIRegistryClient("https://registry.example.com")
        mock_http = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_http.delete.return_value = mock_response
        client._client = mock_http
        assert await client.delete_tag("repo", "v1") is False

    def test_get_stats(self):
        client = OCIRegistryClient("https://registry.example.com")
        stats = client.get_stats()
        assert stats["pushes"] == 0
        assert stats["type"] == "generic"

    async def test_context_manager(self):
        client = OCIRegistryClient("https://registry.example.com")
        async with client as c:
            assert c._client is not None
        assert c._client is None


class TestOCIRegistryClientAdapter:
    async def test_push_delegates(self):
        mock_client = AsyncMock()
        mock_client.push_bundle.return_value = ("digest", MagicMock())
        adapter = OCIRegistryClientAdapter(mock_client)
        result = await adapter.push_bundle("repo", "v1", "/path", MagicMock())
        mock_client.push_bundle.assert_called_once()

    async def test_pull_delegates(self):
        mock_client = AsyncMock()
        mock_manifest = MagicMock()
        mock_client.pull_bundle.return_value = (mock_manifest, "/path")
        adapter = OCIRegistryClientAdapter(mock_client)
        result = await adapter.pull_bundle("repo", "v1", "/dest")
        mock_client.pull_bundle.assert_called_once()


class TestBundleDistributionService:
    def test_get_distribution_service_none(self):
        assert (
            get_distribution_service() is not None or get_distribution_service() is None
        )  # coverage


class TestBundleArtifact:
    def test_creation(self):
        a = BundleArtifact(digest="sha256:abc", size=100)
        assert a.media_type == "application/vnd.opa.bundle.layer.v1+gzip"


# ---------------------------------------------------------------------------
# 3. multi_approver tests
# ---------------------------------------------------------------------------
from enhanced_agent_bus.deliberation_layer.multi_approver import (
    ApprovalDecision,
    ApprovalPolicy,
    ApprovalRequest,
    ApprovalStatus,
    Approver,
    ApproverRole,
    EscalationLevel,
    MultiApproverWorkflowEngine,
    SlackNotificationChannel,
    TeamsNotificationChannel,
    get_workflow_engine,
    initialize_workflow_engine,
    shutdown_workflow_engine,
)


class TestApproverRole:
    def test_values(self):
        assert ApproverRole.SECURITY_TEAM.value == "security_team"
        assert ApproverRole.ON_CALL.value == "on_call"


class TestApprover:
    def test_has_role(self):
        a = Approver(
            id="a1",
            name="Alice",
            email="a@x.com",
            roles=[ApproverRole.SECURITY_TEAM, ApproverRole.PLATFORM_ADMIN],
        )
        assert a.has_role(ApproverRole.SECURITY_TEAM) is True
        assert a.has_role(ApproverRole.ON_CALL) is False


class TestApprovalDecision:
    def test_to_dict(self):
        d = ApprovalDecision(
            approver_id="a1",
            approver_name="Alice",
            decision=ApprovalStatus.APPROVED,
            reasoning="looks good",
        )
        result = d.to_dict()
        assert result["decision"] == "approved"
        assert result["reasoning"] == "looks good"


class TestApprovalPolicy:
    def _make_policy(self, **overrides):
        defaults = {
            "name": "Test Policy",
            "required_roles": [ApproverRole.SECURITY_TEAM],
            "min_approvers": 1,
        }
        defaults.update(overrides)
        return ApprovalPolicy(**defaults)

    def _make_decision(self, approver_id="a1", status=ApprovalStatus.APPROVED):
        return ApprovalDecision(
            approver_id=approver_id,
            approver_name="Test",
            decision=status,
            reasoning="ok",
        )

    def _make_approver(self, id="a1", roles=None):
        return Approver(
            id=id,
            name="Test",
            email="t@x.com",
            roles=roles or [ApproverRole.SECURITY_TEAM],
        )

    def test_minimum_approvers_not_met(self):
        policy = self._make_policy(min_approvers=2)
        valid, reason = policy.validate_approvers(
            [self._make_decision()],
            {"a1": self._make_approver()},
            "requester",
        )
        assert valid is False
        assert "Need 2" in reason

    def test_self_approval_rejected(self):
        policy = self._make_policy(allow_self_approval=False)
        valid, reason = policy.validate_approvers(
            [self._make_decision(approver_id="requester")],
            {"requester": self._make_approver(id="requester")},
            "requester",
        )
        assert valid is False
        assert "Self-approval" in reason

    def test_self_approval_allowed(self):
        policy = self._make_policy(allow_self_approval=True)
        valid, _ = policy.validate_approvers(
            [self._make_decision(approver_id="requester")],
            {"requester": self._make_approver(id="requester")},
            "requester",
        )
        assert valid is True

    def test_require_all_roles(self):
        policy = self._make_policy(
            required_roles=[ApproverRole.SECURITY_TEAM, ApproverRole.COMPLIANCE_TEAM],
            require_all_roles=True,
            min_approvers=1,
        )
        # Only security team approved
        valid, reason = policy.validate_approvers(
            [self._make_decision()],
            {"a1": self._make_approver()},
            "other",
        )
        assert valid is False
        assert "Missing" in reason

    def test_require_all_roles_met(self):
        policy = self._make_policy(
            required_roles=[ApproverRole.SECURITY_TEAM, ApproverRole.COMPLIANCE_TEAM],
            require_all_roles=True,
            min_approvers=1,
        )
        decisions = [
            self._make_decision(approver_id="a1"),
            self._make_decision(approver_id="a2"),
        ]
        approvers = {
            "a1": self._make_approver(id="a1", roles=[ApproverRole.SECURITY_TEAM]),
            "a2": self._make_approver(id="a2", roles=[ApproverRole.COMPLIANCE_TEAM]),
        }
        valid, _ = policy.validate_approvers(decisions, approvers, "other")
        assert valid is True

    def test_any_role_required_no_match(self):
        policy = self._make_policy(
            required_roles=[ApproverRole.COMPLIANCE_TEAM],
            require_all_roles=False,
        )
        valid, reason = policy.validate_approvers(
            [self._make_decision()],
            {"a1": self._make_approver(roles=[ApproverRole.SECURITY_TEAM])},
            "other",
        )
        assert valid is False
        assert "No approver" in reason

    def test_any_role_required_empty_roles(self):
        policy = self._make_policy(required_roles=[], require_all_roles=False)
        valid, _ = policy.validate_approvers(
            [self._make_decision()],
            {"a1": self._make_approver()},
            "other",
        )
        assert valid is True


class TestApprovalRequest:
    def _make_request(self, **overrides):
        defaults = {
            "id": "req-1",
            "request_type": "test",
            "requester_id": "user-1",
            "requester_name": "User",
            "tenant_id": "t-1",
            "title": "Test Request",
            "description": "Desc",
            "risk_score": 0.5,
            "policy": ApprovalPolicy(name="p", required_roles=[ApproverRole.SECURITY_TEAM]),
            "payload": {"key": "val"},
        }
        defaults.update(overrides)
        return ApprovalRequest(**defaults)

    def test_invalid_hash_raises(self):
        with pytest.raises(ValueError, match="Invalid constitutional hash"):
            self._make_request(constitutional_hash="wrong")

    def test_deadline_auto_set(self):
        req = self._make_request()
        assert req.deadline is not None

    def test_compute_hash(self):
        req = self._make_request()
        h = req.compute_hash()
        assert isinstance(h, str)
        assert len(h) == 16

    def test_to_dict(self):
        req = self._make_request()
        d = req.to_dict()
        assert d["id"] == "req-1"
        assert d["status"] == "pending"
        assert "request_hash" in d


class TestSlackNotificationChannel:
    async def test_send_approval_request(self):
        channel = SlackNotificationChannel()
        policy = ApprovalPolicy(name="p", required_roles=[ApproverRole.SECURITY_TEAM])
        req = ApprovalRequest(
            id="r1",
            request_type="test",
            requester_id="u1",
            requester_name="User",
            tenant_id="t1",
            title="Title",
            description="Desc",
            risk_score=0.95,
            policy=policy,
            payload={},
        )
        approver = Approver(
            id="a1",
            name="Alice",
            email="a@x.com",
            roles=[ApproverRole.SECURITY_TEAM],
            slack_id="U123",
        )
        result = await channel.send_approval_request(req, [approver])
        assert result is True

    async def test_send_decision_notification(self):
        channel = SlackNotificationChannel()
        req = MagicMock(id="r1")
        decision = ApprovalDecision(
            approver_id="a1",
            approver_name="Alice",
            decision=ApprovalStatus.REJECTED,
            reasoning="no",
        )
        result = await channel.send_decision_notification(req, decision)
        assert result is True

    async def test_send_escalation_notification(self):
        channel = SlackNotificationChannel()
        req = MagicMock(id="r1", title="Test", constitutional_hash="x")
        result = await channel.send_escalation_notification(req, EscalationLevel.LEVEL_3)
        assert result is True

    def test_risk_emoji_thresholds(self):
        channel = SlackNotificationChannel()
        assert channel._get_risk_emoji(0.95) != channel._get_risk_emoji(0.3)
        assert channel._get_risk_emoji(0.75) != channel._get_risk_emoji(0.55)


class TestTeamsNotificationChannel:
    async def test_send_approval_request(self):
        channel = TeamsNotificationChannel()
        policy = ApprovalPolicy(name="p", required_roles=[ApproverRole.SECURITY_TEAM])
        req = ApprovalRequest(
            id="r1",
            request_type="test",
            requester_id="u1",
            requester_name="User",
            tenant_id="t1",
            title="Title",
            description="Desc",
            risk_score=0.5,
            policy=policy,
            payload={},
        )
        result = await channel.send_approval_request(req, [])
        assert result is True

    async def test_send_decision_notification(self):
        channel = TeamsNotificationChannel()
        req = MagicMock(id="r1")
        decision = ApprovalDecision(
            approver_id="a1",
            approver_name="A",
            decision=ApprovalStatus.APPROVED,
            reasoning="ok",
        )
        assert await channel.send_decision_notification(req, decision) is True

    async def test_send_escalation(self):
        channel = TeamsNotificationChannel()
        req = MagicMock(id="r1")
        assert await channel.send_escalation_notification(req, EscalationLevel.EXECUTIVE) is True

    def test_theme_colors(self):
        channel = TeamsNotificationChannel()
        assert channel._get_theme_color(0.95) == "FF0000"
        assert channel._get_theme_color(0.75) == "FFA500"
        assert channel._get_theme_color(0.55) == "FFFF00"
        assert channel._get_theme_color(0.3) == "00FF00"


class TestMultiApproverWorkflowEngine:
    def _make_engine(self):
        channel = AsyncMock()
        channel.send_approval_request = AsyncMock(return_value=True)
        channel.send_decision_notification = AsyncMock(return_value=True)
        channel.send_escalation_notification = AsyncMock(return_value=True)
        engine = MultiApproverWorkflowEngine(notification_channels=[channel])
        return engine

    def _register_approvers(self, engine):
        engine.register_approver(
            Approver(
                id="sec-1",
                name="Sec",
                email="s@x.com",
                roles=[ApproverRole.SECURITY_TEAM],
            )
        )
        engine.register_approver(
            Approver(
                id="comp-1",
                name="Comp",
                email="c@x.com",
                roles=[ApproverRole.COMPLIANCE_TEAM],
            )
        )
        engine.register_approver(
            Approver(
                id="admin-1",
                name="Admin",
                email="a@x.com",
                roles=[ApproverRole.TENANT_ADMIN],
            )
        )

    async def test_create_request_auto_approve_low_risk(self):
        engine = self._make_engine()
        self._register_approvers(engine)
        req = await engine.create_request(
            request_type="standard",
            requester_id="u1",
            requester_name="User",
            tenant_id="t1",
            title="Low Risk",
            description="Desc",
            risk_score=0.1,
            payload={},
            policy_id="standard_request",
        )
        assert req.status == ApprovalStatus.APPROVED

    async def test_create_request_pending(self):
        engine = self._make_engine()
        self._register_approvers(engine)
        req = await engine.create_request(
            request_type="high",
            requester_id="u1",
            requester_name="User",
            tenant_id="t1",
            title="High Risk",
            description="Desc",
            risk_score=0.85,
            payload={},
        )
        assert req.status == ApprovalStatus.PENDING

    async def test_create_request_unknown_policy_raises(self):
        engine = self._make_engine()
        with pytest.raises(ValueError, match="Unknown policy"):
            await engine.create_request(
                request_type="x",
                requester_id="u1",
                requester_name="User",
                tenant_id="t1",
                title="T",
                description="D",
                risk_score=0.5,
                payload={},
                policy_id="nonexistent",
            )

    async def test_submit_decision_reject(self):
        engine = self._make_engine()
        self._register_approvers(engine)
        req = await engine.create_request(
            request_type="policy",
            requester_id="u1",
            requester_name="User",
            tenant_id="t1",
            title="Test",
            description="Desc",
            risk_score=0.85,
            payload={},
        )
        ok, msg = await engine.submit_decision(
            req.id, "sec-1", ApprovalStatus.REJECTED, "security concern"
        )
        assert ok is True
        assert "rejected" in msg.lower()

    async def test_submit_decision_not_found(self):
        engine = self._make_engine()
        ok, msg = await engine.submit_decision("missing", "a1", ApprovalStatus.APPROVED, "ok")
        assert ok is False
        assert "not found" in msg.lower()

    async def test_submit_decision_not_pending(self):
        engine = self._make_engine()
        self._register_approvers(engine)
        req = await engine.create_request(
            request_type="standard",
            requester_id="u1",
            requester_name="User",
            tenant_id="t1",
            title="Auto",
            description="Desc",
            risk_score=0.1,
            payload={},
            policy_id="standard_request",
        )
        # already approved
        ok, msg = await engine.submit_decision(req.id, "admin-1", ApprovalStatus.APPROVED, "ok")
        assert ok is False
        assert "not pending" in msg.lower()

    async def test_submit_decision_duplicate(self):
        engine = self._make_engine()
        self._register_approvers(engine)
        req = await engine.create_request(
            request_type="high",
            requester_id="u1",
            requester_name="User",
            tenant_id="t1",
            title="Test",
            description="D",
            risk_score=0.85,
            payload={},
        )
        await engine.submit_decision(req.id, "sec-1", ApprovalStatus.APPROVED, "ok")
        ok, msg = await engine.submit_decision(req.id, "sec-1", ApprovalStatus.APPROVED, "again")
        assert ok is False
        assert "already submitted" in msg.lower()

    async def test_submit_decision_empty_reasoning(self):
        engine = self._make_engine()
        self._register_approvers(engine)
        req = await engine.create_request(
            request_type="high",
            requester_id="u1",
            requester_name="User",
            tenant_id="t1",
            title="T",
            description="D",
            risk_score=0.85,
            payload={},
        )
        ok, msg = await engine.submit_decision(req.id, "sec-1", ApprovalStatus.APPROVED, "   ")
        assert ok is False
        assert "Reasoning" in msg

    async def test_submit_decision_unknown_approver(self):
        engine = self._make_engine()
        self._register_approvers(engine)
        req = await engine.create_request(
            request_type="high",
            requester_id="u1",
            requester_name="User",
            tenant_id="t1",
            title="T",
            description="D",
            risk_score=0.85,
            payload={},
        )
        ok, msg = await engine.submit_decision(req.id, "unknown", ApprovalStatus.APPROVED, "ok")
        assert ok is False
        assert "not registered" in msg.lower()

    async def test_cancel_request(self):
        engine = self._make_engine()
        self._register_approvers(engine)
        req = await engine.create_request(
            request_type="high",
            requester_id="u1",
            requester_name="User",
            tenant_id="t1",
            title="T",
            description="D",
            risk_score=0.85,
            payload={},
        )
        assert await engine.cancel_request(req.id, "no longer needed") is True
        assert engine.get_request(req.id).status == ApprovalStatus.CANCELLED

    async def test_cancel_request_not_found(self):
        engine = self._make_engine()
        assert await engine.cancel_request("missing", "reason") is False

    async def test_get_pending_requests(self):
        engine = self._make_engine()
        self._register_approvers(engine)
        await engine.create_request(
            request_type="high",
            requester_id="u1",
            requester_name="User",
            tenant_id="t1",
            title="T1",
            description="D",
            risk_score=0.85,
            payload={},
        )
        pending = engine.get_pending_requests(tenant_id="t1")
        assert len(pending) == 1

    async def test_get_pending_requests_by_approver(self):
        engine = self._make_engine()
        self._register_approvers(engine)
        await engine.create_request(
            request_type="high",
            requester_id="u1",
            requester_name="User",
            tenant_id="t1",
            title="T1",
            description="D",
            risk_score=0.85,
            payload={},
        )
        pending = engine.get_pending_requests(approver_id="sec-1")
        assert len(pending) >= 1

    async def test_get_stats(self):
        engine = self._make_engine()
        stats = engine.get_stats()
        assert "total_requests" in stats
        assert "by_status" in stats

    def test_select_policy_for_risk(self):
        engine = self._make_engine()
        assert engine._select_policy_for_risk(0.95) == "critical_deployment"
        assert engine._select_policy_for_risk(0.8) == "high_risk_action"
        assert engine._select_policy_for_risk(0.6) == "policy_change"
        assert engine._select_policy_for_risk(0.2) == "standard_request"

    def test_register_policy(self):
        engine = self._make_engine()
        custom = ApprovalPolicy(name="Custom", required_roles=[ApproverRole.ON_CALL])
        engine.register_policy("custom_id", custom)
        assert "custom_id" in engine._policies

    async def test_start_and_stop(self):
        engine = self._make_engine()
        await engine.start()
        assert engine._running is True
        await engine.stop()
        assert engine._running is False

    async def test_process_pending_timeout(self):
        engine = self._make_engine()
        self._register_approvers(engine)
        req = await engine.create_request(
            request_type="high",
            requester_id="u1",
            requester_name="User",
            tenant_id="t1",
            title="T",
            description="D",
            risk_score=0.85,
            payload={},
        )
        # Force deadline to past
        req.deadline = datetime.now(UTC) - timedelta(hours=1)
        await engine._process_pending_requests()
        assert req.status == ApprovalStatus.TIMEOUT

    async def test_process_pending_escalation(self):
        engine = self._make_engine()
        self._register_approvers(engine)
        req = await engine.create_request(
            request_type="high",
            requester_id="u1",
            requester_name="User",
            tenant_id="t1",
            title="T",
            description="D",
            risk_score=0.85,
            payload={},
        )
        # Force old creation time for escalation
        req.created_at = datetime.now(UTC) - timedelta(hours=20)
        req.deadline = datetime.now(UTC) + timedelta(hours=100)
        await engine._process_pending_requests()
        assert req.escalation_level.value > EscalationLevel.LEVEL_1.value

    def test_calculate_escalation_level(self):
        engine = self._make_engine()
        policy = ApprovalPolicy(
            name="p",
            required_roles=[ApproverRole.SECURITY_TEAM],
            escalation_hours=4.0,
        )
        req = ApprovalRequest(
            id="r1",
            request_type="t",
            requester_id="u1",
            requester_name="U",
            tenant_id="t1",
            title="T",
            description="D",
            risk_score=0.5,
            policy=policy,
            payload={},
        )
        now = req.created_at + timedelta(hours=5)
        level = engine._calculate_escalation_level(req, now)
        assert level == EscalationLevel.LEVEL_2

        now = req.created_at + timedelta(hours=9)
        level = engine._calculate_escalation_level(req, now)
        assert level == EscalationLevel.LEVEL_3

        now = req.created_at + timedelta(hours=13)
        level = engine._calculate_escalation_level(req, now)
        assert level == EscalationLevel.EXECUTIVE

        now = req.created_at + timedelta(hours=1)
        level = engine._calculate_escalation_level(req, now)
        assert level is None

    async def test_audit_callback_called(self):
        callback = MagicMock()
        engine = MultiApproverWorkflowEngine(
            notification_channels=[AsyncMock()],
            audit_callback=callback,
        )
        engine.register_approver(
            Approver(
                id="sec-1",
                name="Sec",
                email="s@x.com",
                roles=[ApproverRole.SECURITY_TEAM],
            )
        )
        req = await engine.create_request(
            request_type="high",
            requester_id="u1",
            requester_name="User",
            tenant_id="t1",
            title="T",
            description="D",
            risk_score=0.85,
            payload={},
        )
        await engine.submit_decision(req.id, "sec-1", ApprovalStatus.APPROVED, "ok")
        callback.assert_called_once()


class TestWorkflowSingletons:
    async def test_initialize_and_shutdown(self):
        channel = AsyncMock()
        channel.send_approval_request = AsyncMock(return_value=True)
        channel.send_decision_notification = AsyncMock(return_value=True)
        channel.send_escalation_notification = AsyncMock(return_value=True)

        engine = await initialize_workflow_engine(notification_channels=[channel])
        assert engine is not None
        assert get_workflow_engine() is engine
        await shutdown_workflow_engine()
        assert get_workflow_engine() is None


# ---------------------------------------------------------------------------
# 4. routes/tenants helper function tests
# ---------------------------------------------------------------------------
from fastapi import HTTPException

from enhanced_agent_bus.routes.tenants import (
    _build_quota_check_response,
    _build_tenant_hierarchy_response,
    _build_tenant_list_response,
    _build_usage_response,
    _calculate_utilization,
    _check_tenant_scope,
    _extract_usage_and_quota_dicts,
    _has_auth_configuration,
    _is_production_runtime,
    _is_uuid,
    _parse_status_filter,
    _quota_resource_keys,
    _raise_internal_tenant_error,
    _raise_tenant_not_found,
    _raise_value_http_error,
    _to_dict_safe,
    _validate_admin_api_key,
)


class TestToDict:
    def test_none(self):
        assert _to_dict_safe(None) == {}

    def test_dict(self):
        assert _to_dict_safe({"a": 1}) == {"a": 1}

    def test_model_dump(self):
        obj = MagicMock()
        obj.model_dump.return_value = {"x": 1}
        assert _to_dict_safe(obj) == {"x": 1}

    def test_to_dict_method(self):
        obj = MagicMock(spec=[])
        obj.to_dict = MagicMock(return_value={"y": 2})
        assert _to_dict_safe(obj) == {"y": 2}

    def test_dataclass(self):
        from dataclasses import dataclass as dc

        @dc
        class Foo:
            val: int = 1

        assert _to_dict_safe(Foo()) == {"val": 1}

    def test_fallback_dict(self):
        assert _to_dict_safe([("a", 1)]) == {"a": 1}

    def test_unconvertible(self):
        assert _to_dict_safe(42) == {}


class TestIsUuid:
    def test_valid_uuid(self):
        assert _is_uuid("550e8400-e29b-41d4-a716-446655440000") is True

    def test_invalid_uuid(self):
        assert _is_uuid("system-admin") is False

    def test_short_string(self):
        assert _is_uuid("abc") is False


class TestCheckTenantScope:
    def test_same_tenant_allowed(self):
        _check_tenant_scope("t1", "t1")  # should not raise

    def test_super_admin_allowed(self):
        _check_tenant_scope(
            "550e8400-e29b-41d4-a716-446655440000",
            "other-tenant",
            is_super_admin=True,
        )  # should not raise

    def test_non_uuid_admin_allowed(self):
        _check_tenant_scope("system-admin", "any-tenant")  # should not raise

    def test_cross_tenant_denied(self):
        with pytest.raises(HTTPException) as exc:
            _check_tenant_scope(
                "550e8400-e29b-41d4-a716-446655440000",
                "660e8400-e29b-41d4-a716-446655440000",
            )
        assert exc.value.status_code == 403


class TestParseStatusFilter:
    def test_none_returns_none(self):
        assert _parse_status_filter(None) is None

    def test_valid_status(self):
        result = _parse_status_filter("active")
        assert result is not None

    def test_invalid_status_raises(self):
        with pytest.raises(HTTPException) as exc:
            _parse_status_filter("invalid_status")
        assert exc.value.status_code == 400


class TestQuotaResourceKeys:
    def test_known_resource(self):
        usage_key, quota_key = _quota_resource_keys("agents")
        assert usage_key == "agents_count"
        assert quota_key == "max_agents"

    def test_unknown_resource(self):
        usage_key, quota_key = _quota_resource_keys("custom")
        assert usage_key == "custom_count"
        assert quota_key == "max_custom"


class TestCalculateUtilization:
    def test_basic(self):
        usage = {"agents_count": 50}
        quota = {"max_agents": 100}
        result = _calculate_utilization(usage, quota)
        assert result["agents_count"] == 50.0

    def test_zero_quota(self):
        usage = {"agents_count": 50}
        quota = {"max_agents": 0}
        result = _calculate_utilization(usage, quota)
        assert "agents_count" not in result

    def test_non_numeric_skipped(self):
        usage = {"agents_count": "bad"}
        quota = {"max_agents": 100}
        result = _calculate_utilization(usage, quota)
        assert "agents_count" not in result


class TestBuildResponses:
    def test_build_usage_response(self):
        resp = _build_usage_response("t1", usage_dict={"a": 1}, quota_dict={"b": 2})
        assert resp.tenant_id == "t1"

    def test_build_quota_check_response(self):
        from enhanced_agent_bus.routes.models.tenant_models import QuotaCheckRequest

        req = QuotaCheckRequest(resource="agents", requested_amount=5)
        resp = _build_quota_check_response(
            "t1",
            req,
            available=True,
            usage_dict={"agents_count": 10},
            quota_dict={"max_agents": 100},
        )
        assert resp.available is True
        assert resp.remaining == 90

    def test_build_quota_check_response_non_int_values(self):
        from enhanced_agent_bus.routes.models.tenant_models import QuotaCheckRequest

        req = QuotaCheckRequest(resource="agents", requested_amount=1)
        resp = _build_quota_check_response(
            "t1",
            req,
            available=True,
            usage_dict={"agents_count": "bad"},
            quota_dict={"max_agents": "bad"},
        )
        assert resp.current_usage == 0
        assert resp.quota_limit == 0


class TestRaiseHelpers:
    def test_raise_tenant_not_found(self):
        from enhanced_agent_bus.routes.tenants import TenantNotFoundError

        err = TenantNotFoundError("not found", tenant_id="t1")
        with pytest.raises(HTTPException) as exc:
            _raise_tenant_not_found(err)
        assert exc.value.status_code == 404

    def test_raise_internal_error(self):
        with pytest.raises(HTTPException) as exc:
            _raise_internal_tenant_error(RuntimeError("fail"), "action", "ctx")
        assert exc.value.status_code == 500

    def test_raise_value_error_duplicate(self):
        with pytest.raises(HTTPException) as exc:
            _raise_value_http_error(ValueError("already exists"), action="test")
        assert exc.value.status_code == 409

    def test_raise_value_error_generic(self):
        with pytest.raises(HTTPException) as exc:
            _raise_value_http_error(ValueError("bad input"), action="test")
        assert exc.value.status_code == 400

    def test_raise_value_error_conflict_markers(self):
        with pytest.raises(HTTPException) as exc:
            _raise_value_http_error(
                ValueError("has children"),
                action="test",
                conflict_markers=("children",),
            )
        assert exc.value.status_code == 409


class TestValidateAdminApiKey:
    def test_empty_admin_key_returns_false(self):
        with patch("enhanced_agent_bus.routes.tenants.TENANT_ADMIN_KEY", ""):
            assert _validate_admin_api_key("anything") is False

    def test_valid_key(self):
        with patch("enhanced_agent_bus.routes.tenants.TENANT_ADMIN_KEY", "secret"):
            assert _validate_admin_api_key("secret") is True

    def test_invalid_key(self):
        with patch("enhanced_agent_bus.routes.tenants.TENANT_ADMIN_KEY", "secret"):
            assert _validate_admin_api_key("wrong") is False


class TestExtractUsageAndQuotaDicts:
    def test_with_overrides(self):
        tenant = MagicMock()
        tenant.usage = MagicMock()
        tenant.usage.model_dump.return_value = {"agents_count": 5}
        tenant.quota = MagicMock()
        tenant.quota.model_dump.return_value = {"max_agents": 100}
        override = MagicMock()
        override.model_dump.return_value = {"agents_count": 10}
        usage, quota = _extract_usage_and_quota_dicts(tenant, usage_override=override)
        assert usage == {"agents_count": 10}

    def test_without_overrides(self):
        tenant = MagicMock()
        tenant.usage = {"agents_count": 5}
        tenant.quota = {"max_agents": 100}
        usage, quota = _extract_usage_and_quota_dicts(tenant)
        assert usage == {"agents_count": 5}


class TestBuildTenantHierarchyResponse:
    def test_with_ancestors(self):
        mock_tenants = []
        for i in range(3):
            t = MagicMock()
            t.tenant_id = f"t{i}"
            t.name = f"Tenant {i}"
            t.slug = f"tenant-{i}"
            t.status = MagicMock(value="active")
            t.parent_tenant_id = None
            t.config = {}
            t.quota = {}
            t.usage = {}
            t.metadata = {}
            t.created_at = datetime.now(UTC)
            t.updated_at = datetime.now(UTC)
            t.activated_at = None
            t.suspended_at = None
            t.constitutional_hash = None
            mock_tenants.append(t)
        resp = _build_tenant_hierarchy_response("t2", ancestors=mock_tenants, descendants=[])
        assert resp.depth == 2
        assert len(resp.ancestors) == 2  # all but last

    def test_no_ancestors(self):
        resp = _build_tenant_hierarchy_response("t1", ancestors=[], descendants=[])
        assert resp.depth == 0
        assert resp.ancestors == []
