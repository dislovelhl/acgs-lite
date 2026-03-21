"""
ACGS-2 Enhanced Agent Bus - LLM Provider Capability Matrix
Constitutional Hash: cdd01ef066bc6cf2

Defines capability dimensions for LLM providers and implements capability-based
routing for multi-provider antifragility. Supports dynamic capability discovery,
fallback planning, and cost-aware selection.

Features:
- Comprehensive capability dimensions (context, function calling, vision, etc.)
- Provider capability registry with versioning
- Capability-based routing engine
- Dynamic capability discovery at startup
- Fallback chain generation based on capabilities
- Constitutional validation throughout
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum

from pydantic import BaseModel, Field

# Import centralized constitutional hash from shared module
try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH  # noqa: E402
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from src.core.shared.types import JSONDict  # noqa: E402
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)
DISCOVERY_HOOK_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
)


# =============================================================================
# Capability Dimensions
# =============================================================================


class CapabilityDimension(str, Enum):  # noqa: UP042
    """
    Capability dimensions for LLM providers.

    Constitutional Hash: cdd01ef066bc6cf2

    Each dimension represents a specific capability that may vary across providers.
    """

    # Core capabilities
    CONTEXT_LENGTH = "context_length"
    MAX_OUTPUT_TOKENS = "max_output_tokens"
    STREAMING = "streaming"
    BATCHING = "batching"

    # Function/Tool capabilities
    FUNCTION_CALLING = "function_calling"
    PARALLEL_FUNCTION_CALLS = "parallel_function_calls"
    STRUCTURED_OUTPUT = "structured_output"

    # Multimodal capabilities
    VISION = "vision"
    AUDIO_INPUT = "audio_input"
    AUDIO_OUTPUT = "audio_output"
    VIDEO = "video"
    FILE_UPLOAD = "file_upload"

    # Advanced capabilities
    JSON_MODE = "json_mode"
    CODE_INTERPRETER = "code_interpreter"
    WEB_SEARCH = "web_search"
    RETRIEVAL = "retrieval"

    # Constitutional AI capabilities
    CONSTITUTIONAL_VALIDATION = "constitutional_validation"
    POLICY_ADHERENCE = "policy_adherence"
    SAFETY_FILTERING = "safety_filtering"

    # Performance characteristics
    LATENCY_CLASS = "latency_class"
    RATE_LIMIT_RPM = "rate_limit_rpm"
    RATE_LIMIT_TPM = "rate_limit_tpm"

    # Pricing
    INPUT_COST_PER_1K = "input_cost_per_1k"
    OUTPUT_COST_PER_1K = "output_cost_per_1k"
    CACHED_INPUT_COST_PER_1K = "cached_input_cost_per_1k"


class LatencyClass(str, Enum):  # noqa: UP042
    """Latency classification for providers."""

    ULTRA_LOW = "ultra_low"  # <100ms
    LOW = "low"  # 100-500ms
    MEDIUM = "medium"  # 500ms-2s
    HIGH = "high"  # 2-10s
    VARIABLE = "variable"  # Depends on load


class CapabilityLevel(str, Enum):  # noqa: UP042
    """Level of support for a capability."""

    NONE = "none"
    BASIC = "basic"
    STANDARD = "standard"
    ADVANCED = "advanced"
    FULL = "full"


# =============================================================================
# Capability Value Types
# =============================================================================


@dataclass
class CapabilityValue:
    """
    Value for a specific capability.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    dimension: CapabilityDimension
    value: bool | int | float | str | CapabilityLevel | None
    metadata: dict[str, str | int | float | bool] = field(default_factory=dict)
    last_verified: datetime = field(default_factory=lambda: datetime.now(UTC))
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        value_repr = self.value
        if isinstance(self.value, Enum):
            value_repr = self.value.value
        return {
            "dimension": self.dimension.value,
            "value": value_repr,
            "metadata": self.metadata,
            "last_verified": self.last_verified.isoformat(),
            "constitutional_hash": self.constitutional_hash,
        }

    def is_satisfied_by(self, required: CapabilityRequirement) -> bool:
        """Check if this capability satisfies a requirement."""
        if required.dimension != self.dimension:
            return False

        # Boolean capabilities
        if isinstance(self.value, bool):
            if required.min_value is True:
                return self.value is True
            return True

        # Numeric capabilities
        if isinstance(self.value, (int, float)):
            if required.min_value is not None and self.value < required.min_value:
                return False
            return not (required.max_value is not None and self.value > required.max_value)

        # Level capabilities
        if isinstance(self.value, CapabilityLevel):
            level_order = [
                CapabilityLevel.NONE,
                CapabilityLevel.BASIC,
                CapabilityLevel.STANDARD,
                CapabilityLevel.ADVANCED,
                CapabilityLevel.FULL,
            ]
            current_idx = level_order.index(self.value)
            required_idx = level_order.index(required.min_value)
            return current_idx >= required_idx

        # String equality
        if isinstance(self.value, str):
            if required.exact_value is not None:
                return self.value == required.exact_value
            return True

        return True


