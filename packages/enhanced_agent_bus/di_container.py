"""
Dependency Injection Container for ACGS-2 MetaOrchestrator.

Constitutional Hash: 608508a9bd224290

Provides lightweight DI for coordinator wiring without heavy frameworks.
This module implements a simple but effective dependency injection pattern
that allows for loose coupling between components and easier testing.

Example:
    Basic usage with the default container::

        container = get_container()
        memory_coord = container.resolve(MemoryCoordinator)

    Custom container with manual registration::

        container = DIContainer()
        container.register(MyService, factory=lambda: MyService(config))
        service = container.resolve(MyService)
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TypeVar

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)
T = TypeVar("T")


@dataclass
class ServiceDescriptor:
    """Describes a service registration within the DI container.

    Holds metadata about how a service should be instantiated, including
    its type, optional factory function, cached instance, and lifecycle.

    Attributes:
        service_type: The type/class of the service being registered.
        factory: Optional callable that creates new instances of the service.
            If None and no instance is provided, the service_type itself is used.
        instance: Optional pre-created instance of the service. If provided,
            this instance is returned directly on resolution.
        singleton: If True, only one instance is created and reused for all
            subsequent resolutions. Defaults to True.
    """

    service_type: type[object]
    factory: Callable[..., object] | None = None
    instance: object | None = None
    singleton: bool = True


@dataclass
class DIContainer:
    """Lightweight Dependency Injection container for ACGS-2 components.

    Manages service registrations and resolutions, supporting singleton and
    transient lifecycles. Thread-safety is the caller's responsibility.

    Attributes:
        constitutional_hash: The constitutional hash for verification.
        _services: Internal registry mapping service types to their descriptors.
        _initialized: Flag indicating if the container has been initialized.

    Example:
        >>> container = DIContainer()
        >>> container.register(MyService, factory=lambda: MyService("config"))
        >>> service = container.resolve(MyService)
    """

    constitutional_hash: str = CONSTITUTIONAL_HASH
    _services: dict[type[object], ServiceDescriptor] = field(default_factory=dict)
    _initialized: bool = False

    def register(
        self,
        service_type: type[T],
        factory: Callable[..., T] | None = None,
        instance: T | None = None,
        singleton: bool = True,
    ) -> DIContainer:
        """Register a service type with the container.

        Adds a service to the container's registry. Services can be registered
        with a pre-created instance, a factory function, or just the type itself
        (which will be instantiated directly when resolved).

        Args:
            service_type: The type/class to register. This is used as the key
                for later resolution.
            factory: Optional callable that returns a new instance of the service.
                If not provided and no instance is given, service_type() is called.
            instance: Optional pre-created instance to use. If provided, this
                exact instance is returned on every resolve() call.
            singleton: If True (default), only one instance is created and cached.
                If False, a new instance is created on each resolve() call.

        Returns:
            Self reference to allow method chaining.

        Example:
            >>> container = DIContainer()
            >>> container.register(ConfigService, instance=config)
            >>> container.register(DataService, factory=lambda: DataService(db))
            >>> container.register(SimpleService)  # Uses SimpleService() directly
        """
        if instance is not None:
            self._services[service_type] = ServiceDescriptor(
                service_type=service_type,
                instance=instance,
                singleton=True,
            )
        elif factory is not None:
            self._services[service_type] = ServiceDescriptor(
                service_type=service_type,
                factory=factory,
                singleton=singleton,
            )
        else:
            self._services[service_type] = ServiceDescriptor(
                service_type=service_type,
                factory=service_type,
                singleton=singleton,
            )
        return self

    def resolve(self, service_type: type[T]) -> T:
        """Resolve and return an instance of the requested service type.

        Looks up the service in the registry and returns an instance. For
        singletons, the same instance is returned on subsequent calls. For
        transient services, a new instance is created each time.

        Args:
            service_type: The type/class to resolve. Must have been previously
                registered with register().

        Returns:
            An instance of the requested service type.

        Raises:
            KeyError: If the service type has not been registered.
            ValueError: If the service has no factory and no instance available.

        Example:
            >>> container = DIContainer()
            >>> container.register(MyService, factory=lambda: MyService())
            >>> service = container.resolve(MyService)
        """
        if service_type not in self._services:
            raise KeyError(f"Service {service_type.__name__} not registered")

        descriptor = self._services[service_type]

        if descriptor.instance is not None:
            return descriptor.instance

        if descriptor.factory is None:
            raise ValueError(f"No factory for {service_type.__name__}")

        instance = descriptor.factory()

        if descriptor.singleton:
            descriptor.instance = instance

        return instance

    def try_resolve(self, service_type: type[T]) -> T | None:
        """Attempt to resolve a service, returning None on failure.

        A safe version of resolve() that catches resolution errors and
        returns None instead of raising exceptions. Useful when a service
        may or may not be registered.

        Args:
            service_type: The type/class to resolve.

        Returns:
            An instance of the requested service type, or None if the service
            is not registered or cannot be resolved.

        Example:
            >>> container = DIContainer()
            >>> service = container.try_resolve(OptionalService)
            >>> if service is not None:
            ...     service.do_something()
        """
        try:
            return self.resolve(service_type)
        except (KeyError, ValueError):
            return None

    def is_registered(self, service_type: type[object]) -> bool:
        """Check if a service type has been registered.

        Args:
            service_type: The type/class to check for registration.

        Returns:
            True if the service type is registered, False otherwise.

        Example:
            >>> container = DIContainer()
            >>> container.register(MyService)
            >>> container.is_registered(MyService)
            True
            >>> container.is_registered(OtherService)
            False
        """
        return service_type in self._services

    def get_registered_services(self) -> dict[str, bool]:
        """Get a summary of all registered services and their instantiation state.

        Returns:
            A dictionary mapping service class names to boolean values indicating
            whether an instance has been created (True) or not yet (False).

        Example:
            >>> container = DIContainer()
            >>> container.register(ServiceA)
            >>> container.register(ServiceB, instance=ServiceB())
            >>> container.get_registered_services()
            {'ServiceA': False, 'ServiceB': True}
        """
        return {svc.__name__: desc.instance is not None for svc, desc in self._services.items()}


def create_default_container() -> DIContainer:
    """Create and configure a DIContainer with all default ACGS-2 coordinators.

    Instantiates a new container and registers all standard coordinator types
    with their default configurations. This is the primary way to get a
    fully-configured container for production use.

    Returns:
        A new DIContainer instance with the following coordinators registered:
            - MemoryCoordinator (persistence enabled)
            - SwarmCoordinator (max 10 agents)
            - WorkflowCoordinator (evolution enabled)
            - ResearchCoordinator
            - MACICoordinator (strict mode)

    Example:
        >>> container = create_default_container()
        >>> memory = container.resolve(MemoryCoordinator)
    """
    from .coordinators import (
        MACICoordinator,
        MemoryCoordinator,
        ResearchCoordinator,
        SwarmCoordinator,
        WorkflowCoordinator,
    )

    container = DIContainer()

    container.register(MemoryCoordinator, lambda: MemoryCoordinator(persistence_enabled=True))
    container.register(SwarmCoordinator, lambda: SwarmCoordinator(max_agents=10))
    container.register(WorkflowCoordinator, lambda: WorkflowCoordinator(enable_evolution=True))
    container.register(ResearchCoordinator, lambda: ResearchCoordinator())
    container.register(MACICoordinator, lambda: MACICoordinator(strict_mode=True))

    logger.info(f"[{CONSTITUTIONAL_HASH}] DI container initialized with default coordinators")
    return container


_default_container: DIContainer | None = None


def get_container() -> DIContainer:
    """Get or create the global default DI container.

    Returns the singleton default container, creating it via
    create_default_container() on first access. Subsequent calls
    return the same container instance.

    Returns:
        The global DIContainer instance with all default coordinators registered.

    Example:
        >>> container = get_container()
        >>> coordinator = container.resolve(MemoryCoordinator)

    Note:
        Use reset_container() to clear the global container and force
        re-creation on the next get_container() call.
    """
    global _default_container
    if _default_container is None:
        _default_container = create_default_container()
    return _default_container


def reset_container() -> None:
    """Reset the global default container to None.

    Clears the cached global container, causing the next call to
    get_container() to create a fresh instance. Useful for testing
    or when you need to reinitialize all coordinators.

    Example:
        >>> reset_container()  # Clear existing container
        >>> container = get_container()  # Fresh container created

    Warning:
        All references to services resolved from the previous container
        will still point to the old instances. This only affects future
        get_container() calls.
    """
    global _default_container
    _default_container = None
