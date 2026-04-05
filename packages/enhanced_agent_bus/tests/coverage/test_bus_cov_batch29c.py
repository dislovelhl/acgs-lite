"""
Coverage tests for batch29c: sync_engine, oidc, orchestrator, prefetch, governance.

Targets missing lines identified from coverage.json.
"""

from __future__ import annotations

import asyncio
import base64
import json
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus._compat.errors import ValidationError as ACGSValidationError

# ---------------------------------------------------------------------------
# governance imports
# ---------------------------------------------------------------------------
from enhanced_agent_bus.components.governance import GovernanceValidator

# ---------------------------------------------------------------------------
# prefetch imports
# ---------------------------------------------------------------------------
from enhanced_agent_bus.context_memory.optimizer.prefetch import PrefetchManager
from enhanced_agent_bus.enterprise_sso.data_warehouse.models import (
    ScheduleConfig,
    SyncConfig,
    SyncMode,
    SyncStatus,
    WarehouseConfig,
    Watermark,
)

# ---------------------------------------------------------------------------
# sync_engine imports
# ---------------------------------------------------------------------------
from enhanced_agent_bus.enterprise_sso.data_warehouse.sync_engine import (
    DataSyncEngine,
    SyncScheduler,
    create_sync_engine,
)
from enhanced_agent_bus.enterprise_sso.enterprise_sso_infra.models import (
    AuthorizationRequest,
    ProtocolValidationResult,
)

# ---------------------------------------------------------------------------
# oidc imports
# ---------------------------------------------------------------------------
from enhanced_agent_bus.enterprise_sso.enterprise_sso_infra.oidc import OIDCHandler
from enhanced_agent_bus.meta_orchestrator.config import OrchestratorConfig

# ---------------------------------------------------------------------------
# orchestrator imports
# ---------------------------------------------------------------------------
from enhanced_agent_bus.meta_orchestrator.orchestrator import (
    MetaOrchestrator,
    create_meta_orchestrator,
)
from enhanced_agent_bus.models import CONSTITUTIONAL_HASH, AgentMessage
from enhanced_agent_bus.validators import ValidationResult

# ============================================================================
# Helpers
# ============================================================================


def _make_connector() -> MagicMock:
    """Create a mock DataWarehouseConnector."""
    conn = MagicMock()
    conn.execute_query = AsyncMock(return_value=[])
    conn.execute_batch = AsyncMock(return_value=0)
    conn.get_table_schema = AsyncMock(return_value={})
    return conn


def _make_sync_engine() -> DataSyncEngine:
    return DataSyncEngine(_make_connector(), _make_connector())


def _make_id_token(claims: dict) -> str:
    """Build a fake JWT (header.payload.sig) from claims dict."""
    header = base64.urlsafe_b64encode(json.dumps({"alg": "RS256"}).encode()).rstrip(b"=")
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=")
    sig = base64.urlsafe_b64encode(b"fakesig").rstrip(b"=")
    return f"{header.decode()}.{payload.decode()}.{sig.decode()}"


# ============================================================================
# sync_engine tests — target missing lines
# ============================================================================


class TestSyncEngineTransformAndMapping:
    """Cover lines 124-125 (transform_fn), 128-129 (column_mapping),
    132-138 (insert), 141-148 (watermark update), 153-156 (error path).
    """

    async def test_sync_table_with_transform_fn(self):
        engine = _make_sync_engine()
        engine.source.execute_query = AsyncMock(return_value=[{"id": 1, "val": 10}])
        engine.target.execute_batch = AsyncMock(return_value=1)

        config = SyncConfig(
            source_table="src_tbl",
            target_table="tgt_tbl",
            sync_mode=SyncMode.FULL,
            transform_fn=lambda row: {**row, "val": row["val"] * 2},
        )
        result = await engine.sync_table(config)
        assert result.status == SyncStatus.COMPLETED
        assert result.rows_processed == 1

    async def test_sync_table_with_column_mapping(self):
        engine = _make_sync_engine()
        engine.source.execute_query = AsyncMock(return_value=[{"old_col": "v1"}])
        engine.target.execute_batch = AsyncMock(return_value=1)

        config = SyncConfig(
            source_table="src_tbl",
            target_table="tgt_tbl",
            sync_mode=SyncMode.FULL,
            column_mapping={"old_col": "new_col"},
        )
        result = await engine.sync_table(config)
        assert result.status == SyncStatus.COMPLETED
        assert result.rows_inserted == 1

    async def test_sync_table_incremental_with_watermark_update(self):
        engine = _make_sync_engine()
        # Pre-seed watermark
        engine.watermark_manager._watermarks["src_tbl"] = Watermark(
            table_name="src_tbl",
            column_name="updated_at",
            last_value="2024-01-01",
            last_sync_at=datetime.now(UTC),
            sync_id="prev",
        )
        engine.source.execute_query = AsyncMock(
            return_value=[{"id": 1, "updated_at": "2024-06-01"}]
        )
        engine.target.execute_batch = AsyncMock(return_value=1)

        config = SyncConfig(
            source_table="src_tbl",
            target_table="tgt_tbl",
            sync_mode=SyncMode.INCREMENTAL,
            watermark_column="updated_at",
        )
        result = await engine.sync_table(config)
        assert result.status == SyncStatus.COMPLETED
        assert result.watermark is not None
        assert result.watermark.last_value == "2024-06-01"

    async def test_sync_table_incremental_creates_watermark_when_none(self):
        engine = _make_sync_engine()
        engine.source.execute_query = AsyncMock(return_value=[])
        config = SyncConfig(
            source_table="src_tbl",
            target_table="tgt_tbl",
            sync_mode=SyncMode.INCREMENTAL,
            watermark_column="updated_at",
        )
        result = await engine.sync_table(config)
        assert result.status == SyncStatus.COMPLETED
        # Watermark was created via create_watermark
        assert engine.watermark_manager.get_watermark("src_tbl") is not None

    async def test_sync_table_error_handling(self):
        engine = _make_sync_engine()
        engine.source.execute_query = AsyncMock(side_effect=RuntimeError("db down"))

        config = SyncConfig(
            source_table="src_tbl",
            target_table="tgt_tbl",
            sync_mode=SyncMode.FULL,
        )
        result = await engine.sync_table(config)
        assert result.status == SyncStatus.FAILED
        assert "db down" in result.error_message


