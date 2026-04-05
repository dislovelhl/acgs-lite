"""
ACGS-2 Response Quality Enhancement - Refiner
Constitutional Hash: 608508a9bd224290

Iterative response refinement with constitutional compliance integration.
"""

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
from enhanced_agent_bus._compat.errors import ACGSBaseError

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.llm_adapters.base import BaseLLMAdapter, LLMMessage
from enhanced_agent_bus.observability.structured_logging import get_logger

from .models import (
    QualityAssessment,
    RefinementIteration,
    RefinementResult,
    RefinementStatus,
)
from .validator import ResponseQualityValidator

logger = get_logger(__name__)
REFINEMENT_ITERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
)
ASYNC_REFINEMENT_ITERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
)


class RefinementError(ACGSBaseError):
    """Raised when refinement fails."""

    http_status_code = 500
    error_code = "REFINEMENT_ERROR"


class ConstitutionalViolationError(ACGSBaseError):
    """Raised when constitutional principles are violated."""

    http_status_code = 400
    error_code = "CONSTITUTIONAL_VIOLATION_ERROR"


class ConstitutionalSelfCorrector(Protocol):
    """
    Protocol for constitutional self-correction integration.

    Implementations should apply constitutional AI principles
    to refine responses for compliance.
    """

    def correct(self, response: str, violations: list[str], context: JSONDict | None = None) -> str:
        """
        Apply constitutional correction to a response.

        Args:
            response: The response to correct
            violations: List of constitutional violations detected
            context: Optional context for correction

        Returns:
            Corrected response text
        """
        ...

    async def correct_async(
        self, response: str, violations: list[str], context: JSONDict | None = None
    ) -> str:
        """Async version of correct."""
        ...


class LLMRefiner(Protocol):
    """
    Protocol for LLM-based response refinement.

    Implementations should use an LLM to improve response quality
    based on assessment feedback.
    """

    def refine(
        self, response: str, assessment: QualityAssessment, context: JSONDict | None = None
    ) -> str:
        """
        Refine a response based on quality assessment.

        Args:
            response: The response to refine
            assessment: Quality assessment with improvement suggestions
            context: Optional context for refinement

        Returns:
            Refined response text
        """
        ...

    async def refine_async(
        self, response: str, assessment: QualityAssessment, context: JSONDict | None = None
    ) -> str:
        """Async version of refine."""
        ...


@dataclass
class RefinementConfig:
    """Configuration for response refinement."""

    max_iterations: int = 3
    improvement_threshold: float = 0.01
    stop_on_pass: bool = True
    require_constitutional: bool = True
    timeout_per_iteration_ms: float = 5000.0
    enable_logging: bool = True


class DefaultLLMRefiner:
    """
    Default LLM refiner implementation.

    This is a placeholder that applies basic text improvements.
    Production usage should provide a proper LLM-based implementation.
    """

    def refine(
        self, response: str, assessment: QualityAssessment, context: JSONDict | None = None
    ) -> str:
        """Apply basic refinement based on suggestions."""
        refined = response

        # Apply basic improvements based on failing dimensions
        for dim in assessment.failing_dimensions:
            if dim.name == "coherence":
                # Add structure if lacking
                if not refined.endswith("."):
                    refined = refined.rstrip() + "."
                # Ensure proper capitalization
                sentences = refined.split(". ")
                refined = ". ".join(s.capitalize() for s in sentences if s)

            elif dim.name == "relevance" and context and "query" in context:
                # Prepend context acknowledgment
                query = context["query"]
                if not refined.lower().startswith(query.lower()[:20]):
                    refined = f"Regarding your query: {refined}"

            elif dim.name == "safety":
                # Basic harmful content removal
                harmful_words = ["hack", "steal", "kill"]
                for word in harmful_words:
                    refined = refined.replace(word, "[redacted]")

        return refined

    async def refine_async(
        self, response: str, assessment: QualityAssessment, context: JSONDict | None = None
    ) -> str:
        """Async version uses sync implementation."""
        return self.refine(response, assessment, context)


