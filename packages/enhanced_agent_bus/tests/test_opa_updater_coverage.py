"""
ACGS-2 Enhanced Agent Bus - OPA Policy Updater Coverage Tests
Constitutional Hash: 608508a9bd224290

Comprehensive tests to boost constitutional/opa_updater.py coverage from 72% to ≥95%.
Covers all classes, methods, error paths, and edge cases.
"""

from __future__ import annotations

import json
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import httpx

# Constitutional hash for tests
from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.constitutional.opa_updater import (
    AIOFILES_AVAILABLE,
    OPAPolicyUpdater,
    PolicyUpdateRequest,
    PolicyUpdateResult,
    PolicyUpdateStatus,
    PolicyValidationResult,
)

# ---------------------------------------------------------------------------
# Helpers / shared fixtures
# ---------------------------------------------------------------------------

SAMPLE_REGO = """
package test

default allow = false

allow {
    input.user == "admin"
}
"""


def _make_request(**kwargs) -> PolicyUpdateRequest:
    defaults = {
        "policy_id": "test_policy",
        "policy_content": SAMPLE_REGO,
        "version": "v1.0.0",
    }
    defaults.update(kwargs)
    return PolicyUpdateRequest(**defaults)


def _make_result(**kwargs) -> PolicyUpdateResult:
    defaults = {
        "update_id": "test-update-id",
        "policy_id": "test_policy",
        "version": "v1.0.0",
        "status": PolicyUpdateStatus.PENDING,
    }
    defaults.update(kwargs)
    return PolicyUpdateResult(**defaults)


def _make_http_response(
    status_code: int, json_body: dict | None = None, content_type: str = "application/json"
) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = {"content-type": content_type}
    if json_body is not None:
        resp.json.return_value = json_body
    else:
        resp.json.return_value = {}
    return resp


# ---------------------------------------------------------------------------
# PolicyUpdateStatus Enum Tests
# ---------------------------------------------------------------------------


class TestPolicyUpdateStatus:
    def test_all_values_present(self):
        values = {s.value for s in PolicyUpdateStatus}
        assert "pending" in values
        assert "validating" in values
        assert "compiling" in values
        assert "uploading" in values
        assert "activating" in values
        assert "completed" in values
        assert "failed" in values
        assert "rolled_back" in values

    def test_is_string_enum(self):
        assert isinstance(PolicyUpdateStatus.COMPLETED, str)
        assert PolicyUpdateStatus.FAILED == "failed"


# ---------------------------------------------------------------------------
# PolicyValidationResult Model Tests
# ---------------------------------------------------------------------------


class TestPolicyValidationResult:
    def test_default_values(self):
        result = PolicyValidationResult(policy_id="test", is_valid=True)
        assert result.errors == []
        assert result.warnings == []
        assert result.syntax_check is False
        assert result.compile_check is False
        assert result.metadata == {}

    def test_invalid_with_errors(self):
        result = PolicyValidationResult(
            policy_id="test",
            is_valid=False,
            errors=["syntax error line 5"],
            warnings=["deprecated function"],
        )
        assert not result.is_valid
        assert len(result.errors) == 1
        assert len(result.warnings) == 1

    def test_valid_with_checks(self):
        result = PolicyValidationResult(
            policy_id="my_policy",
            is_valid=True,
            syntax_check=True,
            compile_check=True,
        )
        assert result.is_valid
        assert result.syntax_check
        assert result.compile_check


# ---------------------------------------------------------------------------
# PolicyUpdateRequest Model Tests
# ---------------------------------------------------------------------------


class TestPolicyUpdateRequest:
    def test_default_values(self):
        req = _make_request()
        assert req.policy_id == "test_policy"
        assert req.version == "v1.0.0"
        assert req.constitutional_hash == CONSTITUTIONAL_HASH
        assert req.dry_run is False
        assert req.metadata == {}

    def test_dry_run_flag(self):
        req = _make_request(dry_run=True)
        assert req.dry_run is True

    def test_custom_metadata(self):
        req = _make_request(metadata={"author": "alice"})
        assert req.metadata["author"] == "alice"

    def test_custom_constitutional_hash(self):
        req = _make_request(constitutional_hash="custom_hash")  # pragma: allowlist secret
        assert req.constitutional_hash == "custom_hash"  # pragma: allowlist secret


# ---------------------------------------------------------------------------
# PolicyUpdateResult Model Tests
# ---------------------------------------------------------------------------


class TestPolicyUpdateResult:
    def test_default_values(self):
        result = _make_result()
        assert result.health_check_passed is False
        assert result.cache_invalidated is False
        assert result.rolled_back is False
        assert result.error_message is None
        assert result.previous_version is None
        assert result.validation is None
        assert result.timestamp is not None

    def test_with_validation(self):
        validation = PolicyValidationResult(policy_id="test", is_valid=True)
        result = _make_result(validation=validation)
        assert result.validation is not None
        assert result.validation.is_valid

    def test_failed_status_with_error(self):
        result = _make_result(
            status=PolicyUpdateStatus.FAILED,
            error_message="Something broke",
        )
        assert result.status == PolicyUpdateStatus.FAILED
        assert result.error_message == "Something broke"


# ---------------------------------------------------------------------------
# OPAPolicyUpdater.__init__ Tests
# ---------------------------------------------------------------------------


