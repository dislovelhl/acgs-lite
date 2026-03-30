"""Constitutional Swarm Miner — Bittensor miner runtime.

Wraps AgentDNA + SwarmExecutor into a Bittensor-compatible miner that:
  1. Receives escalated governance cases (DeliberationSynapse)
  2. Validates constitution hash match
  3. Runs local DNA pre-check on its judgment (443ns)
  4. Returns judgment with cryptographic artifact hash (JudgmentSynapse)

The actual deliberation is delegated to a pluggable handler — the miner
runtime handles protocol, verification, and artifact management.

Bittensor SDK is NOT required — this module uses constitutional_swarm
primitives only. The bittensor.Synapse base class is injected at
deployment time.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from acgs_lite import MACIRole

from constitutional_swarm.artifact import Artifact, ArtifactStore
from constitutional_swarm.bittensor.protocol import MinerConfig, MinerTier, SubnetMetrics
from constitutional_swarm.bittensor.synapses import DeliberationSynapse, JudgmentSynapse
from constitutional_swarm.capability import Capability, CapabilityRegistry
from constitutional_swarm.dna import AgentDNA


class ConstitutionMismatchError(ValueError):
    """Raised when miner's constitution hash doesn't match the request."""


class DNAPreCheckFailedError(RuntimeError):
    """Raised when the miner's own DNA rejects its judgment."""


# Type for the pluggable deliberation handler
DeliberationHandler = Callable[[str, str, dict[str, Any]], Awaitable[tuple[str, str]]]
"""async (task_description, context, metadata) -> (judgment, reasoning)"""


@dataclass
class MinerStats:
    """Runtime statistics for a constitutional miner."""

    judgments_submitted: int = 0
    judgments_accepted: int = 0
    judgments_rejected: int = 0
    dna_pre_check_failures: int = 0
    constitution_mismatches: int = 0
    total_deliberation_time_ms: float = 0.0
    total_dna_latency_ns: int = 0

    @property
    def acceptance_rate(self) -> float:
        if self.judgments_submitted == 0:
            return 0.0
        return self.judgments_accepted / self.judgments_submitted

    @property
    def avg_deliberation_ms(self) -> float:
        if self.judgments_submitted == 0:
            return 0.0
        return self.total_deliberation_time_ms / self.judgments_submitted

    @property
    def avg_dna_ns(self) -> int:
        if self.judgments_submitted == 0:
            return 0
        return self.total_dna_latency_ns // self.judgments_submitted


