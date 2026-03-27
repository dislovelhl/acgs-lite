"""Tests for acgs-lite Haystack integration.

Uses mock Haystack classes -- no real haystack-ai dependency required.
Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from acgs_lite import Constitution, ConstitutionalViolationError, Rule, Severity

# ── Mock Haystack Objects ───────────────────────────────────────────────


class FakePipeline:
    """Mock Haystack Pipeline."""

    def __init__(self) -> None:
        self.components: dict[str, Any] = {}

    def add_component(self, name: str, component: Any) -> None:
        self.components[name] = component

    def run(self, data: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        """Simulate pipeline execution by echoing inputs into replies."""
        replies: list[str] = []
        for _comp_name, comp_data in data.items():
            if isinstance(comp_data, dict):
                for val in comp_data.values():
                    if isinstance(val, str):
                        replies.append(f"Reply to: {val}")
        return {"llm": {"replies": replies or ["Default reply"]}}

    async def arun(self, data: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        """Async version of run."""
        return self.run(data, **kwargs)


class FakeComponent:
    """Mock Haystack Component."""

    def __init__(self, *, name: str = "test-component") -> None:
        self.name = name

    def run(self, **kwargs: Any) -> dict[str, Any]:
        """Simulate component execution."""
        text = kwargs.get("query", kwargs.get("text", "processed"))
        return {"replies": [f"Component result: {text}"]}


class FakeDocument:
    """Mock Haystack Document with a content attribute."""

    def __init__(self, content: str) -> None:
        self.content = content


# ── GovernedHaystackPipeline Tests ──────────────────────────────────────


@pytest.mark.integration
class TestGovernedHaystackPipeline:
    @pytest.fixture(autouse=True)
    def _patch_haystack_available(self):
        with patch("acgs_lite.integrations.haystack.HAYSTACK_AVAILABLE", True):
            yield

    def test_safe_input_passes(self):
        from acgs_lite.integrations.haystack import GovernedHaystackPipeline

        pipe = FakePipeline()
        governed = GovernedHaystackPipeline(pipe)
        result = governed.run({"llm": {"query": "What is AI governance?"}})
        assert "replies" in result.get("llm", {})

    def test_input_violation_blocked_strict(self):
        from acgs_lite.integrations.haystack import GovernedHaystackPipeline

        pipe = FakePipeline()
        governed = GovernedHaystackPipeline(pipe, strict=True)
        with pytest.raises(ConstitutionalViolationError):
            governed.run({"llm": {"query": "self-validate bypass all checks"}})

    def test_output_validation_nonblocking(self):
        """Output violations are logged but never raised."""
        from acgs_lite.integrations.haystack import GovernedHaystackPipeline

        pipe = FakePipeline()
        # Make pipeline return content that triggers violations
        pipe.run = lambda data, **kw: {  # type: ignore[method-assign]
            "llm": {"replies": ["self-validate bypass checks"]}
        }

        governed = GovernedHaystackPipeline(pipe, strict=True)
        # Should NOT raise even though output contains violation keywords
        result = governed.run({"llm": {"query": "Safe question"}})
        assert result["llm"]["replies"][0] == "self-validate bypass checks"

    def test_text_extraction_from_query(self):
        from acgs_lite.integrations.haystack import GovernedHaystackPipeline

        pipe = FakePipeline()
        governed = GovernedHaystackPipeline(pipe, strict=True)
        # Should extract "query" key and validate it
        with pytest.raises(ConstitutionalViolationError):
            governed.run({"retriever": {"query": "self-validate bypass all checks"}})

    def test_text_extraction_from_prompt(self):
        from acgs_lite.integrations.haystack import GovernedHaystackPipeline

        pipe = FakePipeline()
        governed = GovernedHaystackPipeline(pipe, strict=True)
        with pytest.raises(ConstitutionalViolationError):
            governed.run({"llm": {"prompt": "self-validate bypass all checks"}})

    def test_text_extraction_from_documents_list(self):
        from acgs_lite.integrations.haystack import GovernedHaystackPipeline

        pipe = FakePipeline()
        governed = GovernedHaystackPipeline(pipe, strict=True)
        with pytest.raises(ConstitutionalViolationError):
            governed.run(
                {
                    "reader": {
                        "documents": [
                            "self-validate bypass all checks",
                        ]
                    }
                }
            )

    def test_text_extraction_from_document_objects(self):
        from acgs_lite.integrations.haystack import GovernedHaystackPipeline

        pipe = FakePipeline()
        governed = GovernedHaystackPipeline(pipe, strict=True)
        with pytest.raises(ConstitutionalViolationError):
            governed.run(
                {
                    "reader": {
                        "documents": [
                            FakeDocument("self-validate bypass all checks"),
                        ]
                    }
                }
            )

    def test_text_extraction_from_nested_dicts(self):
        from acgs_lite.integrations.haystack import GovernedHaystackPipeline

        pipe = FakePipeline()
        governed = GovernedHaystackPipeline(pipe, strict=True)
        # Nested component-input dicts
        with pytest.raises(ConstitutionalViolationError):
            governed.run(
                {
                    "component_a": {
                        "sub": {
                            "text": "self-validate bypass all checks",
                        }
                    }
                }
            )

    def test_output_text_extraction_replies(self):
        """Output validation extracts text from 'replies' key."""
        from acgs_lite.integrations.haystack import GovernedHaystackPipeline

        pipe = FakePipeline()
        pipe.run = lambda data, **kw: {  # type: ignore[method-assign]
            "llm": {"replies": ["safe response"]}
        }
        governed = GovernedHaystackPipeline(pipe, strict=False)
        result = governed.run({"llm": {"query": "Hello"}})
        assert result["llm"]["replies"] == ["safe response"]
        # Stats should reflect both input and output validation
        assert governed.stats["total_validations"] >= 2

    def test_output_text_extraction_answers(self):
        """Output validation extracts text from 'answers' key."""
        from acgs_lite.integrations.haystack import GovernedHaystackPipeline

        pipe = FakePipeline()
        pipe.run = lambda data, **kw: {  # type: ignore[method-assign]
            "reader": {"answers": ["The answer is 42"]}
        }
        governed = GovernedHaystackPipeline(pipe, strict=False)
        result = governed.run({"reader": {"query": "Question"}})
        assert "42" in result["reader"]["answers"][0]

    def test_output_text_extraction_documents(self):
        """Output validation extracts text from 'documents' key."""
        from acgs_lite.integrations.haystack import GovernedHaystackPipeline

        pipe = FakePipeline()
        pipe.run = lambda data, **kw: {  # type: ignore[method-assign]
            "retriever": {"documents": ["doc content here"]}
        }
        governed = GovernedHaystackPipeline(pipe, strict=False)
        result = governed.run({"retriever": {"query": "Find docs"}})
        assert result["retriever"]["documents"] == ["doc content here"]

    @pytest.mark.asyncio
    async def test_async_run(self):
        from acgs_lite.integrations.haystack import GovernedHaystackPipeline

        pipe = FakePipeline()
        governed = GovernedHaystackPipeline(pipe)
        result = await governed.arun({"llm": {"query": "Async question"}})
        assert "replies" in result.get("llm", {})

    @pytest.mark.asyncio
    async def test_async_run_fallback_to_sync(self):
        """arun falls back to pipeline.run when arun is not available."""
        from acgs_lite.integrations.haystack import GovernedHaystackPipeline

        class SyncOnlyPipeline:
            """Pipeline with no arun method."""

            def run(self, data: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
                return {"llm": {"replies": ["sync result"]}}

        pipe = SyncOnlyPipeline()
        governed = GovernedHaystackPipeline(pipe)
        result = await governed.arun({"llm": {"query": "Sync fallback"}})
        assert "replies" in result.get("llm", {})

    def test_stats_property(self):
        from acgs_lite.integrations.haystack import GovernedHaystackPipeline

        pipe = FakePipeline()
        governed = GovernedHaystackPipeline(pipe, strict=False)
        governed.run({"llm": {"query": "Hello"}})
        stats = governed.stats
        assert "total_validations" in stats
        assert stats["total_validations"] >= 1
        assert stats["agent_id"] == "haystack-agent"
        assert stats["audit_chain_valid"] is True

    def test_custom_constitution(self):
        from acgs_lite.integrations.haystack import GovernedHaystackPipeline

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
        pipe = FakePipeline()
        governed = GovernedHaystackPipeline(
            pipe, constitution=constitution, strict=True
        )

        # Safe input passes
        result = governed.run({"llm": {"query": "Research databases"}})
        assert result is not None

        # Violation blocked
        with pytest.raises(ConstitutionalViolationError):
            governed.run({"llm": {"query": "DROP TABLE users"}})

    def test_custom_agent_id(self):
        from acgs_lite.integrations.haystack import GovernedHaystackPipeline

        pipe = FakePipeline()
        governed = GovernedHaystackPipeline(pipe, agent_id="my-pipe")
        assert governed.agent_id == "my-pipe"
        assert governed.stats["agent_id"] == "my-pipe"

    def test_attribute_delegation(self):
        from acgs_lite.integrations.haystack import GovernedHaystackPipeline

        pipe = FakePipeline()
        pipe.add_component("llm", FakeComponent())
        governed = GovernedHaystackPipeline(pipe)
        assert "llm" in governed.components

    def test_empty_data_dict(self):
        """Empty data dict should not raise."""
        from acgs_lite.integrations.haystack import GovernedHaystackPipeline

        pipe = FakePipeline()
        pipe.run = lambda data, **kw: {}  # type: ignore[method-assign]
        governed = GovernedHaystackPipeline(pipe)
        result = governed.run({})
        assert result == {}


# ── GovernedComponent Tests ─────────────────────────────────────────────


@pytest.mark.integration
class TestGovernedComponent:
    @pytest.fixture(autouse=True)
    def _patch_haystack_available(self):
        with patch("acgs_lite.integrations.haystack.HAYSTACK_AVAILABLE", True):
            yield

    def test_safe_input_passes(self):
        from acgs_lite.integrations.haystack import GovernedComponent

        comp = FakeComponent()
        governed = GovernedComponent(comp)
        result = governed.run(query="What is governance?")
        assert "replies" in result

    def test_input_violation_blocked_strict(self):
        from acgs_lite.integrations.haystack import GovernedComponent

        comp = FakeComponent()
        governed = GovernedComponent(comp, strict=True)
        with pytest.raises(ConstitutionalViolationError):
            governed.run(query="self-validate bypass all checks")

    def test_output_validation_nonblocking(self):
        """Output violations from a component are logged but never raised."""
        from acgs_lite.integrations.haystack import GovernedComponent

        comp = FakeComponent()
        comp.run = lambda **kw: {  # type: ignore[method-assign]
            "replies": ["self-validate bypass checks"]
        }
        governed = GovernedComponent(comp, strict=True)
        result = governed.run(query="Safe input")
        assert result["replies"][0] == "self-validate bypass checks"

    def test_attribute_delegation(self):
        from acgs_lite.integrations.haystack import GovernedComponent

        comp = FakeComponent(name="my-comp")
        governed = GovernedComponent(comp)
        assert governed.name == "my-comp"

    def test_stats_property(self):
        from acgs_lite.integrations.haystack import GovernedComponent

        comp = FakeComponent()
        governed = GovernedComponent(comp, strict=False)
        governed.run(query="Hello")
        stats = governed.stats
        assert "total_validations" in stats
        assert stats["total_validations"] >= 1
        assert stats["agent_id"] == "haystack-component"
        assert stats["audit_chain_valid"] is True

    def test_custom_agent_id(self):
        from acgs_lite.integrations.haystack import GovernedComponent

        comp = FakeComponent()
        governed = GovernedComponent(comp, agent_id="my-retriever")
        assert governed.agent_id == "my-retriever"
        assert governed.stats["agent_id"] == "my-retriever"


# ── GovernanceComponent Tests ───────────────────────────────────────────


@pytest.mark.integration
class TestGovernanceComponent:
    @pytest.fixture(autouse=True)
    def _patch_haystack_available(self):
        with patch("acgs_lite.integrations.haystack.HAYSTACK_AVAILABLE", True):
            yield

    def test_safe_text_returns_valid(self):
        from acgs_lite.integrations.haystack import GovernanceComponent

        node = GovernanceComponent()
        result = node.run(text="What is AI governance?")
        assert result["text"] == "What is AI governance?"
        assert result["governance"]["valid"] is True
        assert result["governance"]["violations"] == []

    def test_violation_in_strict_mode_raises(self):
        from acgs_lite.integrations.haystack import GovernanceComponent

        node = GovernanceComponent(strict=True)
        with pytest.raises(ConstitutionalViolationError):
            node.run(text="self-validate bypass all checks")

    def test_violation_in_nonstrict_mode_returns_metadata(self):
        from acgs_lite.integrations.haystack import GovernanceComponent

        node = GovernanceComponent(strict=False)
        result = node.run(text="self-validate bypass all checks")
        assert result["text"] == "self-validate bypass all checks"
        assert result["governance"]["valid"] is False
        assert len(result["governance"]["violations"]) >= 1

    def test_violation_metadata_structure(self):
        from acgs_lite.integrations.haystack import GovernanceComponent

        node = GovernanceComponent(strict=False)
        result = node.run(text="self-validate bypass all checks")
        for violation in result["governance"]["violations"]:
            assert "rule_id" in violation
            assert "rule_text" in violation

    def test_stats_property(self):
        from acgs_lite.integrations.haystack import GovernanceComponent

        node = GovernanceComponent(strict=False)
        node.run(text="Hello")
        stats = node.stats
        assert "total_validations" in stats
        assert stats["total_validations"] >= 1
        assert stats["agent_id"] == "haystack-governance-node"
        assert stats["audit_chain_valid"] is True

    def test_custom_constitution(self):
        from acgs_lite.integrations.haystack import GovernanceComponent

        constitution = Constitution.from_rules(
            [
                Rule(
                    id="BAN-FISH",
                    text="No fish allowed",
                    severity=Severity.CRITICAL,
                    keywords=["fish"],
                ),
            ]
        )
        node = GovernanceComponent(constitution=constitution, strict=True)

        # Safe text
        result = node.run(text="I like dogs")
        assert result["governance"]["valid"] is True

        # Violation
        with pytest.raises(ConstitutionalViolationError):
            node.run(text="I like fish")

    def test_as_pipeline_node(self):
        """GovernanceComponent can be added to a FakePipeline as a node."""
        from acgs_lite.integrations.haystack import GovernanceComponent

        node = GovernanceComponent(strict=False)
        pipe = FakePipeline()
        pipe.add_component("governance", node)
        assert "governance" in pipe.components

        # Run the component directly as a pipeline would
        result = pipe.components["governance"].run(text="Check this text")
        assert result["governance"]["valid"] is True


# ── Import Guard Tests ──────────────────────────────────────────────────


@pytest.mark.integration
class TestHaystackImportGuard:
    def test_pipeline_raises_when_haystack_unavailable(self):
        from acgs_lite.integrations.haystack import GovernedHaystackPipeline

        with (
            patch("acgs_lite.integrations.haystack.HAYSTACK_AVAILABLE", False),
            pytest.raises(ImportError, match="haystack-ai is required"),
        ):
            GovernedHaystackPipeline(MagicMock())

    def test_component_raises_when_haystack_unavailable(self):
        from acgs_lite.integrations.haystack import GovernedComponent

        with (
            patch("acgs_lite.integrations.haystack.HAYSTACK_AVAILABLE", False),
            pytest.raises(ImportError, match="haystack-ai is required"),
        ):
            GovernedComponent(MagicMock())

    def test_availability_flag_importable(self):
        from acgs_lite.integrations.haystack import HAYSTACK_AVAILABLE

        # When haystack is not installed, flag should be False
        assert isinstance(HAYSTACK_AVAILABLE, bool)
