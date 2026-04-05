"""
Migration Job Management API
Constitutional Hash: 608508a9bd224290

Phase 10 Task 11: Migration Job Management API

Provides:
- Job lifecycle management (create, get, list, cancel)
- Progress calculation and ETA estimation
- PDF report generation for migration results
- Background job processing with async task queue
- RESTful API endpoints for tenant migrations
"""

import asyncio
import inspect
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from enum import Enum

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

JOB_WORKER_EXECUTION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    ConnectionError,
    OSError,
    asyncio.TimeoutError,
)

# ============================================================================
# Enums
# ============================================================================


class MigrationJobStatus(Enum):
    """Status of a migration job."""

    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MigrationJobType(Enum):
    """Type of migration job."""

    POLICY_IMPORT = "policy_import"
    DECISION_LOG_IMPORT = "decision_log_import"
    CONSTITUTIONAL_ANALYSIS = "constitutional_analysis"
    FULL_MIGRATION = "full_migration"
    GAP_REMEDIATION = "gap_remediation"


class ReportFormat(Enum):
    """Output format for migration reports."""

    JSON = "json"
    CSV = "csv"
    PDF = "pdf"
    HTML = "html"


# ============================================================================
# Data Classes
# ============================================================================


@dataclass
class MigrationJobProgress:
    """Progress information for a migration job."""

    total_items: int = 0
    processed_items: int = 0
    successful_items: int = 0
    failed_items: int = 0
    current_phase: str = "initializing"
    phase_progress: float = 0.0
    estimated_remaining_seconds: float | None = None
    start_time: datetime | None = None
    constitutional_hash: str = CONSTITUTIONAL_HASH

    @property
    def percentage_complete(self) -> float:
        """Calculate percentage complete."""
        if self.total_items == 0:
            return 0.0
        return (self.processed_items / self.total_items) * 100.0


@dataclass
class MigrationJobConfig:
    """Configuration for a migration job."""

    job_type: MigrationJobType
    source_config: dict = field(default_factory=dict)
    target_config: dict = field(default_factory=dict)
    options: dict = field(default_factory=dict)
    batch_size: int = 100
    max_retries: int = 3
    timeout_seconds: int = 3600
    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass
class MigrationJob:
    """A migration job record."""

    job_id: str
    tenant_id: str
    config: MigrationJobConfig
    status: MigrationJobStatus = MigrationJobStatus.PENDING
    progress: MigrationJobProgress = field(default_factory=MigrationJobProgress)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    result_url: str | None = None
    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass
class MigrationJobResult:
    """Result of a completed migration job."""

    job_id: str
    tenant_id: str
    status: MigrationJobStatus
    summary: dict = field(default_factory=dict)
    details: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    report_generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass
class PDFReport:
    """PDF report for migration results."""

    job_id: str
    tenant_id: str
    filename: str
    content_bytes: bytes
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    constitutional_hash: str = CONSTITUTIONAL_HASH


# ============================================================================
# Implementation Classes
# ============================================================================


