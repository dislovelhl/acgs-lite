"""
ACGS-2 Architecture Fixtures
Constitutional Hash: 608508a9bd224290

Fixtures for architectural layer testing and context management.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

import pytest

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]


class ArchitecturalLayer(Enum):
    """ACGS-2 architectural layers."""

    LAYER1_VALIDATION = "layer1_validation"
    LAYER2_DELIBERATION = "layer2_deliberation"
    LAYER3_POLICY = "layer3_policy"
    LAYER4_AUDIT = "layer4_audit"


class ComponentState(Enum):
    """State of an architectural component."""

    UNINITIALIZED = "uninitialized"
    INITIALIZING = "initializing"
    READY = "ready"
    DEGRADED = "degraded"
    FAILED = "failed"
    SHUTTING_DOWN = "shutting_down"
    SHUTDOWN = "shutdown"


@dataclass
class LayerConfig:
    """Configuration for an architectural layer."""

    layer: ArchitecturalLayer
    timeout_budget_ms: float
    enabled: bool = True
    strict_enforcement: bool = True
    fallback_enabled: bool = True
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        return {
            "layer": self.layer.value,
            "timeout_budget_ms": self.timeout_budget_ms,
            "enabled": self.enabled,
            "strict_enforcement": self.strict_enforcement,
            "fallback_enabled": self.fallback_enabled,
            "constitutional_hash": self.constitutional_hash,
        }


@dataclass
class ComponentInfo:
    """Information about an architectural component."""

    name: str
    layer: ArchitecturalLayer
    state: ComponentState = ComponentState.UNINITIALIZED
    version: str = "1.0.0"
    dependencies: set[str] = field(default_factory=set)
    metadata: JSONDict = field(default_factory=dict)
    last_health_check: datetime | None = None
    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass
class LayerTransition:
    """Record of a layer transition."""

    from_layer: ArchitecturalLayer
    to_layer: ArchitecturalLayer
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    duration_ms: float = 0.0
    success: bool = True
    message: str = ""
    constitutional_hash: str = CONSTITUTIONAL_HASH


class SpecLayerContext:
    """
    Context manager for a specific architectural layer.

    Provides layer-specific configuration and state tracking.
    """

    def __init__(
        self,
        layer: ArchitecturalLayer,
        config: LayerConfig | None = None,
    ):
        self.layer = layer
        self.config = config or LayerConfig(
            layer=layer,
            timeout_budget_ms=self._default_budget(layer),
        )
        self.components: dict[str, ComponentInfo] = {}
        self.is_active = False
        self.entry_time: datetime | None = None
        self.exit_time: datetime | None = None
        self.constitutional_hash = CONSTITUTIONAL_HASH

    @staticmethod
    def _default_budget(layer: ArchitecturalLayer) -> float:
        """Get default timeout budget for a layer."""
        budgets = {
            ArchitecturalLayer.LAYER1_VALIDATION: 5.0,
            ArchitecturalLayer.LAYER2_DELIBERATION: 20.0,
            ArchitecturalLayer.LAYER3_POLICY: 10.0,
            ArchitecturalLayer.LAYER4_AUDIT: 15.0,
        }
        return budgets.get(layer, 10.0)

    def enter(self) -> "SpecLayerContext":
        """Enter the layer context."""
        self.is_active = True
        self.entry_time = datetime.now(UTC)
        return self

    def exit(self) -> float:
        """
        Exit the layer context.

        Returns:
            Duration in milliseconds spent in the layer
        """
        self.is_active = False
        self.exit_time = datetime.now(UTC)

        if self.entry_time:
            duration_ms = (self.exit_time - self.entry_time).total_seconds() * 1000
            return duration_ms
        return 0.0

    def register_component(
        self,
        name: str,
        version: str = "1.0.0",
        dependencies: set[str] | None = None,
    ) -> ComponentInfo:
        """Register a component in this layer."""
        component = ComponentInfo(
            name=name,
            layer=self.layer,
            version=version,
            dependencies=dependencies or set(),
        )
        self.components[name] = component
        return component

    def update_component_state(
        self,
        name: str,
        state: ComponentState,
    ) -> ComponentInfo | None:
        """Update a component's state."""
        if name in self.components:
            self.components[name].state = state
            self.components[name].last_health_check = datetime.now(UTC)
            return self.components[name]
        return None

    def get_component(self, name: str) -> ComponentInfo | None:
        """Get a component by name."""
        return self.components.get(name)

    def is_healthy(self) -> bool:
        """Check if all components in the layer are healthy."""
        for component in self.components.values():
            if component.state in (ComponentState.FAILED, ComponentState.DEGRADED):
                return False
        return True

    def get_ready_components(self) -> list[ComponentInfo]:
        """Get all ready components."""
        return [c for c in self.components.values() if c.state == ComponentState.READY]


