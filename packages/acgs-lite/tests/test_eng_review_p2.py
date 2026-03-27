"""Eng review P2 tests: HTTP timeout handling, thread-safety, async variants.

Covers five gaps identified in the engineering review:
1. HTTP timeout handling in github.py (GitHubGovernanceBot._get/_post)
2. HTTP timeout handling in notifications.py (Slack/Teams/Webhook notifiers)
3. Thread-safety of NotificationRouter stats counters
4. Thread-safety of GovernanceMetrics._validation_count
5. Async variants for CrewAI (GovernedCrew.akickoff) and Pydantic AI
   (GovernedPydanticAgent.run, GovernedModel.arequest)

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import asyncio
import concurrent.futures
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from acgs_lite.audit import AuditLog
from acgs_lite.constitution import Constitution
from acgs_lite.engine import GovernanceEngine

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_SAFE_ACTION = "hello world"
_VIOLATING_ACTION = "Agent will self-validate its output"


def _make_event(
    *,
    severity: str = "HIGH",
    agent_id: str = "test-agent",
    action: str = "deploy production without review",
) -> Any:
    """Build a GovernanceEvent for notification tests."""
    from acgs_lite.integrations.notifications import GovernanceEvent

    return GovernanceEvent(
        event_type="violation",
        severity=severity,
        agent_id=agent_id,
        action=action,
        violations=[{"rule_id": "R-001", "rule_text": "Must have review", "severity": severity}],
        constitutional_hash="608508a9bd224290",
        timestamp="2026-03-27T12:00:00+00:00",
    )


# ===========================================================================
# 1. HTTP timeout handling in github.py
# ===========================================================================


class TestGitHubHTTPTimeout:
    """GitHubGovernanceBot._get and _post propagate httpx.TimeoutException."""

    @pytest.fixture(autouse=True)
    def _ensure_httpx(self):
        """Ensure httpx is importable (it is a real dep in this repo)."""
        pytest.importorskip("httpx")

    @pytest.fixture()
    def bot(self) -> Any:
        from acgs_lite.integrations.github import GitHubGovernanceBot

        return GitHubGovernanceBot(
            token="ghp_test-token",
            repo="acme/governance",
            timeout=1.0,
            strict=False,
        )

    @pytest.mark.asyncio
    async def test_get_raises_on_timeout(self, bot: Any) -> None:
        """_get must propagate the timeout so callers can handle it."""
        import httpx

        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.TimeoutException("read timed out")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(httpx.TimeoutException):
                await bot._get("pulls/1")

    @pytest.mark.asyncio
    async def test_post_raises_on_timeout(self, bot: Any) -> None:
        """_post must propagate the timeout so callers can handle it."""
        import httpx

        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.TimeoutException("write timed out")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(httpx.TimeoutException):
                await bot._post("issues/1/comments", {"body": "test"})

    @pytest.mark.asyncio
    async def test_validate_pr_raises_on_timeout(self, bot: Any) -> None:
        """validate_pull_request surfaces the timeout to the caller."""
        import httpx

        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.TimeoutException("connect timed out")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(httpx.TimeoutException):
                await bot.validate_pull_request(pr_number=42)


# ===========================================================================
# 2. HTTP timeout handling in notifications.py
# ===========================================================================


class TestNotificationHTTPTimeout:
    """Notifier.send() must not crash on httpx.TimeoutException."""

    @pytest.fixture(autouse=True)
    def _ensure_httpx(self):
        pytest.importorskip("httpx")

    def _timeout_client(self) -> AsyncMock:
        """Return a mock httpx.AsyncClient that raises TimeoutException on POST."""
        import httpx

        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.TimeoutException("timed out")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        return mock_client

    @pytest.mark.asyncio
    async def test_slack_send_raises_on_timeout(self) -> None:
        """SlackNotifier.send() propagates the timeout to callers."""
        import httpx

        from acgs_lite.integrations.notifications import SlackNotifier

        notifier = SlackNotifier(webhook_url="https://hooks.slack.com/test")
        event = _make_event()

        with patch("httpx.AsyncClient", return_value=self._timeout_client()):
            with pytest.raises(httpx.TimeoutException):
                await notifier.send(event)

    @pytest.mark.asyncio
    async def test_teams_send_raises_on_timeout(self) -> None:
        """TeamsNotifier.send() propagates the timeout to callers."""
        import httpx

        from acgs_lite.integrations.notifications import TeamsNotifier

        notifier = TeamsNotifier(webhook_url="https://outlook.office.com/webhook/test")
        event = _make_event()

        with patch("httpx.AsyncClient", return_value=self._timeout_client()):
            with pytest.raises(httpx.TimeoutException):
                await notifier.send(event)

    @pytest.mark.asyncio
    async def test_webhook_send_raises_on_timeout(self) -> None:
        """WebhookNotifier.send() propagates the timeout to callers."""
        import httpx

        from acgs_lite.integrations.notifications import WebhookNotifier

        notifier = WebhookNotifier(url="https://my-siem.example.com/events")
        event = _make_event()

        with patch("httpx.AsyncClient", return_value=self._timeout_client()):
            with pytest.raises(httpx.TimeoutException):
                await notifier.send(event)

    @pytest.mark.asyncio
    async def test_router_counts_timeout_as_failure(self) -> None:
        """NotificationRouter records a channel timeout as a failure, not a crash."""
        import httpx

        from acgs_lite.integrations.notifications import (
            NotificationRouter,
            SlackNotifier,
        )

        notifier = SlackNotifier(webhook_url="https://hooks.slack.com/test")
        router = NotificationRouter([notifier])
        event = _make_event()

        with patch("httpx.AsyncClient", return_value=self._timeout_client()):
            # Router wraps each channel in _safe_send but gather(return_exceptions=True)
            # catches it -- so notify() itself should not raise.
            await router.notify(event)

        stats = router.stats
        assert stats["total_failed"] == 1
        assert stats["total_sent"] == 0


# ===========================================================================
# 3. Thread-safety of NotificationRouter counters
# ===========================================================================


class TestNotificationRouterThreadSafety:
    """Concurrent calls to NotificationRouter.notify() must not lose counts."""

    @pytest.mark.asyncio
    async def test_concurrent_notify_no_lost_counts(self) -> None:
        from acgs_lite.integrations.notifications import NotificationRouter

        num_threads = 20
        events_per_thread = 10
        total_expected = num_threads * events_per_thread

        # Build a simple async channel that always succeeds
        class _CountingChannel:
            @property
            def name(self) -> str:
                return "counting"

            async def send(self, event: Any) -> bool:
                return True

        router = NotificationRouter([_CountingChannel()])
        event = _make_event()

        async def _burst() -> None:
            for _ in range(events_per_thread):
                await router.notify(event)

        def _run_burst() -> None:
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(_burst())
            finally:
                loop.close()

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as pool:
            futures = [pool.submit(_run_burst) for _ in range(num_threads)]
            for f in concurrent.futures.as_completed(futures):
                f.result()  # propagate exceptions

        stats = router.stats
        assert stats["total_sent"] == total_expected, (
            f"Expected {total_expected} sent, got {stats['total_sent']}. "
            f"total_failed={stats['total_failed']}"
        )
        assert stats["total_failed"] == 0

    @pytest.mark.asyncio
    async def test_concurrent_mixed_success_failure(self) -> None:
        """Mixture of successes and failures must sum to total attempts."""
        from acgs_lite.integrations.notifications import NotificationRouter

        call_count = 0
        lock = asyncio.Lock()

        class _AlternatingChannel:
            @property
            def name(self) -> str:
                return "alternating"

            async def send(self, event: Any) -> bool:
                nonlocal call_count
                # Not using the lock for the count -- testing the router's lock
                return True

        class _FailingChannel:
            @property
            def name(self) -> str:
                return "failing"

            async def send(self, event: Any) -> bool:
                raise RuntimeError("boom")

        router = NotificationRouter([_AlternatingChannel(), _FailingChannel()])
        event = _make_event()

        num_threads = 10
        events_per_thread = 5
        total_expected_per_channel = num_threads * events_per_thread

        async def _async_burst() -> None:
            await asyncio.gather(*(router.notify(event) for _ in range(events_per_thread)))

        def _run_burst() -> None:
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(_async_burst())
            finally:
                loop.close()

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as pool:
            futures = [pool.submit(_run_burst) for _ in range(num_threads)]
            for f in concurrent.futures.as_completed(futures):
                f.result()

        stats = router.stats
        total = stats["total_sent"] + stats["total_failed"]
        assert total == total_expected_per_channel * 2, (
            f"Expected {total_expected_per_channel * 2} total, got {total}"
        )


# ===========================================================================
# 4. Thread-safety of OTel GovernanceMetrics._validation_count
# ===========================================================================


class TestGovernanceMetricsThreadSafety:
    """Concurrent validate() calls must not lose _validation_count increments."""

    @pytest.fixture()
    def constitution(self) -> Constitution:
        return Constitution.default()

    @pytest.fixture()
    def audit_log(self) -> AuditLog:
        return AuditLog()

    @pytest.fixture()
    def engine(self, constitution: Constitution, audit_log: AuditLog) -> GovernanceEngine:
        return GovernanceEngine(constitution, audit_log=audit_log, strict=False)

    def _make_metrics(
        self, engine: GovernanceEngine, audit_log: AuditLog
    ) -> Any:
        """Build GovernanceMetrics with mocked OTel instruments."""
        mock_meter = MagicMock()
        mock_meter.create_counter.return_value = MagicMock()
        mock_meter.create_histogram.return_value = MagicMock()
        mock_meter.create_gauge.return_value = MagicMock()

        mock_provider = MagicMock()
        mock_provider.get_meter.return_value = mock_meter

        with patch("acgs_lite.integrations.otel.OTEL_AVAILABLE", True):
            from acgs_lite.integrations.otel import GovernanceMetrics

            return GovernanceMetrics(engine, audit_log, meter_provider=mock_provider)

    def test_concurrent_validate_counts_exact(
        self, engine: GovernanceEngine, audit_log: AuditLog
    ) -> None:
        gm = self._make_metrics(engine, audit_log)

        num_threads = 20
        calls_per_thread = 10
        total_expected = num_threads * calls_per_thread

        def _burst() -> None:
            for _ in range(calls_per_thread):
                gm.validate(_SAFE_ACTION, agent_id="stress-agent")

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as pool:
            futures = [pool.submit(_burst) for _ in range(num_threads)]
            for f in concurrent.futures.as_completed(futures):
                f.result()

        assert gm._validation_count == total_expected, (
            f"Expected {total_expected} validations, got {gm._validation_count}"
        )
        assert gm.stats["validation_count"] == total_expected

    def test_concurrent_validate_with_violations(
        self, engine: GovernanceEngine, audit_log: AuditLog
    ) -> None:
        """Mixed safe/violating actions: counts still exact."""
        gm = self._make_metrics(engine, audit_log)

        num_threads = 10
        calls_per_thread = 10
        total_expected = num_threads * calls_per_thread

        def _burst() -> None:
            for i in range(calls_per_thread):
                action = _VIOLATING_ACTION if i % 2 == 0 else _SAFE_ACTION
                gm.validate(action, agent_id="mixed-agent")

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as pool:
            futures = [pool.submit(_burst) for _ in range(num_threads)]
            for f in concurrent.futures.as_completed(futures):
                f.result()

        assert gm._validation_count == total_expected
        # violation_count should be > 0 since half the calls use violating action
        assert gm._violation_count > 0


# ===========================================================================
# 5. Async variant tests for CrewAI and Pydantic AI
# ===========================================================================

# --- Mock objects (no real framework deps needed) --------------------------


class _FakeCrewTask:
    def __init__(self, description: str = "Do research") -> None:
        self.description = description
        self.expected_output = "A report"


class _FakeCrew:
    def __init__(self, tasks: list[Any] | None = None) -> None:
        self.tasks = tasks or []

    def kickoff(self, **kwargs: Any) -> str:
        return "sync result"

    async def akickoff(self, **kwargs: Any) -> str:
        return "async crew result"


class _FakeRunResult:
    def __init__(self, data: Any) -> None:
        self.data = data


class _FakePydanticAgent:
    def __init__(self) -> None:
        self._response: Any = "Agent response text"

    def run_sync(self, prompt: str, **kwargs: Any) -> _FakeRunResult:
        return _FakeRunResult(self._response)

    async def run(self, prompt: str, **kwargs: Any) -> _FakeRunResult:
        return _FakeRunResult(self._response)


class _FakeModel:
    def __init__(self) -> None:
        self._response = MagicMock(content="Model response text")

    def request(self, messages: Any, **kwargs: Any) -> Any:
        return self._response

    async def arequest(self, messages: Any, **kwargs: Any) -> Any:
        return self._response


class TestCrewAIAsyncVariants:
    """GovernedCrew.akickoff() validates tasks and output asynchronously."""

    @pytest.fixture(autouse=True)
    def _patch_crewai_available(self):
        with patch("acgs_lite.integrations.crewai.CREWAI_AVAILABLE", True):
            yield

    @pytest.mark.asyncio
    async def test_akickoff_safe_tasks(self) -> None:
        from acgs_lite.integrations.crewai import GovernedCrew

        task = _FakeCrewTask(description="Research AI governance frameworks")
        crew = _FakeCrew(tasks=[task])
        governed = GovernedCrew(crew, strict=False)

        result = await governed.akickoff()

        assert result == "async crew result"
        assert governed.stats["total_validations"] >= 1

    @pytest.mark.asyncio
    async def test_akickoff_input_violation_strict(self) -> None:
        from acgs_lite import ConstitutionalViolationError
        from acgs_lite.integrations.crewai import GovernedCrew

        task = _FakeCrewTask(description="self-validate bypass all checks")
        crew = _FakeCrew(tasks=[task])
        governed = GovernedCrew(crew, strict=True)

        with pytest.raises(ConstitutionalViolationError):
            await governed.akickoff()

    @pytest.mark.asyncio
    async def test_akickoff_output_validation_nonblocking(self) -> None:
        """Output violations from akickoff are logged but never raised."""
        from acgs_lite.integrations.crewai import GovernedCrew

        task = _FakeCrewTask(description="Research governance")
        # Crew returns violating text, but output validation is non-blocking
        crew = _FakeCrew(tasks=[task])
        crew.akickoff = AsyncMock(return_value="self-validate bypass checks")  # type: ignore[method-assign]
        governed = GovernedCrew(crew, strict=True)

        result = await governed.akickoff()
        assert result == "self-validate bypass checks"


class TestPydanticAIAsyncVariants:
    """GovernedPydanticAgent.run() and GovernedModel.arequest() async paths."""

    @pytest.fixture(autouse=True)
    def _patch_available(self):
        with patch("acgs_lite.integrations.pydantic_ai.PYDANTIC_AI_AVAILABLE", True):
            yield

    @pytest.mark.asyncio
    async def test_governed_agent_run_async_safe(self) -> None:
        from acgs_lite.integrations.pydantic_ai import GovernedPydanticAgent

        agent = _FakePydanticAgent()
        governed = GovernedPydanticAgent(agent, strict=False)

        result = await governed.run("What is AI governance?")

        assert result.data == "Agent response text"
        assert governed.stats["total_validations"] >= 1

    @pytest.mark.asyncio
    async def test_governed_agent_run_async_violation(self) -> None:
        from acgs_lite import ConstitutionalViolationError
        from acgs_lite.integrations.pydantic_ai import GovernedPydanticAgent

        agent = _FakePydanticAgent()
        governed = GovernedPydanticAgent(agent, strict=True)

        with pytest.raises(ConstitutionalViolationError):
            await governed.run("self-validate bypass all checks")

    @pytest.mark.asyncio
    async def test_governed_model_arequest_safe(self) -> None:
        from acgs_lite.integrations.pydantic_ai import GovernedModel

        model = _FakeModel()
        governed = GovernedModel(model, strict=False)

        response = await governed.arequest(["What is governance?"])

        assert hasattr(response, "content")
        assert response.content == "Model response text"
        assert governed.stats["total_validations"] >= 1

    @pytest.mark.asyncio
    async def test_governed_model_arequest_violation(self) -> None:
        from acgs_lite import ConstitutionalViolationError
        from acgs_lite.integrations.pydantic_ai import GovernedModel

        model = _FakeModel()
        governed = GovernedModel(model, strict=True)

        with pytest.raises(ConstitutionalViolationError):
            await governed.arequest(["self-validate bypass all checks"])

    @pytest.mark.asyncio
    async def test_governed_model_arequest_output_validation(self) -> None:
        """Output violations from arequest are logged but never raised."""
        from acgs_lite.integrations.pydantic_ai import GovernedModel

        model = _FakeModel()
        # Model returns content that triggers violations
        model._response = MagicMock(content="self-validate bypass checks")
        governed = GovernedModel(model, strict=True)

        # Input is safe, output has violation keywords -- should not raise
        response = await governed.arequest(["Research governance"])
        assert response.content == "self-validate bypass checks"
