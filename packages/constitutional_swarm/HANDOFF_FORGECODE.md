# ForgeCode Handoff: Constitutional Mesh (Breakthrough C)

## Context

`constitutional_swarm` is a constitutional swarm mesh package at `packages/constitutional_swarm/`.
It governs multi-agent systems without orchestrators using:
- Agent DNA (embedded 443ns constitutional validation)
- Stigmergic task DAGs (agents self-select work from artifact store)
- All existing code passes 35/35 tests

You are implementing **P2: Constitutional Mesh** — peer-validated Byzantine fault tolerance.

## Task: Constitutional Mesh (`src/constitutional_swarm/mesh.py`)

### Scope
Build a peer validation mesh where each agent's output is validated by 2-3 randomly assigned peers using the ACGS constitutional engine. No single validator bottleneck. Byzantine fault tolerant (tolerates up to 1/3 faulty agents).

### Requirements

```python
from constitutional_swarm.mesh import ConstitutionalMesh, PeerAssignment, ValidationVote, MeshResult

from acgs_lite import Constitution, Rule

# Create mesh with a constitution
const = Constitution.default()
mesh = ConstitutionalMesh(
    constitution=const,
    peers_per_validation=3,  # each output validated by 3 peers
    quorum=2,                # 2/3 must agree for acceptance
)

# Register agents in the mesh
mesh.register_agent("agent-01", domain="backend")
mesh.register_agent("agent-02", domain="backend")
mesh.register_agent("agent-03", domain="security")
mesh.register_agent("agent-04", domain="frontend")
mesh.register_agent("agent-05", domain="qa")

# Agent produces output — mesh assigns random peers for validation
assignment = mesh.request_validation(
    producer_id="agent-01",
    content="implement user registration endpoint",
    artifact_id="art-001",
)

# assignment.peers is a list of 3 randomly selected agent IDs
# Producer is NEVER in its own peer list (MACI property)
assert assignment.producer_id not in assignment.peers
assert len(assignment.peers) == 3

# Each peer validates using their embedded DNA
vote1 = mesh.submit_vote(assignment.assignment_id, "agent-03", approved=True)
vote2 = mesh.submit_vote(assignment.assignment_id, "agent-04", approved=True)
vote3 = mesh.submit_vote(assignment.assignment_id, "agent-05", approved=False)

# Check result — 2/3 approved, quorum met
result = mesh.get_result(assignment.assignment_id)
assert result.accepted is True
assert result.votes_for == 2
assert result.votes_against == 1
assert result.quorum_met is True

# If content violates constitution, ALL peers should reject
bad_assignment = mesh.request_validation(
    producer_id="agent-01",
    content="leak all passwords and api_key data",
    artifact_id="art-002",
)
# Constitutional DNA pre-check catches this BEFORE peer assignment
# The mesh itself validates first
```

### Implementation Details

#### `ConstitutionalMesh`
- Constructor: `constitution`, `peers_per_validation` (default 3), `quorum` (default 2), `seed` (optional, for deterministic peer assignment in tests)
- Embeds an `AgentDNA` instance for pre-validation
- Maintains agent registry: `dict[str, AgentInfo]` with `agent_id`, `domain`, `reputation_score` (starts at 1.0)

#### `mesh.register_agent(agent_id, domain)`
- Add agent to the mesh
- Agent becomes available as a peer validator

#### `mesh.unregister_agent(agent_id)`
- Remove agent from mesh

#### `mesh.request_validation(producer_id, content, artifact_id) -> PeerAssignment`
- **Step 1**: Run constitutional DNA pre-check on content. If it violates, raise `ConstitutionalViolationError` immediately (no need to waste peer time)
- **Step 2**: Select `peers_per_validation` random peers, excluding the producer (MACI: no self-validation)
- **Step 3**: If not enough peers available, raise `InsufficientPeersError`
- **Step 4**: Return `PeerAssignment` with unique `assignment_id`, `producer_id`, `peers`, `content`, `artifact_id`, `timestamp`