@dataclass
class CapabilityRequirement:
    """
    Requirement specification for a capability.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    dimension: CapabilityDimension
    min_value: bool | int | float | str | CapabilityLevel | None = None
    max_value: bool | int | float | str | CapabilityLevel | None = None
    exact_value: bool | int | float | str | CapabilityLevel | None = None
    priority: int = 1  # 1=required, 2=preferred, 3=nice-to-have
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "dimension": self.dimension.value,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "exact_value": self.exact_value,
            "priority": self.priority,
            "constitutional_hash": self.constitutional_hash,
        }


# =============================================================================
# Provider Capability Profile
# =============================================================================


class ProviderCapabilityProfile(BaseModel):
    """
    Complete capability profile for an LLM provider/model.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    provider_id: str = Field(..., description="Unique provider identifier")
    model_id: str = Field(..., description="Specific model identifier")
    display_name: str = Field(..., description="Human-readable name")
    provider_type: str = Field(..., description="Provider type (openai, anthropic, etc.)")

    # Core capabilities
    context_length: int = Field(default=4096, description="Maximum context length in tokens")
    max_output_tokens: int = Field(default=4096, description="Maximum output tokens")
    supports_streaming: bool = Field(default=True, description="Streaming support")
    supports_batching: bool = Field(default=False, description="Batch request support")

    # Function/Tool capabilities
    function_calling: CapabilityLevel = Field(
        default=CapabilityLevel.NONE, description="Function calling support level"
    )
    parallel_function_calls: bool = Field(
        default=False, description="Parallel function call support"
    )
    structured_output: CapabilityLevel = Field(
        default=CapabilityLevel.NONE, description="Structured output/JSON mode support"
    )

    # Multimodal capabilities
    vision: bool = Field(default=False, description="Image input support")
    audio_input: bool = Field(default=False, description="Audio input support")
    audio_output: bool = Field(default=False, description="Audio output support")
    video: bool = Field(default=False, description="Video input support")
    file_upload: bool = Field(default=False, description="File upload support")

    # Advanced capabilities
    json_mode: bool = Field(default=False, description="JSON mode support")
    code_interpreter: bool = Field(default=False, description="Code interpreter support")
    web_search: bool = Field(default=False, description="Web search support")
    retrieval: bool = Field(default=False, description="Retrieval/RAG support")

    # Constitutional AI capabilities
    constitutional_validation: bool = Field(
        default=True, description="Constitutional validation support"
    )
    policy_adherence: CapabilityLevel = Field(
        default=CapabilityLevel.STANDARD, description="Policy adherence level"
    )
    safety_filtering: CapabilityLevel = Field(
        default=CapabilityLevel.STANDARD, description="Safety filtering level"
    )

    # Performance
    latency_class: LatencyClass = Field(
        default=LatencyClass.MEDIUM, description="Expected latency class"
    )
    rate_limit_rpm: int = Field(default=60, description="Requests per minute limit")
    rate_limit_tpm: int = Field(default=100000, description="Tokens per minute limit")

    # Pricing (USD per 1000 tokens)
    input_cost_per_1k: float = Field(default=0.0, description="Input cost per 1K tokens")
    output_cost_per_1k: float = Field(default=0.0, description="Output cost per 1K tokens")
    cached_input_cost_per_1k: float = Field(
        default=0.0, description="Cached input cost per 1K tokens"
    )

    # Metadata
    version: str = Field(default="1.0", description="Profile version")
    last_updated: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Last update time"
    )
    is_active: bool = Field(default=True, description="Whether provider is active")
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH, description="Constitutional hash")

    model_config = {"from_attributes": True}

    def get_capability(self, dimension: CapabilityDimension) -> CapabilityValue:
        """Get capability value for a dimension."""
        value_map = {
            CapabilityDimension.CONTEXT_LENGTH: self.context_length,
            CapabilityDimension.MAX_OUTPUT_TOKENS: self.max_output_tokens,
            CapabilityDimension.STREAMING: self.supports_streaming,
            CapabilityDimension.BATCHING: self.supports_batching,
            CapabilityDimension.FUNCTION_CALLING: self.function_calling,
            CapabilityDimension.PARALLEL_FUNCTION_CALLS: self.parallel_function_calls,
            CapabilityDimension.STRUCTURED_OUTPUT: self.structured_output,
            CapabilityDimension.VISION: self.vision,
            CapabilityDimension.AUDIO_INPUT: self.audio_input,
            CapabilityDimension.AUDIO_OUTPUT: self.audio_output,
            CapabilityDimension.VIDEO: self.video,
            CapabilityDimension.FILE_UPLOAD: self.file_upload,
            CapabilityDimension.JSON_MODE: self.json_mode,
            CapabilityDimension.CODE_INTERPRETER: self.code_interpreter,
            CapabilityDimension.WEB_SEARCH: self.web_search,
            CapabilityDimension.RETRIEVAL: self.retrieval,
            CapabilityDimension.CONSTITUTIONAL_VALIDATION: self.constitutional_validation,
            CapabilityDimension.POLICY_ADHERENCE: self.policy_adherence,
            CapabilityDimension.SAFETY_FILTERING: self.safety_filtering,
            CapabilityDimension.LATENCY_CLASS: self.latency_class,
            CapabilityDimension.RATE_LIMIT_RPM: self.rate_limit_rpm,
            CapabilityDimension.RATE_LIMIT_TPM: self.rate_limit_tpm,
            CapabilityDimension.INPUT_COST_PER_1K: self.input_cost_per_1k,
            CapabilityDimension.OUTPUT_COST_PER_1K: self.output_cost_per_1k,
            CapabilityDimension.CACHED_INPUT_COST_PER_1K: self.cached_input_cost_per_1k,
        }
        return CapabilityValue(
            dimension=dimension,
            value=value_map.get(dimension),
            last_verified=self.last_updated,
        )

    def satisfies_requirements(
        self, requirements: list[CapabilityRequirement]
    ) -> tuple[bool, list[str]]:
        """
        Check if this profile satisfies all requirements.

        Returns:
            Tuple of (all_satisfied, list_of_unsatisfied_dimensions)
        """
        unsatisfied = []
        for req in requirements:
            if req.priority == 1:  # Required
                capability = self.get_capability(req.dimension)
                if not capability.is_satisfied_by(req):
                    unsatisfied.append(req.dimension.value)

        return len(unsatisfied) == 0, unsatisfied

    def calculate_score(
        self, requirements: list[CapabilityRequirement], weights: dict[str, float] | None = None
    ) -> float:
        """
        Calculate a score for this profile based on requirements.

        Higher score = better match for requirements.
        """
        if weights is None:
            weights = {}

        score = 0.0
        max_score = 0.0

        for req in requirements:
            weight = weights.get(req.dimension.value, 1.0) / req.priority
            max_score += weight

            capability = self.get_capability(req.dimension)
            if capability.is_satisfied_by(req):
                score += weight
                # Bonus for exceeding requirements
                if isinstance(capability.value, (int, float)) and req.min_value is not None:
                    excess_ratio = capability.value / req.min_value
                    if excess_ratio > 1:
                        score += weight * min(0.2, (excess_ratio - 1) * 0.1)

        return score / max_score if max_score > 0 else 0.0


