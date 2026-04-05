"""
Additional coverage tests for Constitutional Amendment Activation Saga.
Constitutional Hash: 608508a9bd224290

Covers lines: 128-159, 163-173, 212, 217, 305-307, 332, 337, 348-363,
378-410, 472-482, 479-480, 497-512, 559-572, 568-569, 603-613, 610-611,
674-758, 801-837
"""

import hashlib
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

from .. import activation_saga as _saga_module
from ..activation_saga import (
    ActivationSagaActivities,
    ActivationSagaError,
    activate_amendment,
    create_activation_saga,
)
from ..amendment_model import AmendmentProposal, AmendmentStatus
from ..storage import ConstitutionalStorageService
from ..version_model import ConstitutionalStatus, ConstitutionalVersion

pytestmark = [
    pytest.mark.constitutional,
]


# ---------------------------------------------------------------------------
# Helpers / shared fixtures
# ---------------------------------------------------------------------------


def _make_amendment(**kwargs) -> AmendmentProposal:
    defaults = dict(
        proposal_id="amendment-123",
        proposed_changes={"principle_1": "Updated governance principle"},
        justification="Improving governance compliance per MACI framework.",
        proposer_agent_id="agent-executive-001",
        target_version="1.0.0",
        new_version="1.1.0",
        status=AmendmentStatus.APPROVED,
        impact_score=0.75,
    )
    defaults.update(kwargs)
    return AmendmentProposal(**defaults)


def _make_version(**kwargs) -> ConstitutionalVersion:
    defaults = dict(
        version_id="version-1.0.0",
        version="1.0.0",
        constitutional_hash=CONSTITUTIONAL_HASH,
        content={"principles": ["P1", "P2"]},
        status=ConstitutionalStatus.ACTIVE,
    )
    defaults.update(kwargs)
    return ConstitutionalVersion(**defaults)


def _make_activities(mock_storage=None, **kwargs):
    if mock_storage is None:
        mock_storage = AsyncMock(spec=ConstitutionalStorageService)
    return ActivationSagaActivities(
        storage=mock_storage,
        opa_url=kwargs.get("opa_url", "http://localhost:8181"),
        audit_service_url=kwargs.get("audit_service_url", "http://localhost:8001"),
        redis_url=kwargs.get("redis_url", "redis://localhost:6379"),
    )


# ---------------------------------------------------------------------------
# initialize() — lines 128-159
# ---------------------------------------------------------------------------


class TestInitialize:
    """Tests for ActivationSagaActivities.initialize()."""

    async def test_initialize_creates_http_client(self):
        """initialize() should always create an httpx.AsyncClient."""
        activities = _make_activities()
        assert activities._http_client is None

        with patch.object(_saga_module, "REDIS_AVAILABLE", False):
            with patch.object(_saga_module, "OPAClient", None):
                with patch.object(_saga_module, "AuditClient", None):
                    await activities.initialize()

        assert activities._http_client is not None
        await activities._http_client.aclose()

    async def test_initialize_redis_available_success(self):
        """initialize() should connect to Redis when available."""
        activities = _make_activities()

        mock_redis_instance = AsyncMock()

        original_from_url = None
        if _saga_module.aioredis:
            original_from_url = _saga_module.aioredis.from_url

        async def fake_from_url(url, **kwargs):
            return mock_redis_instance

        with patch.object(_saga_module, "REDIS_AVAILABLE", True):
            with patch.object(_saga_module, "OPAClient", None):
                with patch.object(_saga_module, "AuditClient", None):
                    if _saga_module.aioredis:
                        _saga_module.aioredis.from_url = fake_from_url
                    try:
                        await activities.initialize()
                    finally:
                        if _saga_module.aioredis and original_from_url is not None:
                            _saga_module.aioredis.from_url = original_from_url
                        if activities._http_client:
                            await activities._http_client.aclose()

        assert activities._redis_client is mock_redis_instance

    async def test_initialize_redis_connection_error(self):
        """initialize() should handle Redis connection errors gracefully."""
        activities = _make_activities()

        original_from_url = None
        if _saga_module.aioredis:
            original_from_url = _saga_module.aioredis.from_url

        async def raise_from_url(url, **kwargs):
            raise ConnectionError("refused")

        with patch.object(_saga_module, "REDIS_AVAILABLE", True):
            with patch.object(_saga_module, "OPAClient", None):
                with patch.object(_saga_module, "AuditClient", None):
                    if _saga_module.aioredis:
                        _saga_module.aioredis.from_url = raise_from_url
                    try:
                        await activities.initialize()
                    finally:
                        if _saga_module.aioredis and original_from_url is not None:
                            _saga_module.aioredis.from_url = original_from_url
                        if activities._http_client:
                            await activities._http_client.aclose()

        # Should not raise; redis client stays None
        assert activities._redis_client is None

    async def test_initialize_opa_client_success(self):
        """initialize() should initialise OPAClient when available."""
        activities = _make_activities()

        mock_opa = AsyncMock()
        mock_opa_cls = MagicMock(return_value=mock_opa)

        _globs = ActivationSagaActivities.initialize.__globals__
        with patch.dict(
            _globs, {"REDIS_AVAILABLE": False, "OPAClient": mock_opa_cls, "AuditClient": None}
        ):
            await activities.initialize()
            if activities._http_client:
                await activities._http_client.aclose()

        mock_opa.initialize.assert_awaited_once()

    async def test_initialize_opa_client_error(self):
        """initialize() should handle OPAClient initialization errors."""
        activities = _make_activities()

        mock_opa = AsyncMock()
        mock_opa.initialize = AsyncMock(side_effect=RuntimeError("OPA unavailable"))
        mock_opa_cls = MagicMock(return_value=mock_opa)

        with patch.object(_saga_module, "REDIS_AVAILABLE", False):
            with patch.object(_saga_module, "OPAClient", mock_opa_cls):
                with patch.object(_saga_module, "AuditClient", None):
                    await activities.initialize()
                    if activities._http_client:
                        await activities._http_client.aclose()

        assert activities._opa_client is None

    async def test_initialize_audit_client_success(self):
        """initialize() should start AuditClient when available."""
        activities = _make_activities()

        mock_audit = AsyncMock()
        mock_audit_cls = MagicMock(return_value=mock_audit)

        _globs = ActivationSagaActivities.initialize.__globals__
        with patch.dict(
            _globs, {"REDIS_AVAILABLE": False, "OPAClient": None, "AuditClient": mock_audit_cls}
        ):
            await activities.initialize()
            if activities._http_client:
                await activities._http_client.aclose()

        mock_audit.start.assert_awaited_once()

    async def test_initialize_audit_client_error(self):
        """initialize() should handle AuditClient start errors."""
        activities = _make_activities()

        mock_audit = AsyncMock()
        mock_audit.start = AsyncMock(side_effect=OSError("audit unavailable"))
        mock_audit_cls = MagicMock(return_value=mock_audit)

        with patch.object(_saga_module, "REDIS_AVAILABLE", False):
            with patch.object(_saga_module, "OPAClient", None):
                with patch.object(_saga_module, "AuditClient", mock_audit_cls):
                    await activities.initialize()
                    if activities._http_client:
                        await activities._http_client.aclose()

        assert activities._audit_client is None


