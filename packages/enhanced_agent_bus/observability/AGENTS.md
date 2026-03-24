# Observability

> Scope: `packages/enhanced_agent_bus/observability/` — metrics, structured logging, telemetry,
> and timeout budgeting.

## Structure

- `prometheus_metrics.py`: Prometheus-facing metrics
- `structured_logging.py`: structured logging helpers
- `telemetry.py`: telemetry integration
- `timeout_budget.py`: timeout/deadline budgeting
- `batch_metrics.py`, `decorators.py`: metrics helpers and wrappers
- `capacity_metrics/`: capacity collectors, models, trackers, compatibility helpers

## Where to Look

| Task | Location |
| ---- | -------- |
| Add metric | `prometheus_metrics.py`, `batch_metrics.py` |
| Structured log event | `structured_logging.py` |
| Telemetry integration | `telemetry.py` |
| Timeout propagation | `timeout_budget.py` |
| Capacity planning/measurement | `capacity_metrics/` |

## Conventions

- Keep observability non-blocking in hot paths.
- Reuse shared metric/logging definitions where they already exist.

## Anti-Patterns

- Do not use `print()` in production paths.
- Do not let observability failures take down request processing.