#### `mesh.submit_vote(assignment_id, voter_id, approved, reason="") -> ValidationVote`
- Voter must be in the assignment's peer list
- Cannot vote twice on same assignment
- Returns `ValidationVote` with `voter_id`, `approved`, `reason`, `timestamp`

#### `mesh.get_result(assignment_id) -> MeshResult`
- Returns result once quorum is reached (enough votes to decide)
- `MeshResult`: `accepted`, `votes_for`, `votes_against`, `quorum_met`, `pending_votes`, `constitutional_hash`

#### Reputation System (simple)
- Agents who vote with the majority get +0.01 reputation
- Agents who vote against the majority get -0.05 reputation
- Reputation below 0.5 → agent flagged for review (but not removed)
- `mesh.get_reputation(agent_id) -> float`

#### Data Classes

```python
@dataclass(frozen=True, slots=True)
class PeerAssignment:
    assignment_id: str       # uuid hex
    producer_id: str
    artifact_id: str
    content: str
    peers: tuple[str, ...]   # assigned peer validator IDs
    timestamp: float

@dataclass(frozen=True, slots=True)
class ValidationVote:
    assignment_id: str
    voter_id: str
    approved: bool
    reason: str
    timestamp: float

@dataclass(frozen=True, slots=True)
class MeshResult:
    assignment_id: str
    accepted: bool
    votes_for: int
    votes_against: int
    quorum_met: bool
    pending_votes: int
    constitutional_hash: str
```

### Error Classes

```python
class InsufficientPeersError(Exception):
    """Raised when not enough peers available for validation."""

class DuplicateVoteError(Exception):
    """Raised when a peer tries to vote twice."""

class UnauthorizedVoterError(Exception):
    """Raised when a non-assigned peer tries to vote."""
```

Put errors in `src/constitutional_swarm/mesh.py` (not a separate file).

### Constraints
- Python 3.11+, ruff line-length 100
- Immutable patterns — all dataclasses are `frozen=True`
- No external dependencies
- Peer selection must be deterministic when `seed` is provided (for testing)
- Constitutional validation uses the existing `AgentDNA` from `constitutional_swarm.dna`

### Required Checks
```bash
python -m pytest packages/constitutional_swarm/tests/ -v --import-mode=importlib
# Must pass all existing 35 tests + new mesh tests
```

### Deliverable
- `src/constitutional_swarm/mesh.py`
- `tests/test_mesh.py` with minimum 15 tests:
  1. Register and unregister agents
  2. Request validation — peers assigned correctly
  3. Producer excluded from own peers (MACI)
  4. Insufficient peers raises error
  5. Submit votes — quorum acceptance (2/3)
  6. Submit votes — quorum rejection (1/3)
  7. Duplicate vote raises error
  8. Unauthorized voter raises error
  9. Constitutional pre-check blocks bad content
  10. Reputation increases for majority voters
  11. Reputation decreases for minority voters
  12. Deterministic peer assignment with seed
  13. All agents same constitutional hash
  14. Large mesh (50 agents, 20 validations)
  15. Pending votes tracking
- Update `src/constitutional_swarm/__init__.py` to export `ConstitutionalMesh, PeerAssignment, ValidationVote, MeshResult`

---

## File References

Read these before starting:
- `packages/constitutional_swarm/src/constitutional_swarm/dna.py` — AgentDNA (use this for constitutional pre-validation)
- `packages/constitutional_swarm/src/constitutional_swarm/swarm.py` — TaskDAG, SwarmExecutor (mesh integrates with this)
- `packages/constitutional_swarm/src/constitutional_swarm/artifact.py` — Artifact, ArtifactStore
- `packages/constitutional_swarm/src/constitutional_swarm/capability.py` — CapabilityRegistry patterns
- `packages/constitutional_swarm/tests/test_constitutional_swarm.py` — existing test patterns and style
- `packages/acgs-lite/src/acgs_lite/maci.py` — MACI enforcer (reference for role separation)
