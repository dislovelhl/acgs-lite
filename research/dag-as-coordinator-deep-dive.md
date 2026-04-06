# The DAG-as-Coordinator Pattern — Deep Implementation Study

**Source**: `constitutional_swarm` in `acgs-clean`
**Date**: 2026-04-06
**Lines studied**: ~2,500 across 7 files (swarm.py, artifact.py, capability.py, compiler.py, execution.py, bench.py, dna.py)
**Test corpus**: 625 tests, all passing

---

## The Core Thesis

Most multi-agent frameworks have an **orchestrator** — a central process that decides who does what, routes messages between agents, and manages state. LangGraph has a `StateGraph` that sequences node calls. CrewAI has a `Crew` that manages task delegation. AutoGen has a `GroupChatManager` that routes messages.

The constitutional_swarm pattern eliminates the orchestrator entirely. The coordination mechanism is the **data structure itself**: a TaskDAG + an ArtifactStore. No routing, no message passing, no central brain. Agents look at the DAG, see what's ready, claim it, do it, publish the result. The DAG updates. Downstream tasks unlock. Next agent picks up work.

This is **stigmergy** — the biological term for coordination through environmental modification. Ants don't talk to each other about where food is; they lay pheromone trails and other ants follow them. Here, agents don't message each other about what to work on; they publish artifacts and the DAG structure propagates readiness.

---

## The Four Components

### 1. TaskDAG — The Immutable Plan

```
TaskDAG
├── nodes: dict[str, TaskNode]     # node_id → node
├── goal: str                       # human-readable goal
└── dag_id: str                     # UUID

TaskNode
├── node_id: str                    # deterministic hash of title
├── title, description, domain
├── required_capabilities: tuple[str, ...]
├── depends_on: tuple[str, ...]     # parent node IDs
├── status: ExecutionStatus         # BLOCKED → READY → CLAIMED → COMPLETED
├── claimed_by: str | None
├── artifact_id: str | None
└── priority: int
```

**Key design decision: immutability.** Every mutation (`add_node`, `mark_ready`, `claim_node`, `complete_node`) returns a **new TaskDAG**. The original is never modified.

```python
dag = dag.claim_node("A", "agent-01")      # returns new DAG
dag = dag.complete_node("A", "art-A")       # returns new DAG
dag = dag.mark_ready()                       # returns new DAG
```

This means:
- **Concurrent reads are safe** — multiple agents can read the DAG simultaneously without locks at the DAG level
- **State history is free** — you can keep old references
- **No defensive copying** — callers can't corrupt internal state

The SwarmExecutor wraps this with a single `threading.Lock` for the write path, but the DAG itself is a pure functional data structure.

**`mark_ready()` is the key operation.** After any node completes, `mark_ready()` scans all BLOCKED nodes and promotes those whose dependencies are all COMPLETED. This is the propagation mechanism — no orchestrator decides "B and C are ready now because A finished." The DAG structure itself determines readiness.

```python
def mark_ready(self) -> TaskDAG:
    new_nodes = dict(self.nodes)
    for nid, node in new_nodes.items():
        if node.status != ExecutionStatus.BLOCKED:
            continue
        if self._dependencies_completed(node):
            new_nodes[nid] = TaskNode(..., status=ExecutionStatus.READY)
    return TaskDAG(dag_id=self.dag_id, goal=self.goal, nodes=new_nodes)
```

### 2. ArtifactStore — The Stigmergic Medium

```
ArtifactStore
├── _artifacts: dict[str, Artifact]       # content-addressed store
├── _by_task: dict[str, list[str]]        # task_id → artifact IDs
├── _by_domain: dict[str, list[str]]      # domain → artifact IDs
├── _by_agent: dict[str, list[str]]       # agent_id → artifact IDs
└── _watchers: dict[str, list[Callable]]  # key → callbacks
```

```
Artifact (frozen dataclass, slots)
├── artifact_id: str
├── task_id: str          # links to TaskNode
├── agent_id: str         # who produced it
├── content_type: str
├── content: str
├── domain: str
├── tags: tuple[str, ...]
├── parent_artifacts: tuple[str, ...]   # provenance chain
├── constitutional_hash: str            # governance integrity
└── content_hash: property              # SHA-256[:32] of content
```

**Agents never message each other.** Agent A publishes an artifact. Agent B discovers it via `get_by_task()` or `get_by_domain()`. The store IS the communication channel.

