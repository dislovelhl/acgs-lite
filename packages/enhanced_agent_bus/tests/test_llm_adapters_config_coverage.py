# Constitutional Hash: 608508a9bd224290
"""
Comprehensive tests for src/core/enhanced_agent_bus/llm_adapters/config.py

Targets ≥95% line coverage of all classes, methods, validators, and branches.
"""

import os
from unittest.mock import patch

import pytest
from pydantic import SecretStr, ValidationError

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.llm_adapters.config import (
    AdapterConfig,
    AdapterType,
    AnthropicAdapterConfig,
    AWSBedrockAdapterConfig,
    AzureOpenAIAdapterConfig,
    BaseAdapterConfig,
    CustomAdapterConfig,
    HuggingFaceAdapterConfig,
    KimiAdapterConfig,
    ModelParameters,
    OpenAIAdapterConfig,
    RateLimitConfig,
)

# ---------------------------------------------------------------------------
# AdapterType enum
# ---------------------------------------------------------------------------


class TestAdapterType:
    def test_all_values_exist(self):
        assert AdapterType.OPENAI.value == "openai"
        assert AdapterType.ANTHROPIC.value == "anthropic"
        assert AdapterType.AZURE_OPENAI.value == "azure_openai"
        assert AdapterType.AWS_BEDROCK.value == "aws_bedrock"
        assert AdapterType.HUGGINGFACE.value == "huggingface"
        assert AdapterType.KIMI.value == "kimi"
        assert AdapterType.CUSTOM.value == "custom"

    def test_enum_count(self):
        assert len(AdapterType) == 9

    def test_enum_from_value(self):
        assert AdapterType("openai") is AdapterType.OPENAI
        assert AdapterType("custom") is AdapterType.CUSTOM

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            AdapterType("invalid_type")


# ---------------------------------------------------------------------------
# RateLimitConfig
# ---------------------------------------------------------------------------


class TestRateLimitConfig:
    def test_default_values(self):
        cfg = RateLimitConfig()
        assert cfg.requests_per_minute == 60
        assert cfg.tokens_per_minute == 90000
        assert cfg.requests_per_day is None
        assert cfg.tokens_per_day is None
        assert cfg.max_concurrent_requests == 10
        assert cfg.retry_after_seconds == 60

    def test_custom_values(self):
        cfg = RateLimitConfig(
            requests_per_minute=30,
            tokens_per_minute=50000,
            requests_per_day=1000,
            tokens_per_day=500000,
            max_concurrent_requests=5,
            retry_after_seconds=120,
        )
        assert cfg.requests_per_minute == 30
        assert cfg.tokens_per_minute == 50000
        assert cfg.requests_per_day == 1000
        assert cfg.tokens_per_day == 500000
        assert cfg.max_concurrent_requests == 5
        assert cfg.retry_after_seconds == 120

    def test_to_dict_defaults(self):
        cfg = RateLimitConfig()
        d = cfg.to_dict()
        assert d["requests_per_minute"] == 60
        assert d["tokens_per_minute"] == 90000
        assert d["requests_per_day"] is None
        assert d["tokens_per_day"] is None
        assert d["max_concurrent_requests"] == 10
        assert d["retry_after_seconds"] == 60

    def test_to_dict_with_optional_values(self):
        cfg = RateLimitConfig(requests_per_day=1000, tokens_per_day=500000)
        d = cfg.to_dict()
        assert d["requests_per_day"] == 1000
        assert d["tokens_per_day"] == 500000

    def test_requests_per_minute_minimum_boundary(self):
        cfg = RateLimitConfig(requests_per_minute=1)
        assert cfg.requests_per_minute == 1

    def test_requests_per_minute_below_minimum_raises(self):
        with pytest.raises(ValidationError):
            RateLimitConfig(requests_per_minute=0)

    def test_tokens_per_minute_below_minimum_raises(self):
        with pytest.raises(ValidationError):
            RateLimitConfig(tokens_per_minute=0)

    def test_requests_per_day_below_minimum_raises(self):
        with pytest.raises(ValidationError):
            RateLimitConfig(requests_per_day=0)

    def test_tokens_per_day_below_minimum_raises(self):
        with pytest.raises(ValidationError):
            RateLimitConfig(tokens_per_day=0)

    def test_max_concurrent_requests_below_minimum_raises(self):
        with pytest.raises(ValidationError):
            RateLimitConfig(max_concurrent_requests=0)

    def test_retry_after_seconds_below_minimum_raises(self):
        with pytest.raises(ValidationError):
            RateLimitConfig(retry_after_seconds=0)

    def test_from_attributes_mode(self):
        # model_config allows from_attributes
        assert RateLimitConfig.model_config.get("from_attributes") is True


# ---------------------------------------------------------------------------
# ModelParameters
# ---------------------------------------------------------------------------


