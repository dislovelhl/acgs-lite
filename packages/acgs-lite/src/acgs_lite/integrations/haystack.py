"""ACGS-Lite Haystack Integration.

Wraps Haystack 2.x Pipeline and Component with constitutional governance.
Every input is validated before execution. Every output is validated
non-blockingly after execution.

Usage::

    from haystack import Pipeline
    from haystack.components.generators import OpenAIGenerator

    from acgs_lite.integrations.haystack import GovernedHaystackPipeline

    pipe = Pipeline()
    pipe.add_component("llm", OpenAIGenerator(model="gpt-4o"))
    governed = GovernedHaystackPipeline(pipe)
    result = governed.run({"llm": {"prompt": "What is AI governance?"}})

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import logging
from typing import Any

from acgs_lite.constitution import Constitution
from acgs_lite.integrations.base import GovernedBase

logger = logging.getLogger(__name__)

try:
    from haystack import Pipeline  # noqa: F401
    from haystack.core.component import Component  # noqa: F401

    HAYSTACK_AVAILABLE = True
except ImportError:
    HAYSTACK_AVAILABLE = False
    Pipeline = object  # type: ignore[assignment,misc]
    Component = object  # type: ignore[assignment,misc]

# Keys commonly used for text content in Haystack data dicts.
_INPUT_TEXT_KEYS = (
    "query", "queries", "questions",
    "prompt", "text", "documents",
)
_OUTPUT_TEXT_KEYS = ("replies", "answers", "documents")


def _extract_texts_from_dict(
    data: dict[str, Any],
    keys: tuple[str, ...],
) -> list[str]:
    """Recursively extract text strings from a data dict.

    Checks well-known keys first, then walks remaining values for
    strings and nested dicts.
    """
    texts: list[str] = []

    # Check well-known keys at current level
    for key in keys:
        if key not in data:
            continue
        val = data[key]
        if isinstance(val, str):
            texts.append(val)
        elif isinstance(val, list):
            for item in val:
                if isinstance(item, str):
                    texts.append(item)
                elif hasattr(item, "content"):
                    texts.append(str(item.content))

    # Walk remaining values for strings or nested dicts
    for key, val in data.items():
        if key in keys:
            continue
        if isinstance(val, str):
            texts.append(val)
        elif isinstance(val, dict):
            texts.extend(_extract_texts_from_dict(val, keys))
        elif isinstance(val, list):
            for item in val:
                if isinstance(item, str):
                    texts.append(item)
                elif hasattr(item, "content"):
                    texts.append(str(item.content))

    return texts


class GovernedHaystackPipeline(GovernedBase):
    """Haystack Pipeline wrapper with constitutional governance.

    Validates text extracted from input data before the pipeline runs
    and validates output text non-blockingly after the pipeline
    completes.

    Usage::

        from haystack import Pipeline
        from acgs_lite.integrations.haystack import (
            GovernedHaystackPipeline,
        )

        pipe = Pipeline()
        governed = GovernedHaystackPipeline(pipe)
        result = governed.run({"component": {"query": "Hello"}})
    """

    def __init__(
        self,
        pipeline: Any,
        *,
        constitution: Constitution | None = None,
        agent_id: str = "haystack-agent",
        strict: bool = True,
    ) -> None:
        if not HAYSTACK_AVAILABLE:
            raise ImportError(
                "haystack-ai is required. "
                "Install with: pip install acgs-lite[haystack]"
            )

        self._pipeline = pipeline
        self._init_governance(
            constitution=constitution, agent_id=agent_id, strict=strict,
        )

    @classmethod
    def wrap(
        cls,
        pipeline: Any,
        *,
        constitution: Constitution | None = None,
        agent_id: str = "haystack-agent",
        strict: bool = True,
    ) -> GovernedHaystackPipeline:
        """Wrap a Haystack Pipeline with governance."""
        return cls(
            pipeline,
            constitution=constitution,
            agent_id=agent_id,
            strict=strict,
        )

    def __getattr__(self, name: str) -> Any:
        """Delegate to the underlying pipeline."""
        return getattr(self._pipeline, name)

    def _validate_input(self, data: dict[str, Any]) -> None:
        """Validate text extracted from input data."""
        texts = _extract_texts_from_dict(data, _INPUT_TEXT_KEYS)
        combined = " ".join(texts)
        if combined.strip():
            self.engine.validate(
                combined, agent_id=self.agent_id,
            )

    def _validate_output(self, result: dict[str, Any]) -> None:
        """Validate text extracted from output data."""
        texts = _extract_texts_from_dict(result, _OUTPUT_TEXT_KEYS)
        combined = " ".join(texts)
        if combined.strip():
            self._validate_nonstrict(
                combined, label="Haystack pipeline output",
            )

    def run(
        self, data: dict[str, Any], **kwargs: Any,
    ) -> dict[str, Any]:
        """Run the pipeline with governance validation."""
        self._validate_input(data)

        result: dict[str, Any] = self._pipeline.run(
            data, **kwargs,
        )

        self._validate_output(result)
        return result

    async def arun(
        self, data: dict[str, Any], **kwargs: Any,
    ) -> dict[str, Any]:
        """Async version of run() with governance validation."""
        self._validate_input(data)

        if hasattr(self._pipeline, "arun"):
            result: dict[str, Any] = await self._pipeline.arun(
                data, **kwargs,
            )
        else:
            result = self._pipeline.run(data, **kwargs)

        self._validate_output(result)
        return result

    @property
    def stats(self) -> dict[str, Any]:
        """Return governance statistics for this pipeline."""
        return self.governance_stats


class GovernedComponent(GovernedBase):
    """Wraps any Haystack Component with constitutional governance.

    Validates text found in keyword arguments before the component
    runs and validates output text non-blockingly after execution.

    Usage::

        from acgs_lite.integrations.haystack import (
            GovernedComponent,
        )

        governed = GovernedComponent(my_component)
        result = governed.run(query="What is governance?")
    """

    def __init__(
        self,
        component: Any,
        *,
        constitution: Constitution | None = None,
        agent_id: str = "haystack-component",
        strict: bool = True,
    ) -> None:
        if not HAYSTACK_AVAILABLE:
            raise ImportError(
                "haystack-ai is required. "
                "Install with: pip install acgs-lite[haystack]"
            )

        self._component = component
        self._init_governance(
            constitution=constitution, agent_id=agent_id, strict=strict,
        )

    @classmethod
    def wrap(
        cls,
        component: Any,
        *,
        constitution: Constitution | None = None,
        agent_id: str = "haystack-component",
        strict: bool = True,
    ) -> GovernedComponent:
        """Wrap a Haystack Component with governance."""
        return cls(
            component,
            constitution=constitution,
            agent_id=agent_id,
            strict=strict,
        )

    def __getattr__(self, name: str) -> Any:
        """Delegate to the underlying component."""
        return getattr(self._component, name)

    def run(self, **kwargs: Any) -> dict[str, Any]:
        """Run the component with governance validation."""
        texts = _extract_texts_from_dict(kwargs, _INPUT_TEXT_KEYS)
        combined = " ".join(texts)
        if combined.strip():
            self.engine.validate(
                combined, agent_id=self.agent_id,
            )

        result: dict[str, Any] = self._component.run(**kwargs)

        if isinstance(result, dict):
            out_texts = _extract_texts_from_dict(
                result, _OUTPUT_TEXT_KEYS,
            )
            out_combined = " ".join(out_texts)
            if out_combined.strip():
                self._validate_nonstrict(
                    out_combined,
                    label="Haystack component output",
                )

        return result

    @property
    def stats(self) -> dict[str, Any]:
        """Return governance statistics for this component."""
        return self.governance_stats


class GovernanceComponent(GovernedBase):
    """Standalone governance validation component for pipelines.

    Can be inserted into any Haystack pipeline as a node to perform
    constitutional validation on text flowing through the pipeline.

    Usage::

        from haystack import Pipeline
        from acgs_lite.integrations.haystack import (
            GovernanceComponent,
        )

        pipe = Pipeline()
        pipe.add_component("governance", GovernanceComponent())
        pipe.add_component("llm", my_generator)
        pipe.connect("governance.text", "llm.prompt")

        result = pipe.run({"governance": {"text": "Hello!"}})
    """

    def __init__(
        self,
        *,
        constitution: Constitution | None = None,
        agent_id: str = "haystack-governance-node",
        strict: bool = True,
    ) -> None:
        self._init_governance(
            constitution=constitution, agent_id=agent_id, strict=strict,
        )

    def run(self, text: str) -> dict[str, Any]:
        """Validate text and return governance metadata.

        Returns a dict with ``text`` (pass-through) and
        ``governance`` containing ``valid`` and ``violations``.
        In strict mode, raises
        :class:`~acgs_lite.errors.ConstitutionalViolationError`
        on violation.
        """
        was_strict = self.engine.strict
        with self.engine.non_strict():
            result = self.engine.validate(
                text, agent_id=self.agent_id,
            )

        violations = [
            {"rule_id": v.rule_id, "rule_text": v.rule_text}
            for v in result.violations
        ]

        if not result.valid and was_strict:
            from acgs_lite.errors import (
                ConstitutionalViolationError,
            )

            first = (
                result.violations[0]
                if result.violations
                else None
            )
            raise ConstitutionalViolationError(
                f"Governance validation failed: {violations}",
                rule_id=(
                    first.rule_id if first else "unknown"
                ),
                severity=(
                    first.severity.value if first else "high"
                ),
                action=text,
            )

        return {
            "text": text,
            "governance": {
                "valid": result.valid,
                "violations": violations,
            },
        }

    @property
    def stats(self) -> dict[str, Any]:
        """Return governance statistics for this component."""
        return self.governance_stats