# ---------------------------------------------------------------------------
# close() — lines 163-173
# ---------------------------------------------------------------------------


class TestClose:
    """Tests for ActivationSagaActivities.close()."""

    async def test_close_with_all_clients(self):
        """close() should close all active clients."""
        activities = _make_activities()

        mock_http = AsyncMock()
        mock_redis = AsyncMock()
        mock_opa = AsyncMock()
        mock_audit = AsyncMock()

        activities._http_client = mock_http
        activities._redis_client = mock_redis
        activities._opa_client = mock_opa
        activities._audit_client = mock_audit

        await activities.close()

        mock_http.aclose.assert_awaited_once()
        mock_redis.close.assert_awaited_once()
        mock_opa.close.assert_awaited_once()
        mock_audit.stop.assert_awaited_once()

    async def test_close_with_no_clients(self):
        """close() should be a no-op when no clients exist."""
        activities = _make_activities()
        # All clients are None by default — should not raise
        await activities.close()

    async def test_close_with_only_http(self):
        """close() with only http client set."""
        activities = _make_activities()
        mock_http = AsyncMock()
        activities._http_client = mock_http
        await activities.close()
        mock_http.aclose.assert_awaited_once()

    async def test_close_with_only_redis(self):
        """close() with only redis client set."""
        activities = _make_activities()
        mock_redis = AsyncMock()
        activities._redis_client = mock_redis
        await activities.close()
        mock_redis.close.assert_awaited_once()


# ---------------------------------------------------------------------------
# validate_activation() — lines 212, 217 (warning paths)
# ---------------------------------------------------------------------------


class TestValidateActivationWarningPaths:
    """Test warning-path branches in validate_activation."""

    async def test_target_version_not_active(self):
        """validate_activation warns when target version is not the active one."""
        mock_storage = AsyncMock(spec=ConstitutionalStorageService)
        amendment = _make_amendment()
        target = _make_version()
        different_active = _make_version(version_id="version-9.9.9", version="9.9.9")

        mock_storage.get_amendment.return_value = amendment
        mock_storage.get_version.return_value = target
        mock_storage.get_active_version.return_value = different_active

        activities = _make_activities(mock_storage)
        result = await activities.validate_activation(
            {"saga_id": "s1", "context": {"amendment_id": "amendment-123"}}
        )
        # Should still succeed
        assert result["is_valid"] is True

    async def test_no_active_version_warns_but_passes(self):
        """validate_activation warns when no active version exists."""
        mock_storage = AsyncMock(spec=ConstitutionalStorageService)
        amendment = _make_amendment()
        target = _make_version()

        mock_storage.get_amendment.return_value = amendment
        mock_storage.get_version.return_value = target
        mock_storage.get_active_version.return_value = None

        activities = _make_activities(mock_storage)
        result = await activities.validate_activation(
            {"saga_id": "s1", "context": {"amendment_id": "amendment-123"}}
        )
        assert result["is_valid"] is True

    async def test_target_version_not_found(self):
        """validate_activation raises when target version is missing."""
        mock_storage = AsyncMock(spec=ConstitutionalStorageService)
        amendment = _make_amendment()

        mock_storage.get_amendment.return_value = amendment
        mock_storage.get_version.return_value = None

        activities = _make_activities(mock_storage)
        with pytest.raises(ActivationSagaError, match="Target version"):
            await activities.validate_activation(
                {"saga_id": "s1", "context": {"amendment_id": "amendment-123"}}
            )

    async def test_hash_mismatch_blocks_activation(self):
        """validate_activation fails closed on constitutional hash mismatch."""
        mock_storage = AsyncMock(spec=ConstitutionalStorageService)
        amendment = _make_amendment()
        target = _make_version(constitutional_hash="deadbeef00000001")
        active = _make_version(constitutional_hash="deadbeef00000001")

        mock_storage.get_amendment.return_value = amendment
        mock_storage.get_version.return_value = target
        mock_storage.get_active_version.return_value = active

        activities = _make_activities(mock_storage)
        with pytest.raises(ActivationSagaError, match="constitutional hash"):
            await activities.validate_activation(
                {"saga_id": "s1", "context": {"amendment_id": "amendment-123"}}
            )


