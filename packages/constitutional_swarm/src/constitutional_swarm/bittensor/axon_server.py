"""Miner axon server wrapping ConstitutionalMiner for bittensor protocol.

Provides handler functions compatible with bittensor's axon.attach() API:
  - forward_fn: async handler that processes governance cases
  - blacklist_fn: rejects requests (placeholder, always allows)
  - verify_fn: validates required fields before processing
  - priority_fn: ranks requests by impact score

Usage (local testing):
    server = MinerAxonServer(miner)
    result = await server.forward(governance_synapse)

Usage (real bittensor):
    axon = bt.Axon(wallet=wallet)
    server = MinerAxonServer(miner)
    axon.attach(
        forward_fn=server.forward,
        blacklist_fn=server.blacklist,
        verify_fn=server.verify,
        priority_fn=server.priority,
    )
"""

from __future__ import annotations

import time

from constitutional_swarm.bittensor.miner import (
    ConstitutionalMiner,
    ConstitutionMismatchError,
    DNAPreCheckFailedError,
)
from constitutional_swarm.bittensor.synapse_adapter import (
    GovernanceDeliberation,
    bt_to_deliberation,
    judgment_to_bt,
)


class MinerAxonServer:
    """Wraps a ConstitutionalMiner into bittensor axon-compatible handlers.

    The server converts between the bt.Synapse wire format
    (GovernanceDeliberation) and the internal frozen dataclass synapses,
    delegating actual processing to the ConstitutionalMiner.
    """

    def __init__(self, miner: ConstitutionalMiner) -> None:
        self._miner = miner

    @property
    def miner(self) -> ConstitutionalMiner:
        return self._miner

    async def forward(
        self, synapse: GovernanceDeliberation,
    ) -> GovernanceDeliberation:
        """Process a governance deliberation request.

        Converts the bt synapse to an internal DeliberationSynapse,
        runs it through the ConstitutionalMiner, and fills response
        fields on the bt synapse.

        On error (constitution mismatch, DNA failure, timeout), the
        error_message field is set instead of raising — following
        bittensor's pattern where forward_fn should not raise.
        """
        try:
            delib = bt_to_deliberation(synapse)
            judgment = await self._miner.process(delib)
            judgment_to_bt(judgment, synapse)
            synapse.response_timestamp = time.time()
        except ConstitutionMismatchError as exc:
            synapse.error_message = f"Constitution mismatch: {exc}"
        except DNAPreCheckFailedError as exc:
            synapse.error_message = f"DNA pre-check failed: {exc}"
        except TimeoutError:
            synapse.error_message = "Deliberation timed out"
        except Exception as exc:  # noqa: BLE001 - bt forward handlers must fail closed without raising
            synapse.error_message = f"Processing error: {type(exc).__name__}"
        return synapse

    def blacklist(self, synapse: GovernanceDeliberation) -> bool:
        """Decide whether to reject a request outright.

        Returns True to blacklist (reject), False to allow.
        Currently allows all requests — tier-based filtering
        will be added post-testnet validation.
        """
        return False

    def verify(self, synapse: GovernanceDeliberation) -> None:
        """Validate required fields before processing.

        Raises ValueError if critical fields are missing.
        Called by bittensor's axon before forward_fn.
        """
        if not synapse.task_id:
            raise ValueError("task_id is required")
        if not synapse.constitution_hash:
            raise ValueError("constitution_hash is required")
        if not synapse.task_dag_json:
            raise ValueError("task_dag_json is required")

    def priority(self, synapse: GovernanceDeliberation) -> float:
        """Assign processing priority based on impact score.

        Higher impact cases get processed first when the miner
        has a backlog of requests.
        """
        return synapse.impact_score
