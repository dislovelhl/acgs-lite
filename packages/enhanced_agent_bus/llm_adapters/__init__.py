from src.core.shared.constants import CONSTITUTIONAL_HASH

"""
ACGS-2 Enhanced Agent Bus - LLM Adapters
Constitutional Hash: cdd01ef066bc6cf2

Model-agnostic integration framework for LLM providers.
Provides standardized adapters for OpenAI, Anthropic, AWS Bedrock,
Hugging Face, Azure OpenAI, and custom models.

Key Features:
- Unified interface across all providers
- Constitutional compliance validation
- Token counting and cost estimation
- Streaming support
- Automatic retry with exponential backoff
- Health checks and circuit breaker pattern
- Fallback chain support
"""

from .base import (  # noqa: E402
    AdapterStatus,
    BaseLLMAdapter,
    CompletionMetadata,
    CostEstimate,
    HealthCheckResult,
    LLMMessage,
    LLMResponse,
    RetryConfig,
    StreamingMode,
    TokenUsage,
)

# Phase 3 LLM Antifragility modules
from .capability_matrix import (  # noqa: E402
    CapabilityDimension,
    CapabilityLevel,
    CapabilityRegistry,
    CapabilityRequirement,
    LatencyClass,
    ProviderCapabilityProfile,
    get_capability_registry,
)
from .config import (  # noqa: E402
    AdapterConfig,
    AdapterType,
    AnthropicAdapterConfig,
    AWSBedrockAdapterConfig,
    AzureOpenAIAdapterConfig,
    BaseAdapterConfig,
    CustomAdapterConfig,
    HuggingFaceAdapterConfig,
    KimiAdapterConfig,
    LocoOperatorAdapterConfig,
    ModelParameters,
    OpenAIAdapterConfig,
    OpenClawAdapterConfig,
    RateLimitConfig,
)
from .cost_optimizer import (  # noqa: E402
    BatchOptimizer,
    BatchRequest,
    BatchResult,
    BudgetLimit,
    BudgetManager,
    CostAnomaly,
    CostAnomalyDetector,
    CostModel,
    CostOptimizer,
    CostTier,
    QualityLevel,
    UrgencyLevel,
    get_cost_optimizer,
)
from .llm_failover import (  # noqa: E402
    FailoverEvent,
    HealthMetrics,
    HedgedRequest,
    LLMFailoverOrchestrator,
    LLMProviderType,
    ProactiveFailoverManager,
    ProviderHealthScore,
    ProviderHealthScorer,
    ProviderWarmupManager,
    RequestHedgingManager,
    WarmupResult,
    get_llm_circuit_config,
    get_llm_failover_orchestrator,
    reset_llm_failover_orchestrator,
)
from .models import (  # noqa: E402
    FunctionDefinition,
    FunctionParameters,
    LLMRequest,
    MessageConverter,
    RequestConverter,
    ResponseConverter,
    ToolCall,
    ToolCallFunction,
    ToolDefinition,
    ToolType,
)
from .registry import (  # noqa: E402
    AdapterMetrics,
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerState,
    FallbackChain,
    LLMAdapterRegistry,
)

# Import adapters
try:
    from .openai_adapter import OpenAIAdapter
except ImportError:
    OpenAIAdapter = None  # type: ignore[assignment]

try:
    from .anthropic_adapter import AnthropicAdapter
except ImportError:
    AnthropicAdapter = None  # type: ignore[assignment]

try:
    from .bedrock_adapter import BedrockAdapter
except ImportError:
    BedrockAdapter = None  # type: ignore[assignment]

try:
    from .huggingface_adapter import HuggingFaceAdapter
except ImportError:
    HuggingFaceAdapter = None  # type: ignore[assignment]

try:
    from .azure_openai_adapter import AzureOpenAIAdapter
except ImportError:
    AzureOpenAIAdapter = None  # type: ignore[assignment]

try:
    from .openclaw_adapter import OpenClawAdapter
except ImportError:
    OpenClawAdapter = None  # type: ignore[assignment]

# Version info
__version__ = "1.0.0"
__constitutional_hash__ = CONSTITUTIONAL_HASH

__all__ = [
    "AWSBedrockAdapterConfig",
    "AdapterConfig",
    "AdapterMetrics",
    "AdapterStatus",
    "AdapterType",
    "AnthropicAdapter",
    "AnthropicAdapterConfig",
    "AzureOpenAIAdapter",
    "AzureOpenAIAdapterConfig",
    # Configuration
    "BaseAdapterConfig",
    # Base Classes
    "BaseLLMAdapter",
    # Cost Optimizer (Phase 3.2)
    "BatchOptimizer",
    "BatchRequest",
    "BatchResult",
    "BedrockAdapter",
    "BudgetLimit",
    "BudgetManager",
    # Capability Matrix (Phase 3.1)
    "CapabilityDimension",
    "CapabilityLevel",
    "CapabilityRegistry",
    "CapabilityRequirement",
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitBreakerState",
    "CompletionMetadata",
    "CostAnomaly",
    "CostAnomalyDetector",
    "CostEstimate",
    "CostEstimate",
    "CostModel",
    "CostOptimizer",
    "CostTier",
    "CustomAdapterConfig",
    # LLM Failover (Phase 3.3)
    "FailoverEvent",
    "FallbackChain",
    "FunctionDefinition",
    "FunctionParameters",
    "HealthCheckResult",
    "HealthMetrics",
    "HedgedRequest",
    "HuggingFaceAdapter",
    "HuggingFaceAdapterConfig",
    "KimiAdapterConfig",
    # Registry
    "LLMAdapterRegistry",
    "LLMFailoverOrchestrator",
    # Models
    "LLMMessage",
    "LLMProviderType",
    "LLMRequest",
    "LLMResponse",
    "LatencyClass",
    "LocoOperatorAdapterConfig",
    # Converters
    "MessageConverter",
    "ModelParameters",
    # Adapters
    "OpenAIAdapter",
    "OpenAIAdapterConfig",
    "OpenClawAdapter",
    "OpenClawAdapterConfig",
    "ProactiveFailoverManager",
    "ProviderCapabilityProfile",
    "ProviderHealthScore",
    "ProviderHealthScorer",
    "ProviderWarmupManager",
    "QualityLevel",
    "RateLimitConfig",
    "RequestConverter",
    "RequestHedgingManager",
    "ResponseConverter",
    "RetryConfig",
    # Enums
    "StreamingMode",
    # Data Classes
    "TokenUsage",
    "ToolCall",
    "ToolCallFunction",
    # Tool/Function Models
    "ToolDefinition",
    "ToolType",
    "UrgencyLevel",
    "WarmupResult",
    "__constitutional_hash__",
    # Metadata
    "__version__",
    "get_capability_registry",
    "get_cost_optimizer",
    "get_llm_circuit_config",
    "get_llm_failover_orchestrator",
    "reset_llm_failover_orchestrator",
]
