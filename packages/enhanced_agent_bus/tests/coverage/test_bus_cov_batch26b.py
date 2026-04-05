"""Coverage tests for src.core.shared.config.integrations and security.

Tests both the pydantic-settings branch (HAS_PYDANTIC_SETTINGS=True) and
the dataclass fallback branch (HAS_PYDANTIC_SETTINGS=False) for all
config classes.
"""

from __future__ import annotations

import importlib
import os
import sys
from unittest.mock import patch

import pytest
from pydantic import SecretStr, ValidationError

_PATCHED_MODS = (
    "src.core.shared.config.integrations",
    "src.core.shared.config.security",
)


@pytest.fixture(autouse=True)
def _restore_config_modules():
    """Ensure config modules are restored to pydantic-settings version after each test."""
    originals = {k: sys.modules.get(k) for k in _PATCHED_MODS}
    yield
    for mod_name, orig in originals.items():
        if orig is not None:
            sys.modules[mod_name] = orig
        else:
            sys.modules.pop(mod_name, None)


# ---------------------------------------------------------------------------
# Helpers to import modules under both branches
# ---------------------------------------------------------------------------


def _import_integrations_pydantic():
    """Import integrations module with pydantic_settings available (normal)."""
    mod_name = "src.core.shared.config.integrations"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    mod = importlib.import_module(mod_name)
    return mod


def _import_integrations_dataclass():
    """Import integrations module with pydantic_settings blocked."""
    mod_name = "src.core.shared.config.integrations"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    real_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__

    def fake_import(name, *args, **kwargs):
        if name == "pydantic_settings":
            raise ImportError("mocked")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake_import):
        mod = importlib.import_module(mod_name)
    return mod


def _import_security_pydantic():
    """Import security module with pydantic_settings available (normal)."""
    mod_name = "src.core.shared.config.security"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    mod = importlib.import_module(mod_name)
    return mod


def _import_security_dataclass():
    """Import security module with pydantic_settings blocked."""
    mod_name = "src.core.shared.config.security"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    real_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__

    def fake_import(name, *args, **kwargs):
        if name == "pydantic_settings":
            raise ImportError("mocked")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake_import):
        mod = importlib.import_module(mod_name)
    return mod


# ===================================================================
# INTEGRATIONS — pydantic-settings branch
# ===================================================================


class TestIntegrationsPydanticSettings:
    """Test integrations.py classes when pydantic_settings is available."""

    def test_has_pydantic_settings_flag(self):
        mod = _import_integrations_pydantic()
        assert mod.HAS_PYDANTIC_SETTINGS is True

    # -- ServiceSettings --------------------------------------------------

    def test_service_settings_defaults(self):
        mod = _import_integrations_pydantic()
        s = mod.ServiceSettings()
        assert s.agent_bus_url == "http://localhost:8000"
        assert s.policy_registry_url == "http://localhost:8000"
        assert s.api_gateway_url == "http://localhost:8080"
        assert s.tenant_management_url == "http://localhost:8500"
        assert s.hitl_approvals_url == "http://localhost:8200"
        assert s.ml_governance_url == "http://localhost:8400"
        assert s.compliance_docs_url == "http://localhost:8100"
        assert s.audit_service_url == "http://localhost:8300"

    def test_service_settings_from_env(self):
        mod = _import_integrations_pydantic()
        env = {
            "AGENT_BUS_URL": "http://bus:9000",
            "POLICY_REGISTRY_URL": "http://registry:9001",
            "API_GATEWAY_URL": "http://gw:9002",
            "TENANT_MANAGEMENT_URL": "http://tenant:9003",
            "HITL_APPROVALS_URL": "http://hitl:9004",
            "ML_GOVERNANCE_URL": "http://ml:9005",
            "COMPLIANCE_DOCS_URL": "http://docs:9006",
            "AUDIT_SERVICE_URL": "http://audit:9007",
        }
        with patch.dict(os.environ, env, clear=False):
            s = mod.ServiceSettings()
        assert s.agent_bus_url == "http://bus:9000"
        assert s.policy_registry_url == "http://registry:9001"
        assert s.api_gateway_url == "http://gw:9002"
        assert s.tenant_management_url == "http://tenant:9003"
        assert s.hitl_approvals_url == "http://hitl:9004"
        assert s.ml_governance_url == "http://ml:9005"
        assert s.compliance_docs_url == "http://docs:9006"
        assert s.audit_service_url == "http://audit:9007"

    # -- BundleSettings ---------------------------------------------------

    def test_bundle_settings_defaults(self):
        mod = _import_integrations_pydantic()
        s = mod.BundleSettings()
        assert s.registry_url == "http://localhost:5000"
        assert s.storage_path == "./storage/bundles"
        assert s.s3_bucket is None
        assert s.policy_public_key is None
        assert s.github_webhook_secret is None

    def test_bundle_settings_from_env(self):
        mod = _import_integrations_pydantic()
        env = {
            "BUNDLE_REGISTRY_URL": "http://reg:6000",
            "BUNDLE_STORAGE_PATH": "/opt/bundles",
            "BUNDLE_S3_BUCKET": "my-bucket",
            "POLICY_PUBLIC_KEY": "pk-abc",
            "GITHUB_WEBHOOK_SECRET": "ghsecret123",
        }
        with patch.dict(os.environ, env, clear=False):
            s = mod.BundleSettings()
        assert s.registry_url == "http://reg:6000"
        assert s.storage_path == "/opt/bundles"
        assert s.s3_bucket == "my-bucket"
        assert s.policy_public_key == "pk-abc"
        assert isinstance(s.github_webhook_secret, SecretStr)
        assert s.github_webhook_secret.get_secret_value() == "ghsecret123"

    # -- OpenCodeSettings -------------------------------------------------

    def test_opencode_settings_defaults(self):
        mod = _import_integrations_pydantic()
        s = mod.OpenCodeSettings()
        assert s.url == "http://localhost:4096"
        assert s.username == "opencode"
        assert s.password is None
        assert s.timeout_seconds == 30.0
        assert s.max_connections == 50
        assert s.max_retries == 3
        assert s.circuit_breaker_threshold == 5
        assert s.circuit_breaker_timeout == 60.0

    def test_opencode_settings_from_env(self):
        mod = _import_integrations_pydantic()
        env = {
            "OPENCODE_URL": "http://oc:5000",
            "OPENCODE_USERNAME": "admin",
            "OPENCODE_PASSWORD": "pass123",
            "OPENCODE_TIMEOUT": "60.0",
            "OPENCODE_MAX_CONNECTIONS": "200",
            "OPENCODE_MAX_RETRIES": "5",
            "OPENCODE_CIRCUIT_THRESHOLD": "10",
            "OPENCODE_CIRCUIT_TIMEOUT": "120.0",
        }
        with patch.dict(os.environ, env, clear=False):
            s = mod.OpenCodeSettings()
        assert s.url == "http://oc:5000"
        assert s.username == "admin"
        assert isinstance(s.password, SecretStr)
        assert s.password.get_secret_value() == "pass123"
        assert s.timeout_seconds == 60.0
        assert s.max_connections == 200
        assert s.max_retries == 5
        assert s.circuit_breaker_threshold == 10
        assert s.circuit_breaker_timeout == 120.0

    # -- SearchPlatformSettings -------------------------------------------

    def test_search_platform_defaults(self):
        mod = _import_integrations_pydantic()
        s = mod.SearchPlatformSettings()
        assert s.url == "http://localhost:9080"
        assert s.timeout_seconds == 30.0
        assert s.max_connections == 100
        assert s.max_retries == 3
        assert s.retry_delay_seconds == 1.0
        assert s.circuit_breaker_threshold == 5
        assert s.circuit_breaker_timeout == 30.0
        assert s.enable_compliance is True

    def test_search_platform_from_env(self):
        mod = _import_integrations_pydantic()
        env = {
            "SEARCH_PLATFORM_URL": "http://search:7000",
            "SEARCH_PLATFORM_TIMEOUT": "45.0",
            "SEARCH_PLATFORM_MAX_CONNECTIONS": "500",
            "SEARCH_PLATFORM_MAX_RETRIES": "7",
            "SEARCH_PLATFORM_RETRY_DELAY": "2.5",
            "SEARCH_PLATFORM_CIRCUIT_THRESHOLD": "15",
            "SEARCH_PLATFORM_CIRCUIT_TIMEOUT": "90.0",
            "SEARCH_PLATFORM_ENABLE_COMPLIANCE": "false",
        }
        with patch.dict(os.environ, env, clear=False):
            s = mod.SearchPlatformSettings()
        assert s.url == "http://search:7000"
        assert s.timeout_seconds == 45.0
        assert s.max_connections == 500
        assert s.max_retries == 7
        assert s.retry_delay_seconds == 2.5
        assert s.circuit_breaker_threshold == 15
        assert s.circuit_breaker_timeout == 90.0
        assert s.enable_compliance is False


