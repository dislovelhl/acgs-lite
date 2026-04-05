"""
Tests for LLM Provider Capability Matrix.
Constitutional Hash: 608508a9bd224290
"""

from datetime import datetime, timedelta, timezone

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.llm_adapters.capability_matrix import (
    CapabilityDimension,
    CapabilityLevel,
    CapabilityRegistry,
    CapabilityRequirement,
    CapabilityRouter,
    CapabilityValue,
    LatencyClass,
    ProviderCapabilityProfile,
    get_capability_registry,
    get_capability_router,
    initialize_capability_matrix,
)


class TestCapabilityDimension:
    """Tests for CapabilityDimension enum."""

    def test_core_dimensions_defined(self):
        """Test core capability dimensions are defined."""
        assert CapabilityDimension.CONTEXT_LENGTH == "context_length"
        assert CapabilityDimension.MAX_OUTPUT_TOKENS == "max_output_tokens"
        assert CapabilityDimension.STREAMING == "streaming"
        assert CapabilityDimension.BATCHING == "batching"

    def test_function_dimensions_defined(self):
        """Test function/tool dimensions are defined."""
        assert CapabilityDimension.FUNCTION_CALLING == "function_calling"
        assert CapabilityDimension.PARALLEL_FUNCTION_CALLS == "parallel_function_calls"
        assert CapabilityDimension.STRUCTURED_OUTPUT == "structured_output"

    def test_multimodal_dimensions_defined(self):
        """Test multimodal dimensions are defined."""
        assert CapabilityDimension.VISION == "vision"
        assert CapabilityDimension.AUDIO_INPUT == "audio_input"
        assert CapabilityDimension.AUDIO_OUTPUT == "audio_output"
        assert CapabilityDimension.VIDEO == "video"

    def test_constitutional_dimensions_defined(self):
        """Test constitutional AI dimensions are defined."""
        assert CapabilityDimension.CONSTITUTIONAL_VALIDATION == "constitutional_validation"
        assert CapabilityDimension.POLICY_ADHERENCE == "policy_adherence"
        assert CapabilityDimension.SAFETY_FILTERING == "safety_filtering"


class TestCapabilityLevel:
    """Tests for CapabilityLevel enum."""

    def test_levels_defined(self):
        """Test capability levels are defined."""
        assert CapabilityLevel.NONE == "none"
        assert CapabilityLevel.BASIC == "basic"
        assert CapabilityLevel.STANDARD == "standard"
        assert CapabilityLevel.ADVANCED == "advanced"
        assert CapabilityLevel.FULL == "full"


class TestLatencyClass:
    """Tests for LatencyClass enum."""

    def test_latency_classes_defined(self):
        """Test latency classes are defined."""
        assert LatencyClass.ULTRA_LOW == "ultra_low"
        assert LatencyClass.LOW == "low"
        assert LatencyClass.MEDIUM == "medium"
        assert LatencyClass.HIGH == "high"
        assert LatencyClass.VARIABLE == "variable"