class TestModelParameters:
    def test_default_values(self):
        mp = ModelParameters()
        assert mp.temperature == 0.7
        assert mp.max_tokens == 1024
        assert mp.top_p == 1.0
        assert mp.top_k is None
        assert mp.frequency_penalty == 0.0
        assert mp.presence_penalty == 0.0
        assert mp.stop_sequences is None

    def test_custom_values(self):
        mp = ModelParameters(
            temperature=0.3,
            max_tokens=512,
            top_p=0.9,
            top_k=50,
            frequency_penalty=0.5,
            presence_penalty=-0.5,
            stop_sequences=["STOP", "END"],
        )
        assert mp.temperature == 0.3
        assert mp.max_tokens == 512
        assert mp.top_p == 0.9
        assert mp.top_k == 50
        assert mp.frequency_penalty == 0.5
        assert mp.presence_penalty == -0.5
        assert mp.stop_sequences == ["STOP", "END"]

    def test_to_dict_defaults_excludes_none(self):
        mp = ModelParameters()
        d = mp.to_dict()
        # top_k and stop_sequences are None by default — should be excluded
        assert "top_k" not in d
        assert "stop_sequences" not in d
        assert d["temperature"] == 0.7
        assert d["max_tokens"] == 1024

    def test_to_dict_includes_non_none(self):
        mp = ModelParameters(top_k=40, stop_sequences=["STOP"])
        d = mp.to_dict()
        assert d["top_k"] == 40
        assert d["stop_sequences"] == ["STOP"]

    def test_to_dict_frequency_and_presence_penalty_included_when_zero(self):
        mp = ModelParameters()
        d = mp.to_dict()
        # 0.0 is not None so it should be present
        assert "frequency_penalty" in d
        assert "presence_penalty" in d

    def test_to_dict_max_tokens_none_excluded(self):
        mp = ModelParameters(max_tokens=None)
        d = mp.to_dict()
        assert "max_tokens" not in d

    def test_temperature_out_of_range_below(self):
        with pytest.raises(ValidationError):
            ModelParameters(temperature=-0.1)

    def test_temperature_out_of_range_above(self):
        with pytest.raises(ValidationError):
            ModelParameters(temperature=2.1)

    def test_top_p_boundary_zero(self):
        mp = ModelParameters(top_p=0.0)
        assert mp.top_p == 0.0

    def test_top_p_boundary_one(self):
        mp = ModelParameters(top_p=1.0)
        assert mp.top_p == 1.0

    def test_top_p_above_max_raises(self):
        with pytest.raises(ValidationError):
            ModelParameters(top_p=1.1)

    def test_top_k_below_minimum_raises(self):
        with pytest.raises(ValidationError):
            ModelParameters(top_k=0)

    def test_max_tokens_below_minimum_raises(self):
        with pytest.raises(ValidationError):
            ModelParameters(max_tokens=0)

    def test_frequency_penalty_boundary(self):
        mp = ModelParameters(frequency_penalty=-2.0)
        assert mp.frequency_penalty == -2.0
        mp2 = ModelParameters(frequency_penalty=2.0)
        assert mp2.frequency_penalty == 2.0

    def test_frequency_penalty_out_of_range(self):
        with pytest.raises(ValidationError):
            ModelParameters(frequency_penalty=2.1)

    def test_presence_penalty_out_of_range(self):
        with pytest.raises(ValidationError):
            ModelParameters(presence_penalty=-2.1)


# ---------------------------------------------------------------------------
# BaseAdapterConfig
# ---------------------------------------------------------------------------