# ===================================================================
# INTEGRATIONS — dataclass fallback branch
# ===================================================================


class TestIntegrationsDataclassFallback:
    """Test integrations.py classes when pydantic_settings is NOT available."""

    def test_has_pydantic_settings_false(self):
        mod = _import_integrations_dataclass()
        assert mod.HAS_PYDANTIC_SETTINGS is False

    # -- ServiceSettings --------------------------------------------------

    def test_service_settings_defaults(self):
        mod = _import_integrations_dataclass()
        s = mod.ServiceSettings()
        assert s.agent_bus_url == "http://localhost:8000"
        assert s.policy_registry_url == "http://localhost:8000"
        assert s.api_gateway_url == "http://localhost:8080"
        assert s.tenant_management_url == "http://localhost:8500"
        assert s.hitl_approvals_url == "http://localhost:8200"
        assert s.ml_governance_url == "http://localhost:8400"
        assert s.compliance_docs_url == "http://localhost:8100"
        assert s.audit_service_url == "http://localhost:8300"

    def test_service_settings_from_env(self):
        mod = _import_integrations_dataclass()
        env = {
            "AGENT_BUS_URL": "http://bus:1111",
            "POLICY_REGISTRY_URL": "http://reg:2222",
            "API_GATEWAY_URL": "http://gw:3333",
            "TENANT_MANAGEMENT_URL": "http://tm:4444",
            "HITL_APPROVALS_URL": "http://hitl:5555",
            "ML_GOVERNANCE_URL": "http://ml:6666",
            "COMPLIANCE_DOCS_URL": "http://cd:7777",
            "AUDIT_SERVICE_URL": "http://audit:8888",
        }
        with patch.dict(os.environ, env, clear=False):
            s = mod.ServiceSettings()
        assert s.agent_bus_url == "http://bus:1111"
        assert s.policy_registry_url == "http://reg:2222"
        assert s.api_gateway_url == "http://gw:3333"
        assert s.tenant_management_url == "http://tm:4444"
        assert s.hitl_approvals_url == "http://hitl:5555"
        assert s.ml_governance_url == "http://ml:6666"
        assert s.compliance_docs_url == "http://cd:7777"
        assert s.audit_service_url == "http://audit:8888"

    # -- BundleSettings ---------------------------------------------------

    def test_bundle_settings_defaults(self):
        mod = _import_integrations_dataclass()
        s = mod.BundleSettings()
        assert s.registry_url == "http://localhost:5000"
        assert s.storage_path == "./storage/bundles"
        assert s.s3_bucket is None
        assert s.policy_public_key is None
        assert s.github_webhook_secret is None

    def test_bundle_settings_from_env(self):
        mod = _import_integrations_dataclass()
        env = {
            "BUNDLE_REGISTRY_URL": "http://reg:6060",
            "BUNDLE_STORAGE_PATH": "/tmp/bundles",
            "BUNDLE_S3_BUCKET": "test-bucket",
            "POLICY_PUBLIC_KEY": "pk-xyz",
            "GITHUB_WEBHOOK_SECRET": "webhooksecret",
        }
        with patch.dict(os.environ, env, clear=False):
            s = mod.BundleSettings()
        assert s.registry_url == "http://reg:6060"
        assert s.storage_path == "/tmp/bundles"
        assert s.s3_bucket == "test-bucket"
        assert s.policy_public_key == "pk-xyz"
        assert isinstance(s.github_webhook_secret, SecretStr)
        assert s.github_webhook_secret.get_secret_value() == "webhooksecret"

    def test_bundle_settings_no_webhook_secret(self):
        """Webhook secret is None when env var not set."""
        mod = _import_integrations_dataclass()
        # Ensure env var is NOT set
        env_clear = {
            "GITHUB_WEBHOOK_SECRET": "",
            "BUNDLE_S3_BUCKET": "",
            "POLICY_PUBLIC_KEY": "",
        }
        with patch.dict(os.environ, {}, clear=False):
            for k in env_clear:
                os.environ.pop(k, None)
            s = mod.BundleSettings()
        assert s.github_webhook_secret is None
        assert s.s3_bucket is None
        assert s.policy_public_key is None

    # -- OpenCodeSettings -------------------------------------------------

    def test_opencode_settings_defaults(self):
        mod = _import_integrations_dataclass()
        s = mod.OpenCodeSettings()
        assert s.url == "http://localhost:4096"
        assert s.username == "opencode"
        assert s.password is None
        assert s.timeout_seconds == 30.0
        assert s.max_connections == 50
        assert s.max_retries == 3
        assert s.circuit_breaker_threshold == 5
        assert s.circuit_breaker_timeout == 60.0

    def test_opencode_settings_from_env(self):
        mod = _import_integrations_dataclass()
        env = {
            "OPENCODE_URL": "http://oc:4000",
            "OPENCODE_USERNAME": "root",
            "OPENCODE_PASSWORD": "secret",
            "OPENCODE_TIMEOUT": "99.9",
            "OPENCODE_MAX_CONNECTIONS": "999",
            "OPENCODE_MAX_RETRIES": "10",
            "OPENCODE_CIRCUIT_THRESHOLD": "20",
            "OPENCODE_CIRCUIT_TIMEOUT": "300.0",
        }
        with patch.dict(os.environ, env, clear=False):
            s = mod.OpenCodeSettings()
        assert s.url == "http://oc:4000"
        assert s.username == "root"
        assert isinstance(s.password, SecretStr)
        assert s.password.get_secret_value() == "secret"
        assert s.timeout_seconds == 99.9
        assert s.max_connections == 999
        assert s.max_retries == 10
        assert s.circuit_breaker_threshold == 20
        assert s.circuit_breaker_timeout == 300.0

    def test_opencode_no_password(self):
        """Password is None when env var not set."""
        mod = _import_integrations_dataclass()
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OPENCODE_PASSWORD", None)
            s = mod.OpenCodeSettings()
        assert s.password is None

    # -- SearchPlatformSettings -------------------------------------------

    def test_search_platform_defaults(self):
        mod = _import_integrations_dataclass()
        s = mod.SearchPlatformSettings()
        assert s.url == "http://localhost:9080"
        assert s.timeout_seconds == 30.0
        assert s.max_connections == 100
        assert s.max_retries == 3
        assert s.retry_delay_seconds == 1.0
        assert s.circuit_breaker_threshold == 5
        assert s.circuit_breaker_timeout == 30.0
        assert s.enable_compliance is True

    def test_search_platform_from_env(self):
        mod = _import_integrations_dataclass()
        env = {
            "SEARCH_PLATFORM_URL": "http://sp:7777",
            "SEARCH_PLATFORM_TIMEOUT": "120.0",
            "SEARCH_PLATFORM_MAX_CONNECTIONS": "1000",
            "SEARCH_PLATFORM_MAX_RETRIES": "12",
            "SEARCH_PLATFORM_RETRY_DELAY": "3.5",
            "SEARCH_PLATFORM_CIRCUIT_THRESHOLD": "25",
            "SEARCH_PLATFORM_CIRCUIT_TIMEOUT": "180.0",
            "SEARCH_PLATFORM_ENABLE_COMPLIANCE": "false",
        }
        with patch.dict(os.environ, env, clear=False):
            s = mod.SearchPlatformSettings()
        assert s.url == "http://sp:7777"
        assert s.timeout_seconds == 120.0
        assert s.max_connections == 1000
        assert s.max_retries == 12
        assert s.retry_delay_seconds == 3.5
        assert s.circuit_breaker_threshold == 25
        assert s.circuit_breaker_timeout == 180.0
        assert s.enable_compliance is False

    def test_search_platform_compliance_true_string(self):
        mod = _import_integrations_dataclass()
        with patch.dict(os.environ, {"SEARCH_PLATFORM_ENABLE_COMPLIANCE": "True"}, clear=False):
            s = mod.SearchPlatformSettings()
        assert s.enable_compliance is True


