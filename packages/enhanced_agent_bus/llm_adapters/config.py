"""
ACGS-2 Enhanced Agent Bus - LLM Adapter Configuration
Constitutional Hash: cdd01ef066bc6cf2

Pydantic models for adapter configuration including API keys, endpoints,
model parameters, and rate limits. Supports environment variable injection
and provider-specific validation.
"""

import os
from enum import Enum

from pydantic import BaseModel, Field, SecretStr, field_validator

# Import centralized constitutional hash from shared module
try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from src.core.shared.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)


class AdapterType(Enum):
    """Supported LLM adapter types.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    AZURE_OPENAI = "azure_openai"
    AWS_BEDROCK = "aws_bedrock"
    HUGGINGFACE = "huggingface"
    KIMI = "kimi"
    XAI = "xai"
    OPENCLAW = "openclaw"
    CUSTOM = "custom"


class RateLimitConfig(BaseModel):
    """Rate limiting configuration for API requests.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    requests_per_minute: int = Field(
        default=60,
        description="Maximum requests per minute",
        ge=1,
    )
    tokens_per_minute: int = Field(
        default=90000,
        description="Maximum tokens per minute",
        ge=1,
    )
    requests_per_day: int | None = Field(
        default=None,
        description="Maximum requests per day (optional)",
        ge=1,
    )
    tokens_per_day: int | None = Field(
        default=None,
        description="Maximum tokens per day (optional)",
        ge=1,
    )
    max_concurrent_requests: int = Field(
        default=10,
        description="Maximum concurrent requests",
        ge=1,
    )
    retry_after_seconds: int = Field(
        default=60,
        description="Seconds to wait after hitting rate limit",
        ge=1,
    )

    model_config = {"from_attributes": True}

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "requests_per_minute": self.requests_per_minute,
            "tokens_per_minute": self.tokens_per_minute,
            "requests_per_day": self.requests_per_day,
            "tokens_per_day": self.tokens_per_day,
            "max_concurrent_requests": self.max_concurrent_requests,
            "retry_after_seconds": self.retry_after_seconds,
        }