# =============================================================================
# Capability Registry
# =============================================================================


class CapabilityRegistry:
    """
    Registry for managing provider capability profiles.

    Constitutional Hash: cdd01ef066bc6cf2

    Provides:
    - Provider registration and discovery
    - Capability-based querying
    - Dynamic capability updates
    - Fallback chain generation
    """

    def __init__(self) -> None:
        """Initialize the capability registry."""
        self._profiles: dict[str, ProviderCapabilityProfile] = {}
        self._provider_groups: dict[str, set[str]] = {}
        self._discovery_hooks: list[Callable[[], list[ProviderCapabilityProfile]]] = []
        self._last_discovery: datetime | None = None
        self._discovery_interval = timedelta(hours=1)
        self._lock = asyncio.Lock()
        self._initialized = False

        # Register default profiles
        self._register_default_profiles()

    def _register_default_profiles(self) -> None:
        """Register default provider profiles."""
        defaults = [
            # OpenAI models
            ProviderCapabilityProfile(
                provider_id="openai-gpt4o",
                model_id="gpt-4o",
                display_name="GPT-4o",
                provider_type="openai",
                context_length=128000,
                max_output_tokens=16384,
                supports_streaming=True,
                function_calling=CapabilityLevel.FULL,
                parallel_function_calls=True,
                structured_output=CapabilityLevel.FULL,
                vision=True,
                json_mode=True,
                latency_class=LatencyClass.LOW,
                rate_limit_rpm=500,
                rate_limit_tpm=800000,
                input_cost_per_1k=0.0025,
                output_cost_per_1k=0.01,
                cached_input_cost_per_1k=0.00125,
            ),
            ProviderCapabilityProfile(
                provider_id="openai-gpt4o-mini",
                model_id="gpt-4o-mini",
                display_name="GPT-4o Mini",
                provider_type="openai",
                context_length=128000,
                max_output_tokens=16384,
                supports_streaming=True,
                function_calling=CapabilityLevel.FULL,
                parallel_function_calls=True,
                structured_output=CapabilityLevel.FULL,
                vision=True,
                json_mode=True,
                latency_class=LatencyClass.ULTRA_LOW,
                rate_limit_rpm=500,
                rate_limit_tpm=2000000,
                input_cost_per_1k=0.00015,
                output_cost_per_1k=0.0006,
                cached_input_cost_per_1k=0.000075,
            ),
            ProviderCapabilityProfile(
                provider_id="openai-o1",
                model_id="o1",
                display_name="O1",
                provider_type="openai",
                context_length=200000,
                max_output_tokens=100000,
                supports_streaming=True,
                function_calling=CapabilityLevel.FULL,
                parallel_function_calls=True,
                structured_output=CapabilityLevel.FULL,
                vision=True,
                json_mode=True,
                latency_class=LatencyClass.HIGH,
                rate_limit_rpm=500,
                rate_limit_tpm=2500000,
                input_cost_per_1k=0.015,
                output_cost_per_1k=0.06,
                cached_input_cost_per_1k=0.0075,
            ),
            # Anthropic models (current generation)
            ProviderCapabilityProfile(
                provider_id="anthropic-claude-opus-4-6",
                model_id="claude-opus-4-6",
                display_name="Claude Opus 4.6",
                provider_type="anthropic",
                context_length=200000,
                max_output_tokens=32000,
                supports_streaming=True,
                function_calling=CapabilityLevel.FULL,
                parallel_function_calls=True,
                structured_output=CapabilityLevel.FULL,
                vision=True,
                json_mode=True,
                latency_class=LatencyClass.MEDIUM,
                rate_limit_rpm=1000,
                rate_limit_tpm=400000,
                input_cost_per_1k=0.005,
                output_cost_per_1k=0.025,
                cached_input_cost_per_1k=0.0025,
            ),
            ProviderCapabilityProfile(
                provider_id="anthropic-claude-sonnet-4-6",
                model_id="claude-sonnet-4-6",
                display_name="Claude Sonnet 4.6",
                provider_type="anthropic",
                context_length=200000,
                max_output_tokens=16384,
                supports_streaming=True,
                function_calling=CapabilityLevel.FULL,
                parallel_function_calls=True,
                structured_output=CapabilityLevel.FULL,
                vision=True,
                json_mode=True,
                latency_class=LatencyClass.LOW,
                rate_limit_rpm=1000,
                rate_limit_tpm=400000,
                input_cost_per_1k=0.003,
                output_cost_per_1k=0.015,
                cached_input_cost_per_1k=0.00375,
            ),
            ProviderCapabilityProfile(
                provider_id="anthropic-claude-haiku-4-5",
                model_id="claude-haiku-4-5-20251001",
                display_name="Claude Haiku 4.5",
                provider_type="anthropic",
                context_length=200000,
                max_output_tokens=16384,
                supports_streaming=True,
                function_calling=CapabilityLevel.FULL,
                parallel_function_calls=True,
                structured_output=CapabilityLevel.FULL,
                vision=True,
                json_mode=True,
                latency_class=LatencyClass.ULTRA_LOW,
                rate_limit_rpm=1000,
                rate_limit_tpm=400000,
                input_cost_per_1k=0.001,
                output_cost_per_1k=0.005,
                cached_input_cost_per_1k=0.0001,
            ),
            # Google models
            ProviderCapabilityProfile(
                provider_id="google-gemini-2.0-flash",
                model_id="gemini-2.0-flash",
                display_name="Gemini 2.0 Flash",
                provider_type="google",
                context_length=1000000,
                max_output_tokens=8192,
                supports_streaming=True,
                function_calling=CapabilityLevel.FULL,
                parallel_function_calls=True,
                structured_output=CapabilityLevel.FULL,
                vision=True,
                audio_input=True,
                video=True,
                json_mode=True,
                latency_class=LatencyClass.ULTRA_LOW,
                rate_limit_rpm=1500,
                rate_limit_tpm=4000000,
                input_cost_per_1k=0.0,  # Free tier
                output_cost_per_1k=0.0,
            ),
            # AWS Bedrock
            ProviderCapabilityProfile(
                provider_id="bedrock-claude-sonnet-4-6",
                model_id="anthropic.claude-sonnet-4-6-v1:0",
                display_name="Claude Sonnet 4.6 (Bedrock)",
                provider_type="bedrock",
                context_length=200000,
                max_output_tokens=16384,
                supports_streaming=True,
                function_calling=CapabilityLevel.FULL,
                parallel_function_calls=True,
                structured_output=CapabilityLevel.FULL,
                vision=True,
                json_mode=True,
                latency_class=LatencyClass.LOW,
                rate_limit_rpm=1000,
                rate_limit_tpm=1000000,
                input_cost_per_1k=0.003,
                output_cost_per_1k=0.015,
            ),
            # Azure OpenAI
            ProviderCapabilityProfile(
                provider_id="azure-gpt-5-4",
                model_id="gpt-5.4",
                display_name="GPT-5.4 (Azure)",
                provider_type="azure",
                context_length=400000,
                max_output_tokens=16384,
                supports_streaming=True,
                function_calling=CapabilityLevel.FULL,
                parallel_function_calls=True,
                structured_output=CapabilityLevel.FULL,
                vision=True,
                json_mode=True,
                latency_class=LatencyClass.LOW,
                rate_limit_rpm=1000,
                rate_limit_tpm=450000,
                input_cost_per_1k=0.002,
                output_cost_per_1k=0.016,
            ),
            # xAI (Grok)
            ProviderCapabilityProfile(
                provider_id="xai-grok-4-1-fast",
                model_id="grok-4-1-fast",
                display_name="Grok 4.1 Fast",
                provider_type="xai",
                context_length=2000000,
                max_output_tokens=32768,
                supports_streaming=True,
                function_calling=CapabilityLevel.FULL,
                parallel_function_calls=True,
                structured_output=CapabilityLevel.FULL,
                vision=True,
                json_mode=True,
                latency_class=LatencyClass.ULTRA_LOW,
                rate_limit_rpm=607,
                rate_limit_tpm=4000000,
                input_cost_per_1k=0.0002,
                output_cost_per_1k=0.0005,
                cached_input_cost_per_1k=0.00005,
            ),
            ProviderCapabilityProfile(
                provider_id="xai-grok-4-20",
                model_id="grok-4.20",
                display_name="Grok 4.20",
                provider_type="xai",
                context_length=2000000,
                max_output_tokens=32768,
                supports_streaming=True,
                function_calling=CapabilityLevel.FULL,
                parallel_function_calls=True,
                structured_output=CapabilityLevel.FULL,
                vision=True,
                json_mode=True,
                latency_class=LatencyClass.LOW,
                rate_limit_rpm=607,
                rate_limit_tpm=4000000,
                input_cost_per_1k=0.002,
                output_cost_per_1k=0.006,
                cached_input_cost_per_1k=0.0002,
            ),
            # Moonshot AI (Kimi)
            ProviderCapabilityProfile(
                provider_id="moonshot-kimi-k2-5-free",
                model_id="kimi-k2.5-free",
                display_name="Kimi K2.5 Free",
                provider_type="moonshot",
                context_length=256000,
                max_output_tokens=8192,
                supports_streaming=True,
                function_calling=CapabilityLevel.FULL,
                parallel_function_calls=True,
                structured_output=CapabilityLevel.FULL,
                vision=True,
                json_mode=True,
                latency_class=LatencyClass.LOW,
                rate_limit_rpm=300,
                rate_limit_tpm=2000000,
                input_cost_per_1k=0.0,  # Free tier
                output_cost_per_1k=0.0,
                cached_input_cost_per_1k=0.0,
            ),
            # OpenClaw Gateway (routes to underlying providers)
            ProviderCapabilityProfile(
                provider_id="openclaw-claude-opus-4-6",
                model_id="anthropic/claude-opus-4-6",
                display_name="Claude Opus 4.6 (OpenClaw)",
                provider_type="openclaw",
                context_length=200000,
                max_output_tokens=32000,
                supports_streaming=True,
                function_calling=CapabilityLevel.FULL,
                parallel_function_calls=True,
                structured_output=CapabilityLevel.FULL,
                vision=True,
                json_mode=True,
                latency_class=LatencyClass.MEDIUM,
                rate_limit_rpm=100,
                rate_limit_tpm=200000,
                input_cost_per_1k=0.005,
                output_cost_per_1k=0.025,
                cached_input_cost_per_1k=0.0025,
            ),
        ]

        for profile in defaults:
            self._profiles[profile.provider_id] = profile
            self._add_to_groups(profile)

    def _add_to_groups(self, profile: ProviderCapabilityProfile) -> None:
        """Add profile to provider groups for quick lookup."""
        # Group by provider type
        if profile.provider_type not in self._provider_groups:
            self._provider_groups[profile.provider_type] = set()
        self._provider_groups[profile.provider_type].add(profile.provider_id)

    def register_profile(self, profile: ProviderCapabilityProfile) -> None:
        """Register a new provider capability profile."""
        self._profiles[profile.provider_id] = profile
        self._add_to_groups(profile)
        logger.info(f"Registered capability profile: {profile.provider_id}")

    def get_profile(self, provider_id: str) -> ProviderCapabilityProfile | None:
        """Get a provider's capability profile."""
        return self._profiles.get(provider_id)

    def get_all_profiles(self, active_only: bool = True) -> list[ProviderCapabilityProfile]:
        """Get all registered profiles."""
        profiles = list(self._profiles.values())
        if active_only:
            profiles = [p for p in profiles if p.is_active]
        return profiles

    def get_by_provider_type(self, provider_type: str) -> list[ProviderCapabilityProfile]:
        """Get all profiles for a provider type."""
        provider_ids = self._provider_groups.get(provider_type, set())
        return [self._profiles[pid] for pid in provider_ids if pid in self._profiles]

    def find_capable_providers(
        self, requirements: list[CapabilityRequirement]
    ) -> list[tuple[ProviderCapabilityProfile, float]]:
        """
        Find providers that satisfy requirements, sorted by score.

        Returns:
            List of (profile, score) tuples, sorted by score descending
        """
        results = []
        for profile in self._profiles.values():
            if not profile.is_active:
                continue

            satisfied, _ = profile.satisfies_requirements(requirements)
            if satisfied:
                score = profile.calculate_score(requirements)
                results.append((profile, score))

        # Sort by score descending
        results.sort(key=lambda x: x[1], reverse=True)
        return results

    def generate_fallback_chain(
        self,
        primary_provider_id: str,
        requirements: list[CapabilityRequirement],
        max_fallbacks: int = 3,
    ) -> list[str]:
        """
        Generate a fallback chain for a primary provider.

        The chain includes alternative providers that satisfy requirements,
        prioritizing different provider types for true redundancy.
        """
        primary = self._profiles.get(primary_provider_id)
        if not primary:
            return []

        # Find capable providers excluding primary
        capable = self.find_capable_providers(requirements)
        capable = [(p, s) for p, s in capable if p.provider_id != primary_provider_id]

        # Prioritize different provider types
        fallbacks: list[str] = []
        used_types = {primary.provider_type}

        # First pass: different provider types
        for profile, _ in capable:
            if len(fallbacks) >= max_fallbacks:
                break
            if profile.provider_type not in used_types:
                fallbacks.append(profile.provider_id)
                used_types.add(profile.provider_type)

        # Second pass: fill remaining slots
        for profile, _ in capable:
            if len(fallbacks) >= max_fallbacks:
                break
            if profile.provider_id not in fallbacks:
                fallbacks.append(profile.provider_id)

        return fallbacks

    def register_discovery_hook(self, hook: Callable[[], list[ProviderCapabilityProfile]]) -> None:
        """Register a hook for dynamic capability discovery."""
        self._discovery_hooks.append(hook)

    async def discover_capabilities(self, force: bool = False) -> int:
        """
        Run capability discovery to update profiles.

        Returns:
            Number of profiles updated
        """
        async with self._lock:
            now = datetime.now(UTC)
            if (
                not force
                and self._last_discovery
                and now - self._last_discovery < self._discovery_interval
            ):
                return 0

            updated = 0
            for hook in self._discovery_hooks:
                try:
                    profiles = hook()
                    for profile in profiles:
                        self.register_profile(profile)
                        updated += 1
                except DISCOVERY_HOOK_ERRORS as e:
                    logger.error(f"Discovery hook failed: {e}")

            self._last_discovery = now
            self._initialized = True
            logger.info(f"Capability discovery completed, {updated} profiles updated")
            return updated

    async def initialize(self) -> None:
        """Initialize the registry with capability discovery."""
        if not self._initialized:
            await self.discover_capabilities(force=True)