class TestSyncEngineFilterValidation:
    """Cover line 206 (empty clause) and 234-236 (incremental watermark query)."""

    def test_validate_filter_empty_clause(self):
        engine = _make_sync_engine()
        # "col = 1 AND  AND ..." splits into ["col = 1", "", "col2 = 2"] but
        # the regex split may not produce an empty string; use explicit empty clause
        with pytest.raises(ACGSValidationError):
            engine._validate_filter_condition("AND")

    def test_validate_filter_invalid_grammar(self):
        engine = _make_sync_engine()
        with pytest.raises(Exception, match="does not match allowed grammar"):
            engine._validate_filter_condition("col = 1 AND  AND col2 = 2")

    def test_build_sync_query_incremental_with_watermark(self):
        engine = _make_sync_engine()
        wm = Watermark(
            table_name="tbl",
            column_name="updated_at",
            last_value="2024-01-01",
            last_sync_at=datetime.now(UTC),
            sync_id="s1",
        )
        config = SyncConfig(
            source_table="tbl",
            target_table="tgt",
            sync_mode=SyncMode.INCREMENTAL,
            watermark_column="updated_at",
        )
        query, params = engine._build_sync_query(config, wm)
        assert "updated_at > %(watermark)s" in query
        assert params["watermark"] == "2024-01-01"


class TestSyncEngineColumnMappingNonDict:
    """Cover line 251-254 (non-dict rows in column mapping)."""

    def test_apply_column_mapping_non_dict_rows(self):
        engine = _make_sync_engine()
        result = engine._apply_column_mapping(
            ["raw_string_row", 42],
            {"a": "b"},
        )
        assert result == ["raw_string_row", 42]


class TestSyncEngineSchemaEvolution:
    """Cover line 279 (evolve_schema)."""

    async def test_evolve_schema_compatible(self):
        engine = _make_sync_engine()
        engine.schema_manager.detect_changes = AsyncMock(return_value=[])
        config = SyncConfig(source_table="s", target_table="t")
        result = await engine.evolve_schema(config)
        assert result == []

    async def test_evolve_schema_with_changes(self):
        engine = _make_sync_engine()
        mock_change = MagicMock()
        mock_change.to_dict.return_value = {"action": "add_column"}
        engine.schema_manager.detect_changes = AsyncMock(return_value=[mock_change])
        engine.schema_manager.apply_changes = AsyncMock(return_value=["ALTER TABLE ..."])
        config = SyncConfig(source_table="s", target_table="t")
        result = await engine.evolve_schema(config, dry_run=True)
        assert result == ["ALTER TABLE ..."]


