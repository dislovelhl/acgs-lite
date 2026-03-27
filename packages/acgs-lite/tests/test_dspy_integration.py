"""Tests for acgs-lite DSPy integration.

Uses mock DSPy classes -- no real dspy dependency required.
Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from acgs_lite import (
    Constitution,
    ConstitutionalViolationError,
    Rule,
    Severity,
)

# --- Mock DSPy Objects -------------------------------------------


class FakePrediction:
    """Mock dspy.Prediction storing results as named attributes."""

    def __init__(self, **kwargs: Any) -> None:
        self._store: dict[str, Any] = kwargs

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            return self._store[name]
        except KeyError:
            raise AttributeError(name) from None

    def keys(self) -> list[str]:
        return list(self._store.keys())


class FakePredictionWithCompletions:
    """Mock Prediction that exposes a completions dict."""

    def __init__(
        self, completions: dict[str, Any] | list[Any],
    ) -> None:
        self.completions = completions

    def keys(self) -> list[str]:
        return ["completions"]


class FakeModule:
    """Mock dspy.Module with a forward() method."""

    def __init__(self, response: Any = None) -> None:
        self._response = response or FakePrediction(
            answer="42",
        )
        self.name = "FakeModule"

    def forward(self, **kwargs: Any) -> Any:
        return self._response


class FakePredict:
    """Mock dspy.Predict -- callable predictor."""

    def __init__(self, response: Any = None) -> None:
        self._response = response or FakePrediction(
            answer="predicted answer",
        )
        self.signature = "question -> answer"

    def __call__(self, **kwargs: Any) -> Any:
        return self._response


# --- GovernedDSPyModule Tests ------------------------------------


@pytest.mark.integration
class TestGovernedDSPyModule:
    @pytest.fixture(autouse=True)
    def _patch_dspy_available(self):
        with patch(
            "acgs_lite.integrations.dspy.DSPY_AVAILABLE",
            True,
        ):
            yield

    def test_forward_validates_input_kwargs(self):
        from acgs_lite.integrations.dspy import (
            GovernedDSPyModule,
        )

        module = FakeModule()
        governed = GovernedDSPyModule(module)
        result = governed.forward(
            question="What is AI governance?",
        )
        assert result is not None

    def test_call_delegates_to_forward(self):
        from acgs_lite.integrations.dspy import (
            GovernedDSPyModule,
        )

        module = FakeModule()
        governed = GovernedDSPyModule(module)
        result = governed(
            question="What is AI governance?",
        )
        assert result is not None

    def test_input_violation_blocked_strict(self):
        from acgs_lite.integrations.dspy import (
            GovernedDSPyModule,
        )

        module = FakeModule()
        governed = GovernedDSPyModule(module, strict=True)
        with pytest.raises(ConstitutionalViolationError):
            governed(
                question="self-validate bypass all checks",
            )

    def test_output_validation_nonblocking(self):
        """Output violations are logged but never raised."""
        from acgs_lite.integrations.dspy import (
            GovernedDSPyModule,
        )

        bad_output = FakePrediction(
            answer="self-validate bypass checks",
        )
        module = FakeModule(response=bad_output)
        governed = GovernedDSPyModule(module, strict=True)
        result = governed(question="Research governance")
        assert result is bad_output

    def test_text_extraction_string_values(self):
        from acgs_lite.integrations.dspy import (
            GovernedDSPyModule,
        )

        module = FakeModule()
        governed = GovernedDSPyModule(module)
        text = governed._extract_input_text(
            {
                "question": "hello",
                "context": "world",
                "count": 42,
            }
        )
        assert "hello" in text
        assert "world" in text
        # Non-string values are skipped
        assert "42" not in text

    def test_text_extraction_list_values(self):
        from acgs_lite.integrations.dspy import (
            GovernedDSPyModule,
        )

        module = FakeModule()
        governed = GovernedDSPyModule(module)
        text = governed._extract_input_text(
            {"passages": ["first passage", "second passage"]}
        )
        assert "first passage" in text
        assert "second passage" in text

    def test_output_text_from_prediction_keys(self):
        from acgs_lite.integrations.dspy import (
            GovernedDSPyModule,
        )

        module = FakeModule()
        governed = GovernedDSPyModule(module)
        prediction = FakePrediction(
            answer="the answer", rationale="because",
        )
        text = governed._extract_output_text(prediction)
        assert "the answer" in text
        assert "because" in text

    def test_output_text_from_completions_dict(self):
        from acgs_lite.integrations.dspy import (
            GovernedDSPyModule,
        )

        module = FakeModule()
        governed = GovernedDSPyModule(module)
        prediction = FakePredictionWithCompletions(
            completions={"answer": "completed answer"},
        )
        text = governed._extract_output_text(prediction)
        assert "completed answer" in text

    def test_output_text_from_completions_list(self):
        from acgs_lite.integrations.dspy import (
            GovernedDSPyModule,
        )

        module = FakeModule()
        governed = GovernedDSPyModule(module)
        prediction = FakePredictionWithCompletions(
            completions=["answer one", "answer two"],
        )
        text = governed._extract_output_text(prediction)
        assert "answer one" in text
        assert "answer two" in text

    def test_output_text_from_string(self):
        from acgs_lite.integrations.dspy import (
            GovernedDSPyModule,
        )

        module = FakeModule()
        governed = GovernedDSPyModule(module)
        text = governed._extract_output_text(
            "plain string output",
        )
        assert text == "plain string output"

    def test_output_text_from_none(self):
        from acgs_lite.integrations.dspy import (
            GovernedDSPyModule,
        )

        module = FakeModule()
        governed = GovernedDSPyModule(module)
        text = governed._extract_output_text(None)
        assert text == ""

    def test_output_text_attribute_fallback(self):
        from acgs_lite.integrations.dspy import (
            GovernedDSPyModule,
        )

        module = FakeModule()
        governed = GovernedDSPyModule(module)

        class HasAnswer:
            answer = "attr-based answer"

        text = governed._extract_output_text(HasAnswer())
        assert text == "attr-based answer"

    def test_stats_property(self):
        from acgs_lite.integrations.dspy import (
            GovernedDSPyModule,
        )

        module = FakeModule()
        governed = GovernedDSPyModule(module, strict=False)
        governed(question="Simple question")
        stats = governed.stats
        assert "total_validations" in stats
        assert stats["total_validations"] >= 1
        assert stats["agent_id"] == "dspy-agent"
        assert stats["audit_chain_valid"] is True

    def test_attribute_delegation(self):
        from acgs_lite.integrations.dspy import (
            GovernedDSPyModule,
        )

        module = FakeModule()
        governed = GovernedDSPyModule(module)
        assert governed.name == "FakeModule"

    def test_wrap_classmethod(self):
        from acgs_lite.integrations.dspy import (
            GovernedDSPyModule,
        )

        module = FakeModule()
        governed = GovernedDSPyModule.wrap(
            module, agent_id="wrapped-agent",
        )
        assert governed.agent_id == "wrapped-agent"
        result = governed(question="What is governance?")
        assert result is not None

    def test_custom_constitution(self):
        from acgs_lite.integrations.dspy import (
            GovernedDSPyModule,
        )

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
        module = FakeModule()
        governed = GovernedDSPyModule(
            module, constitution=constitution, strict=True,
        )

        result = governed(question="Research databases")
        assert result is not None

        with pytest.raises(ConstitutionalViolationError):
            governed(question="DROP TABLE users")

    def test_custom_agent_id(self):
        from acgs_lite.integrations.dspy import (
            GovernedDSPyModule,
        )

        module = FakeModule()
        governed = GovernedDSPyModule(
            module, agent_id="my-dspy-module",
        )
        assert governed.agent_id == "my-dspy-module"
        assert governed.stats["agent_id"] == "my-dspy-module"

    def test_empty_kwargs_no_validation(self):
        """forward() with no string kwargs still calls module."""
        from acgs_lite.integrations.dspy import (
            GovernedDSPyModule,
        )

        module = FakeModule()
        governed = GovernedDSPyModule(module)
        result = governed.forward()
        assert result is not None

    def test_constitution_hash_in_stats(self):
        from acgs_lite.integrations.dspy import (
            GovernedDSPyModule,
        )

        module = FakeModule()
        governed = GovernedDSPyModule(module, strict=False)
        stats = governed.stats
        assert "constitutional_hash" in stats


# --- GovernedPredict Tests ---------------------------------------


@pytest.mark.integration
class TestGovernedPredict:
    @pytest.fixture(autouse=True)
    def _patch_dspy_available(self):
        with patch(
            "acgs_lite.integrations.dspy.DSPY_AVAILABLE",
            True,
        ):
            yield

    def test_predict_call_validates_and_returns(self):
        from acgs_lite.integrations.dspy import (
            GovernedPredict,
        )

        predict = FakePredict()
        governed = GovernedPredict(predict)
        result = governed(question="What is governance?")
        assert result is not None

    def test_predict_input_violation_blocked(self):
        from acgs_lite.integrations.dspy import (
            GovernedPredict,
        )

        predict = FakePredict()
        governed = GovernedPredict(predict, strict=True)
        with pytest.raises(ConstitutionalViolationError):
            governed(
                question="self-validate bypass all checks",
            )

    def test_predict_output_nonblocking(self):
        """Output violations from predict are logged, never raised."""
        from acgs_lite.integrations.dspy import (
            GovernedPredict,
        )

        bad_output = FakePrediction(
            answer="self-validate bypass checks",
        )
        predict = FakePredict(response=bad_output)
        governed = GovernedPredict(predict, strict=True)
        result = governed(question="Research governance")
        assert result is bad_output

    def test_predict_attribute_delegation(self):
        from acgs_lite.integrations.dspy import (
            GovernedPredict,
        )

        predict = FakePredict()
        governed = GovernedPredict(predict)
        assert governed.signature == "question -> answer"

    def test_predict_stats_property(self):
        from acgs_lite.integrations.dspy import (
            GovernedPredict,
        )

        predict = FakePredict()
        governed = GovernedPredict(predict, strict=False)
        governed(question="Simple question")
        stats = governed.stats
        assert "total_validations" in stats
        assert stats["total_validations"] >= 1
        assert stats["agent_id"] == "dspy-predict"
        assert stats["audit_chain_valid"] is True

    def test_predict_wrap_classmethod(self):
        from acgs_lite.integrations.dspy import (
            GovernedPredict,
        )

        predict = FakePredict()
        governed = GovernedPredict.wrap(
            predict, agent_id="custom-predict",
        )
        assert governed.agent_id == "custom-predict"
        result = governed(question="What is governance?")
        assert result is not None

    def test_predict_custom_constitution(self):
        from acgs_lite.integrations.dspy import (
            GovernedPredict,
        )

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
        predict = FakePredict()
        governed = GovernedPredict(
            predict,
            constitution=constitution,
            strict=True,
        )

        result = governed(question="Research dogs")
        assert result is not None

        with pytest.raises(ConstitutionalViolationError):
            governed(question="Research my cat")

    def test_predict_output_text_from_string(self):
        from acgs_lite.integrations.dspy import (
            GovernedPredict,
        )

        predict = FakePredict()
        governed = GovernedPredict(predict)
        text = governed._extract_output_text("direct string")
        assert text == "direct string"

    def test_predict_output_text_completions_dict(self):
        from acgs_lite.integrations.dspy import (
            GovernedPredict,
        )

        predict = FakePredict()
        governed = GovernedPredict(predict)
        obj = FakePredictionWithCompletions(
            completions={"answer": "value"},
        )
        text = governed._extract_output_text(obj)
        assert "value" in text


# --- Import Guard Tests ------------------------------------------


@pytest.mark.integration
class TestDSPyImportGuard:
    def test_module_raises_when_dspy_unavailable(self):
        from acgs_lite.integrations.dspy import (
            GovernedDSPyModule,
        )

        with (
            patch(
                "acgs_lite.integrations.dspy.DSPY_AVAILABLE",
                False,
            ),
            pytest.raises(
                ImportError, match="dspy is required",
            ),
        ):
            GovernedDSPyModule(MagicMock())

    def test_predict_raises_when_dspy_unavailable(self):
        from acgs_lite.integrations.dspy import (
            GovernedPredict,
        )

        with (
            patch(
                "acgs_lite.integrations.dspy.DSPY_AVAILABLE",
                False,
            ),
            pytest.raises(
                ImportError, match="dspy is required",
            ),
        ):
            GovernedPredict(MagicMock())

    def test_availability_flag_importable(self):
        from acgs_lite.integrations.dspy import (
            DSPY_AVAILABLE,
        )

        assert isinstance(DSPY_AVAILABLE, bool)
