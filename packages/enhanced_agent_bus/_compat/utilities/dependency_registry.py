"""Shim for src.core.shared.utilities.dependency_registry."""
from __future__ import annotations

from typing import Any, ClassVar

try:
    from src.core.shared.utilities.dependency_registry import *  # noqa: F403
    from src.core.shared.utilities.dependency_registry import DependencyRegistry, FeatureFlag
except ImportError:
    from enum import Enum, auto

    class FeatureFlag(Enum):
        METRICS = auto()
        OTEL = auto()
        AUDIT = auto()
        REDIS = auto()
        KAFKA = auto()
        OPA = auto()
        MACI = auto()
        DELIBERATION = auto()
        CIRCUIT_BREAKER = auto()
        CRYPTO = auto()
        PQC = auto()
        CACHING = auto()
        PERSISTENCE = auto()
        SWARM = auto()
        LANGGRAPH = auto()
        CONTEXT_MEMORY = auto()
        RUST = auto()
        METERING = auto()
        LLM = auto()
        IMPACT_SCORER = auto()

    class DependencyRegistry:
        """Standalone stub for the centralized dependency registry."""

        _dependencies: ClassVar[dict[str, Any]] = {}
        _feature_status: ClassVar[dict[FeatureFlag, bool]] = {}
        _initialized: bool = False

        @classmethod
        def register(cls, name: str, module_path: str = "", import_name: str = "",
                     feature_flag: FeatureFlag | None = None, fallback_paths: list[str] | None = None,
                     factory: Any = None, singleton: bool = False) -> None:
            cls._dependencies[name] = {
                "name": name, "module_path": module_path, "import_name": import_name,
                "feature_flag": feature_flag, "factory": factory, "singleton": singleton,
            }

        @classmethod
        def get(cls, name: str, default: Any = None, create: bool = True) -> Any:
            dep = cls._dependencies.get(name)
            if dep and create and dep.get("factory"):
                return dep["factory"]()
            return default

        @classmethod
        def resolve(cls, name: str) -> Any:
            return cls.get(name)

        @classmethod
        def is_available(cls, feature: FeatureFlag) -> bool:
            return cls._feature_status.get(feature, False)

        @classmethod
        def set_available(cls, feature: FeatureFlag, available: bool = True) -> None:
            cls._feature_status[feature] = available

        @classmethod
        def has(cls, name: str) -> bool:
            return name in cls._dependencies

        @classmethod
        def clear(cls) -> None:
            cls._dependencies.clear()
            cls._feature_status.clear()
            cls._initialized = False

        @classmethod
        def all(cls) -> dict[str, Any]:
            return dict(cls._dependencies)

        @classmethod
        def initialize_defaults(cls) -> None:
            """No-op in standalone mode — monorepo registers real defaults."""
            cls._initialized = True

        @classmethod
        def get_status_report(cls) -> dict[str, Any]:
            return {
                "initialized": cls._initialized,
                "dependencies": len(cls._dependencies),
                "features": {f.name: v for f, v in cls._feature_status.items()},
            }

    _registry: DependencyRegistry | None = None

    def get_dependency_registry() -> DependencyRegistry:
        global _registry  # noqa: PLW0603
        if _registry is None:
            _registry = DependencyRegistry()
        return _registry