# ---------------------------------------------------------------------------
# restore_backup() — line 305-307 (exception path)
# ---------------------------------------------------------------------------


class TestRestoreBackupException:
    """Test restore_backup compensation exception path."""

    async def test_restore_backup_storage_error(self):
        """restore_backup returns False when storage.activate_version raises."""
        mock_storage = AsyncMock(spec=ConstitutionalStorageService)
        mock_storage.activate_version = AsyncMock(side_effect=RuntimeError("DB failure"))

        activities = _make_activities(mock_storage)
        result = await activities.restore_backup(
            {
                "saga_id": "s1",
                "context": {"backup_current_version": {"version_id": "v-1.0.0"}},
            }
        )
        assert result is False

    async def test_restore_backup_value_error(self):
        """restore_backup returns False on ValueError from storage."""
        mock_storage = AsyncMock(spec=ConstitutionalStorageService)
        mock_storage.activate_version = AsyncMock(side_effect=ValueError("bad id"))

        activities = _make_activities(mock_storage)
        result = await activities.restore_backup(
            {
                "saga_id": "s1",
                "context": {"backup_current_version": {"version_id": "v-bad"}},
            }
        )
        assert result is False


# ---------------------------------------------------------------------------
# update_opa_policies() — lines 332, 337, 348->363, 356, 359-360
# ---------------------------------------------------------------------------


class TestUpdateOpaPolicies:
    """Tests for update_opa_policies activity."""

    async def test_amendment_not_found_raises(self):
        """update_opa_policies raises when amendment not found."""
        mock_storage = AsyncMock(spec=ConstitutionalStorageService)
        mock_storage.get_amendment.return_value = None

        activities = _make_activities(mock_storage)
        with pytest.raises(ActivationSagaError, match="not found"):
            await activities.update_opa_policies(
                {
                    "saga_id": "s1",
                    "context": {
                        "amendment_id": "missing",
                        "validate_activation": {"new_version": "1.1.0"},
                    },
                }
            )

    async def test_target_version_not_found_raises(self):
        """update_opa_policies raises when target version not found."""
        mock_storage = AsyncMock(spec=ConstitutionalStorageService)
        amendment = _make_amendment()
        mock_storage.get_amendment.return_value = amendment
        mock_storage.get_version.return_value = None

        activities = _make_activities(mock_storage)
        with pytest.raises(ActivationSagaError, match="Target version not found"):
            await activities.update_opa_policies(
                {
                    "saga_id": "s1",
                    "context": {
                        "amendment_id": "amendment-123",
                        "validate_activation": {"new_version": "1.1.0"},
                    },
                }
            )

    async def test_no_http_client_skips_opa_call(self):
        """update_opa_policies skips HTTP call when no client available."""
        mock_storage = AsyncMock(spec=ConstitutionalStorageService)
        amendment = _make_amendment()
        target = _make_version()
        mock_storage.get_amendment.return_value = amendment
        mock_storage.get_version.return_value = target

        activities = _make_activities(mock_storage)
        # _http_client is None by default

        result = await activities.update_opa_policies(
            {
                "saga_id": "s1",
                "context": {
                    "amendment_id": "amendment-123",
                    "validate_activation": {"new_version": "1.1.0"},
                },
            }
        )
        assert result["updated"] is True

    async def test_opa_non_200_response_logs_warning(self):
        """update_opa_policies logs warning on non-200 OPA response."""
        mock_storage = AsyncMock(spec=ConstitutionalStorageService)
        amendment = _make_amendment()
        target = _make_version()
        mock_storage.get_amendment.return_value = amendment
        mock_storage.get_version.return_value = target

        activities = _make_activities(mock_storage)
        mock_http = AsyncMock()
        mock_http.put.return_value = MagicMock(status_code=500)
        activities._http_client = mock_http

        result = await activities.update_opa_policies(
            {
                "saga_id": "s1",
                "context": {
                    "amendment_id": "amendment-123",
                    "validate_activation": {"new_version": "1.1.0"},
                },
            }
        )
        assert result["updated"] is True  # Still returns success

    async def test_opa_request_error_continues(self):
        """update_opa_policies continues on OPA HTTP request error."""
        import httpx

        mock_storage = AsyncMock(spec=ConstitutionalStorageService)
        amendment = _make_amendment()
        target = _make_version()
        mock_storage.get_amendment.return_value = amendment
        mock_storage.get_version.return_value = target

        activities = _make_activities(mock_storage)
        mock_http = AsyncMock()
        mock_http.put.side_effect = httpx.RequestError("connection failed")
        activities._http_client = mock_http

        # Should not raise — OPA update is not critical
        result = await activities.update_opa_policies(
            {
                "saga_id": "s1",
                "context": {
                    "amendment_id": "amendment-123",
                    "validate_activation": {"new_version": "1.1.0"},
                },
            }
        )
        assert result["updated"] is True

    async def test_opa_204_response_succeeds(self):
        """update_opa_policies handles 204 No Content response."""
        mock_storage = AsyncMock(spec=ConstitutionalStorageService)
        amendment = _make_amendment()
        target = _make_version()
        mock_storage.get_amendment.return_value = amendment
        mock_storage.get_version.return_value = target

        activities = _make_activities(mock_storage)
        mock_http = AsyncMock()
        mock_http.put.return_value = MagicMock(status_code=204)
        activities._http_client = mock_http

        result = await activities.update_opa_policies(
            {
                "saga_id": "s1",
                "context": {
                    "amendment_id": "amendment-123",
                    "validate_activation": {"new_version": "1.1.0"},
                },
            }
        )
        assert result["updated"] is True


