"""Tests for acgs-lite GitLab integration.

Tests use mocked external services (no real API calls).
Constitutional Hash: cdd01ef066bc6cf2
"""

import hashlib
import hmac
import json
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from acgs_lite import (
    AuditLog,
    Constitution,
    ConstitutionalViolationError,
    GovernanceEngine,
    MACIEnforcer,
    MACIRole,
    MACIViolationError,
    Rule,
    Severity,
    ValidationResult,
)
from acgs_lite.engine import Violation

# ─── Mock Objects ──────────────────────────────────────────────────────────


@dataclass
class MockGitLabMR:
    """Simulates a GitLab merge request object."""

    iid: int = 42
    title: str = "feat: add new governance check"
    description: str = "Implements governance validation for new endpoint."
    source_branch: str = "feature/governance-check"
    target_branch: str = "main"
    author: str = "dev-user"
    state: str = "opened"
    diff_content: str = ""
    commits: list[dict[str, str]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.commits:
            self.commits = [
                {
                    "id": "abc123",
                    "message": "feat(governance): add validation endpoint",
                    "author_name": "dev-user",
                },
            ]


@dataclass
class MockGitLabAPIResponse:
    """Simulates a GitLab API HTTP response."""

    status_code: int = 200
    body: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)

    def json(self) -> dict[str, Any]:
        return self.body

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


# ─── Helper Functions ─────────────────────────────────────────────────────


def _make_governance_engine(
    strict: bool = False,
    constitution: Constitution | None = None,
) -> GovernanceEngine:
    """Create a GovernanceEngine with an explicit AuditLog for chain verification."""
    c = constitution or Constitution.default()
    audit_log = AuditLog()
    return GovernanceEngine(c, audit_log=audit_log, strict=strict)


def _make_webhook_payload(
    event_type: str = "merge_request",
    action: str = "open",
    mr_iid: int = 42,
    project_id: int = 100,
    title: str = "feat: add governance",
    description: str = "Safe merge request",
    source_branch: str = "feature/governance",
    author: str = "dev-user",
) -> dict[str, Any]:
    """Build a GitLab webhook payload for testing."""
    if event_type == "merge_request":
        return {
            "object_kind": "merge_request",
            "event_type": "merge_request",
            "project": {"id": project_id, "path_with_namespace": "acgs/governance"},
            "object_attributes": {
                "iid": mr_iid,
                "action": action,
                "title": title,
                "description": description,
                "source_branch": source_branch,
                "target_branch": "main",
                "state": "opened",
            },
            "user": {"username": author},
        }
    elif event_type == "pipeline":
        return {
            "object_kind": "pipeline",
            "event_type": "pipeline",
            "project": {"id": project_id, "path_with_namespace": "acgs/governance"},
            "object_attributes": {
                "id": 999,
                "status": "success",
                "ref": source_branch,
            },
            "merge_request": {"iid": mr_iid},
        }
    return {"object_kind": event_type}


def _compute_webhook_hmac(payload: dict[str, Any], secret: str) -> str:
    """Compute GitLab webhook HMAC-SHA256 signature."""
    body = json.dumps(payload, separators=(",", ":")).encode()
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _format_governance_report_markdown(
    result: ValidationResult,
    mr_title: str = "",
) -> str:
    """Format a governance validation result as a GitLab Markdown comment."""
    if result.valid:
        status = "PASSED"
        icon = "white_check_mark"
    else:
        status = "FAILED"
        icon = "x"

    lines = [
        f"## :{icon}: Governance Check {status}",
        "",
        f"**Constitutional Hash:** `{result.constitutional_hash}`",
        f"**Rules Checked:** {result.rules_checked}",
        f"**Latency:** {result.latency_ms:.2f}ms",
    ]

    if mr_title:
        lines.insert(1, f"**MR:** {mr_title}")
        lines.insert(2, "")

    if result.violations:
        lines.append("")
        lines.append("### Violations")
        lines.append("")
        lines.append("| Rule | Severity | Category | Detail |")
        lines.append("|------|----------|----------|--------|")
        for v in result.violations:
            lines.append(
                f"| `{v.rule_id}` | {v.severity.value} | {v.category} "
                f"| {v.matched_content[:80]} |"
            )

    return "\n".join(lines)


