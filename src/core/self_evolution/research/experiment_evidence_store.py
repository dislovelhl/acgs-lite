"""File-backed bounded experiment evidence store.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from src.core.self_evolution.models import BoundedExperimentEvidenceRecord

DEFAULT_BOUNDED_EXPERIMENT_EVIDENCE_PATH = Path("/tmp/acgs-self-evolution-evidence")
_EVIDENCE_FILENAME = "bounded_experiment_evidence.jsonl"


class BoundedExperimentEvidenceStore:
    """Minimal append-only evidence store backed by JSONL on disk."""

    def __init__(self, path: str | Path = DEFAULT_BOUNDED_EXPERIMENT_EVIDENCE_PATH):
        self._path = Path(path)
        self._file = self._path / _EVIDENCE_FILENAME

    async def append(self, record: BoundedExperimentEvidenceRecord) -> None:
        self._path.mkdir(parents=True, exist_ok=True)
        with self._file.open("a", encoding="utf-8") as handle:
            handle.write(record.model_dump_json())
            handle.write("\n")

    async def list_records(self) -> list[BoundedExperimentEvidenceRecord]:
        if not self._file.exists():
            return []
        records: list[BoundedExperimentEvidenceRecord] = []
        with self._file.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                records.append(BoundedExperimentEvidenceRecord.model_validate_json(line))
        return records

    async def get(self, evidence_id: UUID) -> BoundedExperimentEvidenceRecord | None:
        for record in await self.list_records():
            if record.evidence_id == evidence_id:
                return record
        return None


__all__ = [
    "DEFAULT_BOUNDED_EXPERIMENT_EVIDENCE_PATH",
    "BoundedExperimentEvidenceStore",
]