**`watch(key, callback)` enables reactive pipelines:**
```python
store.watch("backend", lambda artifact: trigger_tests(artifact))
```
When a backend artifact is published, the callback fires. This replaces polling. In production, this would be backed by Redis pub/sub, a Postgres LISTEN/NOTIFY, or git webhooks.

**Integrity verification is built in:**
```python
store.verify_integrity("art-001")  # recomputes SHA-256, compares
```
Combined with `constitutional_hash` on each artifact, you can verify that: (a) the content hasn't been tampered with, and (b) the agent that produced it was running the same constitution as everyone else.

### 3. CapabilityRegistry — O(1) Routing Without Broadcasting

```
CapabilityRegistry
├── _by_agent: dict[str, list[Capability]]
├── _by_domain: dict[str, list[(str, Capability)]]   # O(1) domain lookup
└── _by_name: dict[str, list[(str, Capability)]]      # O(1) name lookup
```

```
Capability (frozen dataclass, slots)
├── name: str
├── domain: str
├── description: str
├── model_tier: str         # "sonnet", "opus", "haiku"
├── avg_latency_ms: float   # for routing decisions
├── cost_per_task: float    # for budget-aware routing
└── tags: tuple[str, ...]
```

When a task requires `"code_review"` in the `"security"` domain, the registry returns matching agents in O(1) — not by broadcasting to all N agents and waiting for responses.

**`find_best()` scores by multiple dimensions:**
```python
best = registry.find_best("code_review", domain="security",
                           prefer_fast=True)
# Scores: match quality + 1/latency + 1/cost
```

This is the routing table for the swarm. It replaces the orchestrator's routing logic with a declarative lookup.

### 4. SwarmExecutor — The Thin Runtime

```python
class SwarmExecutor:
    _registry: CapabilityRegistry
    _store: ArtifactStore
    _dag: TaskDAG | None
    _lock: threading.Lock       # single lock for all writes
```

The executor has **five methods**:

| Method | What it does |
|--------|-------------|
| `load_dag(dag)` | Sets the DAG, calls `mark_ready()` |
| `available_tasks(agent_id)` | Returns READY tasks matching agent's capabilities |
| `claim(node_id, agent_id)` | Claims a task (updates DAG) |
| `submit(node_id, artifact)` | Publishes artifact, completes node, calls `mark_ready()` |
| `is_complete` / `progress` | Status queries |

**The entire coordination logic is 14 lines:**

```python
def submit(self, node_id, artifact):
    with self._lock:
        node = self._dag.nodes.get(node_id)
        if node.claimed_by is not None and artifact.agent_id != node.claimed_by:
            raise PermissionError(...)      # MACI enforcement
        self._store.publish(artifact)        # store the result
        self._dag = self._dag.complete_node(node_id, artifact.artifact_id)
        self._dag = self._dag.mark_ready()   # propagate readiness
```

That's it. `submit()` is the only coordination logic in the entire system. It:
1. Verifies MACI (submitter == claimant)
2. Stores the artifact
3. Marks the node complete
4. Propagates readiness to downstream nodes

No message routing. No state machine. No callback chains.

---

## The Execution Loop

Here's how a swarm actually runs:

```
while not executor.is_complete:
    for agent_id in agents:
        tasks = executor.available_tasks(agent_id)    # O(1) per capability match
        if not tasks:
            continue
        task = tasks[0]                                # highest priority
        receipt = executor.claim(task.node_id, agent_id)
        
        # --- Agent does actual work here ---
        dna.validate(input)                            # 443ns governance check
        result = agent.execute(task)
        dna.validate(result)                           # output governance
        
        artifact = Artifact(
            artifact_id=f"art-{task.node_id}",
            task_id=task.node_id,
            agent_id=agent_id,
            content=result,
            constitutional_hash=dna.hash,
        )
        executor.submit(task.node_id, artifact)        # triggers mark_ready()
```

The agent loop is trivially parallelizable — each agent runs independently, the only synchronization point is the lock inside SwarmExecutor.

---

## Benchmark Results

Real numbers from the benchmark harness (100 agents, 8 domains):