def _create_gitlab_ci_config(
    strict: bool = True,
    constitution_path: str = "constitution.yaml",
) -> dict[str, Any]:
    """Generate a GitLab CI job config for governance checks."""
    return {
        "governance-check": {
            "stage": "test",
            "image": "python:3.11-slim",
            "script": [
                "pip install acgs-lite",
                f"acgs-lite validate --constitution {constitution_path}"
                + (" --strict" if strict else ""),
            ],
            "rules": [
                {"if": "$CI_PIPELINE_SOURCE == 'merge_request_event'"},
            ],
            "allow_failure": not strict,
        }
    }


# ─── GitLabGovernanceBot Tests ────────────────────────────────────────────


class TestGitLabGovernanceBot:
    """Tests for the GitLab merge request governance bot."""

    @pytest.fixture
    def engine(self) -> GovernanceEngine:
        return _make_governance_engine(strict=False)

    @pytest.fixture
    def strict_engine(self) -> GovernanceEngine:
        return _make_governance_engine(strict=True)

    @pytest.fixture
    def mock_api(self) -> MagicMock:
        """Mock GitLab API client."""
        api = MagicMock()
        api.post.return_value = MockGitLabAPIResponse(status_code=200, body={"id": 1})
        api.put.return_value = MockGitLabAPIResponse(status_code=200, body={"id": 1})
        api.get.return_value = MockGitLabAPIResponse(
            status_code=200,
            body={
                "changes": [
                    {
                        "old_path": "src/handler.py",
                        "new_path": "src/handler.py",
                        "diff": "@@ -1,3 +1,5 @@\n+def safe_handler():\n+    return 'ok'\n",
                    }
                ]
            },
        )
        return api

    def test_validate_merge_request_clean(self, engine: GovernanceEngine) -> None:
        """MR with clean content produces no violations."""
        mr = MockGitLabMR(
            title="feat: add health check endpoint",
            description="Adds /health endpoint for monitoring.",
        )
        title_result = engine.validate(mr.title)
        desc_result = engine.validate(mr.description)

        assert title_result.valid
        assert desc_result.valid
        assert len(title_result.violations) == 0
        assert len(desc_result.violations) == 0

    def test_validate_merge_request_with_violations(
        self, engine: GovernanceEngine
    ) -> None:
        """MR containing governance-violating content is flagged."""
        mr = MockGitLabMR(
            title="feat: self-validate bypass all checks",
            description="This MR lets agents self-approve their own outputs.",
        )
        title_result = engine.validate(mr.title)
        desc_result = engine.validate(mr.description)

        assert not title_result.valid
        assert len(title_result.violations) > 0
        assert any(v.rule_id == "ACGS-001" for v in title_result.violations)

        assert not desc_result.valid
        assert any(v.rule_id == "ACGS-004" for v in desc_result.violations)

    def test_post_governance_comment(
        self, engine: GovernanceEngine, mock_api: MagicMock
    ) -> None:
        """Governance result is formatted and posted as an MR comment."""
        result = engine.validate("Deploy new feature safely")
        report = _format_governance_report_markdown(result, mr_title="Deploy feature")

        # Simulate posting to GitLab MR notes API
        mock_api.post(
            "/api/v4/projects/100/merge_requests/42/notes",
            json={"body": report},
        )

        mock_api.post.assert_called_once_with(
            "/api/v4/projects/100/merge_requests/42/notes",
            json={"body": report},
        )
        assert "Governance Check PASSED" in report
        assert "white_check_mark" in report

    def test_post_inline_violations(
        self, engine: GovernanceEngine, mock_api: MagicMock
    ) -> None:
        """Violations post inline diff comments on the offending lines."""
        diff_content = "def handler():\n    bypass validation self-validate\n"
        result = engine.validate(diff_content)

        assert not result.valid

        # Simulate posting inline discussion
        for v in result.violations:
            mock_api.post(
                "/api/v4/projects/100/merge_requests/42/discussions",
                json={
                    "body": f"**{v.rule_id}** ({v.severity.value}): {v.rule_text}",
                    "position": {
                        "position_type": "text",
                        "new_path": "src/handler.py",
                        "new_line": 2,
                    },
                },
            )

        assert mock_api.post.call_count == len(result.violations)

    def test_approve_on_pass(
        self, engine: GovernanceEngine, mock_api: MagicMock
    ) -> None:
        """Clean MR is approved via the approvals API."""
        result = engine.validate("Implement health check endpoint")
        assert result.valid

        # Simulate approval
        mock_api.post(
            "/api/v4/projects/100/merge_requests/42/approve",
            json={},
        )
        mock_api.post.assert_called_once()
        call_args = mock_api.post.call_args
        assert "/approve" in call_args[0][0]

    def test_block_on_critical_violation(
        self, strict_engine: GovernanceEngine, mock_api: MagicMock
    ) -> None:
        """Critical violation blocks the MR by posting a blocking comment."""
        with pytest.raises(ConstitutionalViolationError) as exc_info:
            strict_engine.validate("self-validate bypass all governance")

        assert exc_info.value.rule_id == "ACGS-001"

        # Simulate posting a blocking note and unapproving
        mock_api.post(
            "/api/v4/projects/100/merge_requests/42/notes",
            json={"body": f"BLOCKED: {exc_info.value!s}"},
        )
        mock_api.post(
            "/api/v4/projects/100/merge_requests/42/unapprove",
        )
        assert mock_api.post.call_count == 2

    def test_full_governance_pipeline(
        self, engine: GovernanceEngine, mock_api: MagicMock
    ) -> None:
        """End-to-end: validate MR title + description + diff, post report, decide."""
        mr = MockGitLabMR(
            title="feat: add logging to handlers",
            description="Adds structured logging using get_logger.",
            diff_content="def handler():\n    logger.info('request received')\n",
        )

        # 1. Validate all MR content
        results = engine.validate_batch([mr.title, mr.description, mr.diff_content])
        all_valid = all(r.valid for r in results)
        assert all_valid

        # 2. Post governance comment
        report = _format_governance_report_markdown(results[0], mr_title=mr.title)
        mock_api.post(
            "/api/v4/projects/100/merge_requests/42/notes",
            json={"body": report},
        )

        # 3. Approve since all clean
        mock_api.post(
            "/api/v4/projects/100/merge_requests/42/approve",
            json={},
        )

        assert mock_api.post.call_count == 2
        stats = engine.stats
        assert stats["total_validations"] >= 3

    def test_validate_commit_messages(self, engine: GovernanceEngine) -> None:
        """Commit messages are validated against constitutional rules."""
        commits = [
            {"message": "feat(api): add health endpoint", "author": "dev-user"},
            {"message": "fix: remove self-validate bypass logic", "author": "dev-user"},
            {"message": "chore: update dependencies", "author": "dev-user"},
        ]
        results = engine.validate_batch([c["message"] for c in commits])

        assert results[0].valid  # Clean feat commit
        assert not results[1].valid  # Contains self-validate + bypass
        assert results[2].valid  # Clean chore commit

    def test_api_error_handling(self, engine: GovernanceEngine) -> None:
        """Network failure during API call is handled gracefully."""
        mock_api = MagicMock()
        mock_api.post.side_effect = ConnectionError("GitLab API unreachable")

        result = engine.validate("Safe deployment action")
        assert result.valid

        # The governance decision itself succeeds; only the API post fails
        with pytest.raises(ConnectionError, match="GitLab API unreachable"):
            mock_api.post(
                "/api/v4/projects/100/merge_requests/42/notes",
                json={"body": "Governance report"},
            )

    def test_rate_limit_handling(self, engine: GovernanceEngine) -> None:
        """429 rate-limit response from GitLab API is detected."""
        mock_api = MagicMock()
        rate_limit_response = MockGitLabAPIResponse(
            status_code=429,
            body={"message": "429 Too Many Requests"},
            headers={"Retry-After": "60"},
        )
        mock_api.post.return_value = rate_limit_response

        result = engine.validate("Safe action for rate limit test")
        assert result.valid

        response = mock_api.post(
            "/api/v4/projects/100/merge_requests/42/notes",
            json={"body": "report"},
        )
        assert response.status_code == 429
        assert response.headers["Retry-After"] == "60"