class MigrationJobManager:
    """Manages migration jobs for tenants."""

    def __init__(self, constitutional_hash: str = CONSTITUTIONAL_HASH):
        self.constitutional_hash = constitutional_hash
        self._jobs: dict[str, MigrationJob] = {}
        self._results: dict[str, MigrationJobResult] = {}
        self._job_callbacks: dict[str, Callable] = {}

    async def create_job(self, tenant_id: str, config: MigrationJobConfig) -> MigrationJob:
        """Create a new migration job."""
        job_id = str(uuid.uuid4())
        job = MigrationJob(
            job_id=job_id,
            tenant_id=tenant_id,
            config=config,
            status=MigrationJobStatus.PENDING,
            constitutional_hash=self.constitutional_hash,
        )
        self._jobs[job_id] = job
        return job

    async def get_job(self, job_id: str, tenant_id: str) -> MigrationJob | None:
        """Get a migration job by ID."""
        job = self._jobs.get(job_id)
        if job and job.tenant_id == tenant_id:
            return job
        return None

    async def list_jobs(
        self,
        tenant_id: str,
        status: MigrationJobStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MigrationJob]:
        """List migration jobs for a tenant."""
        jobs = [j for j in self._jobs.values() if j.tenant_id == tenant_id]
        if status:
            jobs = [j for j in jobs if j.status == status]
        jobs.sort(key=lambda x: x.created_at, reverse=True)
        return jobs[offset : offset + limit]

    async def cancel_job(self, job_id: str, tenant_id: str) -> MigrationJob | None:
        """Cancel a migration job."""
        job = await self.get_job(job_id, tenant_id)
        if not job:
            return None
        if job.status in (MigrationJobStatus.COMPLETED, MigrationJobStatus.CANCELLED):
            return job  # Already terminal state
        job.status = MigrationJobStatus.CANCELLED
        job.completed_at = datetime.now(UTC)
        return job

    async def start_job(self, job_id: str, tenant_id: str) -> MigrationJob | None:
        """Start a pending migration job."""
        job = await self.get_job(job_id, tenant_id)
        if not job:
            return None
        if job.status != MigrationJobStatus.PENDING:
            return job
        job.status = MigrationJobStatus.QUEUED
        return job

    async def update_progress(
        self,
        job_id: str,
        processed: int,
        successful: int,
        failed: int,
        total: int,
        phase: str = "processing",
    ) -> MigrationJob | None:
        """Update job progress."""
        job = self._jobs.get(job_id)
        if not job:
            return None

        job.progress.processed_items = processed
        job.progress.successful_items = successful
        job.progress.failed_items = failed
        job.progress.total_items = total
        job.progress.current_phase = phase
        job.progress.phase_progress = (processed / total * 100) if total > 0 else 0

        # Calculate ETA
        if job.started_at and processed > 0:
            elapsed = (datetime.now(UTC) - job.started_at).total_seconds()
            rate = processed / elapsed
            remaining = total - processed
            if rate > 0:
                job.progress.estimated_remaining_seconds = remaining / rate

        if job.status == MigrationJobStatus.QUEUED:
            job.status = MigrationJobStatus.RUNNING
            job.started_at = datetime.now(UTC)
            job.progress.start_time = job.started_at

        return job

    async def complete_job(self, job_id: str, result: MigrationJobResult) -> MigrationJob | None:
        """Mark a job as completed with results."""
        job = self._jobs.get(job_id)
        if not job:
            return None
        job.status = MigrationJobStatus.COMPLETED
        job.completed_at = datetime.now(UTC)
        self._results[job_id] = result
        return job

    async def fail_job(self, job_id: str, error_message: str) -> MigrationJob | None:
        """Mark a job as failed."""
        job = self._jobs.get(job_id)
        if not job:
            return None
        job.status = MigrationJobStatus.FAILED
        job.error_message = error_message
        job.completed_at = datetime.now(UTC)
        return job

    async def get_result(self, job_id: str, tenant_id: str) -> MigrationJobResult | None:
        """Get results for a completed job."""
        job = await self.get_job(job_id, tenant_id)
        if not job or job.status != MigrationJobStatus.COMPLETED:
            return None
        return self._results.get(job_id)