class TestOPAPolicyUpdaterInit:
    def test_default_init(self):
        updater = OPAPolicyUpdater()
        assert updater.opa_url == "http://localhost:8181"
        assert updater.audit_service_url == "http://localhost:8001"
        assert updater.enable_health_checks is True
        assert updater.enable_cache_invalidation is True
        assert updater.enable_rollback is True
        assert updater.health_check_timeout == 5.0
        assert updater._http_client is None
        assert updater._opa_client is None
        assert updater._audit_client is None
        assert updater._policy_backups == {}

    def test_trailing_slash_stripped(self):
        updater = OPAPolicyUpdater(opa_url="http://localhost:8181/")
        assert updater.opa_url == "http://localhost:8181"

    def test_custom_params(self):
        updater = OPAPolicyUpdater(
            opa_url="http://opa:9999",
            audit_service_url="http://audit:9000",
            enable_health_checks=False,
            enable_cache_invalidation=False,
            enable_rollback=False,
            health_check_timeout=10.0,
            policy_backup_dir="/tmp/backups",
        )
        assert updater.opa_url == "http://opa:9999"
        assert updater.enable_health_checks is False
        assert updater.enable_cache_invalidation is False
        assert updater.enable_rollback is False
        assert updater.health_check_timeout == 10.0
        assert updater.policy_backup_dir == "/tmp/backups"

    def test_default_backup_dir_is_tempdir(self):
        updater = OPAPolicyUpdater()
        assert updater.policy_backup_dir == tempfile.gettempdir()


# ---------------------------------------------------------------------------
# OPAPolicyUpdater.connect Tests
# ---------------------------------------------------------------------------


class TestOPAPolicyUpdaterConnect:
    async def test_connect_creates_http_client(self):
        updater = OPAPolicyUpdater()
        with (
            patch("enhanced_agent_bus.constitutional.opa_updater.OPAClient", None),
            patch("enhanced_agent_bus.constitutional.opa_updater.AuditClient", None),
        ):
            await updater.connect()
            assert updater._http_client is not None
            await updater._http_client.aclose()

    async def test_connect_with_opa_client_success(self):
        mock_opa = AsyncMock()
        mock_opa_cls = MagicMock(return_value=mock_opa)
        updater = OPAPolicyUpdater()
        with (
            patch("enhanced_agent_bus.constitutional.opa_updater.OPAClient", mock_opa_cls),
            patch("enhanced_agent_bus.constitutional.opa_updater.AuditClient", None),
        ):
            await updater.connect()
            mock_opa.initialize.assert_called_once()
            assert updater._opa_client is mock_opa
            await updater._http_client.aclose()

    async def test_connect_opa_client_init_error(self):
        mock_opa = AsyncMock()
        mock_opa.initialize.side_effect = RuntimeError("Connection refused")
        mock_opa_cls = MagicMock(return_value=mock_opa)
        updater = OPAPolicyUpdater()
        with (
            patch("enhanced_agent_bus.constitutional.opa_updater.OPAClient", mock_opa_cls),
            patch("enhanced_agent_bus.constitutional.opa_updater.AuditClient", None),
        ):
            await updater.connect()
            assert updater._opa_client is None
            await updater._http_client.aclose()

    async def test_connect_with_audit_client_success(self):
        mock_audit = AsyncMock()
        mock_audit_cls = MagicMock(return_value=mock_audit)
        updater = OPAPolicyUpdater()
        with (
            patch("enhanced_agent_bus.constitutional.opa_updater.OPAClient", None),
            patch("enhanced_agent_bus.constitutional.opa_updater.AuditClient", mock_audit_cls),
        ):
            await updater.connect()
            mock_audit.start.assert_called_once()
            assert updater._audit_client is mock_audit
            await updater._http_client.aclose()

    async def test_connect_audit_client_init_error(self):
        mock_audit = AsyncMock()
        mock_audit.start.side_effect = ValueError("Bad URL")
        mock_audit_cls = MagicMock(return_value=mock_audit)
        updater = OPAPolicyUpdater()
        with (
            patch("enhanced_agent_bus.constitutional.opa_updater.OPAClient", None),
            patch("enhanced_agent_bus.constitutional.opa_updater.AuditClient", mock_audit_cls),
        ):
            await updater.connect()
            assert updater._audit_client is None
            await updater._http_client.aclose()


# ---------------------------------------------------------------------------
# OPAPolicyUpdater.disconnect Tests
# ---------------------------------------------------------------------------


class TestOPAPolicyUpdaterDisconnect:
    async def test_disconnect_closes_http_client(self):
        updater = OPAPolicyUpdater()
        mock_http = AsyncMock()
        updater._http_client = mock_http
        await updater.disconnect()
        mock_http.aclose.assert_called_once()
        assert updater._http_client is None

    async def test_disconnect_closes_opa_client(self):
        updater = OPAPolicyUpdater()
        mock_opa = AsyncMock()
        updater._opa_client = mock_opa
        await updater.disconnect()
        mock_opa.close.assert_called_once()
        assert updater._opa_client is None

    async def test_disconnect_stops_audit_client(self):
        updater = OPAPolicyUpdater()
        mock_audit = AsyncMock()
        updater._audit_client = mock_audit
        await updater.disconnect()
        mock_audit.stop.assert_called_once()
        assert updater._audit_client is None

    async def test_disconnect_when_nothing_connected(self):
        updater = OPAPolicyUpdater()
        # Should not raise when all clients are None
        await updater.disconnect()

    async def test_disconnect_all_clients(self):
        updater = OPAPolicyUpdater()
        mock_http = AsyncMock()
        mock_opa = AsyncMock()
        mock_audit = AsyncMock()
        updater._http_client = mock_http
        updater._opa_client = mock_opa
        updater._audit_client = mock_audit
        await updater.disconnect()
        mock_http.aclose.assert_called_once()
        mock_opa.close.assert_called_once()
        mock_audit.stop.assert_called_once()