class TestCapabilityValue:
    """Tests for CapabilityValue dataclass."""

    def test_value_creation(self):
        """Test creating a capability value."""
        value = CapabilityValue(
            dimension=CapabilityDimension.CONTEXT_LENGTH,
            value=128000,
        )
        assert value.dimension == CapabilityDimension.CONTEXT_LENGTH
        assert value.value == 128000
        assert value.constitutional_hash == CONSTITUTIONAL_HASH

    def test_value_to_dict(self):
        """Test capability value serialization."""
        value = CapabilityValue(
            dimension=CapabilityDimension.VISION,
            value=True,
            metadata={"provider": "openai"},
        )
        d = value.to_dict()

        assert d["dimension"] == "vision"
        assert d["value"] is True
        assert d["metadata"]["provider"] == "openai"
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_boolean_satisfaction(self):
        """Test boolean capability satisfaction."""
        value = CapabilityValue(
            dimension=CapabilityDimension.VISION,
            value=True,
        )
        req_true = CapabilityRequirement(
            dimension=CapabilityDimension.VISION,
            min_value=True,
        )
        req_any = CapabilityRequirement(
            dimension=CapabilityDimension.VISION,
        )

        assert value.is_satisfied_by(req_true) is True
        assert value.is_satisfied_by(req_any) is True

    def test_boolean_unsatisfied(self):
        """Test boolean capability not satisfied."""
        value = CapabilityValue(
            dimension=CapabilityDimension.VISION,
            value=False,
        )
        req = CapabilityRequirement(
            dimension=CapabilityDimension.VISION,
            min_value=True,
        )

        assert value.is_satisfied_by(req) is False

    def test_numeric_satisfaction(self):
        """Test numeric capability satisfaction."""
        value = CapabilityValue(
            dimension=CapabilityDimension.CONTEXT_LENGTH,
            value=128000,
        )
        req = CapabilityRequirement(
            dimension=CapabilityDimension.CONTEXT_LENGTH,
            min_value=100000,
        )

        assert value.is_satisfied_by(req) is True

    def test_numeric_unsatisfied_min(self):
        """Test numeric capability not meeting minimum."""
        value = CapabilityValue(
            dimension=CapabilityDimension.CONTEXT_LENGTH,
            value=8000,
        )
        req = CapabilityRequirement(
            dimension=CapabilityDimension.CONTEXT_LENGTH,
            min_value=100000,
        )

        assert value.is_satisfied_by(req) is False

    def test_level_satisfaction(self):
        """Test level capability satisfaction."""
        value = CapabilityValue(
            dimension=CapabilityDimension.FUNCTION_CALLING,
            value=CapabilityLevel.FULL,
        )
        req = CapabilityRequirement(
            dimension=CapabilityDimension.FUNCTION_CALLING,
            min_value=CapabilityLevel.STANDARD,
        )

        assert value.is_satisfied_by(req) is True

    def test_level_unsatisfied(self):
        """Test level capability not satisfied."""
        value = CapabilityValue(
            dimension=CapabilityDimension.FUNCTION_CALLING,
            value=CapabilityLevel.BASIC,
        )
        req = CapabilityRequirement(
            dimension=CapabilityDimension.FUNCTION_CALLING,
            min_value=CapabilityLevel.ADVANCED,
        )

        assert value.is_satisfied_by(req) is False


class TestCapabilityRequirement:
    """Tests for CapabilityRequirement dataclass."""

    def test_requirement_creation(self):
        """Test creating a capability requirement."""
        req = CapabilityRequirement(
            dimension=CapabilityDimension.CONTEXT_LENGTH,
            min_value=100000,
            priority=1,
        )
        assert req.dimension == CapabilityDimension.CONTEXT_LENGTH
        assert req.min_value == 100000
        assert req.priority == 1
        assert req.constitutional_hash == CONSTITUTIONAL_HASH

    def test_requirement_to_dict(self):
        """Test requirement serialization."""
        req = CapabilityRequirement(
            dimension=CapabilityDimension.VISION,
            min_value=True,
            priority=2,
        )
        d = req.to_dict()

        assert d["dimension"] == "vision"
        assert d["min_value"] is True
        assert d["priority"] == 2


