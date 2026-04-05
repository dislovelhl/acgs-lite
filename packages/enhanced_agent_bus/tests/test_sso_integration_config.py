"""Tests for enterprise_sso/integration_config.py.

Covers IntegrationConfig serialization, EncryptionService local encrypt/decrypt,
IntegrationHealthChecker, IntegrationAuditService, and IntegrationConfigService CRUD,
connectivity testing, and health monitoring.
"""

import pytest

from enhanced_agent_bus.enterprise_sso.integration_config import (
    EncryptionService,
    IntegrationAuditService,
    IntegrationConfig,
    IntegrationConfigService,
    IntegrationHealthChecker,
    IntegrationStatus,
    IntegrationType,
)

# ---------------------------------------------------------------------------
# IntegrationConfig dataclass
# ---------------------------------------------------------------------------


class TestIntegrationConfig:
    def test_to_dict_redacts_sensitive(self):
        cfg = IntegrationConfig(
            id="int-1",
            tenant_id="t1",
            integration_type=IntegrationType.LDAP,
            name="Test LDAP",
            config={"host": "ldap.example.com", "password": "secret123"},
            encrypted_fields={"password"},
        )
        result = cfg.to_dict(redact_sensitive=True)
        assert result["config"]["password"] == "********"
        assert result["config"]["host"] == "ldap.example.com"
        assert result["integration_type"] == "ldap"
        assert result["id"] == "int-1"

    def test_to_dict_no_redaction(self):
        cfg = IntegrationConfig(
            id="int-2",
            tenant_id="t1",
            integration_type=IntegrationType.SAML,
            name="SAML IDP",
            config={"secret": "plain"},
            encrypted_fields={"secret"},
        )
        result = cfg.to_dict(redact_sensitive=False)
        assert result["config"]["secret"] == "plain"

    def test_default_status_is_pending(self):
        cfg = IntegrationConfig(
            id="int-3",
            tenant_id="t1",
            integration_type=IntegrationType.OIDC,
            name="OIDC",
            config={},
        )
        assert cfg.status == IntegrationStatus.PENDING

    def test_to_dict_has_constitutional_hash(self):
        cfg = IntegrationConfig(
            id="int-4",
            tenant_id="t1",
            integration_type=IntegrationType.KAFKA,
            name="Kafka",
            config={},
        )
        result = cfg.to_dict()
        assert "constitutional_hash" in result


# ---------------------------------------------------------------------------
# EncryptionService
# ---------------------------------------------------------------------------


class TestEncryptionService:
    @pytest.mark.asyncio
    async def test_local_encrypt_decrypt_roundtrip(self):
        svc = EncryptionService()
        encrypted = await svc.encrypt("hello world")
        assert "ciphertext" in encrypted
        assert "key_id" in encrypted
        decrypted = await svc.decrypt(encrypted["ciphertext"])
        assert decrypted == "hello world"

    @pytest.mark.asyncio
    async def test_local_encrypt_different_inputs(self):
        svc = EncryptionService()
        e1 = await svc.encrypt("aaa")
        e2 = await svc.encrypt("bbb")
        assert e1["ciphertext"] != e2["ciphertext"]

    @pytest.mark.asyncio
    async def test_local_encrypt_empty_string(self):
        svc = EncryptionService()
        encrypted = await svc.encrypt("")
        decrypted = await svc.decrypt(encrypted["ciphertext"])
        assert decrypted == ""

    @pytest.mark.asyncio
    async def test_local_key_id(self):
        svc = EncryptionService()
        encrypted = await svc.encrypt("test")
        assert encrypted["key_id"] == "local-dev-key"


# ---------------------------------------------------------------------------
# IntegrationHealthChecker
# ---------------------------------------------------------------------------


class TestIntegrationHealthChecker:
    @pytest.mark.asyncio
    async def test_check_all_types(self):
        checker = IntegrationHealthChecker()
        for itype in IntegrationType:
            result = await checker.check_health(itype, {})
            assert result["healthy"] is True
            assert "message" in result

    @pytest.mark.asyncio
    async def test_check_ldap(self):
        checker = IntegrationHealthChecker()
        result = await checker.check_ldap({})
        assert result["healthy"] is True

    @pytest.mark.asyncio
    async def test_check_kafka(self):
        checker = IntegrationHealthChecker()
        result = await checker.check_kafka({})
        assert result["healthy"] is True


# ---------------------------------------------------------------------------
# IntegrationAuditService
# ---------------------------------------------------------------------------


class TestIntegrationAuditService:
    def test_log_creates_entry(self):
        audit = IntegrationAuditService()
        entry = audit.log("create", "t1", "int-1", actor="admin")
        assert entry["action"] == "create"
        assert entry["tenant_id"] == "t1"
        assert entry["integration_id"] == "int-1"
        assert "timestamp" in entry

    def test_get_logs_no_filter(self):
        audit = IntegrationAuditService()
        audit.log("create", "t1", "int-1")
        audit.log("update", "t2", "int-2")
        logs = audit.get_logs()
        assert len(logs) == 2

    def test_get_logs_filter_tenant(self):
        audit = IntegrationAuditService()
        audit.log("create", "t1", "int-1")
        audit.log("update", "t2", "int-2")
        logs = audit.get_logs(tenant_id="t1")
        assert len(logs) == 1
        assert logs[0]["tenant_id"] == "t1"

    def test_get_logs_filter_integration(self):
        audit = IntegrationAuditService()
        audit.log("create", "t1", "int-1")
        audit.log("update", "t1", "int-2")
        logs = audit.get_logs(integration_id="int-2")
        assert len(logs) == 1