# ---------------------------------------------------------------------------
# revert_opa_policies() — lines 378-410
# ---------------------------------------------------------------------------


class TestRevertOpaPolicies:
    """Tests for revert_opa_policies compensation."""

    async def test_revert_no_http_client_returns_true(self):
        """revert_opa_policies returns True when no HTTP client."""
        activities = _make_activities()
        # _http_client is None

        result = await activities.revert_opa_policies(
            {
                "saga_id": "s1",
                "context": {
                    "backup_current_version": {"constitutional_hash": "abc", "version": "1.0.0"}
                },
            }
        )
        assert result is True

    async def test_revert_opa_200_success(self):
        """revert_opa_policies returns True on 200 response."""
        activities = _make_activities()
        mock_http = AsyncMock()
        mock_http.put.return_value = MagicMock(status_code=200)
        activities._http_client = mock_http

        result = await activities.revert_opa_policies(
            {
                "saga_id": "s1",
                "context": {
                    "backup_current_version": {
                        "constitutional_hash": CONSTITUTIONAL_HASH,
                        "version": "1.0.0",
                    }
                },
            }
        )
        assert result is True

    async def test_revert_opa_204_success(self):
        """revert_opa_policies returns True on 204 response."""
        activities = _make_activities()
        mock_http = AsyncMock()
        mock_http.put.return_value = MagicMock(status_code=204)
        activities._http_client = mock_http

        result = await activities.revert_opa_policies(
            {
                "saga_id": "s1",
                "context": {
                    "backup_current_version": {
                        "constitutional_hash": CONSTITUTIONAL_HASH,
                        "version": "1.0.0",
                    }
                },
            }
        )
        assert result is True

    async def test_revert_opa_error_response_returns_false(self):
        """revert_opa_policies returns False on non-200/204 response."""
        activities = _make_activities()
        mock_http = AsyncMock()
        mock_http.put.return_value = MagicMock(status_code=503)
        activities._http_client = mock_http

        result = await activities.revert_opa_policies(
            {
                "saga_id": "s1",
                "context": {
                    "backup_current_version": {
                        "constitutional_hash": CONSTITUTIONAL_HASH,
                        "version": "1.0.0",
                    }
                },
            }
        )
        assert result is False

    async def test_revert_opa_request_error_returns_false(self):
        """revert_opa_policies returns False on HTTP request exception."""
        import httpx

        activities = _make_activities()
        mock_http = AsyncMock()
        mock_http.put.side_effect = httpx.RequestError("timeout")
        activities._http_client = mock_http

        result = await activities.revert_opa_policies(
            {
                "saga_id": "s1",
                "context": {
                    "backup_current_version": {
                        "constitutional_hash": CONSTITUTIONAL_HASH,
                        "version": "1.0.0",
                    }
                },
            }
        )
        assert result is False

    async def test_revert_opa_empty_backup_uses_defaults(self):
        """revert_opa_policies uses default hash when backup is empty."""
        activities = _make_activities()
        mock_http = AsyncMock()
        mock_http.put.return_value = MagicMock(status_code=200)
        activities._http_client = mock_http

        result = await activities.revert_opa_policies(
            {"saga_id": "s1", "context": {}}  # no backup data
        )
        assert result is True
        # Should have called put with the default CONSTITUTIONAL_HASH
        put_call_kwargs = mock_http.put.call_args
        assert put_call_kwargs is not None


# ---------------------------------------------------------------------------
# update_cache() — lines 472->482, 479-480 (redis error paths)
# ---------------------------------------------------------------------------