class ProgressCalculator:
    """Calculates progress and ETA for migration jobs."""

    def __init__(self, constitutional_hash: str = CONSTITUTIONAL_HASH):
        self.constitutional_hash = constitutional_hash
        self._history: dict[str, list[tuple[datetime, int]]] = {}

    def record_progress(self, job_id: str, processed: int) -> None:
        """Record a progress point for ETA calculation."""
        if job_id not in self._history:
            self._history[job_id] = []
        self._history[job_id].append((datetime.now(UTC), processed))
        # Keep only last 100 points
        self._history[job_id] = self._history[job_id][-100:]

    def calculate_eta(self, job_id: str, total: int) -> datetime | None:
        """Calculate estimated completion time."""
        history = self._history.get(job_id, [])
        if len(history) < 2:
            return None

        # Calculate rate from last few data points
        recent = history[-10:]
        if len(recent) < 2:
            return None

        time_diff = (recent[-1][0] - recent[0][0]).total_seconds()
        items_diff = recent[-1][1] - recent[0][1]

        if time_diff <= 0 or items_diff <= 0:
            return None

        rate = items_diff / time_diff
        remaining = total - recent[-1][1]

        if rate <= 0:
            return None

        seconds_remaining = remaining / rate
        return datetime.now(UTC) + timedelta(seconds=seconds_remaining)

    def get_processing_rate(self, job_id: str) -> float | None:
        """Get current processing rate (items/second)."""
        history = self._history.get(job_id, [])
        if len(history) < 2:
            return None

        recent = history[-10:]
        time_diff = (recent[-1][0] - recent[0][0]).total_seconds()
        items_diff = recent[-1][1] - recent[0][1]

        if time_diff <= 0:
            return None

        return items_diff / time_diff


class PDFReportGenerator:
    """Generates PDF reports for migration results."""

    def __init__(self, constitutional_hash: str = CONSTITUTIONAL_HASH):
        self.constitutional_hash = constitutional_hash

    async def generate_report(self, result: MigrationJobResult) -> PDFReport:
        """Generate a PDF report from migration results."""
        # Simulate PDF generation (in real impl, use reportlab or similar)
        content = self._create_pdf_content(result)

        filename = (
            f"migration_report_{result.job_id}_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.pdf"
        )

        return PDFReport(
            job_id=result.job_id,
            tenant_id=result.tenant_id,
            filename=filename,
            content_bytes=content,
            constitutional_hash=self.constitutional_hash,
        )

    def _create_pdf_content(self, result: MigrationJobResult) -> bytes:
        """Create PDF content (simplified for testing)."""
        # In real implementation, use reportlab or weasyprint
        content = f"""
%PDF-1.4
Migration Report
================
Job ID: {result.job_id}
Tenant ID: {result.tenant_id}
Status: {result.status.value}
Constitutional Hash: {result.constitutional_hash}

Summary:
{result.summary}

Warnings: {len(result.warnings)}
Errors: {len(result.errors)}
Details: {len(result.details)} items

Generated at: {result.report_generated_at.isoformat()}
%%EOF
"""
        return content.encode("utf-8")


class AsyncTaskQueue:
    """Async task queue for background job processing."""

    def __init__(self, max_workers: int = 4, constitutional_hash: str = CONSTITUTIONAL_HASH):
        self.max_workers = max_workers
        self.constitutional_hash = constitutional_hash
        self._queue: asyncio.Queue = asyncio.Queue()
        self._workers: list[asyncio.Task] = []
        self._running = False
        self._results: JSONDict = {}

    async def start(self) -> None:
        """Start the task queue workers."""
        self._running = True
        for i in range(self.max_workers):
            worker = asyncio.create_task(self._worker(i))
            self._workers.append(worker)

    async def stop(self) -> None:
        """Stop the task queue workers."""
        self._running = False
        # Add sentinel values to unblock workers
        for _ in self._workers:
            await self._queue.put(None)
        # Wait for workers to finish
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

    async def enqueue(self, job_id: str, task_func: Callable, *args, **kwargs) -> None:
        """Add a task to the queue."""
        await self._queue.put((job_id, task_func, args, kwargs))

    async def _worker(self, worker_id: int) -> None:
        """Worker coroutine that processes tasks."""
        while self._running:
            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                if item is None:
                    break

                job_id, task_func, args, kwargs = item
                try:
                    if inspect.iscoroutinefunction(task_func):
                        result = await task_func(*args, **kwargs)
                    else:
                        result = task_func(*args, **kwargs)
                    self._results[job_id] = {"status": "success", "result": result}
                except JOB_WORKER_EXECUTION_ERRORS as e:
                    self._results[job_id] = {"status": "error", "error": str(e)}
                finally:
                    self._queue.task_done()
            except TimeoutError:
                continue

    def get_result(self, job_id: str) -> dict | None:
        """Get the result of a completed task."""
        return self._results.get(job_id)  # type: ignore[no-any-return]

    @property
    def queue_size(self) -> int:
        """Get current queue size."""
        return self._queue.qsize()


