"""Dataset snapshot builder for flywheel replay and evaluation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

try:
    import redis.asyncio as redis_asyncio
except ImportError:
    redis_asyncio = None  # type: ignore[assignment]

from enhanced_agent_bus.persistence.repository import WorkflowRepository

from .models import DatasetSnapshot, DecisionEvent, FeedbackEvent
from .redaction import contains_unredacted_pii, redact_for_dataset_export


class FlywheelDatasetError(RuntimeError):
    """Base error for dataset builder failures."""


class CrossTenantDatasetError(FlywheelDatasetError):
    """Raised when dataset assembly attempts to mix tenants."""


class MixedConstitutionalHashError(FlywheelDatasetError):
    """Raised when dataset assembly attempts to mix constitutional hashes."""


class UnredactedDatasetError(FlywheelDatasetError):
    """Raised when an export still contains obvious PII after redaction."""


class FeedbackEventSource(Protocol):
    async def list_feedback_events(
        self,
        tenant_id: str,
        workload_key: str | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[FeedbackEvent]:
        """List normalized feedback events for flywheel dataset assembly."""


@dataclass(slots=True)
class InMemoryFeedbackEventSource:
    events: list[FeedbackEvent]

    async def list_feedback_events(
        self,
        tenant_id: str,
        workload_key: str | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[FeedbackEvent]:
        events = [event for event in self.events if event.tenant_id == tenant_id]
        if workload_key is not None:
            events = [event for event in events if event.workload_key == workload_key]
        events.sort(key=lambda item: item.created_at, reverse=True)
        return events[offset : offset + limit]


class RedisFeedbackEventSource:
    """Read normalized gateway feedback events from the Redis feedback store."""

    def __init__(self, redis_url: str, *, key_prefix: str = "acgs:feedback:") -> None:
        if redis_asyncio is None:
            raise ImportError("redis is required to read flywheel feedback events")
        self._redis_url = redis_url
        self._key_prefix = key_prefix
        self._client: redis_asyncio.Redis | None = None

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def list_feedback_events(
        self,
        tenant_id: str,
        workload_key: str | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[FeedbackEvent]:
        client = await self._get_client()
        events: list[FeedbackEvent] = []
        async for key in client.scan_iter(match=f"{self._key_prefix}*"):
            payload = await client.get(key)
            if not payload:
                continue
            parsed = json.loads(payload)
            normalized = parsed.get("flywheel_feedback_event")
            if not isinstance(normalized, dict):
                continue
            event = FeedbackEvent.model_validate(normalized)
            if event.tenant_id != tenant_id:
                continue
            if workload_key is not None and event.workload_key != workload_key:
                continue
            events.append(event)
        events.sort(key=lambda item: item.created_at, reverse=True)
        return events[offset : offset + limit]

    async def _get_client(self) -> redis_asyncio.Redis:
        if self._client is None:
            self._client = redis_asyncio.from_url(self._redis_url, decode_responses=True)
        return self._client


class DatasetSnapshotBuilder:
    """Assemble tenant-scoped, redacted flywheel datasets."""

    def __init__(
        self,
        repository: WorkflowRepository,
        feedback_source: FeedbackEventSource,
        *,
        artifact_root: str | Path,
    ) -> None:
        self._repository = repository
        self._feedback_source = feedback_source
        self._artifact_root = Path(artifact_root)

    async def build_snapshot(
        self,
        *,
        tenant_id: str,
        workload_key: str,
        limit: int = 1000,
        decision_events: list[DecisionEvent] | None = None,
        feedback_events: list[FeedbackEvent] | None = None,
    ) -> DatasetSnapshot:
        decisions = decision_events
        if decisions is None:
            decisions = await self._repository.list_decision_events(
                tenant_id,
                workload_key=workload_key,
                limit=limit,
            )
        feedback = feedback_events
        if feedback is None:
            feedback = await self._feedback_source.list_feedback_events(
                tenant_id,
                workload_key=workload_key,
                limit=limit,
            )

        all_events = [*decisions, *feedback]
        constitutional_hash = self._resolve_constitutional_hash(workload_key, all_events)
        self._assert_dataset_isolation(
            tenant_id=tenant_id,
            workload_key=workload_key,
            constitutional_hash=constitutional_hash,
            decision_events=decisions,
            feedback_events=feedback,
        )
        records = self._build_records(decisions, feedback)

        snapshot = DatasetSnapshot(
            tenant_id=tenant_id,
            workload_key=workload_key,
            constitutional_hash=constitutional_hash,
            record_count=len(records),
            redaction_status="redacted",
            artifact_manifest_uri="pending",
            window_started_at=min((event.created_at for event in all_events), default=None),
            window_ended_at=max((event.created_at for event in all_events), default=None),
            source_counts={
                "decision_events": len(decisions),
                "feedback_events": len(feedback),
            },
        )
        manifest_uri = await self._write_snapshot_artifacts(snapshot=snapshot, records=records)
        snapshot = snapshot.model_copy(update={"artifact_manifest_uri": manifest_uri})
        await self._repository.save_dataset_snapshot(snapshot)
        return snapshot

    def _assert_dataset_isolation(
        self,
        *,
        tenant_id: str,
        workload_key: str,
        constitutional_hash: str,
        decision_events: list[DecisionEvent],
        feedback_events: list[FeedbackEvent],
    ) -> None:
        for event in [*decision_events, *feedback_events]:
            if event.tenant_id != tenant_id:
                raise CrossTenantDatasetError(
                    f"dataset assembly crossed tenant boundary: {event.tenant_id!r} != {tenant_id!r}"
                )
            if event.workload_key != workload_key:
                raise FlywheelDatasetError(
                    f"dataset assembly crossed workload boundary: {event.workload_key!r}"
                )
            if event.constitutional_hash != constitutional_hash:
                raise MixedConstitutionalHashError(
                    "dataset assembly crossed constitutional hash boundary"
                )

    def _build_records(
        self,
        decision_events: list[DecisionEvent],
        feedback_events: list[FeedbackEvent],
    ) -> list[dict[str, object]]:
        records: list[dict[str, object]] = []
        for event in sorted(decision_events, key=lambda item: item.created_at):
            redacted = redact_for_dataset_export(event.model_dump(mode="json"))
            if contains_unredacted_pii(redacted):
                raise UnredactedDatasetError("decision event export still contains PII")
            records.append({"record_type": "decision_event", "record": redacted})
        for event in sorted(feedback_events, key=lambda item: item.created_at):
            redacted = redact_for_dataset_export(event.model_dump(mode="json"))
            if contains_unredacted_pii(redacted):
                raise UnredactedDatasetError("feedback event export still contains PII")
            records.append({"record_type": "feedback_event", "record": redacted})
        return records

    async def _write_snapshot_artifacts(
        self,
        *,
        snapshot: DatasetSnapshot,
        records: list[dict[str, object]],
    ) -> str:
        snapshot_dir = self._artifact_root.resolve() / snapshot.tenant_id / snapshot.snapshot_id
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        dataset_path = snapshot_dir / "records.jsonl"
        manifest_path = snapshot_dir / "manifest.json"
        with dataset_path.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, separators=(",", ":"), default=_json_default))
                handle.write("\n")
        manifest = {
            "snapshot_id": snapshot.snapshot_id,
            "tenant_id": snapshot.tenant_id,
            "workload_key": snapshot.workload_key,
            "constitutional_hash": snapshot.constitutional_hash,
            "record_count": snapshot.record_count,
            "redaction_status": snapshot.redaction_status,
            "source_counts": snapshot.source_counts,
            "window_started_at": _datetime_to_iso(snapshot.window_started_at),
            "window_ended_at": _datetime_to_iso(snapshot.window_ended_at),
            "dataset_uri": dataset_path.as_uri(),
            "created_at": snapshot.created_at.isoformat(),
        }
        with manifest_path.open("w", encoding="utf-8") as handle:
            json.dump(manifest, handle, separators=(",", ":"), default=_json_default)
        return manifest_path.as_uri()

    @staticmethod
    def _resolve_constitutional_hash(
        workload_key: str, events: list[DecisionEvent | FeedbackEvent]
    ) -> str:
        if events:
            hashes = {event.constitutional_hash for event in events}
            if len(hashes) > 1:
                raise MixedConstitutionalHashError(
                    "dataset assembly crossed constitutional hash boundary"
                )
            return next(iter(hashes))
        segments = workload_key.split("/")
        return segments[-1] if segments else ""


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _datetime_to_iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


__all__ = [
    "CrossTenantDatasetError",
    "DatasetSnapshotBuilder",
    "FeedbackEventSource",
    "FlywheelDatasetError",
    "InMemoryFeedbackEventSource",
    "MixedConstitutionalHashError",
    "RedisFeedbackEventSource",
    "UnredactedDatasetError",
]
