"""Structured incident lifecycle for governance violations.

Tracks governance incidents from detection through triage, containment,
resolution, and post-mortem — with severity-based escalation, assignee
management, timeline reconstruction, and incident metrics.

Example::

    from acgs_lite.constitution.incident import (
        IncidentManager, IncidentSeverity, IncidentPhase,
    )

    mgr = IncidentManager()
    inc = mgr.create(
        title="Unauthorized self-validation detected",
        severity=IncidentSeverity.CRITICAL,
        source="maci_enforcer",
    )
    mgr.assign(inc.incident_id, assignee="security-team")
    mgr.transition(inc.incident_id, IncidentPhase.CONTAINED)
    mgr.add_note(inc.incident_id, "Blocked agent access pending review")
    mgr.transition(inc.incident_id, IncidentPhase.RESOLVED, resolution="Agent permissions revoked")
    report = mgr.incident_report(inc.incident_id)
"""

from __future__ import annotations

import enum
import time
import uuid
from dataclasses import dataclass, field


class IncidentSeverity(enum.IntEnum):
    LOW = 0
    MEDIUM = 1
    HIGH = 2
    CRITICAL = 3


class IncidentPhase(str, enum.Enum):
    DETECTED = "detected"
    TRIAGED = "triaged"
    CONTAINED = "contained"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"
    POST_MORTEM = "post_mortem"
    CLOSED = "closed"


_VALID_TRANSITIONS: dict[IncidentPhase, set[IncidentPhase]] = {
    IncidentPhase.DETECTED: {IncidentPhase.TRIAGED, IncidentPhase.CONTAINED},
    IncidentPhase.TRIAGED: {IncidentPhase.CONTAINED, IncidentPhase.INVESTIGATING},
    IncidentPhase.CONTAINED: {IncidentPhase.INVESTIGATING, IncidentPhase.RESOLVED},
    IncidentPhase.INVESTIGATING: {IncidentPhase.CONTAINED, IncidentPhase.RESOLVED},
    IncidentPhase.RESOLVED: {IncidentPhase.POST_MORTEM, IncidentPhase.CLOSED},
    IncidentPhase.POST_MORTEM: {IncidentPhase.CLOSED},
    IncidentPhase.CLOSED: set(),
}


@dataclass
class TimelineEntry:
    """Single event in an incident's timeline."""

    timestamp: float
    phase: IncidentPhase
    actor: str
    note: str = ""


@dataclass
class Incident:
    """A governance incident with full lifecycle state."""

    incident_id: str
    title: str
    severity: IncidentSeverity
    source: str
    phase: IncidentPhase = IncidentPhase.DETECTED
    assignee: str = ""
    resolution: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    closed_at: float | None = None
    timeline: list[TimelineEntry] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    related_artifact_ids: list[str] = field(default_factory=list)


