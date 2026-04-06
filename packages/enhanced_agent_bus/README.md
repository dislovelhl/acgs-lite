# enhanced-agent-bus

[![PyPI](https://img.shields.io/pypi/v/enhanced-agent-bus)](https://pypi.org/project/enhanced-agent-bus/)
[![Python](https://img.shields.io/pypi/pyversions/enhanced-agent-bus)](https://pypi.org/project/enhanced-agent-bus/)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](https://www.apache.org/licenses/LICENSE-2.0)

**ACGS-2 Enhanced Agent Bus — high-performance multi-tenant agent communication infrastructure with constitutional compliance.**

`enhanced-agent-bus` is a **FastAPI service**, not an importable library. Run it with `uvicorn`; agents and governance dashboards talk to it over HTTP. It provides agent registration, constitutional message routing, MACI enforcement, durable workflow execution, human-in-the-loop deliberation, Z3 formal verification, rate limiting, and Prometheus metrics.

> **Version:** 3.0.2

## Installation and Running

```bash
pip install enhanced-agent-bus
```

Start the service:

```bash
uvicorn enhanced_agent_bus.api.app:app --host 0.0.0.0 --port 8000
```

Or with multiple workers:

```bash
uvicorn enhanced_agent_bus.api.app:app --host 0.0.0.0 --port 8000 --workers 4
```

Requires Python 3.11+. Redis is required for production deployments (rate limiting, deliberation, MACI record storage).

### Docker

A production Dockerfile is included. It builds a Rust optimization kernel in a multi-stage build, then runs the service as a non-root `acgs` user:

```bash
docker build -f enhanced_agent_bus/Dockerfile -t enhanced-agent-bus .
docker run -p 8000:8000 enhanced-agent-bus
```

## API Endpoints

The service mounts 14 core routers:

### Health

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Full health report (bus, Redis, Kafka, circuit breakers) |
| `GET` | `/health/live` | Kubernetes liveness probe |
| `GET` | `/health/ready` | Kubernetes readiness probe |
| `GET` | `/health/startup` | Startup probe |
| `GET` | `/health/redis` | Redis connectivity check |
| `GET` | `/health/kafka` | Kafka connectivity check |

### Messages

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/` | Send a message to the agent bus for constitutional validation and routing |
| `GET` | `/messages/{message_id}` | Retrieve a message by ID |

### Governance & MACI

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/governance/...` | MACI role query and governance state |
| `POST` | `/governance/maci/assign` | Assign a MACI role to an agent |
| `POST` | `/governance/maci/validate` | Validate an agent's action against its MACI role |
| `POST` | `/governance/maci/record` | Record a MACI governance event |
| `POST` | `/governance/maci/review` | Submit a MACI review decision |

### Agent Health

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/agents` | List registered agents and their health |
| `POST` | `/api/v1/agents` | Register an agent |
| `DELETE` | `/api/v1/agents/{agent_id}` | Deregister an agent |

### Policies

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/policies` | Load or update governance policies |

### Batch Processing

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/batch` | Submit a batch of messages for concurrent constitutional validation |

### Workflows (durable saga execution)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/workflows` | Create a durable workflow |
| `GET` | `/workflows` | List workflows |
| `GET` | `/workflows/{workflow_id}` | Inspect a workflow |
| `POST` | `/workflows/{workflow_id}/cancel` | Cancel a workflow |
| `POST` | `/workflows/{workflow_id}/retry` | Retry a failed workflow |

### Z3 Formal Verification

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/z3/...` | Z3 SMT solver status |
| `POST` | `/z3/...` | Submit a constraint for Z3 verification |

### Other endpoints

- `GET /stats` — bus statistics and Prometheus-compatible metrics
- `GET /usage` — metering and rate-limit usage
- `POST /signup` — tenant registration
- `GET /badge` — governance compliance badge generation
- `GET /widget.js` — embeddable governance widget

Optional routers (registered when dependencies are available):
- **Constitutional Review API** — structured constitutional review workflows
- **Circuit Breaker Health** — circuit breaker state and trip history
- **Session Governance API** — multi-session governance state tracking
- **Visual Studio / Copilot API** — IDE integration endpoints

## Architecture and Subsystems

### Core message bus (`agent_bus.py`)

`EnhancedAgentBus` manages agent registration, message routing, and constitutional validation. Every message is validated against the loaded constitutional rules before delivery.

### Deliberation layer (`deliberation_layer/`)

Human-in-the-loop vote collection and consensus. Provides `DeliberationQueue`, `VotingService`, `EventDrivenVoteCollector` (Redis pub/sub), `RedisVotingSystem`, `GraphRAGContextEnricher`, and `multi_approver`. See also: the `acgs-deliberation` package, which re-exports this layer's stable surface.

### Enterprise SSO (`enterprise_sso/`)

LDAP integration, SAML/OIDC middleware, data warehouse connectors, Kafka streaming, and tenant migration tooling.

### Adaptive governance (`adaptive_governance/`)

ML-driven governance adaptation: `audit_judge`, `llm_judge`, `blue_team` red-teaming, DTMC learning, amendment recommendations, and impact scoring.

### MACI enforcement (`maci_enforcement.py`)

`MACIEnforcer` + `MACIRoleRegistry` — enforces PROPOSER / VALIDATOR / EXECUTOR / OBSERVER separation for every agent interaction.

### Durable workflow execution (`persistence/`)

Saga-pattern workflow executor with PostgreSQL backend (`PostgresWorkflowRepository`) and in-memory fallback (`InMemoryWorkflowRepository`).

### Batch processing (`batch_processor.py`)

`BatchMessageProcessor` — concurrent constitutional validation for bulk message ingestion with configurable item timeout, concurrency, and slow-item threshold.

### Observability

Structured logging via `observability/structured_logging.py`, Prometheus metrics via `prometheus-client`, and per-request correlation IDs.

## Configuration

Key runtime settings in `api/config.py`:

| Setting | Default | Description |
|---------|---------|-------------|
| `DEFAULT_API_PORT` | `8000` | Service port |
| `DEFAULT_WORKERS` | `4` | Uvicorn worker count |
| `CIRCUIT_BREAKER_FAIL_MAX` | (configured) | Failures before circuit trips |
| `CIRCUIT_BREAKER_RESET_TIMEOUT_SECONDS` | (configured) | Circuit reset timeout |
| `BATCH_PROCESSOR_MAX_CONCURRENCY` | (configured) | Max concurrent batch items |

Redis connection: `REDIS_URL` environment variable (defaults to `redis://localhost:6379`).

## Security

- **Rate limiting** — 60 requests/minute per client via `slowapi` (429 on breach)
- **MACI enforcement** — every governance action checked against role permissions
- **Constitutional validation** — all messages validated before routing
- **Non-root container** — Dockerfile creates `acgs` user (UID 1000)
- **Patched dependencies** — `pydantic>=2.12.1` (CVE-2025-6607), `litellm>=1.61.6` (CVE-2025-1499), `setuptools>=80.9.0` (CVE-2025-69226/69229), `cryptography>=44.0.2`
- **JWT authentication** — `PyJWT>=2.8.0` for bearer token validation

## Optional Dependencies

```bash
pip install "enhanced-agent-bus[ml]"       # NumPy, scikit-learn, MLflow, Evidently, River
pip install "enhanced-agent-bus[pqc]"      # Post-Quantum Cryptography (liboqs, CRYSTALS-Kyber)
pip install "enhanced-agent-bus[postgres]" # asyncpg + SQLAlchemy for PostgreSQL persistence
pip install "enhanced-agent-bus[messaging]"# aiokafka for Kafka streaming
```

## Runtime dependencies

`fastapi`, `uvicorn`, `redis`, `httpx`, `pydantic>=2.12.1`, `litellm`, `slowapi`, `msgpack`, `pybreaker`, `prometheus-client`, `jsonschema`, `PyJWT`, `cachetools`, `PyYAML`, `psutil`, `orjson`, `aiofiles`, `python-multipart`

## License

Apache-2.0.

## Links

- [Homepage](https://acgs.ai)
- [PyPI](https://pypi.org/project/enhanced-agent-bus/)
- [Issues](https://github.com/dislovelhl/enhanced-agent-bus/issues)
- [Changelog](https://github.com/dislovelhl/enhanced-agent-bus/releases)