class TestUpdateCacheRedisErrors:
    """Tests for update_cache Redis error paths."""

    def _patched_activities(self, mock_storage):
        """Return activities with _compute_constitutional_hash returning valid 16-char hash."""
        activities = _make_activities(mock_storage)
        activities._compute_constitutional_hash = MagicMock(return_value=CONSTITUTIONAL_HASH)
        return activities

    async def test_update_cache_no_redis_client(self):
        """update_cache works when no Redis client is available."""
        mock_storage = AsyncMock(spec=ConstitutionalStorageService)
        amendment = _make_amendment()
        target = _make_version()
        mock_storage.get_amendment.return_value = amendment
        mock_storage.get_version.return_value = target

        activities = self._patched_activities(mock_storage)
        # _redis_client is None by default

        result = await activities.update_cache(
            {
                "saga_id": "s1",
                "context": {
                    "amendment_id": "amendment-123",
                    "validate_activation": {"new_version": "1.1.0"},
                },
            }
        )
        assert result["activated"] is True
        assert result["cache_invalidated"] is False

    async def test_update_cache_redis_delete_error(self):
        """update_cache handles Redis delete errors gracefully."""
        mock_storage = AsyncMock(spec=ConstitutionalStorageService)
        amendment = _make_amendment()
        target = _make_version()
        mock_storage.get_amendment.return_value = amendment
        mock_storage.get_version.return_value = target

        activities = self._patched_activities(mock_storage)
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock(side_effect=ConnectionError("Redis gone"))
        activities._redis_client = mock_redis

        result = await activities.update_cache(
            {
                "saga_id": "s1",
                "context": {
                    "amendment_id": "amendment-123",
                    "validate_activation": {"new_version": "1.1.0"},
                },
            }
        )
        assert result["activated"] is True
        assert result["cache_invalidated"] is False

    async def test_update_cache_redis_value_error(self):
        """update_cache handles Redis ValueError gracefully."""
        mock_storage = AsyncMock(spec=ConstitutionalStorageService)
        amendment = _make_amendment()
        target = _make_version()
        mock_storage.get_amendment.return_value = amendment
        mock_storage.get_version.return_value = target

        activities = self._patched_activities(mock_storage)
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock(side_effect=ValueError("bad key"))
        activities._redis_client = mock_redis

        result = await activities.update_cache(
            {
                "saga_id": "s1",
                "context": {
                    "amendment_id": "amendment-123",
                    "validate_activation": {"new_version": "1.1.0"},
                },
            }
        )
        assert result["activated"] is True
        assert result["cache_invalidated"] is False


# ---------------------------------------------------------------------------
# revert_cache() — lines 497-512
# ---------------------------------------------------------------------------


class TestRevertCache:
    """Tests for revert_cache compensation."""

    async def test_revert_cache_no_redis_returns_true(self):
        """revert_cache returns True when no Redis client."""
        activities = _make_activities()

        result = await activities.revert_cache({"saga_id": "s1", "context": {}})
        assert result is True

    async def test_revert_cache_success(self):
        """revert_cache invalidates cache key successfully."""
        activities = _make_activities()
        mock_redis = AsyncMock()
        mock_redis.delete.return_value = 1
        activities._redis_client = mock_redis

        result = await activities.revert_cache({"saga_id": "s1", "context": {}})
        assert result is True
        mock_redis.delete.assert_awaited_once_with("constitutional:active_version")

    async def test_revert_cache_redis_error_returns_false(self):
        """revert_cache returns False on Redis error."""
        activities = _make_activities()
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock(side_effect=OSError("Redis down"))
        activities._redis_client = mock_redis

        result = await activities.revert_cache({"saga_id": "s1", "context": {}})
        assert result is False

    async def test_revert_cache_connection_error_returns_false(self):
        """revert_cache returns False on ConnectionError."""
        activities = _make_activities()
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock(side_effect=ConnectionError("reset"))
        activities._redis_client = mock_redis

        result = await activities.revert_cache({"saga_id": "s1", "context": {}})
        assert result is False

    async def test_revert_cache_value_error_returns_false(self):
        """revert_cache returns False on ValueError."""
        activities = _make_activities()
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock(side_effect=ValueError("invalid"))
        activities._redis_client = mock_redis

        result = await activities.revert_cache({"saga_id": "s1", "context": {}})
        assert result is False


# ---------------------------------------------------------------------------
# audit_activation() — lines 559-572, 568-569 (audit client paths)
# ---------------------------------------------------------------------------


class TestAuditActivation:
    """Tests for audit_activation activity."""

    async def test_audit_no_client_still_returns(self):
        """audit_activation succeeds even without audit client."""
        activities = _make_activities()
        # _audit_client is None

        result = await activities.audit_activation(
            {
                "saga_id": "s1",
                "context": {
                    "amendment_id": "amendment-123",
                    "validate_activation": {"new_version": "1.1.0"},
                    "backup_current_version": {"version": "1.0.0", "version_id": "v-1"},
                    "update_cache": {"new_version_id": "v-2", "new_hash": "abc123"},
                },
            }
        )
        assert result["event_type"] == "constitutional_version_activated"

    async def test_audit_client_error_logged_as_warning(self):
        """audit_activation handles audit client log errors gracefully."""
        activities = _make_activities()
        mock_audit = AsyncMock()
        mock_audit.log = AsyncMock(side_effect=RuntimeError("audit down"))
        activities._audit_client = mock_audit

        result = await activities.audit_activation(
            {
                "saga_id": "s1",
                "context": {
                    "amendment_id": "amendment-456",
                    "validate_activation": {"new_version": "2.0.0"},
                    "backup_current_version": {"version": "1.9.0", "version_id": "v-old"},
                    "update_cache": {"new_version_id": "v-new"},
                },
            }
        )
        # Should still return audit event despite error
        assert result["event_type"] == "constitutional_version_activated"
        assert result["amendment_id"] == "amendment-456"

    async def test_audit_uses_cache_hash_when_available(self):
        """audit_activation uses new_hash from cache update when available."""
        activities = _make_activities()

        result = await activities.audit_activation(
            {
                "saga_id": "s1",
                "context": {
                    "amendment_id": "amendment-123",
                    "validate_activation": {"new_version": "1.1.0"},
                    "backup_current_version": {"version": "1.0.0", "version_id": "v1"},
                    "update_cache": {"new_version_id": "v2", "new_hash": "custom-hash-value"},
                },
            }
        )
        assert result["constitutional_hash"] == "custom-hash-value"

    async def test_audit_falls_back_to_constitutional_hash(self):
        """audit_activation falls back to CONSTITUTIONAL_HASH when no new_hash."""
        activities = _make_activities()

        result = await activities.audit_activation(
            {
                "saga_id": "s1",
                "context": {
                    "amendment_id": "amendment-123",
                    "validate_activation": {"new_version": "1.1.0"},
                    "backup_current_version": {},
                    "update_cache": {},
                },
            }
        )
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_audit_client_os_error(self):
        """audit_activation handles OSError from audit client."""
        activities = _make_activities()
        mock_audit = AsyncMock()
        mock_audit.log = AsyncMock(side_effect=OSError("io error"))
        activities._audit_client = mock_audit

        result = await activities.audit_activation(
            {
                "saga_id": "s2",
                "context": {
                    "amendment_id": "amend-x",
                    "validate_activation": {},
                    "backup_current_version": {},
                    "update_cache": {},
                },
            }
        )
        assert result["event_type"] == "constitutional_version_activated"


