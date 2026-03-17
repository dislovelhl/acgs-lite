"""
ACGS-2 Enhanced Agent Bus - Constitutional Version History Service
Constitutional Hash: cdd01ef066bc6cf2

Service to track all constitutional versions with pagination, filtering,
and audit trail export capabilities.
"""

import csv
from datetime import UTC, datetime, timezone
from io import StringIO
from typing import Optional

from pydantic import BaseModel, Field

from enhanced_agent_bus.observability.structured_logging import get_logger

# Import centralized constitutional hash
try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH
except ImportError:
    # Fallback for standalone usage
    from src.core.shared.constants import CONSTITUTIONAL_HASH

from src.core.shared.json_utils import dumps as json_dumps
from src.core.shared.types import JSONDict

from .storage import ConstitutionalStorageService  # type: ignore[attr-defined]
from .version_model import ConstitutionalStatus, ConstitutionalVersion

logger = get_logger(__name__)


class VersionHistoryQuery(BaseModel):
    """Query parameters for version history listing.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    limit: int = Field(default=50, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)
    status: ConstitutionalStatus | None = Field(None)
    from_date: datetime | None = Field(None)
    to_date: datetime | None = Field(None)
    include_metadata: bool = Field(default=True)
    sort_order: str = Field(default="desc", pattern="^(asc|desc)$")


class VersionHistorySummary(BaseModel):
    """Summary statistics for version history.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    total_versions: int = Field(default=0)
    active_version: str | None = Field(None)
    total_amendments: int = Field(default=0)
    rollback_count: int = Field(default=0)
    rejection_count: int = Field(default=0)
    latest_version: str | None = Field(None)
    earliest_version: str | None = Field(None)
    version_statuses: dict[str, int] = Field(default_factory=dict)


