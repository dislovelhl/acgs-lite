"""
Dependency Injection Container for ACGS-2.

Constitutional Hash: cdd01ef066bc6cf2
"""

from typing import ClassVar, TypeVar, cast

from src.core.shared.structured_logging import get_logger

T = TypeVar("T")

logger = get_logger(__name__)


class DIContainer:
    """
    Centralized Dependency Injection container for ACGS-2 services.

    Manages singleton lifecycles and provides unified access to core components.
    Constitutional Hash: cdd01ef066bc6cf2
    """

    _instance: ClassVar["DIContainer | None"] = None
    _services: ClassVar[dict[type[object], object]] = {}
    _named_services: ClassVar[dict[str, object]] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def register(cls, service_type: type[T], instance: T) -> None:
        """Register a service instance for a given type."""
        cls._services[service_type] = instance
        logger.debug(f"Registered service: {service_type.__name__}")

    @classmethod
    def register_named(cls, name: str, instance: object) -> None:
        """Register a named service instance."""
        cls._named_services[name] = instance
        logger.debug(f"Registered named service: {name}")

    @classmethod
    def get(cls, service_type: type[T]) -> T:
        """Retrieve a service by its type."""
        if service_type not in cls._services:
            raise KeyError(f"Service not registered: {service_type.__name__}")
        return cast(T, cls._services[service_type])

    @classmethod
    def get_named(cls, name: str) -> object:
        """Retrieve a named service."""
        if name not in cls._named_services:
            raise KeyError(f"Named service not registered: {name}")
        return cls._named_services[name]

    @classmethod
    def reset(cls) -> None:
        """Reset the container (for testing)."""
        cls._services.clear()
        cls._named_services.clear()

    # Convenience accessors for core services
    @classmethod
    def get_identity_provider(cls) -> object:
        """Retrieve the identity provider service."""
        return cls.get_named("identity_provider")

    @classmethod
    def get_metering_service(cls) -> object:
        """Retrieve the metering service."""
        return cls.get_named("metering_service")

    @classmethod
    def get_policy_service(cls) -> object:
        """Retrieve the policy service."""
        return cls.get_named("policy_service")


def inject(service_type: type[T]) -> T:
    """Helper for dependency injection."""
    return DIContainer.get(service_type)


def inject_named(name: str) -> object:
    """Helper for named dependency injection."""
    return DIContainer.get_named(name)
