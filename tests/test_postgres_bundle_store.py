"""Unit tests for PostgresBundleStore using a mock psycopg pool.

These tests do NOT require a running Postgres instance.  They verify:

- import-time is lazy (module imports fine without psycopg installed)
- the store implements the BundleStore protocol
- SQL statements are well-formed (driver parameter shape matches expectations)
- CAS conflict raises CASVersionConflict
- ACTIVE uniqueness violation is re-raised as LifecycleError

An end-to-end integration test against a real Postgres would live under
``tests/integration/`` and be gated by a ``postgres`` pytest marker; it
is intentionally out of scope for the unit suite.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

import pytest


class _FakeCursor:
    def __init__(self, connection: _FakeConnection) -> None:
        self._conn = connection
        self._last_rows: list[tuple[Any, ...]] = []

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *exc: Any) -> None:
        return None

    def execute(self, sql: str, params: Any = None) -> None:
        self._conn.executed.append((sql, params))
        # Programmed responses queued on the connection:
        if self._conn.fetch_queue:
            self._last_rows = self._conn.fetch_queue.pop(0)
        else:
            self._last_rows = []
        # A programmed error can be queued to raise on .execute().
        err = self._conn.raise_on_next_execute
        if err is not None:
            self._conn.raise_on_next_execute = None
            raise err

    def fetchone(self) -> tuple[Any, ...] | None:
        return self._last_rows[0] if self._last_rows else None

    def fetchall(self) -> list[tuple[Any, ...]]:
        return list(self._last_rows)


class _FakeConnection:
    def __init__(self) -> None:
        self.executed: list[tuple[str, Any]] = []
        self.fetch_queue: list[list[tuple[Any, ...]]] = []
        self.committed = False
        self.rolled_back = False
        self.raise_on_next_execute: Exception | None = None

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self)

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


class _FakePool:
    def __init__(self) -> None:
        self.conn = _FakeConnection()
        self.closed = False

    @contextmanager
    def connection(self) -> Any:
        yield self.conn

    def close(self) -> None:
        self.closed = True


class _FakePsycopgError(Exception):
    pass


class _FakeUniqueViolation(_FakePsycopgError):
    pass


def _install_fake_psycopg(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Install a tiny fake ``psycopg`` module so the store imports cleanly."""
    fake_errors = SimpleNamespace(UniqueViolation=_FakeUniqueViolation)
    fake_psycopg = SimpleNamespace(
        Error=_FakePsycopgError,
        errors=fake_errors,
    )
    monkeypatch.setitem(sys.modules, "psycopg", fake_psycopg)
    fake_pool_mod = SimpleNamespace(ConnectionPool=_FakePool)
    monkeypatch.setitem(sys.modules, "psycopg_pool", fake_pool_mod)
    return fake_psycopg


def _make_bundle(
    tenant: str = "t1",
    status: str = "draft",
) -> Any:
    from acgs_lite.constitution.bundle import BundleStatus, ConstitutionBundle
    from acgs_lite.constitution.constitution import Constitution

    constitution = Constitution(name="c", hash="h" * 16, rules=())
    return ConstitutionBundle(
        tenant_id=tenant,
        constitution=constitution,
        proposed_by="p1",
        status=BundleStatus(status),
    )


class TestImportability:
    def test_module_importable_without_psycopg(self) -> None:
        # The module itself should import without psycopg installed — the
        # dependency is only required at instantiation time.
        import importlib

        module = importlib.import_module("acgs_lite.constitution.postgres_bundle_store")
        assert hasattr(module, "PostgresBundleStore")

    def test_missing_psycopg_raises_clear_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from acgs_lite.constitution import postgres_bundle_store

        def _raise(*a: Any, **kw: Any) -> Any:
            raise ImportError(
                "PostgresBundleStore requires the 'postgres' extra. "
                "Install with: pip install 'acgs-lite[postgres]'"
            )

        monkeypatch.setattr(postgres_bundle_store, "_import_psycopg", _raise)
        with pytest.raises(ImportError, match="postgres.*extra"):
            postgres_bundle_store.PostgresBundleStore(dsn="postgresql://x")