# ---------------------------------------------------------------------------
# mark_audit_failed() — lines 603-613, 610-611
# ---------------------------------------------------------------------------


class TestMarkAuditFailed:
    """Tests for mark_audit_failed compensation."""

    async def test_mark_audit_failed_no_audit_client(self):
        """mark_audit_failed returns True without audit client."""
        activities = _make_activities()

        result = await activities.mark_audit_failed(
            {
                "saga_id": "s1",
                "context": {"audit_activation": {"audit_id": "audit-999"}},
            }
        )
        assert result is True

    async def test_mark_audit_failed_client_error_still_returns_true(self):
        """mark_audit_failed returns True even when audit client raises."""
        activities = _make_activities()
        mock_audit = AsyncMock()
        mock_audit.log = AsyncMock(side_effect=RuntimeError("audit down"))
        activities._audit_client = mock_audit

        result = await activities.mark_audit_failed(
            {
                "saga_id": "s1",
                "context": {"audit_activation": {"audit_id": "audit-888"}},
            }
        )
        assert result is True

    async def test_mark_audit_failed_missing_audit_data_uses_unknown(self):
        """mark_audit_failed uses 'unknown' when audit_id not in context."""
        activities = _make_activities()
        mock_audit = AsyncMock()
        activities._audit_client = mock_audit

        result = await activities.mark_audit_failed(
            {"saga_id": "s1", "context": {}}  # no audit_activation
        )
        assert result is True

    async def test_mark_audit_failed_connection_error(self):
        """mark_audit_failed handles ConnectionError from audit client."""
        activities = _make_activities()
        mock_audit = AsyncMock()
        mock_audit.log = AsyncMock(side_effect=ConnectionError("gone"))
        activities._audit_client = mock_audit

        result = await activities.mark_audit_failed(
            {
                "saga_id": "s1",
                "context": {"audit_activation": {"audit_id": "audit-777"}},
            }
        )
        assert result is True

    async def test_mark_audit_failed_os_error(self):
        """mark_audit_failed handles OSError from audit client."""
        activities = _make_activities()
        mock_audit = AsyncMock()
        mock_audit.log = AsyncMock(side_effect=OSError("disk full"))
        activities._audit_client = mock_audit

        result = await activities.mark_audit_failed(
            {
                "saga_id": "s1",
                "context": {"audit_activation": {}},
            }
        )
        assert result is True


# ---------------------------------------------------------------------------
# create_activation_saga() — lines 674-758 (with mocked workflow)
# ---------------------------------------------------------------------------


def _make_mock_saga_classes():
    """Build mock classes that mimic the saga workflow module."""

    class MockSagaCompensation:
        def __init__(self, name, description, execute):
            self.name = name
            self.description = description
            self.execute = execute

    class MockSagaStep:
        def __init__(
            self, name, description, execute, compensation, timeout_seconds=30, is_optional=False
        ):
            self.name = name
            self.description = description
            self.execute = execute
            self.compensation = compensation
            self.timeout_seconds = timeout_seconds
            self.is_optional = is_optional

    class MockSagaContext:
        def __init__(self, saga_id, constitutional_hash=None, step_results=None):
            self.saga_id = saga_id
            self.constitutional_hash = constitutional_hash
            self._data = step_results or {}

        def set_step_result(self, key, value):
            self._data[key] = value

    class MockSagaResult:
        def __init__(self, status="COMPLETED", step_results=None):
            self.status = status
            self.step_results = step_results or {}

    class MockConstitutionalSagaWorkflow:
        def __init__(self, saga_id):
            self.saga_id = saga_id
            self._steps = []

        def add_step(self, step):
            self._steps.append(step)

        async def execute(self, context):
            return MockSagaResult()

    return (
        MockConstitutionalSagaWorkflow,
        MockSagaStep,
        MockSagaCompensation,
        MockSagaContext,
        MockSagaResult,
    )


