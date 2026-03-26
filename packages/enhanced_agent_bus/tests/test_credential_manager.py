"""Tests for enhanced_agent_bus.mcp_integration.auth.credential_manager.

Covers: Credential, CredentialType, CredentialScope, CredentialStatus,
CredentialManager (store, get, list, rotate, revoke, delete, inject, load,
get_stats), ToolCredential bindings, encryption.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from enhanced_agent_bus.mcp_integration.auth.credential_manager import (
    Credential,
    CredentialManager,
    CredentialManagerConfig,
    CredentialScope,
    CredentialStatus,
    CredentialType,
    ToolCredential,
)


# ---------------------------------------------------------------------------
# Credential dataclass
# ---------------------------------------------------------------------------
class TestCredential:
    def test_is_expired_no_expiry(self):
        cred = Credential(
            credential_id="c1",
            name="test",
            credential_type=CredentialType.API_KEY,
            scope=CredentialScope.GLOBAL,
        )
        assert cred.is_expired() is False

    def test_is_expired_past(self):
        cred = Credential(
            credential_id="c1",
            name="test",
            credential_type=CredentialType.API_KEY,
            scope=CredentialScope.GLOBAL,
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        assert cred.is_expired() is True

    def test_is_expired_future(self):
        cred = Credential(
            credential_id="c1",
            name="test",
            credential_type=CredentialType.API_KEY,
            scope=CredentialScope.GLOBAL,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        assert cred.is_expired() is False

    def test_needs_rotation_no_interval(self):
        cred = Credential(
            credential_id="c1",
            name="test",
            credential_type=CredentialType.API_KEY,
            scope=CredentialScope.GLOBAL,
        )
        assert cred.needs_rotation() is False

    def test_needs_rotation_due(self):
        cred = Credential(
            credential_id="c1",
            name="test",
            credential_type=CredentialType.API_KEY,
            scope=CredentialScope.GLOBAL,
            rotation_interval_days=1,
            created_at=datetime.now(UTC) - timedelta(days=2),
        )
        assert cred.needs_rotation() is True

    def test_needs_rotation_not_due(self):
        cred = Credential(
            credential_id="c1",
            name="test",
            credential_type=CredentialType.API_KEY,
            scope=CredentialScope.GLOBAL,
            rotation_interval_days=30,
            last_rotation=datetime.now(UTC),
        )
        assert cred.needs_rotation() is False

    def test_to_dict_without_sensitive(self):
        cred = Credential(
            credential_id="c1",
            name="test",
            credential_type=CredentialType.API_KEY,
            scope=CredentialScope.GLOBAL,
            data_hash="abc123",
        )
        d = cred.to_dict(include_sensitive=False)
        assert "data_hash" not in d
        assert d["credential_id"] == "c1"
        assert d["credential_type"] == "api_key"

    def test_to_dict_with_sensitive(self):
        cred = Credential(
            credential_id="c1",
            name="test",
            credential_type=CredentialType.API_KEY,
            scope=CredentialScope.GLOBAL,
            data_hash="abc123",
        )
        d = cred.to_dict(include_sensitive=True)
        assert d["data_hash"] == "abc123"


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class TestEnums:
    def test_credential_types(self):
        assert CredentialType.API_KEY.value == "api_key"
        assert CredentialType.BEARER_TOKEN.value == "bearer_token"
        assert CredentialType.BASIC_AUTH.value == "basic_auth"
        assert CredentialType.HMAC_SECRET.value == "hmac_secret"

    def test_credential_scopes(self):
        assert CredentialScope.GLOBAL.value == "global"
        assert CredentialScope.TOOL_SPECIFIC.value == "tool_specific"

    def test_credential_status(self):
        assert CredentialStatus.ACTIVE.value == "active"
        assert CredentialStatus.REVOKED.value == "revoked"


# ---------------------------------------------------------------------------
# CredentialManager config / init
# ---------------------------------------------------------------------------
class TestCredentialManagerInit:
    def test_default_config(self):
        mgr = CredentialManager()
        assert mgr.config.encryption_enabled is True
        assert mgr.config.max_total_credentials == 1000

    def test_custom_config(self):
        config = CredentialManagerConfig(
            encryption_enabled=False,
            max_total_credentials=10,
        )
        mgr = CredentialManager(config=config)
        assert mgr.config.encryption_enabled is False


# ---------------------------------------------------------------------------
# CredentialManager.store_credential
# ---------------------------------------------------------------------------
class TestStoreCredential:
    async def test_store_and_retrieve(self, tmp_path):
        config = CredentialManagerConfig(
            storage_path=str(tmp_path / "creds"),
            encryption_enabled=False,
        )
        mgr = CredentialManager(config=config)

        cred = await mgr.store_credential(
            name="my-api-key",
            credential_type=CredentialType.API_KEY,
            credential_data={"api_key": "sk-test-123"},
            tool_names=["tool-a"],
        )
        assert cred.name == "my-api-key"
        assert cred.credential_type == CredentialType.API_KEY
        assert cred.data_hash is not None
        assert mgr._stats["credentials_stored"] == 1

        # Retrieve
        result = await mgr.get_credential(cred.credential_id)
        assert result is not None
        retrieved_cred, data = result
        assert retrieved_cred.credential_id == cred.credential_id
        assert data["api_key"] == "sk-test-123"

    async def test_store_creates_tool_binding(self, tmp_path):
        config = CredentialManagerConfig(
            storage_path=str(tmp_path / "creds"),
            encryption_enabled=False,
        )
        mgr = CredentialManager(config=config)

        await mgr.store_credential(
            name="token",
            credential_type=CredentialType.BEARER_TOKEN,
            credential_data={"token": "tok123"},
            tool_names=["tool-a", "tool-b"],
        )
        assert "tool-a" in mgr._tool_bindings
        assert "tool-b" in mgr._tool_bindings

    async def test_store_with_encryption(self, tmp_path):
        config = CredentialManagerConfig(
            storage_path=str(tmp_path / "creds"),
            encryption_enabled=True,
            encryption_key="test-passphrase-for-encryption",
        )
        mgr = CredentialManager(config=config)
        cred = await mgr.store_credential(
            name="secret",
            credential_type=CredentialType.API_KEY,
            credential_data={"api_key": "encrypted-value"},
        )
        # encrypted_data should differ from raw JSON
        raw = json.dumps({"api_key": "encrypted-value"}).encode()
        assert cred.encrypted_data != raw

        # But decryption should work
        result = await mgr.get_credential(cred.credential_id)
        assert result is not None
        _, data = result
        assert data["api_key"] == "encrypted-value"


# ---------------------------------------------------------------------------
# CredentialManager.get_credential
# ---------------------------------------------------------------------------
class TestGetCredential:
    async def test_not_found(self, tmp_path):
        config = CredentialManagerConfig(storage_path=str(tmp_path), encryption_enabled=False)
        mgr = CredentialManager(config=config)
        assert await mgr.get_credential("nonexistent") is None

    async def test_tracks_usage(self, tmp_path):
        config = CredentialManagerConfig(
            storage_path=str(tmp_path / "creds"), encryption_enabled=False
        )
        mgr = CredentialManager(config=config)
        cred = await mgr.store_credential(
            name="test",
            credential_type=CredentialType.API_KEY,
            credential_data={"key": "val"},
        )
        await mgr.get_credential(cred.credential_id)
        await mgr.get_credential(cred.credential_id)
        assert cred.usage_count == 2
        assert mgr._stats["credentials_retrieved"] == 2

    async def test_marks_expired(self, tmp_path):
        config = CredentialManagerConfig(
            storage_path=str(tmp_path / "creds"), encryption_enabled=False
        )
        mgr = CredentialManager(config=config)
        cred = await mgr.store_credential(
            name="expired",
            credential_type=CredentialType.API_KEY,
            credential_data={"key": "val"},
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        result = await mgr.get_credential(cred.credential_id)
        assert result is not None
        assert result[0].status == CredentialStatus.EXPIRED


# ---------------------------------------------------------------------------
# CredentialManager.get_credentials_for_tool
# ---------------------------------------------------------------------------
class TestGetCredentialsForTool:
    async def test_returns_matching_bindings(self, tmp_path):
        config = CredentialManagerConfig(
            storage_path=str(tmp_path / "creds"), encryption_enabled=False
        )
        mgr = CredentialManager(config=config)
        await mgr.store_credential(
            name="key1",
            credential_type=CredentialType.API_KEY,
            credential_data={"api_key": "k1"},
            tool_names=["tool-a"],
        )
        await mgr.store_credential(
            name="key2",
            credential_type=CredentialType.BEARER_TOKEN,
            credential_data={"token": "t1"},
            tool_names=["tool-b"],
        )
        bindings = await mgr.get_credentials_for_tool("tool-a")
        assert len(bindings) == 1
        assert bindings[0].credential.name == "key1"

    async def test_filters_by_type(self, tmp_path):
        config = CredentialManagerConfig(
            storage_path=str(tmp_path / "creds"), encryption_enabled=False
        )
        mgr = CredentialManager(config=config)
        await mgr.store_credential(
            name="key1",
            credential_type=CredentialType.API_KEY,
            credential_data={"api_key": "k1"},
            tool_names=["tool-a"],
        )
        await mgr.store_credential(
            name="token1",
            credential_type=CredentialType.BEARER_TOKEN,
            credential_data={"token": "t1"},
            tool_names=["tool-a"],
        )
        bindings = await mgr.get_credentials_for_tool(
            "tool-a", credential_type=CredentialType.API_KEY
        )
        assert len(bindings) == 1

    async def test_excludes_expired(self, tmp_path):
        config = CredentialManagerConfig(
            storage_path=str(tmp_path / "creds"), encryption_enabled=False
        )
        mgr = CredentialManager(config=config)
        await mgr.store_credential(
            name="expired",
            credential_type=CredentialType.API_KEY,
            credential_data={"api_key": "k1"},
            tool_names=["tool-a"],
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        bindings = await mgr.get_credentials_for_tool("tool-a")
        assert len(bindings) == 0

    async def test_excludes_revoked(self, tmp_path):
        config = CredentialManagerConfig(
            storage_path=str(tmp_path / "creds"), encryption_enabled=False
        )
        mgr = CredentialManager(config=config)
        cred = await mgr.store_credential(
            name="will-revoke",
            credential_type=CredentialType.API_KEY,
            credential_data={"api_key": "k1"},
            tool_names=["tool-a"],
        )
        await mgr.revoke_credential(cred.credential_id)
        bindings = await mgr.get_credentials_for_tool("tool-a")
        assert len(bindings) == 0


# ---------------------------------------------------------------------------
# CredentialManager.inject_credentials
# ---------------------------------------------------------------------------
class TestInjectCredentials:
    async def test_inject_api_key_header(self, tmp_path):
        config = CredentialManagerConfig(
            storage_path=str(tmp_path / "creds"), encryption_enabled=False
        )
        mgr = CredentialManager(config=config)
        await mgr.store_credential(
            name="api-key",
            credential_type=CredentialType.API_KEY,
            credential_data={"api_key": "my-key-123"},
            tool_names=["tool-a"],
        )
        result = await mgr.inject_credentials("tool-a")
        assert result["headers"]["X-API-Key"] == "my-key-123"

    async def test_inject_bearer_token(self, tmp_path):
        config = CredentialManagerConfig(
            storage_path=str(tmp_path / "creds"), encryption_enabled=False
        )
        mgr = CredentialManager(config=config)
        await mgr.store_credential(
            name="bearer",
            credential_type=CredentialType.BEARER_TOKEN,
            credential_data={"token": "tok-abc"},
            tool_names=["tool-a"],
        )
        result = await mgr.inject_credentials("tool-a")
        assert result["headers"]["Authorization"] == "Bearer tok-abc"

    async def test_inject_basic_auth(self, tmp_path):
        config = CredentialManagerConfig(
            storage_path=str(tmp_path / "creds"), encryption_enabled=False
        )
        mgr = CredentialManager(config=config)
        await mgr.store_credential(
            name="basic",
            credential_type=CredentialType.BASIC_AUTH,
            credential_data={"username": "user", "password": "pass"},
            tool_names=["tool-a"],
        )
        result = await mgr.inject_credentials("tool-a")
        import base64

        expected = "Basic " + base64.b64encode(b"user:pass").decode()
        assert result["headers"]["Authorization"] == expected

    async def test_inject_no_credentials(self, tmp_path):
        config = CredentialManagerConfig(
            storage_path=str(tmp_path / "creds"), encryption_enabled=False
        )
        mgr = CredentialManager(config=config)
        result = await mgr.inject_credentials("tool-no-creds")
        assert result["headers"] == {}


# ---------------------------------------------------------------------------
# CredentialManager._extract_value
# ---------------------------------------------------------------------------
class TestExtractValue:
    def test_api_key(self):
        mgr = CredentialManager(config=CredentialManagerConfig(encryption_enabled=False))
        assert mgr._extract_value({"api_key": "k1"}, CredentialType.API_KEY) == "k1"
        assert mgr._extract_value({"key": "k2"}, CredentialType.API_KEY) == "k2"

    def test_bearer_token(self):
        mgr = CredentialManager(config=CredentialManagerConfig(encryption_enabled=False))
        assert mgr._extract_value({"token": "t1"}, CredentialType.BEARER_TOKEN) == "t1"
        assert mgr._extract_value({"access_token": "t2"}, CredentialType.BEARER_TOKEN) == "t2"

    def test_basic_auth(self):
        mgr = CredentialManager(config=CredentialManagerConfig(encryption_enabled=False))
        result = mgr._extract_value({"username": "u", "password": "p"}, CredentialType.BASIC_AUTH)
        assert result == "u:p"

    def test_hmac_secret(self):
        mgr = CredentialManager(config=CredentialManagerConfig(encryption_enabled=False))
        assert mgr._extract_value({"secret": "s1"}, CredentialType.HMAC_SECRET) == "s1"

    def test_custom(self):
        mgr = CredentialManager(config=CredentialManagerConfig(encryption_enabled=False))
        assert mgr._extract_value({"value": "v1"}, CredentialType.CUSTOM) == "v1"

    def test_missing_key_returns_none(self):
        mgr = CredentialManager(config=CredentialManagerConfig(encryption_enabled=False))
        assert mgr._extract_value({}, CredentialType.API_KEY) is None


# ---------------------------------------------------------------------------
# CredentialManager.rotate_credential
# ---------------------------------------------------------------------------
class TestRotateCredential:
    async def test_rotate(self, tmp_path):
        config = CredentialManagerConfig(
            storage_path=str(tmp_path / "creds"), encryption_enabled=False
        )
        mgr = CredentialManager(config=config)
        cred = await mgr.store_credential(
            name="rotate-me",
            credential_type=CredentialType.API_KEY,
            credential_data={"api_key": "old-key"},
        )
        old_hash = cred.data_hash

        rotated = await mgr.rotate_credential(cred.credential_id, {"api_key": "new-key"})
        assert rotated is not None
        assert rotated.data_hash != old_hash
        assert rotated.last_rotation is not None
        assert mgr._stats["credentials_rotated"] == 1

        # Verify new data
        result = await mgr.get_credential(cred.credential_id)
        _, data = result
        assert data["api_key"] == "new-key"

    async def test_rotate_nonexistent(self, tmp_path):
        config = CredentialManagerConfig(
            storage_path=str(tmp_path / "creds"), encryption_enabled=False
        )
        mgr = CredentialManager(config=config)
        assert await mgr.rotate_credential("nonexistent", {"key": "val"}) is None


# ---------------------------------------------------------------------------
# CredentialManager.revoke_credential
# ---------------------------------------------------------------------------
class TestRevokeCredential:
    async def test_revoke(self, tmp_path):
        config = CredentialManagerConfig(
            storage_path=str(tmp_path / "creds"), encryption_enabled=False
        )
        mgr = CredentialManager(config=config)
        cred = await mgr.store_credential(
            name="revoke-me",
            credential_type=CredentialType.API_KEY,
            credential_data={"api_key": "k1"},
            tool_names=["tool-a"],
        )
        result = await mgr.revoke_credential(cred.credential_id)
        assert result is True
        assert cred.status == CredentialStatus.REVOKED
        # Binding removed
        bindings = mgr._tool_bindings.get("tool-a", [])
        assert len(bindings) == 0

    async def test_revoke_nonexistent(self, tmp_path):
        config = CredentialManagerConfig(
            storage_path=str(tmp_path / "creds"), encryption_enabled=False
        )
        mgr = CredentialManager(config=config)
        assert await mgr.revoke_credential("nonexistent") is False


# ---------------------------------------------------------------------------
# CredentialManager.delete_credential
# ---------------------------------------------------------------------------
class TestDeleteCredential:
    async def test_delete(self, tmp_path):
        config = CredentialManagerConfig(
            storage_path=str(tmp_path / "creds"), encryption_enabled=False
        )
        mgr = CredentialManager(config=config)
        cred = await mgr.store_credential(
            name="delete-me",
            credential_type=CredentialType.API_KEY,
            credential_data={"api_key": "k1"},
            tool_names=["tool-a"],
        )
        result = await mgr.delete_credential(cred.credential_id)
        assert result is True
        assert cred.credential_id not in mgr._credentials

    async def test_delete_nonexistent(self, tmp_path):
        config = CredentialManagerConfig(
            storage_path=str(tmp_path / "creds"), encryption_enabled=False
        )
        mgr = CredentialManager(config=config)
        assert await mgr.delete_credential("nonexistent") is False


# ---------------------------------------------------------------------------
# CredentialManager.revoke_tool_credentials
# ---------------------------------------------------------------------------
class TestRevokeToolCredentials:
    async def test_revoke_all_for_tool(self, tmp_path):
        config = CredentialManagerConfig(
            storage_path=str(tmp_path / "creds"), encryption_enabled=False
        )
        mgr = CredentialManager(config=config)
        await mgr.store_credential(
            name="k1",
            credential_type=CredentialType.API_KEY,
            credential_data={"api_key": "a"},
            tool_names=["tool-a"],
        )
        await mgr.store_credential(
            name="k2",
            credential_type=CredentialType.API_KEY,
            credential_data={"api_key": "b"},
            tool_names=["tool-a"],
        )
        count = await mgr.revoke_tool_credentials("tool-a")
        assert count == 2
        assert "tool-a" not in mgr._tool_bindings


# ---------------------------------------------------------------------------
# CredentialManager.list_credentials
# ---------------------------------------------------------------------------
class TestListCredentials:
    async def test_list_all(self, tmp_path):
        config = CredentialManagerConfig(
            storage_path=str(tmp_path / "creds"), encryption_enabled=False
        )
        mgr = CredentialManager(config=config)
        await mgr.store_credential(
            name="k1",
            credential_type=CredentialType.API_KEY,
            credential_data={"api_key": "a"},
            tool_names=["tool-a"],
        )
        await mgr.store_credential(
            name="k2",
            credential_type=CredentialType.BEARER_TOKEN,
            credential_data={"token": "t"},
            tool_names=["tool-b"],
        )
        result = mgr.list_credentials()
        assert len(result) == 2

    async def test_filter_by_tool(self, tmp_path):
        config = CredentialManagerConfig(
            storage_path=str(tmp_path / "creds"), encryption_enabled=False
        )
        mgr = CredentialManager(config=config)
        await mgr.store_credential(
            name="k1",
            credential_type=CredentialType.API_KEY,
            credential_data={"api_key": "a"},
            tool_names=["tool-a"],
        )
        await mgr.store_credential(
            name="k2",
            credential_type=CredentialType.API_KEY,
            credential_data={"api_key": "b"},
            tool_names=["tool-b"],
        )
        result = mgr.list_credentials(tool_name="tool-a")
        assert len(result) == 1

    async def test_filter_by_type(self, tmp_path):
        config = CredentialManagerConfig(
            storage_path=str(tmp_path / "creds"), encryption_enabled=False
        )
        mgr = CredentialManager(config=config)
        await mgr.store_credential(
            name="k1",
            credential_type=CredentialType.API_KEY,
            credential_data={"api_key": "a"},
        )
        await mgr.store_credential(
            name="k2",
            credential_type=CredentialType.BEARER_TOKEN,
            credential_data={"token": "t"},
        )
        result = mgr.list_credentials(credential_type=CredentialType.API_KEY)
        assert len(result) == 1

    async def test_exclude_expired(self, tmp_path):
        config = CredentialManagerConfig(
            storage_path=str(tmp_path / "creds"), encryption_enabled=False
        )
        mgr = CredentialManager(config=config)
        await mgr.store_credential(
            name="expired",
            credential_type=CredentialType.API_KEY,
            credential_data={"api_key": "a"},
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        assert len(mgr.list_credentials()) == 0
        assert len(mgr.list_credentials(include_expired=True)) == 1


# ---------------------------------------------------------------------------
# CredentialManager.load_credentials
# ---------------------------------------------------------------------------
class TestLoadCredentials:
    async def test_load_from_storage(self, tmp_path):
        storage = tmp_path / "creds"
        config = CredentialManagerConfig(storage_path=str(storage), encryption_enabled=False)
        mgr1 = CredentialManager(config=config)
        cred = await mgr1.store_credential(
            name="persisted",
            credential_type=CredentialType.API_KEY,
            credential_data={"api_key": "k1"},
            tool_names=["tool-a"],
        )

        # Load into a fresh manager
        mgr2 = CredentialManager(config=config)
        count = await mgr2.load_credentials()
        assert count == 1
        assert cred.credential_id in mgr2._credentials
        assert "tool-a" in mgr2._tool_bindings

    async def test_load_empty_directory(self, tmp_path):
        config = CredentialManagerConfig(
            storage_path=str(tmp_path / "empty"), encryption_enabled=False
        )
        mgr = CredentialManager(config=config)
        count = await mgr.load_credentials()
        assert count == 0

    async def test_load_corrupt_file_skipped(self, tmp_path):
        storage = tmp_path / "creds"
        storage.mkdir()
        (storage / "bad.json").write_text("not valid json{{{")
        config = CredentialManagerConfig(storage_path=str(storage), encryption_enabled=False)
        mgr = CredentialManager(config=config)
        count = await mgr.load_credentials()
        assert count == 0


# ---------------------------------------------------------------------------
# CredentialManager.get_stats
# ---------------------------------------------------------------------------
class TestGetStats:
    async def test_stats(self, tmp_path):
        config = CredentialManagerConfig(
            storage_path=str(tmp_path / "creds"), encryption_enabled=False
        )
        mgr = CredentialManager(config=config)
        await mgr.store_credential(
            name="k1",
            credential_type=CredentialType.API_KEY,
            credential_data={"api_key": "a"},
        )
        stats = mgr.get_stats()
        assert stats["credentials_stored"] == 1
        assert stats["total_credentials"] == 1
        assert stats["encryption_enabled"] is False


# ---------------------------------------------------------------------------
# ToolCredential binding types
# ---------------------------------------------------------------------------
class TestCreateDefaultBinding:
    def test_bearer_binding(self, tmp_path):
        config = CredentialManagerConfig(storage_path=str(tmp_path), encryption_enabled=False)
        mgr = CredentialManager(config=config)
        cred = Credential(
            credential_id="c1",
            name="bearer",
            credential_type=CredentialType.BEARER_TOKEN,
            scope=CredentialScope.TOOL_SPECIFIC,
        )
        binding = mgr._create_default_binding("tool-a", cred)
        assert binding.injection_target == "headers"
        assert binding.injection_key == "Authorization"
        assert binding.injection_prefix == "Bearer "

    def test_api_key_binding(self, tmp_path):
        config = CredentialManagerConfig(storage_path=str(tmp_path), encryption_enabled=False)
        mgr = CredentialManager(config=config)
        cred = Credential(
            credential_id="c1",
            name="api-key",
            credential_type=CredentialType.API_KEY,
            scope=CredentialScope.TOOL_SPECIFIC,
        )
        binding = mgr._create_default_binding("tool-a", cred)
        assert binding.injection_key == "X-API-Key"

    def test_basic_auth_binding(self, tmp_path):
        config = CredentialManagerConfig(storage_path=str(tmp_path), encryption_enabled=False)
        mgr = CredentialManager(config=config)
        cred = Credential(
            credential_id="c1",
            name="basic",
            credential_type=CredentialType.BASIC_AUTH,
            scope=CredentialScope.TOOL_SPECIFIC,
        )
        binding = mgr._create_default_binding("tool-a", cred)
        assert binding.injection_prefix == "Basic "
        assert binding.transform == "base64"

    def test_custom_binding(self, tmp_path):
        config = CredentialManagerConfig(storage_path=str(tmp_path), encryption_enabled=False)
        mgr = CredentialManager(config=config)
        cred = Credential(
            credential_id="c1",
            name="custom",
            credential_type=CredentialType.CUSTOM,
            scope=CredentialScope.TOOL_SPECIFIC,
        )
        binding = mgr._create_default_binding("tool-a", cred)
        assert binding.injection_target == "headers"
        assert binding.injection_key == "Authorization"


# ---------------------------------------------------------------------------
# Encryption
# ---------------------------------------------------------------------------
class TestEncryption:
    def test_encrypt_decrypt_roundtrip(self, tmp_path):
        config = CredentialManagerConfig(
            storage_path=str(tmp_path),
            encryption_enabled=True,
            encryption_key="test-secret-key-for-encryption",
        )
        mgr = CredentialManager(config=config)
        data = b"sensitive-data"
        encrypted = mgr._encrypt(data)
        assert encrypted != data
        decrypted = mgr._decrypt(encrypted)
        assert decrypted == data

    def test_no_encryption(self, tmp_path):
        config = CredentialManagerConfig(storage_path=str(tmp_path), encryption_enabled=False)
        mgr = CredentialManager(config=config)
        data = b"plaintext"
        assert mgr._encrypt(data) == data
        assert mgr._decrypt(data) == data