class TestSaveAndGet:
    def test_save_bundle_executes_upsert(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _install_fake_psycopg(monkeypatch)
        from acgs_lite.constitution.postgres_bundle_store import PostgresBundleStore

        pool = _FakePool()
        store = PostgresBundleStore(pool=pool, schema_setup=False)
        store.save_bundle(_make_bundle())

        sqls = [sql for sql, _ in pool.conn.executed]
        assert any("INSERT INTO bundles" in s for s in sqls)
        assert pool.conn.committed

    def test_save_bundle_active_uniqueness_raises_lifecycle_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _install_fake_psycopg(monkeypatch)
        from acgs_lite.constitution.lifecycle_service import LifecycleError
        from acgs_lite.constitution.postgres_bundle_store import PostgresBundleStore

        pool = _FakePool()
        pool.conn.raise_on_next_execute = _FakeUniqueViolation("dup")
        store = PostgresBundleStore(pool=pool, schema_setup=False)
        with pytest.raises(LifecycleError, match="ACTIVE"):
            store.save_bundle(_make_bundle(status="active"))

    def test_get_bundle_returns_none_for_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _install_fake_psycopg(monkeypatch)
        from acgs_lite.constitution.postgres_bundle_store import PostgresBundleStore

        pool = _FakePool()
        store = PostgresBundleStore(pool=pool, schema_setup=False)
        assert store.get_bundle("missing") is None


class TestCASVersion:
    def test_cas_version_mismatch_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _install_fake_psycopg(monkeypatch)
        from acgs_lite.constitution.bundle_store import CASVersionConflict
        from acgs_lite.constitution.postgres_bundle_store import PostgresBundleStore

        pool = _FakePool()
        # First .execute() is SELECT FOR UPDATE; queue one row with version=5.
        pool.conn.fetch_queue.append([(5,)])
        store = PostgresBundleStore(pool=pool, schema_setup=False)
        with pytest.raises(CASVersionConflict):
            store.cas_tenant_version("t1", expected=0)
        assert pool.conn.rolled_back

    def test_cas_version_happy_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _install_fake_psycopg(monkeypatch)
        from acgs_lite.constitution.postgres_bundle_store import PostgresBundleStore

        pool = _FakePool()
        pool.conn.fetch_queue.append([(2,)])
        store = PostgresBundleStore(pool=pool, schema_setup=False)
        store.cas_tenant_version("t1", expected=2)
        inserts = [sql for sql, _ in pool.conn.executed if "INSERT INTO tenant_versions" in sql]
        assert inserts, "cas_tenant_version must INSERT/UPDATE on match"
        assert pool.conn.committed


class TestProtocolConformance:
    def test_is_bundle_store(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _install_fake_psycopg(monkeypatch)
        from acgs_lite.constitution.bundle_store import BundleStore
        from acgs_lite.constitution.postgres_bundle_store import PostgresBundleStore

        pool = _FakePool()
        store = PostgresBundleStore(pool=pool, schema_setup=False)
        assert isinstance(store, BundleStore)


class TestClose:
    def test_owned_pool_closed_on_close(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _install_fake_psycopg(monkeypatch)
        from acgs_lite.constitution import postgres_bundle_store as mod

        captured: dict[str, Any] = {}

        class _CapturingPool(_FakePool):
            def __init__(self, *a: Any, **kw: Any) -> None:
                super().__init__()
                captured["pool"] = self

        monkeypatch.setitem(
            sys.modules,
            "psycopg_pool",
            SimpleNamespace(ConnectionPool=_CapturingPool),
        )
        store = mod.PostgresBundleStore(dsn="postgresql://x", schema_setup=False)
        store.close()
        assert captured["pool"].closed is True

    def test_external_pool_not_closed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _install_fake_psycopg(monkeypatch)
        from acgs_lite.constitution.postgres_bundle_store import PostgresBundleStore

        pool = _FakePool()
        store = PostgresBundleStore(pool=pool, schema_setup=False)
        store.close()
        assert pool.closed is False, "store must not close a pool it does not own"
