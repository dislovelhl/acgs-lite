# acgs-deliberation

[![PyPI](https://img.shields.io/pypi/v/acgs-deliberation)](https://pypi.org/project/acgs-deliberation/)
[![Python](https://img.shields.io/pypi/pyversions/acgs-deliberation)](https://pypi.org/project/acgs-deliberation/)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](https://www.apache.org/licenses/LICENSE-2.0)

**ACGS deliberation and human-in-the-loop (HITL) orchestration — stable import surface for `enhanced-agent-bus` deliberation.**

`acgs-deliberation` is the first extraction target from `enhanced-agent-bus`. Currently it re-exports the stable deliberation surface from `enhanced_agent_bus.deliberation_layer` so new code can use `from acgs_deliberation import ...` without depending on the full bus package directly. Source migration is ongoing.

> **Note:** This package requires `enhanced-agent-bus>=3.0.0` as a runtime dependency. If you need only deliberation features, install this package; if you need the full agent bus service, install `enhanced-agent-bus` directly.

## Installation

```bash
pip install acgs-deliberation
```

Requires Python 3.11+.

## Quick Start

### Voting and consensus

```python
from acgs_deliberation import (
    VotingService, VotingStrategy, Vote, Election,
    VoteSession, EventDrivenVoteCollector, get_vote_collector,
)

service = VotingService(strategy=VotingStrategy.MAJORITY)
election = service.create_election(topic="approve-deployment", participants=["a", "b", "c"])

service.cast_vote(election.id, Vote(voter_id="a", approve=True))
service.cast_vote(election.id, Vote(voter_id="b", approve=True))
service.cast_vote(election.id, Vote(voter_id="c", approve=False))

result = service.tally(election.id)
print(result.approved)  # True (2/3 majority)
```

### Deliberation queue

```python
from acgs_deliberation import DeliberationQueue, DeliberationTask

queue = DeliberationQueue()
task = DeliberationTask(
    task_id="task-1",
    description="Review proposed database schema change",
    required_approvers=2,
)
queue.enqueue(task)
pending = queue.pending()
```

### Redis-backed deliberation (for distributed deployments)

```python
from acgs_deliberation import (
    REDIS_AVAILABLE,
    get_redis_deliberation_queue,
    get_redis_voting_system,
)

if REDIS_AVAILABLE:
    rq = get_redis_deliberation_queue()
    rvs = get_redis_voting_system()
```

### Multi-approver workflow

```python
from acgs_deliberation import multi_approver

@multi_approver(required=2, timeout_seconds=300)
async def deploy_to_production(config: dict) -> str:
    return "deployed"
```

### Full deliberation layer integration

```python
from acgs_deliberation import DeliberationLayer

layer = DeliberationLayer()
await layer.initialize()
result = await layer.submit_for_deliberation(
    action="deploy", context={"env": "production"}
)
```

### GraphRAG context enrichment

```python
from acgs_deliberation import GraphRAGContextEnricher

enricher = GraphRAGContextEnricher()
enriched = await enricher.enrich(task, context={"related_decisions": [...]})
```

## Key Features

- **Voting service** — `VotingService` with pluggable `VotingStrategy` (majority, unanimous, weighted)
- **Event-driven vote collection** — `EventDrivenVoteCollector` via Redis pub/sub; `VoteEvent` / `VoteSession` lifecycle
- **Deliberation queue** — `DeliberationQueue` / `DeliberationTask` for async task approval workflows
- **Redis backends** — `RedisDeliberationQueue` / `RedisVotingSystem` for persistent, distributed deployments
- **Multi-approver decorator** — `multi_approver` for gating async functions behind human approval
- **Impact scoring** — `calculate_message_impact` / `get_impact_scorer` (requires `enhanced-agent-bus[ml]` for ML-backed scoring)
- **GraphRAG enrichment** — `GraphRAGContextEnricher` attaches related decisions to deliberation context
- **`DeliberationLayer`** — full integration point with dependency injection for all components

## Exported Symbols

| Symbol | Description |
|--------|-------------|
| `DeliberationLayer` | Main integration class with dependency injection |
| `DeliberationQueue` | In-process deliberation task queue |
| `DeliberationTask` | A pending decision requiring human approval |
| `Election` | An open voting round |
| `Vote` | A single voter's approval/rejection |
| `VoteEvent` | Event emitted when a vote is cast |
| `VoteSession` | Session tracking an active vote collection |
| `VotingService` | Creates elections and tallies votes |
| `VotingStrategy` | Enum: `MAJORITY`, `UNANIMOUS`, `WEIGHTED` |
| `EventDrivenVoteCollector` | Redis pub/sub–based vote collection |
| `get_vote_collector` | Factory for the global `EventDrivenVoteCollector` |
| `reset_vote_collector` | Resets the global vote collector (testing) |
| `GraphRAGContextEnricher` | Attaches graph-RAG context to deliberation tasks |
| `RedisDeliberationQueue` | Redis-backed `DeliberationQueue` |
| `RedisVotingSystem` | Redis-backed voting system |
| `get_redis_deliberation_queue` | Factory for the Redis deliberation queue |
| `get_redis_voting_system` | Factory for the Redis voting system |
| `multi_approver` | Decorator: gate an async function behind N approvals |
| `calculate_message_impact` | Score the governance impact of a message |
| `get_impact_scorer` | Factory for the impact scorer (lazy-loads ML deps) |
| `REDIS_AVAILABLE` | `True` when Redis dependencies are installed |

## Runtime dependencies

- `enhanced-agent-bus>=3.0.0`

Redis-backed components require Redis to be running. ML-backed impact scoring requires `pip install enhanced-agent-bus[ml]`.

## License

Apache-2.0.

## Links

- [Homepage](https://acgs.ai)
- [PyPI](https://pypi.org/project/acgs-deliberation/)
- [Issues](https://github.com/dislovelhl/acgs-deliberation/issues)