# ===================================================================
# SECURITY — pydantic-settings branch
# ===================================================================


class TestSecurityPydanticSettings:
    """Test security.py classes when pydantic_settings is available."""

    def test_has_pydantic_settings_flag(self):
        mod = _import_security_pydantic()
        assert mod.HAS_PYDANTIC_SETTINGS is True

    # -- SecuritySettings -------------------------------------------------

    def test_security_settings_defaults(self):
        mod = _import_security_pydantic()
        s = mod.SecuritySettings()
        assert s.api_key_internal is None
        assert s.jwt_secret is None
        assert s.jwt_public_key == "SYSTEM_PUBLIC_KEY_PLACEHOLDER"
        assert s.admin_api_key is None

    def test_security_settings_from_env(self):
        mod = _import_security_pydantic()
        env = {
            "API_KEY_INTERNAL": "a" * 40,
            "JWT_SECRET": "b" * 64,
            "JWT_PUBLIC_KEY": "my-pub-key",
            "ADMIN_API_KEY": "c" * 40,
        }
        with patch.dict(os.environ, env, clear=False):
            s = mod.SecuritySettings()
        assert isinstance(s.api_key_internal, SecretStr)
        assert s.api_key_internal.get_secret_value() == "a" * 40
        assert isinstance(s.jwt_secret, SecretStr)
        assert s.jwt_secret.get_secret_value() == "b" * 64
        assert s.jwt_public_key == "my-pub-key"
        assert isinstance(s.admin_api_key, SecretStr)
        assert s.admin_api_key.get_secret_value() == "c" * 40

    def test_security_settings_validator_placeholder_rejected(self):
        """Forbidden placeholder values must raise ValidationError."""
        mod = _import_security_pydantic()
        for placeholder in ["PLACEHOLDER", "CHANGE_ME", "DANGEROUS_DEFAULT", "dev-secret"]:
            with pytest.raises(ValidationError):
                with patch.dict(os.environ, {"JWT_SECRET": placeholder}, clear=False):
                    mod.SecuritySettings()

    def test_security_settings_validator_short_secret_allowed(self):
        """Short secrets pass the validator (just a warning path)."""
        mod = _import_security_pydantic()
        # Short but not a placeholder -- should be allowed (pass with warning)
        with patch.dict(os.environ, {"JWT_SECRET": "short-but-valid-value-ok"}, clear=False):
            s = mod.SecuritySettings()
        assert s.jwt_secret.get_secret_value() == "short-but-valid-value-ok"

    def test_security_settings_validator_none_passes(self):
        """None values pass validation when env vars not set."""
        mod = _import_security_pydantic()
        with patch.dict(os.environ, {}, clear=False):
            for k in ["JWT_SECRET", "API_KEY_INTERNAL"]:
                os.environ.pop(k, None)
            s = mod.SecuritySettings()
        assert s.jwt_secret is None
        assert s.api_key_internal is None

    # -- OPASettings ------------------------------------------------------

    def test_opa_settings_defaults(self):
        mod = _import_security_pydantic()
        s = mod.OPASettings()
        assert s.url == "http://localhost:8181"
        assert s.max_connections == 100
        assert s.mode == "http"
        assert s.fail_closed is True
        assert s.ssl_verify is True
        assert s.ssl_cert is None
        assert s.ssl_key is None

    def test_opa_settings_from_env(self):
        mod = _import_security_pydantic()
        env = {
            "OPA_URL": "http://opa:8282",
            "OPA_MAX_CONNECTIONS": "200",
            "OPA_MODE": "embedded",
            "OPA_SSL_VERIFY": "false",
            "OPA_SSL_CERT": "/certs/opa.crt",
            "OPA_SSL_KEY": "/certs/opa.key",
        }
        with patch.dict(os.environ, env, clear=False):
            s = mod.OPASettings()
        assert s.url == "http://opa:8282"
        assert s.max_connections == 200
        assert s.mode == "embedded"
        assert s.fail_closed is True  # always fail-closed
        assert s.ssl_verify is False
        assert s.ssl_cert == "/certs/opa.crt"
        assert s.ssl_key == "/certs/opa.key"

    # -- AuditSettings ----------------------------------------------------

    def test_audit_settings_defaults(self):
        mod = _import_security_pydantic()
        s = mod.AuditSettings()
        assert s.url == "http://localhost:8001"

    def test_audit_settings_from_env(self):
        mod = _import_security_pydantic()
        with patch.dict(os.environ, {"AUDIT_SERVICE_URL": "http://audit:9999"}, clear=False):
            s = mod.AuditSettings()
        assert s.url == "http://audit:9999"

    # -- VaultSettings ----------------------------------------------------

    def test_vault_settings_defaults(self):
        mod = _import_security_pydantic()
        s = mod.VaultSettings()
        assert s.address == "http://127.0.0.1:8200"
        assert s.token is None
        assert s.namespace is None
        assert s.transit_mount == "transit"
        assert s.kv_mount == "secret"
        assert s.kv_version == 2
        assert s.timeout == 30.0
        assert s.verify_tls is True
        assert s.ca_cert is None
        assert s.client_cert is None
        assert s.client_key is None

    def test_vault_settings_from_env(self):
        mod = _import_security_pydantic()
        env = {
            "VAULT_ADDR": "http://vault:8200",
            "VAULT_TOKEN": "hvs.test-token",
            "VAULT_NAMESPACE": "prod",
            "VAULT_TRANSIT_MOUNT": "my-transit",
            "VAULT_KV_MOUNT": "my-kv",
            "VAULT_KV_VERSION": "1",
            "VAULT_TIMEOUT": "15.0",
            "VAULT_VERIFY_TLS": "false",
            "VAULT_CACERT": "/certs/ca.pem",
            "VAULT_CLIENT_CERT": "/certs/client.pem",
            "VAULT_CLIENT_KEY": "/certs/client.key",
        }
        with patch.dict(os.environ, env, clear=False):
            s = mod.VaultSettings()
        assert s.address == "http://vault:8200"
        assert isinstance(s.token, SecretStr)
        assert s.token.get_secret_value() == "hvs.test-token"
        assert s.namespace == "prod"
        assert s.transit_mount == "my-transit"
        assert s.kv_mount == "my-kv"
        assert s.kv_version == 1
        assert s.timeout == 15.0
        assert s.verify_tls is False
        assert s.ca_cert == "/certs/ca.pem"
        assert s.client_cert == "/certs/client.pem"
        assert s.client_key == "/certs/client.key"

    # -- SSOSettings ------------------------------------------------------

    def test_sso_settings_defaults(self, monkeypatch: pytest.MonkeyPatch):
        mod = _import_security_pydantic()
        for env_var in (
            "SSO_ENABLED",
            "OIDC_ENABLED",
            "OIDC_CLIENT_ID",
            "OIDC_CLIENT_SECRET",
            "OIDC_ISSUER_URL",
            "OIDC_SCOPES",
            "OIDC_USE_PKCE",
            "SAML_ENABLED",
            "SAML_ENTITY_ID",
            "SAML_SIGN_REQUESTS",
            "SAML_WANT_ASSERTIONS_SIGNED",
            "SAML_WANT_ASSERTIONS_ENCRYPTED",
            "SAML_SP_CERTIFICATE",
            "SAML_SP_PRIVATE_KEY",
            "SAML_IDP_METADATA_URL",
            "SAML_IDP_SSO_URL",
            "SAML_IDP_SLO_URL",
            "SAML_IDP_CERTIFICATE",
            "SSO_AUTO_PROVISION",
            "SSO_DEFAULT_ROLE",
            "SSO_ALLOWED_DOMAINS",
            "WORKOS_ENABLED",
            "WORKOS_API_BASE_URL",
            "WORKOS_CLIENT_ID",
            "WORKOS_API_KEY",
            "WORKOS_WEBHOOK_SECRET",
            "WORKOS_WEBHOOK_DEDUPE_TTL_SECONDS",
            "WORKOS_WEBHOOK_FAIL_CLOSED",
            "WORKOS_PORTAL_DEFAULT_INTENT",
            "WORKOS_PORTAL_RETURN_URL",
            "WORKOS_PORTAL_SUCCESS_URL",
        ):
            monkeypatch.delenv(env_var, raising=False)
        s = mod.SSOSettings()
        assert s.enabled is True
        assert s.session_lifetime_seconds == 3600
        assert s.oidc_enabled is True
        assert s.oidc_client_id is None
        assert s.oidc_client_secret is None
        assert s.oidc_issuer_url is None
        assert s.oidc_scopes == ["openid", "email", "profile"]
        assert s.oidc_use_pkce is True
        assert s.saml_enabled is True
        assert s.saml_entity_id is None
        assert s.saml_sign_requests is True
        assert s.saml_want_assertions_signed is True
        assert s.saml_want_assertions_encrypted is False
        assert s.saml_sp_certificate is None
        assert s.saml_sp_private_key is None
        assert s.saml_idp_metadata_url is None
        assert s.saml_idp_sso_url is None
        assert s.saml_idp_slo_url is None
        assert s.saml_idp_certificate is None
        assert s.auto_provision_users is True
        assert s.default_role_on_provision == "viewer"
        assert s.allowed_domains is None
        assert s.workos_enabled is False
        assert s.workos_api_base_url == "https://api.workos.com"
        assert s.workos_client_id is None
        assert s.workos_api_key is None
        assert s.workos_webhook_secret is None
        assert s.workos_webhook_dedupe_ttl_seconds == 86400
        assert s.workos_webhook_fail_closed is True
        assert s.workos_portal_default_intent == "sso"
        assert s.workos_portal_return_url is None
        assert s.workos_portal_success_url is None
        assert s.trusted_hosts == ["localhost", "127.0.0.1"]

    def test_sso_settings_from_env(self):
        mod = _import_security_pydantic()
        env = {
            "SSO_ENABLED": "false",
            "SSO_SESSION_LIFETIME": "7200",
            "OIDC_ENABLED": "false",
            "OIDC_CLIENT_ID": "my-client",
            "OIDC_CLIENT_SECRET": "oidc-secret",
            "OIDC_ISSUER_URL": "https://issuer.example.com",
            "OIDC_USE_PKCE": "false",
            "SAML_ENABLED": "false",
            "SAML_ENTITY_ID": "urn:myapp",
            "SAML_SIGN_REQUESTS": "false",
            "SAML_WANT_ASSERTIONS_SIGNED": "false",
            "SAML_WANT_ASSERTIONS_ENCRYPTED": "true",
            "SAML_SP_CERTIFICATE": "sp-cert-data",
            "SAML_SP_PRIVATE_KEY": "sp-key-data",
            "SAML_IDP_METADATA_URL": "https://idp.example.com/metadata",
            "SAML_IDP_SSO_URL": "https://idp.example.com/sso",
            "SAML_IDP_SLO_URL": "https://idp.example.com/slo",
            "SAML_IDP_CERTIFICATE": "idp-cert-data",
            "SSO_AUTO_PROVISION": "false",
            "SSO_DEFAULT_ROLE": "admin",
            "WORKOS_ENABLED": "true",
            "WORKOS_API_BASE_URL": "https://custom.workos.com",
            "WORKOS_CLIENT_ID": "wos-client",
            "WORKOS_API_KEY": "wos-api-key",
            "WORKOS_WEBHOOK_SECRET": "wos-webhook",
            "WORKOS_WEBHOOK_DEDUPE_TTL_SECONDS": "43200",
            "WORKOS_WEBHOOK_FAIL_CLOSED": "false",
            "WORKOS_PORTAL_DEFAULT_INTENT": "dsync",
            "WORKOS_PORTAL_RETURN_URL": "https://app/return",
            "WORKOS_PORTAL_SUCCESS_URL": "https://app/success",
        }
        with patch.dict(os.environ, env, clear=False):
            s = mod.SSOSettings()
        assert s.enabled is False
        assert s.session_lifetime_seconds == 7200
        assert s.oidc_enabled is False
        assert s.oidc_client_id == "my-client"
        assert isinstance(s.oidc_client_secret, SecretStr)
        assert s.oidc_client_secret.get_secret_value() == "oidc-secret"
        assert s.oidc_issuer_url == "https://issuer.example.com"
        assert s.oidc_use_pkce is False
        assert s.saml_enabled is False
        assert s.saml_entity_id == "urn:myapp"
        assert s.saml_sign_requests is False
        assert s.saml_want_assertions_signed is False
        assert s.saml_want_assertions_encrypted is True
        assert s.saml_sp_certificate == "sp-cert-data"
        assert isinstance(s.saml_sp_private_key, SecretStr)
        assert s.saml_sp_private_key.get_secret_value() == "sp-key-data"
        assert s.saml_idp_metadata_url == "https://idp.example.com/metadata"
        assert s.saml_idp_sso_url == "https://idp.example.com/sso"
        assert s.saml_idp_slo_url == "https://idp.example.com/slo"
        assert s.saml_idp_certificate == "idp-cert-data"
        assert s.auto_provision_users is False
        assert s.default_role_on_provision == "admin"
        assert s.workos_enabled is True
        assert s.workos_api_base_url == "https://custom.workos.com"
        assert s.workos_client_id == "wos-client"
        assert isinstance(s.workos_api_key, SecretStr)
        assert s.workos_api_key.get_secret_value() == "wos-api-key"
        assert isinstance(s.workos_webhook_secret, SecretStr)
        assert s.workos_webhook_secret.get_secret_value() == "wos-webhook"
        assert s.workos_webhook_dedupe_ttl_seconds == 43200
        assert s.workos_webhook_fail_closed is False
        assert s.workos_portal_default_intent == "dsync"
        assert s.workos_portal_return_url == "https://app/return"
        assert s.workos_portal_success_url == "https://app/success"