# =============================================================================
# Capability-Based Router
# =============================================================================


class CapabilityRouter:
    """
    Routes requests to providers based on capability requirements.

    Constitutional Hash: cdd01ef066bc6cf2

    Provides:
    - Capability-based provider selection
    - Cost-aware routing
    - Automatic fallback handling
    - Load balancing across capable providers
    """

    def __init__(self, registry: CapabilityRegistry | None = None) -> None:
        """Initialize the capability router."""
        self.registry = registry or CapabilityRegistry()
        self._routing_preferences: dict[str, bool] = {
            "prefer_low_cost": False,
            "prefer_low_latency": True,
            "load_balance": True,
            "provider_diversity": True,
        }
        self._usage_counts: dict[str, int] = {}

    def set_preferences(self, preferences: dict[str, bool]) -> None:
        """Set routing preferences."""
        self._routing_preferences.update(preferences)

    def select_provider(
        self,
        requirements: list[CapabilityRequirement],
        exclude_providers: list[str] | None = None,
    ) -> ProviderCapabilityProfile | None:
        """
        Select the best provider for given requirements.

        Args:
            requirements: Capability requirements
            exclude_providers: Provider IDs to exclude (e.g., for fallback)

        Returns:
            Best matching provider profile, or None
        """
        exclude = set(exclude_providers or [])
        capable = self.registry.find_capable_providers(requirements)
        capable = [(p, s) for p, s in capable if p.provider_id not in exclude]

        if not capable:
            return None

        # Apply preferences
        if self._routing_preferences.get("prefer_low_cost"):
            capable.sort(key=lambda x: x[0].input_cost_per_1k + x[0].output_cost_per_1k)
        elif self._routing_preferences.get("prefer_low_latency"):
            latency_order = {
                LatencyClass.ULTRA_LOW: 0,
                LatencyClass.LOW: 1,
                LatencyClass.MEDIUM: 2,
                LatencyClass.HIGH: 3,
                LatencyClass.VARIABLE: 4,
            }
            capable.sort(key=lambda x: latency_order.get(x[0].latency_class, 5))

        # Load balancing
        if self._routing_preferences.get("load_balance") and len(capable) > 1:
            # Weight by inverse usage count
            min_usage = min(self._usage_counts.get(p.provider_id, 0) for p, _ in capable)
            for profile, _ in capable:
                if self._usage_counts.get(profile.provider_id, 0) == min_usage:
                    self._usage_counts[profile.provider_id] = (
                        self._usage_counts.get(profile.provider_id, 0) + 1
                    )
                    return profile

        # Return best match
        if capable:
            selected = capable[0][0]
            self._usage_counts[selected.provider_id] = (
                self._usage_counts.get(selected.provider_id, 0) + 1
            )
            return selected

        return None

    def get_fallback_chain(
        self,
        primary: ProviderCapabilityProfile,
        requirements: list[CapabilityRequirement],
    ) -> list[ProviderCapabilityProfile]:
        """Get fallback providers for a primary provider."""
        fallback_ids = self.registry.generate_fallback_chain(primary.provider_id, requirements)
        return [
            self.registry.get_profile(pid) for pid in fallback_ids if self.registry.get_profile(pid)
        ]

    def estimate_cost(
        self,
        profile: ProviderCapabilityProfile,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        """Estimate cost for a request."""
        input_cost = (input_tokens / 1000) * profile.input_cost_per_1k
        output_cost = (output_tokens / 1000) * profile.output_cost_per_1k
        return input_cost + output_cost


# =============================================================================
# Global Instances
# =============================================================================

_capability_registry: CapabilityRegistry | None = None
_capability_router: CapabilityRouter | None = None


def get_capability_registry() -> CapabilityRegistry:
    """Get the global capability registry."""
    global _capability_registry
    if _capability_registry is None:
        _capability_registry = CapabilityRegistry()
    return _capability_registry


def get_capability_router() -> CapabilityRouter:
    """Get the global capability router."""
    global _capability_router
    if _capability_router is None:
        _capability_router = CapabilityRouter(get_capability_registry())
    return _capability_router


async def initialize_capability_matrix() -> None:
    """Initialize the capability matrix system."""
    registry = get_capability_registry()
    await registry.initialize()
    logger.info("Capability matrix initialized")


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Enums
    "CapabilityDimension",
    "CapabilityLevel",
    # Classes
    "CapabilityRegistry",
    "CapabilityRequirement",
    "CapabilityRouter",
    # Data classes
    "CapabilityValue",
    "LatencyClass",
    # Models
    "ProviderCapabilityProfile",
    # Global accessors
    "get_capability_registry",
    "get_capability_router",
    "initialize_capability_matrix",
]
