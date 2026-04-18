"""CDP storage backends — pluggable Protocol + InMemory stub.

Pattern mirrors AuditBackend in audit.py: define Protocol first,
ship InMemory* stub alongside it, swap at runtime.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import builtins
from collections import OrderedDict
from typing import Protocol, runtime_checkable

from acgs_lite.cdp.record import CDPRecordV1


@runtime_checkable
class CDPBackend(Protocol):
    """Protocol for CDP persistence backends."""

    def save(self, record: CDPRecordV1) -> None:
        """Persist a CDP record. Called after finalize()."""
        ...

    def get(self, cdp_id: str) -> CDPRecordV1 | None:
        """Retrieve a record by ID. Returns None if not found."""
        ...

    def list(
        self,
        tenant_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CDPRecordV1]:
        """Return a paginated list of records, newest first."""
        ...

    def chain_hashes(self, tenant_id: str | None = None) -> builtins.list[str]:
        """Return ordered list of cdp_hash values for chain verification."""
        ...

    def count(self, tenant_id: str | None = None) -> int:
        """Return total record count."""
        ...


class InMemoryCDPBackend:
    """Thread-unsafe in-process CDP store — for tests and single-process use.

    Ordered dict preserves insertion order. Newest-first listing is achieved
    by reversing on read.

    Attributes:
        save_calls: list of CDPRecordV1 objects passed to save() — for assertions.
    """

    def __init__(self, max_records: int = 10_000) -> None:
        self._records: OrderedDict[str, CDPRecordV1] = OrderedDict()
        self._max_records = max_records
        self.save_calls: list[CDPRecordV1] = []

    def save(self, record: CDPRecordV1) -> None:
        self.save_calls.append(record)
        self._records[record.cdp_id] = record
        # Evict oldest if over capacity
        while len(self._records) > self._max_records:
            self._records.popitem(last=False)

    def get(self, cdp_id: str) -> CDPRecordV1 | None:
        return self._records.get(cdp_id)

    def list(
        self,
        tenant_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CDPRecordV1]:
        records = list(self._records.values())
        if tenant_id is not None:
            records = [r for r in records if r.tenant_id == tenant_id]
        records.reverse()  # newest first
        return records[offset : offset + limit]

    def chain_hashes(self, tenant_id: str | None = None) -> builtins.list[str]:
        records = list(self._records.values())
        if tenant_id is not None:
            records = [r for r in records if r.tenant_id == tenant_id]
        return [r.cdp_hash for r in records]

    def count(self, tenant_id: str | None = None) -> int:
        if tenant_id is None:
            return len(self._records)
        return sum(1 for r in self._records.values() if r.tenant_id == tenant_id)

    def verify_chain(self, tenant_id: str | None = None) -> tuple[bool, builtins.list[str]]:
        """Verify hash chain integrity. Returns (is_valid, list_of_broken_ids)."""
        records = list(self._records.values())
        if tenant_id is not None:
            records = [r for r in records if r.tenant_id == tenant_id]

        broken: list[str] = []
        prev_hash = "genesis"

        for record in records:
            # Verify the record's own hash
            if not record.verify():
                broken.append(record.cdp_id)
                continue

            # Verify chain linkage
            if record.prev_cdp_hash != prev_hash and prev_hash != "genesis":
                # Only check linkage after the first record
                broken.append(record.cdp_id)

            prev_hash = record.cdp_hash

        return (len(broken) == 0, broken)
