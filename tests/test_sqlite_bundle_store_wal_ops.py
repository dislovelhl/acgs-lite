"""Tests for SQLiteBundleStore WAL operational hooks (sqlite-wal-ops)."""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from acgs_lite.constitution.sqlite_bundle_store import (
    SQLiteBundleStore,
    _is_vulnerable_to_wal_reset_bug,
)


@pytest.fixture
def store(tmp_path: Path) -> SQLiteBundleStore:
    return SQLiteBundleStore(tmp_path / "bundles.db")


class TestWalAutoCheckpoint:
    def test_default_pragma_applied(self, store: SQLiteBundleStore) -> None:
        with store._connect() as conn:
            row = conn.execute("PRAGMA wal_autocheckpoint").fetchone()
        assert row[0] == 500

    def test_custom_pragma_applied(self, tmp_path: Path) -> None:
        store = SQLiteBundleStore(tmp_path / "bundles.db", wal_autocheckpoint=42)
        with store._connect() as conn:
            row = conn.execute("PRAGMA wal_autocheckpoint").fetchone()
        assert row[0] == 42


class TestCheckpointApi:
    def test_passive_checkpoint_returns_pages(self, store: SQLiteBundleStore) -> None:
        log, ckpt = store.checkpoint("PASSIVE")
        assert isinstance(log, int)
        assert isinstance(ckpt, int)

    def test_full_checkpoint_runs(self, store: SQLiteBundleStore) -> None:
        # Force some WAL traffic, then checkpoint.
        with store._connect() as conn:
            conn.execute(
                "INSERT INTO bundles (bundle_id, tenant_id, status, payload, updated_at) "
                "VALUES ('b1', 't1', 'draft', '{}', '2025-01-01')"
            )
            conn.commit()
        log, ckpt = store.checkpoint("FULL")
        assert log >= 0
        assert ckpt >= 0

    def test_invalid_mode_raises(self, store: SQLiteBundleStore) -> None:
        with pytest.raises(ValueError, match="checkpoint mode"):
            store.checkpoint("BOGUS")  # type: ignore[arg-type]


class TestVersionWarning:
    @pytest.mark.parametrize(
        "version,vulnerable",
        [
            ((3, 7, 0), True),
            ((3, 44, 5), True),
            ((3, 44, 6), False),
            ((3, 44, 7), False),
            ((3, 45, 0), True),
            ((3, 50, 6), True),
            ((3, 50, 7), False),
            ((3, 51, 0), True),
            ((3, 51, 2), True),
            ((3, 51, 3), False),
            ((3, 52, 0), False),
            ((4, 0, 0), False),
        ],
    )
    def test_version_classification(self, version: tuple[int, int, int], vulnerable: bool) -> None:
        assert _is_vulnerable_to_wal_reset_bug(version) is vulnerable

    def test_warning_emitted_at_most_once(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Force the module to think it has not warned yet.
        import acgs_lite.constitution.sqlite_bundle_store as mod

        monkeypatch.setattr(mod, "_WAL_BUG_WARNING_EMITTED", False)
        # Pretend we're on a vulnerable version.
        monkeypatch.setattr(mod, "_sqlite_version_tuple", lambda: (3, 51, 2))

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            SQLiteBundleStore(tmp_path / "a.db")
            SQLiteBundleStore(tmp_path / "b.db")

        wal_warnings = [w for w in caught if "WAL-reset" in str(w.message)]
        assert len(wal_warnings) == 1
        assert issubclass(wal_warnings[0].category, RuntimeWarning)

    def test_no_warning_on_safe_version(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import acgs_lite.constitution.sqlite_bundle_store as mod

        monkeypatch.setattr(mod, "_WAL_BUG_WARNING_EMITTED", False)
        monkeypatch.setattr(mod, "_sqlite_version_tuple", lambda: (3, 51, 3))

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            SQLiteBundleStore(tmp_path / "a.db")

        assert not [w for w in caught if "WAL-reset" in str(w.message)]