class VersionHistoryService:
    """Constitutional version history service.

    This service provides:
    - list all constitutional versions with pagination and filtering
    - Get version history summary statistics
    - Export version history as audit trail (JSON, CSV)
    - Track version lineage and transitions

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def __init__(self, storage: ConstitutionalStorageService):
        """Initialize version history service.

        Args:
            storage: ConstitutionalStorageService instance for data access
        """
        self.storage = storage
        self._cache: JSONDict = {}
        self._cache_ttl = 300  # 5 minutes
        self._last_cache_update: datetime | None = None

    async def list_versions(
        self, query: VersionHistoryQuery | None = None
    ) -> list[ConstitutionalVersion]:
        """list constitutional versions with pagination and filtering.

        Args:
            query: Query parameters for filtering and pagination

        Returns:
            list of ConstitutionalVersion objects matching query
        """
        if query is None:
            query = VersionHistoryQuery(
                limit=50,
                offset=0,
                status=None,
                from_date=None,
                to_date=None,
            )

        logger.info(
            f"[{CONSTITUTIONAL_HASH}] Listing versions "
            f"(limit={query.limit}, offset={query.offset}, status={query.status})"
        )

        # Get versions from storage
        versions = await self.storage.list_versions(
            limit=query.limit,
            offset=query.offset,
            status=query.status,
        )

        # Apply date filtering if specified
        if query.from_date:
            versions = [v for v in versions if v.created_at >= query.from_date]

        if query.to_date:
            versions = [v for v in versions if v.created_at <= query.to_date]

        # Sort by creation date (default: descending)
        if query.sort_order == "asc":
            versions.sort(key=lambda v: v.created_at)
        else:
            versions.sort(key=lambda v: v.created_at, reverse=True)

        # Remove metadata if not requested
        if not query.include_metadata:
            for version in versions:
                version.metadata = {}

        logger.info(f"[{CONSTITUTIONAL_HASH}] Found {len(versions)} versions")

        return list(versions)  # type: ignore[return-value]

    async def get_version_lineage(self, version_id: str) -> list[ConstitutionalVersion]:
        """Get the complete lineage (history) of a version.

        Traces back through predecessor_version to get full history.

        Args:
            version_id: Version ID to trace lineage for

        Returns:
            list of ConstitutionalVersion objects in lineage (newest to oldest)
        """
        lineage: list[ConstitutionalVersion] = []
        current_id = version_id

        # Prevent infinite loops with a maximum depth
        max_depth = 1000
        depth = 0

        while current_id and depth < max_depth:
            version = await self.storage.get_version(current_id)
            if not version:
                logger.warning(f"[{CONSTITUTIONAL_HASH}] Version {current_id} not found in lineage")
                break

            lineage.append(version)
            current_id = version.predecessor_version
            depth += 1

        if depth >= max_depth:
            logger.warning(
                f"[{CONSTITUTIONAL_HASH}] Maximum lineage depth reached for {version_id}"
            )

        logger.info(
            f"[{CONSTITUTIONAL_HASH}] Version {version_id} lineage: {len(lineage)} versions"
        )

        return lineage

    async def get_summary(self) -> VersionHistorySummary:
        """Get summary statistics for version history.

        Returns:
            VersionHistorySummary with statistics
        """
        logger.info(f"[{CONSTITUTIONAL_HASH}] Computing version history summary")

        # Check cache
        if self._is_cache_valid("summary"):
            logger.debug(f"[{CONSTITUTIONAL_HASH}] Using cached summary")
            return self._cache["summary"]  # type: ignore[no-any-return]

        # Get all versions (no limit)
        all_versions = await self.storage.list_versions(limit=10000, offset=0)

        # Compute statistics
        summary = VersionHistorySummary(
            total_versions=len(all_versions),
            active_version=None,
            total_amendments=0,
            rollback_count=0,
            rejection_count=0,
            latest_version=None,
            earliest_version=None,
        )

        # Count versions by status
        status_counts: dict[str, int] = {}
        for version in all_versions:
            status_str = version.status.value
            status_counts[status_str] = status_counts.get(status_str, 0) + 1

            # Track special statuses
            if version.is_active:
                summary.active_version = version.version
            if version.is_rolled_back:
                summary.rollback_count += 1
            if version.is_rejected:
                summary.rejection_count += 1

        summary.version_statuses = status_counts

        # Get latest and earliest versions
        if all_versions:
            # Versions are already sorted by created_at desc from storage
            summary.latest_version = all_versions[0].version
            summary.earliest_version = all_versions[-1].version

        # Count active amendments (would need amendment storage integration)
        # For now, use rollback count as proxy
        summary.total_amendments = len(all_versions) - 1  # Exclude v1.0.0

        # Cache the summary
        self._cache["summary"] = summary
        self._last_cache_update = datetime.now(UTC)

        logger.info(
            f"[{CONSTITUTIONAL_HASH}] Summary computed: "
            f"{summary.total_versions} versions, {summary.total_amendments} amendments"
        )

        return summary

    async def export_audit_trail(
        self, format: str = "json", query: VersionHistoryQuery | None = None
    ) -> str:
        """Export version history as audit trail.

        Args:
            format: Export format ("json" or "csv")
            query: Optional query to filter versions

        Returns:
            Exported data as string (JSON or CSV)

        Raises:
            ValueError: If format is not supported
        """
        if format not in ("json", "csv"):
            raise ValueError(f"Unsupported export format: {format}")

        logger.info(f"[{CONSTITUTIONAL_HASH}] Exporting audit trail (format={format})")

        # Get versions
        versions = await self.list_versions(query)

        if format == "json":
            return await self._export_json(versions)
        else:
            return await self._export_csv(versions)

    async def _export_json(self, versions: list[ConstitutionalVersion]) -> str:
        """Export versions as JSON.

        Args:
            versions: list of versions to export

        Returns:
            JSON string
        """
        audit_trail = {
            "constitutional_hash": CONSTITUTIONAL_HASH,
            "exported_at": datetime.now(UTC).isoformat(),
            "total_versions": len(versions),
            "versions": [
                {
                    "version_id": v.version_id,
                    "version": v.version,
                    "constitutional_hash": v.constitutional_hash,
                    "status": v.status.value,
                    "predecessor_version": v.predecessor_version,
                    "created_at": v.created_at.isoformat(),
                    "activated_at": v.activated_at.isoformat() if v.activated_at else None,
                    "deactivated_at": v.deactivated_at.isoformat() if v.deactivated_at else None,
                    "metadata": v.metadata,
                    # Include key content fields for audit purposes
                    "content_summary": {
                        "keys": list(v.content.keys()) if v.content else [],
                        "size": len(json_dumps(v.content)) if v.content else 0,
                    },
                }
                for v in versions
            ],
        }

        return str(json_dumps(audit_trail, indent=2))

    async def _export_csv(self, versions: list[ConstitutionalVersion]) -> str:
        """Export versions as CSV.

        Args:
            versions: list of versions to export

        Returns:
            CSV string
        """
        output = StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow(
            [
                "version_id",
                "version",
                "constitutional_hash",
                "status",
                "predecessor_version",
                "created_at",
                "activated_at",
                "deactivated_at",
                "content_keys",
                "content_size_bytes",
            ]
        )

        # Write data rows
        for v in versions:
            writer.writerow(
                [
                    v.version_id,
                    v.version,
                    v.constitutional_hash,
                    v.status.value,
                    v.predecessor_version or "",
                    v.created_at.isoformat(),
                    v.activated_at.isoformat() if v.activated_at else "",
                    v.deactivated_at.isoformat() if v.deactivated_at else "",
                    ",".join(v.content.keys()) if v.content else "",
                    len(json_dumps(v.content)) if v.content else 0,
                ]
            )

        return output.getvalue()

    async def get_version_by_semver(self, version: str) -> ConstitutionalVersion | None:
        """Get a version by its semantic version string.

        Args:
            version: Semantic version string (e.g., "1.0.0")

        Returns:
            ConstitutionalVersion or None if not found
        """
        logger.info(f"[{CONSTITUTIONAL_HASH}] Looking up version by semver: {version}")

        # Get all versions (could optimize with DB query in the future)
        versions = await self.storage.list_versions(limit=10000, offset=0)

        for v in versions:
            if v.version == version:
                logger.info(f"[{CONSTITUTIONAL_HASH}] Found version {version}: {v.version_id}")
                return v  # type: ignore[no-any-return]

        logger.warning(f"[{CONSTITUTIONAL_HASH}] Version {version} not found")
        return None

    async def get_transition_history(self) -> list[JSONDict]:
        """Get history of version transitions (activations/deactivations).

        Returns:
            list of transition events with timestamps and details
        """
        logger.info(f"[{CONSTITUTIONAL_HASH}] Computing version transition history")

        # Get all versions
        versions = await self.storage.list_versions(limit=10000, offset=0)

        transitions: list[JSONDict] = []

        for version in versions:
            # Add activation event
            if version.activated_at:
                transitions.append(
                    {
                        "event": "activated",
                        "version_id": version.version_id,
                        "version": version.version,
                        "timestamp": version.activated_at.isoformat(),
                        "constitutional_hash": version.constitutional_hash,
                    }
                )

            # Add deactivation event
            if version.deactivated_at:
                transitions.append(
                    {
                        "event": "deactivated",
                        "version_id": version.version_id,
                        "version": version.version,
                        "timestamp": version.deactivated_at.isoformat(),
                        "status": version.status.value,
                        "constitutional_hash": version.constitutional_hash,
                    }
                )

        # Sort by timestamp
        transitions.sort(key=lambda t: t["timestamp"])

        logger.info(f"[{CONSTITUTIONAL_HASH}] Found {len(transitions)} version transitions")

        return transitions

    def _is_cache_valid(self, key: str) -> bool:
        """Check if cached value is still valid.

        Args:
            key: Cache key to check

        Returns:
            True if cache is valid, False otherwise
        """
        if key not in self._cache:
            return False

        if not self._last_cache_update:
            return False

        elapsed = (datetime.now(UTC) - self._last_cache_update).total_seconds()
        return elapsed < self._cache_ttl

    def clear_cache(self) -> None:
        """Clear all cached data."""
        self._cache.clear()
        self._last_cache_update = None
        logger.info(f"[{CONSTITUTIONAL_HASH}] Version history cache cleared")
