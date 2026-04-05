"""Tests for AuditStore implementations."""

from __future__ import annotations

from acgs.audit_memory import InMemoryAuditStore
from acgs.audit_sqlite import SQLiteAuditStore
from acgs.audit_store import AuditStore

from acgs_lite.audit import AuditEntry


def _make_entry(i: int, agent_id: str = "agent-1") -> AuditEntry:
    return AuditEntry(
        id=f"entry-{i}",
        type="validation",
        agent_id=agent_id,
        action=f"action-{i}",
        valid=i % 2 == 0,
        violations=[] if i % 2 == 0 else [f"rule-{i}"],
    )


class SharedStoreTests:
    """Tests that apply to every AuditStore implementation."""

    def make_store(self, tmp_path=None) -> AuditStore:
        raise NotImplementedError

    def test_conforms_to_abc(self, tmp_path):
        store = self.make_store(tmp_path)
        assert isinstance(store, AuditStore)

    def test_append_and_get(self, tmp_path):
        store = self.make_store(tmp_path)
        entry = _make_entry(1)
        store.append(entry)
        retrieved = store.get("entry-1")
        assert retrieved is not None
        assert retrieved.id == "entry-1"
        assert retrieved.action == "action-1"

    def test_get_nonexistent(self, tmp_path):
        store = self.make_store(tmp_path)
        assert store.get("nope") is None

    def test_count(self, tmp_path):
        store = self.make_store(tmp_path)
        assert store.count() == 0
        store.append(_make_entry(1))
        store.append(_make_entry(2))
        assert store.count() == 2

    def test_list_entries(self, tmp_path):
        store = self.make_store(tmp_path)
        for i in range(5):
            store.append(_make_entry(i))
        entries = store.list_entries(limit=3)
        assert len(entries) == 3

    def test_list_with_offset(self, tmp_path):
        store = self.make_store(tmp_path)
        for i in range(10):
            store.append(_make_entry(i))
        page = store.list_entries(limit=3, offset=7)
        assert len(page) == 3
        assert page[0].id == "entry-7"

    def test_list_filter_by_agent(self, tmp_path):
        store = self.make_store(tmp_path)
        store.append(_make_entry(1, agent_id="alice"))
        store.append(_make_entry(2, agent_id="bob"))
        store.append(_make_entry(3, agent_id="alice"))
        alice_entries = store.list_entries(agent_id="alice")
        assert len(alice_entries) == 2
        assert all(e.agent_id == "alice" for e in alice_entries)

    def test_verify_chain_empty(self, tmp_path):
        store = self.make_store(tmp_path)
        assert store.verify_chain() is True

    def test_verify_chain_valid(self, tmp_path):
        store = self.make_store(tmp_path)
        for i in range(10):
            store.append(_make_entry(i))
        assert store.verify_chain() is True

    def test_pagination_50_entries(self, tmp_path):
        store = self.make_store(tmp_path)
        for i in range(50):
            store.append(_make_entry(i))
        assert store.count() == 50
        page = store.list_entries(limit=10, offset=20)
        assert len(page) == 10
        assert page[0].id == "entry-20"


class TestInMemoryAuditStore(SharedStoreTests):
    def make_store(self, tmp_path=None) -> AuditStore:
        return InMemoryAuditStore()


class TestSQLiteAuditStore(SharedStoreTests):
    def make_store(self, tmp_path=None) -> AuditStore:
        path = tmp_path / "test.db" if tmp_path else "test.db"
        return SQLiteAuditStore(path)

    def test_chain_tamper_detection(self, tmp_path):
        store = SQLiteAuditStore(tmp_path / "tamper.db")
        for i in range(5):
            store.append(_make_entry(i))
        assert store.verify_chain() is True

        # Tamper with an entry
        store._conn.execute("UPDATE audit_entries SET action = 'TAMPERED' WHERE id = 'entry-2'")
        store._conn.commit()
        assert store.verify_chain() is False

    def test_persistence_across_connections(self, tmp_path):
        db_path = tmp_path / "persist.db"
        store1 = SQLiteAuditStore(db_path)
        store1.append(_make_entry(1))
        store1.close()

        store2 = SQLiteAuditStore(db_path)
        assert store2.count() == 1
        assert store2.get("entry-1") is not None
        store2.close()