class ConstitutionalMiner:
    """Bittensor miner runtime for constitutional governance subnet.

    Usage:
        async def my_deliberation(task, context, meta):
            # Human-in-the-loop or AI-assisted deliberation
            return ("Privacy takes precedence", "Article 8 ECHR applies")

        miner = ConstitutionalMiner(
            config=MinerConfig(constitution_path="governance.yaml"),
            deliberation_handler=my_deliberation,
        )
        judgment = await miner.process(synapse)
    """

    def __init__(
        self,
        config: MinerConfig,
        deliberation_handler: DeliberationHandler,
    ) -> None:
        self._config = config
        self._handler = deliberation_handler
        self._dna = AgentDNA.from_yaml(
            config.constitution_path,
            agent_id=config.agent_id,
            maci_role=MACIRole.EXECUTOR,
            strict=config.strict_dna,
            validate_output=config.validate_output,
        )
        self._store = ArtifactStore()
        self._registry = CapabilityRegistry()
        self._registry.register(
            config.agent_id,
            [
                Capability(name=cap, domain=cap)
                for cap in config.capabilities
            ],
        )
        self._stats = MinerStats()
        self._previous_hash: str | None = None

    @property
    def constitution_hash(self) -> str:
        return self._dna.hash

    @property
    def agent_id(self) -> str:
        return self._config.agent_id

    @property
    def tier(self) -> MinerTier:
        return self._config.tier

    @property
    def previous_hash(self) -> str | None:
        return self._previous_hash

    @property
    def stats(self) -> MinerStats:
        return self._stats

    @property
    def dna_stats(self) -> dict[str, Any]:
        return self._dna.stats

    def rotate_constitution(self, new_constitution_path: str) -> None:
        """Rotate to a new constitution, preserving the old hash as a grace window.

        During the grace window, synapses matching either the current or
        previous constitution hash are accepted.
        """
        old_hash = self._dna.hash
        self._dna = AgentDNA.from_yaml(
            new_constitution_path,
            agent_id=self._config.agent_id,
            maci_role=MACIRole.EXECUTOR,
            strict=self._config.strict_dna,
            validate_output=self._config.validate_output,
        )
        self._previous_hash = old_hash

    async def process(self, synapse: DeliberationSynapse) -> JudgmentSynapse:
        """Process an escalated governance case.

        Steps:
          1. Verify constitution hash matches (current or previous during rollover)
          2. Run deliberation handler (human or AI)
          3. DNA pre-check on judgment (443ns)
          4. Create content-addressed artifact
          5. Return JudgmentSynapse

        Raises:
            ConstitutionMismatchError: Hash doesn't match.
            DNAPreCheckFailedError: Miner's own DNA rejects the judgment.
        """
        # Step 1: Verify constitution hash (accept current or previous during rollover)
        accepted_hashes = {self._dna.hash}
        if self._previous_hash is not None:
            accepted_hashes = accepted_hashes | {self._previous_hash}

        if synapse.constitution_hash not in accepted_hashes:
            self._stats.constitution_mismatches += 1
            raise ConstitutionMismatchError(
                f"Expected one of {accepted_hashes}, "
                f"got {synapse.constitution_hash}"
            )

        # Step 2: Run deliberation (with deadline enforcement)
        import asyncio

        start = time.monotonic()
        timeout = synapse.deadline_seconds if synapse.deadline_seconds > 0 else None
        handler_coro = self._handler(
            synapse.context or synapse.task_dag_json,
            synapse.domain,
            {
                "task_id": synapse.task_id,
                "impact_score": synapse.impact_score,
                "impact_vector": synapse.impact_vector,
                "escalation_type": synapse.escalation_type,
                "required_capabilities": synapse.required_capabilities,
            },
        )
        if timeout is not None:
            judgment, reasoning = await asyncio.wait_for(handler_coro, timeout=timeout)
        else:
            judgment, reasoning = await handler_coro
        elapsed_ms = (time.monotonic() - start) * 1000
        self._stats.total_deliberation_time_ms += elapsed_ms

        # Step 3: DNA pre-check (443ns)
        dna_result = self._dna.validate(judgment)
        self._stats.total_dna_latency_ns += dna_result.latency_ns

        if not dna_result.valid:
            self._stats.dna_pre_check_failures += 1
            raise DNAPreCheckFailedError(
                f"DNA rejected judgment: {dna_result.violations}"
            )

        # Step 4: Create artifact
        artifact = Artifact(
            artifact_id=uuid.uuid4().hex[:12],
            task_id=synapse.task_id,
            agent_id=self._config.agent_id,
            content_type="governance_judgment",
            content=judgment,
            domain=synapse.domain,
            constitutional_hash=self._dna.hash,
            metadata={"reasoning": reasoning},
        )
        self._store.publish(artifact)

        # Step 5: Return synapse
        self._stats.judgments_submitted += 1
        return JudgmentSynapse(
            task_id=synapse.task_id,
            miner_uid=self._config.agent_id,
            judgment=judgment,
            reasoning=reasoning,
            artifact_hash=artifact.content_hash,
            constitutional_hash=self._dna.hash,
            dna_valid=dna_result.valid,
            dna_violations=dna_result.violations,
            dna_latency_ns=dna_result.latency_ns,
            domain=synapse.domain,
        )

    def record_acceptance(self) -> None:
        """Called when validator accepts this miner's judgment."""
        self._stats.judgments_accepted += 1

    def record_rejection(self) -> None:
        """Called when validator rejects this miner's judgment."""
        self._stats.judgments_rejected += 1
