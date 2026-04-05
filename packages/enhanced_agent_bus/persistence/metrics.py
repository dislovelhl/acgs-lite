"""
Workflow execution metrics.

Constitutional Hash: 608508a9bd224290
"""

from enhanced_agent_bus._compat.metrics import _get_or_create_counter, _get_or_create_histogram

# Workflow metrics
WORKFLOW_STARTED_TOTAL = _get_or_create_counter(
    "durable_workflow_started_total",
    "Total number of workflows started",
    ["workflow_type", "tenant_id"],
)

WORKFLOW_COMPLETED_TOTAL = _get_or_create_counter(
    "durable_workflow_completed_total",
    "Total number of workflows completed successfully",
    ["workflow_type", "tenant_id"],
)

WORKFLOW_FAILED_TOTAL = _get_or_create_counter(
    "durable_workflow_failed_total",
    "Total number of workflows failed",
    ["workflow_type", "tenant_id"],
)

WORKFLOW_CANCELLED_TOTAL = _get_or_create_counter(
    "durable_workflow_cancelled_total",
    "Total number of workflows cancelled",
    ["workflow_type", "tenant_id"],
)

WORKFLOW_DURATION_SECONDS = _get_or_create_histogram(
    "durable_workflow_duration_seconds",
    "Duration of completed workflows",
    ["workflow_type", "tenant_id"],
)

# Step metrics
WORKFLOW_STEP_COMPLETED_TOTAL = _get_or_create_counter(
    "durable_workflow_step_completed_total",
    "Total number of workflow steps completed",
    ["workflow_type", "step_name"],
)

WORKFLOW_STEP_FAILED_TOTAL = _get_or_create_counter(
    "durable_workflow_step_failed_total",
    "Total number of workflow steps failed",
    ["workflow_type", "step_name"],
)

WORKFLOW_STEP_DURATION_SECONDS = _get_or_create_histogram(
    "durable_workflow_step_duration_seconds",
    "Duration of completed workflow steps",
    ["workflow_type", "step_name"],
)

# Compensation metrics
WORKFLOW_COMPENSATION_TOTAL = _get_or_create_counter(
    "durable_workflow_compensation_total",
    "Total number of compensations executed",
    ["workflow_type"],
)

WORKFLOW_COMPENSATION_FAILED_TOTAL = _get_or_create_counter(
    "durable_workflow_compensation_failed_total",
    "Total number of compensations failed",
    ["workflow_type"],
)