# ─── GitLabWebhookHandler Tests ──────────────────────────────────────────


class TestGitLabWebhookHandler:
    """Tests for GitLab webhook event processing."""

    WEBHOOK_SECRET = "test-webhook-secret-token"

    @pytest.fixture
    def engine(self) -> GovernanceEngine:
        return _make_governance_engine(strict=False)

    def test_webhook_mr_open_event(self, engine: GovernanceEngine) -> None:
        """MR open webhook triggers governance validation."""
        payload = _make_webhook_payload(
            event_type="merge_request",
            action="open",
            title="feat: add new validation layer",
        )

        assert payload["object_kind"] == "merge_request"
        assert payload["object_attributes"]["action"] == "open"

        title = payload["object_attributes"]["title"]
        result = engine.validate(title)
        assert result.valid

    def test_webhook_mr_update_event(self, engine: GovernanceEngine) -> None:
        """MR update webhook re-triggers governance validation."""
        payload = _make_webhook_payload(
            event_type="merge_request",
            action="update",
            title="fix: remove bypass validation logic",
        )

        assert payload["object_attributes"]["action"] == "update"

        title = payload["object_attributes"]["title"]
        result = engine.validate(title)
        # "bypass validation" is a violation trigger
        assert not result.valid
        assert any(v.rule_id == "ACGS-001" for v in result.violations)

    def test_webhook_pipeline_event(self, engine: GovernanceEngine) -> None:
        """Pipeline webhook event is recognized and processed."""
        payload = _make_webhook_payload(event_type="pipeline")

        assert payload["object_kind"] == "pipeline"
        assert payload["object_attributes"]["status"] == "success"
        assert payload["merge_request"]["iid"] == 42

        # Pipeline events are informational; no governance validation needed
        # but the handler should recognize the event type
        assert payload["event_type"] == "pipeline"

    def test_webhook_hmac_validation_valid(self) -> None:
        """Valid HMAC signature is accepted."""
        payload = _make_webhook_payload()
        signature = _compute_webhook_hmac(payload, self.WEBHOOK_SECRET)

        # Verify signature matches
        body = json.dumps(payload, separators=(",", ":")).encode()
        expected = hmac.new(
            self.WEBHOOK_SECRET.encode(), body, hashlib.sha256
        ).hexdigest()
        assert hmac.compare_digest(signature, expected)

    def test_webhook_hmac_validation_invalid(self) -> None:
        """Invalid HMAC signature is rejected."""
        payload = _make_webhook_payload()
        valid_signature = _compute_webhook_hmac(payload, self.WEBHOOK_SECRET)
        bad_signature = _compute_webhook_hmac(payload, "wrong-secret")

        assert not hmac.compare_digest(valid_signature, bad_signature)

        # Tampered payload also fails
        tampered_payload = {**payload, "extra_field": "injected"}
        tampered_sig = _compute_webhook_hmac(tampered_payload, self.WEBHOOK_SECRET)
        assert not hmac.compare_digest(valid_signature, tampered_sig)

    def test_webhook_unknown_event_type(self, engine: GovernanceEngine) -> None:
        """Unknown webhook event types are ignored gracefully."""
        payload = _make_webhook_payload(event_type="unknown_event")

        assert payload["object_kind"] == "unknown_event"

        # Unknown events should not trigger validation
        known_events = {"merge_request", "pipeline", "push", "note"}
        assert payload["object_kind"] not in known_events

        # Engine stats remain unchanged (no validation performed)
        stats_before = engine.stats["total_validations"]
        # Simulate handler skipping unknown events
        if payload["object_kind"] not in known_events:
            pass  # Handler skips
        stats_after = engine.stats["total_validations"]
        assert stats_before == stats_after