class DefaultConstitutionalCorrector:
    """
    Default constitutional self-corrector implementation.

    This is a placeholder that applies basic constitutional corrections.
    Production usage should integrate with the full ConstitutionalSelfCorrector.
    """

    def correct(self, response: str, violations: list[str], context: JSONDict | None = None) -> str:
        """Apply basic constitutional corrections."""
        corrected = response

        for violation in violations:
            violation_lower = violation.lower()

            if "harmful" in violation_lower or "unsafe" in violation_lower:
                # Add safety disclaimer
                corrected = f"[Reviewed for safety] {corrected}"

            if "bias" in violation_lower:
                # Add neutrality note
                corrected = f"{corrected} (Note: This response aims to be balanced and fair.)"

            if "privacy" in violation_lower:
                # Redact potential PII patterns
                import re

                corrected = re.sub(r"\b\d{3}-\d{2}-\d{4}\b", "[SSN-REDACTED]", corrected)
                corrected = re.sub(r"\b[\w.-]+@[\w.-]+\.\w+\b", "[EMAIL-REDACTED]", corrected)

        return corrected

    async def correct_async(
        self, response: str, violations: list[str], context: JSONDict | None = None
    ) -> str:
        """Async version uses sync implementation."""
        return self.correct(response, violations, context)


class AdapterLLMRefiner(LLMRefiner):
    """
    LLM refiner that uses a BaseLLMAdapter for actual response improvement.
    """
    def __init__(self, adapter: BaseLLMAdapter):
        self.adapter = adapter

    def refine(
        self, response: str, assessment: QualityAssessment, context: JSONDict | None = None
    ) -> str:
        prompt = self._build_prompt(response, assessment, context)
        messages = [
            LLMMessage(role="system", content="You are a response quality improvement assistant. Refine the provided response based on the quality assessment and critique. Return ONLY the refined response text, without any additional commentary."),
            LLMMessage(role="user", content=prompt)
        ]
        try:
            result = self.adapter.complete(messages=messages, temperature=0.3)
            return result.content.strip()
        except Exception as e:
            logger.error(f"AdapterLLMRefiner failed: {e}")
            return response

    async def refine_async(
        self, response: str, assessment: QualityAssessment, context: JSONDict | None = None
    ) -> str:
        prompt = self._build_prompt(response, assessment, context)
        messages = [
            LLMMessage(role="system", content="You are a response quality improvement assistant. Refine the provided response based on the quality assessment and critique. Return ONLY the refined response text, without any additional commentary."),
            LLMMessage(role="user", content=prompt)
        ]
        try:
            result = await self.adapter.acomplete(messages=messages, temperature=0.3)
            return result.content.strip()
        except Exception as e:
            logger.error(f"AdapterLLMRefiner async failed: {e}")
            return response

    def _build_prompt(self, response: str, assessment: QualityAssessment, context: JSONDict | None) -> str:
        critiques = []
        for dim in assessment.failing_dimensions:
            if dim.critique:
                critiques.append(f"- {dim.name}: {dim.critique}")
            else:
                critiques.append(f"- {dim.name}: Score {dim.score:.2f} is below threshold {dim.threshold:.2f}")

        prompt = f"Original Response:\n{response}\n\nThe response failed the following quality dimensions:\n"
        prompt += "\n".join(critiques)

        if assessment.refinement_suggestions:
            prompt += "\n\nSuggestions for improvement:\n"
            for sug in assessment.refinement_suggestions:
                prompt += f"- {sug}\n"

        if context:
            prompt += f"\n\nContext:\n{context}\n"

        prompt += "\nPlease provide a refined version of the response that addresses these issues. Keep the core meaning intact while improving the quality."
        return prompt


