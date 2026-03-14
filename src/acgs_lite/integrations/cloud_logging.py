"""ACGS-Lite Google Cloud Logging Integration.

Exports governance audit trail entries to Google Cloud Logging as structured
log entries with governance-specific labels for querying and alerting.

Usage::

    from acgs_lite.integrations.cloud_logging import CloudLoggingAuditExporter
    from acgs_lite.audit import AuditEntry

    exporter = CloudLoggingAuditExporter(project_id="my-project")
    exporter.export_entry(audit_entry)
    exporter.export_batch([entry1, entry2, entry3])

Constitutional Hash: cdd01ef066bc6cf2
"""

from __future__ import annotations

import logging
from typing import Any

from acgs_lite.audit import AuditEntry

logger = logging.getLogger(__name__)

try:
    import google.cloud.logging as cloud_logging
    from google.cloud.logging_v2.entries import StructEntry

    CLOUD_LOGGING_AVAILABLE = True
except ImportError:
    CLOUD_LOGGING_AVAILABLE = False
    cloud_logging = None  # type: ignore[assignment]
    StructEntry = None  # type: ignore[assignment,misc]

_LOG_NAME = "acgs-lite-governance"


def _build_labels(entry: AuditEntry) -> dict[str, str]:
    """Build Cloud Logging labels from an audit entry.

    Labels are indexed for fast filtering in Cloud Logging queries.

    Args:
        entry: The audit entry to extract labels from.

    Returns:
        Dict of string labels suitable for Cloud Logging.
    """
    labels: dict[str, str] = {
        "agent_id": entry.agent_id or "unknown",
        "entry_type": entry.type,
        "valid": str(entry.valid).lower(),
    }

    if entry.constitutional_hash:
        labels["constitutional_hash"] = entry.constitutional_hash

    # Extract rule_id and severity from violations if present
    if entry.violations:
        labels["rule_ids"] = ",".join(entry.violations[:10])

    # Extract severity and decision from metadata if available
    metadata = entry.metadata or {}
    if "severity" in metadata:
        labels["severity"] = str(metadata["severity"])
    if "decision" in metadata:
        labels["decision"] = str(metadata["decision"])
    if "risk_score" in metadata:
        labels["risk_score"] = str(metadata["risk_score"])

    return labels


def _severity_to_cloud_severity(entry: AuditEntry) -> str:
    """Map audit entry state to Cloud Logging severity.

    Args:
        entry: The audit entry to determine severity for.

    Returns:
        Cloud Logging severity string (DEFAULT, INFO, WARNING, ERROR, CRITICAL).
    """
    if not entry.valid and entry.violations:
        # Check metadata for severity hint
        metadata = entry.metadata or {}
        sev = str(metadata.get("severity", "")).lower()
        if sev == "critical":
            return "CRITICAL"
        if sev in ("high", "error"):
            return "ERROR"
        return "WARNING"
    if not entry.valid:
        return "WARNING"
    return "INFO"


class CloudLoggingAuditExporter:
    """Exports ACGS-Lite audit entries to Google Cloud Logging.

    Each governance decision is logged as a structured entry with labels
    for rule_id, severity, decision, and constitutional_hash. This enables
    Cloud Logging queries like::

        resource.type="cloud_run_revision"
        logName="projects/my-project/logs/acgs-lite-governance"
        labels.valid="false"

    Args:
        project_id: GCP project ID. If None, uses Application Default Credentials.
        log_name: Cloud Logging log name. Defaults to "acgs-lite-governance".
    """

    def __init__(
        self,
        *,
        project_id: str | None = None,
        log_name: str = _LOG_NAME,
    ) -> None:
        if not CLOUD_LOGGING_AVAILABLE:
            raise ImportError(
                "google-cloud-logging is required. "
                "Install with: pip install acgs-lite[google-cloud]"
            )

        self._client = cloud_logging.Client(project=project_id)  # type: ignore[union-attr]
        self._logger = self._client.logger(log_name)
        self._log_name = log_name
        self._exported_count = 0

    def export_entry(self, entry: AuditEntry) -> None:
        """Export a single audit entry to Cloud Logging.

        Args:
            entry: The AuditEntry to export as a structured log entry.
        """
        struct: dict[str, Any] = entry.to_dict()
        labels = _build_labels(entry)
        severity = _severity_to_cloud_severity(entry)

        self._logger.log_struct(
            struct,
            labels=labels,
            severity=severity,
        )
        self._exported_count += 1

        logger.debug(
            "Exported audit entry %s to Cloud Logging (severity=%s)",
            entry.id,
            severity,
        )

    def export_batch(self, entries: list[AuditEntry]) -> None:
        """Export multiple audit entries to Cloud Logging.

        Entries are written individually to preserve per-entry labels and
        severity. For high-throughput scenarios, Cloud Logging client
        batches writes internally.

        Args:
            entries: List of AuditEntry objects to export.
        """
        for entry in entries:
            try:
                self.export_entry(entry)
            except Exception:
                logger.error(
                    "Failed to export audit entry %s to Cloud Logging",
                    entry.id,
                    exc_info=True,
                )

    @property
    def exported_count(self) -> int:
        """Total number of entries successfully exported."""
        return self._exported_count

    @property
    def stats(self) -> dict[str, Any]:
        """Return exporter statistics."""
        return {
            "log_name": self._log_name,
            "exported_count": self._exported_count,
            "available": CLOUD_LOGGING_AVAILABLE,
        }