class TestProviderCapabilityProfile:
    """Tests for ProviderCapabilityProfile model."""

    @pytest.fixture
    def sample_profile(self):
        """Create a sample profile for testing."""
        return ProviderCapabilityProfile(
            provider_id="test-provider",
            model_id="test-model",
            display_name="Test Model",
            provider_type="test",
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
            input_cost_per_1k=0.01,
            output_cost_per_1k=0.03,
        )

    def test_profile_creation(self, sample_profile):
        """Test creating a provider profile."""
        assert sample_profile.provider_id == "test-provider"
        assert sample_profile.model_id == "test-model"
        assert sample_profile.context_length == 128000
        assert sample_profile.constitutional_hash == CONSTITUTIONAL_HASH

    def test_get_capability(self, sample_profile):
        """Test getting capability value from profile."""
        cap = sample_profile.get_capability(CapabilityDimension.CONTEXT_LENGTH)
        assert cap.value == 128000
        assert cap.dimension == CapabilityDimension.CONTEXT_LENGTH

    def test_get_boolean_capability(self, sample_profile):
        """Test getting boolean capability value."""
        cap = sample_profile.get_capability(CapabilityDimension.VISION)
        assert cap.value is True

    def test_get_level_capability(self, sample_profile):
        """Test getting level capability value."""
        cap = sample_profile.get_capability(CapabilityDimension.FUNCTION_CALLING)
        assert cap.value == CapabilityLevel.FULL

    def test_satisfies_requirements_all_met(self, sample_profile):
        """Test profile satisfies all requirements."""
        requirements = [
            CapabilityRequirement(
                dimension=CapabilityDimension.CONTEXT_LENGTH,
                min_value=100000,
                priority=1,
            ),
            CapabilityRequirement(
                dimension=CapabilityDimension.VISION,
                min_value=True,
                priority=1,
            ),
        ]

        satisfied, unsatisfied = sample_profile.satisfies_requirements(requirements)
        assert satisfied is True
        assert len(unsatisfied) == 0

    def test_satisfies_requirements_not_met(self, sample_profile):
        """Test profile doesn't satisfy requirements."""
        requirements = [
            CapabilityRequirement(
                dimension=CapabilityDimension.CONTEXT_LENGTH,
                min_value=500000,  # Higher than profile
                priority=1,
            ),
        ]

        satisfied, unsatisfied = sample_profile.satisfies_requirements(requirements)
        assert satisfied is False
        assert "context_length" in unsatisfied

    def test_calculate_score(self, sample_profile):
        """Test profile score calculation."""
        requirements = [
            CapabilityRequirement(
                dimension=CapabilityDimension.CONTEXT_LENGTH,
                min_value=100000,
                priority=1,
            ),
            CapabilityRequirement(
                dimension=CapabilityDimension.VISION,
                min_value=True,
                priority=1,
            ),
        ]

        score = sample_profile.calculate_score(requirements)
        assert 0.0 <= score <= 1.5  # Can exceed 1.0 with bonus


class TestCapabilityRegistry:
    """Tests for CapabilityRegistry class."""

    @pytest.fixture
    def registry(self):
        """Create a fresh registry for each test."""
        return CapabilityRegistry()

    def test_default_profiles_registered(self, registry):
        """Test default profiles are registered."""
        profiles = registry.get_all_profiles()
        assert len(profiles) > 0

        # Check OpenAI profile exists
        openai_profiles = registry.get_by_provider_type("openai")
        assert len(openai_profiles) > 0

    def test_register_profile(self, registry):
        """Test registering a new profile."""
        profile = ProviderCapabilityProfile(
            provider_id="custom-provider",
            model_id="custom-model",
            display_name="Custom Model",
            provider_type="custom",
        )
        registry.register_profile(profile)

        retrieved = registry.get_profile("custom-provider")
        assert retrieved is not None
        assert retrieved.provider_id == "custom-provider"

    def test_get_by_provider_type(self, registry):
        """Test getting profiles by provider type."""
        anthropic_profiles = registry.get_by_provider_type("anthropic")
        assert len(anthropic_profiles) > 0
        for profile in anthropic_profiles:
            assert profile.provider_type == "anthropic"

    def test_find_capable_providers(self, registry):
        """Test finding providers by capability requirements."""
        requirements = [
            CapabilityRequirement(
                dimension=CapabilityDimension.CONTEXT_LENGTH,
                min_value=100000,
                priority=1,
            ),
            CapabilityRequirement(
                dimension=CapabilityDimension.VISION,
                min_value=True,
                priority=1,
            ),
        ]

        capable = registry.find_capable_providers(requirements)
        assert len(capable) > 0

        # All returned profiles should satisfy requirements
        for profile, _score in capable:
            satisfied, _ = profile.satisfies_requirements(requirements)
            assert satisfied is True

    def test_find_capable_providers_strict_requirements(self, registry):
        """Test finding providers with strict requirements."""
        requirements = [
            CapabilityRequirement(
                dimension=CapabilityDimension.CONTEXT_LENGTH,
                min_value=500000,  # Very high
                priority=1,
            ),
        ]

        capable = registry.find_capable_providers(requirements)
        # Only Gemini should satisfy this
        assert all(p.context_length >= 500000 for p, _ in capable)

    def test_generate_fallback_chain(self, registry):
        """Test fallback chain generation."""
        requirements = [
            CapabilityRequirement(
                dimension=CapabilityDimension.VISION,
                min_value=True,
                priority=1,
            ),
        ]

        fallbacks = registry.generate_fallback_chain("openai-gpt4o", requirements, max_fallbacks=3)

        assert len(fallbacks) <= 3
        assert "openai-gpt4o" not in fallbacks

        # Should prefer different provider types
        if len(fallbacks) >= 2:
            profile1 = registry.get_profile(fallbacks[0])
            profile2 = registry.get_profile(fallbacks[1])
            # First two should be different provider types
            assert profile1.provider_type != profile2.provider_type

    def test_register_discovery_hook(self, registry):
        """Test registering a discovery hook."""
        discovered = []

        def discovery_hook():
            discovered.append("called")
            return []

        registry.register_discovery_hook(discovery_hook)
        assert len(registry._discovery_hooks) > 0


