"""
ACGS-2 Configuration Merger Utility
Constitutional Hash: 608508a9bd224290

Single source of truth for configuration merging across the codebase.
Replaces scattered config merging logic found in factory.py and other modules.

Usage:
    from src.core.shared.utilities import ConfigMerger

    # Merge configs with defaults
    config = ConfigMerger.merge(base_config, overrides)

    # Deep merge nested dicts
    config = ConfigMerger.deep_merge(defaults, user_config, env_config)
"""

import copy
from typing import TypeVar

from src.core.shared.structured_logging import get_logger
from src.core.shared.types import JSONDict

logger = get_logger(__name__)
T = TypeVar("T")
ConfigDict = JSONDict


class ConfigMerger:
    """
    Utility for merging configuration dictionaries.

    Provides consistent config handling across the codebase:
    - Deep merge of nested dictionaries
    - Override precedence (later sources win)
    - Null/empty value handling
    - Type preservation for non-dict values

    Thread-safe and stateless - all methods are classmethods.
    """

    @classmethod
    def merge(
        cls,
        base: ConfigDict | None,
        *overrides: ConfigDict | None,
        deep: bool = True,
    ) -> ConfigDict:
        """
        Merge multiple configuration dictionaries.

        Args:
            base: Base configuration (can be None)
            *overrides: Override configurations in precedence order
            deep: If True, recursively merge nested dicts

        Returns:
            Merged configuration dictionary

        Example:
            config = ConfigMerger.merge(
                defaults,
                env_config,
                user_config,  # Highest precedence
            )
        """
        result: ConfigDict = copy.deepcopy(base) if base else {}

        for override in overrides:
            if override is None:
                continue
            if deep:
                cls._deep_merge_into(result, override)
            else:
                result.update(override)

        return result

    @classmethod
    def deep_merge(cls, *configs: ConfigDict | None) -> ConfigDict:
        """
        Deep merge multiple configurations (later configs have precedence).

        Args:
            *configs: Configuration dicts in precedence order (last wins)

        Returns:
            Deeply merged configuration

        Example:
            config = ConfigMerger.deep_merge(
                system_defaults,
                tenant_defaults,
                user_preferences,
            )
        """
        if not configs:
            return {}

        result: ConfigDict = {}
        for config in configs:
            if config is not None:
                cls._deep_merge_into(result, config)

        return result

    @classmethod
    def _deep_merge_into(cls, target: ConfigDict, source: ConfigDict) -> None:
        """
        Recursively merge source into target (mutates target).

        Args:
            target: Target dictionary to merge into
            source: Source dictionary to merge from
        """
        for key, value in source.items():
            if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                # Recursively merge nested dicts
                cls._deep_merge_into(target[key], value)
            else:
                # Override with source value (deep copy if mutable)
                if isinstance(value, dict):
                    target[key] = copy.deepcopy(value)
                elif isinstance(value, list):
                    target[key] = copy.deepcopy(value)
                else:
                    target[key] = value

    @classmethod
    def merge_with_env(
        cls,
        config: ConfigDict,
        env_prefix: str,
        env_vars: dict[str, str] | None = None,
    ) -> ConfigDict:
        """
        Merge configuration with environment variable overrides.

        Environment variables override config values when:
        - The env var matches {prefix}_{KEY} pattern
        - The key exists in the config (no new keys added)

        Args:
            config: Base configuration
            env_prefix: Prefix for env vars (e.g., "ACGS2")
            env_vars: Environment variables (defaults to os.environ)

        Returns:
            Configuration with env var overrides applied

        Example:
            # If ACGS2_REDIS_URL is set, it overrides config["redis_url"]
            config = ConfigMerger.merge_with_env(config, "ACGS2")
        """
        import os

        env_vars = env_vars or dict(os.environ)

        result = copy.deepcopy(config)
        prefix = f"{env_prefix}_"

        for key in config.keys():
            env_key = f"{prefix}{key.upper()}"
            if env_key in env_vars:
                env_value = env_vars[env_key]
                # Type coercion based on original type
                result[key] = cls._coerce_type(env_value, config[key])

        return result

    @classmethod
    def _coerce_type(
        cls, value: str, reference: object
    ) -> str | int | float | bool | list | object:
        """
        Coerce string value to match reference type.

        Args:
            value: String value from environment
            reference: Reference value for type inference

        Returns:
            Coerced value matching reference type
        """
        if reference is None:
            return value

        ref_type = type(reference)

        if ref_type is bool:
            return value.lower() in ("true", "1", "yes", "on")
        elif ref_type is int:
            try:
                return int(value)
            except ValueError:
                return reference
        elif ref_type is float:
            try:
                return float(value)
            except ValueError:
                return reference
        elif ref_type is list:
            # Comma-separated list
            return [v.strip() for v in value.split(",") if v.strip()]
        else:
            return value

    @classmethod
    def get_nested(
        cls,
        config: ConfigDict,
        path: str,
        default: T | None = None,
        separator: str = ".",
    ) -> T | None:
        """
        Get a nested config value using dot notation.

        Args:
            config: Configuration dictionary
            path: Dot-separated path (e.g., "redis.connection.pool_size")
            default: Default value if path not found
            separator: Path separator (default ".")

        Returns:
            Value at path or default

        Example:
            pool_size = ConfigMerger.get_nested(config, "redis.pool.size", 10)
        """
        keys = path.split(separator)
        value: object = config

        for key in keys:
            if not isinstance(value, dict):
                return default
            value = value.get(key)
            if value is None:
                return default

        return value

    @classmethod
    def set_nested(
        cls,
        config: ConfigDict,
        path: str,
        value: object,
        separator: str = ".",
    ) -> ConfigDict:
        """
        Set a nested config value using dot notation.

        Creates intermediate dicts as needed.

        Args:
            config: Configuration dictionary (will be mutated)
            path: Dot-separated path
            value: Value to set
            separator: Path separator

        Returns:
            The mutated config dict

        Example:
            ConfigMerger.set_nested(config, "redis.pool.size", 20)
        """
        keys = path.split(separator)
        current = config

        for key in keys[:-1]:
            if key not in current or not isinstance(current[key], dict):
                current[key] = {}
            current = current[key]

        current[keys[-1]] = value
        return config

    @classmethod
    def filter_keys(
        cls,
        config: ConfigDict,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
    ) -> ConfigDict:
        """
        Filter configuration keys.

        Args:
            config: Configuration dictionary
            include: Keys to include (if None, include all)
            exclude: Keys to exclude (applied after include)

        Returns:
            Filtered configuration

        Example:
            public_config = ConfigMerger.filter_keys(
                config,
                exclude=["password", "secret", "api_key"]
            )
        """
        result = dict(config)

        if include is not None:
            result = {k: v for k, v in result.items() if k in include}

        if exclude is not None:
            result = {k: v for k, v in result.items() if k not in exclude}

        return result

    @classmethod
    def redact_secrets(
        cls,
        config: ConfigDict,
        secret_patterns: list[str] | None = None,
        redacted_value: str = "***REDACTED***",
    ) -> ConfigDict:
        """
        Redact secret values from configuration for logging/display.

        Args:
            config: Configuration dictionary
            secret_patterns: Key patterns to redact (default: password, secret, key, token)
            redacted_value: Replacement value for secrets

        Returns:
            Configuration with secrets redacted

        Example:
            safe_config = ConfigMerger.redact_secrets(config)
            logger.info(f"Config: {safe_config}")
        """
        if secret_patterns is None:
            secret_patterns = [
                "password",
                "secret",
                "key",
                "token",
                "credential",
                "auth",
                "private",
            ]

        def should_redact(key: str) -> bool:
            """Return True if the key matches a known secret pattern."""
            key_lower = key.lower()
            return any(pattern in key_lower for pattern in secret_patterns)

        def redact_dict(d: ConfigDict) -> ConfigDict:
            """Recursively redact sensitive values in a config dictionary."""
            result: ConfigDict = {}
            for k, v in d.items():
                if should_redact(k):
                    result[k] = redacted_value
                elif isinstance(v, dict):
                    result[k] = redact_dict(v)
                elif isinstance(v, list):
                    result[k] = [
                        redact_dict(item) if isinstance(item, dict) else item for item in v
                    ]
                else:
                    result[k] = v
            return result

        return redact_dict(config)
