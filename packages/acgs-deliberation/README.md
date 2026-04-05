# acgs-deliberation

[![PyPI](https://img.shields.io/pypi/v/acgs-deliberation)](https://pypi.org/project/acgs-deliberation/)
[![Python](https://img.shields.io/pypi/pyversions/acgs-deliberation)](https://pypi.org/project/acgs-deliberation/)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)

**Deliberation, HITL orchestration, consensus, and impact routing for ACGS agents.**

`acgs-deliberation` is the extraction-friendly deliberation package for the ACGS runtime.
Today it re-exports the stable surface from `enhanced_agent_bus.deliberation_layer`, so
you can start using the standalone import path now without waiting for the full source
move.

## Installation

`acgs-deliberation` supports Python 3.11+.

```bash
pip install acgs-deliberation
```

## Quick Start

```python
from acgs_deliberation import Vote, VotingService, calculate_message_impact
from enhanced_agent_bus.models import AgentMessage, MessageType, Priority

message = AgentMessage(
    from_agent="planner",
    to_agent="compliance",
    message_type=MessageType.COMMAND,
    priority=Priority.HIGH,
    content={"action": "deploy", "target": "payments"},
)

voting = VotingService(force_in_memory=True)
election_id = await voting.create_election(
    message,
    participants=["security", "risk", "compliance"],
)

await voting.cast_vote(
    election_id,
    Vote(agent_id="security", decision="APPROVE", reason="controls in place"),
)

decision = await voting.get_result(election_id)
impact = calculate_message_impact(message.to_dict(), {"environment": "production"})
```

### Redis-Backed Voting

```python
from acgs_deliberation import get_redis_voting_system

redis_voting = get_redis_voting_system()
```

## Key Features

- Voting primitives including `VotingService`, `Election`, `Vote`, and
  `VotingStrategy`.
- Event-driven collection via `EventDrivenVoteCollector`, `VoteSession`, and
  `VoteEvent`.
- Deliberation queue support with `DeliberationQueue` and `DeliberationTask`.
- Optional Redis-backed queueing and voting primitives for distributed deployments.
- Impact scoring and GraphRAG context enrichment hooks for review routing.

## Package Relationship

- Install name: `acgs-deliberation`
- Import namespace: `acgs_deliberation`
- Runtime dependency: `enhanced-agent-bus>=3.0.0`

## License

AGPL-3.0-or-later. Commercial licensing is available; contact `hello@acgs.ai`.

## Links

- [Homepage](https://acgs.ai)
- [Documentation](https://github.com/acgs2_admin/acgs/tree/main/packages/acgs-deliberation)
- [PyPI](https://pypi.org/project/acgs-deliberation/)
- [Repository](https://github.com/acgs2_admin/acgs)
- [Issues](https://github.com/acgs2_admin/acgs/issues)
- [Changelog](https://github.com/acgs2_admin/acgs/releases)

Constitutional Hash: `608508a9bd224290`