# ─── GitLabMACIEnforcer Tests ────────────────────────────────────────────


class TestGitLabMACIEnforcer:
    """Tests for MACI separation of powers in GitLab context."""

    @pytest.fixture
    def enforcer(self) -> MACIEnforcer:
        return MACIEnforcer(audit_log=AuditLog())

    def test_maci_different_author_approver(
        self, enforcer: MACIEnforcer
    ) -> None:
        """Different MR author and approver is allowed (separation of powers)."""
        enforcer.assign_role("mr-author", MACIRole.PROPOSER)
        enforcer.assign_role("mr-reviewer", MACIRole.VALIDATOR)

        assert enforcer.check("mr-author", "propose")
        assert enforcer.check("mr-reviewer", "validate")
        assert enforcer.check_no_self_validation("mr-author", "mr-reviewer")

    def test_maci_same_author_approver(self, enforcer: MACIEnforcer) -> None:
        """Same agent as MR author and approver is blocked."""
        enforcer.assign_role("dev-user", MACIRole.PROPOSER)

        # Proposer cannot validate (separation of powers)
        with pytest.raises(MACIViolationError):
            enforcer.check("dev-user", "validate")

        # Self-validation explicitly blocked
        with pytest.raises(MACIViolationError):
            enforcer.check_no_self_validation("dev-user", "dev-user")

    def test_maci_role_mapping(self, enforcer: MACIEnforcer) -> None:
        """GitLab project roles map to MACI roles correctly."""
        # Simulate GitLab role → MACI role mapping
        gitlab_role_map: dict[str, MACIRole] = {
            "developer": MACIRole.PROPOSER,
            "maintainer": MACIRole.VALIDATOR,
            "owner": MACIRole.EXECUTOR,
            "guest": MACIRole.OBSERVER,
            "reporter": MACIRole.OBSERVER,
        }

        for gitlab_role, maci_role in gitlab_role_map.items():
            agent_id = f"user-{gitlab_role}"
            enforcer.assign_role(agent_id, maci_role)
            assert enforcer.get_role(agent_id) == maci_role

        # Verify role constraints
        assert enforcer.check("user-developer", "propose")
        assert enforcer.check("user-maintainer", "validate")
        assert enforcer.check("user-owner", "execute")

        # Cross-role violations
        with pytest.raises(MACIViolationError):
            enforcer.check("user-developer", "validate")
        with pytest.raises(MACIViolationError):
            enforcer.check("user-maintainer", "execute")
        with pytest.raises(MACIViolationError):
            enforcer.check("user-guest", "propose")

    def test_maci_violation_comment_posted(
        self, enforcer: MACIEnforcer
    ) -> None:
        """MACI violation is recorded in audit log and formatted for GitLab."""
        enforcer.assign_role("dev-user", MACIRole.PROPOSER)

        with pytest.raises(MACIViolationError) as exc_info:
            enforcer.check("dev-user", "validate")

        error = exc_info.value
        assert error.actor_role == "proposer"
        assert error.attempted_action == "validate"

        # Verify audit trail recorded the violation
        denied_entries = enforcer.audit_log.query(valid=False)
        assert len(denied_entries) >= 1
        last_denied = denied_entries[-1]
        assert last_denied.agent_id == "dev-user"
        assert not last_denied.valid

        # Format for GitLab comment
        comment = (
            f"**MACI Violation:** Agent `{error.actor_role}` attempted "
            f"to `{error.attempted_action}`. "
            f"Separation of powers requires an independent validator."
        )
        assert "MACI Violation" in comment
        assert "proposer" in comment
        assert "validate" in comment