class AdapterConstitutionalCorrector(ConstitutionalSelfCorrector):
    """
    Constitutional corrector that uses a BaseLLMAdapter for actual response improvement.
    """
    def __init__(self, adapter: BaseLLMAdapter):
        self.adapter = adapter

    def correct(self, response: str, violations: list[str], context: JSONDict | None = None) -> str:
        prompt = self._build_prompt(response, violations, context)
        messages = [
            LLMMessage(role="system", content="You are a constitutional compliance assistant. Correct the provided response to address the listed constitutional violations. Ensure the core meaning is preserved but non-compliant parts are rewritten or removed. Return ONLY the corrected response text, without any additional commentary."),
            LLMMessage(role="user", content=prompt)
        ]
        try:
            result = self.adapter.complete(messages=messages, temperature=0.2)
            return result.content.strip()
        except Exception as e:
            logger.error(f"AdapterConstitutionalCorrector failed: {e}")
            return response

    async def correct_async(
        self, response: str, violations: list[str], context: JSONDict | None = None
    ) -> str:
        prompt = self._build_prompt(response, violations, context)
        messages = [
            LLMMessage(role="system", content="You are a constitutional compliance assistant. Correct the provided response to address the listed constitutional violations. Ensure the core meaning is preserved but non-compliant parts are rewritten or removed. Return ONLY the corrected response text, without any additional commentary."),
            LLMMessage(role="user", content=prompt)
        ]
        try:
            result = await self.adapter.acomplete(messages=messages, temperature=0.2)
            return result.content.strip()
        except Exception as e:
            logger.error(f"AdapterConstitutionalCorrector async failed: {e}")
            return response

    def _build_prompt(self, response: str, violations: list[str], context: JSONDict | None) -> str:
        prompt = f"Original Response:\n{response}\n\nConstitutional Violations:\n"
        for v in violations:
            prompt += f"- {v}\n"

        if context:
            prompt += f"\nContext:\n{context}\n"

        prompt += "\nPlease provide a corrected version of the response that resolves these violations."
        return prompt