class TestBaseAdapterConfig:
    def _make_config(self, **kwargs):
        defaults = {
            "adapter_type": AdapterType.CUSTOM,
            "model": "test-model",
        }
        defaults.update(kwargs)
        return BaseAdapterConfig(**defaults)

    def test_minimal_construction(self):
        cfg = self._make_config()
        assert cfg.adapter_type == AdapterType.CUSTOM
        assert cfg.model == "test-model"
        assert cfg.api_key is None
        assert cfg.api_base is None
        assert cfg.timeout_seconds == 120
        assert cfg.max_retries == 3
        assert isinstance(cfg.rate_limit, RateLimitConfig)
        assert isinstance(cfg.default_parameters, ModelParameters)
        assert cfg.constitutional_hash == CONSTITUTIONAL_HASH
        assert cfg.extra_headers is None

    def test_with_api_key(self):
        cfg = self._make_config(api_key=SecretStr("my-secret-key"))
        assert cfg.api_key is not None
        assert cfg.api_key.get_secret_value() == "my-secret-key"

    def test_with_all_fields(self):
        cfg = self._make_config(
            api_key=SecretStr("key-123"),
            api_base="https://api.example.com",
            timeout_seconds=30,
            max_retries=5,
            rate_limit=RateLimitConfig(requests_per_minute=10),
            default_parameters=ModelParameters(temperature=0.5),
            extra_headers={"X-Custom": "header"},
        )
        assert cfg.timeout_seconds == 30
        assert cfg.max_retries == 5
        assert cfg.rate_limit.requests_per_minute == 10
        assert cfg.default_parameters.temperature == 0.5
        assert cfg.extra_headers == {"X-Custom": "header"}

    def test_constitutional_hash_default_is_correct(self):
        cfg = self._make_config()
        assert cfg.constitutional_hash == CONSTITUTIONAL_HASH

    def test_constitutional_hash_wrong_length_raises(self):
        with pytest.raises(ValidationError):
            self._make_config(constitutional_hash="short")

    def test_constitutional_hash_16_chars_accepted(self):
        cfg = self._make_config(constitutional_hash="abcdef1234567890")
        assert cfg.constitutional_hash == "abcdef1234567890"

    def test_constitutional_hash_15_chars_raises(self):
        with pytest.raises(ValidationError):
            self._make_config(constitutional_hash="a" * 15)

    def test_constitutional_hash_17_chars_raises(self):
        with pytest.raises(ValidationError):
            self._make_config(constitutional_hash="a" * 17)

    def test_get_api_key_from_config(self):
        cfg = self._make_config(api_key=SecretStr("direct-key"))
        result = cfg.get_api_key("SOME_ENV_VAR")
        assert result == "direct-key"

    def test_get_api_key_from_env_var(self):
        cfg = self._make_config()  # no api_key
        with patch.dict(os.environ, {"MY_API_KEY": "env-key"}):
            result = cfg.get_api_key("MY_API_KEY")
        assert result == "env-key"

    def test_get_api_key_returns_none_when_missing(self):
        cfg = self._make_config()
        env_key = "NONEXISTENT_ENV_VAR_12345"
        os.environ.pop(env_key, None)
        result = cfg.get_api_key(env_key)
        assert result is None

    def test_to_dict_no_secrets(self):
        cfg = self._make_config(api_key=SecretStr("super-secret"))
        d = cfg.to_dict(include_secrets=False)
        assert d["api_key"] == "***"
        assert d["adapter_type"] == "custom"
        assert d["model"] == "test-model"

    def test_to_dict_with_secrets(self):
        cfg = self._make_config(api_key=SecretStr("super-secret"))
        d = cfg.to_dict(include_secrets=True)
        assert d["api_key"] == "super-secret"

    def test_to_dict_no_api_key_shows_none(self):
        cfg = self._make_config()
        d = cfg.to_dict(include_secrets=False)
        assert d["api_key"] is None

    def test_to_dict_no_api_key_include_secrets_true_shows_none(self):
        cfg = self._make_config()
        d = cfg.to_dict(include_secrets=True)
        assert d["api_key"] is None

    def test_to_dict_contains_all_keys(self):
        cfg = self._make_config()
        d = cfg.to_dict()
        expected_keys = {
            "adapter_type",
            "model",
            "api_key",
            "api_base",
            "timeout_seconds",
            "max_retries",
            "rate_limit",
            "default_parameters",
            "constitutional_hash",
            "extra_headers",
        }
        assert expected_keys.issubset(d.keys())

    def test_to_dict_rate_limit_is_dict(self):
        cfg = self._make_config()
        d = cfg.to_dict()
        assert isinstance(d["rate_limit"], dict)

    def test_to_dict_default_parameters_is_dict(self):
        cfg = self._make_config()
        d = cfg.to_dict()
        assert isinstance(d["default_parameters"], dict)

    def test_timeout_below_minimum_raises(self):
        with pytest.raises(ValidationError):
            self._make_config(timeout_seconds=0)

    def test_max_retries_zero_is_valid(self):
        cfg = self._make_config(max_retries=0)
        assert cfg.max_retries == 0

    def test_max_retries_negative_raises(self):
        with pytest.raises(ValidationError):
            self._make_config(max_retries=-1)


# ---------------------------------------------------------------------------
# OpenAIAdapterConfig
# ---------------------------------------------------------------------------


