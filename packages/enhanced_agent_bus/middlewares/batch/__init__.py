"""
Batch Processing Middleware for ACGS-2 Pipeline.

Constitutional Hash: 608508a9bd224290

This module provides specialized middleware for batch request processing:
- Validation: Batch structure and schema validation
- Tenant Isolation: Multi-tenant consistency enforcement
- Deduplication: Duplicate request detection and removal
- Governance: MACI and constitutional compliance
- Concurrency: Concurrent processing control
- Processing: Core batch item execution
- Auto-tuning: Dynamic batch size adjustment
- Metrics: Batch-level metrics collection
"""

from .auto_tune import (
    BatchAutoTuneException,
    BatchAutoTuneMiddleware,
)
from .concurrency import (
    BatchConcurrencyException,
    BatchConcurrencyMiddleware,
)
from .context import BatchPipelineContext
from .deduplication import (
    BatchDeduplicationException,
    BatchDeduplicationMiddleware,
)
from .exceptions import BatchMiddlewareException
from .governance import (
    BatchGovernanceException,
    BatchGovernanceMiddleware,
)
from .metrics import (
    BatchMetricsException,
    BatchMetricsMiddleware,
)
from .processing import (
    BatchProcessingException,
    BatchProcessingMiddleware,
)
from .tenant_isolation import (
    BatchTenantIsolationException,
    BatchTenantIsolationMiddleware,
)
from .validation import (
    BatchValidationException,
    BatchValidationMiddleware,
)

__all__ = [
    "BatchAutoTuneException",
    # Auto-tuning
    "BatchAutoTuneMiddleware",
    "BatchConcurrencyException",
    # Concurrency
    "BatchConcurrencyMiddleware",
    "BatchDeduplicationException",
    # Deduplication
    "BatchDeduplicationMiddleware",
    "BatchGovernanceException",
    # Governance
    "BatchGovernanceMiddleware",
    "BatchMetricsException",
    # Metrics
    "BatchMetricsMiddleware",
    # Base Exception
    "BatchMiddlewareException",
    # Context
    "BatchPipelineContext",
    "BatchProcessingException",
    # Processing
    "BatchProcessingMiddleware",
    "BatchTenantIsolationException",
    # Tenant Isolation
    "BatchTenantIsolationMiddleware",
    "BatchValidationException",
    # Validation
    "BatchValidationMiddleware",
]
