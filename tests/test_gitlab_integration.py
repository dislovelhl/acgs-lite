"""Tests for acgs_lite.integrations.gitlab module.

Exercises the real GitLabGovernanceBot, GitLabWebhookHandler,
GitLabMACIEnforcer classes plus helper functions with mocked HTTP layer.
No real network or database calls.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from acgs_lite import AuditLog, Constitution, Rule, Severity
from acgs_lite.integrations.gitlab import (
    GitLabGovernanceBot,
    GitLabMACIEnforcer,
    GitLabWebhookHandler,
    GovernanceReport,
    _compute_risk_score,
    _parse_added_lines,
    create_gitlab_ci_config,
    format_governance_report,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def constitution() -> Constitution:
    """Constitution with rules that can produce violations on known keywords."""
    return Constitution.from_rules(
        [
            Rule(
                id="ACGS-001",
                text="Agents must not bypass independent validation.",
                severity=Severity.CRITICAL,
                keywords=["bypass", "self-validate"],
            ),
            Rule(
                id="ACGS-004",
                text="Agents must not self-approve their own outputs.",
                severity=Severity.HIGH,
                keywords=["self-approve", "own outputs"],
            ),
        ]
    )


@pytest.fixture
def bot(constitution: Constitution) -> GitLabGovernanceBot:
    """GitLabGovernanceBot with mocked HTTP so no real requests are made."""
    return GitLabGovernanceBot(
        token="glpat-test-token",
        project_id=100,
        constitution=constitution,
        base_url="https://gitlab.example.com/api/v4",
        timeout=5.0,
        strict=False,
    )


@pytest.fixture
def clean_mr_data() -> dict[str, Any]:
    """MR data dict simulating a clean merge request."""
    return {
        "iid": 42,
        "title": "feat: add health check endpoint",
        "description": "Adds /health for monitoring.",
        "diff_refs": {
            "base_sha": "aaa111",
            "head_sha": "bbb222",
        },
        "author": {"username": "dev-user"},
    }


@pytest.fixture
def clean_changes() -> dict[str, Any]:
    """Changes payload with harmless diff content."""
    return {
        "changes": [
            {
                "old_path": "src/app.py",
                "new_path": "src/app.py",
                "diff": ("@@ -1,3 +1,5 @@\n+def health():\n+    return 'ok'\n # existing\n"),
            }
        ]
    }


@pytest.fixture
def violating_mr_data() -> dict[str, Any]:
    """MR data dict whose title triggers a violation."""
    return {
        "iid": 99,
        "title": "feat: self-validate bypass all checks",
        "description": "Let agents self-approve their own outputs.",
        "diff_refs": {
            "base_sha": "aaa111",
            "head_sha": "bbb222",
        },
        "author": {"username": "bad-actor"},
    }


@pytest.fixture
def violating_changes() -> dict[str, Any]:
    return {
        "changes": [
            {
                "new_path": "src/evil.py",
                "diff": ("@@ -0,0 +1,2 @@\n+bypass validation here\n+safe line\n"),
            }
        ]
    }


# ---------------------------------------------------------------------------
# _parse_added_lines tests
# ---------------------------------------------------------------------------


class TestParseAddedLines:
    """Tests for the unified-diff parser helper."""

    def test_simple_addition(self) -> None:
        diff = "@@ -0,0 +1,3 @@\n+line one\n+line two\n+line three\n"
        result = _parse_added_lines(diff)
        assert len(result) == 3
        assert result[0] == (1, "line one")
        assert result[1] == (2, "line two")
        assert result[2] == (3, "line three")

    def test_skips_blank_added_lines(self) -> None:
        diff = "@@ -0,0 +1,3 @@\n+content\n+\n+more\n"
        result = _parse_added_lines(diff)
        # blank line (just whitespace after +) is skipped
        assert len(result) == 2
        assert result[0][1] == "content"
        assert result[1][1] == "more"

    def test_ignores_deleted_lines(self) -> None:
        diff = "@@ -1,3 +1,2 @@\n-removed\n context\n+added\n"
        result = _parse_added_lines(diff)
        assert len(result) == 1
        assert result[0][1] == "added"

    def test_multiple_hunks(self) -> None:
        diff = "@@ -1,2 +1,3 @@\n ctx\n+first add\n@@ -10,2 +11,3 @@\n ctx\n+second add\n"
        result = _parse_added_lines(diff)
        assert len(result) == 2
        assert result[0][1] == "first add"
        assert result[1][1] == "second add"

    def test_empty_diff(self) -> None:
        assert _parse_added_lines("") == []

    def test_no_hunk_header(self) -> None:
        # Lines without a hunk header start at line 0
        diff = "+orphan line\n"
        result = _parse_added_lines(diff)
        assert len(result) == 1
        assert result[0] == (0, "orphan line")

    def test_ignores_file_headers(self) -> None:
        diff = "--- a/old.py\n+++ b/new.py\n@@ -0,0 +1,1 @@\n+real line\n"
        result = _parse_added_lines(diff)
        assert len(result) == 1
        assert result[0][1] == "real line"

    def test_context_lines_advance_counter(self) -> None:
        diff = "@@ -1,4 +1,5 @@\n ctx1\n ctx2\n+added at 3\n ctx3\n"
        result = _parse_added_lines(diff)
        assert result[0] == (3, "added at 3")


# ---------------------------------------------------------------------------
# _compute_risk_score tests
# ---------------------------------------------------------------------------


class TestComputeRiskScore:
    """Tests for the risk score computation helper."""

    def test_no_issues_returns_zero(self) -> None:
        assert _compute_risk_score([], []) == 0.0

    def test_single_critical_violation(self) -> None:
        score = _compute_risk_score([{"severity": "critical"}], [])
        assert score == pytest.approx(1.0)

    def test_single_low_warning(self) -> None:
        score = _compute_risk_score([], [{"severity": "low"}])
        # low weight 0.1 * 0.5 = 0.05, normalised by 1 item => 0.05
        assert score == pytest.approx(0.05)

    def test_capped_at_one(self) -> None:
        violations = [{"severity": "critical"}] * 10
        score = _compute_risk_score(violations, [])
        assert score <= 1.0

    def test_mixed_severities(self) -> None:
        violations = [{"severity": "high"}, {"severity": "medium"}]
        score = _compute_risk_score(violations, [])
        assert 0.0 < score < 1.0

    def test_unknown_severity_defaults(self) -> None:
        score = _compute_risk_score([{"severity": "unknown"}], [])
        # defaults to medium weight 0.3
        assert score == pytest.approx(0.3)


# ---------------------------------------------------------------------------
# GovernanceReport tests
# ---------------------------------------------------------------------------


class TestGovernanceReport:
    """Tests for the frozen GovernanceReport dataclass."""

    def test_immutable(self) -> None:
        report = GovernanceReport(mr_iid=1, title="t", passed=True, risk_score=0.0)
        with pytest.raises(AttributeError):
            report.passed = False  # type: ignore[misc]

    def test_defaults(self) -> None:
        report = GovernanceReport(mr_iid=1, title="t", passed=True, risk_score=0.0)
        assert report.violations == []
        assert report.warnings == []
        assert report.commit_violations == []
        assert report.rules_checked == 0
        assert report.constitutional_hash == ""
        assert report.latency_ms == 0.0


# ---------------------------------------------------------------------------
# format_governance_report tests
# ---------------------------------------------------------------------------


class TestFormatGovernanceReport:
    """Tests for the Markdown report formatter."""

    def test_passed_report(self) -> None:
        report = GovernanceReport(
            mr_iid=1,
            title="Clean MR",
            passed=True,
            risk_score=0.0,
            rules_checked=5,
            constitutional_hash="abc123",
        )
        md = format_governance_report(report)
        assert "PASSED" in md
        assert "white_check_mark" in md
        assert "abc123" in md
        assert "Rules Checked" in md

    def test_failed_report_with_violations(self) -> None:
        report = GovernanceReport(
            mr_iid=2,
            title="Bad MR",
            passed=False,
            risk_score=0.8,
            violations=[
                {
                    "rule_id": "ACGS-001",
                    "rule_text": "No bypass",
                    "severity": "critical",
                    "source": "diff",
                    "file": "src/x.py",
                    "line": 10,
                }
            ],
            rules_checked=3,
        )
        md = format_governance_report(report)
        assert "FAILED" in md
        assert ":x:" in md
        assert "ACGS-001" in md
        assert "src/x.py:10" in md
        assert "### Violations" in md

    def test_warnings_section(self) -> None:
        report = GovernanceReport(
            mr_iid=3,
            title="Warn MR",
            passed=True,
            risk_score=0.1,
            warnings=[{"rule_id": "W-001", "rule_text": "Minor issue", "severity": "low"}],
        )
        md = format_governance_report(report)
        assert "### Warnings" in md
        assert "W-001" in md

    def test_commit_violations_section(self) -> None:
        report = GovernanceReport(
            mr_iid=4,
            title="Commit MR",
            passed=False,
            risk_score=0.5,
            commit_violations=[
                {
                    "sha": "abc123",
                    "message": "bad commit",
                    "violations": [{"rule_id": "R-1", "rule_text": "bad"}],
                }
            ],
        )
        md = format_governance_report(report)
        assert "### Commit Message Violations" in md
        assert "abc123" in md

    def test_footer_present(self) -> None:
        report = GovernanceReport(mr_iid=1, title="t", passed=True, risk_score=0.0)
        md = format_governance_report(report)
        assert "ACGS Governance Bot" in md


# ---------------------------------------------------------------------------
# create_gitlab_ci_config tests
# ---------------------------------------------------------------------------


class TestCreateGitLabCIConfig:
    """Tests for the CI config generator."""

    def test_generates_yaml_string(self) -> None:
        config = create_gitlab_ci_config()
        assert isinstance(config, str)
        assert "governance:" in config
        assert "stage: test" in config
        assert "pip install acgs-lite[gitlab]" in config

    def test_includes_constitutional_hash(self) -> None:
        c = Constitution.default()
        config = create_gitlab_ci_config(c)
        assert c.hash in config

    def test_merge_request_event_rule(self) -> None:
        config = create_gitlab_ci_config()
        assert "merge_request_event" in config


# ---------------------------------------------------------------------------
# GitLabGovernanceBot tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestGitLabGovernanceBot:
    """Tests for GitLabGovernanceBot using mocked HTTP layer."""

    def test_init_stores_config(self, bot: GitLabGovernanceBot) -> None:
        assert bot._project_id == 100
        assert bot._base_url == "https://gitlab.example.com/api/v4"
        assert bot._timeout == 5.0

    def test_headers_include_token(self, bot: GitLabGovernanceBot) -> None:
        headers = bot._headers()
        assert headers["PRIVATE-TOKEN"] == "glpat-test-token"
        assert headers["Content-Type"] == "application/json"

    def test_project_url(self, bot: GitLabGovernanceBot) -> None:
        url = bot._project_url("merge_requests/42")
        assert url == "https://gitlab.example.com/api/v4/projects/100/merge_requests/42"

    def test_base_url_trailing_slash_stripped(self, constitution: Constitution) -> None:
        b = GitLabGovernanceBot(
            token="t",
            project_id=1,
            constitution=constitution,
            base_url="https://example.com/api/v4/",
        )
        assert b._base_url == "https://example.com/api/v4"

    def test_default_constitution_when_none(self) -> None:
        b = GitLabGovernanceBot(token="t", project_id=1, constitution=None)
        assert b.constitution is not None
        assert len(b.constitution.rules) > 0

    def test_httpx_import_guard(self) -> None:
        with (
            patch("acgs_lite.integrations.gitlab.HTTPX_AVAILABLE", False),
            pytest.raises(ImportError, match="httpx is required"),
        ):
            GitLabGovernanceBot(token="t", project_id=1)

    @pytest.mark.asyncio
    async def test_get_calls_httpx(self, bot: GitLabGovernanceBot) -> None:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": 42}
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("acgs_lite.integrations.gitlab.httpx.AsyncClient", return_value=mock_client):
            result = await bot._get("merge_requests/42")

        assert result == {"id": 42}
        mock_client.get.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_post_calls_httpx(self, bot: GitLabGovernanceBot) -> None:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": 1}
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("acgs_lite.integrations.gitlab.httpx.AsyncClient", return_value=mock_client):
            result = await bot._post("merge_requests/42/notes", {"body": "hello"})

        assert result == {"id": 1}
        mock_client.post.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_validate_merge_request_clean(
        self,
        bot: GitLabGovernanceBot,
        clean_mr_data: dict[str, Any],
        clean_changes: dict[str, Any],
    ) -> None:
        call_count = 0

        async def mock_get(path: str) -> Any:
            nonlocal call_count
            call_count += 1
            if "changes" in path:
                return clean_changes
            return clean_mr_data

        bot._get = mock_get  # type: ignore[assignment]

        report = await bot.validate_merge_request(42)

        assert report.passed is True
        assert report.mr_iid == 42
        assert report.title == "feat: add health check endpoint"
        assert len(report.violations) == 0
        assert report.rules_checked > 0
        assert report.constitutional_hash == bot.constitution.hash

    @pytest.mark.asyncio
    async def test_validate_merge_request_with_violations(
        self,
        bot: GitLabGovernanceBot,
        violating_mr_data: dict[str, Any],
        violating_changes: dict[str, Any],
    ) -> None:
        async def mock_get(path: str) -> Any:
            if "changes" in path:
                return violating_changes
            return violating_mr_data

        bot._get = mock_get  # type: ignore[assignment]

        report = await bot.validate_merge_request(99)

        assert report.passed is False
        assert len(report.violations) > 0
        assert report.risk_score > 0.0
        # Check audit log was recorded
        entries = bot.audit_log.query(entry_type="gitlab_mr_validation")
        assert len(entries) >= 1

    @pytest.mark.asyncio
    async def test_post_governance_comment(self, bot: GitLabGovernanceBot) -> None:
        post_called_with: dict[str, Any] = {}

        async def mock_post(path: str, json_body: dict[str, Any]) -> Any:
            post_called_with["path"] = path
            post_called_with["body"] = json_body
            return {"id": 1}

        bot._post = mock_post  # type: ignore[assignment]

        report = GovernanceReport(
            mr_iid=42,
            title="Test MR",
            passed=True,
            risk_score=0.0,
            rules_checked=5,
        )
        await bot.post_governance_comment(42, report)

        assert "merge_requests/42/notes" in post_called_with["path"]
        assert "Governance Report" in post_called_with["body"]["body"]

    @pytest.mark.asyncio
    async def test_post_inline_violations(self, bot: GitLabGovernanceBot) -> None:
        mr_data = {
            "diff_refs": {"head_sha": "head123", "base_sha": "base456"},
        }

        async def mock_get(path: str) -> Any:
            return mr_data

        posted: list[dict[str, Any]] = []

        async def mock_post(path: str, json_body: dict[str, Any]) -> Any:
            posted.append({"path": path, "body": json_body})
            return {"id": len(posted)}

        bot._get = mock_get  # type: ignore[assignment]
        bot._post = mock_post  # type: ignore[assignment]

        violations = [
            {
                "rule_id": "ACGS-001",
                "rule_text": "No bypass",
                "severity": "critical",
                "matched_content": "bypass",
                "file": "src/x.py",
                "line": 10,
            },
            {
                "rule_id": "ACGS-002",
                "rule_text": "Warn",
                "severity": "high",
                "matched_content": "warn",
                "file": None,
                "line": None,
            },
        ]

        results = await bot.post_inline_violations(42, violations)

        # Only the first violation has file+line, so only one discussion posted
        assert len(results) == 1
        assert "discussions" in posted[0]["path"]
        assert posted[0]["body"]["position"]["head_sha"] == "head123"
        assert posted[0]["body"]["position"]["new_line"] == 10

    @pytest.mark.asyncio
    async def test_post_inline_violations_exception_handling(
        self, bot: GitLabGovernanceBot
    ) -> None:
        mr_data = {"diff_refs": {"head_sha": "h", "base_sha": "b"}}

        async def mock_get(path: str) -> Any:
            return mr_data

        async def mock_post(path: str, json_body: dict[str, Any]) -> Any:
            raise ConnectionError("network down")

        bot._get = mock_get  # type: ignore[assignment]
        bot._post = mock_post  # type: ignore[assignment]

        violations = [
            {
                "rule_id": "R1",
                "rule_text": "t",
                "severity": "high",
                "matched_content": "m",
                "file": "a.py",
                "line": 1,
            }
        ]
        # Should not raise; failures are logged and skipped
        results = await bot.post_inline_violations(42, violations)
        assert results == []

    @pytest.mark.asyncio
    async def test_approve_or_block_approved(self, bot: GitLabGovernanceBot) -> None:
        posted: list[dict[str, Any]] = []

        async def mock_post(path: str, json_body: dict[str, Any]) -> Any:
            posted.append({"path": path})
            return {"id": 1}

        bot._post = mock_post  # type: ignore[assignment]

        report = GovernanceReport(mr_iid=42, title="t", passed=True, risk_score=0.0)
        result = await bot.approve_or_block(42, report)

        assert result["action"] == "approved"
        assert "approve" in posted[0]["path"]

    @pytest.mark.asyncio
    async def test_approve_or_block_blocked(self, bot: GitLabGovernanceBot) -> None:
        posted: list[dict[str, Any]] = []

        async def mock_post(path: str, json_body: dict[str, Any]) -> Any:
            posted.append({"path": path, "body": json_body})
            return {"id": 1}

        bot._post = mock_post  # type: ignore[assignment]

        report = GovernanceReport(
            mr_iid=42,
            title="t",
            passed=False,
            risk_score=0.8,
            violations=[{"severity": "critical"}],
        )
        result = await bot.approve_or_block(42, report)

        assert result["action"] == "blocked"
        assert "notes" in posted[0]["path"]
        assert "Merge Blocked" in posted[0]["body"]["body"]

    @pytest.mark.asyncio
    async def test_approve_or_block_approve_failure(self, bot: GitLabGovernanceBot) -> None:
        async def mock_post(path: str, json_body: dict[str, Any]) -> Any:
            raise ConnectionError("API down")

        bot._post = mock_post  # type: ignore[assignment]

        report = GovernanceReport(mr_iid=42, title="t", passed=True, risk_score=0.0)
        result = await bot.approve_or_block(42, report)
        assert result["action"] == "approve_failed"

    @pytest.mark.asyncio
    async def test_validate_commit_messages(self, bot: GitLabGovernanceBot) -> None:
        commits = [
            {"id": "aabbccdd11223344", "message": "feat: add endpoint"},
            {"id": "eeff001122334455", "message": "bypass validation self-validate"},
            {"id": "1122334455667788", "message": "chore: update deps"},
        ]

        async def mock_get(path: str) -> Any:
            return commits

        bot._get = mock_get  # type: ignore[assignment]

        result = await bot.validate_commit_messages(42)

        # Only the second commit should have violations
        assert len(result) == 1
        assert result[0]["sha"] == "eeff0011"
        assert len(result[0]["violations"]) > 0

    @pytest.mark.asyncio
    async def test_run_governance_pipeline_clean(
        self,
        bot: GitLabGovernanceBot,
        clean_mr_data: dict[str, Any],
        clean_changes: dict[str, Any],
    ) -> None:
        async def mock_get(path: str) -> Any:
            if "commits" in path:
                return [{"id": "aabb112233445566", "message": "feat: clean commit"}]
            if "changes" in path:
                return clean_changes
            return clean_mr_data

        posted: list[str] = []

        async def mock_post(path: str, json_body: dict[str, Any]) -> Any:
            posted.append(path)
            return {"id": 1}

        bot._get = mock_get  # type: ignore[assignment]
        bot._post = mock_post  # type: ignore[assignment]

        report = await bot.run_governance_pipeline(42)

        assert report.passed is True
        assert report.mr_iid == 42
        # Should have posted governance comment and approved
        assert any("notes" in p for p in posted)
        assert any("approve" in p for p in posted)

    @pytest.mark.asyncio
    async def test_run_governance_pipeline_with_violations(
        self,
        bot: GitLabGovernanceBot,
        violating_mr_data: dict[str, Any],
        violating_changes: dict[str, Any],
    ) -> None:
        async def mock_get(path: str) -> Any:
            if "commits" in path:
                return [{"id": "cc11223344556677", "message": "clean commit message"}]
            if "changes" in path:
                return violating_changes
            return violating_mr_data

        posted: list[str] = []

        async def mock_post(path: str, json_body: dict[str, Any]) -> Any:
            posted.append(path)
            return {"id": 1}

        bot._get = mock_get  # type: ignore[assignment]
        bot._post = mock_post  # type: ignore[assignment]

        report = await bot.run_governance_pipeline(99)

        assert report.passed is False
        assert len(report.violations) > 0
        # Should have posted inline violations and a block note
        assert any("discussions" in p for p in posted)
        assert any("notes" in p for p in posted)

    @pytest.mark.asyncio
    async def test_run_governance_pipeline_with_commit_violations(
        self,
        bot: GitLabGovernanceBot,
        clean_mr_data: dict[str, Any],
        clean_changes: dict[str, Any],
    ) -> None:
        async def mock_get(path: str) -> Any:
            if "commits" in path:
                return [{"id": "dd11223344556677", "message": "bypass validation commit"}]
            if "changes" in path:
                return clean_changes
            return clean_mr_data

        posted: list[str] = []

        async def mock_post(path: str, json_body: dict[str, Any]) -> Any:
            posted.append(path)
            return {"id": 1}

        bot._get = mock_get  # type: ignore[assignment]
        bot._post = mock_post  # type: ignore[assignment]

        report = await bot.run_governance_pipeline(42)

        # MR content is clean but commit message has violations
        assert report.passed is False
        assert len(report.commit_violations) > 0

    def test_validate_text_restores_strict(self, bot: GitLabGovernanceBot) -> None:
        bot.engine.strict = True
        bot._validate_text("bypass validation", agent_id="test")
        assert bot.engine.strict is True

    def test_stats_property(self, bot: GitLabGovernanceBot) -> None:
        stats = bot.stats
        assert "project_id" in stats
        assert stats["project_id"] == 100
        assert "audit_chain_valid" in stats


# ---------------------------------------------------------------------------
# GitLabWebhookHandler tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestGitLabWebhookHandler:
    """Tests for the webhook handler with mocked bot and request objects."""

    WEBHOOK_SECRET = "test-secret-token"

    @pytest.fixture
    def handler(self, bot: GitLabGovernanceBot) -> GitLabWebhookHandler:
        return GitLabWebhookHandler(
            webhook_secret=self.WEBHOOK_SECRET,
            bot=bot,
        )

    def test_verify_signature_valid(self, handler: GitLabWebhookHandler) -> None:
        assert handler.verify_signature(self.WEBHOOK_SECRET) is True

    def test_verify_signature_invalid(self, handler: GitLabWebhookHandler) -> None:
        assert handler.verify_signature("wrong-secret") is False

    def test_verify_signature_empty(self, handler: GitLabWebhookHandler) -> None:
        assert handler.verify_signature("") is False

    @pytest.mark.asyncio
    async def test_route_event_unsupported(self, handler: GitLabWebhookHandler) -> None:
        result = await handler._route_event("Push Hook", {})
        assert result["action"] == "ignored"
        assert "unsupported" in result["reason"]

    @pytest.mark.asyncio
    async def test_route_event_merge_request(self, handler: GitLabWebhookHandler) -> None:
        body = {
            "object_attributes": {"action": "unsupported_action", "iid": 42},
        }
        result = await handler._route_event("Merge Request Hook", body)
        assert result["status"] == "skipped"

    @pytest.mark.asyncio
    async def test_handle_merge_request_open(
        self,
        handler: GitLabWebhookHandler,
        clean_mr_data: dict[str, Any],
        clean_changes: dict[str, Any],
    ) -> None:
        async def mock_get(path: str) -> Any:
            if "commits" in path:
                return [{"id": "aa11223344556677", "message": "clean"}]
            if "changes" in path:
                return clean_changes
            return clean_mr_data

        async def mock_post(path: str, json_body: dict[str, Any]) -> Any:
            return {"id": 1}

        handler._bot._get = mock_get  # type: ignore[assignment]
        handler._bot._post = mock_post  # type: ignore[assignment]

        body = {"object_attributes": {"action": "open", "iid": 42}}
        result = await handler._handle_merge_request(body)

        assert result["event"] == "merge_request"
        assert result["action"] == "open"
        assert "governance_passed" in result

    @pytest.mark.asyncio
    async def test_handle_merge_request_approved(
        self,
        handler: GitLabWebhookHandler,
        clean_mr_data: dict[str, Any],
        clean_changes: dict[str, Any],
    ) -> None:
        async def mock_get(path: str) -> Any:
            if "changes" in path:
                return clean_changes
            return clean_mr_data

        handler._bot._get = mock_get  # type: ignore[assignment]

        body = {"object_attributes": {"action": "approved", "iid": 42}}
        result = await handler._handle_merge_request(body)

        assert result["action"] == "approved"
        assert "post_approval_valid" in result

    @pytest.mark.asyncio
    async def test_handle_merge_request_merge_noted(self, handler: GitLabWebhookHandler) -> None:
        body = {"object_attributes": {"action": "merge", "iid": 42}}
        result = await handler._handle_merge_request(body)
        assert result["status"] == "noted"

    @pytest.mark.asyncio
    async def test_handle_merge_request_missing_iid(self, handler: GitLabWebhookHandler) -> None:
        body = {"object_attributes": {"action": "open"}}
        result = await handler._handle_merge_request(body)
        assert result["status"] == "skipped"

    @pytest.mark.asyncio
    async def test_handle_pipeline_success(
        self,
        handler: GitLabWebhookHandler,
        clean_mr_data: dict[str, Any],
        clean_changes: dict[str, Any],
    ) -> None:
        async def mock_get(path: str) -> Any:
            if "changes" in path:
                return clean_changes
            return clean_mr_data

        handler._bot._get = mock_get  # type: ignore[assignment]

        body = {
            "object_attributes": {"status": "success"},
            "merge_request": {"iid": 42},
        }
        result = await handler._handle_pipeline(body)

        assert result["event"] == "pipeline"
        assert result["status"] == "success"
        assert "governance_passed" in result

    @pytest.mark.asyncio
    async def test_handle_pipeline_no_mr(self, handler: GitLabWebhookHandler) -> None:
        body = {"object_attributes": {"status": "success"}}
        result = await handler._handle_pipeline(body)
        assert result["action"] == "skipped"

    @pytest.mark.asyncio
    async def test_handle_pipeline_unsupported_status(self, handler: GitLabWebhookHandler) -> None:
        body = {
            "object_attributes": {"status": "running"},
            "merge_request": {"iid": 42},
        }
        result = await handler._handle_pipeline(body)
        assert result["action"] == "skipped"

    @pytest.mark.asyncio
    async def test_handle_pipeline_failed_noted(self, handler: GitLabWebhookHandler) -> None:
        body = {
            "object_attributes": {"status": "failed"},
            "merge_request": {"iid": 42},
        }
        result = await handler._handle_pipeline(body)
        assert result["action"] == "noted"

    @pytest.mark.asyncio
    async def test_handle_webhook_invalid_token(self, handler: GitLabWebhookHandler) -> None:
        """Full handle() path with invalid token returns 401."""
        mock_request = MagicMock()
        mock_request.headers = {"X-Gitlab-Token": "wrong", "X-Gitlab-Event": "Merge Request Hook"}
        mock_request.json = AsyncMock(return_value={})

        # Need starlette JSONResponse
        try:
            import starlette  # noqa: F401

            response = await handler.handle(mock_request)
            assert response.status_code == 401
        except ImportError:
            pytest.skip("starlette not installed")

    @pytest.mark.asyncio
    async def test_handle_webhook_valid_token(
        self,
        handler: GitLabWebhookHandler,
        clean_mr_data: dict[str, Any],
        clean_changes: dict[str, Any],
    ) -> None:
        """Full handle() path with valid token processes event."""
        try:
            import starlette  # noqa: F401
        except ImportError:
            pytest.skip("starlette not installed")

        async def mock_get(path: str) -> Any:
            if "commits" in path:
                return [{"id": "ff11223344556677", "message": "ok"}]
            if "changes" in path:
                return clean_changes
            return clean_mr_data

        async def mock_post(path: str, json_body: dict[str, Any]) -> Any:
            return {"id": 1}

        handler._bot._get = mock_get  # type: ignore[assignment]
        handler._bot._post = mock_post  # type: ignore[assignment]

        mock_request = MagicMock()
        mock_request.headers = {
            "X-Gitlab-Token": self.WEBHOOK_SECRET,
            "X-Gitlab-Event": "Merge Request Hook",
        }
        mock_request.json = AsyncMock(
            return_value={"object_attributes": {"action": "open", "iid": 42}}
        )

        response = await handler.handle(mock_request)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_handle_webhook_processing_error(self, handler: GitLabWebhookHandler) -> None:
        """Exception during event routing returns 500."""
        try:
            import starlette  # noqa: F401
        except ImportError:
            pytest.skip("starlette not installed")

        # Make _route_event raise, not request.json()
        async def broken_route(event_type: str, body: dict[str, Any]) -> Any:
            raise RuntimeError("processing exploded")

        handler._route_event = broken_route  # type: ignore[assignment]

        mock_request = MagicMock()
        mock_request.headers = {
            "X-Gitlab-Token": self.WEBHOOK_SECRET,
            "X-Gitlab-Event": "Merge Request Hook",
        }
        mock_request.json = AsyncMock(
            return_value={"object_attributes": {"action": "open", "iid": 1}}
        )

        response = await handler.handle(mock_request)
        assert response.status_code == 500


# ---------------------------------------------------------------------------
# GitLabMACIEnforcer tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestGitLabMACIEnforcer:
    """Tests for MACI separation of powers enforcement."""

    @pytest.fixture
    def maci_enforcer(self) -> GitLabMACIEnforcer:
        return GitLabMACIEnforcer(audit_log=AuditLog())

    @pytest.mark.asyncio
    async def test_check_mr_separation_valid(
        self,
        maci_enforcer: GitLabMACIEnforcer,
        bot: GitLabGovernanceBot,
    ) -> None:
        async def mock_get(path: str) -> Any:
            if "approvals" in path:
                return {"approved_by": [{"user": {"username": "reviewer"}}]}
            return {"author": {"username": "dev-user"}}

        bot._get = mock_get  # type: ignore[assignment]

        result = await maci_enforcer.check_mr_separation(bot, mr_iid=42)

        assert result["separation_valid"] is True
        assert result["author"] == "dev-user"
        assert "reviewer" in result["approvers"]
        assert len(result["violations"]) == 0

    @pytest.mark.asyncio
    async def test_check_mr_separation_self_approval(
        self,
        maci_enforcer: GitLabMACIEnforcer,
        bot: GitLabGovernanceBot,
    ) -> None:
        async def mock_get(path: str) -> Any:
            if "approvals" in path:
                return {"approved_by": [{"user": {"username": "dev-user"}}]}
            return {"author": {"username": "dev-user"}}

        bot._get = mock_get  # type: ignore[assignment]

        result = await maci_enforcer.check_mr_separation(bot, mr_iid=42)

        assert result["separation_valid"] is False
        assert len(result["violations"]) == 1
        assert result["violations"][0]["type"] == "self_approval"
        assert "dev-user" in result["violations"][0]["message"]

    @pytest.mark.asyncio
    async def test_check_mr_no_approvers(
        self,
        maci_enforcer: GitLabMACIEnforcer,
        bot: GitLabGovernanceBot,
    ) -> None:
        async def mock_get(path: str) -> Any:
            if "approvals" in path:
                return {"approved_by": []}
            return {"author": {"username": "dev-user"}}

        bot._get = mock_get  # type: ignore[assignment]

        result = await maci_enforcer.check_mr_separation(bot, mr_iid=42)

        assert result["separation_valid"] is True
        assert result["approvers"] == []

    @pytest.mark.asyncio
    async def test_check_mr_empty_username_approver(
        self,
        maci_enforcer: GitLabMACIEnforcer,
        bot: GitLabGovernanceBot,
    ) -> None:
        async def mock_get(path: str) -> Any:
            if "approvals" in path:
                return {"approved_by": [{"user": {"username": ""}}]}
            return {"author": {"username": "dev-user"}}

        bot._get = mock_get  # type: ignore[assignment]

        result = await maci_enforcer.check_mr_separation(bot, mr_iid=42)
        assert result["separation_valid"] is True

    @pytest.mark.asyncio
    async def test_audit_log_recorded(
        self,
        maci_enforcer: GitLabMACIEnforcer,
        bot: GitLabGovernanceBot,
    ) -> None:
        async def mock_get(path: str) -> Any:
            if "approvals" in path:
                return {"approved_by": []}
            return {"author": {"username": "dev-user"}}

        bot._get = mock_get  # type: ignore[assignment]

        await maci_enforcer.check_mr_separation(bot, mr_iid=42)

        entries = bot.audit_log.query(entry_type="maci_mr_check")
        assert len(entries) >= 1
        assert entries[-1].agent_id == "gitlab-maci-enforcer"

    @pytest.mark.asyncio
    async def test_post_maci_violation(
        self,
        maci_enforcer: GitLabMACIEnforcer,
        bot: GitLabGovernanceBot,
    ) -> None:
        posted: list[dict[str, Any]] = []

        async def mock_post(path: str, json_body: dict[str, Any]) -> Any:
            posted.append({"path": path, "body": json_body})
            return {"id": 1}

        bot._post = mock_post  # type: ignore[assignment]

        violations = [
            {
                "type": "self_approval",
                "agent": "dev-user",
                "message": "dev-user authored and approved MR !42",
            }
        ]
        await maci_enforcer.post_maci_violation(bot, mr_iid=42, violations=violations)

        assert len(posted) == 1
        assert "notes" in posted[0]["path"]
        body_text = posted[0]["body"]["body"]
        assert "MACI Separation of Powers Violation" in body_text
        assert "ACGS-004" in body_text
        assert "self_approval" in body_text

    def test_role_map(self) -> None:
        from acgs_lite.maci import MACIRole

        enforcer = GitLabMACIEnforcer()
        assert enforcer._ROLE_MAP["author"] == MACIRole.PROPOSER
        assert enforcer._ROLE_MAP["reviewer"] == MACIRole.VALIDATOR
        assert enforcer._ROLE_MAP["approver"] == MACIRole.VALIDATOR
        assert enforcer._ROLE_MAP["merger"] == MACIRole.EXECUTOR
