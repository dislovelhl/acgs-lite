"""Tests for acgs_lite.integrations.github module.

Exercises the real GitHubGovernanceBot, GitHubWebhookHandler,
GitHubMACIEnforcer classes plus helper functions with mocked HTTP layer.
No real network or database calls.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from acgs_lite import AuditLog, Constitution, Rule, Severity
from acgs_lite.integrations.github import (
    GitHubGovernanceBot,
    GitHubMACIEnforcer,
    GitHubWebhookHandler,
    GovernanceReport,
    _compute_risk_score,
    _parse_added_lines,
    create_github_actions_config,
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
def bot(constitution: Constitution) -> GitHubGovernanceBot:
    """GitHubGovernanceBot with mocked HTTP so no real requests are made."""
    return GitHubGovernanceBot(
        token="ghp_test-token",
        repo="acme/governance",
        constitution=constitution,
        base_url="https://api.github.example.com",
        timeout=5.0,
        strict=False,
    )


@pytest.fixture
def clean_pr_data() -> dict[str, Any]:
    """PR data dict simulating a clean pull request."""
    return {
        "number": 42,
        "title": "feat: add health check endpoint",
        "body": "Adds /health for monitoring.",
        "user": {"login": "dev-user"},
    }


@pytest.fixture
def clean_files() -> list[dict[str, Any]]:
    """Files payload with harmless patch content."""
    return [
        {
            "filename": "src/app.py",
            "patch": (
                "@@ -1,3 +1,5 @@\n"
                "+def health():\n"
                "+    return 'ok'\n"
                " # existing\n"
            ),
        }
    ]


@pytest.fixture
def violating_pr_data() -> dict[str, Any]:
    """PR data dict whose title triggers a violation."""
    return {
        "number": 99,
        "title": "feat: self-validate bypass all checks",
        "body": "Let agents self-approve their own outputs.",
        "user": {"login": "bad-actor"},
    }


@pytest.fixture
def violating_files() -> list[dict[str, Any]]:
    return [
        {
            "filename": "src/evil.py",
            "patch": (
                "@@ -0,0 +1,2 @@\n"
                "+bypass validation here\n"
                "+safe line\n"
            ),
        }
    ]


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
        assert len(result) == 2
        assert result[0][1] == "content"
        assert result[1][1] == "more"

    def test_ignores_deleted_lines(self) -> None:
        diff = "@@ -1,3 +1,2 @@\n-removed\n context\n+added\n"
        result = _parse_added_lines(diff)
        assert len(result) == 1
        assert result[0][1] == "added"

    def test_multiple_hunks(self) -> None:
        diff = (
            "@@ -1,2 +1,3 @@\n"
            " ctx\n"
            "+first add\n"
            "@@ -10,2 +11,3 @@\n"
            " ctx\n"
            "+second add\n"
        )
        result = _parse_added_lines(diff)
        assert len(result) == 2
        assert result[0][1] == "first add"
        assert result[1][1] == "second add"

    def test_empty_diff(self) -> None:
        assert _parse_added_lines("") == []

    def test_no_hunk_header(self) -> None:
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

    def test_warnings_reduce_risk(self) -> None:
        v_only = _compute_risk_score([{"severity": "high"}], [])
        w_only = _compute_risk_score([], [{"severity": "high"}])
        assert w_only < v_only


# ---------------------------------------------------------------------------
# GovernanceReport tests
# ---------------------------------------------------------------------------


class TestGovernanceReport:
    """Tests for the frozen GovernanceReport dataclass."""

    def test_immutable(self) -> None:
        report = GovernanceReport(
            pr_number=1, title="t", passed=True, risk_score=0.0
        )
        with pytest.raises(AttributeError):
            report.passed = False  # type: ignore[misc]

    def test_defaults(self) -> None:
        report = GovernanceReport(
            pr_number=1, title="t", passed=True, risk_score=0.0
        )
        assert report.violations == []
        assert report.warnings == []
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
            pr_number=1,
            title="Clean PR",
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
            pr_number=2,
            title="Bad PR",
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
            pr_number=3,
            title="Warn PR",
            passed=True,
            risk_score=0.1,
            warnings=[
                {
                    "rule_id": "W-001",
                    "rule_text": "Minor issue",
                    "severity": "low",
                }
            ],
        )
        md = format_governance_report(report)
        assert "### Warnings" in md
        assert "W-001" in md

    def test_footer_present(self) -> None:
        report = GovernanceReport(
            pr_number=1, title="t", passed=True, risk_score=0.0
        )
        md = format_governance_report(report)
        assert "ACGS Governance Bot" in md

    def test_table_structure(self) -> None:
        report = GovernanceReport(
            pr_number=1, title="t", passed=True, risk_score=0.5,
            rules_checked=10, constitutional_hash="608508a9bd224290",
        )
        md = format_governance_report(report)
        assert "| Field | Value |" in md
        assert "| Risk Score |" in md


# ---------------------------------------------------------------------------
# create_github_actions_config tests
# ---------------------------------------------------------------------------


class TestCreateGitHubActionsConfig:
    """Tests for the GitHub Actions config generator."""

    def test_generates_yaml_string(self) -> None:
        config = create_github_actions_config()
        assert isinstance(config, str)
        assert "name: Governance" in config
        assert "pull_request:" in config
        assert "pip install acgs[github]" in config

    def test_includes_constitutional_hash(self) -> None:
        c = Constitution.default()
        config = create_github_actions_config(c)
        assert c.hash in config

    def test_pull_request_trigger(self) -> None:
        config = create_github_actions_config()
        assert "opened" in config
        assert "synchronize" in config
        assert "reopened" in config

    def test_uses_actions_checkout(self) -> None:
        config = create_github_actions_config()
        assert "actions/checkout@v4" in config

    def test_uses_setup_python(self) -> None:
        config = create_github_actions_config()
        assert "actions/setup-python@v5" in config

    def test_permissions_section(self) -> None:
        config = create_github_actions_config()
        assert "permissions:" in config
        assert "pull-requests: write" in config

    def test_custom_constitution_hash_included(self) -> None:
        c = Constitution.from_rules(
            [Rule(id="T-1", text="Test", severity=Severity.LOW, keywords=["x"])]
        )
        config = create_github_actions_config(c)
        assert c.hash in config


# ---------------------------------------------------------------------------
# GitHubGovernanceBot tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestGitHubGovernanceBot:
    """Tests for GitHubGovernanceBot using mocked HTTP layer."""

    def test_init_stores_config(self, bot: GitHubGovernanceBot) -> None:
        assert bot._repo == "acme/governance"
        assert bot._base_url == "https://api.github.example.com"
        assert bot._timeout == 5.0

    def test_headers_include_token(self, bot: GitHubGovernanceBot) -> None:
        headers = bot._headers()
        assert headers["Authorization"] == "Bearer ghp_test-token"
        assert "application/vnd.github+json" in headers["Accept"]

    def test_repo_url(self, bot: GitHubGovernanceBot) -> None:
        url = bot._repo_url("pulls/42")
        expected = (
            "https://api.github.example.com/repos/acme/governance/pulls/42"
        )
        assert url == expected

    def test_base_url_trailing_slash_stripped(
        self, constitution: Constitution
    ) -> None:
        b = GitHubGovernanceBot(
            token="t",
            repo="a/b",
            constitution=constitution,
            base_url="https://example.com/",
        )
        assert b._base_url == "https://example.com"

    def test_default_constitution_when_none(self) -> None:
        b = GitHubGovernanceBot(
            token="t", repo="a/b", constitution=None
        )
        assert b.constitution is not None
        assert len(b.constitution.rules) > 0

    def test_httpx_import_guard(self) -> None:
        with (
            patch(
                "acgs_lite.integrations.github.HTTPX_AVAILABLE", False
            ),
            pytest.raises(ImportError, match="httpx is required"),
        ):
            GitHubGovernanceBot(token="t", repo="a/b")

    @pytest.mark.asyncio
    async def test_get_calls_httpx(
        self, bot: GitHubGovernanceBot
    ) -> None:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": 42}
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "acgs_lite.integrations.github.httpx.AsyncClient",
            return_value=mock_client,
        ):
            result = await bot._get("pulls/42")

        assert result == {"id": 42}
        mock_client.get.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_post_calls_httpx(
        self, bot: GitHubGovernanceBot
    ) -> None:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": 1}
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "acgs_lite.integrations.github.httpx.AsyncClient",
            return_value=mock_client,
        ):
            result = await bot._post(
                "issues/42/comments", {"body": "hello"}
            )

        assert result == {"id": 1}
        mock_client.post.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_validate_pull_request_clean(
        self,
        bot: GitHubGovernanceBot,
        clean_pr_data: dict[str, Any],
        clean_files: list[dict[str, Any]],
    ) -> None:
        call_count = 0

        async def mock_get(path: str) -> Any:
            nonlocal call_count
            call_count += 1
            if "files" in path:
                return clean_files
            return clean_pr_data

        bot._get = mock_get  # type: ignore[assignment]

        report = await bot.validate_pull_request(42)

        assert report.passed is True
        assert report.pr_number == 42
        assert report.title == "feat: add health check endpoint"
        assert len(report.violations) == 0
        assert report.rules_checked > 0
        assert report.constitutional_hash == bot.constitution.hash

    @pytest.mark.asyncio
    async def test_validate_pull_request_with_violations(
        self,
        bot: GitHubGovernanceBot,
        violating_pr_data: dict[str, Any],
        violating_files: list[dict[str, Any]],
    ) -> None:
        async def mock_get(path: str) -> Any:
            if "files" in path:
                return violating_files
            return violating_pr_data

        bot._get = mock_get  # type: ignore[assignment]

        report = await bot.validate_pull_request(99)

        assert report.passed is False
        assert len(report.violations) > 0
        assert report.risk_score > 0.0
        # Check audit log was recorded
        entries = bot.audit_log.query(entry_type="github_pr_validation")
        assert len(entries) >= 1

    @pytest.mark.asyncio
    async def test_post_governance_comment(
        self, bot: GitHubGovernanceBot
    ) -> None:
        post_called_with: dict[str, Any] = {}

        async def mock_post(
            path: str, json_body: dict[str, Any]
        ) -> Any:
            post_called_with["path"] = path
            post_called_with["body"] = json_body
            return {"id": 1}

        bot._post = mock_post  # type: ignore[assignment]

        report = GovernanceReport(
            pr_number=42,
            title="Test PR",
            passed=True,
            risk_score=0.0,
            rules_checked=5,
        )
        await bot.post_governance_comment(42, report)

        assert "issues/42/comments" in post_called_with["path"]
        assert "Governance Report" in post_called_with["body"]["body"]

    @pytest.mark.asyncio
    async def test_run_governance_pipeline_clean(
        self,
        bot: GitHubGovernanceBot,
        clean_pr_data: dict[str, Any],
        clean_files: list[dict[str, Any]],
    ) -> None:
        async def mock_get(path: str) -> Any:
            if "files" in path:
                return clean_files
            return clean_pr_data

        posted: list[str] = []

        async def mock_post(
            path: str, json_body: dict[str, Any]
        ) -> Any:
            posted.append(path)
            return {"id": 1}

        bot._get = mock_get  # type: ignore[assignment]
        bot._post = mock_post  # type: ignore[assignment]

        report = await bot.run_governance_pipeline(42)

        assert report.passed is True
        assert report.pr_number == 42
        # Should have posted governance comment
        assert any("comments" in p for p in posted)

    @pytest.mark.asyncio
    async def test_run_governance_pipeline_with_violations(
        self,
        bot: GitHubGovernanceBot,
        violating_pr_data: dict[str, Any],
        violating_files: list[dict[str, Any]],
    ) -> None:
        async def mock_get(path: str) -> Any:
            if "files" in path:
                return violating_files
            return violating_pr_data

        posted: list[str] = []

        async def mock_post(
            path: str, json_body: dict[str, Any]
        ) -> Any:
            posted.append(path)
            return {"id": 1}

        bot._get = mock_get  # type: ignore[assignment]
        bot._post = mock_post  # type: ignore[assignment]

        report = await bot.run_governance_pipeline(99)

        assert report.passed is False
        assert len(report.violations) > 0
        # Should have posted governance comment
        assert any("comments" in p for p in posted)

    def test_validate_text_restores_strict(
        self, bot: GitHubGovernanceBot
    ) -> None:
        bot.engine.strict = True
        bot._validate_text("bypass validation", agent_id="test")
        assert bot.engine.strict is True

    def test_stats_property(self, bot: GitHubGovernanceBot) -> None:
        stats = bot.stats
        assert "repo" in stats
        assert stats["repo"] == "acme/governance"
        assert "audit_chain_valid" in stats

    @pytest.mark.asyncio
    async def test_validate_pr_empty_body(
        self, bot: GitHubGovernanceBot, clean_files: list[dict[str, Any]],
    ) -> None:
        pr_data = {
            "number": 10,
            "title": "feat: minor",
            "body": None,
            "user": {"login": "dev"},
        }

        async def mock_get(path: str) -> Any:
            if "files" in path:
                return clean_files
            return pr_data

        bot._get = mock_get  # type: ignore[assignment]

        report = await bot.validate_pull_request(10)
        assert report.passed is True

    @pytest.mark.asyncio
    async def test_validate_pr_no_patch(
        self, bot: GitHubGovernanceBot,
    ) -> None:
        pr_data = {
            "number": 11,
            "title": "chore: rename",
            "body": "",
            "user": {"login": "dev"},
        }
        files = [{"filename": "renamed.py", "patch": ""}]

        async def mock_get(path: str) -> Any:
            if "files" in path:
                return files
            return pr_data

        bot._get = mock_get  # type: ignore[assignment]

        report = await bot.validate_pull_request(11)
        assert report.passed is True


# ---------------------------------------------------------------------------
# GitHubWebhookHandler tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestGitHubWebhookHandler:
    """Tests for the webhook handler with mocked bot and request objects."""

    WEBHOOK_SECRET = "test-secret-token"

    @pytest.fixture
    def handler(self, bot: GitHubGovernanceBot) -> GitHubWebhookHandler:
        return GitHubWebhookHandler(
            webhook_secret=self.WEBHOOK_SECRET,
            bot=bot,
        )

    def test_verify_signature_valid(
        self, handler: GitHubWebhookHandler
    ) -> None:
        import hashlib
        import hmac as _hmac

        payload = b'{"action": "opened"}'
        digest = _hmac.new(
            self.WEBHOOK_SECRET.encode(), payload, hashlib.sha256
        ).hexdigest()
        signature = f"sha256={digest}"
        assert handler.verify_signature(payload, signature) is True

    def test_verify_signature_invalid(
        self, handler: GitHubWebhookHandler
    ) -> None:
        payload = b'{"action": "opened"}'
        assert (
            handler.verify_signature(payload, "sha256=badhex") is False
        )

    def test_verify_signature_missing_prefix(
        self, handler: GitHubWebhookHandler
    ) -> None:
        payload = b'{"action": "opened"}'
        assert handler.verify_signature(payload, "nope") is False

    def test_verify_signature_empty(
        self, handler: GitHubWebhookHandler
    ) -> None:
        assert handler.verify_signature(b"", "") is False

    @pytest.mark.asyncio
    async def test_route_event_unsupported(
        self, handler: GitHubWebhookHandler
    ) -> None:
        result = await handler._route_event("push", {})
        assert result["action"] == "ignored"
        assert "unsupported" in result["reason"]

    @pytest.mark.asyncio
    async def test_route_event_pull_request_skipped(
        self, handler: GitHubWebhookHandler
    ) -> None:
        body = {
            "action": "closed",
            "pull_request": {"number": 42},
        }
        result = await handler._route_event("pull_request", body)
        assert result["status"] == "skipped"

    @pytest.mark.asyncio
    async def test_handle_pull_request_opened(
        self,
        handler: GitHubWebhookHandler,
        clean_pr_data: dict[str, Any],
        clean_files: list[dict[str, Any]],
    ) -> None:
        async def mock_get(path: str) -> Any:
            if "files" in path:
                return clean_files
            return clean_pr_data

        async def mock_post(
            path: str, json_body: dict[str, Any]
        ) -> Any:
            return {"id": 1}

        handler._bot._get = mock_get  # type: ignore[assignment]
        handler._bot._post = mock_post  # type: ignore[assignment]

        body = {
            "action": "opened",
            "pull_request": {"number": 42},
        }
        result = await handler._handle_pull_request(body)

        assert result["event"] == "pull_request"
        assert result["action"] == "opened"
        assert "governance_passed" in result

    @pytest.mark.asyncio
    async def test_handle_pull_request_synchronize(
        self,
        handler: GitHubWebhookHandler,
        clean_pr_data: dict[str, Any],
        clean_files: list[dict[str, Any]],
    ) -> None:
        async def mock_get(path: str) -> Any:
            if "files" in path:
                return clean_files
            return clean_pr_data

        async def mock_post(
            path: str, json_body: dict[str, Any]
        ) -> Any:
            return {"id": 1}

        handler._bot._get = mock_get  # type: ignore[assignment]
        handler._bot._post = mock_post  # type: ignore[assignment]

        body = {
            "action": "synchronize",
            "pull_request": {"number": 42},
        }
        result = await handler._handle_pull_request(body)

        assert result["event"] == "pull_request"
        assert result["action"] == "synchronize"
        assert "governance_passed" in result

    @pytest.mark.asyncio
    async def test_handle_pull_request_missing_number(
        self, handler: GitHubWebhookHandler
    ) -> None:
        body = {
            "action": "opened",
            "pull_request": {},
        }
        result = await handler._handle_pull_request(body)
        assert result["status"] == "skipped"

    @pytest.mark.asyncio
    async def test_handle_webhook_invalid_signature(
        self, handler: GitHubWebhookHandler
    ) -> None:
        """Full handle() path with invalid signature returns 401."""
        try:
            import starlette  # noqa: F401
        except ImportError:
            pytest.skip("starlette not installed")

        mock_request = MagicMock()
        mock_request.headers = {
            "X-Hub-Signature-256": "sha256=bad",
            "X-GitHub-Event": "pull_request",
        }
        mock_request.body = AsyncMock(return_value=b'{"action":"opened"}')
        mock_request.json = AsyncMock(return_value={})

        response = await handler.handle(mock_request)
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_handle_webhook_valid_signature(
        self,
        handler: GitHubWebhookHandler,
        clean_pr_data: dict[str, Any],
        clean_files: list[dict[str, Any]],
    ) -> None:
        """Full handle() path with valid signature processes event."""
        try:
            import starlette  # noqa: F401
        except ImportError:
            pytest.skip("starlette not installed")

        import hashlib
        import hmac as _hmac

        async def mock_get(path: str) -> Any:
            if "files" in path:
                return clean_files
            return clean_pr_data

        async def mock_post(
            path: str, json_body: dict[str, Any]
        ) -> Any:
            return {"id": 1}

        handler._bot._get = mock_get  # type: ignore[assignment]
        handler._bot._post = mock_post  # type: ignore[assignment]

        payload = b'{"action":"opened","pull_request":{"number":42}}'
        digest = _hmac.new(
            self.WEBHOOK_SECRET.encode(), payload, hashlib.sha256
        ).hexdigest()

        mock_request = MagicMock()
        mock_request.headers = {
            "X-Hub-Signature-256": f"sha256={digest}",
            "X-GitHub-Event": "pull_request",
        }
        mock_request.body = AsyncMock(return_value=payload)
        mock_request.json = AsyncMock(
            return_value={
                "action": "opened",
                "pull_request": {"number": 42},
            }
        )

        response = await handler.handle(mock_request)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_handle_webhook_processing_error(
        self, handler: GitHubWebhookHandler
    ) -> None:
        """Exception during event routing returns 500."""
        try:
            import starlette  # noqa: F401
        except ImportError:
            pytest.skip("starlette not installed")

        import hashlib
        import hmac as _hmac

        # Make _route_event raise
        async def broken_route(
            event_type: str, body: dict[str, Any]
        ) -> Any:
            raise RuntimeError("processing exploded")

        handler._route_event = broken_route  # type: ignore[assignment]

        payload = b'{"action":"opened","pull_request":{"number":1}}'
        digest = _hmac.new(
            self.WEBHOOK_SECRET.encode(), payload, hashlib.sha256
        ).hexdigest()

        mock_request = MagicMock()
        mock_request.headers = {
            "X-Hub-Signature-256": f"sha256={digest}",
            "X-GitHub-Event": "pull_request",
        }
        mock_request.body = AsyncMock(return_value=payload)
        mock_request.json = AsyncMock(
            return_value={
                "action": "opened",
                "pull_request": {"number": 1},
            }
        )

        response = await handler.handle(mock_request)
        assert response.status_code == 500

    @pytest.mark.asyncio
    async def test_handle_pull_request_reopened(
        self,
        handler: GitHubWebhookHandler,
        clean_pr_data: dict[str, Any],
        clean_files: list[dict[str, Any]],
    ) -> None:
        async def mock_get(path: str) -> Any:
            if "files" in path:
                return clean_files
            return clean_pr_data

        async def mock_post(path: str, json_body: dict[str, Any]) -> Any:
            return {"id": 1}

        handler._bot._get = mock_get  # type: ignore[assignment]
        handler._bot._post = mock_post  # type: ignore[assignment]

        body = {
            "action": "reopened",
            "pull_request": {"number": 42},
        }
        result = await handler._handle_pull_request(body)

        assert result["event"] == "pull_request"
        assert result["action"] == "reopened"
        assert result["governance_passed"] is True


# ---------------------------------------------------------------------------
# GitHubMACIEnforcer tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestGitHubMACIEnforcer:
    """Tests for MACI separation of powers enforcement."""

    @pytest.fixture
    def maci_enforcer(self) -> GitHubMACIEnforcer:
        return GitHubMACIEnforcer(audit_log=AuditLog())

    @pytest.mark.asyncio
    async def test_check_pr_separation_valid(
        self,
        maci_enforcer: GitHubMACIEnforcer,
        bot: GitHubGovernanceBot,
    ) -> None:
        async def mock_get(path: str) -> Any:
            if "reviews" in path:
                return [
                    {
                        "user": {"login": "reviewer"},
                        "state": "APPROVED",
                    }
                ]
            return {"user": {"login": "dev-user"}}

        bot._get = mock_get  # type: ignore[assignment]

        result = await maci_enforcer.check_pr_separation(
            bot, pr_number=42
        )

        assert result["separation_valid"] is True
        assert result["author"] == "dev-user"
        assert "reviewer" in result["approvers"]
        assert len(result["violations"]) == 0

    @pytest.mark.asyncio
    async def test_check_pr_separation_self_approval(
        self,
        maci_enforcer: GitHubMACIEnforcer,
        bot: GitHubGovernanceBot,
    ) -> None:
        async def mock_get(path: str) -> Any:
            if "reviews" in path:
                return [
                    {
                        "user": {"login": "dev-user"},
                        "state": "APPROVED",
                    }
                ]
            return {"user": {"login": "dev-user"}}

        bot._get = mock_get  # type: ignore[assignment]

        result = await maci_enforcer.check_pr_separation(
            bot, pr_number=42
        )

        assert result["separation_valid"] is False
        assert len(result["violations"]) == 1
        assert result["violations"][0]["type"] == "self_approval"
        assert "dev-user" in result["violations"][0]["message"]

    @pytest.mark.asyncio
    async def test_check_pr_no_approvers(
        self,
        maci_enforcer: GitHubMACIEnforcer,
        bot: GitHubGovernanceBot,
    ) -> None:
        async def mock_get(path: str) -> Any:
            if "reviews" in path:
                return []
            return {"user": {"login": "dev-user"}}

        bot._get = mock_get  # type: ignore[assignment]

        result = await maci_enforcer.check_pr_separation(
            bot, pr_number=42
        )

        assert result["separation_valid"] is True
        assert result["approvers"] == []

    @pytest.mark.asyncio
    async def test_check_pr_non_approved_review_ignored(
        self,
        maci_enforcer: GitHubMACIEnforcer,
        bot: GitHubGovernanceBot,
    ) -> None:
        """Reviews with state != APPROVED should not count as approvals."""

        async def mock_get(path: str) -> Any:
            if "reviews" in path:
                return [
                    {
                        "user": {"login": "dev-user"},
                        "state": "COMMENTED",
                    }
                ]
            return {"user": {"login": "dev-user"}}

        bot._get = mock_get  # type: ignore[assignment]

        result = await maci_enforcer.check_pr_separation(
            bot, pr_number=42
        )

        assert result["separation_valid"] is True

    @pytest.mark.asyncio
    async def test_check_pr_empty_login_approver(
        self,
        maci_enforcer: GitHubMACIEnforcer,
        bot: GitHubGovernanceBot,
    ) -> None:
        async def mock_get(path: str) -> Any:
            if "reviews" in path:
                return [
                    {"user": {"login": ""}, "state": "APPROVED"}
                ]
            return {"user": {"login": "dev-user"}}

        bot._get = mock_get  # type: ignore[assignment]

        result = await maci_enforcer.check_pr_separation(
            bot, pr_number=42
        )
        assert result["separation_valid"] is True

    @pytest.mark.asyncio
    async def test_audit_log_recorded(
        self,
        maci_enforcer: GitHubMACIEnforcer,
        bot: GitHubGovernanceBot,
    ) -> None:
        async def mock_get(path: str) -> Any:
            if "reviews" in path:
                return []
            return {"user": {"login": "dev-user"}}

        bot._get = mock_get  # type: ignore[assignment]

        await maci_enforcer.check_pr_separation(bot, pr_number=42)

        entries = bot.audit_log.query(entry_type="maci_pr_check")
        assert len(entries) >= 1
        assert entries[-1].agent_id == "github-maci-enforcer"

    @pytest.mark.asyncio
    async def test_post_maci_violation(
        self,
        maci_enforcer: GitHubMACIEnforcer,
        bot: GitHubGovernanceBot,
    ) -> None:
        posted: list[dict[str, Any]] = []

        async def mock_post(
            path: str, json_body: dict[str, Any]
        ) -> Any:
            posted.append({"path": path, "body": json_body})
            return {"id": 1}

        bot._post = mock_post  # type: ignore[assignment]

        violations = [
            {
                "type": "self_approval",
                "agent": "dev-user",
                "message": (
                    "dev-user authored and approved PR #42"
                ),
            }
        ]
        await maci_enforcer.post_maci_violation(
            bot, pr_number=42, violations=violations
        )

        assert len(posted) == 1
        assert "comments" in posted[0]["path"]
        body_text = posted[0]["body"]["body"]
        assert "MACI Separation of Powers Violation" in body_text
        assert "ACGS-004" in body_text
        assert "self_approval" in body_text

    def test_role_map(self) -> None:
        from acgs_lite.maci import MACIRole

        enforcer = GitHubMACIEnforcer()
        assert enforcer._ROLE_MAP["author"] == MACIRole.PROPOSER
        assert enforcer._ROLE_MAP["reviewer"] == MACIRole.VALIDATOR
        assert enforcer._ROLE_MAP["merger"] == MACIRole.EXECUTOR

    @pytest.mark.asyncio
    async def test_multiple_approvers_one_self(
        self,
        maci_enforcer: GitHubMACIEnforcer,
        bot: GitHubGovernanceBot,
    ) -> None:
        async def mock_get(path: str) -> Any:
            if "reviews" in path:
                return [
                    {"user": {"login": "dev-user"}, "state": "APPROVED"},
                    {"user": {"login": "other-user"}, "state": "APPROVED"},
                ]
            return {"user": {"login": "dev-user"}}

        bot._get = mock_get  # type: ignore[assignment]

        result = await maci_enforcer.check_pr_separation(bot, pr_number=42)
        assert result["separation_valid"] is False
        assert len(result["violations"]) == 1


# ---------------------------------------------------------------------------
# Graceful httpx-unavailable handling
# ---------------------------------------------------------------------------


class TestHttpxUnavailable:
    """Verify that missing httpx raises clear ImportError."""

    def test_bot_raises_without_httpx(self) -> None:
        with (
            patch(
                "acgs_lite.integrations.github.HTTPX_AVAILABLE", False
            ),
            pytest.raises(ImportError, match="httpx is required"),
        ):
            GitHubGovernanceBot(token="t", repo="a/b")