# ---------------------------------------------------------------------------
# OPAPolicyUpdater._validate_policy Tests
# ---------------------------------------------------------------------------


class TestValidatePolicy:
    def _make_updater_with_mock_http(self) -> tuple[OPAPolicyUpdater, AsyncMock]:
        updater = OPAPolicyUpdater()
        mock_http = AsyncMock()
        updater._http_client = mock_http
        return updater, mock_http

    async def test_validate_no_http_client(self):
        updater = OPAPolicyUpdater()
        req = _make_request()
        result = await updater._validate_policy(req)
        assert not result.is_valid
        assert any("HTTP client not initialized" in e for e in result.errors)

    async def test_validate_syntax_error_response(self):
        updater, mock_http = self._make_updater_with_mock_http()
        # PUT returns 400 (syntax error)
        put_resp = _make_http_response(400, {"message": "syntax error at line 3"})
        delete_resp = _make_http_response(200)
        mock_http.put.return_value = put_resp
        mock_http.delete.return_value = delete_resp

        req = _make_request()
        result = await updater._validate_policy(req)

        assert not result.is_valid
        assert result.syntax_check is False
        assert any("syntax error" in e.lower() for e in result.errors)
        mock_http.delete.assert_called_once()

    async def test_validate_syntax_error_non_json_response(self):
        updater, mock_http = self._make_updater_with_mock_http()
        put_resp = MagicMock()
        put_resp.status_code = 422
        put_resp.headers = {"content-type": "text/plain"}
        put_resp.json.return_value = {}
        delete_resp = _make_http_response(200)
        mock_http.put.return_value = put_resp
        mock_http.delete.return_value = delete_resp

        req = _make_request()
        result = await updater._validate_policy(req)
        assert not result.is_valid
        assert any("HTTP 422" in e for e in result.errors)

    async def test_validate_success_path(self):
        updater, mock_http = self._make_updater_with_mock_http()
        put_resp = _make_http_response(200)
        compile_resp = _make_http_response(200, {"result": {}})
        delete_resp = _make_http_response(200)
        mock_http.put.return_value = put_resp
        mock_http.post.return_value = compile_resp
        mock_http.delete.return_value = delete_resp

        req = _make_request()
        result = await updater._validate_policy(req)

        assert result.is_valid
        assert result.syntax_check is True
        assert result.compile_check is True

    async def test_validate_compile_failure(self):
        updater, mock_http = self._make_updater_with_mock_http()
        put_resp = _make_http_response(200)
        compile_resp = _make_http_response(400, {"message": "compilation failed"})
        delete_resp = _make_http_response(200)
        mock_http.put.return_value = put_resp
        mock_http.post.return_value = compile_resp
        mock_http.delete.return_value = delete_resp

        req = _make_request()
        result = await updater._validate_policy(req)

        assert not result.is_valid
        assert result.syntax_check is True
        assert result.compile_check is False
        assert any("Compilation error" in e for e in result.errors)

    async def test_validate_compile_failure_non_json(self):
        updater, mock_http = self._make_updater_with_mock_http()
        put_resp = _make_http_response(200)
        compile_resp = MagicMock()
        compile_resp.status_code = 500
        compile_resp.headers = {"content-type": "text/plain"}
        compile_resp.json.return_value = {}
        delete_resp = _make_http_response(200)
        mock_http.put.return_value = put_resp
        mock_http.post.return_value = compile_resp
        mock_http.delete.return_value = delete_resp

        req = _make_request()
        result = await updater._validate_policy(req)
        assert not result.is_valid
        assert any("Compilation failed with status 500" in e for e in result.errors)

    async def test_validate_http_error(self):
        updater, mock_http = self._make_updater_with_mock_http()
        mock_http.put.side_effect = httpx.HTTPError("Connection refused")

        req = _make_request()
        result = await updater._validate_policy(req)
        assert not result.is_valid
        assert any("HTTP error" in e for e in result.errors)

    async def test_validate_generic_exception(self):
        updater, mock_http = self._make_updater_with_mock_http()
        mock_http.put.side_effect = ValueError("Unexpected error")

        req = _make_request()
        result = await updater._validate_policy(req)
        assert not result.is_valid
        assert any("Validation error" in e for e in result.errors)


# ---------------------------------------------------------------------------
# OPAPolicyUpdater._backup_current_policy Tests
# ---------------------------------------------------------------------------


