"""BundleAwareGovernanceEngine — composition wrapper that pulls the active
:class:`ConstitutionBundle` from a :class:`BundleStore` and returns a
fully-initialised :class:`GovernanceEngine` for the tenant's active rules.

Design notes
------------
* ``GovernanceEngine`` uses ``__slots__`` and pre-compiles rules at ``__init__``
  time, so hot-swapping a constitution on an existing instance is impossible.
  This class is a **factory / cache** — not a subclass.
* The internal cache is keyed by ``(tenant_id, bundle_hash)`` so that two
  tenants never share an engine, and switching to a new bundle always produces
  a fresh engine while keeping the old engine warm for any in-flight requests.
* ``invalidate(tenant_id)`` must be called by the lifecycle coordinator after
  ``activate()`` and ``rollback()`` so stale engines are evicted promptly.
* Thread safety is provided by a ``threading.Lock``; the lock is held only for
  cache reads/writes, not for the (potentially slow) engine construction.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from acgs_lite.constitution.bundle_store import BundleStore
    from acgs_lite.engine.core import GovernanceEngine


class BundleAwareGovernanceEngine:
    """Factory that constructs and caches :class:`GovernanceEngine` instances
    keyed to the active :class:`ConstitutionBundle` for a tenant.

    Usage::

        store = InMemoryBundleStore()  # or SQLiteBundleStore(...)
        binding = BundleAwareGovernanceEngine(store)

        engine = binding.for_active_bundle("tenant-42")
        if engine is None:
            raise RuntimeError("No active constitution for tenant-42")
        result = engine.validate(action, context)

        # After activate() or rollback() in the lifecycle coordinator:
        binding.invalidate("tenant-42")
    """

    def __init__(self, store: BundleStore) -> None:
        self._store = store
        self._cache: dict[tuple[str, str], GovernanceEngine] = {}
        self._lock = threading.Lock()

    # ── public API ──────────────────────────────────────────────────────

    def for_active_bundle(self, tenant_id: str) -> GovernanceEngine | None:
        """Return a :class:`GovernanceEngine` backed by the tenant's active bundle.

        Returns ``None`` when no bundle is currently active for the tenant.
        The engine is cached by ``(tenant_id, bundle_hash)``; a new engine is
        constructed only when the active bundle changes.

        :param tenant_id: Tenant identifier to look up in the bundle store.
        """
        bundle = self._store.get_active_bundle(tenant_id)
        if bundle is None:
            return None

        bundle_hash = bundle.constitutional_hash
        cache_key = (tenant_id, bundle_hash)

        with self._lock:
            if cache_key in self._cache:
                return self._cache[cache_key]

        # Construct outside the lock — engine init can be slow (Rust compile).
        from acgs_lite.engine.core import GovernanceEngine  # local import avoids circular dep

        engine = GovernanceEngine(bundle.constitution, strict=False)

        with self._lock:
            # Check again in case another thread populated it while we built.
            if cache_key not in self._cache:
                self._cache[cache_key] = engine
            return self._cache[cache_key]

    def invalidate(self, tenant_id: str) -> None:
        """Evict all cached engines for *tenant_id*.

        Must be called by the lifecycle coordinator after ``activate()`` and
        ``rollback()`` so in-flight requests use the updated constitution.

        :param tenant_id: Tenant whose cached engines should be removed.
        """
        with self._lock:
            stale = [k for k in self._cache if k[0] == tenant_id]
            for k in stale:
                del self._cache[k]

    @classmethod
    def for_active_bundle_once(cls, store: BundleStore, tenant_id: str) -> GovernanceEngine | None:
        """Convenience classmethod: construct an engine without caching.

        Useful in one-shot scripts or tests where lifecycle management is
        handled elsewhere and caching would be misleading.

        :param store: The :class:`BundleStore` to look up the active bundle.
        :param tenant_id: Tenant identifier.
        """
        bundle = store.get_active_bundle(tenant_id)
        if bundle is None:
            return None
        from acgs_lite.engine.core import GovernanceEngine

        return GovernanceEngine(bundle.constitution, strict=False)
