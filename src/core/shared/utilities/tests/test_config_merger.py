"""
Tests for ConfigMerger utility.
Constitutional Hash: cdd01ef066bc6cf2
"""

from src.core.shared.utilities import ConfigMerger


class TestConfigMergerMerge:
    """Test ConfigMerger.merge() method."""

    def test_merge_basic(self) -> None:
        """Test basic merge of two configs."""
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}
        result = ConfigMerger.merge(base, override)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_merge_none_base(self) -> None:
        """Test merge with None base."""
        result = ConfigMerger.merge(None, {"a": 1})
        assert result == {"a": 1}

    def test_merge_none_override(self) -> None:
        """Test merge with None override."""
        result = ConfigMerger.merge({"a": 1}, None)
        assert result == {"a": 1}

    def test_merge_multiple_overrides(self) -> None:
        """Test merge with multiple overrides."""
        base = {"a": 1}
        override1 = {"b": 2}
        override2 = {"c": 3}
        result = ConfigMerger.merge(base, override1, override2)
        assert result == {"a": 1, "b": 2, "c": 3}

    def test_merge_shallow(self) -> None:
        """Test shallow merge (deep=False)."""
        base = {"nested": {"a": 1, "b": 2}}
        override = {"nested": {"b": 3}}
        result = ConfigMerger.merge(base, override, deep=False)
        assert result == {"nested": {"b": 3}}  # Full replacement


class TestConfigMergerDeepMerge:
    """Test ConfigMerger.deep_merge() method."""

    def test_deep_merge_nested_dicts(self) -> None:
        """Test deep merge of nested dictionaries."""
        config1 = {"nested": {"a": 1, "b": 2}}
        config2 = {"nested": {"b": 3, "c": 4}}
        result = ConfigMerger.deep_merge(config1, config2)
        assert result == {"nested": {"a": 1, "b": 3, "c": 4}}

    def test_deep_merge_preserves_lists(self) -> None:
        """Test that lists are replaced, not merged."""
        config1 = {"items": [1, 2, 3]}
        config2 = {"items": [4, 5]}
        result = ConfigMerger.deep_merge(config1, config2)
        assert result == {"items": [4, 5]}

    def test_deep_merge_empty_configs(self) -> None:
        """Test deep merge with empty configs."""
        result = ConfigMerger.deep_merge()
        assert result == {}

    def test_deep_merge_three_levels(self) -> None:
        """Test deep merge with three nesting levels."""
        config1 = {"a": {"b": {"c": 1}}}
        config2 = {"a": {"b": {"d": 2}}}
        result = ConfigMerger.deep_merge(config1, config2)
        assert result == {"a": {"b": {"c": 1, "d": 2}}}


class TestConfigMergerMergeWithEnv:
    """Test ConfigMerger.merge_with_env() method."""

    def test_merge_with_env_string(self) -> None:
        """Test env override for string value."""
        config = {"db_host": "localhost"}
        env_vars = {"TEST_DB_HOST": "production-db"}
        result = ConfigMerger.merge_with_env(config, "TEST", env_vars)
        assert result["db_host"] == "production-db"

    def test_merge_with_env_int(self) -> None:
        """Test env override with int coercion."""
        config = {"port": 8080}
        env_vars = {"TEST_PORT": "9090"}
        result = ConfigMerger.merge_with_env(config, "TEST", env_vars)
        assert result["port"] == 9090

    def test_merge_with_env_bool(self) -> None:
        """Test env override with bool coercion."""
        config = {"debug": False}
        env_vars = {"TEST_DEBUG": "true"}
        result = ConfigMerger.merge_with_env(config, "TEST", env_vars)
        assert result["debug"] is True

    def test_merge_with_env_list(self) -> None:
        """Test env override with list coercion."""
        config = {"hosts": ["host1"]}
        env_vars = {"TEST_HOSTS": "host1, host2, host3"}
        result = ConfigMerger.merge_with_env(config, "TEST", env_vars)
        assert result["hosts"] == ["host1", "host2", "host3"]

    def test_merge_with_env_no_override(self) -> None:
        """Test that missing env vars don't affect config."""
        config = {"value": "original"}
        env_vars = {}
        result = ConfigMerger.merge_with_env(config, "TEST", env_vars)
        assert result["value"] == "original"