class TestCapabilityRouter:
    """Tests for CapabilityRouter class."""

    @pytest.fixture
    def router(self):
        """Create a fresh router for each test."""
        return CapabilityRouter()

    def test_select_provider(self, router):
        """Test selecting a provider based on requirements."""
        requirements = [
            CapabilityRequirement(
                dimension=CapabilityDimension.CONTEXT_LENGTH,
                min_value=100000,
                priority=1,
            ),
        ]

        provider = router.select_provider(requirements)
        assert provider is not None
        assert provider.context_length >= 100000

    def test_select_provider_with_exclusions(self, router):
        """Test selecting provider with exclusions."""
        requirements = [
            CapabilityRequirement(
                dimension=CapabilityDimension.VISION,
                min_value=True,
                priority=1,
            ),
        ]

        provider = router.select_provider(
            requirements, exclude_providers=["openai-gpt4o", "openai-gpt4o-mini"]
        )
        assert provider is not None
        assert provider.provider_id not in ["openai-gpt4o", "openai-gpt4o-mini"]

    def test_select_provider_no_match(self, router):
        """Test selecting when no provider matches."""
        requirements = [
            CapabilityRequirement(
                dimension=CapabilityDimension.CONTEXT_LENGTH,
                min_value=10000000,  # Impossibly high
                priority=1,
            ),
        ]

        provider = router.select_provider(requirements)
        assert provider is None

    def test_set_preferences(self, router):
        """Test setting routing preferences."""
        router.set_preferences(
            {
                "prefer_low_cost": True,
                "prefer_low_latency": False,
            }
        )

        assert router._routing_preferences["prefer_low_cost"] is True
        assert router._routing_preferences["prefer_low_latency"] is False

    def test_prefer_low_cost_routing(self, router):
        """Test cost-aware routing prefers cheaper providers."""
        router.set_preferences(
            {
                "prefer_low_cost": True,
                "prefer_low_latency": False,
                "load_balance": False,
            }
        )

        requirements = [
            CapabilityRequirement(
                dimension=CapabilityDimension.FUNCTION_CALLING,
                min_value=CapabilityLevel.STANDARD,
                priority=1,
            ),
        ]

        # Select multiple times - should get same low-cost provider
        providers = [router.select_provider(requirements) for _ in range(3)]
        costs = [p.input_cost_per_1k + p.output_cost_per_1k for p in providers if p]

        # Should be consistently cheap
        assert all(c == costs[0] for c in costs)

    def test_get_fallback_chain(self, router):
        """Test getting fallback chain for a provider."""
        requirements = [
            CapabilityRequirement(
                dimension=CapabilityDimension.VISION,
                min_value=True,
                priority=1,
            ),
        ]

        primary = router.registry.get_profile("openai-gpt4o")
        fallbacks = router.get_fallback_chain(primary, requirements)

        assert len(fallbacks) > 0
        assert all(f.provider_id != "openai-gpt4o" for f in fallbacks)

    def test_estimate_cost(self, router):
        """Test cost estimation."""
        profile = router.registry.get_profile("openai-gpt4o")

        cost = router.estimate_cost(
            profile,
            input_tokens=1000,
            output_tokens=500,
        )

        expected = (1000 / 1000) * profile.input_cost_per_1k + (
            500 / 1000
        ) * profile.output_cost_per_1k
        assert cost == expected