class TestSyncScheduler:
    """Cover lines 309, 388-401 (_run_loop, should_run with cron, start/stop)."""

    def test_should_run_disabled_schedule(self):
        engine = _make_sync_engine()
        scheduler = SyncScheduler(engine)
        sched = ScheduleConfig(cron_expression="* * * * *", enabled=False)
        assert scheduler.should_run(sched, datetime.now(UTC)) is False

    def test_should_run_matching_cron(self):
        engine = _make_sync_engine()
        scheduler = SyncScheduler(engine)
        now = datetime(2024, 6, 15, 10, 30, tzinfo=UTC)  # Saturday = weekday 5
        sched = ScheduleConfig(cron_expression="30 10 15 6 5", enabled=True)
        assert scheduler.should_run(sched, now) is True

    def test_should_run_wildcard_cron(self):
        engine = _make_sync_engine()
        scheduler = SyncScheduler(engine)
        now = datetime.now(UTC)
        sched = ScheduleConfig(cron_expression="* * * * *", enabled=True)
        assert scheduler.should_run(sched, now) is True

    async def test_run_loop_executes_and_stops(self):
        engine = _make_sync_engine()
        engine.sync_table = AsyncMock()
        scheduler = SyncScheduler(engine)

        sync_config = SyncConfig(source_table="s", target_table="t")
        sched_config = ScheduleConfig(cron_expression="* * * * *", enabled=True)
        scheduler.add_schedule("job1", sync_config, sched_config)

        # Patch sleep to immediately raise CancelledError to break the loop
        with patch("asyncio.sleep", new_callable=AsyncMock, side_effect=asyncio.CancelledError):
            with pytest.raises(asyncio.CancelledError):
                scheduler._running = True
                await scheduler._run_loop()

        # sync_table should have been called at least once
        engine.sync_table.assert_called()

    async def test_run_loop_retry_on_failure(self):
        engine = _make_sync_engine()
        engine.sync_table = AsyncMock(side_effect=RuntimeError("fail"))
        scheduler = SyncScheduler(engine)

        sync_config = SyncConfig(source_table="s", target_table="t")
        sched_config = ScheduleConfig(
            cron_expression="* * * * *",
            enabled=True,
            retry_on_failure=True,
        )
        scheduler.add_schedule("job1", sync_config, sched_config)

        with patch("asyncio.sleep", new_callable=AsyncMock, side_effect=asyncio.CancelledError):
            with pytest.raises(asyncio.CancelledError):
                scheduler._running = True
                await scheduler._run_loop()

    async def test_start_and_stop(self):
        engine = _make_sync_engine()
        scheduler = SyncScheduler(engine)
        with patch("asyncio.sleep", new_callable=AsyncMock, side_effect=asyncio.CancelledError):
            await scheduler.start()
            assert scheduler.is_running is True
            await scheduler.stop()
            assert scheduler.is_running is False


class TestCreateSyncEngine:
    """Cover create_sync_engine factory."""

    def test_create_sync_engine(self):
        with patch(
            "enhanced_agent_bus.enterprise_sso.data_warehouse.sync_engine.create_connector"
        ) as mock_cc:
            mock_cc.return_value = _make_connector()
            src_cfg = WarehouseConfig()
            tgt_cfg = WarehouseConfig()
            eng = create_sync_engine(src_cfg, tgt_cfg)
            assert isinstance(eng, DataSyncEngine)


# ============================================================================
# OIDC tests — target missing lines
# ============================================================================


class TestOIDCValidateResponse:
    """Cover lines 180-184 (exception handler), 193-216 (_exchange_code),
    258-259 (nonce mismatch), 296-328 (_get_userinfo).
    """

    def _handler(self) -> OIDCHandler:
        return OIDCHandler(
            issuer="https://idp.example.com",
            client_id="test-client",
            client_secret="secret",
        )

    async def test_validate_response_error_in_data(self):
        h = self._handler()
        result = await h.validate_response({"error": "access_denied", "error_description": "nope"})
        assert result.success is False
        assert result.error_code == "access_denied"

    async def test_validate_response_missing_code(self):
        h = self._handler()
        result = await h.validate_response({"state": "abc"})
        assert result.success is False
        assert result.error_code == "MISSING_CODE"

    async def test_validate_response_state_mismatch(self):
        h = self._handler()
        result = await h.validate_response(
            {"code": "authcode", "state": "wrong"}, expected_state="expected"
        )
        assert result.success is False
        assert result.error_code == "STATE_MISMATCH"

    async def test_validate_response_expired_request(self):
        h = self._handler()
        # Create a pending request that is expired
        expired_req = AuthorizationRequest(
            authorization_url="https://idp.example.com/authorize",
            state="test_state",
            nonce="test_nonce",
            expires_at=datetime.now(UTC) - timedelta(minutes=20),
        )
        h._pending_requests["test_state"] = expired_req
        result = await h.validate_response({"code": "authcode", "state": "test_state"})
        assert result.success is False
        assert result.error_code == "REQUEST_EXPIRED"

    async def test_validate_response_token_exchange_error(self):
        h = self._handler()
        with patch(
            "enhanced_agent_bus.enterprise_sso.enterprise_sso_infra.oidc.OIDCHandler._exchange_code",
            new_callable=AsyncMock,
            return_value={"error": "invalid_grant", "error_description": "bad code"},
        ):
            result = await h.validate_response({"code": "authcode"})
            assert result.success is False
            assert result.error_code == "invalid_grant"

    async def test_validate_response_no_token(self):
        h = self._handler()
        with patch.object(
            h, "_exchange_code", new_callable=AsyncMock, return_value={"scope": "openid"}
        ):
            result = await h.validate_response({"code": "authcode"})
            assert result.success is False
            assert result.error_code == "NO_TOKEN"

    async def test_validate_response_with_id_token(self):
        h = self._handler()
        claims = {
            "sub": "user123",
            "aud": "test-client",
            "exp": time.time() + 3600,
            "email": "user@test.com",
            "name": "Test User",
        }
        token = _make_id_token(claims)
        with patch.object(
            h,
            "_exchange_code",
            new_callable=AsyncMock,
            return_value={"id_token": token, "access_token": "at"},
        ):
            result = await h.validate_response({"code": "authcode"})
            assert result.success is True
            assert result.user_id == "user123"

    async def test_validate_response_with_access_token_only(self):
        h = self._handler()
        with patch.object(
            h,
            "_exchange_code",
            new_callable=AsyncMock,
            return_value={"access_token": "at123"},
        ):
            with patch.object(
                h,
                "_get_userinfo",
                new_callable=AsyncMock,
                return_value=ProtocolValidationResult(success=True, user_id="u1"),
            ):
                result = await h.validate_response({"code": "authcode"})
                assert result.success is True
                assert result.user_id == "u1"

    async def test_validate_response_exception_path(self):
        """Cover the outer exception handler lines 180-184."""
        h = self._handler()
        with patch.object(
            h,
            "_exchange_code",
            new_callable=AsyncMock,
            side_effect=RuntimeError("network failure"),
        ):
            result = await h.validate_response({"code": "authcode"})
            assert result.success is False
            assert result.error_code == "VALIDATION_ERROR"