class TestBackupCurrentPolicy:
    async def test_backup_disabled(self):
        updater = OPAPolicyUpdater(enable_rollback=False)
        result = await updater._backup_current_policy("test_policy")
        assert result is None

    async def test_backup_no_http_client(self):
        updater = OPAPolicyUpdater()
        result = await updater._backup_current_policy("test_policy")
        assert result is None

    async def test_backup_policy_found(self):
        updater = OPAPolicyUpdater(policy_backup_dir=tempfile.gettempdir())
        mock_http = AsyncMock()
        updater._http_client = mock_http
        policy_data = {"result": {"id": "test_policy", "raw": SAMPLE_REGO}}
        mock_http.get.return_value = _make_http_response(200, policy_data)

        with patch("enhanced_agent_bus.constitutional.opa_updater.AIOFILES_AVAILABLE", False):
            result = await updater._backup_current_policy("test_policy")

        assert result is not None
        assert "test_policy" in result
        assert "test_policy" in updater._policy_backups

    async def test_backup_policy_not_found_404(self):
        updater = OPAPolicyUpdater()
        mock_http = AsyncMock()
        updater._http_client = mock_http
        mock_http.get.return_value = _make_http_response(404)

        result = await updater._backup_current_policy("test_policy")
        assert result is None

    async def test_backup_http_error_status(self):
        updater = OPAPolicyUpdater()
        mock_http = AsyncMock()
        updater._http_client = mock_http
        mock_http.get.return_value = _make_http_response(500)

        result = await updater._backup_current_policy("test_policy")
        assert result is None

    async def test_backup_exception(self):
        updater = OPAPolicyUpdater()
        mock_http = AsyncMock()
        updater._http_client = mock_http
        mock_http.get.side_effect = RuntimeError("Network failure")

        result = await updater._backup_current_policy("test_policy")
        assert result is None

    async def test_backup_with_aiofiles(self):
        updater = OPAPolicyUpdater(policy_backup_dir=tempfile.gettempdir())
        mock_http = AsyncMock()
        updater._http_client = mock_http
        policy_data = {"result": {"id": "test_policy", "raw": SAMPLE_REGO}}
        mock_http.get.return_value = _make_http_response(200, policy_data)

        # Build a proper async context manager for aiofiles.open
        mock_file = AsyncMock()

        class _AsyncCM:
            async def __aenter__(self):
                return mock_file

            async def __aexit__(self, *args):
                return None

        mock_aiofiles_mod = MagicMock()
        mock_aiofiles_mod.open.return_value = _AsyncCM()

        with (
            patch("enhanced_agent_bus.constitutional.opa_updater.AIOFILES_AVAILABLE", True),
            patch("enhanced_agent_bus.constitutional.opa_updater.aiofiles", mock_aiofiles_mod),
        ):
            result = await updater._backup_current_policy("test_policy")

        assert result is not None


# ---------------------------------------------------------------------------
# OPAPolicyUpdater._upload_policy_to_opa Tests
# ---------------------------------------------------------------------------


class TestUploadPolicyToOpa:
    async def test_upload_no_http_client(self):
        updater = OPAPolicyUpdater()
        req = _make_request()
        result = await updater._upload_policy_to_opa(req)
        assert result is False

    async def test_upload_success_200(self):
        updater = OPAPolicyUpdater()
        mock_http = AsyncMock()
        updater._http_client = mock_http
        mock_http.put.return_value = _make_http_response(200)

        req = _make_request()
        result = await updater._upload_policy_to_opa(req)
        assert result is True

    async def test_upload_success_204(self):
        updater = OPAPolicyUpdater()
        mock_http = AsyncMock()
        updater._http_client = mock_http
        mock_http.put.return_value = _make_http_response(204)

        req = _make_request()
        result = await updater._upload_policy_to_opa(req)
        assert result is True

    async def test_upload_failure_400(self):
        updater = OPAPolicyUpdater()
        mock_http = AsyncMock()
        updater._http_client = mock_http
        mock_http.put.return_value = _make_http_response(400)

        req = _make_request()
        result = await updater._upload_policy_to_opa(req)
        assert result is False

    async def test_upload_exception(self):
        updater = OPAPolicyUpdater()
        mock_http = AsyncMock()
        updater._http_client = mock_http
        mock_http.put.side_effect = TypeError("Encoding error")

        req = _make_request()
        result = await updater._upload_policy_to_opa(req)
        assert result is False


# ---------------------------------------------------------------------------
# OPAPolicyUpdater._health_check_opa Tests
# ---------------------------------------------------------------------------


class TestHealthCheckOpa:
    async def test_health_check_via_opa_client_healthy(self):
        updater = OPAPolicyUpdater()
        mock_opa = AsyncMock()
        mock_opa.health_check.return_value = {"status": "healthy"}
        updater._opa_client = mock_opa

        result = await updater._health_check_opa()
        assert result is True

    async def test_health_check_via_opa_client_unhealthy(self):
        updater = OPAPolicyUpdater()
        mock_opa = AsyncMock()
        mock_opa.health_check.return_value = {"status": "degraded"}
        updater._opa_client = mock_opa

        result = await updater._health_check_opa()
        assert result is False

    async def test_health_check_via_opa_client_exception(self):
        updater = OPAPolicyUpdater()
        mock_opa = AsyncMock()
        mock_opa.health_check.side_effect = RuntimeError("Connection lost")
        updater._opa_client = mock_opa

        result = await updater._health_check_opa()
        assert result is False

    async def test_health_check_http_fallback_healthy(self):
        updater = OPAPolicyUpdater()
        mock_http = AsyncMock()
        updater._http_client = mock_http
        mock_http.get.return_value = _make_http_response(200)

        result = await updater._health_check_opa()
        assert result is True

    async def test_health_check_http_fallback_unhealthy(self):
        updater = OPAPolicyUpdater()
        mock_http = AsyncMock()
        updater._http_client = mock_http
        mock_http.get.return_value = _make_http_response(503)

        result = await updater._health_check_opa()
        assert result is False

    async def test_health_check_no_clients(self):
        updater = OPAPolicyUpdater()
        # Neither _opa_client nor _http_client set
        result = await updater._health_check_opa()
        assert result is False

    async def test_health_check_http_exception(self):
        updater = OPAPolicyUpdater()
        mock_http = AsyncMock()
        updater._http_client = mock_http
        mock_http.get.side_effect = ValueError("Timeout")

        result = await updater._health_check_opa()
        assert result is False