class ModelParameters(BaseModel):
    """Default model parameters for LLM requests.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    temperature: float = Field(
        default=0.7,
        description="Sampling temperature",
        ge=0.0,
        le=2.0,
    )
    max_tokens: int | None = Field(
        default=1024,
        description="Maximum tokens to generate",
        ge=1,
    )
    top_p: float = Field(
        default=1.0,
        description="Nucleus sampling parameter",
        ge=0.0,
        le=1.0,
    )
    top_k: int | None = Field(
        default=None,
        description="Top-k sampling parameter (provider-specific)",
        ge=1,
    )
    frequency_penalty: float | None = Field(
        default=0.0,
        description="Frequency penalty (OpenAI-specific)",
        ge=-2.0,
        le=2.0,
    )
    presence_penalty: float | None = Field(
        default=0.0,
        description="Presence penalty (OpenAI-specific)",
        ge=-2.0,
        le=2.0,
    )
    stop_sequences: list[str] | None = Field(
        default=None,
        description="Stop sequences for generation",
    )

    model_config = {"from_attributes": True}

    def to_dict(self) -> JSONDict:
        """Convert to dictionary, excluding None values."""
        return {
            k: v
            for k, v in {
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
                "top_p": self.top_p,
                "top_k": self.top_k,
                "frequency_penalty": self.frequency_penalty,
                "presence_penalty": self.presence_penalty,
                "stop_sequences": self.stop_sequences,
            }.items()
            if v is not None
        }


class BaseAdapterConfig(BaseModel):
    """Base configuration for all LLM adapters.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    adapter_type: AdapterType = Field(
        ...,
        description="Type of LLM adapter",
    )
    model: str = Field(
        ...,
        description="Model identifier (e.g., 'gpt-5.4', 'claude-sonnet-4-6')",
    )
    api_key: SecretStr | None = Field(
        default=None,
        description="API key for authentication (use env var if not provided)",
    )
    api_base: str | None = Field(
        default=None,
        description="Base URL for API endpoint (provider-specific)",
    )
    timeout_seconds: int = Field(
        default=120,
        description="Request timeout in seconds",
        ge=1,
    )
    max_retries: int = Field(
        default=3,
        description="Maximum number of retry attempts",
        ge=0,
    )
    rate_limit: RateLimitConfig = Field(
        default_factory=RateLimitConfig,
        description="Rate limiting configuration",
    )
    default_parameters: ModelParameters = Field(
        default_factory=ModelParameters,
        description="Default model parameters",
    )
    constitutional_hash: str = Field(
        default=CONSTITUTIONAL_HASH,
        description="Constitutional hash for compliance",
    )
    extra_headers: dict[str, str] | None = Field(
        default=None,
        description="Additional HTTP headers",
    )

    model_config = {"from_attributes": True}

    @field_validator("constitutional_hash")
    @classmethod
    def validate_constitutional_hash(cls, v: str) -> str:
        """Validate constitutional hash format."""
        if len(v) != 16:
            raise ValueError(f"Constitutional hash must be 16 characters, got {len(v)}")
        return v

    def get_api_key(self, env_var: str) -> str | None:
        """Get API key from config or environment variable.

        Args:
            env_var: Environment variable name to check

        Returns:
            API key string or None
        """
        if self.api_key:
            return str(self.api_key.get_secret_value())  # type: ignore[no-any-return]
        _env_val = os.environ.get(env_var)
        if _env_val is None:
            return None
        return str(_env_val)

    def to_dict(self, include_secrets: bool = False) -> JSONDict:
        """Convert to dictionary.

        Args:
            include_secrets: Whether to include API keys in output

        Returns:
            Dictionary representation
        """
        result = {
            "adapter_type": self.adapter_type.value,
            "model": self.model,
            "api_base": self.api_base,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "rate_limit": self.rate_limit.to_dict(),
            "default_parameters": self.default_parameters.to_dict(),
            "constitutional_hash": self.constitutional_hash,
            "extra_headers": self.extra_headers,
        }

        if include_secrets and self.api_key:
            result["api_key"] = self.api_key.get_secret_value()
        else:
            result["api_key"] = "***" if self.api_key else None

        return result


class OpenAIAdapterConfig(BaseAdapterConfig):
    """Configuration for OpenAI adapter.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    adapter_type: AdapterType = Field(
        default=AdapterType.OPENAI,
        description="Adapter type (always 'openai')",
    )
    organization: str | None = Field(
        default=None,
        description="OpenAI organization ID",
    )
    api_version: str | None = Field(
        default=None,
        description="API version (for compatibility)",
    )

    @classmethod
    def from_environment(
        cls,
        model: str = "gpt-5.4",
        **kwargs: object,
    ) -> "OpenAIAdapterConfig":
        """Create config from environment variables.

        Environment variables:
            - OPENAI_API_KEY: API key
            - OPENAI_API_BASE: Base URL (optional)
            - OPENAI_ORGANIZATION: Organization ID (optional)

        Args:
            model: Model identifier
            **kwargs: Additional configuration overrides

        Returns:
            OpenAIAdapterConfig instance
        """
        api_key = os.getenv("OPENAI_API_KEY")

        return cls(
            model=model,
            api_key=SecretStr(api_key) if api_key else None,
            api_base=os.getenv("OPENAI_API_BASE"),
            organization=os.getenv("OPENAI_ORGANIZATION"),
            rate_limit=RateLimitConfig(
                requests_per_minute=int(os.getenv("OPENAI_RPM", "60")),
                tokens_per_minute=int(os.getenv("OPENAI_TPM", "90000")),
            ),
            **kwargs,
        )


class AnthropicAdapterConfig(BaseAdapterConfig):
    """Configuration for Anthropic adapter.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    adapter_type: AdapterType = Field(
        default=AdapterType.ANTHROPIC,
        description="Adapter type (always 'anthropic')",
    )
    api_version: str = Field(
        default="2023-06-01",
        description="Anthropic API version",
    )

    @classmethod
    def from_environment(
        cls,
        model: str = "claude-sonnet-4-6",
        **kwargs: object,
    ) -> "AnthropicAdapterConfig":
        """Create config from environment variables.

        Environment variables:
            - ANTHROPIC_API_KEY: API key
            - ANTHROPIC_API_BASE: Base URL (optional)
            - ANTHROPIC_API_VERSION: API version (optional)

        Args:
            model: Model identifier
            **kwargs: Additional configuration overrides

        Returns:
            AnthropicAdapterConfig instance
        """
        api_key = os.getenv("ANTHROPIC_API_KEY")

        return cls(
            model=model,
            api_key=SecretStr(api_key) if api_key else None,
            api_base=os.getenv("ANTHROPIC_API_BASE"),
            api_version=os.getenv("ANTHROPIC_API_VERSION", "2023-06-01"),
            rate_limit=RateLimitConfig(
                requests_per_minute=int(os.getenv("ANTHROPIC_RPM", "50")),
                tokens_per_minute=int(os.getenv("ANTHROPIC_TPM", "100000")),
            ),
            **kwargs,
        )