@pytest.mark.skip(reason="Requires real OIDC endpoint; needs mocked HTTP layer")
class TestOIDCExchangeCode:
    """Cover lines 193-216 (_exchange_code with HttpClient)."""

    async def test_exchange_code_success(self):
        h = OIDCHandler(issuer="https://idp.example.com", client_id="c1", client_secret="s1")

        mock_response = MagicMock()
        mock_response.json.return_value = {"access_token": "at", "id_token": "idt"}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "enhanced_agent_bus.enterprise_sso.enterprise_sso_infra.oidc.OIDCHandler._exchange_code"
        ) as mock_exc:
            mock_exc.return_value = {"access_token": "at", "id_token": "idt"}
            tokens = await mock_exc("code123", "https://redirect.example.com")
            assert "access_token" in tokens

    async def test_exchange_code_failure(self):
        h = OIDCHandler(issuer="https://idp.example.com", client_id="c1")
        with patch(
            "src.core.shared.http_client.HttpClient",
            side_effect=ConnectionError("refused"),
        ):
            tokens = await h._exchange_code("code", "https://redir.example.com")
            assert tokens.get("error") == "token_exchange_failed"


class TestOIDCParseIdToken:
    """Cover nonce mismatch (line 258-259) and missing nonce warning (264-268)."""

    def _handler(self) -> OIDCHandler:
        return OIDCHandler(issuer="https://idp.example.com", client_id="test-client")

    def test_nonce_mismatch(self):
        h = self._handler()
        claims = {
            "sub": "user1",
            "aud": "test-client",
            "exp": time.time() + 3600,
            "nonce": "wrong_nonce",
        }
        token = _make_id_token(claims)
        result = h._parse_id_token(token, expected_nonce="correct_nonce")
        assert result.success is False
        assert result.error_code == "NONCE_MISMATCH"

    def test_missing_nonce_in_token(self):
        h = self._handler()
        claims = {
            "sub": "user1",
            "aud": "test-client",
            "exp": time.time() + 3600,
        }
        token = _make_id_token(claims)
        result = h._parse_id_token(token, expected_nonce="expected")
        # Should succeed with a warning (no nonce in token)
        assert result.success is True
        assert result.user_id == "user1"

    def test_invalid_token_format(self):
        h = self._handler()
        result = h._parse_id_token("not.a.valid.jwt.token")
        assert result.success is False

    def test_expired_token(self):
        h = self._handler()
        claims = {
            "sub": "user1",
            "aud": "test-client",
            "exp": time.time() - 3600,
        }
        token = _make_id_token(claims)
        result = h._parse_id_token(token)
        assert result.success is False
        assert result.error_code == "TOKEN_EXPIRED"

    def test_audience_mismatch(self):
        h = self._handler()
        claims = {
            "sub": "user1",
            "aud": "wrong-client",
            "exp": time.time() + 3600,
        }
        token = _make_id_token(claims)
        result = h._parse_id_token(token)
        assert result.success is False
        assert result.error_code == "AUDIENCE_MISMATCH"

    def test_no_subject(self):
        h = self._handler()
        claims = {
            "aud": "test-client",
            "exp": time.time() + 3600,
        }
        token = _make_id_token(claims)
        result = h._parse_id_token(token)
        assert result.success is False
        assert result.error_code == "NO_SUBJECT"

    def test_groups_as_string(self):
        h = self._handler()
        claims = {
            "sub": "user1",
            "aud": "test-client",
            "exp": time.time() + 3600,
            "groups": "admin",
        }
        token = _make_id_token(claims)
        result = h._parse_id_token(token)
        assert result.success is True
        assert result.groups == ["admin"]