class IncidentManager:
    """Manage governance incident lifecycles.

    Enforces valid phase transitions, tracks timeline events, supports
    assignment, tagging, artifact linking, and generates incident reports
    with duration metrics.

    Example::

        mgr = IncidentManager()
        inc = mgr.create("MACI violation", IncidentSeverity.HIGH, source="audit")
        mgr.transition(inc.incident_id, IncidentPhase.TRIAGED)
        mgr.transition(inc.incident_id, IncidentPhase.CONTAINED)
        mgr.transition(inc.incident_id, IncidentPhase.RESOLVED, resolution="Fixed")
        open_incidents = mgr.query_open()
    """

    def __init__(self) -> None:
        self._incidents: dict[str, Incident] = {}

    def create(
        self,
        title: str,
        severity: IncidentSeverity,
        source: str = "",
        tags: list[str] | None = None,
        related_artifact_ids: list[str] | None = None,
    ) -> Incident:
        incident_id = f"INC-{uuid.uuid4().hex[:12]}"
        now = time.time()
        incident = Incident(
            incident_id=incident_id,
            title=title,
            severity=severity,
            source=source,
            created_at=now,
            updated_at=now,
            tags=tags or [],
            related_artifact_ids=related_artifact_ids or [],
            timeline=[
                TimelineEntry(
                    timestamp=now,
                    phase=IncidentPhase.DETECTED,
                    actor="system",
                    note=f"Incident created: {title}",
                )
            ],
        )
        self._incidents[incident_id] = incident
        return incident

    def get(self, incident_id: str) -> Incident | None:
        return self._incidents.get(incident_id)

    def transition(
        self,
        incident_id: str,
        target_phase: IncidentPhase,
        actor: str = "system",
        resolution: str = "",
        note: str = "",
    ) -> bool:
        """Advance an incident to *target_phase* if the transition is valid."""
        incident = self._incidents.get(incident_id)
        if incident is None:
            return False
        valid_targets = _VALID_TRANSITIONS.get(incident.phase, set())
        if target_phase not in valid_targets:
            return False

        now = time.time()
        incident.phase = target_phase
        incident.updated_at = now

        if resolution:
            incident.resolution = resolution
        if target_phase == IncidentPhase.CLOSED:
            incident.closed_at = now

        incident.timeline.append(
            TimelineEntry(
                timestamp=now,
                phase=target_phase,
                actor=actor,
                note=note or f"Transitioned to {target_phase.value}",
            )
        )
        return True

    def assign(self, incident_id: str, assignee: str) -> bool:
        incident = self._incidents.get(incident_id)
        if incident is None:
            return False
        incident.assignee = assignee
        incident.updated_at = time.time()
        return True

    def add_note(self, incident_id: str, note: str, actor: str = "system") -> bool:
        incident = self._incidents.get(incident_id)
        if incident is None:
            return False
        incident.timeline.append(
            TimelineEntry(
                timestamp=time.time(),
                phase=incident.phase,
                actor=actor,
                note=note,
            )
        )
        incident.updated_at = time.time()
        return True

    def add_tag(self, incident_id: str, tag: str) -> bool:
        incident = self._incidents.get(incident_id)
        if incident is None:
            return False
        if tag not in incident.tags:
            incident.tags.append(tag)
        return True

    def link_artifact(self, incident_id: str, artifact_id: str) -> bool:
        incident = self._incidents.get(incident_id)
        if incident is None:
            return False
        if artifact_id not in incident.related_artifact_ids:
            incident.related_artifact_ids.append(artifact_id)
        return True

    def escalate(self, incident_id: str, new_severity: IncidentSeverity) -> bool:
        """Raise an incident's severity (only upward escalation allowed)."""
        incident = self._incidents.get(incident_id)
        if incident is None:
            return False
        if new_severity <= incident.severity:
            return False
        old = incident.severity
        incident.severity = new_severity
        incident.updated_at = time.time()
        incident.timeline.append(
            TimelineEntry(
                timestamp=time.time(),
                phase=incident.phase,
                actor="system",
                note=f"Escalated from {old.name} to {new_severity.name}",
            )
        )
        return True

    def query_open(self) -> list[Incident]:
        closed = {IncidentPhase.RESOLVED, IncidentPhase.POST_MORTEM, IncidentPhase.CLOSED}
        return [i for i in self._incidents.values() if i.phase not in closed]

    def query_by_severity(self, min_severity: IncidentSeverity) -> list[Incident]:
        return [i for i in self._incidents.values() if i.severity >= min_severity]

    def query_by_phase(self, phase: IncidentPhase) -> list[Incident]:
        return [i for i in self._incidents.values() if i.phase == phase]

    def query_by_source(self, source: str) -> list[Incident]:
        return [i for i in self._incidents.values() if i.source == source]

    def incident_report(self, incident_id: str) -> dict[str, object] | None:
        """Generate a structured report for a single incident."""
        incident = self._incidents.get(incident_id)
        if incident is None:
            return None

        duration_seconds: float | None = None
        if incident.closed_at is not None:
            duration_seconds = incident.closed_at - incident.created_at
        elif incident.phase != IncidentPhase.DETECTED:
            duration_seconds = time.time() - incident.created_at

        time_to_contain: float | None = None
        for entry in incident.timeline:
            if entry.phase == IncidentPhase.CONTAINED:
                time_to_contain = entry.timestamp - incident.created_at
                break

        return {
            "incident_id": incident.incident_id,
            "title": incident.title,
            "severity": incident.severity.name,
            "phase": incident.phase.value,
            "source": incident.source,
            "assignee": incident.assignee,
            "resolution": incident.resolution,
            "duration_seconds": duration_seconds,
            "time_to_contain_seconds": time_to_contain,
            "timeline_entries": len(incident.timeline),
            "tags": incident.tags,
            "related_artifacts": incident.related_artifact_ids,
        }

    def summary(self) -> dict[str, object]:
        """Dashboard summary across all incidents."""
        by_phase: dict[str, int] = {}
        by_severity: dict[str, int] = {}
        for inc in self._incidents.values():
            by_phase[inc.phase.value] = by_phase.get(inc.phase.value, 0) + 1
            by_severity[inc.severity.name] = by_severity.get(inc.severity.name, 0) + 1
        return {
            "total": len(self._incidents),
            "open": len(self.query_open()),
            "by_phase": by_phase,
            "by_severity": by_severity,
        }
