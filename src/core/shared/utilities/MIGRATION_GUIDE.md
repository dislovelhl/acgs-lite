# DependencyRegistry Migration Guide

**Constitutional Hash:** `608508a9bd224290`

This guide describes how to migrate from the scattered `try/except ImportError` pattern
to the centralized `DependencyRegistry` pattern.

## Why Migrate?

The codebase currently has 611+ `try/except ImportError` blocks that:

- Create inconsistent error handling across modules
- Make it difficult to track which features are available
- Duplicate code for common optional dependencies
- Complicate testing and mocking

The `DependencyRegistry` provides:

- Single source of truth for optional dependencies
- Consistent feature flag checking
- Lazy loading with caching
- Easy testing through reset/mock capabilities
- Comprehensive status reporting

## Quick Start

### Before (Old Pattern)

```python
# Scattered across many files
try:
    from src.core.shared.metrics import MESSAGE_QUEUE_DEPTH
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False
    MESSAGE_QUEUE_DEPTH = None
```

### After (New Pattern)

```python
from packages.enhanced_agent_bus.dependency_bridge import (
    is_feature_available,
    get_dependency,
)

# Check if feature is available
if is_feature_available("METRICS"):
    MESSAGE_QUEUE_DEPTH = get_dependency("message_queue_depth")
```

## Migration Steps

### Step 1: Update Imports

Replace scattered imports with dependency_bridge imports:

```python
# Old
from packages.enhanced_agent_bus.imports import (
    METRICS_ENABLED,
    MACI_AVAILABLE,
    get_opa_client,
)

# New
from packages.enhanced_agent_bus.dependency_bridge import (
    is_feature_available,
    get_dependency,
    get_feature_flags,
)
```

### Step 2: Replace Flag Checks

Replace direct flag access with function calls:

```python
# Old
if METRICS_ENABLED:
    do_metrics_stuff()

# New
if is_feature_available("METRICS"):
    do_metrics_stuff()
```

### Step 3: Replace Direct References

Replace direct variable references with get_dependency:

```python
# Old
if MESSAGE_QUEUE_DEPTH:
    MESSAGE_QUEUE_DEPTH.inc()

# New
queue_depth = get_dependency("message_queue_depth")
if queue_depth:
    queue_depth.inc()
```

### Step 4: Update Tests

Update test fixtures to use DependencyRegistry.reset():

```python
import pytest
from src.core.shared.utilities import DependencyRegistry

@pytest.fixture(autouse=True)
def reset_registry():
    DependencyRegistry.reset()
    yield
    DependencyRegistry.reset()
```

## Feature Name Mapping

| Feature Name      | Description            |
| ----------------- | ---------------------- |
| `METRICS`         | Prometheus metrics     |
| `OTEL`            | OpenTelemetry tracing  |
| `AUDIT`           | Audit logging          |
| `REDIS`           | Redis client           |
| `KAFKA`           | Kafka messaging        |
| `OPA`             | Open Policy Agent      |
| `MACI`            | MACI enforcement       |
| `DELIBERATION`    | Deliberation layer     |
| `CIRCUIT_BREAKER` | Circuit breaker        |
| `CRYPTO`          | Cryptographic services |
| `PQC`             | Post-quantum crypto    |
| `RUST`            | Rust acceleration      |
| `METERING`        | Usage metering         |
| `LLM`             | LLM assistant          |
| `IMPACT_SCORER`   | Impact scoring         |

## Legacy Name Mapping

For backward compatibility, these legacy names are still supported:

| Legacy Name           | Registry Name         |
| --------------------- | --------------------- |
| `MESSAGE_QUEUE_DEPTH` | `message_queue_depth` |
| `MACIEnforcer`        | `maci_enforcer`       |
| `MACIRole`            | `maci_role`           |
| `OPAClient`           | `opa_client`          |
| `get_circuit_breaker` | `circuit_breaker`     |
| `PolicyClient`        | `policy_client`       |

## Stub Classes

When MACI is unavailable, stub classes are automatically provided:

```python
from packages.enhanced_agent_bus.dependency_bridge import (
    get_maci_enforcer,
    get_maci_role,
    get_maci_role_registry,
)

# Returns real class if available, stub otherwise
enforcer = get_maci_enforcer()
role = get_maci_role()
registry = get_maci_role_registry()
```

## Testing

### Mocking Feature Availability

```python
from unittest.mock import patch
from src.core.shared.utilities import DependencyRegistry, FeatureFlag

def test_with_mocked_feature():
    DependencyRegistry.reset()

    # Register a fake dependency
    DependencyRegistry.register(
        name="test_dep",
        module_path="json",
        import_name="loads",
        feature_flag=FeatureFlag.METRICS,
    )

    # Now is_available(FeatureFlag.METRICS) returns True
    assert DependencyRegistry.is_available(FeatureFlag.METRICS)
```

### Testing Unavailable Features

```python
def test_unavailable_feature():
    DependencyRegistry.reset()

    # Register an unavailable dependency
    DependencyRegistry.register(
        name="unavailable",
        module_path="nonexistent.module",
        import_name="Something",
        feature_flag=FeatureFlag.RUST,
    )

    # is_available returns False
    assert not DependencyRegistry.is_available(FeatureFlag.RUST)
```

## Gradual Migration

You can migrate gradually by:

1. Start using `dependency_bridge` for new code
2. Existing code using `imports.py` will continue to work
3. Update modules one at a time
4. Run tests after each migration

The `imports.py` module now includes deprecation warnings when using
`get_import_status()` to encourage migration.

## Troubleshooting

### Feature Shows as Unavailable

Check if the dependency is registered:

```python
status = DependencyRegistry.get_status()
print(status["dependencies"])
```

### Import Circular Dependencies

Use lazy loading:

```python
def get_my_dependency():
    return get_dependency("my_dep")
```

### Testing Issues

Always reset the registry in fixtures:

```python
@pytest.fixture(autouse=True)
def reset_registry():
    DependencyRegistry.reset()
    DependencyRegistry.initialize_defaults()
    yield
    DependencyRegistry.reset()
```