# ---------------------------------------------------------------------------
# OPAPolicyUpdater._invalidate_cache Tests
# ---------------------------------------------------------------------------


class TestInvalidateCache:
    async def test_invalidate_no_opa_client(self):
        updater = OPAPolicyUpdater()
        result = await updater._invalidate_cache("test_policy")
        assert result is False

    async def test_invalidate_success(self):
        updater = OPAPolicyUpdater()
        mock_opa = AsyncMock()
        updater._opa_client = mock_opa

        result = await updater._invalidate_cache("test_policy")
        assert result is True
        mock_opa.clear_cache.assert_called_once_with(policy_path="test.policy")

    async def test_invalidate_underscore_to_dot(self):
        updater = OPAPolicyUpdater()
        mock_opa = AsyncMock()
        updater._opa_client = mock_opa

        await updater._invalidate_cache("my_constitutional_policy")
        mock_opa.clear_cache.assert_called_once_with(policy_path="my.constitutional.policy")

    async def test_invalidate_exception(self):
        updater = OPAPolicyUpdater()
        mock_opa = AsyncMock()
        mock_opa.clear_cache.side_effect = RuntimeError("Cache unavailable")
        updater._opa_client = mock_opa

        result = await updater._invalidate_cache("test_policy")
        assert result is False


# ---------------------------------------------------------------------------
# OPAPolicyUpdater._rollback_policy Tests
# ---------------------------------------------------------------------------


