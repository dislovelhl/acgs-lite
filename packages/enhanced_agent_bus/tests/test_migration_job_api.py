"""
Migration Job Management API Tests
Constitutional Hash: 608508a9bd224290

Phase 10 Task 11: Migration Job Management API

Tests:
- Job lifecycle (create, get, list, cancel)
- Progress calculation and ETA estimation
- Result access and PDF report generation
- Background job processing with async task queue
- Constitutional compliance validation
"""

import asyncio
from datetime import UTC, datetime, timedelta, timezone

import pytest

from enterprise_sso.migration_job_api import (
    CONSTITUTIONAL_HASH,
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

# ============================================================================
# Test Classes
# ============================================================================


class TestMigrationJobLifecycle:
    """Tests for migration job lifecycle management."""

    @pytest.fixture
    def job_manager(self):
        return MigrationJobManager()

    async def test_create_job(self, job_manager):
        """Test creating a new migration job."""
        config = MigrationJobConfig(
            job_type=MigrationJobType.POLICY_IMPORT,
            source_config={"path": "/policies"},
            target_config={"database": "policies_db"},
        )

        job = await job_manager.create_job("tenant-001", config)

        assert job.job_id is not None
        assert job.tenant_id == "tenant-001"
        assert job.status == MigrationJobStatus.PENDING
        assert job.config.job_type == MigrationJobType.POLICY_IMPORT

    async def test_get_job(self, job_manager):
        """Test retrieving a job by ID."""
        config = MigrationJobConfig(job_type=MigrationJobType.FULL_MIGRATION)
        job = await job_manager.create_job("tenant-001", config)

        retrieved = await job_manager.get_job(job.job_id, "tenant-001")

        assert retrieved is not None
        assert retrieved.job_id == job.job_id

    async def test_get_job_wrong_tenant(self, job_manager):
        """Test that jobs are tenant-isolated."""
        config = MigrationJobConfig(job_type=MigrationJobType.FULL_MIGRATION)
        job = await job_manager.create_job("tenant-001", config)

        retrieved = await job_manager.get_job(job.job_id, "tenant-002")

        assert retrieved is None

    async def test_list_jobs_for_tenant(self, job_manager):
        """Test listing jobs for a specific tenant."""
        config = MigrationJobConfig(job_type=MigrationJobType.POLICY_IMPORT)

        await job_manager.create_job("tenant-001", config)
        await job_manager.create_job("tenant-001", config)
        await job_manager.create_job("tenant-002", config)

        jobs = await job_manager.list_jobs("tenant-001")

        assert len(jobs) == 2
        assert all(j.tenant_id == "tenant-001" for j in jobs)

    async def test_list_jobs_with_status_filter(self, job_manager):
        """Test filtering jobs by status."""
        config = MigrationJobConfig(job_type=MigrationJobType.POLICY_IMPORT)

        job1 = await job_manager.create_job("tenant-001", config)
        await job_manager.create_job("tenant-001", config)
        await job_manager.cancel_job(job1.job_id, "tenant-001")

        cancelled = await job_manager.list_jobs("tenant-001", MigrationJobStatus.CANCELLED)
        pending = await job_manager.list_jobs("tenant-001", MigrationJobStatus.PENDING)

        assert len(cancelled) == 1
        assert len(pending) == 1

    async def test_cancel_job(self, job_manager):
        """Test cancelling a migration job."""
        config = MigrationJobConfig(job_type=MigrationJobType.POLICY_IMPORT)
        job = await job_manager.create_job("tenant-001", config)

        cancelled = await job_manager.cancel_job(job.job_id, "tenant-001")

        assert cancelled.status == MigrationJobStatus.CANCELLED
        assert cancelled.completed_at is not None

    async def test_start_job(self, job_manager):
        """Test starting a pending job."""
        config = MigrationJobConfig(job_type=MigrationJobType.POLICY_IMPORT)
        job = await job_manager.create_job("tenant-001", config)

        started = await job_manager.start_job(job.job_id, "tenant-001")

        assert started.status == MigrationJobStatus.QUEUED

    async def test_complete_job(self, job_manager):
        """Test completing a job with results."""
        config = MigrationJobConfig(job_type=MigrationJobType.POLICY_IMPORT)
        job = await job_manager.create_job("tenant-001", config)

        result = MigrationJobResult(
            job_id=job.job_id,
            tenant_id="tenant-001",
            status=MigrationJobStatus.COMPLETED,
            summary={"imported": 100, "failed": 0},
        )

        completed = await job_manager.complete_job(job.job_id, result)

        assert completed.status == MigrationJobStatus.COMPLETED
        assert completed.completed_at is not None

    async def test_fail_job(self, job_manager):
        """Test failing a job with error message."""
        config = MigrationJobConfig(job_type=MigrationJobType.POLICY_IMPORT)
        job = await job_manager.create_job("tenant-001", config)

        failed = await job_manager.fail_job(job.job_id, "Connection timeout")

        assert failed.status == MigrationJobStatus.FAILED
        assert failed.error_message == "Connection timeout"


class TestProgressCalculation:
    """Tests for progress calculation and ETA estimation."""

    @pytest.fixture
    def calculator(self):
        return ProgressCalculator()

    def test_record_progress(self, calculator):
        """Test recording progress points."""
        calculator.record_progress("job-001", 10)
        calculator.record_progress("job-001", 20)

        assert len(calculator._history["job-001"]) == 2

    def test_calculate_eta(self, calculator):
        """Test ETA calculation."""
        job_id = "job-001"
        # Simulate progress over time
        calculator._history[job_id] = [
            (datetime.now(UTC) - timedelta(seconds=10), 0),
            (datetime.now(UTC) - timedelta(seconds=5), 50),
            (datetime.now(UTC), 100),
        ]

        eta = calculator.calculate_eta(job_id, total=200)

        assert eta is not None
        # ETA should be in the future
        assert eta > datetime.now(UTC)

    def test_calculate_eta_insufficient_data(self, calculator):
        """Test ETA returns None with insufficient data."""
        calculator.record_progress("job-001", 10)

        eta = calculator.calculate_eta("job-001", total=100)

        assert eta is None

    def test_get_processing_rate(self, calculator):
        """Test getting processing rate."""
        job_id = "job-001"
        calculator._history[job_id] = [
            (datetime.now(UTC) - timedelta(seconds=10), 0),
            (datetime.now(UTC), 100),
        ]

        rate = calculator.get_processing_rate(job_id)

        assert rate is not None
        assert rate == pytest.approx(10.0, rel=0.1)  # 100 items / 10 seconds

    def test_progress_percentage(self):
        """Test progress percentage calculation."""
        progress = MigrationJobProgress(total_items=200, processed_items=50)

        assert progress.percentage_complete == 25.0

    def test_progress_percentage_zero_total(self):
        """Test progress percentage with zero total items."""
        progress = MigrationJobProgress()

        assert progress.percentage_complete == 0.0


class TestPDFReportGeneration:
    """Tests for PDF report generation."""

    @pytest.fixture
    def generator(self):
        return PDFReportGenerator()

    async def test_generate_pdf_report(self, generator):
        """Test generating a PDF report."""
        result = MigrationJobResult(
            job_id="job-001",
            tenant_id="tenant-001",
            status=MigrationJobStatus.COMPLETED,
            summary={"imported": 100},
            warnings=["Warning 1"],
            errors=[],
        )

        pdf = await generator.generate_report(result)

        assert pdf.job_id == "job-001"
        assert pdf.tenant_id == "tenant-001"
        assert pdf.filename.startswith("migration_report_job-001_")
        assert pdf.filename.endswith(".pdf")
        assert len(pdf.content_bytes) > 0

    async def test_pdf_contains_job_info(self, generator):
        """Test that PDF contains job information."""
        result = MigrationJobResult(
            job_id="job-123", tenant_id="tenant-456", status=MigrationJobStatus.COMPLETED
        )

        pdf = await generator.generate_report(result)
        content = pdf.content_bytes.decode("utf-8")

        assert "job-123" in content
        assert "tenant-456" in content
        assert CONSTITUTIONAL_HASH in content

    async def test_pdf_includes_constitutional_hash(self, generator):
        """Test that PDF report includes constitutional hash."""
        result = MigrationJobResult(
            job_id="job-001", tenant_id="tenant-001", status=MigrationJobStatus.COMPLETED
        )

        pdf = await generator.generate_report(result)

        assert pdf.constitutional_hash == CONSTITUTIONAL_HASH


class TestAsyncTaskQueue:
    """Tests for background job processing."""

    @pytest.fixture
    async def task_queue(self):
        queue = AsyncTaskQueue(max_workers=2)
        await queue.start()
        yield queue
        await queue.stop()

    async def test_enqueue_and_process(self, task_queue):
        """Test enqueueing and processing a task."""

        async def sample_task(x):
            return x * 2

        await task_queue.enqueue("job-001", sample_task, 5)
        await asyncio.sleep(0.1)  # Wait for processing

        result = task_queue.get_result("job-001")
        assert result is not None
        assert result["status"] == "success"
        assert result["result"] == 10

    async def test_queue_multiple_tasks(self, task_queue):
        """Test processing multiple tasks."""

        async def sample_task(x):
            return x + 1

        for i in range(5):
            await task_queue.enqueue(f"job-{i}", sample_task, i)

        await asyncio.sleep(0.2)  # Wait for processing

        for i in range(5):
            result = task_queue.get_result(f"job-{i}")
            assert result is not None
            assert result["result"] == i + 1

    async def test_task_error_handling(self, task_queue):
        """Test error handling in task processing."""

        async def failing_task():
            raise ValueError("Task failed")

        await task_queue.enqueue("job-fail", failing_task)
        await asyncio.sleep(0.1)

        result = task_queue.get_result("job-fail")
        assert result is not None
        assert result["status"] == "error"
        assert "Task failed" in result["error"]

    async def test_queue_size(self, task_queue):
        """Test getting queue size."""
        # Initially empty
        initial_size = task_queue.queue_size
        assert initial_size == 0


class TestMigrationJobAPI:
    """Tests for migration job API endpoints."""

    @pytest.fixture
    async def api(self):
        job_manager = MigrationJobManager()
        task_queue = AsyncTaskQueue()
        pdf_generator = PDFReportGenerator()
        return MigrationJobAPI(job_manager, task_queue, pdf_generator)

    async def test_create_migration_endpoint(self, api):
        """Test POST /tenants/{tenant_id}/migrations"""
        response = await api.create_migration(
            tenant_id="tenant-001",
            job_type=MigrationJobType.POLICY_IMPORT,
            source_config={"path": "/data"},
            target_config={"db": "main"},
        )

        assert "job_id" in response
        assert response["status"] == "pending"
        assert response["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_get_migration_endpoint(self, api):
        """Test GET /tenants/{tenant_id}/migrations/{job_id}"""
        create_resp = await api.create_migration(
            tenant_id="tenant-001",
            job_type=MigrationJobType.FULL_MIGRATION,
            source_config={},
            target_config={},
        )

        get_resp = await api.get_migration("tenant-001", create_resp["job_id"])

        assert get_resp is not None
        assert get_resp["job_id"] == create_resp["job_id"]
        assert "progress" in get_resp
        assert get_resp["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_list_migrations_endpoint(self, api):
        """Test GET /tenants/{tenant_id}/migrations"""
        await api.create_migration(
            tenant_id="tenant-001",
            job_type=MigrationJobType.POLICY_IMPORT,
            source_config={},
            target_config={},
        )
        await api.create_migration(
            tenant_id="tenant-001",
            job_type=MigrationJobType.GAP_REMEDIATION,
            source_config={},
            target_config={},
        )

        response = await api.list_migrations("tenant-001")

        assert response["total"] == 2
        assert len(response["jobs"]) == 2
        assert response["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_cancel_migration_endpoint(self, api):
        """Test DELETE /tenants/{tenant_id}/migrations/{job_id}"""
        create_resp = await api.create_migration(
            tenant_id="tenant-001",
            job_type=MigrationJobType.POLICY_IMPORT,
            source_config={},
            target_config={},
        )

        cancel_resp = await api.cancel_migration("tenant-001", create_resp["job_id"])

        assert cancel_resp is not None
        assert cancel_resp["status"] == "cancelled"
        assert cancel_resp["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_get_results_json(self, api):
        """Test GET /tenants/{tenant_id}/migrations/{job_id}/results (JSON)"""
        create_resp = await api.create_migration(
            tenant_id="tenant-001",
            job_type=MigrationJobType.POLICY_IMPORT,
            source_config={},
            target_config={},
        )

        result = MigrationJobResult(
            job_id=create_resp["job_id"],
            tenant_id="tenant-001",
            status=MigrationJobStatus.COMPLETED,
            summary={"imported": 50},
        )
        await api.job_manager.complete_job(create_resp["job_id"], result)

        response = await api.get_migration_results(
            "tenant-001", create_resp["job_id"], ReportFormat.JSON
        )

        assert response is not None
        assert response["format"] == "json"
        assert response["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_get_results_pdf(self, api):
        """Test GET /tenants/{tenant_id}/migrations/{job_id}/results (PDF)"""
        create_resp = await api.create_migration(
            tenant_id="tenant-001",
            job_type=MigrationJobType.POLICY_IMPORT,
            source_config={},
            target_config={},
        )

        result = MigrationJobResult(
            job_id=create_resp["job_id"],
            tenant_id="tenant-001",
            status=MigrationJobStatus.COMPLETED,
        )
        await api.job_manager.complete_job(create_resp["job_id"], result)

        response = await api.get_migration_results(
            "tenant-001", create_resp["job_id"], ReportFormat.PDF
        )

        assert response is not None
        assert response["format"] == "pdf"
        assert "filename" in response
        assert response["constitutional_hash"] == CONSTITUTIONAL_HASH


class TestConstitutionalCompliance:
    """Tests for constitutional hash compliance."""

    def test_job_includes_constitutional_hash(self):
        """Test that jobs include constitutional hash."""
        config = MigrationJobConfig(job_type=MigrationJobType.POLICY_IMPORT)
        job = MigrationJob(job_id="job-001", tenant_id="tenant-001", config=config)

        assert job.constitutional_hash == CONSTITUTIONAL_HASH

    def test_config_includes_constitutional_hash(self):
        """Test that config includes constitutional hash."""
        config = MigrationJobConfig(job_type=MigrationJobType.FULL_MIGRATION)

        assert config.constitutional_hash == CONSTITUTIONAL_HASH

    def test_result_includes_constitutional_hash(self):
        """Test that results include constitutional hash."""
        result = MigrationJobResult(
            job_id="job-001", tenant_id="tenant-001", status=MigrationJobStatus.COMPLETED
        )

        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    def test_progress_includes_constitutional_hash(self):
        """Test that progress includes constitutional hash."""
        progress = MigrationJobProgress()

        assert progress.constitutional_hash == CONSTITUTIONAL_HASH

    def test_pdf_report_includes_constitutional_hash(self):
        """Test that PDF reports include constitutional hash."""
        pdf = PDFReport(
            job_id="job-001", tenant_id="tenant-001", filename="report.pdf", content_bytes=b"test"
        )

        assert pdf.constitutional_hash == CONSTITUTIONAL_HASH