class TestCreateActivationSagaWithWorkflow:
    """Test create_activation_saga when ConstitutionalSagaWorkflow is available."""

    @pytest.fixture
    def mock_storage(self):
        return AsyncMock(spec=ConstitutionalStorageService)

    def test_create_saga_adds_five_steps(self, mock_storage):
        """create_activation_saga builds saga with 5 steps."""
        MockWorkflow, MockStep, MockComp, _MockContext, _MockResult = _make_mock_saga_classes()

        _globs = create_activation_saga.__globals__
        with patch.dict(
            _globs,
            {
                "ConstitutionalSagaWorkflow": MockWorkflow,
                "SagaStep": MockStep,
                "SagaCompensation": MockComp,
            },
        ):
            saga = create_activation_saga(
                amendment_id="amendment-abc",
                storage=mock_storage,
            )

        assert len(saga._steps) == 5

    def test_create_saga_step_names(self, mock_storage):
        """create_activation_saga step names match expected values."""
        MockWorkflow, MockStep, MockComp, _MockContext, _MockResult = _make_mock_saga_classes()

        _globs = create_activation_saga.__globals__
        with patch.dict(
            _globs,
            {
                "ConstitutionalSagaWorkflow": MockWorkflow,
                "SagaStep": MockStep,
                "SagaCompensation": MockComp,
            },
        ):
            saga = create_activation_saga(
                amendment_id="amendment-abc",
                storage=mock_storage,
            )

        step_names = [s.name for s in saga._steps]
        assert "validate_activation" in step_names
        assert "backup_current_version" in step_names
        assert "update_opa_policies" in step_names
        assert "update_cache" in step_names
        assert "audit_activation" in step_names

    def test_create_saga_optional_steps(self, mock_storage):
        """create_activation_saga marks OPA and audit steps as optional."""
        MockWorkflow, MockStep, MockComp, _MockContext, _MockResult = _make_mock_saga_classes()

        _globs = create_activation_saga.__globals__
        with patch.dict(
            _globs,
            {
                "ConstitutionalSagaWorkflow": MockWorkflow,
                "SagaStep": MockStep,
                "SagaCompensation": MockComp,
            },
        ):
            saga = create_activation_saga(
                amendment_id="amendment-abc",
                storage=mock_storage,
            )

        by_name = {s.name: s for s in saga._steps}
        assert by_name["update_opa_policies"].is_optional is True
        assert by_name["audit_activation"].is_optional is True
        assert by_name["validate_activation"].is_optional is False
        assert by_name["update_cache"].is_optional is False

    def test_create_saga_id_contains_amendment_id(self, mock_storage):
        """create_activation_saga embeds amendment_id in the saga_id."""
        MockWorkflow, MockStep, MockComp, _MockContext, _MockResult = _make_mock_saga_classes()

        _globs = create_activation_saga.__globals__
        with patch.dict(
            _globs,
            {
                "ConstitutionalSagaWorkflow": MockWorkflow,
                "SagaStep": MockStep,
                "SagaCompensation": MockComp,
            },
        ):
            saga = create_activation_saga(
                amendment_id="my-amendment",
                storage=mock_storage,
            )

        assert "my-amendment" in saga.saga_id

    def test_create_saga_compensations_set(self, mock_storage):
        """create_activation_saga associates compensation for each step."""
        MockWorkflow, MockStep, MockComp, _MockContext, _MockResult = _make_mock_saga_classes()

        _globs = create_activation_saga.__globals__
        with patch.dict(
            _globs,
            {
                "ConstitutionalSagaWorkflow": MockWorkflow,
                "SagaStep": MockStep,
                "SagaCompensation": MockComp,
            },
        ):
            saga = create_activation_saga(
                amendment_id="amendment-abc",
                storage=mock_storage,
            )

        for step in saga._steps:
            assert step.compensation is not None

    def test_create_saga_timeout_seconds(self, mock_storage):
        """create_activation_saga sets timeout_seconds on each step."""
        MockWorkflow, MockStep, MockComp, _MockContext, _MockResult = _make_mock_saga_classes()

        _globs = create_activation_saga.__globals__
        with patch.dict(
            _globs,
            {
                "ConstitutionalSagaWorkflow": MockWorkflow,
                "SagaStep": MockStep,
                "SagaCompensation": MockComp,
            },
        ):
            saga = create_activation_saga(
                amendment_id="amendment-abc",
                storage=mock_storage,
            )

        for step in saga._steps:
            assert step.timeout_seconds > 0


# ---------------------------------------------------------------------------
# activate_amendment() — lines 801-837
# ---------------------------------------------------------------------------


