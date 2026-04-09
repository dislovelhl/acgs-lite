# ACGS - Constitutional AI Governance
# Copyright (C) 2024-2026 ACGS Contributors
# Licensed under Apache-2.0. See LICENSE for details.
# Commercial license: https://acgs.ai

"""Observation logger for AI coding session telemetry.

Captures tool-call events from Claude Code, OpenCode, and similar agents
to enable workflow pattern analysis (deep observation pattern analysis).

Output: ~/.acgs/observations.jsonl
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_PATH_KEYS = frozenset(
    {
        "path",
        "paths",
        "file",
        "files",
        "filepath",
        "filepaths",
        "file_path",
        "file_paths",
        "input_file",
        "input_files",
        "output_file",
        "output_files",
        "input_path",
        "input_paths",
        "output_path",
        "output_paths",
        "target_path",
        "target_paths",
        "source_path",
        "source_paths",
        "destination_path",
        "destination_paths",
        "artifact_path",
        "artifact_paths",
        "cwd",
        "directory",
        "directories",
        "dir",
        "root",
        "root_dir",
    }
)


def _default_observation_file() -> Path:
    """Return the default observation log path.

    Respects ``ACGS_OBSERVATIONS_PATH`` when set, otherwise uses the
    conventional ``~/.acgs/observations.jsonl`` location.
    """
    configured = os.getenv("ACGS_OBSERVATIONS_PATH")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".acgs" / "observations.jsonl"


@dataclass(frozen=True)
class ToolObservation:
    """A single tool-call observation record.

    Matches the schema used by deep-observation-pattern-analysis:
    - tool_type: The tool invoked (bash, grep, edit, read, task, etc.)
    - timestamp: ISO 8601 UTC timestamp
    - duration_ms: How long the tool took
    - success: Whether it completed without error
    - error_type: Error class if failed (None on success)
    - error_message: Human-readable error detail
    - file_paths: Files touched or inspected
    - session_id: Which agent session this belongs to
    - observation_id: Unique record ID
    - metadata: Extra context (command length, pattern complexity, etc.)
    """

    tool_type: str
    timestamp: str
    duration_ms: float
    success: bool
    error_type: str | None = None
    error_message: str | None = None
    file_paths: list[str] = field(default_factory=list)
    session_id: str | None = None
    observation_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return the observation as a plain dict."""
        return asdict(self)

    def to_json(self) -> str:
        """Serialize to a single JSON line."""
        return json.dumps(self.to_dict(), separators=(",", ":"))

    @classmethod
    def from_json(cls, line: str) -> ToolObservation:
        """Deserialize from a JSON line."""
        data = json.loads(line)
        return cls(**data)


def extract_file_paths(*payloads: Any) -> list[str]:
    """Extract file paths from nested payloads.

    Only values under path-bearing keys are considered, which keeps the
    output focused on files that were likely touched or inspected.
    Duplicate paths are removed while preserving encounter order.
    """

    discovered: list[str] = []
    seen: set[str] = set()

    def _add_path(value: str | Path) -> None:
        path = str(value)
        if not path or path in seen:
            return
        seen.add(path)
        discovered.append(path)

    def _consume_path_value(value: Any) -> None:
        if isinstance(value, (str, Path)):
            _add_path(value)
            return
        if isinstance(value, dict):
            for nested in value.values():
                _consume_path_value(nested)
            return
        if isinstance(value, (list, tuple, set)):
            for item in value:
                _consume_path_value(item)

    def _walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                if str(key).lower() in _PATH_KEYS:
                    _consume_path_value(nested)
                else:
                    _walk(nested)
            return
        if isinstance(value, (list, tuple, set)):
            for item in value:
                _walk(item)

    for payload in payloads:
        _walk(payload)

    return discovered


class ObservationLogger:
    """Append-only JSONL logger for tool-call observations.

    Thread-safe for single-process use. Each call to `record()` appends
    one line to the observations file.

    Usage:
        logger = ObservationLogger()
        logger.record(
            tool_type="bash",
            duration_ms=42.3,
            success=True,
            metadata={"command": "grep -r 'pattern' ."},
        )
    """

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else _default_observation_file()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        *,
        tool_type: str,
        duration_ms: float,
        success: bool,
        error_type: str | None = None,
        error_message: str | None = None,
        file_paths: list[str] | None = None,
        session_id: str | None = None,
        observation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ToolObservation:
        """Record a tool-call observation and append to the JSONL file."""
        obs = ToolObservation(
            tool_type=tool_type,
            timestamp=datetime.now(timezone.utc).isoformat(),
            duration_ms=round(duration_ms, 2),
            success=success,
            error_type=error_type,
            error_message=error_message,
            file_paths=file_paths or [],
            session_id=session_id,
            observation_id=observation_id or uuid.uuid4().hex[:12],
            metadata=metadata or {},
        )
        self._append(obs)
        return obs

    def _append(self, obs: ToolObservation) -> None:
        """Append one observation to the JSONL file."""
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(obs.to_json() + "\n")

    def _iter_lines(self) -> list[str]:
        """Return non-empty JSONL records from disk."""
        if not self.path.exists():
            return []
        with self.path.open(encoding="utf-8") as fh:
            return [line.strip() for line in fh if line.strip()]

    def count(self) -> int:
        """Return total number of observations on disk."""
        return len(self._iter_lines())

    def tail(self, n: int = 20) -> list[ToolObservation]:
        """Return the last N observations."""
        return [ToolObservation.from_json(line) for line in self._iter_lines()[-n:]]


# Convenience: module-level singleton
_default_logger: ObservationLogger | None = None


def get_logger(path: Path | str | None = None) -> ObservationLogger:
    """Get or create the default observation logger."""
    global _default_logger
    if _default_logger is None or (path and _default_logger.path != Path(path)):
        _default_logger = ObservationLogger(path)
    return _default_logger


def record_observation(**kwargs: Any) -> ToolObservation:
    """Record a tool-call observation using the default logger.

    Convenience wrapper:
        record_observation(tool_type="edit", duration_ms=12.5, success=True)
    """
    return get_logger().record(**kwargs)
