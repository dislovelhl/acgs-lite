# Agent Health & Healing

Constitutional Hash: `608508a9bd224290`

## Overview

The `agent_health` sub-package provides health monitoring, anomaly detection, and autonomous
healing capabilities for agents running on the Enhanced Agent Bus. It consists of:

- **`AgentHealthMonitor`** — a background asyncio Task that polls memory usage, tracks failure
  counts, emits Prometheus metrics, and publishes health events to the `HealingEngine`. Runs in
  an isolated asyncio task so monitoring survives a blocked processing loop (NFR-004).
- **`HealingEngine`** — receives detected health conditions, validates the constitutional hash,
  writes an audit log entry before executing, then dispatches the appropriate action based on the
  agent's Autonomy Tier.
- **`FailureLoopDetector`** / **`MemoryExhaustionDetector`** — pure stateful detector classes
  (no I/O). Used by the monitor to identify degradation conditions.
- **Action executors** (`actions.py`) — `GracefulRestarter`, `QuarantineManager`,
  `HITLRequestor`, `SupervisorNotifier`.
- **`AgentHealthStore`** — async Redis-backed store for `AgentHealthRecord`,
  `HealingAction` history, and `HealingOverride`.
- **REST API** (`api/routes/agent_health.py`) — three FastAPI endpoints mounted under
  `/api/v1/agents/{agent_id}/health/`.

## Configuration

All thresholds are declared in `AgentHealthThresholds` (see `models.py`):

| Field | Default | Valid Range | Description |
|---|---|---|---|
| `failure_count_threshold` | `5` | `>= 1` | Consecutive failures within the window before a loop is detected |
| `failure_window_seconds` | `60` | `>= 10` | Sliding window duration (seconds) for the failure loop detector |
| `memory_exhaustion_pct` | `85.0` | `50.0–99.0` | Memory usage percentage that triggers the memory exhaustion detector |
| `memory_hysteresis_pct` | `10.0` | `1.0–30.0` | Hysteresis clearance: memory must drop to `exhaustion_pct - hysteresis_pct` before the exhausted flag clears (prevents flapping) |
| `drain_timeout_seconds` | `30` | `>= 5` | Seconds to wait for in-flight messages to drain before forcing re-queue on graceful restart |
| `metric_emit_interval_seconds` | `10` | `>= 5` | Interval between Prometheus metric emissions from the background monitor task |

### Per-Agent Override

Pass a customised `AgentHealthThresholds` instance at monitor startup:

```python
from packages.enhanced_agent_bus.agent_health.models import AgentHealthThresholds

thresholds = AgentHealthThresholds(
    failure_count_threshold=3,
    failure_window_seconds=30,
    memory_exhaustion_pct=90.0,
)
```

## Integration Guide

### Starting the AgentHealthMonitor

```python
import asyncio
from redis.asyncio import Redis
from packages.enhanced_agent_bus.agent_health.monitor import AgentHealthMonitor
from packages.enhanced_agent_bus.agent_health.models import (
    AgentHealthThresholds,
    AutonomyTier,
)
from packages.enhanced_agent_bus.agent_health.store import AgentHealthStore

redis = Redis.from_url("redis://localhost:6379")
store = AgentHealthStore(redis=redis)
thresholds = AgentHealthThresholds()

monitor = AgentHealthMonitor(
    agent_id="my-agent-001",
    autonomy_tier=AutonomyTier.HUMAN_APPROVED,  # Tier 3 — self-restart
    store=store,
    thresholds=thresholds,
)

# Start the isolated monitoring loop (returns immediately; runs as asyncio.Task)
task = await monitor.start()

# Record events from your message processing loop:
try:
    result = await process_message(msg)
    await monitor.record_success()
except Exception:
    await monitor.record_failure(error_type="ProcessingError")

# On shutdown:
await monitor.stop()
```

### Mounting the API Router

```python
from fastapi import FastAPI
from packages.enhanced_agent_bus.api.routes.agent_health import router as health_router

app = FastAPI()

# Provide the store via app.state (set before the router handles requests):
app.state.agent_health_store = store

app.include_router(health_router)
```