class TestGlobalInstances:
    """Tests for module-level global instances."""

    def test_get_capability_registry(self):
        """Test getting global registry."""
        registry = get_capability_registry()
        assert registry is not None
        assert isinstance(registry, CapabilityRegistry)

    def test_get_capability_router(self):
        """Test getting global router."""
        router = get_capability_router()
        assert router is not None
        assert isinstance(router, CapabilityRouter)

    async def test_initialize_capability_matrix(self):
        """Test initializing capability matrix."""
        await initialize_capability_matrix()
        registry = get_capability_registry()
        assert registry._initialized is True


class TestProviderProfiles:
    """Tests for default provider profiles."""

    @pytest.fixture
    def registry(self):
        """Create a fresh registry for each test."""
        return CapabilityRegistry()

    def test_openai_gpt4o_profile(self, registry):
        """Test OpenAI GPT-4o profile."""
        profile = registry.get_profile("openai-gpt4o")
        assert profile is not None
        assert profile.context_length == 128000
        assert profile.vision is True
        assert profile.function_calling == CapabilityLevel.FULL
        assert profile.latency_class == LatencyClass.LOW

    def test_anthropic_claude_profiles(self, registry):
        """Test Anthropic Claude profiles."""
        opus = registry.get_profile("anthropic-claude-opus-4-6")
        sonnet = registry.get_profile("anthropic-claude-sonnet-4-6")
        haiku = registry.get_profile("anthropic-claude-haiku-4-5")

        assert opus is not None
        assert sonnet is not None
        assert haiku is not None

        # Verify ordering (cost, latency)
        assert opus.input_cost_per_1k > sonnet.input_cost_per_1k
        assert sonnet.input_cost_per_1k > haiku.input_cost_per_1k

    def test_google_gemini_profile(self, registry):
        """Test Google Gemini profile."""
        gemini = registry.get_profile("google-gemini-2.0-flash")
        assert gemini is not None
        assert gemini.context_length == 1000000  # 1M context
        assert gemini.video is True  # Multimodal

    def test_bedrock_profile(self, registry):
        """Test AWS Bedrock profile."""
        bedrock = registry.get_profile("bedrock-claude-sonnet-4-6")
        assert bedrock is not None
        assert bedrock.provider_type == "bedrock"

    def test_azure_profile(self, registry):
        """Test Azure OpenAI profile."""
        azure = registry.get_profile("azure-gpt-5-4")
        assert azure is not None
        assert azure.provider_type == "azure"


class TestConstitutionalCompliance:
    """Tests for constitutional hash compliance."""

    def test_capability_value_has_hash(self):
        """Test capability value includes constitutional hash."""
        value = CapabilityValue(
            dimension=CapabilityDimension.CONTEXT_LENGTH,
            value=128000,
        )
        assert value.constitutional_hash == CONSTITUTIONAL_HASH

    def test_requirement_has_hash(self):
        """Test requirement includes constitutional hash."""
        req = CapabilityRequirement(
            dimension=CapabilityDimension.VISION,
            min_value=True,
        )
        assert req.constitutional_hash == CONSTITUTIONAL_HASH

    def test_profile_has_hash(self):
        """Test profile includes constitutional hash."""
        profile = ProviderCapabilityProfile(
            provider_id="test",
            model_id="test",
            display_name="Test",
            provider_type="test",
        )
        assert profile.constitutional_hash == CONSTITUTIONAL_HASH
