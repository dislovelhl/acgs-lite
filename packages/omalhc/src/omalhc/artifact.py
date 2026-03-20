"""Artifact Store — stigmergic coordination medium.

Agents interact through artifacts, not messages. The store IS the
coordination mechanism. Like how ants coordinate through pheromones,
agents coordinate through published artifacts.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class Artifact:
    """An immutable, content-addressed work product.

    Artifacts are the outputs of agent work. They are stored in the
    artifact store and can be referenced by downstream tasks.
    Content-addressed via SHA-256 for integrity verification.
    """

    artifact_id: str
    task_id: str
    agent_id: str
    content_type: str
    content: str
    domain: str = ""
    tags: tuple[str, ...] = ()
    timestamp: float = field(default_factory=time.time)
    constitutional_hash: str = ""
    parent_artifacts: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def content_hash(self) -> str:
        """SHA-256 hash of the content for integrity verification."""
        return hashlib.sha256(self.content.encode()).hexdigest()[:32]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "artifact_id": self.artifact_id,
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "content_type": self.content_type,
            "content_hash": self.content_hash,
            "domain": self.domain,
            "tags": list(self.tags),
            "timestamp": self.timestamp,
            "constitutional_hash": self.constitutional_hash,
            "parent_artifacts": list(self.parent_artifacts),
        }


class ArtifactStore:
    """In-memory artifact store for stigmergic coordination.

    Agents publish artifacts. Other agents discover and consume them.
    No direct messaging — all coordination through the store.

    In production, this would be backed by git, a database, or
    object storage. The in-memory version is for prototyping.
    """

    def __init__(self) -> None:
        self._artifacts: dict[str, Artifact] = {}
        self._by_task: dict[str, list[str]] = {}
        self._by_domain: dict[str, list[str]] = {}
        self._by_agent: dict[str, list[str]] = {}
        self._watchers: dict[str, list[Any]] = {}

    def publish(self, artifact: Artifact) -> str:
        """Publish an artifact to the store.

        Returns the artifact ID. Notifies watchers of the artifact's
        task_id and domain. Rejects duplicates.
        """
        if artifact.artifact_id in self._artifacts:
            raise ValueError(f"Artifact {artifact.artifact_id} already exists")
        self._artifacts[artifact.artifact_id] = artifact
        self._by_task.setdefault(artifact.task_id, []).append(artifact.artifact_id)
        self._by_domain.setdefault(artifact.domain, []).append(artifact.artifact_id)
        self._by_agent.setdefault(artifact.agent_id, []).append(artifact.artifact_id)
        self._notify(artifact)
        return artifact.artifact_id

    def get(self, artifact_id: str) -> Artifact | None:
        """Retrieve an artifact by ID."""
        return self._artifacts.get(artifact_id)

    def get_by_task(self, task_id: str) -> list[Artifact]:
        """Get all artifacts for a task."""
        ids = self._by_task.get(task_id, [])
        return [self._artifacts[aid] for aid in ids if aid in self._artifacts]

    def get_by_domain(self, domain: str) -> list[Artifact]:
        """Get all artifacts in a domain."""
        ids = self._by_domain.get(domain, [])
        return [self._artifacts[aid] for aid in ids if aid in self._artifacts]

    def get_by_agent(self, agent_id: str) -> list[Artifact]:
        """Get all artifacts produced by an agent."""
        ids = self._by_agent.get(agent_id, [])
        return [self._artifacts[aid] for aid in ids if aid in self._artifacts]

    def watch(self, key: str, callback: Any) -> None:
        """Register a watcher for a task_id or domain.

        Callback is called when a matching artifact is published.
        """
        self._watchers.setdefault(key, []).append(callback)

    def _notify(self, artifact: Artifact) -> None:
        """Notify watchers of a new artifact."""
        for key in (artifact.task_id, artifact.domain):
            for callback in self._watchers.get(key, []):
                callback(artifact)

    def verify_integrity(self, artifact_id: str) -> bool:
        """Verify an artifact's content hash hasn't been tampered with."""
        artifact = self._artifacts.get(artifact_id)
        if artifact is None:
            return False
        expected = hashlib.sha256(artifact.content.encode()).hexdigest()[:32]
        return artifact.content_hash == expected

    @property
    def count(self) -> int:
        """Total number of artifacts in the store."""
        return len(self._artifacts)

    def summary(self) -> dict[str, Any]:
        """Store summary statistics."""
        return {
            "total_artifacts": self.count,
            "domains": len(self._by_domain),
            "agents": len(self._by_agent),
            "tasks": len(self._by_task),
        }