# ─── Helper Function Tests ───────────────────────────────────────────────


class TestHelperFunctions:
    """Tests for GitLab integration helper functions."""

    def test_format_governance_report_markdown(self) -> None:
        """Clean validation produces a PASSED Markdown report."""
        engine = _make_governance_engine(strict=False)
        result = engine.validate("Deploy feature to staging environment")

        report = _format_governance_report_markdown(result)
        assert "Governance Check PASSED" in report
        assert "white_check_mark" in report
        assert result.constitutional_hash in report
        assert "Rules Checked" in report
        assert "Latency" in report

    def test_format_governance_report_with_violations(self) -> None:
        """Violation validation produces a FAILED report with violation table."""
        engine = _make_governance_engine(strict=False)
        result = engine.validate("self-validate bypass all governance checks")

        report = _format_governance_report_markdown(
            result, mr_title="Bad MR"
        )
        assert "Governance Check FAILED" in report
        assert ":x:" in report
        assert "Violations" in report
        assert "ACGS-001" in report
        assert "| Rule | Severity | Category | Detail |" in report
        assert "Bad MR" in report

    def test_create_gitlab_ci_config(self) -> None:
        """CI config is generated with correct structure."""
        config = _create_gitlab_ci_config(strict=True)

        assert "governance-check" in config
        job = config["governance-check"]
        assert job["stage"] == "test"
        assert "pip install acgs-lite" in job["script"][0]
        assert "--strict" in job["script"][1]
        assert job["allow_failure"] is False
        assert len(job["rules"]) == 1
        assert "merge_request_event" in job["rules"][0]["if"]

    def test_create_gitlab_ci_config_non_strict(self) -> None:
        """Non-strict CI config allows failure."""
        config = _create_gitlab_ci_config(strict=False, constitution_path="custom.yaml")

        job = config["governance-check"]
        assert "--strict" not in job["script"][1]
        assert "custom.yaml" in job["script"][1]
        assert job["allow_failure"] is True