## API Reference

All three endpoints require `Authorization: Bearer <token>` with the `operator` role.

### GET `/api/v1/agents/{agent_id}/health`

Returns the current health snapshot for an agent.

**Response 200:**
```json
{
  "agent_id": "my-agent-001",
  "health_state": "HEALTHY",
  "consecutive_failure_count": 0,
  "memory_usage_pct": 42.3,
  "last_error_type": null,
  "last_event_at": "2026-03-05T10:00:00Z",
  "autonomy_tier": "HUMAN_APPROVED",
  "healing_override": null,
  "constitutional_hash": "608508a9bd224290"
}
```

**Errors:** `401` (missing/invalid token), `403` (not operator), `404` (unknown agent).

---

### POST `/api/v1/agents/{agent_id}/health/override`

Creates an operator override to suppress or force a healing action. Written to the audit log
before taking effect (FR-008).

**Request body:**
```json
{
  "mode": "SUPPRESS_HEALING",
  "reason": "Investigating agent state — do not restart",
  "expires_at": "2026-03-05T12:00:00Z"
}
```

Valid `mode` values: `SUPPRESS_HEALING`, `FORCE_RESTART`, `FORCE_QUARANTINE`.

**Response 201:**
```json
{
  "override_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "agent_id": "my-agent-001",
  "mode": "SUPPRESS_HEALING",
  "issued_by": "operator@example.com",
  "issued_at": "2026-03-05T10:00:00Z",
  "expires_at": "2026-03-05T12:00:00Z",
  "audit_event_id": "evt-abc123"
}
```

**Errors:** `400` (invalid mode/reason/expiry), `401`, `403`, `404`, `409` (override already active).

---

### DELETE `/api/v1/agents/{agent_id}/health/override`

Removes the active healing override, restoring automatic healing. Written to the audit log.

**Response:** `204 No Content`

**Errors:** `401`, `403`, `404` (no active override for agent).

---

## Autonomy Tier → Healing Action Mapping

| Autonomy Tier | Value | Detected Condition | Healing Action |
|---|---|---|---|
| ADVISORY (Tier 1) | `ADVISORY` | Failure loop | Quarantine + HITL review request |
| ADVISORY (Tier 1) | `ADVISORY` | Memory exhaustion | Quarantine + HITL review request |
| BOUNDED (Tier 2) | `BOUNDED` | Failure loop | Supervisor notification + await approval (escalates after SLA) |
| BOUNDED (Tier 2) | `BOUNDED` | Memory exhaustion | Supervisor notification + await approval |
| HUMAN_APPROVED (Tier 3) | `HUMAN_APPROVED` | Failure loop | Graceful self-restart (drain in-flight messages, then restart) |
| HUMAN_APPROVED (Tier 3) | `HUMAN_APPROVED` | Memory exhaustion | Graceful self-restart |

All healing decisions are written to the governance audit log **before** the action executes
(constitutional constraint). No healing action bypasses constitutional hash validation
(`608508a9bd224290`).

## Prometheus Metrics

All metrics are labelled with `agent_id` and `autonomy_tier`.

| Metric | Type | Labels | Description |
|---|---|---|---|
| `acgs_agent_health_state` | Gauge | `agent_id`, `autonomy_tier`, `health_state` | Current health state (1 = active state, 0 = inactive) |
| `acgs_agent_consecutive_failures` | Gauge | `agent_id`, `autonomy_tier` | Current consecutive failure count |
| `acgs_agent_memory_usage_pct` | Gauge | `agent_id`, `autonomy_tier` | Memory usage as a percentage of the agent's declared limit |
| `acgs_agent_healing_actions_total` | Counter | `agent_id`, `autonomy_tier`, `action_type` | Total healing actions executed, by type |

Metrics are emitted at `metric_emit_interval_seconds` intervals (default 10 s) by the
background monitor task and scraped by the existing Prometheus endpoint in the Agent Bus.