# ===================================================================
# SECURITY — dataclass fallback branch
# ===================================================================


class TestSecurityDataclassFallback:
    """Test security.py classes when pydantic_settings is NOT available."""

    def test_has_pydantic_settings_false(self):
        mod = _import_security_dataclass()
        assert mod.HAS_PYDANTIC_SETTINGS is False

    # -- SecuritySettings -------------------------------------------------

    def test_security_settings_defaults(self):
        mod = _import_security_dataclass()
        s = mod.SecuritySettings()
        assert s.api_key_internal is None
        assert s.jwt_secret is None
        assert s.jwt_public_key == "SYSTEM_PUBLIC_KEY_PLACEHOLDER"
        assert s.admin_api_key is None

    def test_security_settings_from_env(self):
        mod = _import_security_dataclass()
        env = {
            "API_KEY_INTERNAL": "int-key",
            "JWT_SECRET": "jwt-secret-value",
            "JWT_PUBLIC_KEY": "pub-key-123",
            "ADMIN_API_KEY": "admin-key-val",
            "CORS_ORIGINS": "http://a.com,http://b.com",
        }
        with patch.dict(os.environ, env, clear=False):
            s = mod.SecuritySettings()
        assert isinstance(s.api_key_internal, SecretStr)
        assert s.api_key_internal.get_secret_value() == "int-key"
        assert isinstance(s.jwt_secret, SecretStr)
        assert s.jwt_secret.get_secret_value() == "jwt-secret-value"
        assert s.jwt_public_key == "pub-key-123"
        assert isinstance(s.admin_api_key, SecretStr)
        assert s.admin_api_key.get_secret_value() == "admin-key-val"
        assert s.cors_origins == ["http://a.com", "http://b.com"]

    def test_security_settings_cors_default(self):
        mod = _import_security_dataclass()
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CORS_ORIGINS", None)
            s = mod.SecuritySettings()
        assert s.cors_origins == ["*"]

    def test_security_settings_no_secrets(self):
        """All SecretStr fields are None when env vars not set."""
        mod = _import_security_dataclass()
        with patch.dict(os.environ, {}, clear=False):
            for k in ["API_KEY_INTERNAL", "JWT_SECRET", "ADMIN_API_KEY"]:
                os.environ.pop(k, None)
            s = mod.SecuritySettings()
        assert s.api_key_internal is None
        assert s.jwt_secret is None
        assert s.admin_api_key is None

    # -- OPASettings (dataclass) ------------------------------------------

    def test_opa_settings_defaults(self):
        mod = _import_security_dataclass()
        s = mod.OPASettings()
        assert s.url == "http://localhost:8181"
        assert s.mode == "http"
        assert s.fail_closed is True
        assert s.ssl_verify is True
        assert s.ssl_cert is None
        assert s.ssl_key is None

    def test_opa_settings_from_env(self):
        mod = _import_security_dataclass()
        env = {
            "OPA_URL": "http://opa-dc:8282",
            "OPA_MODE": "fallback",
            "OPA_SSL_VERIFY": "false",
            "OPA_SSL_CERT": "/dc/opa.crt",
            "OPA_SSL_KEY": "/dc/opa.key",
        }
        with patch.dict(os.environ, env, clear=False):
            s = mod.OPASettings()
        assert s.url == "http://opa-dc:8282"
        assert s.mode == "fallback"
        assert s.fail_closed is True  # always true
        assert s.ssl_verify is False
        assert s.ssl_cert == "/dc/opa.crt"
        assert s.ssl_key == "/dc/opa.key"

    # -- AuditSettings (dataclass) ----------------------------------------

    def test_audit_settings_defaults(self):
        mod = _import_security_dataclass()
        s = mod.AuditSettings()
        assert s.url == "http://localhost:8001"

    def test_audit_settings_from_env(self):
        mod = _import_security_dataclass()
        with patch.dict(os.environ, {"AUDIT_SERVICE_URL": "http://dc-audit:9001"}, clear=False):
            s = mod.AuditSettings()
        assert s.url == "http://dc-audit:9001"

    # -- VaultSettings (dataclass) ----------------------------------------

    def test_vault_settings_defaults(self):
        mod = _import_security_dataclass()
        s = mod.VaultSettings()
        assert s.address == "http://127.0.0.1:8200"
        assert s.token is None
        assert s.namespace is None
        assert s.transit_mount == "transit"
        assert s.kv_mount == "secret"
        assert s.kv_version == 2
        assert s.timeout == 30.0
        assert s.verify_tls is True
        assert s.ca_cert is None
        assert s.client_cert is None
        assert s.client_key is None

    def test_vault_settings_from_env(self):
        mod = _import_security_dataclass()
        env = {
            "VAULT_ADDR": "http://dc-vault:8200",
            "VAULT_TOKEN": "dc-token",
            "VAULT_NAMESPACE": "staging",
            "VAULT_TRANSIT_MOUNT": "dc-transit",
            "VAULT_KV_MOUNT": "dc-kv",
            "VAULT_KV_VERSION": "1",
            "VAULT_TIMEOUT": "10.0",
            "VAULT_VERIFY_TLS": "false",
            "VAULT_CACERT": "/dc/ca.pem",
            "VAULT_CLIENT_CERT": "/dc/client.pem",
            "VAULT_CLIENT_KEY": "/dc/client.key",
        }
        with patch.dict(os.environ, env, clear=False):
            s = mod.VaultSettings()
        assert s.address == "http://dc-vault:8200"
        assert isinstance(s.token, SecretStr)
        assert s.token.get_secret_value() == "dc-token"
        assert s.namespace == "staging"
        assert s.transit_mount == "dc-transit"
        assert s.kv_mount == "dc-kv"
        assert s.kv_version == 1
        assert s.timeout == 10.0
        assert s.verify_tls is False
        assert s.ca_cert == "/dc/ca.pem"
        assert s.client_cert == "/dc/client.pem"
        assert s.client_key == "/dc/client.key"

    def test_vault_settings_no_token(self):
        mod = _import_security_dataclass()
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("VAULT_TOKEN", None)
            s = mod.VaultSettings()
        assert s.token is None

    # -- SSOSettings (dataclass) ------------------------------------------

    def test_sso_settings_defaults(self, monkeypatch: pytest.MonkeyPatch):
        mod = _import_security_dataclass()
        for env_var in (
            "SSO_ENABLED",
            "OIDC_ENABLED",
            "OIDC_CLIENT_ID",
            "OIDC_CLIENT_SECRET",
            "OIDC_ISSUER_URL",
            "OIDC_SCOPES",
            "OIDC_USE_PKCE",
            "SAML_ENABLED",
            "SAML_ENTITY_ID",
            "SAML_SIGN_REQUESTS",
            "SAML_WANT_ASSERTIONS_SIGNED",
            "SAML_WANT_ASSERTIONS_ENCRYPTED",
            "SAML_SP_CERTIFICATE",
            "SAML_SP_PRIVATE_KEY",
            "SAML_IDP_METADATA_URL",
            "SAML_IDP_SSO_URL",
            "SAML_IDP_SLO_URL",
            "SAML_IDP_CERTIFICATE",
            "SSO_AUTO_PROVISION",
            "SSO_DEFAULT_ROLE",
            "SSO_ALLOWED_DOMAINS",
            "WORKOS_ENABLED",
            "WORKOS_API_BASE_URL",
            "WORKOS_CLIENT_ID",
            "WORKOS_API_KEY",
            "WORKOS_WEBHOOK_SECRET",
            "WORKOS_WEBHOOK_DEDUPE_TTL_SECONDS",
            "WORKOS_WEBHOOK_FAIL_CLOSED",
            "WORKOS_PORTAL_DEFAULT_INTENT",
            "WORKOS_PORTAL_RETURN_URL",
            "WORKOS_PORTAL_SUCCESS_URL",
        ):
            monkeypatch.delenv(env_var, raising=False)
        s = mod.SSOSettings()
        assert s.enabled is True
        assert s.session_lifetime_seconds == 3600
        assert s.oidc_enabled is True
        assert s.oidc_client_id is None
        assert s.oidc_client_secret is None
        assert s.oidc_issuer_url is None
        assert s.oidc_scopes == ["openid", "email", "profile"]
        assert s.oidc_use_pkce is True
        assert s.saml_enabled is True
        assert s.saml_entity_id is None
        assert s.saml_sign_requests is True
        assert s.saml_want_assertions_signed is True
        assert s.saml_want_assertions_encrypted is False
        assert s.saml_sp_certificate is None
        assert s.saml_sp_private_key is None
        assert s.saml_idp_metadata_url is None
        assert s.saml_idp_sso_url is None
        assert s.saml_idp_slo_url is None
        assert s.saml_idp_certificate is None
        assert s.auto_provision_users is True
        assert s.default_role_on_provision == "viewer"
        assert s.allowed_domains is None
        assert s.workos_enabled is False
        assert s.workos_api_base_url == "https://api.workos.com"
        assert s.workos_client_id is None
        assert s.workos_api_key is None
        assert s.workos_webhook_secret is None
        assert s.workos_webhook_dedupe_ttl_seconds == 86400
        assert s.workos_webhook_fail_closed is False  # dataclass default differs
        assert s.workos_portal_default_intent == "sso"
        assert s.workos_portal_return_url is None
        assert s.workos_portal_success_url is None

    def test_sso_settings_from_env(self):
        mod = _import_security_dataclass()
        env = {
            "SSO_ENABLED": "false",
            "SSO_SESSION_LIFETIME": "1800",
            "OIDC_ENABLED": "false",
            "OIDC_CLIENT_ID": "dc-client",
            "OIDC_CLIENT_SECRET": "dc-oidc-secret",
            "OIDC_ISSUER_URL": "https://dc-issuer.example.com",
            "OIDC_SCOPES": "openid,profile",
            "OIDC_USE_PKCE": "false",
            "SAML_ENABLED": "false",
            "SAML_ENTITY_ID": "urn:dc-app",
            "SAML_SIGN_REQUESTS": "false",
            "SAML_WANT_ASSERTIONS_SIGNED": "false",
            "SAML_WANT_ASSERTIONS_ENCRYPTED": "true",
            "SAML_SP_CERTIFICATE": "dc-sp-cert",
            "SAML_SP_PRIVATE_KEY": "dc-sp-key",
            "SAML_IDP_METADATA_URL": "https://dc-idp/meta",
            "SAML_IDP_SSO_URL": "https://dc-idp/sso",
            "SAML_IDP_SLO_URL": "https://dc-idp/slo",
            "SAML_IDP_CERTIFICATE": "dc-idp-cert",
            "SSO_AUTO_PROVISION": "false",
            "SSO_DEFAULT_ROLE": "editor",
            "SSO_ALLOWED_DOMAINS": "a.com,b.com",
            "WORKOS_ENABLED": "true",
            "WORKOS_API_BASE_URL": "https://dc.workos.com",
            "WORKOS_CLIENT_ID": "dc-wos-client",
            "WORKOS_API_KEY": "dc-wos-key",
            "WORKOS_WEBHOOK_SECRET": "dc-wos-webhook",
            "WORKOS_WEBHOOK_DEDUPE_TTL_SECONDS": "10000",
            "WORKOS_WEBHOOK_FAIL_CLOSED": "true",
            "WORKOS_PORTAL_DEFAULT_INTENT": "dsync",
            "WORKOS_PORTAL_RETURN_URL": "https://dc/return",
            "WORKOS_PORTAL_SUCCESS_URL": "https://dc/success",
        }
        with patch.dict(os.environ, env, clear=False):
            s = mod.SSOSettings()
        assert s.enabled is False
        assert s.session_lifetime_seconds == 1800
        assert s.oidc_enabled is False
        assert s.oidc_client_id == "dc-client"
        assert isinstance(s.oidc_client_secret, SecretStr)
        assert s.oidc_client_secret.get_secret_value() == "dc-oidc-secret"
        assert s.oidc_issuer_url == "https://dc-issuer.example.com"
        assert s.oidc_scopes == ["openid", "profile"]
        assert s.oidc_use_pkce is False
        assert s.saml_enabled is False
        assert s.saml_entity_id == "urn:dc-app"
        assert s.saml_sign_requests is False
        assert s.saml_want_assertions_signed is False
        assert s.saml_want_assertions_encrypted is True
        assert s.saml_sp_certificate == "dc-sp-cert"
        assert isinstance(s.saml_sp_private_key, SecretStr)
        assert s.saml_sp_private_key.get_secret_value() == "dc-sp-key"
        assert s.saml_idp_metadata_url == "https://dc-idp/meta"
        assert s.saml_idp_sso_url == "https://dc-idp/sso"
        assert s.saml_idp_slo_url == "https://dc-idp/slo"
        assert s.saml_idp_certificate == "dc-idp-cert"
        assert s.auto_provision_users is False
        assert s.default_role_on_provision == "editor"
        assert s.allowed_domains == ["a.com", "b.com"]
        assert s.workos_enabled is True
        assert s.workos_api_base_url == "https://dc.workos.com"
        assert s.workos_client_id == "dc-wos-client"
        assert isinstance(s.workos_api_key, SecretStr)
        assert s.workos_api_key.get_secret_value() == "dc-wos-key"
        assert isinstance(s.workos_webhook_secret, SecretStr)
        assert s.workos_webhook_secret.get_secret_value() == "dc-wos-webhook"
        assert s.workos_webhook_dedupe_ttl_seconds == 10000
        assert s.workos_webhook_fail_closed is True
        assert s.workos_portal_default_intent == "dsync"
        assert s.workos_portal_return_url == "https://dc/return"
        assert s.workos_portal_success_url == "https://dc/success"

    def test_sso_no_secrets(self):
        """SecretStr fields are None when env vars not set."""
        mod = _import_security_dataclass()
        with patch.dict(os.environ, {}, clear=False):
            for k in [
                "OIDC_CLIENT_SECRET",
                "SAML_SP_PRIVATE_KEY",
                "WORKOS_API_KEY",
                "WORKOS_WEBHOOK_SECRET",
            ]:
                os.environ.pop(k, None)
            s = mod.SSOSettings()
        assert s.oidc_client_secret is None
        assert s.saml_sp_private_key is None
        assert s.workos_api_key is None
        assert s.workos_webhook_secret is None

    def test_sso_allowed_domains_none(self):
        """allowed_domains is None when env var not set."""
        mod = _import_security_dataclass()
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SSO_ALLOWED_DOMAINS", None)
            s = mod.SSOSettings()
        assert s.allowed_domains is None
