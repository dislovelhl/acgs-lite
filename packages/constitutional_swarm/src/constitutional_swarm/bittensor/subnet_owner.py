"""Constitutional Swarm Subnet Owner — Bittensor SN Owner runtime.

The SN Owner:
  1. Receives escalated governance cases from the ACGS-2 AdaptiveRouter
  2. Packages them as DeliberationSynapses via DAGCompiler
  3. Broadcasts to miners
  4. Collects ValidationSynapses from validators
  5. Records precedent from accepted judgments
  6. Tracks escalation metrics (empirical failure mode distribution)

Bittensor SDK is NOT required — this module uses constitutional_swarm
primitives only.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from acgs_lite import Constitution
from constitutional_swarm.artifact import Artifact, ArtifactStore
from constitutional_swarm.bittensor.protocol import (
    EscalationType,
    SubnetMetrics,
)
from constitutional_swarm.bittensor.synapses import (
    DeliberationSynapse,
    JudgmentSynapse,
    ValidationSynapse,
)
from constitutional_swarm.compiler import DAGCompiler, GoalSpec
from constitutional_swarm.swarm import TaskDAG


@dataclass(frozen=True, slots=True)
class EscalatedCase:
    """An escalated governance case ready for miner deliberation."""

    case_id: str
    synapse: DeliberationSynapse
    dag: TaskDAG
    escalation_type: EscalationType


@dataclass
class PrecedentRecord:
    """A validated miner judgment recorded as precedent."""

    case_id: str
    task_id: str
    miner_uid: str
    judgment: str
    reasoning: str
    escalation_type: EscalationType
    validation_accepted: bool
    votes_for: int
    votes_against: int
    proof_root_hash: str
    constitutional_hash: str


class SubnetOwner:
    """Bittensor SN Owner runtime for constitutional governance subnet.

    Usage:
        owner = SubnetOwner(constitution_path="governance.yaml")

        # Package an escalated case
        case = owner.package_case(
            description="Privacy vs. transparency conflict in financial reporting",
            domain="finance",
            escalation_type=EscalationType.CONSTITUTIONAL_CONFLICT,
            impact_score=0.85,
        )

        # After receiving validation result
        owner.record_result(case, judgment_synapse, validation_synapse)

        # Get empirical escalation distribution
        print(owner.metrics.escalation_distribution())
    """

    def __init__(
        self,
        constitution_path: str,
        *,
        dag_compiler: DAGCompiler | None = None,
    ) -> None:
        self._constitution = Constitution.from_yaml(constitution_path)
        self._compiler = dag_compiler or DAGCompiler()
        self._store = ArtifactStore()
        self._metrics = SubnetMetrics(constitution_hash=self._constitution.hash)
        self._precedents: list[PrecedentRecord] = []
        self._active_cases: dict[str, EscalatedCase] = {}

    @property
    def constitution_hash(self) -> str:
        return self._constitution.hash

    @property
    def metrics(self) -> SubnetMetrics:
        return self._metrics

    @property
    def precedents(self) -> list[PrecedentRecord]:
        return list(self._precedents)

    @property
    def active_cases(self) -> dict[str, EscalatedCase]:
        return dict(self._active_cases)

    def package_case(
        self,
        description: str,
        domain: str,
        *,
        escalation_type: EscalationType = EscalationType.UNKNOWN,
        impact_score: float = 0.0,
        impact_vector: dict[str, float] | None = None,
        required_capabilities: tuple[str, ...] = (),
        deadline_seconds: int = 3600,
        steps: list[dict[str, Any]] | None = None,
    ) -> EscalatedCase:
        """Package an escalated governance case for miner deliberation.

        Compiles the case into a TaskDAG and creates a DeliberationSynapse.
        """
        case_id = uuid.uuid4().hex[:12]
        task_id = uuid.uuid4().hex[:8]

        # Build GoalSpec
        if steps is None:
            steps = [
                {
                    "title": "Analyze governance conflict",
                    "domain": domain,
                    "description": description,
                    "required_capabilities": list(required_capabilities),
                },
            ]

        spec = GoalSpec(
            goal=description,
            domains=[domain],
            steps=steps,
        )
        dag = self._compiler.compile(spec)

        # Create synapse
        synapse = DeliberationSynapse(
            task_id=task_id,
            task_dag_json=_serialize_dag(dag),
            constitution_hash=self._constitution.hash,
            domain=domain,
            required_capabilities=required_capabilities,
            deadline_seconds=deadline_seconds,
            escalation_type=escalation_type.value,
            impact_score=impact_score,
            impact_vector=impact_vector or {},
            context=description,
        )

        # Track
        case = EscalatedCase(
            case_id=case_id,
            synapse=synapse,
            dag=dag,
            escalation_type=escalation_type,
        )
        self._active_cases[case_id] = case
        self._metrics.record_escalation(escalation_type)

        return case

    def record_result(
        self,
        case: EscalatedCase,
        judgment: JudgmentSynapse,
        validation: ValidationSynapse,
    ) -> PrecedentRecord | None:
        """Record the result of a deliberation.

        If accepted, creates a PrecedentRecord. Removes the case from
        active tracking.

        Returns the PrecedentRecord if the judgment was accepted,
        None otherwise.
        """
        self._metrics.total_judgments += 1
        self._metrics.total_validations += 1

        precedent = PrecedentRecord(
            case_id=case.case_id,
            task_id=judgment.task_id,
            miner_uid=judgment.miner_uid,
            judgment=judgment.judgment,
            reasoning=judgment.reasoning,
            escalation_type=case.escalation_type,
            validation_accepted=validation.accepted,
            votes_for=validation.votes_for,
            votes_against=validation.votes_against,
            proof_root_hash=validation.proof_root_hash,
            constitutional_hash=validation.constitutional_hash,
        )

        if validation.accepted:
            self._precedents.append(precedent)
            self._metrics.precedents_created += 1

            # Store the judgment as an artifact
            artifact = Artifact(
                artifact_id=uuid.uuid4().hex[:12],
                task_id=judgment.task_id,
                agent_id=judgment.miner_uid,
                content_type="validated_precedent",
                content=judgment.judgment,
                domain=case.synapse.domain,
                constitutional_hash=judgment.constitutional_hash,
                metadata={
                    "reasoning": judgment.reasoning,
                    "escalation_type": case.escalation_type.value,
                    "votes_for": validation.votes_for,
                    "votes_against": validation.votes_against,
                    "proof_root_hash": validation.proof_root_hash,
                },
            )
            self._store.publish(artifact)

        # Remove from active cases
        self._active_cases.pop(case.case_id, None)

        return precedent if validation.accepted else None

    def summary(self) -> dict[str, Any]:
        """SN Owner operational summary."""
        return {
            "constitution_hash": self._constitution.hash,
            "active_cases": len(self._active_cases),
            "total_escalations": self._metrics.total_escalations,
            "total_judgments": self._metrics.total_judgments,
            "total_validations": self._metrics.total_validations,
            "precedents_created": self._metrics.precedents_created,
            "escalation_distribution": self._metrics.escalation_distribution(),
            "artifacts_stored": self._store.count,
        }


def _serialize_dag(dag: TaskDAG) -> str:
    """Serialize a TaskDAG to JSON string for synapse transport."""
    import json

    nodes = {}
    for nid, node in dag.nodes.items():
        nodes[nid] = {
            "node_id": node.node_id,
            "title": node.title,
            "description": node.description,
            "domain": node.domain,
            "required_capabilities": list(node.required_capabilities),
            "depends_on": list(node.depends_on),
            "priority": node.priority,
            "status": node.status.value,
        }
    return json.dumps({"dag_id": dag.dag_id, "goal": dag.goal, "nodes": nodes})