# ---------------------------------------------------------------------------
# IntegrationConfigService
# ---------------------------------------------------------------------------


class TestIntegrationConfigService:
    @pytest.mark.asyncio
    async def test_create_integration(self):
        svc = IntegrationConfigService()
        result = await svc.create_integration(
            tenant_id="t1",
            integration_type=IntegrationType.LDAP,
            name="Test LDAP",
            config={"host": "ldap.example.com", "password": "secret"},
            created_by="admin",
        )
        assert result.id == "int-1"
        assert result.tenant_id == "t1"
        assert result.integration_type == IntegrationType.LDAP
        assert "password" in result.encrypted_fields

    @pytest.mark.asyncio
    async def test_get_integration(self):
        svc = IntegrationConfigService()
        created = await svc.create_integration("t1", IntegrationType.SAML, "SAML", {})
        fetched = svc.get_integration(created.id)
        assert fetched is not None
        assert fetched.name == "SAML"

    @pytest.mark.asyncio
    async def test_get_integration_tenant_isolation(self):
        svc = IntegrationConfigService()
        created = await svc.create_integration("t1", IntegrationType.SAML, "SAML", {})
        # Wrong tenant
        assert svc.get_integration(created.id, tenant_id="t2") is None

    @pytest.mark.asyncio
    async def test_list_integrations(self):
        svc = IntegrationConfigService()
        await svc.create_integration("t1", IntegrationType.LDAP, "LDAP A", {})
        await svc.create_integration("t1", IntegrationType.SAML, "SAML B", {})
        await svc.create_integration("t2", IntegrationType.OIDC, "OIDC C", {})

        t1_list = svc.list_integrations("t1")
        assert len(t1_list) == 2

    @pytest.mark.asyncio
    async def test_list_integrations_filter_type(self):
        svc = IntegrationConfigService()
        await svc.create_integration("t1", IntegrationType.LDAP, "A", {})
        await svc.create_integration("t1", IntegrationType.SAML, "B", {})

        ldap_only = svc.list_integrations("t1", integration_type=IntegrationType.LDAP)
        assert len(ldap_only) == 1

    @pytest.mark.asyncio
    async def test_update_integration(self):
        svc = IntegrationConfigService()
        created = await svc.create_integration("t1", IntegrationType.LDAP, "Old", {})
        updated = await svc.update_integration(
            created.id, "t1", {"name": "New", "enabled": False}, updated_by="admin"
        )
        assert updated is not None
        assert updated.name == "New"
        assert updated.enabled is False

    @pytest.mark.asyncio
    async def test_update_nonexistent(self):
        svc = IntegrationConfigService()
        result = await svc.update_integration("int-999", "t1", {"name": "x"})
        assert result is None

    @pytest.mark.asyncio
    async def test_update_config_encrypts_sensitive(self):
        svc = IntegrationConfigService()
        created = await svc.create_integration("t1", IntegrationType.LDAP, "LDAP", {})
        await svc.update_integration(created.id, "t1", {"config": {"api_key": "new-key-value"}})
        assert "api_key" in created.encrypted_fields

    @pytest.mark.asyncio
    async def test_delete_integration(self):
        svc = IntegrationConfigService()
        created = await svc.create_integration("t1", IntegrationType.KAFKA, "Kafka", {})
        assert await svc.delete_integration(created.id, "t1", deleted_by="admin") is True
        assert svc.get_integration(created.id) is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self):
        svc = IntegrationConfigService()
        assert await svc.delete_integration("nope", "t1") is False

    @pytest.mark.asyncio
    async def test_test_connectivity(self):
        svc = IntegrationConfigService()
        created = await svc.create_integration("t1", IntegrationType.LDAP, "LDAP", {})
        result = await svc.test_connectivity(created.id, "t1")
        assert result["success"] is True
        assert created.status == IntegrationStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_test_connectivity_not_found(self):
        svc = IntegrationConfigService()
        result = await svc.test_connectivity("nope", "t1")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_check_all_health(self):
        svc = IntegrationConfigService()
        await svc.create_integration("t1", IntegrationType.LDAP, "LDAP", {})
        await svc.create_integration("t1", IntegrationType.SAML, "SAML", {})
        results = await svc.check_all_health("t1")
        assert len(results) == 2

    def test_get_health_summary(self):
        svc = IntegrationConfigService()
        summary = svc.get_health_summary("t1")
        assert summary["total"] == 0
        assert "constitutional_hash" in summary

    def test_is_sensitive_field(self):
        svc = IntegrationConfigService()
        assert svc._is_sensitive_field("password") is True
        assert svc._is_sensitive_field("db_password") is True
        assert svc._is_sensitive_field("api_key") is True
        assert svc._is_sensitive_field("hostname") is False

    @pytest.mark.asyncio
    async def test_get_audit_logs(self):
        svc = IntegrationConfigService()
        await svc.create_integration("t1", IntegrationType.LDAP, "LDAP", {})
        logs = svc.get_audit_logs("t1")
        assert len(logs) >= 1

    def test_invalid_constitutional_hash_raises(self):
        with pytest.raises(ValueError, match="Invalid constitutional hash"):
            IntegrationConfigService(constitutional_hash="wrong")

    @pytest.mark.asyncio
    async def test_update_status_field(self):
        svc = IntegrationConfigService()
        created = await svc.create_integration("t1", IntegrationType.LDAP, "LDAP", {})
        updated = await svc.update_integration(created.id, "t1", {"status": "active"})
        assert updated is not None
        assert updated.status == IntegrationStatus.ACTIVE
