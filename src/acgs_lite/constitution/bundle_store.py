"""Bundle storage backends — Protocol plus in-memory implementation.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from collections import OrderedDict
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable


def _utcnow_dt() -> datetime:
    """Return the current UTC datetime with tzinfo set.

    Canonical source shared by both SQLite and Postgres bundle stores so
    all timestamp values originate from the same code path.  Each store
    converts to the type its driver expects (``str`` for SQLite TEXT
    columns, ``datetime`` for psycopg3 TIMESTAMPTZ columns).
    """
    return datetime.now(UTC)

from acgs_lite.constitution.activation import ActivationRecord
from acgs_lite.constitution.bundle import BundleStatus, ConstitutionBundle


class CASVersionConflict(Exception):
    """Raised when a compare-and-swap tenant version check fails."""


@runtime_checkable
class BundleStore(Protocol):
    """Protocol for constitution bundle persistence backends."""

    def save_bundle(self, bundle: ConstitutionBundle) -> None:
        """Persist a bundle.

        Ordering contract: implementations reject a second ACTIVE bundle
        per tenant. Callers that activate a new bundle must supersede the
        existing active bundle *before* saving the new one as ACTIVE.
        """
        ...

    def get_bundle(self, bundle_id: str) -> ConstitutionBundle | None: ...

    def get_active_bundle(self, tenant_id: str) -> ConstitutionBundle | None: ...

    def list_bundles(
        self,
        tenant_id: str,
        *,
        status: BundleStatus | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[ConstitutionBundle]: ...

    def save_activation(self, record: ActivationRecord) -> None: ...

    def get_activation(self, tenant_id: str) -> ActivationRecord | None: ...

    def get_tenant_version(self, tenant_id: str) -> int:
        """Return the current CAS version counter for a tenant."""
        ...

    def cas_tenant_version(self, tenant_id: str, expected: int) -> None:
        """Atomically increment the tenant version if it matches *expected*.

        Raises :class:`CASVersionConflict` when the stored version differs
        from *expected* (concurrent write detected).
        """
        ...


class InMemoryBundleStore:
    """In-process bundle store for tests and single-process use."""

    def __init__(self, max_bundles: int = 10_000) -> None:
        self._bundles: OrderedDict[str, ConstitutionBundle] = OrderedDict()
        self._activations: dict[str, ActivationRecord] = {}
        self._max_bundles = max_bundles
        self._tenant_versions: dict[str, int] = {}

    def save_bundle(self, bundle: ConstitutionBundle) -> None:
        existing = self._bundles.get(bundle.bundle_id)
        candidate = bundle.model_copy(deep=True)

        if existing is None:
            for stored in self._bundles.values():
                if (
                    stored.tenant_id == candidate.tenant_id
                    and stored.version == candidate.version
                    and stored.bundle_id != candidate.bundle_id
                ):
                    raise ValueError(
                        "Bundle version must be unique per tenant: "
                        f"{candidate.tenant_id!r} v{candidate.version}"
                    )

        active_conflict = self.get_active_bundle(candidate.tenant_id)
        if (
            candidate.status == BundleStatus.ACTIVE
            and active_conflict is not None
            and active_conflict.bundle_id != candidate.bundle_id
        ):
            raise ValueError(f"Tenant {candidate.tenant_id!r} already has an ACTIVE bundle")

        self._bundles[candidate.bundle_id] = candidate
        self._bundles.move_to_end(candidate.bundle_id)
        while len(self._bundles) > self._max_bundles:
            dropped_id, dropped = self._bundles.popitem(last=False)
            if (
                self._activations.get(dropped.tenant_id, None)
                and self._activations[dropped.tenant_id].bundle_id == dropped_id
            ):
                del self._activations[dropped.tenant_id]

    def get_bundle(self, bundle_id: str) -> ConstitutionBundle | None:
        bundle = self._bundles.get(bundle_id)
        return None if bundle is None else bundle.model_copy(deep=True)

    def get_active_bundle(self, tenant_id: str) -> ConstitutionBundle | None:
        for bundle in self._bundles.values():
            if bundle.tenant_id == tenant_id and bundle.status == BundleStatus.ACTIVE:
                return bundle.model_copy(deep=True)
        return None

    def list_bundles(
        self,
        tenant_id: str,
        *,
        status: BundleStatus | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[ConstitutionBundle]:
        bundles = [
            bundle.model_copy(deep=True)
            for bundle in self._bundles.values()
            if bundle.tenant_id == tenant_id and (status is None or bundle.status == status)
        ]
        bundles.sort(key=lambda bundle: bundle.version, reverse=True)
        if limit is None:
            return bundles[offset:]
        return bundles[offset : offset + limit]

    def save_activation(self, record: ActivationRecord) -> None:
        self._activations[record.tenant_id] = record.model_copy(deep=True)

    def get_activation(self, tenant_id: str) -> ActivationRecord | None:
        record = self._activations.get(tenant_id)
        return None if record is None else record.model_copy(deep=True)

    def get_tenant_version(self, tenant_id: str) -> int:
        return self._tenant_versions.get(tenant_id, 0)

    def cas_tenant_version(self, tenant_id: str, expected: int) -> None:
        current = self._tenant_versions.get(tenant_id, 0)
        if current != expected:
            raise CASVersionConflict(
                f"Tenant {tenant_id!r} version conflict: expected {expected}, current {current}"
            )
        self._tenant_versions[tenant_id] = current + 1


__all__ = ["BundleStore", "CASVersionConflict", "InMemoryBundleStore", "_utcnow_dt"]