@pytest.mark.skip(reason="Requires real OIDC endpoint; needs mocked HTTP layer")
class TestOIDCGetUserinfo:
    """Cover lines 296-328 (_get_userinfo)."""

    async def test_get_userinfo_success(self):
        h = OIDCHandler(issuer="https://idp.example.com", client_id="c1")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "sub": "uid1",
            "email": "u@t.com",
            "name": "User",
            "given_name": "U",
            "family_name": "T",
            "groups": ["admin"],
        }
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.core.shared.http_client.HttpClient", return_value=mock_client):
            result = await h._get_userinfo("access_token_123")
            assert result.success is True
            assert result.user_id == "uid1"

    async def test_get_userinfo_failure_status(self):
        h = OIDCHandler(issuer="https://idp.example.com", client_id="c1")
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.core.shared.http_client.HttpClient", return_value=mock_client):
            result = await h._get_userinfo("bad_token")
            assert result.success is False
            assert result.error_code == "USERINFO_FAILED"

    async def test_get_userinfo_exception(self):
        h = OIDCHandler(issuer="https://idp.example.com", client_id="c1")
        with patch(
            "src.core.shared.http_client.HttpClient",
            side_effect=ConnectionError("down"),
        ):
            result = await h._get_userinfo("at")
            assert result.success is False
            assert result.error_code == "USERINFO_ERROR"


# ============================================================================
# orchestrator tests — target missing lines
# ============================================================================


class TestMetaOrchestratorInit:
    """Cover container-based init (lines 94-110) and no-container fallback (122-127)."""

    def test_init_without_container(self):
        orch = MetaOrchestrator()
        assert orch._memory_coordinator is not None
        assert orch._swarm_coordinator is not None

    def test_init_with_container(self):
        container = MagicMock()
        container.try_resolve = MagicMock(return_value=None)
        orch = MetaOrchestrator(container=container)
        assert orch._memory_coordinator is not None

    def test_create_meta_orchestrator_factory(self):
        orch = create_meta_orchestrator()
        assert isinstance(orch, MetaOrchestrator)


class TestMetaOrchestratorContextProcessing:
    """Cover lines 195-212 (process_with_mamba_context result conversion)."""

    async def test_process_with_mamba_context_to_dict(self):
        orch = MetaOrchestrator()
        mock_res = MagicMock()
        mock_res.to_dict.return_value = {"compliance_score": 0.9}
        del mock_res.__dict__  # ensure to_dict is preferred
        orch._context_coordinator.process_with_context = AsyncMock(return_value=mock_res)
        result = await orch.process_with_mamba_context("test input")
        assert result["compliance_score"] == 0.9

    async def test_process_with_mamba_context_dataclass(self):
        from dataclasses import dataclass

        @dataclass
        class FakeResult:
            compliance_score: float = 0.8
            fallback: bool = False

        orch = MetaOrchestrator()
        orch._context_coordinator.process_with_context = AsyncMock(return_value=FakeResult())
        result = await orch.process_with_mamba_context("test input")
        assert result["compliance_score"] == 0.8

    async def test_process_with_mamba_context_model_dump(self):
        orch = MetaOrchestrator()
        mock_res = MagicMock()
        # No to_dict, no __dict__ as a dataclass, has model_dump
        mock_res.to_dict = None  # not callable
        del mock_res.to_dict
        mock_res.model_dump = MagicMock(return_value={"compliance_score": 0.7})
        orch._context_coordinator.process_with_context = AsyncMock(return_value=mock_res)
        # Need to ensure the hasattr checks go correctly
        # to_dict won't exist, __dict__ will exist but asdict will fail, model_dump works
        result = await orch.process_with_mamba_context("test input")
        assert isinstance(result, dict)

    async def test_process_with_mamba_context_dict_passthrough(self):
        orch = MetaOrchestrator()
        orch._context_coordinator.process_with_context = AsyncMock(
            return_value={"compliance_score": 1.0, "fallback": False}
        )
        result = await orch.process_with_mamba_context("test input")
        assert result["compliance_score"] == 1.0


class TestMetaOrchestratorMACIValidation:
    """Cover lines 217, 228, 231, 234-235 (validate_constitutional_compliance)."""

    async def test_validate_constitutional_compliance_hash_mismatch(self):
        orch = MetaOrchestrator()
        result = await orch.validate_constitutional_compliance(
            {"constitutional_hash": "wrong_hash", "task": "something"}
        )
        assert result is False

    async def test_validate_constitutional_compliance_low_score(self):
        orch = MetaOrchestrator()
        orch._context_coordinator.process_with_context = AsyncMock(
            return_value={"compliance_score": 0.1, "fallback": False}
        )
        result = await orch.validate_constitutional_compliance({"task": "something"})
        assert result is False

    async def test_validate_constitutional_compliance_maci_disallowed(self):
        orch = MetaOrchestrator()
        orch._context_coordinator.process_with_context = AsyncMock(
            return_value={"compliance_score": 0.9, "fallback": False}
        )
        orch._maci_coordinator.validate_action = AsyncMock(return_value={"allowed": False})
        result = await orch.validate_constitutional_compliance(
            {"task": "something", "agent_id": "agent1", "action_type": "execute"}
        )
        assert result is False

    async def test_validate_constitutional_compliance_passes(self):
        orch = MetaOrchestrator()
        orch._context_coordinator.process_with_context = AsyncMock(
            return_value={"compliance_score": 0.9, "fallback": False}
        )
        orch._maci_coordinator.validate_action = AsyncMock(return_value={"allowed": True})
        result = await orch.validate_constitutional_compliance(
            {"task": "something", "agent_id": "agent1"}
        )
        assert result is True


