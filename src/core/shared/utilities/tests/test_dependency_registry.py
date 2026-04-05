"""
Tests for DependencyRegistry utility.
Constitutional Hash: 608508a9bd224290
"""

import pytest

from src.core.shared.errors.exceptions import ServiceUnavailableError
from src.core.shared.utilities import DependencyRegistry, FeatureFlag


@pytest.fixture(autouse=True)
def reset_registry() -> None:
    """Reset the registry before each test."""
    DependencyRegistry.reset()
    yield
    DependencyRegistry.reset()


class TestFeatureFlag:
    """Test FeatureFlag enum."""

    def test_feature_flags_exist(self) -> None:
        """Test that expected feature flags exist."""
        assert hasattr(FeatureFlag, "METRICS")
        assert hasattr(FeatureFlag, "REDIS")
        assert hasattr(FeatureFlag, "OPA")
        assert hasattr(FeatureFlag, "MACI")


class TestDependencyRegistryRegister:
    """Test DependencyRegistry.register() method."""

    def test_register_basic(self) -> None:
        """Test basic dependency registration."""
        DependencyRegistry.register(
            name="test_dep",
            module_path="json",
            import_name="loads",
            feature_flag=FeatureFlag.METRICS,
        )
        assert "test_dep" in DependencyRegistry._dependencies

    def test_register_with_fallback(self) -> None:
        """Test registration with fallback paths."""
        DependencyRegistry.register(
            name="test_dep",
            module_path="nonexistent.module",
            import_name="Something",
            feature_flag=FeatureFlag.REDIS,
            fallback_paths=["json"],
        )
        assert DependencyRegistry._dependencies["test_dep"].fallback_paths == ["json"]


class TestDependencyRegistryGet:
    """Test DependencyRegistry.get() method."""

    def test_get_available_dependency(self) -> None:
        """Test getting an available dependency."""
        DependencyRegistry.register(
            name="json_loads",
            module_path="json",
            import_name="loads",
            feature_flag=FeatureFlag.METRICS,
        )
        result = DependencyRegistry.get("json_loads")
        assert result is not None
        # Verify it's actually json.loads
        assert result('{"a": 1}') == {"a": 1}

    def test_get_unavailable_dependency(self) -> None:
        """Test getting an unavailable dependency returns default."""
        DependencyRegistry.register(
            name="nonexistent",
            module_path="nonexistent.module",
            import_name="Something",
            feature_flag=FeatureFlag.REDIS,
        )
        result = DependencyRegistry.get("nonexistent", default="fallback")
        assert result == "fallback"

    def test_get_unknown_dependency(self) -> None:
        """Test getting an unregistered dependency returns default."""
        result = DependencyRegistry.get("unknown", default="fallback")
        assert result == "fallback"

    def test_get_with_fallback_path(self) -> None:
        """Test getting dependency that uses fallback path."""
        DependencyRegistry.register(
            name="fallback_dep",
            module_path="nonexistent.module",
            import_name="dumps",
            feature_flag=FeatureFlag.METRICS,
            fallback_paths=["json"],
        )
        result = DependencyRegistry.get("fallback_dep")
        assert result is not None
        # Should be json.dumps from fallback
        assert result({"a": 1}) == '{"a": 1}'


class TestDependencyRegistryIsAvailable:
    """Test DependencyRegistry.is_available() method."""

    def test_is_available_true(self) -> None:
        """Test feature is available when dependency loads."""
        DependencyRegistry.register(
            name="json_dep",
            module_path="json",
            import_name="loads",
            feature_flag=FeatureFlag.METRICS,
        )
        assert DependencyRegistry.is_available(FeatureFlag.METRICS) is True

    def test_is_available_false(self) -> None:
        """Test feature is unavailable when dependency fails."""
        DependencyRegistry.register(
            name="missing_dep",
            module_path="nonexistent.module",
            import_name="Something",
            feature_flag=FeatureFlag.RUST,
        )
        assert DependencyRegistry.is_available(FeatureFlag.RUST) is False

    def test_is_available_unknown_feature(self) -> None:
        """Test unknown feature returns False."""
        assert DependencyRegistry.is_available(FeatureFlag.PQC) is False


class TestDependencyRegistryRequire:
    """Test DependencyRegistry.require() method."""

    def test_require_available(self) -> None:
        """Test require succeeds for available feature."""
        DependencyRegistry.register(
            name="json_dep",
            module_path="json",
            import_name="loads",
            feature_flag=FeatureFlag.METRICS,
        )
        # Should not raise
        DependencyRegistry.require(FeatureFlag.METRICS)

    def test_require_unavailable(self) -> None:
        """Test require raises for unavailable feature."""
        DependencyRegistry.register(
            name="missing_dep",
            module_path="nonexistent.module",
            import_name="Something",
            feature_flag=FeatureFlag.RUST,
        )
        with pytest.raises(ServiceUnavailableError) as exc_info:
            DependencyRegistry.require(FeatureFlag.RUST)
        assert "RUST" in str(exc_info.value)


class TestDependencyRegistryGetStatus:
    """Test DependencyRegistry.get_status() method."""

    def test_get_status_structure(self) -> None:
        """Test status has expected structure."""
        DependencyRegistry.register(
            name="json_dep",
            module_path="json",
            import_name="loads",
            feature_flag=FeatureFlag.METRICS,
        )
        status = DependencyRegistry.get_status()
        assert "features" in status
        assert "dependencies" in status
        assert "available_features" in status
        assert "missing_features" in status

    def test_get_status_shows_availability(self) -> None:
        """Test status correctly shows dependency availability."""
        DependencyRegistry.register(
            name="json_dep",
            module_path="json",
            import_name="loads",
            feature_flag=FeatureFlag.METRICS,
        )
        DependencyRegistry.register(
            name="missing_dep",
            module_path="nonexistent.module",
            import_name="Something",
            feature_flag=FeatureFlag.RUST,
        )
        status = DependencyRegistry.get_status()
        assert status["dependencies"]["json_dep"]["available"] is True
        assert status["dependencies"]["missing_dep"]["available"] is False


class TestDependencyRegistryInitializeDefaults:
    """Test DependencyRegistry.initialize_defaults() method."""

    def test_initialize_defaults(self) -> None:
        """Test default dependencies are registered."""
        DependencyRegistry.initialize_defaults()
        assert "prometheus_counter" in DependencyRegistry._dependencies
        assert "otel_tracer" in DependencyRegistry._dependencies
        assert "redis_client" in DependencyRegistry._dependencies

    def test_initialize_defaults_idempotent(self) -> None:
        """Test initialize_defaults can be called multiple times."""
        DependencyRegistry.initialize_defaults()
        # Should not raise


class TestDependencyRegistrySingleton:
    """Test singleton behavior."""

    def test_singleton_returns_same_instance(self) -> None:
        """Test singleton dependency returns same instance."""
        DependencyRegistry.register(
            name="singleton_dep",
            module_path="json",
            import_name="loads",
            feature_flag=FeatureFlag.METRICS,
            singleton=True,
        )
        instance1 = DependencyRegistry.get("singleton_dep")
        instance2 = DependencyRegistry.get("singleton_dep")
        assert instance1 is instance2

    def test_non_singleton_returns_import(self) -> None:
        """Test non-singleton returns the imported object."""
        DependencyRegistry.register(
            name="non_singleton",
            module_path="json",
            import_name="loads",
            feature_flag=FeatureFlag.METRICS,
            singleton=False,
        )
        # Without factory, should return the imported function
        result = DependencyRegistry.get("non_singleton", create=False)
        import json

        assert result is json.loads
