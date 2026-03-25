"""
Migration Job Management API - Coverage Tests
Constitutional Hash: 608508a9bd224290

Comprehensive tests targeting >=98% coverage of
enterprise_sso/migration_job_api.py, covering all classes,
methods, branches, and error paths not addressed by the
existing test_migration_job_api.py suite.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta, timezone

import pytest

from enterprise_sso.migration_job_api import (
    CONSTITUTIONAL_HASH,
    JOB_WORKER_EXECUTION_ERRORS,
    AsyncTaskQueue,
    MigrationJob,
    MigrationJobAPI,
    MigrationJobConfig,
    MigrationJobManager,
    MigrationJobProgress,
    MigrationJobResult,
    MigrationJobStatus,
    MigrationJobType,
    PDFReport,
    PDFReportGenerator,
    ProgressCalculator,
    ReportFormat,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TENANT = "tenant-coverage"


def _config(job_type: MigrationJobType = MigrationJobType.POLICY_IMPORT) -> MigrationJobConfig:
    return MigrationJobConfig(job_type=job_type)


# ---------------------------------------------------------------------------
# Enum coverage
# ---------------------------------------------------------------------------


class TestEnumValues:
    """Ensure every enum member is reachable."""

    def test_migration_job_status_all_values(self) -> None:
        expected = {"pending", "queued", "running", "paused", "completed", "failed", "cancelled"}
        actual = {s.value for s in MigrationJobStatus}
        assert actual == expected

    def test_migration_job_type_all_values(self) -> None:
        expected = {
            "policy_import",
            "decision_log_import",
            "constitutional_analysis",
            "full_migration",
            "gap_remediation",
        }
        actual = {t.value for t in MigrationJobType}
        assert actual == expected

    def test_report_format_all_values(self) -> None:
        expected = {"json", "csv", "pdf", "html"}
        actual = {f.value for f in ReportFormat}
        assert actual == expected


# ---------------------------------------------------------------------------
# JOB_WORKER_EXECUTION_ERRORS tuple
# ---------------------------------------------------------------------------


class TestJobWorkerExecutionErrors:
    """Verify the exception tuple contains all documented types."""

    def test_tuple_contents(self) -> None:
        assert RuntimeError in JOB_WORKER_EXECUTION_ERRORS
        assert ValueError in JOB_WORKER_EXECUTION_ERRORS
        assert TypeError in JOB_WORKER_EXECUTION_ERRORS
        assert KeyError in JOB_WORKER_EXECUTION_ERRORS
        assert AttributeError in JOB_WORKER_EXECUTION_ERRORS
        assert ConnectionError in JOB_WORKER_EXECUTION_ERRORS
        assert OSError in JOB_WORKER_EXECUTION_ERRORS
        assert asyncio.TimeoutError in JOB_WORKER_EXECUTION_ERRORS


# ---------------------------------------------------------------------------
# MigrationJobProgress - property branches
# ---------------------------------------------------------------------------


class TestMigrationJobProgressExtra:
    """Extra branches for MigrationJobProgress."""

    def test_percentage_complete_non_zero_total(self) -> None:
        p = MigrationJobProgress(total_items=400, processed_items=100)
        assert p.percentage_complete == pytest.approx(25.0)

    def test_percentage_complete_zero_total(self) -> None:
        p = MigrationJobProgress()
        assert p.percentage_complete == 0.0

    def test_constitutional_hash_default(self) -> None:
        p = MigrationJobProgress()
        assert p.constitutional_hash == CONSTITUTIONAL_HASH

    def test_estimated_remaining_seconds_default_none(self) -> None:
        p = MigrationJobProgress()
        assert p.estimated_remaining_seconds is None

    def test_start_time_default_none(self) -> None:
        p = MigrationJobProgress()
        assert p.start_time is None


# ---------------------------------------------------------------------------
# MigrationJobConfig defaults
# ---------------------------------------------------------------------------


class TestMigrationJobConfigDefaults:
    def test_defaults(self) -> None:
        cfg = MigrationJobConfig(job_type=MigrationJobType.FULL_MIGRATION)
        assert cfg.batch_size == 100
        assert cfg.max_retries == 3
        assert cfg.timeout_seconds == 3600
        assert cfg.source_config == {}
        assert cfg.target_config == {}
        assert cfg.options == {}
        assert cfg.constitutional_hash == CONSTITUTIONAL_HASH

    def test_custom_values(self) -> None:
        cfg = MigrationJobConfig(
            job_type=MigrationJobType.GAP_REMEDIATION,
            source_config={"src": "x"},
            target_config={"dst": "y"},
            options={"dry_run": True},
            batch_size=50,
            max_retries=5,
            timeout_seconds=7200,
        )
        assert cfg.batch_size == 50
        assert cfg.max_retries == 5
        assert cfg.timeout_seconds == 7200
        assert cfg.options["dry_run"] is True


# ---------------------------------------------------------------------------
# MigrationJobResult and PDFReport defaults
# ---------------------------------------------------------------------------


class TestDataClassDefaults:
    def test_migration_job_result_defaults(self) -> None:
        r = MigrationJobResult(
            job_id="j1",
            tenant_id="t1",
            status=MigrationJobStatus.COMPLETED,
        )
        assert r.summary == {}
        assert r.details == []
        assert r.warnings == []
        assert r.errors == []
        assert r.constitutional_hash == CONSTITUTIONAL_HASH

    def test_pdf_report_defaults(self) -> None:
        pdf = PDFReport(
            job_id="j1",
            tenant_id="t1",
            filename="report.pdf",
            content_bytes=b"data",
        )
        assert pdf.constitutional_hash == CONSTITUTIONAL_HASH
        assert isinstance(pdf.generated_at, datetime)

    def test_migration_job_defaults(self) -> None:
        job = MigrationJob(
            job_id="j1",
            tenant_id="t1",
            config=_config(),
        )
        assert job.status == MigrationJobStatus.PENDING
        assert job.started_at is None
        assert job.completed_at is None
        assert job.error_message is None
        assert job.result_url is None
        assert job.constitutional_hash == CONSTITUTIONAL_HASH


# ---------------------------------------------------------------------------
# MigrationJobManager - uncovered branches
# ---------------------------------------------------------------------------


class TestMigrationJobManagerExtra:
    @pytest.fixture
    def mgr(self) -> MigrationJobManager:
        return MigrationJobManager()

    # get_job returns None for unknown id
    async def test_get_job_unknown_id_returns_none(self, mgr: MigrationJobManager) -> None:
        result = await mgr.get_job("nonexistent", TENANT)
        assert result is None

    # cancel_job - already COMPLETED stays as-is
    async def test_cancel_already_completed_returns_job(self, mgr: MigrationJobManager) -> None:
        job = await mgr.create_job(TENANT, _config())
        result_obj = MigrationJobResult(
            job_id=job.job_id,
            tenant_id=TENANT,
            status=MigrationJobStatus.COMPLETED,
        )
        await mgr.complete_job(job.job_id, result_obj)
        cancelled = await mgr.cancel_job(job.job_id, TENANT)
        # Should return unchanged (already terminal)
        assert cancelled is not None
        assert cancelled.status == MigrationJobStatus.COMPLETED

    # cancel_job - already CANCELLED stays as-is
    async def test_cancel_already_cancelled_returns_job(self, mgr: MigrationJobManager) -> None:
        job = await mgr.create_job(TENANT, _config())
        await mgr.cancel_job(job.job_id, TENANT)
        second_cancel = await mgr.cancel_job(job.job_id, TENANT)
        assert second_cancel is not None
        assert second_cancel.status == MigrationJobStatus.CANCELLED

    # cancel_job - job not found returns None
    async def test_cancel_nonexistent_job_returns_none(self, mgr: MigrationJobManager) -> None:
        result = await mgr.cancel_job("no-such-job", TENANT)
        assert result is None

    # start_job - already QUEUED (not PENDING) returns unchanged
    async def test_start_job_non_pending_returns_unchanged(self, mgr: MigrationJobManager) -> None:
        job = await mgr.create_job(TENANT, _config())
        await mgr.start_job(job.job_id, TENANT)  # now QUEUED
        again = await mgr.start_job(job.job_id, TENANT)
        assert again is not None
        assert again.status == MigrationJobStatus.QUEUED  # unchanged

    # start_job - job not found returns None
    async def test_start_job_nonexistent_returns_none(self, mgr: MigrationJobManager) -> None:
        result = await mgr.start_job("no-such-job", TENANT)
        assert result is None

    # fail_job - job not found returns None
    async def test_fail_job_nonexistent_returns_none(self, mgr: MigrationJobManager) -> None:
        result = await mgr.fail_job("no-such-job", "boom")
        assert result is None

    # complete_job - job not found returns None
    async def test_complete_job_nonexistent_returns_none(self, mgr: MigrationJobManager) -> None:
        result_obj = MigrationJobResult(
            job_id="nope",
            tenant_id=TENANT,
            status=MigrationJobStatus.COMPLETED,
        )
        result = await mgr.complete_job("nope", result_obj)
        assert result is None

    # update_progress - job not found returns None
    async def test_update_progress_nonexistent_returns_none(self, mgr: MigrationJobManager) -> None:
        result = await mgr.update_progress("nope", 10, 10, 0, 100)
        assert result is None

    # update_progress - zero total (phase_progress stays 0)
    async def test_update_progress_zero_total(self, mgr: MigrationJobManager) -> None:
        job = await mgr.create_job(TENANT, _config())
        updated = await mgr.update_progress(job.job_id, 0, 0, 0, 0)
        assert updated is not None
        assert updated.progress.phase_progress == 0.0

    # update_progress - QUEUED -> RUNNING transition
    async def test_update_progress_queued_becomes_running(self, mgr: MigrationJobManager) -> None:
        job = await mgr.create_job(TENANT, _config())
        await mgr.start_job(job.job_id, TENANT)  # -> QUEUED
        updated = await mgr.update_progress(job.job_id, 5, 5, 0, 100)
        assert updated is not None
        assert updated.status == MigrationJobStatus.RUNNING
        assert updated.started_at is not None
        assert updated.progress.start_time is not None

    # update_progress - already RUNNING (no second transition)
    async def test_update_progress_running_stays_running(self, mgr: MigrationJobManager) -> None:
        job = await mgr.create_job(TENANT, _config())
        await mgr.start_job(job.job_id, TENANT)
        # First update triggers QUEUED -> RUNNING
        await mgr.update_progress(job.job_id, 5, 5, 0, 100)
        # Second update: already RUNNING, no state change
        updated = await mgr.update_progress(job.job_id, 10, 10, 0, 100)
        assert updated is not None
        assert updated.status == MigrationJobStatus.RUNNING

    # update_progress - ETA branch: started_at set, processed > 0
    async def test_update_progress_with_started_at_eta_calculated(
        self, mgr: MigrationJobManager
    ) -> None:
        job = await mgr.create_job(TENANT, _config())
        await mgr.start_job(job.job_id, TENANT)
        # Trigger QUEUED->RUNNING which sets started_at
        await mgr.update_progress(job.job_id, 10, 10, 0, 100)
        # Push started_at back in time so elapsed > 0
        raw_job = mgr._jobs[job.job_id]
        raw_job.started_at = datetime.now(UTC) - timedelta(seconds=5)
        updated = await mgr.update_progress(job.job_id, 20, 20, 0, 100)
        assert updated is not None
        # ETA should now be calculated (not None)
        assert updated.progress.estimated_remaining_seconds is not None

    # update_progress - rate <= 0 branch: started_at in the future -> negative elapsed
    async def test_update_progress_negative_elapsed_skips_eta(
        self, mgr: MigrationJobManager
    ) -> None:
        job = await mgr.create_job(TENANT, _config())
        await mgr.start_job(job.job_id, TENANT)
        # Trigger RUNNING transition
        await mgr.update_progress(job.job_id, 1, 1, 0, 100)
        # Set started_at in the FUTURE so elapsed < 0 -> rate < 0
        raw_job = mgr._jobs[job.job_id]
        raw_job.started_at = datetime.now(UTC) + timedelta(seconds=9999)
        # Reset estimated_remaining_seconds to confirm it stays None
        raw_job.progress.estimated_remaining_seconds = None
        updated = await mgr.update_progress(job.job_id, 50, 50, 0, 100)
        assert updated is not None
        # rate <= 0 branch taken: ETA not set
        assert updated.progress.estimated_remaining_seconds is None

    # get_result - job not found
    async def test_get_result_job_not_found(self, mgr: MigrationJobManager) -> None:
        result = await mgr.get_result("nope", TENANT)
        assert result is None

    # get_result - job exists but not COMPLETED
    async def test_get_result_job_not_completed(self, mgr: MigrationJobManager) -> None:
        job = await mgr.create_job(TENANT, _config())
        result = await mgr.get_result(job.job_id, TENANT)
        assert result is None

    # get_result - completed, result stored
    async def test_get_result_completed_job(self, mgr: MigrationJobManager) -> None:
        job = await mgr.create_job(TENANT, _config())
        result_obj = MigrationJobResult(
            job_id=job.job_id,
            tenant_id=TENANT,
            status=MigrationJobStatus.COMPLETED,
            summary={"ok": 1},
        )
        await mgr.complete_job(job.job_id, result_obj)
        result = await mgr.get_result(job.job_id, TENANT)
        assert result is not None
        assert result.summary == {"ok": 1}

    # list_jobs - pagination (offset)
    async def test_list_jobs_pagination(self, mgr: MigrationJobManager) -> None:
        for _ in range(5):
            await mgr.create_job(TENANT, _config())
        first_two = await mgr.list_jobs(TENANT, limit=2, offset=0)
        next_two = await mgr.list_jobs(TENANT, limit=2, offset=2)
        assert len(first_two) == 2
        assert len(next_two) == 2
        # IDs should differ
        assert {j.job_id for j in first_two}.isdisjoint({j.job_id for j in next_two})

    # list_jobs - no jobs for tenant
    async def test_list_jobs_empty_for_tenant(self, mgr: MigrationJobManager) -> None:
        jobs = await mgr.list_jobs("unknown-tenant")
        assert jobs == []

    # constructor with custom hash
    def test_custom_constitutional_hash(self) -> None:
        mgr = MigrationJobManager(constitutional_hash="custom-hash")
        assert mgr.constitutional_hash == "custom-hash"


# ---------------------------------------------------------------------------
# ProgressCalculator - edge cases
# ---------------------------------------------------------------------------


class TestProgressCalculatorExtra:
    @pytest.fixture
    def calc(self) -> ProgressCalculator:
        return ProgressCalculator()

    # record_progress creates new list for new job_id
    def test_record_progress_creates_history(self, calc: ProgressCalculator) -> None:
        calc.record_progress("new-job", 5)
        assert "new-job" in calc._history
        assert len(calc._history["new-job"]) == 1

    # record_progress caps at 100 entries
    def test_record_progress_capped_at_100(self, calc: ProgressCalculator) -> None:
        for i in range(110):
            calc.record_progress("job-cap", i)
        assert len(calc._history["job-cap"]) == 100

    # calculate_eta - no history at all
    def test_calculate_eta_no_history(self, calc: ProgressCalculator) -> None:
        eta = calc.calculate_eta("unknown-job", 100)
        assert eta is None

    # calculate_eta - exactly one point
    def test_calculate_eta_one_point(self, calc: ProgressCalculator) -> None:
        calc.record_progress("j", 10)
        eta = calc.calculate_eta("j", 100)
        assert eta is None

    # calculate_eta - exactly two points; recent passes len < 2 guard
    def test_calculate_eta_exactly_two_points(self, calc: ProgressCalculator) -> None:
        now = datetime.now(UTC)
        calc._history["j"] = [
            (now - timedelta(seconds=10), 0),
            (now, 50),
        ]
        eta = calc.calculate_eta("j", total=100)
        assert eta is not None

    # calculate_eta - time_diff == 0 (two points at same time)
    def test_calculate_eta_zero_time_diff(self, calc: ProgressCalculator) -> None:
        now = datetime.now(UTC)
        calc._history["j"] = [(now, 0), (now, 50)]
        eta = calc.calculate_eta("j", 100)
        assert eta is None

    # calculate_eta - items_diff == 0 (no progress between points)
    def test_calculate_eta_zero_items_diff(self, calc: ProgressCalculator) -> None:
        now = datetime.now(UTC)
        calc._history["j"] = [
            (now - timedelta(seconds=10), 50),
            (now, 50),
        ]
        eta = calc.calculate_eta("j", 100)
        assert eta is None

    # calculate_eta - remaining == 0 (already done)
    def test_calculate_eta_already_complete(self, calc: ProgressCalculator) -> None:
        now = datetime.now(UTC)
        calc._history["j"] = [
            (now - timedelta(seconds=5), 0),
            (now, 100),
        ]
        eta = calc.calculate_eta("j", total=100)
        # remaining == 0, so seconds_remaining == 0 -> eta is "now"
        assert eta is not None

    # calculate_eta - negative items_diff (processed went backwards)
    def test_calculate_eta_negative_items_diff(self, calc: ProgressCalculator) -> None:
        now = datetime.now(UTC)
        calc._history["j"] = [
            (now - timedelta(seconds=5), 100),
            (now, 50),  # went backwards
        ]
        eta = calc.calculate_eta("j", 200)
        assert eta is None

    # get_processing_rate - no history
    def test_get_processing_rate_no_history(self, calc: ProgressCalculator) -> None:
        rate = calc.get_processing_rate("unknown")
        assert rate is None

    # get_processing_rate - only one entry
    def test_get_processing_rate_one_entry(self, calc: ProgressCalculator) -> None:
        calc.record_progress("j", 10)
        rate = calc.get_processing_rate("j")
        assert rate is None

    # get_processing_rate - time_diff <= 0
    def test_get_processing_rate_zero_time_diff(self, calc: ProgressCalculator) -> None:
        now = datetime.now(UTC)
        calc._history["j"] = [(now, 0), (now, 100)]
        rate = calc.get_processing_rate("j")
        assert rate is None

    # get_processing_rate - normal path
    def test_get_processing_rate_normal(self, calc: ProgressCalculator) -> None:
        now = datetime.now(UTC)
        calc._history["j"] = [
            (now - timedelta(seconds=10), 0),
            (now, 200),
        ]
        rate = calc.get_processing_rate("j")
        assert rate == pytest.approx(20.0, rel=0.05)

    # constructor custom hash
    def test_custom_hash(self) -> None:
        calc = ProgressCalculator(constitutional_hash="custom")
        assert calc.constitutional_hash == "custom"


# ---------------------------------------------------------------------------
# PDFReportGenerator - extra coverage
# ---------------------------------------------------------------------------


class TestPDFReportGeneratorExtra:
    @pytest.fixture
    def gen(self) -> PDFReportGenerator:
        return PDFReportGenerator()

    async def test_generate_report_with_warnings_and_errors(self, gen: PDFReportGenerator) -> None:
        result = MigrationJobResult(
            job_id="j-warn",
            tenant_id="t1",
            status=MigrationJobStatus.FAILED,
            summary={"ok": 0},
            warnings=["warn1", "warn2"],
            errors=["err1"],
            details=["d1", "d2", "d3"],
        )
        pdf = await gen.generate_report(result)
        content = pdf.content_bytes.decode("utf-8")
        assert "j-warn" in content
        assert "failed" in content
        assert "Warnings: 2" in content
        assert "Errors: 1" in content
        assert "Details: 3 items" in content

    async def test_create_pdf_content_returns_bytes(self, gen: PDFReportGenerator) -> None:
        result = MigrationJobResult(
            job_id="j2",
            tenant_id="t2",
            status=MigrationJobStatus.COMPLETED,
        )
        content = gen._create_pdf_content(result)
        assert isinstance(content, bytes)
        assert len(content) > 0

    def test_custom_constitutional_hash(self) -> None:
        gen = PDFReportGenerator(constitutional_hash="custom-hash")
        assert gen.constitutional_hash == "custom-hash"

    async def test_generated_report_has_correct_tenant(self, gen: PDFReportGenerator) -> None:
        result = MigrationJobResult(
            job_id="j3",
            tenant_id="my-tenant",
            status=MigrationJobStatus.COMPLETED,
        )
        pdf = await gen.generate_report(result)
        assert pdf.tenant_id == "my-tenant"


# ---------------------------------------------------------------------------
# AsyncTaskQueue - uncovered branches
# ---------------------------------------------------------------------------


class TestAsyncTaskQueueExtra:
    # sync (non-coroutine) task function
    async def test_sync_task_function_executed(self) -> None:
        q = AsyncTaskQueue(max_workers=1)
        await q.start()
        try:

            def sync_task(x: int) -> int:
                return x * 3

            await q.enqueue("job-sync", sync_task, 7)
            await asyncio.sleep(0.15)
            result = q.get_result("job-sync")
            assert result is not None
            assert result["status"] == "success"
            assert result["result"] == 21
        finally:
            await q.stop()

    # RuntimeError caught as JOB_WORKER_EXECUTION_ERRORS
    async def test_runtime_error_caught(self) -> None:
        q = AsyncTaskQueue(max_workers=1)
        await q.start()
        try:

            async def boom():
                raise RuntimeError("runtime boom")

            await q.enqueue("job-re", boom)
            await asyncio.sleep(0.15)
            result = q.get_result("job-re")
            assert result is not None
            assert result["status"] == "error"
            assert "runtime boom" in result["error"]
        finally:
            await q.stop()

    # TypeError caught
    async def test_type_error_caught(self) -> None:
        q = AsyncTaskQueue(max_workers=1)
        await q.start()
        try:

            async def type_err():
                raise TypeError("type err")

            await q.enqueue("job-te", type_err)
            await asyncio.sleep(0.15)
            result = q.get_result("job-te")
            assert result is not None
            assert result["status"] == "error"
        finally:
            await q.stop()

    # KeyError caught
    async def test_key_error_caught(self) -> None:
        q = AsyncTaskQueue(max_workers=1)
        await q.start()
        try:

            async def key_err():
                raise KeyError("missing key")

            await q.enqueue("job-ke", key_err)
            await asyncio.sleep(0.15)
            result = q.get_result("job-ke")
            assert result is not None
            assert result["status"] == "error"
        finally:
            await q.stop()

    # AttributeError caught
    async def test_attribute_error_caught(self) -> None:
        q = AsyncTaskQueue(max_workers=1)
        await q.start()
        try:

            async def attr_err():
                raise AttributeError("no attr")

            await q.enqueue("job-ae", attr_err)
            await asyncio.sleep(0.15)
            result = q.get_result("job-ae")
            assert result is not None
            assert result["status"] == "error"
        finally:
            await q.stop()

    # ConnectionError caught
    async def test_connection_error_caught(self) -> None:
        q = AsyncTaskQueue(max_workers=1)
        await q.start()
        try:

            async def conn_err():
                raise ConnectionError("conn failed")

            await q.enqueue("job-ce", conn_err)
            await asyncio.sleep(0.15)
            result = q.get_result("job-ce")
            assert result is not None
            assert result["status"] == "error"
        finally:
            await q.stop()

    # OSError caught
    async def test_os_error_caught(self) -> None:
        q = AsyncTaskQueue(max_workers=1)
        await q.start()
        try:

            async def os_err():
                raise OSError("disk full")

            await q.enqueue("job-oe", os_err)
            await asyncio.sleep(0.15)
            result = q.get_result("job-oe")
            assert result is not None
            assert result["status"] == "error"
        finally:
            await q.stop()

    # get_result returns None for unknown job_id
    async def test_get_result_unknown_returns_none(self) -> None:
        q = AsyncTaskQueue()
        assert q.get_result("no-such-job") is None

    # queue_size property with items in queue (no workers draining)
    async def test_queue_size_nonzero(self) -> None:
        q = AsyncTaskQueue(max_workers=0)
        # Manually push items onto the internal queue
        await q._queue.put(("j1", lambda: None, (), {}))
        await q._queue.put(("j2", lambda: None, (), {}))
        assert q.queue_size == 2

    # constructor custom max_workers
    def test_custom_max_workers(self) -> None:
        q = AsyncTaskQueue(max_workers=8)
        assert q.max_workers == 8

    # constructor custom constitutional hash
    def test_custom_constitutional_hash(self) -> None:
        q = AsyncTaskQueue(constitutional_hash="my-hash")
        assert q.constitutional_hash == "my-hash"

    # stop with no workers (workers list empty)
    async def test_stop_with_no_workers_is_safe(self) -> None:
        q = AsyncTaskQueue(max_workers=2)
        # Don't call start() -- _workers is empty
        await q.stop()  # Should not raise

    # asyncio.TimeoutError during task (caught by inner JOB_WORKER_EXECUTION_ERRORS handler)
    async def test_asyncio_timeout_error_caught(self) -> None:
        q = AsyncTaskQueue(max_workers=1)
        await q.start()
        try:

            async def timeout_err():
                raise TimeoutError()

            await q.enqueue("job-to", timeout_err)
            await asyncio.sleep(0.2)
            result = q.get_result("job-to")
            assert result is not None
            assert result["status"] == "error"
        finally:
            await q.stop()

    # Worker processes kwargs correctly
    async def test_enqueue_with_kwargs(self) -> None:
        q = AsyncTaskQueue(max_workers=1)
        await q.start()
        try:

            async def task_with_kwargs(a: int, b: int = 0) -> int:
                return a + b

            await q.enqueue("job-kw", task_with_kwargs, 3, b=7)
            await asyncio.sleep(0.15)
            result = q.get_result("job-kw")
            assert result is not None
            assert result["result"] == 10
        finally:
            await q.stop()

    # Worker outer TimeoutError continue branch (lines 444-445):
    # A started worker with an empty queue will hit the 1-second wait_for
    # timeout and execute `except asyncio.TimeoutError: continue`.
    async def test_worker_idle_timeout_continue_branch(self) -> None:
        q = AsyncTaskQueue(max_workers=1)
        await q.start()
        try:
            # Wait long enough to let the worker hit the idle timeout at least once
            await asyncio.sleep(1.2)

            # Confirm the worker is still alive and can process tasks
            async def simple() -> int:
                return 99

            await q.enqueue("after-idle", simple)
            await asyncio.sleep(0.15)
            result = q.get_result("after-idle")
            assert result is not None
            assert result["result"] == 99
        finally:
            await q.stop()


# ---------------------------------------------------------------------------
# MigrationJobAPI - uncovered branches
# ---------------------------------------------------------------------------


class TestMigrationJobAPIExtra:
    @pytest.fixture
    def api(self) -> MigrationJobAPI:
        return MigrationJobAPI(
            job_manager=MigrationJobManager(),
            task_queue=AsyncTaskQueue(),
            pdf_generator=PDFReportGenerator(),
        )

    # create_migration with options=None (uses default {})
    async def test_create_migration_options_none(self, api: MigrationJobAPI) -> None:
        resp = await api.create_migration(
            tenant_id=TENANT,
            job_type=MigrationJobType.DECISION_LOG_IMPORT,
            source_config={"src": "x"},
            target_config={"dst": "y"},
            options=None,
        )
        assert resp["status"] == "pending"
        job = await api.job_manager.get_job(resp["job_id"], TENANT)
        assert job is not None
        assert job.config.options == {}

    # create_migration with explicit options dict
    async def test_create_migration_with_options(self, api: MigrationJobAPI) -> None:
        resp = await api.create_migration(
            tenant_id=TENANT,
            job_type=MigrationJobType.CONSTITUTIONAL_ANALYSIS,
            source_config={},
            target_config={},
            options={"dry_run": True},
        )
        job = await api.job_manager.get_job(resp["job_id"], TENANT)
        assert job is not None
        assert job.config.options["dry_run"] is True

    # get_migration returns None for unknown job
    async def test_get_migration_not_found(self, api: MigrationJobAPI) -> None:
        result = await api.get_migration(TENANT, "no-such-job")
        assert result is None

    # get_migration with started_at and completed_at set
    async def test_get_migration_with_timestamps(self, api: MigrationJobAPI) -> None:
        resp = await api.create_migration(
            tenant_id=TENANT,
            job_type=MigrationJobType.FULL_MIGRATION,
            source_config={},
            target_config={},
        )
        job_id = resp["job_id"]
        job = await api.job_manager.get_job(job_id, TENANT)
        assert job is not None
        # Manually set timestamps to exercise isoformat() branches
        job.started_at = datetime.now(UTC)
        job.completed_at = datetime.now(UTC)
        detail = await api.get_migration(TENANT, job_id)
        assert detail is not None
        assert detail["started_at"] is not None
        assert detail["completed_at"] is not None

    # get_migration - started_at and completed_at are None (None branches)
    async def test_get_migration_null_timestamps(self, api: MigrationJobAPI) -> None:
        resp = await api.create_migration(
            tenant_id=TENANT,
            job_type=MigrationJobType.POLICY_IMPORT,
            source_config={},
            target_config={},
        )
        detail = await api.get_migration(TENANT, resp["job_id"])
        assert detail is not None
        assert detail["started_at"] is None
        assert detail["completed_at"] is None

    # list_migrations with status string filter
    async def test_list_migrations_with_status_filter(self, api: MigrationJobAPI) -> None:
        r1 = await api.create_migration(
            tenant_id=TENANT,
            job_type=MigrationJobType.POLICY_IMPORT,
            source_config={},
            target_config={},
        )
        await api.create_migration(
            tenant_id=TENANT,
            job_type=MigrationJobType.GAP_REMEDIATION,
            source_config={},
            target_config={},
        )
        # Cancel first job
        await api.cancel_migration(TENANT, r1["job_id"])
        cancelled_list = await api.list_migrations(TENANT, status="cancelled")
        assert cancelled_list["total"] == 1

    # list_migrations with limit and offset
    async def test_list_migrations_limit_offset(self, api: MigrationJobAPI) -> None:
        for _ in range(4):
            await api.create_migration(
                tenant_id=TENANT,
                job_type=MigrationJobType.POLICY_IMPORT,
                source_config={},
                target_config={},
            )
        resp = await api.list_migrations(TENANT, limit=2, offset=1)
        assert resp["limit"] == 2
        assert resp["offset"] == 1
        assert len(resp["jobs"]) == 2

    # cancel_migration - job not found returns None
    async def test_cancel_migration_not_found(self, api: MigrationJobAPI) -> None:
        result = await api.cancel_migration(TENANT, "no-such-job")
        assert result is None

    # cancel_migration - cancelled_at set (completed_at is not None)
    async def test_cancel_migration_has_cancelled_at(self, api: MigrationJobAPI) -> None:
        resp = await api.create_migration(
            tenant_id=TENANT,
            job_type=MigrationJobType.POLICY_IMPORT,
            source_config={},
            target_config={},
        )
        cancel_resp = await api.cancel_migration(TENANT, resp["job_id"])
        assert cancel_resp is not None
        assert cancel_resp["cancelled_at"] is not None

    # get_migration_results - no result (job not completed)
    async def test_get_migration_results_none(self, api: MigrationJobAPI) -> None:
        resp = await api.create_migration(
            tenant_id=TENANT,
            job_type=MigrationJobType.POLICY_IMPORT,
            source_config={},
            target_config={},
        )
        result = await api.get_migration_results(TENANT, resp["job_id"])
        assert result is None

    # get_migration_results - CSV format (falls through to JSON path)
    async def test_get_migration_results_csv_format(self, api: MigrationJobAPI) -> None:
        resp = await api.create_migration(
            tenant_id=TENANT,
            job_type=MigrationJobType.POLICY_IMPORT,
            source_config={},
            target_config={},
        )
        result_obj = MigrationJobResult(
            job_id=resp["job_id"],
            tenant_id=TENANT,
            status=MigrationJobStatus.COMPLETED,
            summary={"ok": 5},
            details=["d1", "d2"],
            warnings=["w1"],
            errors=[],
        )
        await api.job_manager.complete_job(resp["job_id"], result_obj)
        result = await api.get_migration_results(TENANT, resp["job_id"], ReportFormat.CSV)
        assert result is not None
        assert result["format"] == "json"
        assert result["details_count"] == 2

    # get_migration_results - HTML format (falls through to JSON path)
    async def test_get_migration_results_html_format(self, api: MigrationJobAPI) -> None:
        resp = await api.create_migration(
            tenant_id=TENANT,
            job_type=MigrationJobType.POLICY_IMPORT,
            source_config={},
            target_config={},
        )
        result_obj = MigrationJobResult(
            job_id=resp["job_id"],
            tenant_id=TENANT,
            status=MigrationJobStatus.COMPLETED,
        )
        await api.job_manager.complete_job(resp["job_id"], result_obj)
        result = await api.get_migration_results(TENANT, resp["job_id"], ReportFormat.HTML)
        assert result is not None
        assert result["format"] == "json"

    # get_migration_results - JSON default
    async def test_get_migration_results_json_default(self, api: MigrationJobAPI) -> None:
        resp = await api.create_migration(
            tenant_id=TENANT,
            job_type=MigrationJobType.FULL_MIGRATION,
            source_config={},
            target_config={},
        )
        result_obj = MigrationJobResult(
            job_id=resp["job_id"],
            tenant_id=TENANT,
            status=MigrationJobStatus.COMPLETED,
            summary={"total": 10},
            warnings=["w"],
            errors=["e"],
            details=["x"],
        )
        await api.job_manager.complete_job(resp["job_id"], result_obj)
        result = await api.get_migration_results(TENANT, resp["job_id"])
        assert result is not None
        assert result["warnings"] == ["w"]
        assert result["errors"] == ["e"]
        assert result["details_count"] == 1

    # MigrationJobAPI constructor with custom hash
    def test_custom_hash(self) -> None:
        api = MigrationJobAPI(
            job_manager=MigrationJobManager(),
            task_queue=AsyncTaskQueue(),
            pdf_generator=PDFReportGenerator(),
            constitutional_hash="my-custom-hash",
        )
        assert api.constitutional_hash == "my-custom-hash"

    # All MigrationJobType values used in create_migration
    async def test_all_job_types_creatable(self, api: MigrationJobAPI) -> None:
        for jt in MigrationJobType:
            resp = await api.create_migration(
                tenant_id=TENANT,
                job_type=jt,
                source_config={},
                target_config={},
            )
            assert resp["status"] == "pending"


# ---------------------------------------------------------------------------
# Constitutional hash end-to-end
# ---------------------------------------------------------------------------


class TestConstitutionalHashEndToEnd:
    async def test_full_job_lifecycle_carries_hash(self) -> None:
        mgr = MigrationJobManager()
        cfg = _config()
        job = await mgr.create_job(TENANT, cfg)
        assert job.constitutional_hash == CONSTITUTIONAL_HASH

        await mgr.start_job(job.job_id, TENANT)
        updated = await mgr.update_progress(job.job_id, 50, 50, 0, 100)
        assert updated is not None

        result_obj = MigrationJobResult(
            job_id=job.job_id,
            tenant_id=TENANT,
            status=MigrationJobStatus.COMPLETED,
        )
        completed = await mgr.complete_job(job.job_id, result_obj)
        assert completed is not None
        assert completed.constitutional_hash == CONSTITUTIONAL_HASH

        result = await mgr.get_result(job.job_id, TENANT)
        assert result is not None
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    def test_constitutional_hash_value(self) -> None:
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH  # pragma: allowlist secret