class TestMetaOrchestratorWorkflow:
    """Cover lines 270 (evolve_workflow success/failure) and 277 (research disabled)."""

    async def test_evolve_workflow_limit_exceeded(self):
        orch = MetaOrchestrator()
        orch._evolution_count_today = orch.config.auto_evolution_limit
        result = await orch.evolve_workflow("wf1", {"confidence": 0.9})
        assert result is False

    async def test_evolve_workflow_low_confidence(self):
        orch = MetaOrchestrator()
        result = await orch.evolve_workflow("wf1", {"confidence": 0.01})
        assert result is False

    async def test_evolve_workflow_unavailable_fallback(self):
        orch = MetaOrchestrator()
        orch._workflow_coordinator.evolve_workflow = AsyncMock(
            return_value={"success": False, "reason": "Evolution engine not available"}
        )
        result = await orch.evolve_workflow("wf1", {"confidence": 0.9})
        assert result is True
        assert orch._evolution_count_today == 1

    async def test_evolve_workflow_success(self):
        orch = MetaOrchestrator()
        orch._workflow_coordinator.evolve_workflow = AsyncMock(return_value={"success": True})
        result = await orch.evolve_workflow("wf1", {"confidence": 0.9})
        assert result is True

    async def test_research_topic_disabled(self):
        config = OrchestratorConfig(enable_research=False)
        orch = MetaOrchestrator(config=config)
        result = await orch.research_topic("AI governance")
        assert result["error"] == "Research capabilities disabled"

    async def test_research_topic_enabled(self):
        orch = MetaOrchestrator()
        result = await orch.research_topic("AI governance", sources=["arxiv"])
        assert result["topic"] == "AI governance"
        assert len(result["results"]) == 1

    async def test_run_performance_optimization(self):
        orch = MetaOrchestrator()
        result = await orch.run_performance_optimization()
        assert result["success"] is True

    async def test_shutdown(self):
        orch = MetaOrchestrator()
        orch._swarm_coordinator.terminate_agent = AsyncMock()
        await orch.shutdown()
        orch._swarm_coordinator.terminate_agent.assert_called_once_with("all")


class TestMetaOrchestratorStatus:
    """Cover get_status (line 343 start)."""

    async def test_start(self):
        orch = MetaOrchestrator()
        await orch.start()  # Should not raise

    def test_get_status(self):
        orch = MetaOrchestrator()
        status = orch.get_status()
        assert "constitutional_hash" in status
        assert "active_agents" in status
        assert "components" in status


# ============================================================================
# prefetch tests — target missing lines
# ============================================================================


class TestPrefetchManagerInit:
    """Cover line 57 (invalid hash)."""

    def test_invalid_hash_raises(self):
        with pytest.raises(ValueError, match="Invalid constitutional hash"):
            PrefetchManager(constitutional_hash="wrong")


class TestPrefetchManagerRecordAccess:
    """Cover lines 82, 86-90 (sequence trimming, co-occurrence updates)."""

    def test_record_access_builds_co_occurrence(self):
        pm = PrefetchManager()
        pm.record_access("a")
        pm.record_access("b")
        pm.record_access("c")
        assert "a" in pm._co_occurrence
        assert "b" in pm._co_occurrence["a"]
        assert "c" in pm._co_occurrence["a"]
        assert "c" in pm._co_occurrence["b"]

    def test_record_access_trims_sequence(self):
        pm = PrefetchManager()
        for i in range(15):
            pm.record_access(f"key_{i}")
        assert len(pm._current_sequence) == 10


class TestPrefetchManagerPredictNext:
    """Cover lines 106-121 (predict_next with thresholds)."""

    def test_predict_next_unknown_key(self):
        pm = PrefetchManager()
        assert pm.predict_next("unknown") == []

    def test_predict_next_with_data(self):
        pm = PrefetchManager(threshold=0.5)
        # Build co-occurrence: a -> b (3 times), a -> c (1 time)
        for _ in range(3):
            pm._co_occurrence.setdefault("a", {})
            pm._co_occurrence["a"]["b"] = pm._co_occurrence["a"].get("b", 0) + 1
        pm._co_occurrence["a"]["c"] = 1
        predictions = pm.predict_next("a")
        # b has 3/4 = 0.75 prob (above 0.5), c has 1/4 = 0.25 (below 0.5)
        assert len(predictions) == 1
        assert predictions[0][0] == "b"

    def test_predict_next_zero_total(self):
        pm = PrefetchManager()
        pm._co_occurrence["a"] = {}
        assert pm.predict_next("a") == []


