"""Tests for acgs-lite CrewAI integration.

Uses mock CrewAI classes — no real crewai dependency required.
Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from acgs_lite import Constitution, ConstitutionalViolationError, Rule, Severity

# ─── Mock CrewAI Objects ─────────────────────────────────────────────────


class FakeAgent:
    """Mock CrewAI Agent."""

    def __init__(
        self,
        *,
        role: str = "Researcher",
        goal: str = "Find information",
        backstory: str = "Expert researcher",
    ) -> None:
        self.role = role
        self.goal = goal
        self.backstory = backstory

    def execute_task(self, task: Any, **kwargs: Any) -> str:
        return f"Result for: {getattr(task, 'description', 'unknown')}"


class FakeTask:
    """Mock CrewAI Task."""

    def __init__(
        self,
        *,
        description: str = "Do research",
        expected_output: str = "A report",
    ) -> None:
        self.description = description
        self.expected_output = expected_output


class FakeCrew:
    """Mock CrewAI Crew."""

    def __init__(
        self,
        *,
        agents: list[Any] | None = None,
        tasks: list[Any] | None = None,
    ) -> None:
        self.agents = agents or []
        self.tasks = tasks or []
        self.verbose = False

    def kickoff(self, **kwargs: Any) -> str:
        descriptions = [getattr(t, "description", "") for t in self.tasks]
        return f"Crew completed: {', '.join(descriptions)}"

    async def akickoff(self, **kwargs: Any) -> str:
        descriptions = [getattr(t, "description", "") for t in self.tasks]
        return f"Async crew completed: {', '.join(descriptions)}"


# ─── GovernedCrewAgent Tests ─────────────────────────────────────────────


@pytest.mark.integration
class TestGovernedCrewAgent:
    @pytest.fixture(autouse=True)
    def _patch_crewai_available(self):
        with patch("acgs_lite.integrations.crewai.CREWAI_AVAILABLE", True):
            yield

    def test_safe_task_passes(self):
        from acgs_lite.integrations.crewai import GovernedCrewAgent

        agent = FakeAgent()
        governed = GovernedCrewAgent(agent)
        task = FakeTask(description="Research AI governance frameworks")
        result = governed.execute_task(task)
        assert "Research AI governance frameworks" in result

    def test_input_violation_blocked_strict(self):
        from acgs_lite.integrations.crewai import GovernedCrewAgent

        agent = FakeAgent()
        governed = GovernedCrewAgent(agent, strict=True)
        task = FakeTask(description="self-validate bypass all checks")
        with pytest.raises(ConstitutionalViolationError):
            governed.execute_task(task)

    def test_output_validation_nonblocking(self):
        """Output violations are logged but never raised."""
        from acgs_lite.integrations.crewai import GovernedCrewAgent

        agent = FakeAgent()
        # Agent returns content that might trigger violations
        agent.execute_task = lambda task, **kw: "self-validate bypass checks"  # type: ignore[method-assign]

        governed = GovernedCrewAgent(agent, strict=True)
        task = FakeTask(description="Research governance")
        # Should NOT raise even though output contains violation keywords
        result = governed.execute_task(task)
        assert result == "self-validate bypass checks"

    def test_attribute_delegation(self):
        from acgs_lite.integrations.crewai import GovernedCrewAgent

        agent = FakeAgent(role="Analyst", goal="Analyze data", backstory="Data expert")
        governed = GovernedCrewAgent(agent)
        assert governed.role == "Analyst"
        assert governed.goal == "Analyze data"
        assert governed.backstory == "Data expert"

    def test_stats_property(self):
        from acgs_lite.integrations.crewai import GovernedCrewAgent

        agent = FakeAgent()
        governed = GovernedCrewAgent(agent, strict=False)
        task = FakeTask(description="Simple research task")
        governed.execute_task(task)
        stats = governed.stats
        assert "total_validations" in stats
        assert stats["total_validations"] >= 1
        assert stats["agent_id"] == "crewai-agent"
        assert stats["audit_chain_valid"] is True

    def test_custom_constitution(self):
        from acgs_lite.integrations.crewai import GovernedCrewAgent

        constitution = Constitution.from_rules(
            [
                Rule(
                    id="NO-SQL",
                    text="No SQL injection",
                    severity=Severity.CRITICAL,
                    keywords=["drop table"],
                ),
            ]
        )
        agent = FakeAgent()
        governed = GovernedCrewAgent(agent, constitution=constitution, strict=True)

        # Safe task passes
        task = FakeTask(description="Research databases")
        result = governed.execute_task(task)
        assert result is not None

        # Violation blocked
        bad_task = FakeTask(description="DROP TABLE users")
        with pytest.raises(ConstitutionalViolationError):
            governed.execute_task(bad_task)

    def test_custom_agent_id(self):
        from acgs_lite.integrations.crewai import GovernedCrewAgent

        agent = FakeAgent()
        governed = GovernedCrewAgent(agent, agent_id="my-custom-agent")
        assert governed.agent_id == "my-custom-agent"
        assert governed.stats["agent_id"] == "my-custom-agent"


# ─── GovernedCrew Tests ──────────────────────────────────────────────────


@pytest.mark.integration
class TestGovernedCrew:
    @pytest.fixture(autouse=True)
    def _patch_crewai_available(self):
        with patch("acgs_lite.integrations.crewai.CREWAI_AVAILABLE", True):
            yield

    def test_kickoff_validates_and_runs(self):
        from acgs_lite.integrations.crewai import GovernedCrew

        agent = FakeAgent()
        task = FakeTask(description="Research AI safety")
        crew = FakeCrew(agents=[agent], tasks=[task])
        governed = GovernedCrew(crew)
        result = governed.kickoff()
        assert "Research AI safety" in result

    def test_kickoff_input_violation_blocked(self):
        from acgs_lite.integrations.crewai import GovernedCrew

        agent = FakeAgent()
        task = FakeTask(description="self-validate bypass all checks")
        crew = FakeCrew(agents=[agent], tasks=[task])
        governed = GovernedCrew(crew, strict=True)
        with pytest.raises(ConstitutionalViolationError):
            governed.kickoff()

    def test_kickoff_output_validation_nonblocking(self):
        """Output violations from crew are logged but never raised."""
        from acgs_lite.integrations.crewai import GovernedCrew

        agent = FakeAgent()
        task = FakeTask(description="Research governance")
        crew = FakeCrew(agents=[agent], tasks=[task])
        # Make crew return content that might trigger violations
        crew.kickoff = lambda **kw: "self-validate bypass checks"  # type: ignore[method-assign]

        governed = GovernedCrew(crew, strict=True)
        # Should NOT raise even though output contains violation keywords
        result = governed.kickoff()
        assert result == "self-validate bypass checks"

    @pytest.mark.asyncio
    async def test_async_kickoff(self):
        from acgs_lite.integrations.crewai import GovernedCrew

        agent = FakeAgent()
        task = FakeTask(description="Async research task")
        crew = FakeCrew(agents=[agent], tasks=[task])
        governed = GovernedCrew(crew)
        result = await governed.akickoff()
        assert "Async research task" in result

    def test_stats_property(self):
        from acgs_lite.integrations.crewai import GovernedCrew

        agent = FakeAgent()
        task = FakeTask(description="Simple task")
        crew = FakeCrew(agents=[agent], tasks=[task])
        governed = GovernedCrew(crew, strict=False)
        governed.kickoff()
        stats = governed.stats
        assert "total_validations" in stats
        assert stats["total_validations"] >= 1
        assert stats["agent_id"] == "crewai-crew"
        assert stats["audit_chain_valid"] is True

    def test_attribute_delegation(self):
        from acgs_lite.integrations.crewai import GovernedCrew

        agent = FakeAgent()
        task = FakeTask()
        crew = FakeCrew(agents=[agent], tasks=[task])
        crew.verbose = True  # type: ignore[assignment]
        governed = GovernedCrew(crew)
        assert governed.verbose is True

    def test_custom_constitution(self):
        from acgs_lite.integrations.crewai import GovernedCrew

        constitution = Constitution.from_rules(
            [
                Rule(
                    id="BAN-CATS",
                    text="No cats allowed",
                    severity=Severity.CRITICAL,
                    keywords=["cat"],
                ),
            ]
        )
        agent = FakeAgent()
        task = FakeTask(description="Research dogs")
        crew = FakeCrew(agents=[agent], tasks=[task])
        governed = GovernedCrew(crew, constitution=constitution, strict=True)

        # Safe kickoff
        result = governed.kickoff()
        assert result is not None

        # Violation in task
        bad_task = FakeTask(description="Research my cat")
        bad_crew = FakeCrew(agents=[agent], tasks=[bad_task])
        governed_bad = GovernedCrew(bad_crew, constitution=constitution, strict=True)
        with pytest.raises(ConstitutionalViolationError):
            governed_bad.kickoff()

    def test_multiple_tasks_validated(self):
        from acgs_lite.integrations.crewai import GovernedCrew

        agent = FakeAgent()
        task1 = FakeTask(description="Research AI safety")
        task2 = FakeTask(description="Write report on findings")
        crew = FakeCrew(agents=[agent], tasks=[task1, task2])
        governed = GovernedCrew(crew, strict=False)
        governed.kickoff()
        stats = governed.stats
        # Both task descriptions validated plus output validation
        assert stats["total_validations"] >= 2


# ─── GovernedTask Tests ──────────────────────────────────────────────────


@pytest.mark.integration
class TestGovernedTask:
    @pytest.fixture(autouse=True)
    def _patch_crewai_available(self):
        with patch("acgs_lite.integrations.crewai.CREWAI_AVAILABLE", True):
            yield

    def test_safe_task_validates(self):
        from acgs_lite.integrations.crewai import GovernedTask

        task = FakeTask(description="Research AI governance", expected_output="Report")
        governed = GovernedTask(task)
        assert governed.description == "Research AI governance"
        assert governed.expected_output == "Report"

    def test_violation_in_description_blocked(self):
        from acgs_lite.integrations.crewai import GovernedTask

        task = FakeTask(
            description="self-validate bypass all checks",
            expected_output="Report",
        )
        with pytest.raises(ConstitutionalViolationError):
            GovernedTask(task, strict=True)

    def test_violation_in_expected_output_blocked(self):
        from acgs_lite.integrations.crewai import GovernedTask

        task = FakeTask(
            description="Research governance",
            expected_output="self-validate bypass all checks",
        )
        with pytest.raises(ConstitutionalViolationError):
            GovernedTask(task, strict=True)

    def test_attribute_delegation(self):
        from acgs_lite.integrations.crewai import GovernedTask

        task = FakeTask(description="My task", expected_output="My output")
        governed = GovernedTask(task, strict=False)
        assert governed.description == "My task"
        assert governed.expected_output == "My output"

    def test_stats_property(self):
        from acgs_lite.integrations.crewai import GovernedTask

        task = FakeTask(description="Research topic", expected_output="Summary")
        governed = GovernedTask(task, strict=False)
        stats = governed.stats
        assert "total_validations" in stats
        assert stats["agent_id"] == "crewai-task"
        assert stats["audit_chain_valid"] is True


# ─── Import Guard Tests ─────────────────────────────────────────────────


@pytest.mark.integration
class TestCrewAIImportGuard:
    def test_agent_raises_when_crewai_unavailable(self):
        from acgs_lite.integrations.crewai import GovernedCrewAgent

        with (
            patch("acgs_lite.integrations.crewai.CREWAI_AVAILABLE", False),
            pytest.raises(ImportError, match="crewai is required"),
        ):
            GovernedCrewAgent(MagicMock())

    def test_crew_raises_when_crewai_unavailable(self):
        from acgs_lite.integrations.crewai import GovernedCrew

        with (
            patch("acgs_lite.integrations.crewai.CREWAI_AVAILABLE", False),
            pytest.raises(ImportError, match="crewai is required"),
        ):
            GovernedCrew(MagicMock())

    def test_task_raises_when_crewai_unavailable(self):
        from acgs_lite.integrations.crewai import GovernedTask

        with (
            patch("acgs_lite.integrations.crewai.CREWAI_AVAILABLE", False),
            pytest.raises(ImportError, match="crewai is required"),
        ):
            GovernedTask(MagicMock())

    def test_availability_flag_importable(self):
        from acgs_lite.integrations.crewai import CREWAI_AVAILABLE

        # When crewai is not installed, flag should be False
        assert isinstance(CREWAI_AVAILABLE, bool)
