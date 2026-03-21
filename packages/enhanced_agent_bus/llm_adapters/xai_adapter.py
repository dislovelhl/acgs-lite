"""
ACGS-2 Enhanced Agent Bus - xAI (Grok) LLM Adapter
Constitutional Hash: cdd01ef066bc6cf2

xAI adapter supporting Grok 4.x models via OpenAI-compatible API.
Extends OpenAIAdapter with xAI-specific pricing, server-side tools
(web search, X search, code execution, Collections), and 2M context.
"""

from __future__ import annotations

import time
from typing import ClassVar, cast

from enhanced_agent_bus.observability.structured_logging import get_logger

from .base import (
    CONSTITUTIONAL_HASH,
    AdapterStatus,
    CostEstimate,
    HealthCheckResult,
    LLMMessage,
    LLMResponse,
    RetryConfig,
)
from .config import XAIAdapterConfig
from .models import MessageConverter, ResponseConverter
from .openai_adapter import OpenAIAdapter

logger = get_logger(__name__)

# Default xAI API base URL
XAI_API_BASE = "https://api.x.ai/v1"

_XAI_ADAPTER_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
)


class XAIAdapter(OpenAIAdapter):
    """xAI LLM adapter for Grok models.

    Constitutional Hash: cdd01ef066bc6cf2

    Extends OpenAIAdapter since xAI exposes an OpenAI-compatible API.
    Adds xAI-specific features:
    - Grok model pricing (4.1 Fast, 4, 4.20)
    - Server-side tools (web search, X search, code execution, Collections)
    - 2M token context window
    - Prompt caching (automatic)
    - Batch API support (50% off)
    """

    config: XAIAdapterConfig  # type: ignore[assignment]

    # Grok model pricing per 1M tokens (USD) — March 2026
    MODEL_PRICING: ClassVar[dict] = {
        # Grok 4.1 Fast (budget)
        "grok-4-1-fast-reasoning": {"prompt": 0.20, "completion": 0.50},
        "grok-4-1-fast-non-reasoning": {"prompt": 0.20, "completion": 0.50},
        "grok-4-1-fast": {"prompt": 0.20, "completion": 0.50},
        # Grok 4.20 (premium reasoning)
        "grok-4.20-0309-reasoning": {"prompt": 2.00, "completion": 6.00},
        "grok-4.20-0309-non-reasoning": {"prompt": 2.00, "completion": 6.00},
        "grok-4.20": {"prompt": 2.00, "completion": 6.00},
        # Grok 4 (standard)
        "grok-4": {"prompt": 3.00, "completion": 15.00},
        # Grok 4.20 Multi-Agent (beta)
        "grok-4.20-multi-agent-0309": {"prompt": 2.00, "completion": 6.00},
        "grok-4.20-multi-agent": {"prompt": 2.00, "completion": 6.00},
    }

    # Cached prompt pricing per 1M tokens (USD)
    CACHED_PRICING: ClassVar[dict] = {
        "grok-4-1-fast": 0.05,
        "grok-4-1-fast-reasoning": 0.05,
        "grok-4-1-fast-non-reasoning": 0.05,
        "grok-4.20": 0.20,
        "grok-4.20-0309-reasoning": 0.20,
        "grok-4.20-0309-non-reasoning": 0.20,
        "grok-4": 0.75,
        "grok-4.20-multi-agent-0309": 0.20,
        "grok-4.20-multi-agent": 0.20,
    }

    def __init__(
        self,
        config: XAIAdapterConfig | None = None,
        model: str | None = None,
        api_key: str | None = None,
        retry_config: RetryConfig | None = None,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
        **kwargs: object,
    ) -> None:
        """Initialize xAI adapter.

        Args:
            config: xAI adapter configuration
            model: Model identifier (if config not provided)
            api_key: API key (if config not provided)
            retry_config: Retry configuration
            constitutional_hash: Constitutional hash for compliance
            **kwargs: Additional configuration options
        """
        if config is None:
            if model is None:
                model = "grok-4-1-fast"
            config = XAIAdapterConfig.from_environment(model=model, **kwargs)

        # Ensure api_base points to xAI
        if config.api_base is None:
            config.api_base = XAI_API_BASE

        # Call grandparent init directly to avoid OpenAIAdapter's config creation
        from .base import BaseLLMAdapter

        BaseLLMAdapter.__init__(
            self,
            model=config.model,
            api_key=api_key or config.get_api_key("XAI_API_KEY"),
            retry_config=retry_config,
            constitutional_hash=constitutional_hash,
            **kwargs,
        )

        self.config = config
        self._client = None
        self._async_client = None
        self._tiktoken_encoder = None

    def _get_client(self):
        """Get or create synchronous OpenAI client pointed at xAI."""
        if self._client is None:
            try:
                import openai
            except ImportError:
                raise ImportError(
                    "openai package is required for xAI adapter. "
                    "Install with: pip install openai>=1.0.0"
                ) from None

            if not self.api_key:
                raise ValueError(
                    "xAI API key is required. Set XAI_API_KEY environment "
                    "variable or provide api_key parameter."
                )

            self._client = openai.OpenAI(
                api_key=self.api_key,
                base_url=self.config.api_base or XAI_API_BASE,
                timeout=self.config.timeout_seconds,
            )

        return self._client

    def _get_async_client(self):
        """Get or create asynchronous OpenAI client pointed at xAI."""
        if self._async_client is None:
            try:
                import openai
            except ImportError:
                raise ImportError(
                    "openai package is required for xAI adapter. "
                    "Install with: pip install openai>=1.0.0"
                ) from None

            if not self.api_key:
                raise ValueError(
                    "xAI API key is required. Set XAI_API_KEY environment "
                    "variable or provide api_key parameter."
                )

            self._async_client = openai.AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.config.api_base or XAI_API_BASE,
                timeout=self.config.timeout_seconds,
            )

        return self._async_client

    def complete(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        top_p: float = 1.0,
        stop: list[str] | None = None,
        **kwargs: object,
    ) -> LLMResponse:
        """Generate a completion via xAI API.

        Supports xAI server-side tools via kwargs:
        - xai_tools: list of server-side tool configs (web_search, x_search, etc.)

        Args:
            messages: List of conversation messages
            temperature: Sampling temperature (0.0 to 2.0)
            max_tokens: Maximum tokens to generate
            top_p: Nucleus sampling parameter
            stop: Stop sequences
            **kwargs: Additional xAI-specific parameters

        Returns:
            LLMResponse with generated content and metadata
        """
        self.validate_messages(messages)
        self.validate_constitutional_compliance()

        openai_messages = MessageConverter.to_openai_format(messages)

        request_params: dict[str, object] = {
            "model": self.model,
            "messages": openai_messages,
            "temperature": temperature,
            "top_p": top_p,
        }

        if max_tokens:
            request_params["max_tokens"] = max_tokens
        if stop:
            request_params["stop"] = stop

        # Standard OpenAI-compatible params
        self._add_optional_params(request_params, **kwargs)

        # xAI server-side tools (web_search, x_search, code_execution, etc.)
        xai_tools = kwargs.get("xai_tools")
        if xai_tools:
            request_params["tools"] = xai_tools

        start_time = time.time()
        client = self._get_client()

        try:
            response = client.chat.completions.create(**request_params)
            latency_ms = (time.time() - start_time) * 1000

            response_dict = response.model_dump()
            llm_response = ResponseConverter.from_openai_response(
                response_dict, provider="xai"
            )

            llm_response.metadata.latency_ms = latency_ms
            llm_response.cost = self._estimate_cost_from_usage(
                response_dict.get("usage", {})
            )

            return llm_response

        except _XAI_ADAPTER_OPERATION_ERRORS as e:
            logger.error(f"xAI completion error: {e}")
            raise

    async def acomplete(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        top_p: float = 1.0,
        stop: list[str] | None = None,
        **kwargs: object,
    ) -> LLMResponse:
        """Generate a completion via xAI API asynchronously.

        Args:
            messages: List of conversation messages
            temperature: Sampling temperature (0.0 to 2.0)
            max_tokens: Maximum tokens to generate
            top_p: Nucleus sampling parameter
            stop: Stop sequences
            **kwargs: Additional xAI-specific parameters

        Returns:
            LLMResponse with generated content and metadata
        """
        self.validate_messages(messages)
        self.validate_constitutional_compliance()

        openai_messages = MessageConverter.to_openai_format(messages)

        request_params: dict[str, object] = {
            "model": self.model,
            "messages": openai_messages,
            "temperature": temperature,
            "top_p": top_p,
        }

        if max_tokens:
            request_params["max_tokens"] = max_tokens
        if stop:
            request_params["stop"] = stop

        self._add_optional_params(request_params, **kwargs)

        xai_tools = kwargs.get("xai_tools")
        if xai_tools:
            request_params["tools"] = xai_tools

        start_time = time.time()
        client = self._get_async_client()

        try:
            response = await client.chat.completions.create(**request_params)
            latency_ms = (time.time() - start_time) * 1000

            response_dict = response.model_dump()
            llm_response = ResponseConverter.from_openai_response(
                response_dict, provider="xai"
            )

            llm_response.metadata.latency_ms = latency_ms
            llm_response.cost = self._estimate_cost_from_usage(
                response_dict.get("usage", {})
            )

            return llm_response

        except _XAI_ADAPTER_OPERATION_ERRORS as e:
            logger.error(f"xAI async completion error: {e}")
            raise

    def estimate_cost(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        *,
        cached_tokens: int = 0,
        reasoning_tokens: int = 0,
    ) -> CostEstimate:
        """Estimate cost for an xAI API call.

        Uses xAI Grok pricing. Reasoning tokens are billed at the
        completion rate. Cached prompt tokens use reduced pricing.
        Falls back to grok-4-1-fast pricing for unrecognized models.

        Args:
            prompt_tokens: Number of tokens in the prompt
            completion_tokens: Number of completion tokens
            cached_tokens: Number of cached prompt tokens (cheaper rate)
            reasoning_tokens: Number of reasoning tokens (completion rate)

        Returns:
            CostEstimate with pricing breakdown
        """
        pricing = None
        for model_key, model_pricing in self.MODEL_PRICING.items():
            if self.model == model_key or self.model.startswith(model_key):
                pricing = model_pricing
                break

        if pricing is None:
            logger.warning(
                f"Pricing not found for model {self.model}, "
                "using grok-4-1-fast pricing"
            )
            pricing = self.MODEL_PRICING["grok-4-1-fast"]

        # Cached tokens use reduced rate; uncached at full prompt rate
        cached_rate = self._get_cached_rate()
        uncached_prompt = max(0, prompt_tokens - cached_tokens)
        prompt_cost = (
            (uncached_prompt / 1_000_000.0) * pricing["prompt"]
            + (cached_tokens / 1_000_000.0) * cached_rate
        )

        # Completion + reasoning tokens both billed at completion rate
        total_completion = completion_tokens + reasoning_tokens
        completion_cost = (total_completion / 1_000_000.0) * pricing["completion"]

        return CostEstimate(
            prompt_cost_usd=prompt_cost,
            completion_cost_usd=completion_cost,
            total_cost_usd=prompt_cost + completion_cost,
            currency="USD",
            pricing_model=self.model,
            constitutional_hash=self.constitutional_hash,
        )

    def _estimate_cost_from_usage(self, usage: dict) -> CostEstimate:
        """Extract xAI-specific usage fields and compute cost.

        xAI responses include prompt_tokens_details.cached_tokens and
        completion_tokens_details.reasoning_tokens. When present, these
        are used for more accurate cost calculation.
        """
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)

        prompt_details = usage.get("prompt_tokens_details", {}) or {}
        completion_details = usage.get("completion_tokens_details", {}) or {}

        cached_tokens = prompt_details.get("cached_tokens", 0)
        reasoning_tokens = completion_details.get("reasoning_tokens", 0)

        return self.estimate_cost(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cached_tokens=cached_tokens,
            reasoning_tokens=reasoning_tokens,
        )

    def _get_cached_rate(self) -> float:
        """Get cached prompt token rate for the current model."""
        for model_key, rate in self.CACHED_PRICING.items():
            if self.model == model_key or self.model.startswith(model_key):
                return rate
        return 0.05  # Default to grok-4-1-fast cached rate

    async def health_check(self) -> HealthCheckResult:
        """Check xAI API health and connectivity.

        Returns:
            HealthCheckResult with status and diagnostics
        """
        start_time = time.time()

        try:
            client = self._get_async_client()
            await client.models.list()

            latency_ms = (time.time() - start_time) * 1000

            return HealthCheckResult(
                status=AdapterStatus.HEALTHY,
                latency_ms=latency_ms,
                message="xAI API is accessible",
                details={
                    "model": self.model,
                    "provider": "xai",
                    "api_base": self.config.api_base or XAI_API_BASE,
                },
                constitutional_hash=self.constitutional_hash,
            )

        except _XAI_ADAPTER_OPERATION_ERRORS as e:
            latency_ms = (time.time() - start_time) * 1000
            logger.error(f"xAI health check failed: {e}")

            return HealthCheckResult(
                status=AdapterStatus.UNHEALTHY,
                latency_ms=latency_ms,
                message=f"Health check failed: {e!s}",
                details={
                    "model": self.model,
                    "provider": "xai",
                    "error": str(e),
                },
                constitutional_hash=self.constitutional_hash,
            )

    def get_provider_name(self) -> str:
        """Get the provider name for this adapter."""
        return "xai"


__all__ = ["XAIAdapter"]