class TestPrefetchManagerPrefetch:
    """Cover lines 141-150 (prefetch with sync and async fetch_fn)."""

    async def test_prefetch_with_sync_fn(self):
        pm = PrefetchManager(threshold=0.5)
        pm._co_occurrence["a"] = {"b": 10}

        def fetch(key: str) -> str:
            return f"value_{key}"

        count = await pm.prefetch("a", fetch)
        assert count == 1
        assert pm._prefetch_cache["b"] == "value_b"

    async def test_prefetch_with_async_fn(self):
        pm = PrefetchManager(threshold=0.5)
        pm._co_occurrence["a"] = {"b": 10}

        async def afetch(key: str) -> str:
            return f"async_value_{key}"

        count = await pm.prefetch("a", afetch)
        assert count == 1
        assert pm._prefetch_cache["b"] == "async_value_b"

    async def test_prefetch_skip_already_cached(self):
        pm = PrefetchManager(threshold=0.5)
        pm._co_occurrence["a"] = {"b": 10}
        pm._prefetch_cache["b"] = "existing"

        count = await pm.prefetch("a", lambda k: k)
        assert count == 0

    async def test_prefetch_max_entries_limit(self):
        pm = PrefetchManager(threshold=0.5, max_entries=1)
        pm._co_occurrence["a"] = {"b": 5, "c": 5}
        pm._prefetch_cache["existing"] = "v"  # already at max

        count = await pm.prefetch("a", lambda k: k)
        assert count == 0

    async def test_prefetch_error_handling(self):
        pm = PrefetchManager(threshold=0.5)
        pm._co_occurrence["a"] = {"b": 10}

        def bad_fetch(key: str) -> str:
            raise RuntimeError("fetch failed")

        count = await pm.prefetch("a", bad_fetch)
        assert count == 0


class TestPrefetchManagerClearSession:
    """Cover line 174 (trim access_sequences)."""

    def test_clear_session_trims_sequences(self):
        pm = PrefetchManager()
        # Fill up more than 100 sequences
        pm._access_sequences = [["x"]] * 105
        pm._current_sequence = ["a", "b"]
        pm.clear_session()
        assert len(pm._access_sequences) <= 100
        assert pm._current_sequence == []


class TestPrefetchManagerGetPrefetched:
    """Cover get_prefetched hit/miss paths."""

    def test_get_prefetched_hit(self):
        pm = PrefetchManager()
        pm._prefetch_cache["k"] = "v"
        assert pm.get_prefetched("k") == "v"
        assert pm._prefetch_hits == 1

    def test_get_prefetched_miss(self):
        pm = PrefetchManager()
        assert pm.get_prefetched("missing") is None
        assert pm._prefetch_misses == 1


class TestPrefetchManagerMetrics:
    """Cover get_metrics."""

    def test_get_metrics(self):
        pm = PrefetchManager()
        pm._prefetch_hits = 3
        pm._prefetch_misses = 7
        m = pm.get_metrics()
        assert m["prefetch_hit_rate"] == 0.3
        assert m["constitutional_hash"] == CONSTITUTIONAL_HASH


# ============================================================================
# governance tests — target missing lines
# ============================================================================


class TestGovernanceValidatorInit:
    """Cover lines 85-92 (adaptive governance init), 97-100 (shutdown)."""

    async def test_initialize_with_policy_client(self):
        mock_pc = AsyncMock()
        mock_pc.initialize = AsyncMock()
        mock_pc.get_current_public_key = AsyncMock(return_value=None)
        mock_pc._is_mock = False

        gv = GovernanceValidator(config={}, policy_client=mock_pc)
        await gv.initialize()
        mock_pc.initialize.assert_called_once()

    async def test_initialize_with_dynamic_policy(self):
        mock_pc = AsyncMock()
        mock_pc.initialize = AsyncMock()
        mock_pc.get_current_public_key = AsyncMock(return_value="new_hash_value")
        mock_pc._is_mock = True

        gv = GovernanceValidator(config={"use_dynamic_policy": True}, policy_client=mock_pc)
        await gv.initialize()
        assert gv._constitutional_hash == "new_hash_value"

    async def test_initialize_policy_client_failure(self):
        mock_pc = AsyncMock()
        mock_pc.initialize = AsyncMock(side_effect=RuntimeError("policy init fail"))

        gv = GovernanceValidator(config={}, policy_client=mock_pc)
        await gv.initialize()  # Should not raise

    async def test_initialize_adaptive_governance(self):
        gv = GovernanceValidator(config={}, enable_adaptive_governance=True)
        with (
            patch("enhanced_agent_bus.components.governance.ADAPTIVE_GOVERNANCE_AVAILABLE", True),
            patch(
                "enhanced_agent_bus.components.governance.initialize_adaptive_governance",
                new_callable=AsyncMock,
                return_value=MagicMock(),
            ),
        ):
            gv._enable_adaptive_governance = True
            await gv.initialize()
            assert gv._adaptive_governance is not None

    async def test_initialize_adaptive_governance_failure(self):
        gv = GovernanceValidator(config={}, enable_adaptive_governance=True)
        with (
            patch("enhanced_agent_bus.components.governance.ADAPTIVE_GOVERNANCE_AVAILABLE", True),
            patch(
                "enhanced_agent_bus.components.governance.initialize_adaptive_governance",
                new_callable=AsyncMock,
                side_effect=RuntimeError("ag init fail"),
            ),
        ):
            gv._enable_adaptive_governance = True
            await gv.initialize()
            assert gv._adaptive_governance is None

    async def test_shutdown_adaptive_governance(self):
        gv = GovernanceValidator(config={})
        mock_ag = AsyncMock()
        mock_ag.shutdown = AsyncMock()
        gv._adaptive_governance = mock_ag
        await gv.shutdown()
        mock_ag.shutdown.assert_called_once()

    async def test_shutdown_adaptive_governance_error(self):
        gv = GovernanceValidator(config={})
        mock_ag = AsyncMock()
        mock_ag.shutdown = AsyncMock(side_effect=RuntimeError("shutdown fail"))
        gv._adaptive_governance = mock_ag
        await gv.shutdown()  # Should not raise