class TestConfigMergerGetNested:
    """Test ConfigMerger.get_nested() method."""

    def test_get_nested_simple(self) -> None:
        """Test getting nested value."""
        config = {"a": {"b": {"c": 42}}}
        assert ConfigMerger.get_nested(config, "a.b.c") == 42

    def test_get_nested_missing(self) -> None:
        """Test missing path returns default."""
        config = {"a": {"b": 1}}
        assert ConfigMerger.get_nested(config, "a.b.c", default="missing") == "missing"

    def test_get_nested_none_default(self) -> None:
        """Test missing path returns None by default."""
        config = {"a": 1}
        assert ConfigMerger.get_nested(config, "b.c") is None

    def test_get_nested_custom_separator(self) -> None:
        """Test custom path separator."""
        config = {"a": {"b": 42}}
        assert ConfigMerger.get_nested(config, "a/b", separator="/") == 42


class TestConfigMergerSetNested:
    """Test ConfigMerger.set_nested() method."""

    def test_set_nested_existing(self) -> None:
        """Test setting existing nested path."""
        config = {"a": {"b": 1}}
        ConfigMerger.set_nested(config, "a.b", 42)
        assert config["a"]["b"] == 42

    def test_set_nested_new_path(self) -> None:
        """Test creating new nested path."""
        config = {}
        ConfigMerger.set_nested(config, "a.b.c", 42)
        assert config == {"a": {"b": {"c": 42}}}

    def test_set_nested_returns_config(self) -> None:
        """Test that set_nested returns the config."""
        config = {}
        result = ConfigMerger.set_nested(config, "a", 1)
        assert result is config


class TestConfigMergerFilterKeys:
    """Test ConfigMerger.filter_keys() method."""

    def test_filter_keys_include(self) -> None:
        """Test filtering with include list."""
        config = {"a": 1, "b": 2, "c": 3}
        result = ConfigMerger.filter_keys(config, include=["a", "c"])
        assert result == {"a": 1, "c": 3}

    def test_filter_keys_exclude(self) -> None:
        """Test filtering with exclude list."""
        config = {"a": 1, "b": 2, "c": 3}
        result = ConfigMerger.filter_keys(config, exclude=["b"])
        assert result == {"a": 1, "c": 3}

    def test_filter_keys_both(self) -> None:
        """Test filtering with include and exclude."""
        config = {"a": 1, "b": 2, "c": 3}
        result = ConfigMerger.filter_keys(config, include=["a", "b"], exclude=["b"])
        assert result == {"a": 1}


class TestConfigMergerRedactSecrets:
    """Test ConfigMerger.redact_secrets() method."""

    def test_redact_secrets_password(self) -> None:
        """Test that passwords are redacted."""
        config = {"username": "admin", "password": "secret123"}
        result = ConfigMerger.redact_secrets(config)
        assert result["username"] == "admin"
        assert result["password"] == "***REDACTED***"

    def test_redact_secrets_api_key(self) -> None:
        """Test that API keys are redacted."""
        config = {"api_key": "sk-1234567890"}
        result = ConfigMerger.redact_secrets(config)
        assert result["api_key"] == "***REDACTED***"

    def test_redact_secrets_nested(self) -> None:
        """Test redaction in nested configs."""
        config = {"db": {"host": "localhost", "password": "secret"}}
        result = ConfigMerger.redact_secrets(config)
        assert result["db"]["host"] == "localhost"
        assert result["db"]["password"] == "***REDACTED***"

    def test_redact_secrets_custom_value(self) -> None:
        """Test custom redacted value."""
        config = {"password": "secret"}
        result = ConfigMerger.redact_secrets(config, redacted_value="[HIDDEN]")
        assert result["password"] == "[HIDDEN]"

    def test_redact_secrets_original_unchanged(self) -> None:
        """Test that original config is not modified."""
        config = {"password": "secret"}
        ConfigMerger.redact_secrets(config)
        assert config["password"] == "secret"