class ResponseRefiner:
    """
    Iteratively refines responses to meet quality thresholds.

    This refiner works with a validator to assess response quality
    and applies refinements until the response passes all thresholds
    or the maximum iteration count is reached.

    Integration Points:
        - ConstitutionalSelfCorrector: For constitutional compliance
        - LLMRefiner: For quality improvement via LLM
        - ResponseQualityValidator: For quality assessment

    Attributes:
        max_iterations: Maximum refinement iterations (default: 3)
        config: Refinement configuration
        validator: Response quality validator
        llm_refiner: LLM-based refiner implementation
        constitutional_corrector: Constitutional compliance corrector

    Example:
        >>> refiner = ResponseRefiner()
        >>> result = refiner.refine("incomplete response", context={"query": "What is AI?"})
        >>> print(f"Final: {result.final_response}, Iterations: {result.total_iterations}")
    """

    def __init__(
        self,
        config: RefinementConfig | None = None,
        validator: ResponseQualityValidator | None = None,
        llm_refiner: LLMRefiner | None = None,
        constitutional_corrector: ConstitutionalSelfCorrector | None = None,
        max_iterations: int = 3,
    ):
        """
        Initialize the refiner.

        Args:
            config: Optional refinement configuration
            validator: Optional quality validator (created if not provided)
            llm_refiner: Optional LLM refiner (default used if not provided)
            constitutional_corrector: Optional constitutional corrector
            max_iterations: Maximum iterations (overrides config if provided)
        """
        self.config = config or RefinementConfig()

        # Override max_iterations from parameter if different from default
        if max_iterations != 3 or (config and config.max_iterations != max_iterations):
            self.config.max_iterations = max_iterations

        self.max_iterations = self.config.max_iterations

        self.validator = validator or ResponseQualityValidator()
        self.llm_refiner = llm_refiner or DefaultLLMRefiner()
        self.constitutional_corrector = constitutional_corrector or DefaultConstitutionalCorrector()

        self._refinement_count = 0
        self._total_iterations = 0
        self._created_at = datetime.now()

        logger.info(
            f"ResponseRefiner initialized: max_iterations={self.max_iterations}, "
            f"constitutional_hash={CONSTITUTIONAL_HASH[:8]}..."
        )

    @property
    def stats(self) -> JSONDict:
        """Get refiner statistics."""
        return {
            "refinement_count": self._refinement_count,
            "total_iterations": self._total_iterations,
            "avg_iterations_per_refinement": (
                self._total_iterations / self._refinement_count if self._refinement_count > 0 else 0
            ),
            "created_at": self._created_at.isoformat(),
            "max_iterations": self.max_iterations,
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }

    def refine(
        self,
        response: str,
        context: JSONDict | None = None,
        response_id: str | None = None,
    ) -> RefinementResult:
        """
        Refine a response iteratively to meet quality thresholds.

        Args:
            response: The response to refine
            context: Optional context for assessment and refinement
            response_id: Optional identifier for tracking

        Returns:
            RefinementResult with complete refinement history

        Raises:
            RefinementError: If refinement fails critically
        """
        start_time = time.time()
        self._refinement_count += 1

        # Initial assessment
        initial_assessment = self.validator.validate(response, context, response_id=response_id)

        # Check if already passes
        if self._should_stop(initial_assessment, None, 0):
            return RefinementResult(
                original_response=response,
                final_response=response,
                iterations=[],
                total_iterations=0,
                status=RefinementStatus.SKIPPED,
                initial_assessment=initial_assessment,
                final_assessment=initial_assessment,
                total_duration_ms=(time.time() - start_time) * 1000,
            )

        # Iterative refinement
        iterations: list[RefinementIteration] = []
        current_response = response
        current_assessment = initial_assessment

        for i in range(self.max_iterations):
            iteration_start = time.time()
            self._total_iterations += 1

            try:
                # Refine the response
                refined_response = self._apply_refinement(
                    current_response, current_assessment, context
                )

                # Assess the refined response
                refined_assessment = self.validator.validate(
                    refined_response, context, response_id=response_id
                )

                # Record iteration
                iteration = RefinementIteration(
                    iteration_number=i + 1,
                    original_response=current_response,
                    refined_response=refined_response,
                    before_assessment=current_assessment,
                    after_assessment=refined_assessment,
                    improvements=self._describe_improvements(
                        current_assessment, refined_assessment
                    ),
                    duration_ms=(time.time() - iteration_start) * 1000,
                )
                iterations.append(iteration)

                # Update for next iteration
                current_response = refined_response
                current_assessment = refined_assessment

                # Check if we should stop
                if self._should_stop(current_assessment, iterations[-1], i + 1):
                    break

            except REFINEMENT_ITERATION_ERRORS as e:
                logger.error(f"Refinement iteration {i + 1} failed: {e}")
                return RefinementResult(
                    original_response=response,
                    final_response=current_response,
                    iterations=iterations,
                    total_iterations=len(iterations),
                    status=RefinementStatus.FAILED,
                    initial_assessment=initial_assessment,
                    final_assessment=current_assessment,
                    total_duration_ms=(time.time() - start_time) * 1000,
                )

        # Determine final status
        if current_assessment.passes_threshold:
            status = RefinementStatus.COMPLETED
        else:
            status = RefinementStatus.COMPLETED  # Completed but may not pass

        return RefinementResult(
            original_response=response,
            final_response=current_response,
            iterations=iterations,
            total_iterations=len(iterations),
            status=status,
            initial_assessment=initial_assessment,
            final_assessment=current_assessment,
            total_duration_ms=(time.time() - start_time) * 1000,
        )

    async def refine_async(
        self,
        response: str,
        context: JSONDict | None = None,
        response_id: str | None = None,
    ) -> RefinementResult:
        """
        Async version of refine.

        Args:
            response: The response to refine
            context: Optional context
            response_id: Optional identifier

        Returns:
            RefinementResult
        """
        start_time = time.time()
        self._refinement_count += 1

        # Initial assessment
        initial_assessment = self.validator.validate(response, context, response_id=response_id)

        if self._should_stop(initial_assessment, None, 0):
            return RefinementResult(
                original_response=response,
                final_response=response,
                iterations=[],
                total_iterations=0,
                status=RefinementStatus.SKIPPED,
                initial_assessment=initial_assessment,
                final_assessment=initial_assessment,
                total_duration_ms=(time.time() - start_time) * 1000,
            )

        iterations: list[RefinementIteration] = []
        current_response = response
        current_assessment = initial_assessment

        for i in range(self.max_iterations):
            iteration_start = time.time()
            self._total_iterations += 1

            try:
                # Async refinement
                refined_response = await self._apply_refinement_async(
                    current_response, current_assessment, context
                )

                refined_assessment = self.validator.validate(
                    refined_response, context, response_id=response_id
                )

                iteration = RefinementIteration(
                    iteration_number=i + 1,
                    original_response=current_response,
                    refined_response=refined_response,
                    before_assessment=current_assessment,
                    after_assessment=refined_assessment,
                    improvements=self._describe_improvements(
                        current_assessment, refined_assessment
                    ),
                    duration_ms=(time.time() - iteration_start) * 1000,
                )
                iterations.append(iteration)

                current_response = refined_response
                current_assessment = refined_assessment

                if self._should_stop(current_assessment, iterations[-1], i + 1):
                    break

            except ASYNC_REFINEMENT_ITERATION_ERRORS as e:
                logger.error(f"Async refinement iteration {i + 1} failed: {e}")
                return RefinementResult(
                    original_response=response,
                    final_response=current_response,
                    iterations=iterations,
                    total_iterations=len(iterations),
                    status=RefinementStatus.FAILED,
                    initial_assessment=initial_assessment,
                    final_assessment=current_assessment,
                    total_duration_ms=(time.time() - start_time) * 1000,
                )

        status = RefinementStatus.COMPLETED

        return RefinementResult(
            original_response=response,
            final_response=current_response,
            iterations=iterations,
            total_iterations=len(iterations),
            status=status,
            initial_assessment=initial_assessment,
            final_assessment=current_assessment,
            total_duration_ms=(time.time() - start_time) * 1000,
        )

    def _apply_refinement(
        self, response: str, assessment: QualityAssessment, context: JSONDict | None = None
    ) -> str:
        """
        Apply refinement to a response.

        Args:
            response: The response to refine
            assessment: Current quality assessment
            context: Optional context

        Returns:
            Refined response
        """
        refined = response

        # Apply constitutional corrections if needed
        if not assessment.constitutional_compliance and self.config.require_constitutional:
            violations = [
                dim.critique or f"{dim.name} violation"
                for dim in assessment.failing_dimensions
                if dim.name == "constitutional_alignment"
            ]
            refined = self.constitutional_corrector.correct(refined, violations, context)

        # Apply LLM refinement
        refined = self.llm_refiner.refine(refined, assessment, context)

        return refined

    async def _apply_refinement_async(
        self, response: str, assessment: QualityAssessment, context: JSONDict | None = None
    ) -> str:
        """Async version of _apply_refinement."""
        refined = response

        if not assessment.constitutional_compliance and self.config.require_constitutional:
            violations = [
                dim.critique or f"{dim.name} violation"
                for dim in assessment.failing_dimensions
                if dim.name == "constitutional_alignment"
            ]
            refined = await self.constitutional_corrector.correct_async(
                refined, violations, context
            )

        refined = await self.llm_refiner.refine_async(refined, assessment, context)

        return refined

    def _should_stop(
        self,
        assessment: QualityAssessment,
        last_iteration: RefinementIteration | None,
        iteration_count: int,
    ) -> bool:
        """
        Determine if refinement should stop.

        Args:
            assessment: Current quality assessment
            last_iteration: Last refinement iteration (if any)
            iteration_count: Current iteration count

        Returns:
            True if refinement should stop
        """
        # Stop if passes all thresholds
        if self.config.stop_on_pass and assessment.passes_threshold:
            if assessment.constitutional_compliance or not self.config.require_constitutional:
                return True

        # Stop if no improvement
        if last_iteration:
            if last_iteration.improvement_delta < self.config.improvement_threshold:
                logger.debug(
                    f"Stopping: improvement {last_iteration.improvement_delta:.4f} "
                    f"< threshold {self.config.improvement_threshold}"
                )
                return True

        # Stop if max iterations reached
        return iteration_count >= self.max_iterations

    def _describe_improvements(
        self, before: QualityAssessment, after: QualityAssessment
    ) -> list[str]:
        """
        Describe improvements between two assessments.

        Args:
            before: Assessment before refinement
            after: Assessment after refinement

        Returns:
            List of improvement descriptions
        """
        improvements = []

        # Overall score improvement
        delta = after.overall_score - before.overall_score
        if delta > 0:
            improvements.append(f"Overall score improved by {delta:.3f}")

        # Per-dimension improvements
        before_dims = {d.name: d for d in before.dimensions}
        after_dims = {d.name: d for d in after.dimensions}

        for name, after_dim in after_dims.items():
            before_dim = before_dims.get(name)
            if before_dim:
                dim_delta = after_dim.score - before_dim.score
                if dim_delta > 0.05:  # Significant improvement
                    improvements.append(
                        f"{name}: improved from {before_dim.score:.2f} to {after_dim.score:.2f}"
                    )
                elif not before_dim.passes and after_dim.passes:
                    improvements.append(f"{name}: now passes threshold")

        # Constitutional compliance
        if not before.constitutional_compliance and after.constitutional_compliance:
            improvements.append("Constitutional compliance achieved")

        return improvements

    def refine_batch(
        self, responses: list[str], contexts: list[JSONDict | None] | None = None
    ) -> list[RefinementResult]:
        """
        Refine multiple responses.

        Args:
            responses: List of responses to refine
            contexts: Optional list of contexts

        Returns:
            List of RefinementResult objects
        """
        if contexts is None:
            contexts = [None] * len(responses)

        if len(responses) != len(contexts):
            raise ValueError("responses and contexts must have the same length")

        return [
            self.refine(response, context)
            for response, context in zip(responses, contexts, strict=False)
        ]

    async def refine_batch_async(
        self, responses: list[str], contexts: list[JSONDict | None] | None = None
    ) -> list[RefinementResult]:
        """
        Async version of refine_batch with concurrent processing.

        Args:
            responses: List of responses to refine
            contexts: Optional list of contexts

        Returns:
            List of RefinementResult objects
        """
        if contexts is None:
            contexts = [None] * len(responses)

        if len(responses) != len(contexts):
            raise ValueError("responses and contexts must have the same length")

        tasks = [
            self.refine_async(response, context)
            for response, context in zip(responses, contexts, strict=False)
        ]

        return await asyncio.gather(*tasks)

    def set_constitutional_corrector(self, corrector: ConstitutionalSelfCorrector) -> None:
        """
        Set a custom constitutional corrector.

        Args:
            corrector: Constitutional self-corrector implementation
        """
        self.constitutional_corrector = corrector
        logger.info("Updated constitutional corrector")

    def set_llm_refiner(self, refiner: LLMRefiner) -> None:
        """
        Set a custom LLM refiner.

        Args:
            refiner: LLM refiner implementation
        """
        self.llm_refiner = refiner
        logger.info("Updated LLM refiner")


def create_refiner(
    max_iterations: int = 3,
    validator: ResponseQualityValidator | None = None,
    constitutional_corrector: ConstitutionalSelfCorrector | None = None,
) -> ResponseRefiner:
    """
    Factory function to create a configured refiner.

    Args:
        max_iterations: Maximum refinement iterations
        validator: Optional quality validator
        constitutional_corrector: Optional constitutional corrector

    Returns:
        Configured ResponseRefiner
    """
    config = RefinementConfig(max_iterations=max_iterations)

    return ResponseRefiner(
        config=config,
        validator=validator,
        constitutional_corrector=constitutional_corrector,
        max_iterations=max_iterations,
    )


__all__ = [
    "CONSTITUTIONAL_HASH",
    "ConstitutionalSelfCorrector",
    "ConstitutionalViolationError",
    "DefaultConstitutionalCorrector",
    "DefaultLLMRefiner",
    "AdapterLLMRefiner",
    "AdapterConstitutionalCorrector",
    "LLMRefiner",
    "RefinementConfig",
    "RefinementError",
    "ResponseRefiner",
    "create_refiner",
]