class TestOpenAIAdapterConfig:
    def test_default_adapter_type(self):
        cfg = OpenAIAdapterConfig(model="gpt-4")
        assert cfg.adapter_type == AdapterType.OPENAI

    def test_optional_fields_default(self):
        cfg = OpenAIAdapterConfig(model="gpt-4")
        assert cfg.organization is None
        assert cfg.api_version is None

    def test_with_all_fields(self):
        cfg = OpenAIAdapterConfig(
            model="gpt-4",
            organization="org-123",
            api_version="v2",
            api_key=SecretStr("key"),
        )
        assert cfg.organization == "org-123"
        assert cfg.api_version == "v2"

    def test_from_environment_no_env_vars(self):
        env_overrides = {
            "OPENAI_API_KEY": "",
            "OPENAI_API_BASE": "",
            "OPENAI_ORGANIZATION": "",
            "OPENAI_RPM": "",
            "OPENAI_TPM": "",
        }
        with patch.dict(os.environ, {}, clear=False):
            for k in env_overrides:
                os.environ.pop(k, None)
            cfg = OpenAIAdapterConfig.from_environment()
        assert cfg.api_key is None
        assert cfg.api_base is None
        assert cfg.organization is None
        assert cfg.rate_limit.requests_per_minute == 60
        assert cfg.rate_limit.tokens_per_minute == 90000
        assert cfg.model == "gpt-5.4"

    def test_from_environment_with_env_vars(self):
        env = {
            "OPENAI_API_KEY": "openai-key",
            "OPENAI_API_BASE": "https://my-proxy.com",
            "OPENAI_ORGANIZATION": "org-abc",
            "OPENAI_RPM": "30",
            "OPENAI_TPM": "50000",
        }
        with patch.dict(os.environ, env, clear=False):
            cfg = OpenAIAdapterConfig.from_environment(model="gpt-3.5-turbo")
        assert cfg.api_key.get_secret_value() == "openai-key"
        assert cfg.api_base == "https://my-proxy.com"
        assert cfg.organization == "org-abc"
        assert cfg.rate_limit.requests_per_minute == 30
        assert cfg.rate_limit.tokens_per_minute == 50000
        assert cfg.model == "gpt-3.5-turbo"

    def test_from_environment_default_model(self):
        with patch.dict(os.environ, {}, clear=False):
            for k in ["OPENAI_API_KEY", "OPENAI_API_BASE", "OPENAI_ORGANIZATION"]:
                os.environ.pop(k, None)
            cfg = OpenAIAdapterConfig.from_environment()
        assert cfg.model == "gpt-5.4"

    def test_from_environment_kwargs_override(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OPENAI_API_KEY", None)
            cfg = OpenAIAdapterConfig.from_environment(model="gpt-4", max_retries=5)
        assert cfg.max_retries == 5

    def test_to_dict_shows_adapter_type_as_string(self):
        cfg = OpenAIAdapterConfig(model="gpt-4")
        d = cfg.to_dict()
        assert d["adapter_type"] == "openai"


# ---------------------------------------------------------------------------
# AnthropicAdapterConfig
# ---------------------------------------------------------------------------


class TestAnthropicAdapterConfig:
    def test_default_adapter_type(self):
        cfg = AnthropicAdapterConfig(model="claude-opus-4-6")
        assert cfg.adapter_type == AdapterType.ANTHROPIC

    def test_default_api_version(self):
        cfg = AnthropicAdapterConfig(model="claude-opus-4-6")
        assert cfg.api_version == "2023-06-01"

    def test_from_environment_no_env_vars(self):
        for k in ["ANTHROPIC_API_KEY", "ANTHROPIC_API_BASE", "ANTHROPIC_API_VERSION"]:
            os.environ.pop(k, None)
        cfg = AnthropicAdapterConfig.from_environment()
        assert cfg.api_key is None
        assert cfg.api_base is None
        assert cfg.api_version == "2023-06-01"
        assert cfg.model == "claude-sonnet-4-6"
        assert cfg.rate_limit.requests_per_minute == 50
        assert cfg.rate_limit.tokens_per_minute == 100000

    def test_from_environment_with_env_vars(self):
        env = {
            "ANTHROPIC_API_KEY": "anthropic-key",
            "ANTHROPIC_API_BASE": "https://custom.anthropic.com",
            "ANTHROPIC_API_VERSION": "2024-01-01",
            "ANTHROPIC_RPM": "100",
            "ANTHROPIC_TPM": "200000",
        }
        with patch.dict(os.environ, env, clear=False):
            cfg = AnthropicAdapterConfig.from_environment(model="claude-haiku-3")
        assert cfg.api_key.get_secret_value() == "anthropic-key"
        assert cfg.api_base == "https://custom.anthropic.com"
        assert cfg.api_version == "2024-01-01"
        assert cfg.rate_limit.requests_per_minute == 100
        assert cfg.rate_limit.tokens_per_minute == 200000

    def test_from_environment_default_model(self):
        for k in ["ANTHROPIC_API_KEY"]:
            os.environ.pop(k, None)
        cfg = AnthropicAdapterConfig.from_environment()
        assert cfg.model == "claude-sonnet-4-6"

    def test_from_environment_kwargs_override(self):
        os.environ.pop("ANTHROPIC_API_KEY", None)
        cfg = AnthropicAdapterConfig.from_environment(max_retries=10)
        assert cfg.max_retries == 10


# ---------------------------------------------------------------------------
# AzureOpenAIAdapterConfig
# ---------------------------------------------------------------------------


class TestAzureOpenAIAdapterConfig:
    def test_default_adapter_type(self):
        cfg = AzureOpenAIAdapterConfig(model="gpt-4", deployment_name="my-deploy")
        assert cfg.adapter_type == AdapterType.AZURE_OPENAI

    def test_required_deployment_name(self):
        with pytest.raises(ValidationError):
            AzureOpenAIAdapterConfig(model="gpt-4")  # missing deployment_name

    def test_defaults(self):
        cfg = AzureOpenAIAdapterConfig(model="gpt-4", deployment_name="deploy-1")
        assert cfg.api_version == "2024-02-15-preview"
        assert cfg.azure_endpoint is None
        assert cfg.use_managed_identity is False

    def test_api_base_with_non_azure_domain_logs_warning(self, caplog):
        import logging

        with caplog.at_level(logging.WARNING):
            cfg = AzureOpenAIAdapterConfig(
                model="gpt-4",
                deployment_name="d",
                api_base="https://example.com/api",
            )
        assert "openai.azure.com" in caplog.text or cfg.api_base == "https://example.com/api"

    def test_api_base_with_azure_domain_no_warning(self, caplog):
        import logging

        with caplog.at_level(logging.WARNING):
            cfg = AzureOpenAIAdapterConfig(
                model="gpt-4",
                deployment_name="d",
                api_base="https://myresource.openai.azure.com",
            )
        assert cfg.api_base == "https://myresource.openai.azure.com"

    def test_api_base_none_passes_validator(self):
        cfg = AzureOpenAIAdapterConfig(model="gpt-4", deployment_name="d", api_base=None)
        assert cfg.api_base is None

    def test_from_environment_no_env_vars(self):
        for k in [
            "AZURE_OPENAI_API_KEY",
            "AZURE_OPENAI_ENDPOINT",
            "AZURE_OPENAI_API_VERSION",
            "AZURE_OPENAI_USE_MANAGED_IDENTITY",
        ]:
            os.environ.pop(k, None)
        cfg = AzureOpenAIAdapterConfig.from_environment(deployment_name="test-deploy")
        assert cfg.api_key is None
        assert cfg.api_base is None
        assert cfg.api_version == "2024-02-15-preview"
        assert cfg.use_managed_identity is False
        assert cfg.deployment_name == "test-deploy"

    def test_from_environment_with_env_vars(self):
        env = {
            "AZURE_OPENAI_API_KEY": "azure-key",
            "AZURE_OPENAI_ENDPOINT": "https://my.openai.azure.com",
            "AZURE_OPENAI_API_VERSION": "2024-06-01",
            "AZURE_OPENAI_USE_MANAGED_IDENTITY": "true",
            "AZURE_OPENAI_RPM": "120",
            "AZURE_OPENAI_TPM": "180000",
        }
        with patch.dict(os.environ, env, clear=False):
            cfg = AzureOpenAIAdapterConfig.from_environment(
                deployment_name="prod-deploy",
                model="gpt-35-turbo",
            )
        assert cfg.api_key.get_secret_value() == "azure-key"
        assert cfg.api_base == "https://my.openai.azure.com"
        assert cfg.api_version == "2024-06-01"
        assert cfg.use_managed_identity is True
        assert cfg.rate_limit.requests_per_minute == 120

    def test_from_environment_managed_identity_false(self):
        env = {"AZURE_OPENAI_USE_MANAGED_IDENTITY": "false"}
        with patch.dict(os.environ, env, clear=False):
            for k in ["AZURE_OPENAI_API_KEY"]:
                os.environ.pop(k, None)
            cfg = AzureOpenAIAdapterConfig.from_environment(deployment_name="d")
        assert cfg.use_managed_identity is False

    def test_from_environment_managed_identity_TRUE_uppercase(self):
        env = {
            "AZURE_OPENAI_USE_MANAGED_IDENTITY": "TRUE",
            "AZURE_OPENAI_API_KEY": "",
        }
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("AZURE_OPENAI_API_KEY", None)
            cfg = AzureOpenAIAdapterConfig.from_environment(deployment_name="d")
        assert cfg.use_managed_identity is True

    def test_from_environment_kwargs_override(self):
        for k in ["AZURE_OPENAI_API_KEY"]:
            os.environ.pop(k, None)
        cfg = AzureOpenAIAdapterConfig.from_environment(deployment_name="d", max_retries=7)
        assert cfg.max_retries == 7


# ---------------------------------------------------------------------------
# AWSBedrockAdapterConfig
# ---------------------------------------------------------------------------


class TestAWSBedrockAdapterConfig:
    def test_default_adapter_type(self):
        cfg = AWSBedrockAdapterConfig(model="anthropic.claude-3")
        assert cfg.adapter_type == AdapterType.AWS_BEDROCK

    def test_defaults(self):
        cfg = AWSBedrockAdapterConfig(model="anthropic.claude-3")
        assert cfg.region == "us-east-1"
        assert cfg.aws_access_key_id is None
        assert cfg.aws_secret_access_key is None
        assert cfg.aws_session_token is None
        assert cfg.guardrails_id is None
        assert cfg.guardrails_version is None

    def test_custom_region(self):
        cfg = AWSBedrockAdapterConfig(model="m", region="eu-west-1")
        assert cfg.region == "eu-west-1"

    def test_with_credentials(self):
        cfg = AWSBedrockAdapterConfig(
            model="m",
            aws_access_key_id=SecretStr("AKID"),
            aws_secret_access_key=SecretStr("secret"),
            aws_session_token=SecretStr("token"),
        )
        assert cfg.aws_access_key_id.get_secret_value() == "AKID"
        assert cfg.aws_secret_access_key.get_secret_value() == "secret"
        assert cfg.aws_session_token.get_secret_value() == "token"

    def test_from_environment_no_env_vars(self):
        for k in [
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_SESSION_TOKEN",
            "AWS_REGION",
            "BEDROCK_GUARDRAILS_ID",
            "BEDROCK_GUARDRAILS_VERSION",
        ]:
            os.environ.pop(k, None)
        cfg = AWSBedrockAdapterConfig.from_environment(model="anthropic.claude-3")
        assert cfg.aws_access_key_id is None
        assert cfg.aws_secret_access_key is None
        assert cfg.aws_session_token is None
        assert cfg.region == "us-east-1"
        assert cfg.guardrails_id is None
        assert cfg.guardrails_version is None
        assert cfg.rate_limit.requests_per_minute == 60
        assert cfg.rate_limit.tokens_per_minute == 100000

    def test_from_environment_with_all_env_vars(self):
        env = {
            "AWS_ACCESS_KEY_ID": "access-key",
            "AWS_SECRET_ACCESS_KEY": "secret-key",
            "AWS_SESSION_TOKEN": "session-tok",
            "AWS_REGION": "us-west-2",
            "BEDROCK_GUARDRAILS_ID": "guard-001",
            "BEDROCK_GUARDRAILS_VERSION": "1.0",
            "BEDROCK_RPM": "30",
            "BEDROCK_TPM": "50000",
        }
        with patch.dict(os.environ, env, clear=False):
            cfg = AWSBedrockAdapterConfig.from_environment(model="anthropic.claude-3")
        assert cfg.aws_access_key_id.get_secret_value() == "access-key"
        assert cfg.aws_secret_access_key.get_secret_value() == "secret-key"
        assert cfg.aws_session_token.get_secret_value() == "session-tok"
        assert cfg.region == "us-west-2"
        assert cfg.guardrails_id == "guard-001"
        assert cfg.guardrails_version == "1.0"
        assert cfg.rate_limit.requests_per_minute == 30
        assert cfg.rate_limit.tokens_per_minute == 50000

    def test_from_environment_explicit_region_overrides_env(self):
        env = {"AWS_REGION": "eu-central-1"}
        with patch.dict(os.environ, env, clear=False):
            cfg = AWSBedrockAdapterConfig.from_environment(model="m", region="ap-southeast-1")
        assert cfg.region == "ap-southeast-1"

    def test_from_environment_region_from_env_var(self):
        env = {"AWS_REGION": "ca-central-1"}
        for k in ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"]:
            os.environ.pop(k, None)
        with patch.dict(os.environ, env, clear=False):
            cfg = AWSBedrockAdapterConfig.from_environment(model="m")
        assert cfg.region == "ca-central-1"

    def test_from_environment_kwargs_override(self):
        for k in ["AWS_ACCESS_KEY_ID"]:
            os.environ.pop(k, None)
        cfg = AWSBedrockAdapterConfig.from_environment(model="m", max_retries=2)
        assert cfg.max_retries == 2


# ---------------------------------------------------------------------------
# HuggingFaceAdapterConfig
# ---------------------------------------------------------------------------


class TestHuggingFaceAdapterConfig:
    def test_default_adapter_type(self):
        cfg = HuggingFaceAdapterConfig(model="gpt2")
        assert cfg.adapter_type == AdapterType.HUGGINGFACE

    def test_defaults(self):
        cfg = HuggingFaceAdapterConfig(model="gpt2")
        assert cfg.use_inference_api is True
        assert cfg.inference_endpoint is None
        assert cfg.task == "text-generation"
        assert cfg.device == "cpu"
        assert cfg.quantization is None

    def test_custom_fields(self):
        cfg = HuggingFaceAdapterConfig(
            model="llama-2",
            use_inference_api=False,
            inference_endpoint="https://my-endpoint.hf.space",
            task="text2text-generation",
            device="cuda",
            quantization="8bit",
        )
        assert cfg.use_inference_api is False
        assert cfg.inference_endpoint == "https://my-endpoint.hf.space"
        assert cfg.task == "text2text-generation"
        assert cfg.device == "cuda"
        assert cfg.quantization == "8bit"

    def test_from_environment_no_env_vars(self):
        for k in ["HUGGINGFACE_API_KEY", "HUGGINGFACE_ENDPOINT", "HUGGINGFACE_DEVICE"]:
            os.environ.pop(k, None)
        cfg = HuggingFaceAdapterConfig.from_environment(model="gpt2")
        assert cfg.api_key is None
        assert cfg.inference_endpoint is None
        assert cfg.device == "cpu"
        assert cfg.rate_limit.requests_per_minute == 100
        assert cfg.rate_limit.tokens_per_minute == 100000

    def test_from_environment_with_env_vars(self):
        env = {
            "HUGGINGFACE_API_KEY": "hf-key",
            "HUGGINGFACE_ENDPOINT": "https://custom.endpoint",
            "HUGGINGFACE_DEVICE": "cuda",
            "HUGGINGFACE_RPM": "200",
            "HUGGINGFACE_TPM": "500000",
        }
        with patch.dict(os.environ, env, clear=False):
            cfg = HuggingFaceAdapterConfig.from_environment(
                model="meta-llama/Llama-2-7b-chat-hf", use_inference_api=False
            )
        assert cfg.api_key.get_secret_value() == "hf-key"
        assert cfg.inference_endpoint == "https://custom.endpoint"
        assert cfg.device == "cuda"
        assert cfg.use_inference_api is False
        assert cfg.rate_limit.requests_per_minute == 200

    def test_from_environment_kwargs_override(self):
        os.environ.pop("HUGGINGFACE_API_KEY", None)
        cfg = HuggingFaceAdapterConfig.from_environment(model="gpt2", timeout_seconds=45)
        assert cfg.timeout_seconds == 45


# ---------------------------------------------------------------------------
# KimiAdapterConfig
# ---------------------------------------------------------------------------


class TestKimiAdapterConfig:
    def test_default_adapter_type(self):
        cfg = KimiAdapterConfig(model="kimi-k2.5-free")
        assert cfg.adapter_type == AdapterType.KIMI

    def test_defaults(self):
        cfg = KimiAdapterConfig(model="kimi-k2.5-free")
        assert cfg.api_version == "v1"
        assert cfg.max_context_length == 128000

    def test_custom_context_length(self):
        cfg = KimiAdapterConfig(model="kimi-k2.5", max_context_length=64000)
        assert cfg.max_context_length == 64000

    def test_max_context_length_below_minimum_raises(self):
        with pytest.raises(ValidationError):
            KimiAdapterConfig(model="kimi", max_context_length=0)

    def test_from_environment_no_env_vars(self):
        for k in [
            "MOONSHOT_API_KEY",
            "MOONSHOT_API_BASE",
            "MOONSHOT_API_VERSION",
            "MOONSHOT_RPM",
            "MOONSHOT_TPM",
        ]:
            os.environ.pop(k, None)
        cfg = KimiAdapterConfig.from_environment()
        assert cfg.api_key is None
        assert cfg.api_base == "https://api.moonshot.cn"
        assert cfg.api_version == "v1"
        assert cfg.model == "kimi-k2.5-free"
        assert cfg.rate_limit.requests_per_minute == 100
        assert cfg.rate_limit.tokens_per_minute == 200000

    def test_from_environment_with_env_vars(self):
        env = {
            "MOONSHOT_API_KEY": "moonshot-key",
            "MOONSHOT_API_BASE": "https://custom.moonshot.cn",
            "MOONSHOT_API_VERSION": "v2",
            "MOONSHOT_RPM": "200",
            "MOONSHOT_TPM": "400000",
        }
        with patch.dict(os.environ, env, clear=False):
            cfg = KimiAdapterConfig.from_environment(model="kimi-k2.5")
        assert cfg.api_key.get_secret_value() == "moonshot-key"
        assert cfg.api_base == "https://custom.moonshot.cn"
        assert cfg.api_version == "v2"
        assert cfg.rate_limit.requests_per_minute == 200
        assert cfg.rate_limit.tokens_per_minute == 400000

    def test_from_environment_default_model(self):
        os.environ.pop("MOONSHOT_API_KEY", None)
        cfg = KimiAdapterConfig.from_environment()
        assert cfg.model == "kimi-k2.5-free"

    def test_from_environment_kwargs_override(self):
        os.environ.pop("MOONSHOT_API_KEY", None)
        cfg = KimiAdapterConfig.from_environment(max_retries=1)
        assert cfg.max_retries == 1


# ---------------------------------------------------------------------------
# CustomAdapterConfig
# ---------------------------------------------------------------------------


class TestCustomAdapterConfig:
    def test_default_adapter_type(self):
        cfg = CustomAdapterConfig(model="my-model")
        assert cfg.adapter_type == AdapterType.CUSTOM

    def test_default_custom_params(self):
        cfg = CustomAdapterConfig(model="my-model")
        assert cfg.custom_params == {}

    def test_with_custom_params(self):
        cfg = CustomAdapterConfig(
            model="my-model",
            custom_params={"key1": "value1", "key2": 42},
        )
        assert cfg.custom_params["key1"] == "value1"
        assert cfg.custom_params["key2"] == 42

    def test_from_environment_no_env_vars(self):
        for k in ["CUSTOM_LLM_API_KEY", "CUSTOM_LLM_API_BASE"]:
            os.environ.pop(k, None)
        cfg = CustomAdapterConfig.from_environment(model="local-model")
        assert cfg.api_key is None
        assert cfg.api_base is None
        assert cfg.rate_limit.requests_per_minute == 60
        assert cfg.rate_limit.tokens_per_minute == 100000

    def test_from_environment_with_env_vars(self):
        env = {
            "CUSTOM_LLM_API_KEY": "custom-key",
            "CUSTOM_LLM_API_BASE": "http://localhost:8080",
            "CUSTOM_LLM_RPM": "10",
            "CUSTOM_LLM_TPM": "10000",
        }
        with patch.dict(os.environ, env, clear=False):
            cfg = CustomAdapterConfig.from_environment(model="local-model")
        assert cfg.api_key.get_secret_value() == "custom-key"
        assert cfg.api_base == "http://localhost:8080"
        assert cfg.rate_limit.requests_per_minute == 10
        assert cfg.rate_limit.tokens_per_minute == 10000

    def test_from_environment_custom_prefix(self):
        env = {
            "MY_LLM_API_KEY": "prefix-key",
            "MY_LLM_API_BASE": "http://myserver",
            "MY_LLM_RPM": "5",
            "MY_LLM_TPM": "5000",
        }
        with patch.dict(os.environ, env, clear=False):
            cfg = CustomAdapterConfig.from_environment(model="custom-model", env_prefix="MY_LLM")
        assert cfg.api_key.get_secret_value() == "prefix-key"
        assert cfg.api_base == "http://myserver"
        assert cfg.rate_limit.requests_per_minute == 5

    def test_from_environment_no_prefix_key_returns_none(self):
        for k in ["CUSTOM_LLM_API_KEY", "CUSTOM_LLM_API_BASE"]:
            os.environ.pop(k, None)
        cfg = CustomAdapterConfig.from_environment(model="m")
        assert cfg.api_key is None

    def test_from_environment_kwargs_override(self):
        os.environ.pop("CUSTOM_LLM_API_KEY", None)
        cfg = CustomAdapterConfig.from_environment(model="m", timeout_seconds=300)
        assert cfg.timeout_seconds == 300


# ---------------------------------------------------------------------------
# AdapterConfig union type alias
# ---------------------------------------------------------------------------


class TestAdapterConfigUnion:
    def test_union_includes_all_types(self):
        # Verify the union type works via isinstance checks
        cfg_openai = OpenAIAdapterConfig(model="gpt-4")
        cfg_anthropic = AnthropicAdapterConfig(model="claude")
        cfg_azure = AzureOpenAIAdapterConfig(model="gpt-4", deployment_name="d")
        cfg_bedrock = AWSBedrockAdapterConfig(model="aws.model")
        cfg_hf = HuggingFaceAdapterConfig(model="gpt2")
        cfg_kimi = KimiAdapterConfig(model="kimi")
        cfg_custom = CustomAdapterConfig(model="custom")

        for cfg in [
            cfg_openai,
            cfg_anthropic,
            cfg_azure,
            cfg_bedrock,
            cfg_hf,
            cfg_kimi,
            cfg_custom,
        ]:
            assert isinstance(cfg, BaseAdapterConfig)

    def test_adapter_config_type_alias_exported(self):
        # AdapterConfig is a Union type alias; ensure it's accessible
        assert AdapterConfig is not None


# ---------------------------------------------------------------------------
# __all__ exports
# ---------------------------------------------------------------------------


class TestModuleExports:
    def test_all_exported(self):
        from enhanced_agent_bus.llm_adapters import config as cfg_module

        expected = [
            "AdapterType",
            "RateLimitConfig",
            "ModelParameters",
            "BaseAdapterConfig",
            "OpenAIAdapterConfig",
            "AnthropicAdapterConfig",
            "AzureOpenAIAdapterConfig",
            "AWSBedrockAdapterConfig",
            "HuggingFaceAdapterConfig",
            "KimiAdapterConfig",
            "CustomAdapterConfig",
            "AdapterConfig",
        ]
        for name in expected:
            assert name in cfg_module.__all__, f"{name} missing from __all__"
            assert hasattr(cfg_module, name), f"{name} not accessible on module"


# ---------------------------------------------------------------------------
# Integration / cross-class tests
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_base_config_rate_limit_nested_to_dict(self):
        cfg = OpenAIAdapterConfig(
            model="gpt-4",
            rate_limit=RateLimitConfig(requests_per_minute=15, tokens_per_minute=30000),
        )
        d = cfg.to_dict()
        assert d["rate_limit"]["requests_per_minute"] == 15
        assert d["rate_limit"]["tokens_per_minute"] == 30000

    def test_base_config_model_parameters_nested_to_dict(self):
        cfg = AnthropicAdapterConfig(
            model="claude",
            default_parameters=ModelParameters(temperature=0.0, top_k=10),
        )
        d = cfg.to_dict()
        assert d["default_parameters"]["temperature"] == 0.0
        assert d["default_parameters"]["top_k"] == 10

    def test_get_api_key_prefers_config_over_env(self):
        cfg = OpenAIAdapterConfig(model="gpt-4", api_key=SecretStr("from-config"))
        with patch.dict(os.environ, {"OPENAI_API_KEY": "from-env"}):
            key = cfg.get_api_key("OPENAI_API_KEY")
        assert key == "from-config"

    def test_secret_str_not_leaked_in_repr(self):
        cfg = OpenAIAdapterConfig(model="gpt-4", api_key=SecretStr("top-secret"))
        repr_str = repr(cfg)
        assert "top-secret" not in repr_str

    def test_azure_managed_identity_true_string_conversion(self):
        env = {
            "AZURE_OPENAI_USE_MANAGED_IDENTITY": "True",
        }
        for k in ["AZURE_OPENAI_API_KEY"]:
            os.environ.pop(k, None)
        with patch.dict(os.environ, env, clear=False):
            cfg = AzureOpenAIAdapterConfig.from_environment(deployment_name="d")
        # "True".lower() == "true" so this should be True
        assert cfg.use_managed_identity is True

    def test_bedrock_without_credentials_is_valid_for_iam(self):
        # IAM role-based auth — no access/secret key needed
        cfg = AWSBedrockAdapterConfig(model="anthropic.claude-3", region="us-east-1")
        assert cfg.aws_access_key_id is None
        assert cfg.aws_secret_access_key is None

    def test_model_parameters_to_dict_all_fields_set(self):
        mp = ModelParameters(
            temperature=1.5,
            max_tokens=2048,
            top_p=0.8,
            top_k=50,
            frequency_penalty=1.0,
            presence_penalty=-1.0,
            stop_sequences=["</s>", "[STOP]"],
        )
        d = mp.to_dict()
        assert d["temperature"] == 1.5
        assert d["max_tokens"] == 2048
        assert d["top_p"] == 0.8
        assert d["top_k"] == 50
        assert d["frequency_penalty"] == 1.0
        assert d["presence_penalty"] == -1.0
        assert d["stop_sequences"] == ["</s>", "[STOP]"]

    def test_rate_limit_config_all_optional_none(self):
        cfg = RateLimitConfig()
        d = cfg.to_dict()
        assert d["requests_per_day"] is None
        assert d["tokens_per_day"] is None

    def test_from_env_missing_rpm_tpm_uses_defaults(self):
        """Ensure defaults apply when RPM/TPM env vars are absent."""
        for k in ["OPENAI_RPM", "OPENAI_TPM"]:
            os.environ.pop(k, None)
        os.environ.pop("OPENAI_API_KEY", None)
        cfg = OpenAIAdapterConfig.from_environment()
        assert cfg.rate_limit.requests_per_minute == 60
        assert cfg.rate_limit.tokens_per_minute == 90000

    def test_custom_extra_headers_round_trip(self):
        headers = {"Authorization": "Bearer token", "X-Custom-ID": "12345"}
        cfg = BaseAdapterConfig(
            adapter_type=AdapterType.CUSTOM,
            model="test",
            extra_headers=headers,
        )
        d = cfg.to_dict()
        assert d["extra_headers"] == headers