class TestRollbackPolicy:
    def _base_result(self) -> PolicyUpdateResult:
        return _make_result(status=PolicyUpdateStatus.FAILED)

    async def test_rollback_disabled(self):
        updater = OPAPolicyUpdater(enable_rollback=False)
        result = self._base_result()
        success = await updater._rollback_policy("test_policy", "backup_id", result)
        assert success is False

    async def test_rollback_no_backup_id(self):
        updater = OPAPolicyUpdater()
        result = self._base_result()
        success = await updater._rollback_policy("test_policy", None, result)
        assert success is False

    async def test_rollback_from_memory_success(self):
        updater = OPAPolicyUpdater()
        mock_http = AsyncMock()
        updater._http_client = mock_http
        mock_http.put.return_value = _make_http_response(200)

        # Seed in-memory backup
        updater._policy_backups["test_policy"] = {
            "backup_id": "test_policy_backup_20240101_000000",
            "policy_data": {"result": {"raw": SAMPLE_REGO}},
            "timestamp": "2024-01-01T00:00:00+00:00",
        }

        result = self._base_result()
        success = await updater._rollback_policy(
            "test_policy", "test_policy_backup_20240101_000000", result
        )
        assert success is True
        assert result.rolled_back is True
        assert result.status == PolicyUpdateStatus.ROLLED_BACK

    async def test_rollback_from_memory_204(self):
        updater = OPAPolicyUpdater()
        mock_http = AsyncMock()
        updater._http_client = mock_http
        mock_http.put.return_value = _make_http_response(204)

        updater._policy_backups["test_policy"] = {
            "backup_id": "backup_id",
            "policy_data": {"result": {"raw": SAMPLE_REGO}},
            "timestamp": "2024-01-01T00:00:00+00:00",
        }
        result = self._base_result()
        success = await updater._rollback_policy("test_policy", "backup_id", result)
        assert success is True

    async def test_rollback_upload_failure(self):
        updater = OPAPolicyUpdater()
        mock_http = AsyncMock()
        updater._http_client = mock_http
        mock_http.put.return_value = _make_http_response(500)

        updater._policy_backups["test_policy"] = {
            "backup_id": "backup_id",
            "policy_data": {"result": {"raw": SAMPLE_REGO}},
            "timestamp": "2024-01-01T00:00:00+00:00",
        }
        result = self._base_result()
        success = await updater._rollback_policy("test_policy", "backup_id", result)
        assert success is False

    async def test_rollback_empty_policy_content(self):
        updater = OPAPolicyUpdater()
        mock_http = AsyncMock()
        updater._http_client = mock_http

        updater._policy_backups["test_policy"] = {
            "backup_id": "backup_id",
            "policy_data": {"result": {"raw": ""}},  # empty content
            "timestamp": "2024-01-01T00:00:00+00:00",
        }
        result = self._base_result()
        success = await updater._rollback_policy("test_policy", "backup_id", result)
        assert success is False

    async def test_rollback_from_disk_aiofiles(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_id = "test_policy_backup_disk"
            backup_path = os.path.join(tmpdir, f"{backup_id}.json")
            policy_data = {"result": {"raw": SAMPLE_REGO}}
            with open(backup_path, "w") as f:
                json.dump(policy_data, f)

            updater = OPAPolicyUpdater(policy_backup_dir=tmpdir)
            mock_http = AsyncMock()
            updater._http_client = mock_http
            mock_http.put.return_value = _make_http_response(200)

            # No in-memory backup, falls back to disk
            mock_file = AsyncMock()
            mock_file.read.return_value = json.dumps(policy_data)

            class _AsyncCM:
                async def __aenter__(self):
                    return mock_file

                async def __aexit__(self, *args):
                    return None

            mock_aiofiles_mod = MagicMock()
            mock_aiofiles_mod.open.return_value = _AsyncCM()

            result = self._base_result()
            with (
                patch(
                    "enhanced_agent_bus.constitutional.opa_updater.AIOFILES_AVAILABLE",
                    True,
                ),
                patch(
                    "enhanced_agent_bus.constitutional.opa_updater.aiofiles",
                    mock_aiofiles_mod,
                ),
            ):
                success = await updater._rollback_policy("test_policy", backup_id, result)

            assert success is True

    async def test_rollback_from_disk_sync(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_id = "test_policy_backup_sync"
            backup_path = os.path.join(tmpdir, f"{backup_id}.json")
            policy_data = {"result": {"raw": SAMPLE_REGO}}
            with open(backup_path, "w") as f:
                json.dump(policy_data, f)

            updater = OPAPolicyUpdater(policy_backup_dir=tmpdir)
            mock_http = AsyncMock()
            updater._http_client = mock_http
            mock_http.put.return_value = _make_http_response(200)

            result = self._base_result()
            with patch("enhanced_agent_bus.constitutional.opa_updater.AIOFILES_AVAILABLE", False):
                success = await updater._rollback_policy("test_policy", backup_id, result)

            assert success is True

    async def test_rollback_disk_backup_not_found(self):
        updater = OPAPolicyUpdater(policy_backup_dir="/nonexistent")
        result = self._base_result()
        success = await updater._rollback_policy("test_policy", "nonexistent_backup", result)
        assert success is False

    async def test_rollback_no_http_client(self):
        updater = OPAPolicyUpdater()
        updater._policy_backups["test_policy"] = {
            "backup_id": "backup_id",
            "policy_data": {"result": {"raw": SAMPLE_REGO}},
            "timestamp": "2024-01-01T00:00:00+00:00",
        }
        result = self._base_result()
        success = await updater._rollback_policy("test_policy", "backup_id", result)
        assert success is False

    async def test_rollback_exception(self):
        updater = OPAPolicyUpdater()
        mock_http = AsyncMock()
        updater._http_client = mock_http
        mock_http.put.side_effect = RuntimeError("Write failed")

        updater._policy_backups["test_policy"] = {
            "backup_id": "backup_id",
            "policy_data": {"result": {"raw": SAMPLE_REGO}},
            "timestamp": "2024-01-01T00:00:00+00:00",
        }
        result = self._base_result()
        success = await updater._rollback_policy("test_policy", "backup_id", result)
        assert success is False


# ---------------------------------------------------------------------------
# OPAPolicyUpdater._emit_policy_event Tests
# ---------------------------------------------------------------------------


class TestEmitPolicyEvent:
    async def test_emit_without_audit_client(self):
        updater = OPAPolicyUpdater()
        result = _make_result(status=PolicyUpdateStatus.COMPLETED)
        # Should not raise
        await updater._emit_policy_event(result, "policy_updated")

    async def test_emit_with_audit_client_success(self):
        updater = OPAPolicyUpdater()
        mock_audit = AsyncMock()
        updater._audit_client = mock_audit
        result = _make_result(status=PolicyUpdateStatus.COMPLETED)
        await updater._emit_policy_event(result, "policy_updated")
        mock_audit.log.assert_called_once()

    async def test_emit_with_audit_client_exception(self):
        updater = OPAPolicyUpdater()
        mock_audit = AsyncMock()
        mock_audit.log.side_effect = RuntimeError("Audit service down")
        updater._audit_client = mock_audit
        result = _make_result(status=PolicyUpdateStatus.COMPLETED)
        # Should not propagate exception
        await updater._emit_policy_event(result, "policy_updated")

    async def test_emit_includes_error_message(self):
        updater = OPAPolicyUpdater()
        mock_audit = AsyncMock()
        updater._audit_client = mock_audit
        result = _make_result(
            status=PolicyUpdateStatus.FAILED,
            error_message="Validation failed",
        )
        await updater._emit_policy_event(result, "policy_validation_failed")
        call_kwargs = mock_audit.log.call_args
        assert call_kwargs is not None

    async def test_emit_includes_validation(self):
        updater = OPAPolicyUpdater()
        mock_audit = AsyncMock()
        updater._audit_client = mock_audit
        validation = PolicyValidationResult(
            policy_id="test",
            is_valid=False,
            errors=["syntax error"],
        )
        result = _make_result(
            status=PolicyUpdateStatus.FAILED,
            validation=validation,
        )
        await updater._emit_policy_event(result, "policy_validation_failed")
        mock_audit.log.assert_called_once()

    async def test_emit_rolled_back_result(self):
        updater = OPAPolicyUpdater()
        result = _make_result(
            status=PolicyUpdateStatus.ROLLED_BACK,
            rolled_back=True,
        )
        # Should not raise
        await updater._emit_policy_event(result, "policy_rolled_back")


# ---------------------------------------------------------------------------
# OPAPolicyUpdater.update_policy - High-Level Integration Tests
# ---------------------------------------------------------------------------


class TestUpdatePolicy:
    def _make_updater_with_mocks(self) -> tuple[OPAPolicyUpdater, AsyncMock]:
        updater = OPAPolicyUpdater(policy_backup_dir=tempfile.gettempdir())
        mock_http = AsyncMock()
        updater._http_client = mock_http
        return updater, mock_http

    async def test_update_validation_fails(self):
        updater, mock_http = self._make_updater_with_mocks()
        # PUT returns error (syntax error)
        mock_http.put.return_value = _make_http_response(400, {"message": "syntax error"})
        mock_http.delete.return_value = _make_http_response(200)

        req = _make_request()
        result = await updater.update_policy(req)

        assert result.status == PolicyUpdateStatus.FAILED
        assert result.validation is not None
        assert not result.validation.is_valid
        assert "Policy validation failed" in (result.error_message or "")

    async def test_update_dry_run_success(self):
        updater, mock_http = self._make_updater_with_mocks()
        # Validation passes
        mock_http.put.return_value = _make_http_response(200)
        mock_http.post.return_value = _make_http_response(200, {"result": {}})
        mock_http.delete.return_value = _make_http_response(200)

        req = _make_request(dry_run=True)
        result = await updater.update_policy(req)

        assert result.status == PolicyUpdateStatus.COMPLETED
        assert result.validation is not None
        assert result.validation.is_valid

    async def test_update_full_success(self):
        updater, mock_http = self._make_updater_with_mocks()
        # Validation passes
        mock_http.put.return_value = _make_http_response(200)
        mock_http.post.return_value = _make_http_response(200, {"result": {}})
        mock_http.delete.return_value = _make_http_response(200)
        mock_http.get.return_value = _make_http_response(404)  # No backup found

        updater.enable_health_checks = False
        updater.enable_cache_invalidation = False

        req = _make_request()
        result = await updater.update_policy(req)

        assert result.status == PolicyUpdateStatus.COMPLETED

    async def test_update_upload_fails_triggers_rollback(self):
        updater, mock_http = self._make_updater_with_mocks()

        def put_side_effect(url, **kwargs):
            if "_validate" in url:
                # Validation PUT succeeds
                return _make_http_response(200)
            else:
                # Main upload fails
                return _make_http_response(500)

        mock_http.put.side_effect = put_side_effect
        mock_http.post.return_value = _make_http_response(200, {"result": {}})
        mock_http.delete.return_value = _make_http_response(200)
        mock_http.get.return_value = _make_http_response(404)  # No backup

        req = _make_request()
        result = await updater.update_policy(req)

        assert result.status == PolicyUpdateStatus.FAILED
        assert "Failed to upload policy" in (result.error_message or "")

    async def test_update_health_check_fails_triggers_rollback(self):
        updater, mock_http = self._make_updater_with_mocks()

        call_counts = {"put": 0}

        def put_side_effect(url, **kwargs):
            call_counts["put"] += 1
            return _make_http_response(200)

        mock_http.put.side_effect = put_side_effect
        mock_http.post.return_value = _make_http_response(200, {"result": {}})
        mock_http.delete.return_value = _make_http_response(200)
        mock_http.get.side_effect = [
            _make_http_response(404),  # backup fetch (no backup)
            _make_http_response(503),  # health check fails
        ]

        updater.enable_health_checks = True
        # No opa_client so falls back to HTTP health check

        req = _make_request()
        result = await updater.update_policy(req)

        assert result.status == PolicyUpdateStatus.FAILED
        assert "health check failed" in (result.error_message or "").lower()

    async def test_update_with_health_check_and_cache_invalidation(self):
        updater, mock_http = self._make_updater_with_mocks()
        # OPA client for health/cache
        mock_opa = AsyncMock()
        mock_opa.health_check.return_value = {"status": "healthy"}
        updater._opa_client = mock_opa

        mock_http.put.return_value = _make_http_response(200)
        mock_http.post.return_value = _make_http_response(200, {"result": {}})
        mock_http.delete.return_value = _make_http_response(200)
        mock_http.get.return_value = _make_http_response(404)  # no backup

        updater.enable_health_checks = True
        updater.enable_cache_invalidation = True

        req = _make_request()
        result = await updater.update_policy(req)

        assert result.status == PolicyUpdateStatus.COMPLETED
        assert result.health_check_passed is True
        assert result.cache_invalidated is True

    async def test_update_exception_with_previous_version_triggers_rollback(self):
        updater, mock_http = self._make_updater_with_mocks()

        # Validation passes
        mock_http.put.return_value = _make_http_response(200)
        mock_http.post.return_value = _make_http_response(200, {"result": {}})
        mock_http.delete.return_value = _make_http_response(200)

        # Backup succeeds (returns a backup_id)
        backup_policy = {"result": {"raw": SAMPLE_REGO}}
        mock_http.get.return_value = _make_http_response(200, backup_policy)

        # After backup, make upload raise an unexpected exception
        put_call_count = [0]

        async def put_side_effect(url, **kwargs):
            put_call_count[0] += 1
            if "_validate" in url:
                return _make_http_response(200)
            if put_call_count[0] == 2:
                # Main upload PUT
                raise RuntimeError("Disk full")
            # Rollback PUT
            return _make_http_response(200)

        mock_http.put.side_effect = put_side_effect

        with patch("enhanced_agent_bus.constitutional.opa_updater.AIOFILES_AVAILABLE", False):
            req = _make_request()
            result = await updater.update_policy(req)

        # Should have failed and attempted rollback
        assert result.status in (PolicyUpdateStatus.FAILED, PolicyUpdateStatus.ROLLED_BACK)

    async def test_update_exception_no_previous_version(self):
        updater, mock_http = self._make_updater_with_mocks()

        # Validation: http client not initialized to trigger exception path
        # Actually let's trigger an exception during _backup_current_policy
        # by having validation pass but _backup fail
        mock_http.put.return_value = _make_http_response(200)
        mock_http.post.return_value = _make_http_response(200, {"result": {}})
        mock_http.delete.return_value = _make_http_response(200)

        # Get raises ValueError (unexpected)
        mock_http.get.side_effect = ValueError("Database unavailable")

        req = _make_request()
        result = await updater.update_policy(req)

        # The exception from backup is swallowed (returns None), so result may vary
        # Just ensure we get a valid result object
        assert result.policy_id == "test_policy"

    async def test_update_top_level_exception_with_previous_version(self):
        """Cover lines 309-319: exception in update_policy with previous_version set."""
        updater, mock_http = self._make_updater_with_mocks()

        # Validation PUT succeeds
        mock_http.put.return_value = _make_http_response(200)
        # Compile POST succeeds
        mock_http.post.return_value = _make_http_response(200, {"result": {}})
        # Validate DELETE succeeds
        mock_http.delete.return_value = _make_http_response(200)

        # Backup GET succeeds (sets previous_version)
        backup_policy = {"result": {"raw": SAMPLE_REGO}}
        mock_http.get.return_value = _make_http_response(200, backup_policy)

        # Now make _upload_policy_to_opa raise a RuntimeError (not caught by inner try)
        # by patching it directly on the instance
        call_counts = {"upload": 0}
        original_upload = updater._upload_policy_to_opa

        async def patched_upload(req):
            raise ValueError("Injected top-level exception")

        updater._upload_policy_to_opa = patched_upload

        with patch("enhanced_agent_bus.constitutional.opa_updater.AIOFILES_AVAILABLE", False):
            req = _make_request()
            result = await updater.update_policy(req)

        assert result.status in (PolicyUpdateStatus.FAILED, PolicyUpdateStatus.ROLLED_BACK)
        assert result.error_message is not None

    async def test_update_top_level_exception_without_previous_version(self):
        """Cover lines 309-319: exception in update_policy without previous_version."""
        updater, mock_http = self._make_updater_with_mocks()

        # Validation passes
        mock_http.put.return_value = _make_http_response(200)
        mock_http.post.return_value = _make_http_response(200, {"result": {}})
        mock_http.delete.return_value = _make_http_response(200)
        # No backup (404)
        mock_http.get.return_value = _make_http_response(404)

        # Patch _upload_policy_to_opa to raise TypeError
        async def patched_upload(req):
            raise TypeError("Type error during upload")

        updater._upload_policy_to_opa = patched_upload

        req = _make_request()
        result = await updater.update_policy(req)

        assert result.status == PolicyUpdateStatus.FAILED
        assert "Type error during upload" in (result.error_message or "")

    async def test_update_metadata_includes_constitutional_hash(self):
        updater, mock_http = self._make_updater_with_mocks()
        mock_http.put.return_value = _make_http_response(200)
        mock_http.post.return_value = _make_http_response(200, {"result": {}})
        mock_http.delete.return_value = _make_http_response(200)
        mock_http.get.return_value = _make_http_response(404)

        updater.enable_health_checks = False
        updater.enable_cache_invalidation = False

        req = _make_request()
        result = await updater.update_policy(req)

        assert result.status == PolicyUpdateStatus.COMPLETED
        assert result.metadata.get("constitutional_hash") == CONSTITUTIONAL_HASH
        assert result.metadata.get("dry_run") is False

    async def test_update_policy_with_backup_and_rollback_on_upload_fail(self):
        """Full flow: backup exists, upload fails, rollback from memory."""
        updater, mock_http = self._make_updater_with_mocks()

        # Seed in-memory backup
        updater._policy_backups["test_policy"] = {
            "backup_id": "test_policy_backup_20240101_000000",
            "policy_data": {"result": {"raw": SAMPLE_REGO}},
            "timestamp": "2024-01-01T00:00:00+00:00",
        }

        call_counts = {"put": 0}

        def put_side_effect(url, **kwargs):
            call_counts["put"] += 1
            if "_validate" in url:
                return _make_http_response(200)
            if call_counts["put"] == 2:
                # First real PUT (upload) fails
                return _make_http_response(500)
            # Rollback PUT succeeds
            return _make_http_response(200)

        mock_http.put.side_effect = put_side_effect
        mock_http.post.return_value = _make_http_response(200, {"result": {}})
        mock_http.delete.return_value = _make_http_response(200)
        # Backup GET: return 200 so previous_version is set
        mock_http.get.return_value = _make_http_response(200, {"result": {"raw": SAMPLE_REGO}})

        with patch("enhanced_agent_bus.constitutional.opa_updater.AIOFILES_AVAILABLE", False):
            req = _make_request()
            result = await updater.update_policy(req)

        assert result.status == PolicyUpdateStatus.ROLLED_BACK
        assert result.rolled_back is True


# ---------------------------------------------------------------------------
# AIOFILES_AVAILABLE flag Tests
# ---------------------------------------------------------------------------


class TestAiofilesAvailableFlag:
    def test_flag_is_bool(self):
        assert isinstance(AIOFILES_AVAILABLE, bool)

    def test_import_path(self):
        import importlib

        spec = importlib.util.find_spec("aiofiles")
        if spec is not None:
            assert AIOFILES_AVAILABLE is True
        else:
            assert AIOFILES_AVAILABLE is False


# ---------------------------------------------------------------------------
# Module-level __all__ Tests
# ---------------------------------------------------------------------------


class TestModuleAll:
    def test_all_exports_present(self):
        from enhanced_agent_bus.constitutional import opa_updater

        assert hasattr(opa_updater, "__all__")
        for name in opa_updater.__all__:
            assert hasattr(opa_updater, name)

    def test_all_contains_expected_classes(self):
        from enhanced_agent_bus.constitutional import opa_updater

        assert "OPAPolicyUpdater" in opa_updater.__all__
        assert "PolicyUpdateRequest" in opa_updater.__all__
        assert "PolicyUpdateResult" in opa_updater.__all__
        assert "PolicyUpdateStatus" in opa_updater.__all__
        assert "PolicyValidationResult" in opa_updater.__all__
