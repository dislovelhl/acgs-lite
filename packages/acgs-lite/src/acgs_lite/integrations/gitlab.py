"""ACGS-Lite GitLab Integration.

Governs GitLab merge requests with constitutional validation, MACI separation
of powers enforcement, and automated inline violation comments.

Three main classes:
1. GitLabGovernanceBot: Validates MRs against constitutional rules
2. GitLabWebhookHandler: Receives GitLab webhook events (Starlette-compatible)
3. GitLabMACIEnforcer: Enforces MACI role separation on MR participants

Usage::

    from acgs_lite.integrations.gitlab import GitLabGovernanceBot
    from acgs_lite import Constitution

    bot = GitLabGovernanceBot(
        token="glpat-...",
        project_id=12345,
        constitution=Constitution.from_yaml("rules.yaml"),
    )
    report = await bot.run_governance_pipeline(mr_iid=42)

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import hmac
import logging
from dataclasses import dataclass, field
from typing import Any

from acgs_lite.audit import AuditEntry, AuditLog
from acgs_lite.constitution import Constitution
from acgs_lite.engine import GovernanceEngine, ValidationResult
from acgs_lite.maci import MACIEnforcer, MACIRole

logger = logging.getLogger(__name__)

try:
    import httpx

    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GovernanceReport:
    """Immutable governance report for a merge request."""

    mr_iid: int
    title: str
    passed: bool
    risk_score: float
    violations: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    commit_violations: list[dict[str, Any]] = field(default_factory=list)
    rules_checked: int = 0
    constitutional_hash: str = ""
    latency_ms: float = 0.0


# ---------------------------------------------------------------------------
# GitLabGovernanceBot
# ---------------------------------------------------------------------------


class GitLabGovernanceBot:
    """Validates GitLab merge requests against constitutional governance rules.

    Usage::

        bot = GitLabGovernanceBot(
            token="glpat-...",
            project_id=12345,
            constitution=Constitution.from_yaml("rules.yaml"),
        )
        report = await bot.run_governance_pipeline(mr_iid=42)
    """

    _BASE_URL = "https://gitlab.com/api/v4"

    def __init__(
        self,
        *,
        token: str,
        project_id: int,
        constitution: Constitution | None = None,
        base_url: str | None = None,
        timeout: float = 30.0,
        strict: bool = False,
    ) -> None:
        if not HTTPX_AVAILABLE:
            raise ImportError(
                "httpx is required for GitLab integration. Install with: pip install acgs[gitlab]"
            )

        self._token = token
        self._project_id = project_id
        self._base_url = (base_url or self._BASE_URL).rstrip("/")
        self._timeout = timeout

        self.constitution = constitution or Constitution.default()
        self.audit_log = AuditLog()
        self.engine = GovernanceEngine(
            self.constitution,
            audit_log=self.audit_log,
            strict=strict,
            audit_mode="full",
        )

    # -- HTTP helpers -------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {"PRIVATE-TOKEN": self._token, "Content-Type": "application/json"}

    def _project_url(self, path: str) -> str:
        return f"{self._base_url}/projects/{self._project_id}/{path}"

    async def _get(self, path: str) -> Any:
        """GET request to the GitLab project API."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(self._project_url(path), headers=self._headers())
            resp.raise_for_status()
            result: Any = resp.json()
            return result

    async def _post(self, path: str, json_body: dict[str, Any]) -> Any:
        """POST request to the GitLab project API."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                self._project_url(path),
                headers=self._headers(),
                json=json_body,
            )
            resp.raise_for_status()
            result: Any = resp.json()
            return result

    # -- Core governance methods -------------------------------------------

    async def validate_merge_request(self, mr_iid: int) -> GovernanceReport:
        """Fetch MR details and diffs, validate against constitutional rules.

        Args:
            mr_iid: The merge request internal ID.

        Returns:
            GovernanceReport with violation details, risk score, and decision.
        """
        mr_data = await self._get(f"merge_requests/{mr_iid}")
        changes = await self._get(f"merge_requests/{mr_iid}/changes")

        title = mr_data.get("title", "")
        description = mr_data.get("description", "") or ""
        diffs = changes.get("changes", [])

        all_violations: list[dict[str, Any]] = []
        all_warnings: list[dict[str, Any]] = []
        total_checked = 0

        # Validate title + description
        for text, source in [(title, "title"), (description, "description")]:
            if not text:
                continue
            result = self._validate_text(text, agent_id=f"gitlab-mr-{mr_iid}:{source}")
            total_checked += result.rules_checked
            for v in result.blocking_violations:
                all_violations.append(
                    {**_violation_to_dict(v), "source": source, "file": None, "line": None}
                )
            for w in result.warnings:
                all_warnings.append(
                    {**_violation_to_dict(w), "source": source, "file": None, "line": None}
                )

        # Validate each diff hunk
        for diff in diffs:
            file_path = diff.get("new_path", diff.get("old_path", "unknown"))
            diff_text = diff.get("diff", "")
            if not diff_text:
                continue

            for line_no, line in _parse_added_lines(diff_text):
                result = self._validate_text(line, agent_id=f"gitlab-mr-{mr_iid}:{file_path}")
                total_checked += result.rules_checked
                for v in result.blocking_violations:
                    entry = {
                        **_violation_to_dict(v),
                        "source": "diff",
                        "file": file_path,
                        "line": line_no,
                    }
                    all_violations.append(entry)
                for w in result.warnings:
                    entry = {
                        **_violation_to_dict(w),
                        "source": "diff",
                        "file": file_path,
                        "line": line_no,
                    }
                    all_warnings.append(entry)

        risk_score = _compute_risk_score(all_violations, all_warnings)

        report = GovernanceReport(
            mr_iid=mr_iid,
            title=title,
            passed=len(all_violations) == 0,
            risk_score=risk_score,
            violations=all_violations,
            warnings=all_warnings,
            rules_checked=total_checked,
            constitutional_hash=self.constitution.hash,
        )

        self.audit_log.record(
            AuditEntry(
                id=f"gitlab-mr-{mr_iid}",
                type="gitlab_mr_validation",
                agent_id="gitlab-governance-bot",
                action=f"validate MR !{mr_iid}: {title}",
                valid=report.passed,
                violations=[v["rule_id"] for v in all_violations],
                constitutional_hash=self.constitution.hash,
                metadata={"mr_iid": mr_iid, "risk_score": risk_score},
            )
        )

        return report

    async def post_governance_comment(self, mr_iid: int, report: GovernanceReport) -> Any:
        """Post a formatted governance comment on the merge request.

        Args:
            mr_iid: The merge request internal ID.
            report: The governance report to format and post.

        Returns:
            GitLab API response for the created note.
        """
        body = format_governance_report(report)
        return await self._post(f"merge_requests/{mr_iid}/notes", {"body": body})

    async def post_inline_violations(
        self,
        mr_iid: int,
        violations: list[dict[str, Any]],
    ) -> list[Any]:
        """Post inline diff comments on specific lines where violations were found.

        Args:
            mr_iid: The merge request internal ID.
            violations: List of violation dicts with 'file' and 'line' keys.

        Returns:
            List of GitLab API responses for created discussion notes.
        """
        mr_data = await self._get(f"merge_requests/{mr_iid}")
        head_sha = mr_data.get("diff_refs", {}).get("head_sha", "")
        base_sha = mr_data.get("diff_refs", {}).get("base_sha", "")

        results: list[Any] = []
        for v in violations:
            if v.get("file") is None or v.get("line") is None:
                continue

            note_body = (
                f"**Governance Violation** [{v['severity'].upper()}]\n\n"
                f"Rule `{v['rule_id']}`: {v['rule_text']}\n\n"
                f"Matched: `{v['matched_content']}`"
            )

            discussion_payload: dict[str, Any] = {
                "body": note_body,
                "position": {
                    "position_type": "text",
                    "base_sha": base_sha,
                    "head_sha": head_sha,
                    "start_sha": base_sha,
                    "new_path": v["file"],
                    "old_path": v["file"],
                    "new_line": v["line"],
                },
            }

            try:
                resp = await self._post(
                    f"merge_requests/{mr_iid}/discussions",
                    discussion_payload,
                )
                results.append(resp)
            except Exception:
                logger.warning(
                    "Failed to post inline comment on %s:%s",
                    v["file"],
                    v["line"],
                    exc_info=True,
                )

        return results

    async def approve_or_block(self, mr_iid: int, report: GovernanceReport) -> dict[str, Any]:
        """Approve the MR if governance passes, or post a block comment.

        Args:
            mr_iid: The merge request internal ID.
            report: The governance report with pass/fail decision.

        Returns:
            Dict with 'action' ("approved" or "blocked") and API response.
        """
        if report.passed:
            try:
                resp = await self._post(f"merge_requests/{mr_iid}/approve", {})
                return {"action": "approved", "response": resp}
            except Exception:
                logger.warning("Failed to approve MR !%s", mr_iid, exc_info=True)
                return {"action": "approve_failed", "response": None}

        block_body = (
            "## Governance: Merge Blocked\n\n"
            f"This merge request has **{len(report.violations)} violation(s)** "
            "that must be resolved before merging.\n\n"
            "Please review the governance report above and address all "
            "CRITICAL and HIGH severity findings."
        )
        resp = await self._post(f"merge_requests/{mr_iid}/notes", {"body": block_body})
        return {"action": "blocked", "response": resp}

    async def validate_commit_messages(self, mr_iid: int) -> list[dict[str, Any]]:
        """Validate commit messages in the MR against governance rules.

        Args:
            mr_iid: The merge request internal ID.

        Returns:
            List of commit violation dicts with sha, message, and violations.
        """
        commits = await self._get(f"merge_requests/{mr_iid}/commits")

        commit_violations: list[dict[str, Any]] = []
        for commit in commits:
            sha = commit.get("id", "")[:8]
            message = commit.get("message", "")
            result = self._validate_text(message, agent_id=f"gitlab-commit-{sha}")

            if not result.valid:
                commit_violations.append(
                    {
                        "sha": sha,
                        "message": message.split("\n", 1)[0],
                        "violations": [_violation_to_dict(v) for v in result.violations],
                    }
                )

        return commit_violations

    async def run_governance_pipeline(self, mr_iid: int) -> GovernanceReport:
        """Run the full governance pipeline: validate, comment, approve/block.

        Args:
            mr_iid: The merge request internal ID.

        Returns:
            The complete GovernanceReport.
        """
        report = await self.validate_merge_request(mr_iid)

        commit_violations = await self.validate_commit_messages(mr_iid)
        if commit_violations:
            report = GovernanceReport(
                mr_iid=report.mr_iid,
                title=report.title,
                passed=report.passed and len(commit_violations) == 0,
                risk_score=report.risk_score,
                violations=report.violations,
                warnings=report.warnings,
                commit_violations=commit_violations,
                rules_checked=report.rules_checked,
                constitutional_hash=report.constitutional_hash,
                latency_ms=report.latency_ms,
            )

        await self.post_governance_comment(mr_iid, report)

        diff_violations = [v for v in report.violations if v.get("file") and v.get("line")]
        if diff_violations:
            await self.post_inline_violations(mr_iid, diff_violations)

        await self.approve_or_block(mr_iid, report)

        logger.info(
            "Governance pipeline complete for MR !%s: %s (risk=%.2f, violations=%d)",
            mr_iid,
            "PASSED" if report.passed else "BLOCKED",
            report.risk_score,
            len(report.violations),
        )

        return report

    def _validate_text(self, text: str, agent_id: str) -> ValidationResult:
        """Validate text using the governance engine in non-strict mode."""
        old_strict = self.engine.strict
        self.engine.strict = False
        result = self.engine.validate(text, agent_id=agent_id)
        self.engine.strict = old_strict
        return result

    @property
    def stats(self) -> dict[str, Any]:
        """Return governance statistics."""
        return {
            **self.engine.stats,
            "project_id": self._project_id,
            "audit_chain_valid": self.audit_log.verify_chain(),
        }


# ---------------------------------------------------------------------------
# GitLabWebhookHandler
# ---------------------------------------------------------------------------


class GitLabWebhookHandler:
    """Starlette-compatible handler for GitLab webhook events.

    Validates HMAC signatures, routes MR and pipeline events to governance
    checks, and returns structured JSON responses.

    Usage::

        from starlette.applications import Starlette
        from starlette.routing import Route

        handler = GitLabWebhookHandler(
            webhook_secret="my-secret",
            bot=GitLabGovernanceBot(token="glpat-...", project_id=123),
        )
        app = Starlette(routes=[Route("/webhook", handler.handle, methods=["POST"])])
    """

    # Supported event types and their sub-actions
    _MR_ACTIONS = frozenset({"open", "update", "merge", "approved", "reopen"})
    _PIPELINE_STATUSES = frozenset({"success", "failed"})

    def __init__(
        self,
        *,
        webhook_secret: str,
        bot: GitLabGovernanceBot,
    ) -> None:
        self._secret = webhook_secret.encode()
        self._bot = bot

    def verify_signature(self, token: str) -> bool:
        """Verify the GitLab webhook secret token.

        GitLab uses a shared secret token (X-Gitlab-Token header),
        not HMAC signing like GitHub. We compare using constant-time
        comparison to prevent timing attacks.

        Args:
            token: The token from the X-Gitlab-Token header.

        Returns:
            True if the token matches the configured secret.
        """
        return hmac.compare_digest(token.encode(), self._secret)

    async def handle(self, request: Any) -> Any:
        """Handle an incoming GitLab webhook request.

        Args:
            request: Starlette Request object.

        Returns:
            Starlette JSONResponse with the governance result.
        """
        try:
            from starlette.responses import JSONResponse
        except ImportError as exc:
            raise ImportError(
                "starlette is required for webhook handling. Install with: pip install starlette"
            ) from exc

        # Verify signature
        token = request.headers.get("X-Gitlab-Token", "")
        if not self.verify_signature(token):
            return JSONResponse({"error": "Invalid webhook token"}, status_code=401)

        event_type = request.headers.get("X-Gitlab-Event", "")
        body: dict[str, Any] = await request.json()

        try:
            result = await self._route_event(event_type, body)
            return JSONResponse({"status": "processed", "result": result})
        except Exception:
            logger.error("Webhook processing failed", exc_info=True)
            return JSONResponse({"error": "Processing failed"}, status_code=500)

    async def _route_event(self, event_type: str, body: dict[str, Any]) -> dict[str, Any]:
        """Route a webhook event to the appropriate handler."""
        if event_type == "Merge Request Hook":
            return await self._handle_merge_request(body)
        if event_type == "Pipeline Hook":
            return await self._handle_pipeline(body)

        return {"event": event_type, "action": "ignored", "reason": "unsupported event type"}

    async def _handle_merge_request(self, body: dict[str, Any]) -> dict[str, Any]:
        """Handle merge request events."""
        attrs = body.get("object_attributes", {})
        action = attrs.get("action", "")
        mr_iid = attrs.get("iid")

        if action not in self._MR_ACTIONS or mr_iid is None:
            return {"event": "merge_request", "action": action, "status": "skipped"}

        if action in ("open", "update", "reopen"):
            report = await self._bot.run_governance_pipeline(mr_iid)
            return {
                "event": "merge_request",
                "action": action,
                "mr_iid": mr_iid,
                "governance_passed": report.passed,
                "violations": len(report.violations),
                "risk_score": report.risk_score,
            }

        if action == "approved":
            report = await self._bot.validate_merge_request(mr_iid)
            return {
                "event": "merge_request",
                "action": "approved",
                "mr_iid": mr_iid,
                "post_approval_valid": report.passed,
            }

        return {"event": "merge_request", "action": action, "mr_iid": mr_iid, "status": "noted"}

    async def _handle_pipeline(self, body: dict[str, Any]) -> dict[str, Any]:
        """Handle pipeline events."""
        attrs = body.get("object_attributes", {})
        status = attrs.get("status", "")
        mr_data = body.get("merge_request")

        if status not in self._PIPELINE_STATUSES or mr_data is None:
            return {"event": "pipeline", "status": status, "action": "skipped"}

        mr_iid = mr_data.get("iid")
        if status == "success" and mr_iid is not None:
            report = await self._bot.validate_merge_request(mr_iid)
            return {
                "event": "pipeline",
                "status": "success",
                "mr_iid": mr_iid,
                "governance_passed": report.passed,
            }

        return {"event": "pipeline", "status": status, "action": "noted"}


# ---------------------------------------------------------------------------
# GitLabMACIEnforcer
# ---------------------------------------------------------------------------


class GitLabMACIEnforcer:
    """Maps GitLab MR roles to MACI roles and enforces separation of powers.

    - MR author -> PROPOSER
    - MR reviewer/approver -> VALIDATOR
    - MR merger -> EXECUTOR

    Usage::

        enforcer = GitLabMACIEnforcer()
        result = await enforcer.check_mr_separation(bot, mr_iid=42)
    """

    # GitLab role -> MACI role mapping
    _ROLE_MAP: dict[str, MACIRole] = {
        "author": MACIRole.PROPOSER,
        "reviewer": MACIRole.VALIDATOR,
        "approver": MACIRole.VALIDATOR,
        "merger": MACIRole.EXECUTOR,
    }

    def __init__(self, *, audit_log: AuditLog | None = None) -> None:
        self.enforcer = MACIEnforcer(audit_log=audit_log)

    async def check_mr_separation(
        self,
        bot: GitLabGovernanceBot,
        mr_iid: int,
    ) -> dict[str, Any]:
        """Validate MACI separation of powers on an MR.

        Checks that the MR author is not also an approver, enforcing the
        constitutional rule that proposers cannot validate their own proposals.

        Args:
            bot: The GitLabGovernanceBot (provides API access).
            mr_iid: The merge request internal ID.

        Returns:
            Dict with separation check results and any violations.
        """
        mr_data = await bot._get(f"merge_requests/{mr_iid}")
        approvals = await bot._get(f"merge_requests/{mr_iid}/approvals")

        author_username = mr_data.get("author", {}).get("username", "")
        approved_by = [
            a.get("user", {}).get("username", "") for a in approvals.get("approved_by", [])
        ]

        # Assign MACI roles
        self.enforcer.assign_role(author_username, MACIRole.PROPOSER)
        for approver in approved_by:
            if approver:
                self.enforcer.assign_role(approver, MACIRole.VALIDATOR)

        # Check for self-approval
        violations: list[dict[str, str]] = []
        for approver in approved_by:
            if approver == author_username:
                violations.append(
                    {
                        "type": "self_approval",
                        "agent": author_username,
                        "message": (
                            f"MACI violation: {author_username} authored and approved "
                            f"MR !{mr_iid}. Proposers cannot validate their own proposals."
                        ),
                    }
                )

        result = {
            "mr_iid": mr_iid,
            "author": author_username,
            "approvers": approved_by,
            "separation_valid": len(violations) == 0,
            "violations": violations,
            "role_assignments": self.enforcer.role_assignments,
        }

        bot.audit_log.record(
            AuditEntry(
                id=f"maci-mr-{mr_iid}",
                type="maci_mr_check",
                agent_id="gitlab-maci-enforcer",
                action=f"MACI separation check MR !{mr_iid}",
                valid=len(violations) == 0,
                violations=[v["type"] for v in violations],
                constitutional_hash=bot.constitution.hash,
                metadata=result,
            )
        )

        return result

    async def post_maci_violation(
        self,
        bot: GitLabGovernanceBot,
        mr_iid: int,
        violations: list[dict[str, str]],
    ) -> Any:
        """Post a MACI violation comment on the merge request.

        Args:
            bot: The GitLabGovernanceBot (provides API access).
            mr_iid: The merge request internal ID.
            violations: List of violation dicts from check_mr_separation.

        Returns:
            GitLab API response for the created note.
        """
        lines = ["## MACI Separation of Powers Violation\n"]
        for v in violations:
            lines.append(f"- **{v['type']}**: {v['message']}")
        lines.append(
            "\n> Constitutional rule ACGS-004: Proposers cannot validate their own proposals."
        )

        body = "\n".join(lines)
        return await bot._post(f"merge_requests/{mr_iid}/notes", {"body": body})


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _violation_to_dict(v: Any) -> dict[str, Any]:
    """Convert a Violation namedtuple to a serialisable dict."""
    return {
        "rule_id": v.rule_id,
        "rule_text": v.rule_text,
        "severity": v.severity.value,
        "matched_content": v.matched_content,
        "category": v.category,
    }


def _parse_added_lines(diff_text: str) -> list[tuple[int, str]]:
    """Parse unified diff text, returning (line_number, content) for added lines."""
    results: list[tuple[int, str]] = []
    current_line = 0

    for raw_line in diff_text.splitlines():
        if raw_line.startswith("@@"):
            # Parse hunk header: @@ -old,count +new,count @@
            parts = raw_line.split("+")
            if len(parts) >= 2:
                line_part = parts[1].split(",")[0].split(" ")[0]
                try:
                    current_line = int(line_part)
                except ValueError:
                    current_line = 0
        elif raw_line.startswith("+") and not raw_line.startswith("+++"):
            content = raw_line[1:]
            if content.strip():
                results.append((current_line, content))
            current_line += 1
        elif raw_line.startswith("-") and not raw_line.startswith("---"):
            # Deleted line: don't advance the new-file line counter
            pass
        else:
            # Context line
            current_line += 1

    return results


def _compute_risk_score(
    violations: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> float:
    """Compute a 0.0-1.0 risk score from violations and warnings."""
    if not violations and not warnings:
        return 0.0

    severity_weights = {"critical": 1.0, "high": 0.7, "medium": 0.3, "low": 0.1}
    total = 0.0

    for v in violations:
        total += severity_weights.get(v.get("severity", "medium"), 0.3)
    for w in warnings:
        total += severity_weights.get(w.get("severity", "low"), 0.1) * 0.5

    # Normalize to 0.0-1.0 range (cap at 1.0)
    return min(total / max(len(violations) + len(warnings), 1), 1.0)


def format_governance_report(report: GovernanceReport) -> str:
    """Format a GovernanceReport as Markdown for GitLab comments.

    Args:
        report: The governance report to format.

    Returns:
        Markdown-formatted string suitable for a GitLab MR note.
    """
    status = "PASSED" if report.passed else "FAILED"
    icon = "white_check_mark" if report.passed else "x"

    lines = [
        f"## Governance Report :{icon}:",
        "",
        "| Field | Value |",
        "|-------|-------|",
        f"| Status | **{status}** |",
        f"| Risk Score | {report.risk_score:.2f} |",
        f"| Rules Checked | {report.rules_checked} |",
        f"| Constitutional Hash | `{report.constitutional_hash}` |",
        "",
    ]

    if report.violations:
        lines.append("### Violations")
        lines.append("")
        for v in report.violations:
            sev = v.get("severity", "unknown").upper()
            source = v.get("source", "")
            file_ref = ""
            if v.get("file") and v.get("line"):
                file_ref = f" (`{v['file']}:{v['line']}`)"
            lines.append(
                f"- **[{sev}]** `{v['rule_id']}`: {v.get('rule_text', '')}{file_ref} ({source})"
            )
        lines.append("")

    if report.warnings:
        lines.append("### Warnings")
        lines.append("")
        for w in report.warnings:
            sev = w.get("severity", "unknown").upper()
            lines.append(f"- **[{sev}]** `{w['rule_id']}`: {w.get('rule_text', '')}")
        lines.append("")

    if report.commit_violations:
        lines.append("### Commit Message Violations")
        lines.append("")
        for cv in report.commit_violations:
            lines.append(f"- `{cv['sha']}` {cv['message']}")
            for v in cv.get("violations", []):
                lines.append(f"  - `{v['rule_id']}`: {v.get('rule_text', '')}")
        lines.append("")

    lines.append("---")
    lines.append("*Generated by ACGS Governance Bot*")

    return "\n".join(lines)


def create_gitlab_ci_config(constitution: Constitution | None = None) -> str:
    """Generate a .gitlab-ci.yml snippet for a governance pipeline stage.

    Args:
        constitution: Optional constitution for hash reference.

    Returns:
        YAML string for a GitLab CI governance stage.
    """
    constitution = constitution or Constitution.default()
    const_hash = constitution.hash

    return (
        "# ACGS Governance Pipeline Stage\n"
        "# Constitutional Hash: " + const_hash + "\n"
        "\n"
        "governance:\n"
        "  stage: test\n"
        "  image: python:3.11-slim\n"
        "  variables:\n"
        '    CONSTITUTIONAL_HASH: "' + const_hash + '"\n'
        "  before_script:\n"
        "    - pip install acgs[gitlab]\n"
        "  script:\n"
        '    - python -c "\n'
        "      import asyncio\n"
        "      from acgs_lite.integrations.gitlab import GitLabGovernanceBot\n"
        "      from acgs_lite import Constitution\n"
        "\n"
        "      async def main():\n"
        "          bot = GitLabGovernanceBot(\n"
        "              token=__import__('os').environ['GITLAB_TOKEN'],\n"
        "              project_id=int(__import__('os').environ['CI_PROJECT_ID']),\n"
        "          )\n"
        "          report = await bot.run_governance_pipeline(\n"
        "              mr_iid=int(__import__('os').environ['CI_MERGE_REQUEST_IID']),\n"
        "          )\n"
        "          assert report.passed, "
        "f'Governance: {len(report.violations)} violations'\n"
        "\n"
        "      asyncio.run(main())\n"
        '      "\n'
        "  rules:\n"
        "    - if: $CI_PIPELINE_SOURCE == 'merge_request_event'\n"
    )