class AzureOpenAIAdapterConfig(BaseAdapterConfig):
    """Configuration for Azure OpenAI adapter.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    adapter_type: AdapterType = Field(
        default=AdapterType.AZURE_OPENAI,
        description="Adapter type (always 'azure_openai')",
    )
    deployment_name: str = Field(
        ...,
        description="Azure deployment name",
    )
    api_version: str = Field(
        default="2024-02-15-preview",
        description="Azure OpenAI API version",
    )
    azure_endpoint: str | None = Field(
        default=None,
        description="Azure OpenAI endpoint URL",
    )
    use_managed_identity: bool = Field(
        default=False,
        description="Use Azure Managed Identity for authentication",
    )

    @field_validator("api_base")
    @classmethod
    def validate_azure_endpoint(cls, v: str | None, info: object) -> str | None:
        """Validate Azure endpoint format."""
        if v and not v.endswith(".openai.azure.com"):
            logger.warning(f"Azure endpoint should end with '.openai.azure.com': {v}")
        return v

    @classmethod
    def from_environment(
        cls,
        deployment_name: str,
        model: str = "gpt-5.4",
        **kwargs: object,
    ) -> "AzureOpenAIAdapterConfig":
        """Create config from environment variables.

        Environment variables:
            - AZURE_OPENAI_API_KEY: API key (if not using managed identity)
            - AZURE_OPENAI_ENDPOINT: Endpoint URL
            - AZURE_OPENAI_API_VERSION: API version (optional)
            - AZURE_OPENAI_USE_MANAGED_IDENTITY: Use managed identity (optional)

        Args:
            deployment_name: Azure deployment name
            model: Model identifier
            **kwargs: Additional configuration overrides

        Returns:
            AzureOpenAIAdapterConfig instance
        """
        api_key = os.getenv("AZURE_OPENAI_API_KEY")

        return cls(
            model=model,
            deployment_name=deployment_name,
            api_key=SecretStr(api_key) if api_key else None,
            api_base=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview"),
            use_managed_identity=os.getenv("AZURE_OPENAI_USE_MANAGED_IDENTITY", "false").lower()
            == "true",
            rate_limit=RateLimitConfig(
                requests_per_minute=int(os.getenv("AZURE_OPENAI_RPM", "60")),
                tokens_per_minute=int(os.getenv("AZURE_OPENAI_TPM", "90000")),
            ),
            **kwargs,
        )


class AWSBedrockAdapterConfig(BaseAdapterConfig):
    """Configuration for AWS Bedrock adapter.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    adapter_type: AdapterType = Field(
        default=AdapterType.AWS_BEDROCK,
        description="Adapter type (always 'aws_bedrock')",
    )
    region: str = Field(
        default="us-east-1",
        description="AWS region",
    )
    aws_access_key_id: SecretStr | None = Field(
        default=None,
        description="AWS access key ID (use IAM role if not provided)",
    )
    aws_secret_access_key: SecretStr | None = Field(
        default=None,
        description="AWS secret access key (use IAM role if not provided)",
    )
    aws_session_token: SecretStr | None = Field(
        default=None,
        description="AWS session token (for temporary credentials)",
    )
    guardrails_id: str | None = Field(
        default=None,
        description="Bedrock Guardrails ID",
    )
    guardrails_version: str | None = Field(
        default=None,
        description="Bedrock Guardrails version",
    )

    @classmethod
    def from_environment(
        cls,
        model: str,
        region: str | None = None,
        **kwargs: object,
    ) -> "AWSBedrockAdapterConfig":
        """Create config from environment variables.

        Environment variables:
            - AWS_ACCESS_KEY_ID: Access key ID (optional if using IAM role)
            - AWS_SECRET_ACCESS_KEY: Secret access key (optional if using IAM role)
            - AWS_SESSION_TOKEN: Session token (optional)
            - AWS_REGION: AWS region
            - BEDROCK_GUARDRAILS_ID: Guardrails ID (optional)
            - BEDROCK_GUARDRAILS_VERSION: Guardrails version (optional)

        Args:
            model: Model identifier (e.g., 'anthropic.claude-3-sonnet-20240229-v1:0')
            region: AWS region (defaults to env var or us-east-1)
            **kwargs: Additional configuration overrides

        Returns:
            AWSBedrockAdapterConfig instance
        """
        access_key = os.getenv("AWS_ACCESS_KEY_ID")
        secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
        session_token = os.getenv("AWS_SESSION_TOKEN")

        return cls(
            model=model,
            region=region or os.getenv("AWS_REGION", "us-east-1"),
            aws_access_key_id=SecretStr(access_key) if access_key else None,
            aws_secret_access_key=SecretStr(secret_key) if secret_key else None,
            aws_session_token=SecretStr(session_token) if session_token else None,
            guardrails_id=os.getenv("BEDROCK_GUARDRAILS_ID"),
            guardrails_version=os.getenv("BEDROCK_GUARDRAILS_VERSION"),
            rate_limit=RateLimitConfig(
                requests_per_minute=int(os.getenv("BEDROCK_RPM", "60")),
                tokens_per_minute=int(os.getenv("BEDROCK_TPM", "100000")),
            ),
            **kwargs,
        )