class MigrationJobAPI:
    """API endpoints for migration job management."""

    def __init__(
        self,
        job_manager: MigrationJobManager,
        task_queue: AsyncTaskQueue,
        pdf_generator: PDFReportGenerator,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
    ):
        self.job_manager = job_manager
        self.task_queue = task_queue
        self.pdf_generator = pdf_generator
        self.constitutional_hash = constitutional_hash

    async def create_migration(
        self,
        tenant_id: str,
        job_type: MigrationJobType,
        source_config: dict,
        target_config: dict,
        options: dict | None = None,
    ) -> dict:
        """POST /tenants/{tenant_id}/migrations"""
        config = MigrationJobConfig(
            job_type=job_type,
            source_config=source_config,
            target_config=target_config,
            options=options or {},
            constitutional_hash=self.constitutional_hash,
        )
        job = await self.job_manager.create_job(tenant_id, config)
        return {
            "job_id": job.job_id,
            "status": job.status.value,
            "created_at": job.created_at.isoformat(),
            "constitutional_hash": job.constitutional_hash,
        }

    async def get_migration(self, tenant_id: str, job_id: str) -> dict | None:
        """GET /tenants/{tenant_id}/migrations/{job_id}"""
        job = await self.job_manager.get_job(job_id, tenant_id)
        if not job:
            return None
        return {
            "job_id": job.job_id,
            "tenant_id": job.tenant_id,
            "status": job.status.value,
            "progress": {
                "percentage": job.progress.percentage_complete,
                "processed": job.progress.processed_items,
                "total": job.progress.total_items,
                "phase": job.progress.current_phase,
                "eta_seconds": job.progress.estimated_remaining_seconds,
            },
            "created_at": job.created_at.isoformat(),
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "constitutional_hash": job.constitutional_hash,
        }

    async def list_migrations(
        self, tenant_id: str, status: str | None = None, limit: int = 50, offset: int = 0
    ) -> dict:
        """GET /tenants/{tenant_id}/migrations"""
        status_enum = MigrationJobStatus(status) if status else None
        jobs = await self.job_manager.list_jobs(tenant_id, status_enum, limit, offset)
        return {
            "jobs": [
                {
                    "job_id": j.job_id,
                    "status": j.status.value,
                    "type": j.config.job_type.value,
                    "created_at": j.created_at.isoformat(),
                }
                for j in jobs
            ],
            "total": len(jobs),
            "limit": limit,
            "offset": offset,
            "constitutional_hash": self.constitutional_hash,
        }

    async def cancel_migration(self, tenant_id: str, job_id: str) -> dict | None:
        """DELETE /tenants/{tenant_id}/migrations/{job_id}"""
        job = await self.job_manager.cancel_job(job_id, tenant_id)
        if not job:
            return None
        return {
            "job_id": job.job_id,
            "status": job.status.value,
            "cancelled_at": job.completed_at.isoformat() if job.completed_at else None,
            "constitutional_hash": job.constitutional_hash,
        }

    async def get_migration_results(
        self, tenant_id: str, job_id: str, format: ReportFormat = ReportFormat.JSON
    ) -> dict | None:
        """GET /tenants/{tenant_id}/migrations/{job_id}/results"""
        result = await self.job_manager.get_result(job_id, tenant_id)
        if not result:
            return None

        if format == ReportFormat.PDF:
            pdf = await self.pdf_generator.generate_report(result)
            return {
                "format": "pdf",
                "filename": pdf.filename,
                "content_base64": pdf.content_bytes.decode("utf-8", errors="replace"),
                "constitutional_hash": pdf.constitutional_hash,
            }

        return {
            "format": "json",
            "job_id": result.job_id,
            "status": result.status.value,
            "summary": result.summary,
            "warnings": result.warnings,
            "errors": result.errors,
            "details_count": len(result.details),
            "constitutional_hash": result.constitutional_hash,
        }