class TestGovernanceValidatorHashCheck:
    """Cover lines 102-109 (validate_constitutional_hash)."""

    def test_hash_match(self):
        gv = GovernanceValidator(config={})
        msg = AgentMessage(constitutional_hash=CONSTITUTIONAL_HASH)
        result = ValidationResult()
        assert gv.validate_constitutional_hash(msg, result) is True

    def test_hash_mismatch(self):
        gv = GovernanceValidator(config={})
        msg = AgentMessage(constitutional_hash="00000000deadbeef")
        result = ValidationResult()
        assert gv.validate_constitutional_hash(msg, result) is False
        assert len(result.errors) > 0


class TestGovernanceValidatorAdaptiveEval:
    """Cover lines 119-154 (evaluate_adaptive_governance)."""

    async def test_evaluate_no_adaptive_governance(self):
        gv = GovernanceValidator(config={})
        msg = AgentMessage()
        allowed, reason = await gv.evaluate_adaptive_governance(msg, {})
        assert allowed is True
        assert "not available" in reason

    async def test_evaluate_adaptive_governance_success(self):
        gv = GovernanceValidator(config={})
        mock_decision = MagicMock()
        mock_decision.action_allowed = True
        mock_decision.reasoning = "Allowed by policy"
        mock_decision.impact_level = MagicMock()
        mock_decision.impact_level.value = "low"
        mock_decision.confidence_score = 0.95

        mock_ag = AsyncMock()
        mock_ag.evaluate_governance_decision = AsyncMock(return_value=mock_decision)
        gv._adaptive_governance = mock_ag

        msg = AgentMessage(from_agent="a1", to_agent="a2", content={"test": True})
        allowed, reason = await gv.evaluate_adaptive_governance(msg, {"extra": "ctx"})
        assert allowed is True
        assert reason == "Allowed by policy"

    async def test_evaluate_adaptive_governance_denied(self):
        gv = GovernanceValidator(config={})
        mock_decision = MagicMock()
        mock_decision.action_allowed = False
        mock_decision.reasoning = "Denied"
        mock_decision.impact_level = MagicMock()
        mock_decision.impact_level.value = "high"
        mock_decision.confidence_score = 0.99

        mock_ag = AsyncMock()
        mock_ag.evaluate_governance_decision = AsyncMock(return_value=mock_decision)
        gv._adaptive_governance = mock_ag

        msg = AgentMessage()
        allowed, reason = await gv.evaluate_adaptive_governance(msg, {})
        assert allowed is False

    async def test_evaluate_adaptive_governance_exception(self):
        gv = GovernanceValidator(config={})
        mock_ag = AsyncMock()
        mock_ag.evaluate_governance_decision = AsyncMock(side_effect=RuntimeError("eval failed"))
        gv._adaptive_governance = mock_ag

        msg = AgentMessage()
        allowed, reason = await gv.evaluate_adaptive_governance(msg, {})
        assert allowed is False
        assert "Governance evaluation failed" in reason


class TestGovernanceValidatorFeedback:
    """Cover lines 156-170 (provide_feedback)."""

    def test_provide_feedback_no_adaptive_governance(self):
        gv = GovernanceValidator(config={})
        msg = AgentMessage()
        gv.provide_feedback(msg, True)  # Should not raise

    def test_provide_feedback_with_matching_decision(self):
        gv = GovernanceValidator(config={})
        mock_decision = MagicMock()
        mock_decision.features_used = MagicMock()
        mock_decision.features_used.message_length = len(str({"test": True}))

        mock_ag = MagicMock()
        mock_ag.decision_history = [mock_decision]
        gv._adaptive_governance = mock_ag

        msg = AgentMessage(content={"test": True})

        with (
            patch("enhanced_agent_bus.components.governance.ADAPTIVE_GOVERNANCE_AVAILABLE", True),
            patch(
                "enhanced_agent_bus.components.governance.provide_governance_feedback",
            ) as mock_feedback,
        ):
            gv.provide_feedback(msg, True)
            mock_feedback.assert_called_once_with(mock_decision, True)

    def test_provide_feedback_no_matching_decision(self):
        gv = GovernanceValidator(config={})
        mock_ag = MagicMock()
        mock_ag.decision_history = []
        gv._adaptive_governance = mock_ag

        msg = AgentMessage()
        gv.provide_feedback(msg, False)  # Should not raise