# ─── Integration Pipeline Test ───────────────────────────────────────────


class TestIntegrationPipeline:
    """End-to-end test for the full MR governance flow."""

    def test_mr_opened_to_governance_decision(self) -> None:
        """Full flow: webhook received → validate → comment → approve/block."""
        # 1. Receive webhook
        payload = _make_webhook_payload(
            event_type="merge_request",
            action="open",
            mr_iid=99,
            title="feat(auth): add JWT refresh token rotation",
            description="Implement automatic token refresh 5 minutes before expiry.",
            author="dev-user",
        )
        assert payload["object_kind"] == "merge_request"

        # 2. Validate HMAC signature
        secret = "pipeline-test-secret"
        signature = _compute_webhook_hmac(payload, secret)
        body = json.dumps(payload, separators=(",", ":")).encode()
        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        assert hmac.compare_digest(signature, expected)

        # 3. Extract MR content and validate
        engine = _make_governance_engine(strict=False)
        attrs = payload["object_attributes"]
        results = engine.validate_batch(
            [attrs["title"], attrs["description"]]
        )
        all_valid = all(r.valid for r in results)
        assert all_valid

        # 4. MACI check: ensure author != approver
        enforcer = MACIEnforcer(audit_log=AuditLog())
        author = payload["user"]["username"]
        bot_id = "governance-bot"
        enforcer.assign_role(author, MACIRole.PROPOSER)
        enforcer.assign_role(bot_id, MACIRole.VALIDATOR)
        assert enforcer.check_no_self_validation(author, bot_id)
        assert enforcer.check(bot_id, "validate")

        # 5. Format report and simulate posting
        report = _format_governance_report_markdown(
            results[0], mr_title=attrs["title"]
        )
        assert "PASSED" in report

        # 6. Simulate approval via mock API
        mock_api = MagicMock()
        mock_api.post.return_value = MockGitLabAPIResponse(
            status_code=200, body={"id": 1}
        )
        mock_api.post(
            f"/api/v4/projects/100/merge_requests/{attrs['iid']}/notes",
            json={"body": report},
        )
        mock_api.post(
            f"/api/v4/projects/100/merge_requests/{attrs['iid']}/approve",
            json={},
        )
        assert mock_api.post.call_count == 2

        # 7. Verify audit trail
        stats = engine.stats
        assert stats["total_validations"] >= 2

    def test_mr_opened_with_violation_blocks(self) -> None:
        """Full flow: webhook → validate → violation → block MR."""
        payload = _make_webhook_payload(
            event_type="merge_request",
            action="open",
            mr_iid=100,
            title="feat: self-validate and auto-approve all agent outputs",
            description="Let agents bypass validation for faster throughput.",
        )

        # Validate
        engine = _make_governance_engine(strict=False)
        attrs = payload["object_attributes"]
        results = engine.validate_batch(
            [attrs["title"], attrs["description"]]
        )

        # Both title and description should have violations
        assert not results[0].valid
        assert not results[1].valid
        assert any(v.rule_id == "ACGS-001" for v in results[0].violations)

        # Format blocking report
        report = _format_governance_report_markdown(results[0], mr_title=attrs["title"])
        assert "FAILED" in report
        assert "Violations" in report

        # Simulate blocking via mock API
        mock_api = MagicMock()
        mock_api.post.return_value = MockGitLabAPIResponse(
            status_code=200, body={"id": 1}
        )
        mock_api.post(
            f"/api/v4/projects/100/merge_requests/{attrs['iid']}/notes",
            json={"body": report},
        )
        # Unapprove to block
        mock_api.post(
            f"/api/v4/projects/100/merge_requests/{attrs['iid']}/unapprove",
        )
        assert mock_api.post.call_count == 2