class SpecArchitectureContext:
    """
    Full architecture context for specification testing.

    Manages all layers and cross-layer coordination.
    """

    def __init__(self):
        self.layers: dict[ArchitecturalLayer, SpecLayerContext] = {}
        self.transitions: list[LayerTransition] = []
        self.current_layer: ArchitecturalLayer | None = None
        self.constitutional_hash = CONSTITUTIONAL_HASH

        # Initialize all layers with default configs
        for layer in ArchitecturalLayer:
            self.layers[layer] = SpecLayerContext(layer)

    def get_layer(self, layer: ArchitecturalLayer) -> SpecLayerContext:
        """Get the context for a specific layer."""
        return self.layers[layer]

    def enter_layer(self, layer: ArchitecturalLayer) -> SpecLayerContext:
        """
        Enter a specific layer.

        Args:
            layer: The layer to enter

        Returns:
            The layer context
        """
        # Exit current layer if active
        if self.current_layer and self.current_layer != layer:
            self.exit_layer()

        layer_ctx = self.layers[layer]
        layer_ctx.enter()
        self.current_layer = layer
        return layer_ctx

    def exit_layer(self) -> LayerTransition | None:
        """
        Exit the current layer.

        Returns:
            LayerTransition record if a layer was active
        """
        if not self.current_layer:
            return None

        layer_ctx = self.layers[self.current_layer]
        duration_ms = layer_ctx.exit()

        transition = LayerTransition(
            from_layer=self.current_layer,
            to_layer=self.current_layer,  # Will be updated on next enter
            duration_ms=duration_ms,
            success=layer_ctx.is_healthy(),
        )
        self.transitions.append(transition)

        prev_layer = self.current_layer
        self.current_layer = None

        return transition

    def transition_to(
        self,
        target_layer: ArchitecturalLayer,
    ) -> LayerTransition:
        """
        Transition from current layer to target layer.

        Args:
            target_layer: The layer to transition to

        Returns:
            LayerTransition record
        """
        from_layer = self.current_layer

        # Exit current layer
        if from_layer:
            prev_ctx = self.layers[from_layer]
            duration_ms = prev_ctx.exit()
        else:
            duration_ms = 0.0
            from_layer = target_layer

        # Enter target layer
        target_ctx = self.layers[target_layer]
        target_ctx.enter()
        self.current_layer = target_layer

        transition = LayerTransition(
            from_layer=from_layer,
            to_layer=target_layer,
            duration_ms=duration_ms,
            success=True,
        )
        self.transitions.append(transition)

        return transition

    def register_component(
        self,
        layer: ArchitecturalLayer,
        name: str,
        version: str = "1.0.0",
        dependencies: set[str] | None = None,
    ) -> ComponentInfo:
        """Register a component in a specific layer."""
        return self.layers[layer].register_component(name, version, dependencies)

    def get_component(
        self,
        layer: ArchitecturalLayer,
        name: str,
    ) -> ComponentInfo | None:
        """Get a component from a specific layer."""
        return self.layers[layer].get_component(name)

    def get_all_components(self) -> dict[ArchitecturalLayer, list[ComponentInfo]]:
        """Get all components grouped by layer."""
        return {layer: list(ctx.components.values()) for layer, ctx in self.layers.items()}

    def get_health_report(self) -> JSONDict:
        """
        Generate a health report for all layers.

        Returns:
            Health report with layer and component status
        """
        report = {
            "healthy": True,
            "layers": {},
            "total_components": 0,
            "ready_components": 0,
            "constitutional_hash": self.constitutional_hash,
        }

        for layer, ctx in self.layers.items():
            layer_healthy = ctx.is_healthy()
            ready = ctx.get_ready_components()

            report["layers"][layer.value] = {
                "healthy": layer_healthy,
                "component_count": len(ctx.components),
                "ready_count": len(ready),
                "is_active": ctx.is_active,
            }

            report["total_components"] += len(ctx.components)
            report["ready_components"] += len(ready)

            if not layer_healthy:
                report["healthy"] = False

        return report

    def get_transition_history(self) -> list[LayerTransition]:
        """Get all layer transitions."""
        return self.transitions.copy()

    def validate_constitutional_compliance(self) -> bool:
        """Validate constitutional hash across all layers."""
        for _layer, ctx in self.layers.items():
            if ctx.constitutional_hash != CONSTITUTIONAL_HASH:
                return False
            for component in ctx.components.values():
                if component.constitutional_hash != CONSTITUTIONAL_HASH:
                    return False
        return True

    def reset(self) -> None:
        """Reset architecture state."""
        for ctx in self.layers.values():
            ctx.components.clear()
            ctx.is_active = False
            ctx.entry_time = None
            ctx.exit_time = None
        self.transitions.clear()
        self.current_layer = None


@pytest.fixture
def architecture_context() -> SpecArchitectureContext:
    """
    Fixture providing a full architecture context for spec testing.

    Use in tests verifying cross-layer behavior:
        def test_layer_transition(architecture_context):
            ctx = architecture_context
            ctx.enter_layer(ArchitecturalLayer.LAYER1_VALIDATION)
            transition = ctx.transition_to(ArchitecturalLayer.LAYER2_DELIBERATION)
            assert transition.success
    """
    return SpecArchitectureContext()


@pytest.fixture
def layer_context() -> SpecLayerContext:
    """
    Fixture providing a layer context for spec testing.

    Use in tests verifying single-layer behavior:
        def test_component_registration(layer_context):
            ctx = layer_context
            component = ctx.register_component("validator")
            ctx.update_component_state("validator", ComponentState.READY)
            assert ctx.is_healthy()
    """
    return SpecLayerContext(ArchitecturalLayer.LAYER1_VALIDATION)