class HuggingFaceAdapterConfig(BaseAdapterConfig):
    """Configuration for Hugging Face adapter.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    adapter_type: AdapterType = Field(
        default=AdapterType.HUGGINGFACE,
        description="Adapter type (always 'huggingface')",
    )
    use_inference_api: bool = Field(
        default=True,
        description="Use Hugging Face Inference API (vs local model)",
    )
    inference_endpoint: str | None = Field(
        default=None,
        description="Custom inference endpoint URL",
    )
    task: str = Field(
        default="text-generation",
        description="Hugging Face task type",
    )
    device: str = Field(
        default="cpu",
        description="Device for local inference ('cpu', 'cuda', 'mps')",
    )
    quantization: str | None = Field(
        default=None,
        description="Quantization method for local models (e.g., '8bit', '4bit')",
    )

    @classmethod
    def from_environment(
        cls,
        model: str,
        use_inference_api: bool = True,
        **kwargs: object,
    ) -> "HuggingFaceAdapterConfig":
        """Create config from environment variables.

        Environment variables:
            - HUGGINGFACE_API_KEY: API key for Inference API
            - HUGGINGFACE_ENDPOINT: Custom inference endpoint (optional)
            - HUGGINGFACE_DEVICE: Device for local inference (optional)

        Args:
            model: Model identifier (e.g., 'meta-llama/Llama-2-7b-chat-hf')
            use_inference_api: Use Inference API vs local model
            **kwargs: Additional configuration overrides

        Returns:
            HuggingFaceAdapterConfig instance
        """
        api_key = os.getenv("HUGGINGFACE_API_KEY")

        return cls(
            model=model,
            api_key=SecretStr(api_key) if api_key else None,
            use_inference_api=use_inference_api,
            inference_endpoint=os.getenv("HUGGINGFACE_ENDPOINT"),
            device=os.getenv("HUGGINGFACE_DEVICE", "cpu"),
            rate_limit=RateLimitConfig(
                requests_per_minute=int(os.getenv("HUGGINGFACE_RPM", "100")),
                tokens_per_minute=int(os.getenv("HUGGINGFACE_TPM", "100000")),
            ),
            **kwargs,
        )


class KimiAdapterConfig(BaseAdapterConfig):
    """Configuration for Moonshot AI (Kimi) adapter.

    Constitutional Hash: cdd01ef066bc6cf2

    Supports Kimi K2.5 models with free tier access.
    """

    adapter_type: AdapterType = Field(
        default=AdapterType.KIMI,
        description="Adapter type (always 'kimi')",
    )
    api_version: str = Field(
        default="v1",
        description="Moonshot API version",
    )
    max_context_length: int = Field(
        default=128000,
        description="Maximum context length in tokens",
        ge=1,
    )

    @classmethod
    def from_environment(
        cls,
        model: str = "kimi-k2.5-free",
        **kwargs: object,
    ) -> "KimiAdapterConfig":
        """Create config from environment variables.

        Environment variables:
            - MOONSHOT_API_KEY: API key
            - MOONSHOT_API_BASE: Base URL (optional, defaults to https://api.moonshot.cn)
            - MOONSHOT_API_VERSION: API version (optional)

        Args:
            model: Model identifier (e.g., 'kimi-k2.5-free', 'kimi-k2.5')
            **kwargs: Additional configuration overrides

        Returns:
            KimiAdapterConfig instance
        """
        api_key = os.getenv("MOONSHOT_API_KEY")

        return cls(
            model=model,
            api_key=SecretStr(api_key) if api_key else None,
            api_base=os.getenv("MOONSHOT_API_BASE", "https://api.moonshot.cn"),
            api_version=os.getenv("MOONSHOT_API_VERSION", "v1"),
            rate_limit=RateLimitConfig(
                requests_per_minute=int(os.getenv("MOONSHOT_RPM", "100")),
                tokens_per_minute=int(os.getenv("MOONSHOT_TPM", "200000")),
            ),
            **kwargs,
        )


class XAIAdapterConfig(BaseAdapterConfig):
    """Configuration for xAI (Grok) adapter.

    Constitutional Hash: cdd01ef066bc6cf2

    xAI exposes an OpenAI-compatible API at https://api.x.ai/v1.
    Supports Grok 4.x models with 2M token context, server-side tools
    (web search, X search, code execution, Collections), prompt caching,
    and batch API (50% off).
    """

    adapter_type: AdapterType = Field(
        default=AdapterType.XAI,
        description="Adapter type (always 'xai')",
    )
    enable_web_search: bool = Field(
        default=False,
        description="Enable server-side web search tool",
    )
    enable_x_search: bool = Field(
        default=False,
        description="Enable server-side X (Twitter) search tool",
    )
    enable_code_execution: bool = Field(
        default=False,
        description="Enable server-side code execution tool",
    )
    search_allowed_domains: list[str] | None = Field(
        default=None,
        description="Restrict web search to these domains (max 5)",
    )
    search_excluded_domains: list[str] | None = Field(
        default=None,
        description="Exclude these domains from web search (max 5)",
    )

    @classmethod
    def from_environment(
        cls,
        model: str = "grok-4-1-fast",
        **kwargs: object,
    ) -> "XAIAdapterConfig":
        """Create config from environment variables.

        Environment variables:
            - XAI_API_KEY: API key
            - XAI_API_BASE: Base URL (optional, defaults to https://api.x.ai/v1)
            - XAI_RPM: Requests per minute (optional)
            - XAI_TPM: Tokens per minute (optional)

        Args:
            model: Model identifier (e.g., 'grok-4-1-fast', 'grok-4.20')
            **kwargs: Additional configuration overrides

        Returns:
            XAIAdapterConfig instance
        """
        api_key = os.getenv("XAI_API_KEY")

        return cls(
            model=model,
            api_key=SecretStr(api_key) if api_key else None,
            api_base=os.getenv("XAI_API_BASE", "https://api.x.ai/v1"),
            rate_limit=RateLimitConfig(
                requests_per_minute=int(os.getenv("XAI_RPM", "607")),
                tokens_per_minute=int(os.getenv("XAI_TPM", "4000000")),
            ),
            **kwargs,
        )


class OpenClawAdapterConfig(BaseAdapterConfig):
    """Configuration for OpenClaw gateway adapter.

    Constitutional Hash: cdd01ef066bc6cf2

    OpenClaw is a local agent runtime gateway that proxies requests to
    underlying model providers. It exposes an OpenAI-compatible API endpoint
    and supports routing to multiple providers (Anthropic, OpenAI, etc.).

    Models use the format 'provider/model-name' (e.g., 'anthropic/claude-opus-4-6').
    """

    adapter_type: AdapterType = Field(
        default=AdapterType.OPENCLAW,
        description="Adapter type (always 'openclaw')",
    )
    gateway_url: str = Field(
        default="ws://127.0.0.1:18789",
        description="OpenClaw gateway WebSocket URL",
    )
    gateway_token: SecretStr | None = Field(
        default=None,
        description="OpenClaw gateway authentication token",
    )
    default_agent: str = Field(
        default="main",
        description="Default OpenClaw agent ID",
    )
    thinking_level: str = Field(
        default="off",
        description="Thinking level for reasoning models (off, low, medium, high)",
    )

    @classmethod
    def from_environment(
        cls,
        model: str = "anthropic/claude-opus-4-6",
        **kwargs: object,
    ) -> "OpenClawAdapterConfig":
        """Create config from environment variables.

        Environment variables:
            - OPENCLAW_API_KEY: API key (optional, for remote gateways)
            - OPENCLAW_API_BASE: HTTP API base URL (optional)
            - OPENCLAW_GATEWAY_URL: WebSocket gateway URL (optional)
            - OPENCLAW_GATEWAY_TOKEN: Gateway auth token (optional)
            - OPENCLAW_DEFAULT_AGENT: Default agent ID (optional)

        Args:
            model: Model identifier (e.g., 'anthropic/claude-opus-4-6')
            **kwargs: Additional configuration overrides

        Returns:
            OpenClawAdapterConfig instance
        """
        api_key = os.getenv("OPENCLAW_API_KEY")
        gateway_token = os.getenv("OPENCLAW_GATEWAY_TOKEN")

        return cls(
            model=model,
            api_key=SecretStr(api_key) if api_key else None,
            api_base=os.getenv("OPENCLAW_API_BASE", "http://127.0.0.1:18790"),
            gateway_url=os.getenv("OPENCLAW_GATEWAY_URL", "ws://127.0.0.1:18789"),
            gateway_token=SecretStr(gateway_token) if gateway_token else None,
            default_agent=os.getenv("OPENCLAW_DEFAULT_AGENT", "main"),
            rate_limit=RateLimitConfig(
                requests_per_minute=int(os.getenv("OPENCLAW_RPM", "100")),
                tokens_per_minute=int(os.getenv("OPENCLAW_TPM", "200000")),
            ),
            **kwargs,
        )


class CustomAdapterConfig(BaseAdapterConfig):
    """Configuration for custom LLM adapter.

    Constitutional Hash: cdd01ef066bc6cf2

    Use this for proprietary or local models that don't fit other adapters.
    """

    adapter_type: AdapterType = Field(
        default=AdapterType.CUSTOM,
        description="Adapter type (always 'custom')",
    )
    custom_params: JSONDict = Field(
        default_factory=dict,
        description="Custom parameters specific to the adapter",
    )

    @classmethod
    def from_environment(
        cls,
        model: str,
        env_prefix: str = "CUSTOM_LLM",
        **kwargs: object,
    ) -> "CustomAdapterConfig":
        """Create config from environment variables.

        Environment variables:
            - {env_prefix}_API_KEY: API key
            - {env_prefix}_API_BASE: Base URL

        Args:
            model: Model identifier
            env_prefix: Prefix for environment variables
            **kwargs: Additional configuration overrides

        Returns:
            CustomAdapterConfig instance
        """
        api_key = os.getenv(f"{env_prefix}_API_KEY")

        return cls(
            model=model,
            api_key=SecretStr(api_key) if api_key else None,
            api_base=os.getenv(f"{env_prefix}_API_BASE"),
            rate_limit=RateLimitConfig(
                requests_per_minute=int(os.getenv(f"{env_prefix}_RPM", "60")),
                tokens_per_minute=int(os.getenv(f"{env_prefix}_TPM", "100000")),
            ),
            **kwargs,
        )


class LocoOperatorAdapterConfig(HuggingFaceAdapterConfig):
    """Configuration for LocoOperator-4B (local operator/agent model).

    Constitutional Hash: cdd01ef066bc6cf2

    LocoOperator-4B is a MACI Proposer-only model. It generates governance
    scoring signals and action recommendations that must pass independent
    validation before execution. It is never used as a validator or executor.

    Defaults to local inference (use_inference_api=False) with ChatML format.
    """

    adapter_type: AdapterType = Field(
        default=AdapterType.HUGGINGFACE,
        description="Adapter type (always 'huggingface' for LocoOperator)",
    )
    model: str = Field(
        default="LocoreMind/LocoOperator-4B-GGUF",
        description="LocoOperator model identifier",
    )
    use_inference_api: bool = Field(
        default=False,
        description="Use local inference by default (LocoOperator-4B is local-first)",
    )
    tool_call_format: str = Field(
        default="chatml",
        description="Tool call format used by LocoOperator (chatml/json)",
    )
    max_tool_calls: int = Field(
        default=8,
        description="Maximum tool calls per inference request",
        ge=1,
        le=32,
    )

    @field_validator("tool_call_format")
    @classmethod
    def validate_tool_call_format(cls, v: str) -> str:
        """Validate tool call format is a supported value."""
        allowed = {"chatml", "json", "react"}
        if v not in allowed:
            raise ValueError(f"tool_call_format must be one of {allowed}, got {v!r}")
        return v

    @classmethod
    def from_environment(  # type: ignore[override]
        cls,
        model: str = "LocoreMind/LocoOperator-4B-GGUF",
        **kwargs: object,
    ) -> "LocoOperatorAdapterConfig":
        """Create LocoOperator config from environment variables.

        Environment variables:
            - LOCOOPERATOR_MODEL: Model identifier (optional override)
            - LOCOOPERATOR_DEVICE: Inference device ('cpu', 'cuda', 'mps')
            - LOCOOPERATOR_QUANTIZATION: Quantization method ('4bit', '8bit', None)
            - HUGGINGFACE_API_KEY: API key for HF Inference API fallback (optional)

        Args:
            model: Default model identifier
            **kwargs: Additional configuration overrides

        Returns:
            LocoOperatorAdapterConfig instance
        """
        model_id = os.getenv("LOCOOPERATOR_MODEL", model)
        device = os.getenv("LOCOOPERATOR_DEVICE", "cpu")
        quantization = os.getenv("LOCOOPERATOR_QUANTIZATION")
        api_key = os.getenv("HUGGINGFACE_API_KEY")

        return cls(
            model=model_id,
            api_key=SecretStr(api_key) if api_key else None,
            use_inference_api=False,
            device=device,
            quantization=quantization,
            rate_limit=RateLimitConfig(
                requests_per_minute=int(os.getenv("LOCOOPERATOR_RPM", "30")),
                tokens_per_minute=int(os.getenv("LOCOOPERATOR_TPM", "50000")),
            ),
            **kwargs,
        )


# Type alias for any adapter config
AdapterConfig = (
    OpenAIAdapterConfig
    | AnthropicAdapterConfig
    | AzureOpenAIAdapterConfig
    | AWSBedrockAdapterConfig
    | HuggingFaceAdapterConfig
    | LocoOperatorAdapterConfig
    | KimiAdapterConfig
    | XAIAdapterConfig
    | OpenClawAdapterConfig
    | CustomAdapterConfig
)


__all__ = [
    "AWSBedrockAdapterConfig",
    # Type aliases
    "AdapterConfig",
    # Enums
    "AdapterType",
    "AnthropicAdapterConfig",
    "AzureOpenAIAdapterConfig",
    "BaseAdapterConfig",
    "CustomAdapterConfig",
    "HuggingFaceAdapterConfig",
    "KimiAdapterConfig",
    "LocoOperatorAdapterConfig",
    "ModelParameters",
    "OpenAIAdapterConfig",
    "OpenClawAdapterConfig",
    # Configuration models
    "RateLimitConfig",
    "XAIAdapterConfig",
]