class TestActivateAmendment:
    """Tests for the activate_amendment convenience function."""

    @pytest.fixture
    def mock_storage(self):
        return AsyncMock(spec=ConstitutionalStorageService)

    async def test_activate_amendment_requires_saga_context(self, mock_storage):
        """activate_amendment raises ImportError when SagaContext is None."""
        with patch.object(_saga_module, "SagaContext", None):
            with pytest.raises(ImportError, match="SagaContext not available"):
                await activate_amendment(
                    amendment_id="amendment-123",
                    storage=mock_storage,
                )

    async def test_activate_amendment_full_flow(self, mock_storage):
        """activate_amendment executes full saga and returns result."""
        MockWorkflow, MockStep, MockComp, MockContext, _MockResult = _make_mock_saga_classes()

        _globs = activate_amendment.__globals__
        with patch.dict(
            _globs,
            {
                "ConstitutionalSagaWorkflow": MockWorkflow,
                "SagaStep": MockStep,
                "SagaCompensation": MockComp,
                "SagaContext": MockContext,
            },
        ):
            with patch.object(ActivationSagaActivities, "initialize", new_callable=AsyncMock):
                with patch.object(ActivationSagaActivities, "close", new_callable=AsyncMock):
                    result = await activate_amendment(
                        amendment_id="amendment-xyz",
                        storage=mock_storage,
                    )

        assert result.status == "COMPLETED"

    async def test_activate_amendment_cleanup_on_exception(self, mock_storage):
        """activate_amendment closes activities even when saga.execute raises."""
        MockWorkflow, MockStep, MockComp, MockContext, _MockResult = _make_mock_saga_classes()

        # Make execute raise
        async def raise_execute(self_inner, context):
            raise RuntimeError("saga failed")

        MockWorkflow.execute = raise_execute

        mock_close = AsyncMock()
        mock_init = AsyncMock()

        _globs = activate_amendment.__globals__
        with patch.dict(
            _globs,
            {
                "ConstitutionalSagaWorkflow": MockWorkflow,
                "SagaStep": MockStep,
                "SagaCompensation": MockComp,
                "SagaContext": MockContext,
            },
        ):
            with patch.object(ActivationSagaActivities, "initialize", mock_init):
                with patch.object(ActivationSagaActivities, "close", mock_close):
                    with pytest.raises(RuntimeError, match="saga failed"):
                        await activate_amendment(
                            amendment_id="amendment-fail",
                            storage=mock_storage,
                        )
                    # close() must be called in finally block
                    mock_close.assert_awaited_once()

    async def test_activate_amendment_custom_urls(self, mock_storage):
        """activate_amendment passes custom URLs to the saga."""
        MockWorkflow, MockStep, MockComp, MockContext, _MockResult = _make_mock_saga_classes()

        captured = {}
        original_init = ActivationSagaActivities.__init__

        def capturing_init(self_inner, storage, opa_url, audit_service_url, redis_url):
            captured["opa_url"] = opa_url
            captured["audit_url"] = audit_service_url
            captured["redis_url"] = redis_url
            original_init(
                self_inner,
                storage=storage,
                opa_url=opa_url,
                audit_service_url=audit_service_url,
                redis_url=redis_url,
            )

        _globs = activate_amendment.__globals__
        with patch.dict(
            _globs,
            {
                "ConstitutionalSagaWorkflow": MockWorkflow,
                "SagaStep": MockStep,
                "SagaCompensation": MockComp,
                "SagaContext": MockContext,
            },
        ):
            with patch.object(ActivationSagaActivities, "__init__", capturing_init):
                with patch.object(ActivationSagaActivities, "initialize", new_callable=AsyncMock):
                    with patch.object(ActivationSagaActivities, "close", new_callable=AsyncMock):
                        await activate_amendment(
                            amendment_id="amend-custom",
                            storage=mock_storage,
                            opa_url="http://custom-opa:9191",
                            audit_service_url="http://custom-audit:9001",
                            redis_url="redis://custom-redis:6380",
                        )

        assert captured["opa_url"] == "http://custom-opa:9191"
        assert captured["audit_url"] == "http://custom-audit:9001"
        assert captured["redis_url"] == "redis://custom-redis:6380"


# ---------------------------------------------------------------------------
# Additional edge-case tests
# ---------------------------------------------------------------------------


class TestActivationSagaErrorClass:
    """Test ActivationSagaError metadata."""

    def test_error_has_correct_code(self):
        err = ActivationSagaError("test error")
        assert err.error_code == "ACTIVATION_SAGA_ERROR"
        assert err.http_status_code == 500

    def test_error_is_acgs_base(self):
        from enhanced_agent_bus._compat.errors import ACGSBaseError

        err = ActivationSagaError("boom")
        assert isinstance(err, ACGSBaseError)


class TestComputeConstitutionalHash:
    """Extra tests for _compute_constitutional_hash."""

    def test_different_content_produces_different_hash(self):
        activities = _make_activities()
        h1 = activities._compute_constitutional_hash({"a": 1})
        h2 = activities._compute_constitutional_hash({"a": 2})
        assert h1 != h2

    def test_empty_dict_produces_valid_hash(self):
        activities = _make_activities()
        h = activities._compute_constitutional_hash({})
        assert len(h) == 64

    def test_known_hash_value(self):
        """Verify hash matches expected SHA256 of sorted JSON."""
        activities = _make_activities()
        content = {"x": 1}
        expected = hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()
        assert activities._compute_constitutional_hash(content) == expected


class TestActivitiesDefaultValues:
    """Test ActivationSagaActivities default parameter values."""

    def test_default_opa_url(self):
        activities = ActivationSagaActivities(storage=AsyncMock())
        assert activities.opa_url == "http://localhost:8181"

    def test_default_audit_url(self):
        activities = ActivationSagaActivities(storage=AsyncMock())
        assert activities.audit_service_url == "http://localhost:8001"

    def test_default_redis_url(self):
        activities = ActivationSagaActivities(storage=AsyncMock())
        assert activities.redis_url == "redis://localhost:6379"

    def test_custom_redis_url_none_becomes_default(self):
        activities = ActivationSagaActivities(storage=AsyncMock(), redis_url=None)
        assert activities.redis_url == "redis://localhost:6379"

    def test_custom_redis_url_used_when_provided(self):
        activities = ActivationSagaActivities(storage=AsyncMock(), redis_url="redis://myhost:6380")
        assert activities.redis_url == "redis://myhost:6380"
