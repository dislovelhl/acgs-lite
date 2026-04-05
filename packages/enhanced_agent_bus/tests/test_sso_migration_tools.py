"""Tests for enterprise_sso/migration_tools.py — DecisionLogImporter, ShadowModeExecutor, TrafficRouter."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from enhanced_agent_bus.enterprise_sso.migration_tools import (
    AgreementStatus,
    DecisionLogImporter,
    DecisionSource,
    ImportedDecision,
    ImportResult,
    ImportStatus,
    SchemaMapping,
    ShadowDecisionResult,
    ShadowModeExecutor,
    ShadowModeMetrics,
    ShadowModeState,
    TrafficConfig,
    TrafficRouter,
)


# ---------------------------------------------------------------------------
# DecisionLogImporter
# ---------------------------------------------------------------------------
class TestDecisionLogImporter:
    """Unit tests for CSV import, duplicate detection, and schema mapping."""

    @pytest.fixture()
    def importer(self) -> DecisionLogImporter:
        return DecisionLogImporter()

    @pytest.fixture()
    def basic_mappings(self) -> list[SchemaMapping]:
        return [
            SchemaMapping(source_column="id", target_field="original_id"),
            SchemaMapping(source_column="action", target_field="action"),
            SchemaMapping(source_column="resource", target_field="resource"),
            SchemaMapping(source_column="decision", target_field="decision"),
        ]

    @pytest.fixture()
    def csv_content(self) -> str:
        return "id,action,resource,decision\n1,read,doc,allow\n2,write,doc,deny\n"

    # -- happy path --

    async def test_import_csv_happy_path(self, importer, basic_mappings, csv_content):
        result = await importer.import_csv(csv_content, basic_mappings, "tenant-a")

        assert result.status == ImportStatus.COMPLETED
        assert result.total_rows == 2
        assert result.imported_count == 2
        assert result.duplicate_count == 0
        assert result.error_count == 0
        assert result.start_time is not None
        assert result.end_time is not None

    async def test_import_csv_returns_correct_import_id(
        self, importer, basic_mappings, csv_content
    ):
        result = await importer.import_csv(csv_content, basic_mappings, "t")
        assert result.import_id is not None
        assert len(result.import_id) > 0

    async def test_get_import_result(self, importer, basic_mappings, csv_content):
        result = await importer.import_csv(csv_content, basic_mappings, "t")
        fetched = importer.get_import_result(result.import_id)
        assert fetched is not None
        assert fetched.import_id == result.import_id

    async def test_get_import_result_missing(self, importer):
        assert importer.get_import_result("nonexistent") is None

    async def test_get_imported_decisions(self, importer, basic_mappings, csv_content):
        result = await importer.import_csv(csv_content, basic_mappings, "t")
        decisions = importer.get_imported_decisions(result.import_id)
        assert len(decisions) == 2
        assert all(isinstance(d, ImportedDecision) for d in decisions)

    # -- duplicate detection --

    async def test_duplicate_detection(self, importer):
        """Duplicate detection requires matching original_id, timestamp, action, resource.
        We supply an explicit timestamp transform so both rows produce the same datetime."""
        from datetime import datetime, timezone

        fixed_ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
        mappings = [
            SchemaMapping(source_column="id", target_field="original_id"),
            SchemaMapping(source_column="action", target_field="action"),
            SchemaMapping(source_column="resource", target_field="resource"),
            SchemaMapping(source_column="decision", target_field="decision"),
            SchemaMapping(
                source_column="ts", target_field="timestamp", transform=lambda _v: fixed_ts
            ),
        ]
        csv = "id,action,resource,decision,ts\n1,read,doc,allow,x\n1,read,doc,allow,x\n"
        result = await importer.import_csv(csv, mappings, "t")

        assert result.imported_count == 1
        assert result.duplicate_count == 1
        assert result.total_rows == 2

    async def test_duplicate_detection_disabled(self, importer, basic_mappings):
        csv = "id,action,resource,decision\n1,read,doc,allow\n1,read,doc,allow\n"
        result = await importer.import_csv(csv, basic_mappings, "t", detect_duplicates=False)

        assert result.imported_count == 2
        assert result.duplicate_count == 0

    # -- required field missing --

    async def test_required_field_missing_records_error(self, importer):
        mappings = [
            SchemaMapping(source_column="action", target_field="action", required=True),
        ]
        # DictReader needs at least one non-empty data row; empty value triggers required check
        csv = "action,other\n,val\n"
        result = await importer.import_csv(csv, mappings, "t")

        assert result.error_count == 1
        assert result.imported_count == 0
        assert len(result.errors) == 1

    # -- transform function --

    async def test_transform_applied(self, importer):
        mappings = [
            SchemaMapping(
                source_column="action",
                target_field="action",
                transform=str.upper,
            ),
            SchemaMapping(source_column="resource", target_field="resource"),
            SchemaMapping(source_column="decision", target_field="decision"),
        ]
        csv = "action,resource,decision\nread,doc,allow\n"
        result = await importer.import_csv(csv, mappings, "t")

        assert result.imported_count == 1
        decisions = importer.get_imported_decisions(result.import_id)
        assert decisions[0].action == "READ"

    # -- default value --

    async def test_default_value_used(self, importer):
        mappings = [
            SchemaMapping(source_column="missing_col", target_field="actor", default="system"),
        ]
        csv = "other\nval\n"
        result = await importer.import_csv(csv, mappings, "t")
        assert result.imported_count == 1

    # -- empty CSV --

    async def test_empty_csv(self, importer, basic_mappings):
        csv = "id,action,resource,decision\n"
        result = await importer.import_csv(csv, basic_mappings, "t")
        assert result.status == ImportStatus.COMPLETED
        assert result.total_rows == 0
        assert result.imported_count == 0


# ---------------------------------------------------------------------------
# ShadowModeExecutor
# ---------------------------------------------------------------------------
class TestShadowModeExecutor:
    """Unit tests for shadow mode execution and metrics."""

    @pytest.fixture()
    def matching_executor(self) -> ShadowModeExecutor:
        async def legacy(action, resource, context):
            return "allow"

        async def acgs2(action, resource, context):
            return "allow"

        return ShadowModeExecutor(legacy, acgs2)

    @pytest.fixture()
    def mismatched_executor(self) -> ShadowModeExecutor:
        async def legacy(action, resource, context):
            return "allow"

        async def acgs2(action, resource, context):
            return "deny"

        return ShadowModeExecutor(legacy, acgs2)

    # -- execute_shadow --

    async def test_execute_shadow_matching(self, matching_executor):
        result = await matching_executor.execute_shadow("r1", "read", "doc", {})
        assert result.agreement == AgreementStatus.MATCH
        assert result.legacy_decision == "allow"
        assert result.acgs2_decision == "allow"
        assert result.legacy_latency_ms is not None
        assert result.acgs2_latency_ms is not None

    async def test_execute_shadow_mismatch(self, mismatched_executor):
        result = await mismatched_executor.execute_shadow("r1", "read", "doc", {})
        assert result.agreement == AgreementStatus.MISMATCH

    async def test_execute_shadow_legacy_error(self):
        async def legacy_err(a, r, c):
            raise RuntimeError("boom")

        async def acgs2_ok(a, r, c):
            return "allow"

        executor = ShadowModeExecutor(legacy_err, acgs2_ok)
        result = await executor.execute_shadow("r1", "read", "doc", {})
        assert result.agreement == AgreementStatus.LEGACY_ERROR

    async def test_execute_shadow_acgs2_error(self):
        async def legacy_ok(a, r, c):
            return "allow"

        async def acgs2_err(a, r, c):
            raise ValueError("nope")

        executor = ShadowModeExecutor(legacy_ok, acgs2_err)
        result = await executor.execute_shadow("r1", "read", "doc", {})
        assert result.agreement == AgreementStatus.ACGS2_ERROR

    async def test_execute_shadow_sync_evaluators(self):
        """Sync evaluators should also work."""

        def legacy_sync(a, r, c):
            return "deny"

        def acgs2_sync(a, r, c):
            return "deny"

        executor = ShadowModeExecutor(legacy_sync, acgs2_sync)
        result = await executor.execute_shadow("r1", "read", "doc", {})
        assert result.agreement == AgreementStatus.MATCH
        assert result.legacy_decision == "deny"

    # -- get_metrics --

    async def test_get_metrics_empty(self, matching_executor):
        metrics = matching_executor.get_metrics()
        assert metrics.total_requests == 0
        assert metrics.agreement_rate == 0.0

    async def test_get_metrics_after_executions(self, matching_executor):
        await matching_executor.execute_shadow("r1", "read", "doc", {})
        await matching_executor.execute_shadow("r2", "write", "doc", {})

        metrics = matching_executor.get_metrics()
        assert metrics.total_requests == 2
        assert metrics.matches == 2
        assert metrics.agreement_rate == 100.0
        assert metrics.average_legacy_latency_ms >= 0

    async def test_get_metrics_with_mismatches(self, mismatched_executor):
        await mismatched_executor.execute_shadow("r1", "read", "doc", {})
        metrics = mismatched_executor.get_metrics()
        assert metrics.mismatches == 1
        assert metrics.agreement_rate == 0.0

    # -- state management --

    def test_default_state_disabled(self, matching_executor):
        assert matching_executor.get_state() == ShadowModeState.DISABLED

    def test_set_get_state(self, matching_executor):
        matching_executor.set_state(ShadowModeState.ACTIVE)
        assert matching_executor.get_state() == ShadowModeState.ACTIVE


# ---------------------------------------------------------------------------
# TrafficRouter
# ---------------------------------------------------------------------------
class TestTrafficRouter:
    """Unit tests for traffic routing, auto-rollback, and error tracking."""

    @pytest.fixture()
    def router(self) -> TrafficRouter:
        return TrafficRouter()

    def test_configure_tenant(self, router):
        config = router.configure_tenant("t1", acgs2_percentage=50.0)
        assert config.tenant_id == "t1"
        assert config.acgs2_percentage == 50.0

    def test_configure_tenant_clamps_percentage(self, router):
        config = router.configure_tenant("t1", acgs2_percentage=200.0)
        assert config.acgs2_percentage == 100.0

        config2 = router.configure_tenant("t2", acgs2_percentage=-10.0)
        assert config2.acgs2_percentage == 0.0

    def test_route_request_defaults_to_legacy(self, router):
        assert router.route_request("unknown", "req-1") == "legacy"

    def test_route_request_at_100_percent(self, router):
        router.configure_tenant("t1", acgs2_percentage=100.0)
        # All requests should go to acgs2
        results = {router.route_request("t1", f"req-{i}") for i in range(100)}
        assert results == {"acgs2"}

    def test_route_request_at_0_percent(self, router):
        router.configure_tenant("t1", acgs2_percentage=0.0)
        results = {router.route_request("t1", f"req-{i}") for i in range(100)}
        assert results == {"legacy"}

    def test_record_error_and_get_error_rate(self, router):
        router.configure_tenant("t1", acgs2_percentage=50.0, min_samples=1000)
        # Simulate some requests
        for i in range(10):
            router.route_request("t1", f"req-{i}")
        router.record_error("t1", "acgs2")

        rate = router.get_error_rate("t1")
        assert rate > 0

    def test_get_error_rate_zero_requests(self, router):
        assert router.get_error_rate("unknown") == 0.0

    def test_auto_rollback_on_high_error_rate(self, router):
        router.configure_tenant("t1", acgs2_percentage=50.0, error_threshold=5.0, min_samples=10)
        # Generate enough requests and errors
        for i in range(20):
            router.route_request("t1", f"req-{i}")
        for _ in range(5):
            router.record_error("t1", "acgs2")

        # Next route should trigger rollback
        result = router.route_request("t1", "req-trigger")
        assert result == "legacy"
        assert router.get_config("t1").acgs2_percentage == 0.0

    def test_no_rollback_below_min_samples(self, router):
        router.configure_tenant("t1", acgs2_percentage=50.0, error_threshold=1.0, min_samples=1000)
        router.route_request("t1", "req-1")
        router.record_error("t1", "acgs2")
        # Under min_samples, no rollback
        config = router.get_config("t1")
        assert config.acgs2_percentage == 50.0

    def test_get_config_returns_none_for_unknown(self, router):
        assert router.get_config("nonexistent") is None

    def test_update_percentage_existing(self, router):
        router.configure_tenant("t1", acgs2_percentage=10.0)
        updated = router.update_percentage("t1", 75.0)
        assert updated.acgs2_percentage == 75.0

    def test_update_percentage_new_tenant(self, router):
        config = router.update_percentage("new_tenant", 30.0)
        assert config.tenant_id == "new_tenant"
        assert config.acgs2_percentage == 30.0

    def test_update_percentage_clamps(self, router):
        router.configure_tenant("t1", acgs2_percentage=10.0)
        updated = router.update_percentage("t1", 999.0)
        assert updated.acgs2_percentage == 100.0

    def test_record_error_only_tracks_acgs2(self, router):
        router.configure_tenant("t1", acgs2_percentage=50.0)
        router.route_request("t1", "r1")
        router.record_error("t1", "legacy")
        assert router.get_error_rate("t1") == 0.0


# ---------------------------------------------------------------------------
# Enum / dataclass coverage
# ---------------------------------------------------------------------------
class TestEnumsAndDataclasses:
    def test_import_status_values(self):
        assert ImportStatus.PENDING.value == "pending"
        assert ImportStatus.COMPLETED.value == "completed"

    def test_decision_source_values(self):
        assert DecisionSource.LEGACY.value == "legacy"

    def test_shadow_mode_state_values(self):
        assert ShadowModeState.DISABLED.value == "disabled"
        assert ShadowModeState.ACTIVE.value == "active"

    def test_agreement_status_values(self):
        assert AgreementStatus.MATCH.value == "match"
        assert AgreementStatus.TIMEOUT.value == "timeout"

    def test_shadow_decision_result_defaults(self):
        r = ShadowDecisionResult(request_id="r1")
        assert r.agreement == AgreementStatus.MATCH
        assert r.legacy_decision is None

    def test_traffic_config_defaults(self):
        c = TrafficConfig(tenant_id="t")
        assert c.acgs2_percentage == 0.0
        assert c.auto_rollback is True