| DAG Size | Tasks | Total Time | Val Latency | Throughput | Overhead |
|----------|-------|-----------|-------------|------------|----------|
| 3×5 | 15 | 0.37ms | 5,525 ns | 40,735/s | 21.6% |
| 5×10 | 50 | 1.36ms | 2,703 ns | 36,651/s | 22.1% |
| 10×20 | 200 | 14.18ms | 2,570 ns | 14,100/s | 23.2% |
| 20×30 | 600 | 118.56ms | 2,610 ns | 5,061/s | 21.7% |
| 30×50 | 1,500 | 712.83ms | 2,891 ns | 2,104/s | 21.5% |

**Coordination overhead is constant at ~22%** regardless of DAG size. This is O(N) — it doesn't grow with the number of agents. The 560ns Rust engine validation is a constant per-task cost.

Scaling test (50 tasks, varying agents):

| Agents | Total Time | Throughput | Overhead |
|--------|-----------|------------|----------|
| 10 | 1.39ms | 35,953/s | 23.4% |
| 100 | 1.25ms | 40,023/s | 23.1% |
| 400 | 1.26ms | 39,768/s | 22.5% |
| 800 | 1.28ms | 39,115/s | 22.5% |

**Adding 80× more agents doesn't change throughput.** The bottleneck is the DAG structure (serial dependency chains), not the coordination overhead.

---

## Why This Beats Orchestrator Patterns

### LangGraph (orchestrator = StateGraph)

```python
# LangGraph: explicit edges, central state, sequential routing
graph = StateGraph(AgentState)
graph.add_node("researcher", research_agent)
graph.add_node("writer", write_agent)
graph.add_edge("researcher", "writer")
graph.add_conditional_edges("writer", should_continue, {"end": END, "research": "researcher"})
app = graph.compile()
```

Problems:
1. **The graph IS the orchestrator** — `app.invoke()` steps through nodes sequentially
2. **Adding agents requires editing the graph** — every new agent needs new edges
3. **State is mutable and shared** — `AgentState` is passed through every node, any node can corrupt it
4. **No parallel execution by default** — you need explicit `parallel` branches
5. **No capability-based routing** — you hardcode which node handles what

### CrewAI (orchestrator = Crew)

```python
crew = Crew(
    agents=[researcher, writer, reviewer],
    tasks=[research_task, write_task, review_task],
    process=Process.sequential,  # or hierarchical
)
result = crew.kickoff()
```

Problems:
1. **The Crew is the orchestrator** — it manages task assignment, delegation, and sequencing
2. **Tasks are assigned to specific agents** — no self-selection
3. **Hierarchical mode adds a "manager" agent** — another layer of orchestration
4. **No immutability** — shared mutable state throughout
5. **No governance** — any agent can produce any output

### AutoGen (orchestrator = GroupChatManager)

```python
groupchat = GroupChat(agents=[user, assistant, critic], messages=[])
manager = GroupChatManager(groupchat=groupchat)
user.initiate_chat(manager, message="Build a feature")
```

Problems:
1. **GroupChatManager literally routes every message** — it's a central bottleneck
2. **Message-based coordination** — O(N²) in message volume as agents increase
3. **Turn-based** — one agent speaks at a time
4. **No structured dependencies** — agents decide when to hand off via chat messages
5. **No artifact persistence** — work products are chat messages, not addressable objects

### The DAG Pattern (no orchestrator)

```python
executor = SwarmExecutor(registry, store)
executor.load_dag(dag)
# agents self-select, claim, work, submit — executor just manages DAG state
```

Advantages:
1. **No orchestrator** — DAG structure IS the coordination
2. **Self-selection** — agents pick tasks matching their capabilities
3. **True parallelism** — independent branches execute simultaneously
4. **Immutable state** — DAG operations return new objects
5. **Stigmergic communication** — through artifacts, not messages
6. **Governance built in** — DNA validation on every submit, MACI on claim/submit
7. **O(1) per-agent overhead** — coordination cost doesn't grow with swarm size

---

## What the Pattern Deliberately Omits

The design is notable for what it **doesn't** include:

| Missing Feature | Why It's Omitted | Where It Composes |
|----------------|-------------------|-------------------|
| **Retry logic** | Retry is a policy, not coordination | Wrap `submit()` in a retry loop |
| **Timeouts** | Timeout is a policy | `WorkReceipt.deadline_epoch` + external timer |
| **Async/await** | The lock-based design is simpler for correctness | Replace `threading.Lock` with `asyncio.Lock` |
| **Persistence** | ArtifactStore is in-memory | Swap for git-backed, DB-backed, or S3-backed store |
| **Governance** | DNA validation is separate from execution | `dna.validate()` composes with any executor |
| **Error handling** | `ExecutionStatus.FAILED` exists but no auto-recovery | External supervisor or circuit breaker |
| **Agent lifecycle** | No agent creation/destruction | CapabilityRegistry.register/unregister |

Every omitted feature can be added **externally** without modifying the core. This is the opposite of framework design — instead of building a kitchen-sink orchestrator, build a minimal coordination primitive and let everything else compose around it.

---

## Design Rules for Borrowing This Pattern

### Do

1. **Keep nodes coarse.** One deliverable per node, not one function call. A node should take minutes, not milliseconds.

2. **Back ArtifactStore with git** for persistence. Git already gives you content-addressing, branching, history, and distributed replication.

3. **Use `watch()` over polling.** The current in-memory implementation uses callbacks. In production, this is Redis pub/sub, Postgres LISTEN/NOTIFY, or filesystem watchers.

4. **Make the DAG the single source of truth.** Don't maintain side-channel state about what's done and what's not. The DAG knows.

5. **Use capability matching for routing.** Don't hardcode "agent-01 does task A". Declare capabilities, let the executor match.

### Don't

1. **Don't make nodes too fine-grained.** If you have 10,000 nodes for a single feature, you've built a workflow engine, not a swarm.

2. **Don't add message passing between agents.** The whole point is stigmergic coordination through artifacts. If agents need to talk to each other, your node granularity is wrong.

3. **Don't put retry/timeout in the executor.** These are policies that compose externally.

4. **Don't skip `mark_ready()`.** It's the propagation mechanism. Without it, the DAG is a static plan, not a coordination structure.

5. **Don't mutate the DAG directly.** The immutable pattern is load-bearing — it's what makes concurrent reads safe.

---

## The Biological Analogy

The docstring says "like how ants coordinate through pheromones." This is precise:

| Ant Colony | DAG Swarm |
|-----------|-----------|
| Pheromone trail | Artifact in the store |
| Ant follows strongest trail | Agent picks highest-priority ready task |
| Trail evaporates over time | `WorkReceipt.deadline_epoch` |
| New ants join without briefing | Register capabilities, start claiming tasks |
| Colony scales to millions | Coordination overhead is O(1) per agent |
| No ant knows the colony plan | No agent knows the full DAG — only its available tasks |

The key insight from stigmergy research: **the environment is the coordinator.** Modify the environment (publish an artifact), and other agents respond to the modification (downstream tasks become ready). No central intelligence required.

---

## Comparison to Real-World Distributed Systems

This pattern has surprising parallels to:

**Make/Bazel** — build systems are DAG executors with dependency-driven scheduling. A Makefile is a TaskDAG. `make -j8` is a SwarmExecutor with 8 workers. The pattern works because build systems have proven that DAG + artifact store (file system) + capability matching (tool availability) scales to millions of targets.

**Kubernetes Jobs** — a Job controller watches for pod completion and creates successor pods. The "DAG" is implicit in job dependencies. The "ArtifactStore" is persistent volumes. But Kubernetes adds a massive coordination layer (etcd, kube-scheduler, controller-manager) that this pattern eliminates.

**Git + CI/CD** — CI pipelines ARE DAGs of tasks with artifact passing. GitHub Actions, GitLab CI, Tekton — all implement this pattern with YAML definitions of task graphs. The constitutional_swarm version is the same idea but for agent-to-agent coordination instead of build-to-build.

The difference is that constitutional_swarm makes the coordination pattern **first-class in application code**, not just in infrastructure tooling. You can embed this in any Python application without Kubernetes, without CI runners, without build systems.

---

## Summary

The DAG-as-coordinator pattern works because it reduces multi-agent coordination to three solved problems:

1. **Dependency resolution** — topological sort (well-understood since 1962)
2. **Content-addressed storage** — SHA-256 integrity (well-understood since 2001)
3. **Capability matching** — O(1) hash lookup (well-understood since forever)

No novel algorithms. No complex state machines. No message routing. Just three simple primitives composed correctly. The result is a coordination mechanism that scales linearly, maintains immutability, and eliminates the orchestrator — the single biggest source of complexity in every other multi-agent framework.
