"""Unit tests for constitutional token access audit logging.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import json

import pytest

from acgs_auth0.audit import TokenAccessAuditEntry, TokenAccessOutcome, TokenAuditLog


# ---------------------------------------------------------------------------
# TokenAccessAuditEntry
# ---------------------------------------------------------------------------


class TestTokenAccessAuditEntry:
    def test_to_dict_includes_required_keys(self) -> None:
        entry = TokenAccessAuditEntry(
            agent_id="planner",
            role="EXECUTIVE",
            connection="github",
            requested_scopes=["repo:read"],
            granted_scopes=["repo:read"],
            outcome=TokenAccessOutcome.GRANTED,
        )
        d = entry.to_dict()
        assert d["agent_id"] == "planner"
        assert d["role"] == "EXECUTIVE"
        assert d["connection"] == "github"
        assert d["outcome"] == "granted"
        assert d["constitutional_hash"] == "608508a9bd224290"
        assert "timestamp" in d

    def test_to_json_is_valid_json(self) -> None:
        entry = TokenAccessAuditEntry(
            agent_id="executor",
            role="IMPLEMENTER",
            connection="google-oauth2",
            requested_scopes=["openid"],
            granted_scopes=["openid"],
            outcome=TokenAccessOutcome.GRANTED,
        )
        raw = entry.to_json()
        parsed = json.loads(raw)
        assert parsed["agent_id"] == "executor"


# ---------------------------------------------------------------------------
# TokenAuditLog
# ---------------------------------------------------------------------------


class TestTokenAuditLog:
    def test_record_granted_adds_entry(self) -> None:
        log = TokenAuditLog()
        log.record_granted(
            agent_id="planner",
            role="EXECUTIVE",
            connection="github",
            scopes=["repo:read"],
            user_id="auth0|abc",
            tool_name="list_issues",
        )
        assert len(log) == 1
        entries = log.get_entries()
        assert entries[0].outcome == TokenAccessOutcome.GRANTED

    def test_record_denied_scope_violation(self) -> None:
        log = TokenAuditLog()
        log.record_denied(
            agent_id="planner",
            role="EXECUTIVE",
            connection="github",
            scopes=["repo:write"],
            reason="scope_violation",
            error_message="denied",
        )
        entries = log.get_entries(outcome=TokenAccessOutcome.DENIED_SCOPE_VIOLATION)
        assert len(entries) == 1

    def test_record_denied_role_not_permitted(self) -> None:
        log = TokenAuditLog()
        log.record_denied(
            agent_id="validator",
            role="JUDICIAL",
            connection="github",
            scopes=["read:user"],
            reason="role_not_permitted",
        )
        entries = log.get_entries(outcome=TokenAccessOutcome.DENIED_ROLE_NOT_PERMITTED)
        assert len(entries) == 1

    def test_record_step_up_approved(self) -> None:
        log = TokenAuditLog()
        log.record_step_up(
            agent_id="executor",
            role="IMPLEMENTER",
            connection="github",
            scopes=["repo:write"],
            binding_message="Approve PR creation",
            approved=True,
        )
        entries = log.get_entries(outcome=TokenAccessOutcome.STEP_UP_APPROVED)
        assert len(entries) == 1
        assert entries[0].step_up_binding_message == "Approve PR creation"

    def test_record_step_up_denied(self) -> None:
        log = TokenAuditLog()
        log.record_step_up(
            agent_id="executor",
            role="IMPLEMENTER",
            connection="github",
            scopes=["repo:write"],
            binding_message="Approve PR creation",
            approved=False,
        )
        entries = log.get_entries(outcome=TokenAccessOutcome.STEP_UP_DENIED)
        assert len(entries) == 1

    def test_filter_by_agent_id(self) -> None:
        log = TokenAuditLog()
        log.record_granted(agent_id="agent-1", role="EXECUTIVE", connection="github",
                           scopes=["repo:read"])
        log.record_granted(agent_id="agent-2", role="EXECUTIVE", connection="github",
                           scopes=["repo:read"])
        assert len(log.get_entries(agent_id="agent-1")) == 1
        assert len(log.get_entries(agent_id="agent-2")) == 1

    def test_filter_by_connection(self) -> None:
        log = TokenAuditLog()
        log.record_granted(agent_id="a", role="EXECUTIVE", connection="github",
                           scopes=["repo:read"])
        log.record_granted(agent_id="a", role="EXECUTIVE", connection="google-oauth2",
                           scopes=["openid"])
        github_entries = log.get_entries(connection="github")
        assert len(github_entries) == 1
        assert github_entries[0].connection == "github"

    def test_to_jsonl(self) -> None:
        log = TokenAuditLog()
        log.record_granted(agent_id="a", role="EXECUTIVE", connection="github",
                           scopes=["repo:read"])
        log.record_denied(agent_id="a", role="EXECUTIVE", connection="github",
                          scopes=["repo:write"], reason="scope_violation")
        jsonl = log.to_jsonl()
        lines = jsonl.strip().split("\n")
        assert len(lines) == 2
        for line in lines:
            json.loads(line)  # assert valid JSON

    def test_file_backed_audit(self, tmp_path: pytest.TempPathFactory) -> None:
        log_file = tmp_path / "audit.jsonl"
        log = TokenAuditLog(file_path=log_file)
        log.record_granted(agent_id="a", role="EXECUTIVE", connection="github",
                           scopes=["repo:read"])
        assert log_file.exists()
        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["agent_id"] == "a"

    def test_record_step_up_initiated(self) -> None:
        log = TokenAuditLog()
        log.record_step_up_initiated(
            agent_id="executor",
            role="IMPLEMENTER",
            connection="github",
            scopes=["repo:write"],
            binding_message="Approve PR creation",
            user_id="auth0|demo",
            tool_name="create_pr",
        )
        entries = log.get_entries(outcome=TokenAccessOutcome.STEP_UP_INITIATED)
        assert len(entries) == 1
        assert entries[0].step_up_binding_message == "Approve PR creation"
        assert entries[0].granted_scopes == []

    def test_thread_safety(self) -> None:
        """Multiple threads can write to the audit log without corruption."""
        import threading

        log = TokenAuditLog()
        n = 50

        def write_entry(i: int) -> None:
            log.record_granted(
                agent_id=f"agent-{i}",
                role="EXECUTIVE",
                connection="github",
                scopes=["repo:read"],
            )

        threads = [threading.Thread(target=write_entry, args=(i,)) for i in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(log) == n
