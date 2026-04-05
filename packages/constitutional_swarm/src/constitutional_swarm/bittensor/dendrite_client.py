"""Validator dendrite client for querying miners over bittensor protocol.

In local mode (no bittensor installed), routes queries to registered
MinerAxonServer instances directly. In testnet mode, wraps bt.Dendrite
for real network communication.

Usage (local testing):
    client = ValidatorDendriteClient(constitution_path="governance.yaml")
    client.register_local_miner(axon_server)
    judgments = await client.query_miners(deliberation_synapse)

Usage (real bittensor):
    client = ValidatorDendriteClient(
        constitution_path="governance.yaml",
        wallet=wallet,
        metagraph=metagraph,
    )
    judgments = await client.query_miners(deliberation_synapse)
"""

from __future__ import annotations

import asyncio
from typing import Any

from acgs_lite import Constitution
from constitutional_swarm.bittensor.synapse_adapter import (
    HAS_BITTENSOR,
    GovernanceDeliberation,
    bt_to_judgment,
    deliberation_to_bt,
)
from constitutional_swarm.bittensor.synapses import (
    DeliberationSynapse,
    JudgmentSynapse,
)

if HAS_BITTENSOR:
    import bittensor as bt


class ValidatorDendriteClient:
    """Sends governance cases to miners and collects judgment responses.

    Supports two modes:
      - Local: queries registered MinerAxonServer instances directly
      - Network: uses bt.Dendrite to query remote miners via axon

    In both modes, the public API is the same: query_miners() returns
    a list of JudgmentSynapse from successful responses.
    """

    def __init__(
        self,
        constitution_path: str,
        *,
        wallet: Any | None = None,
        metagraph: Any | None = None,
    ) -> None:
        self._constitution = Constitution.from_yaml(constitution_path)
        self._local_miners: list[Any] = []  # MinerAxonServer instances
        self._wallet = wallet
        self._metagraph = metagraph
        self._dendrite: Any | None = None

        if HAS_BITTENSOR and wallet is not None:
            self._dendrite = bt.Dendrite(wallet=wallet)

    @property
    def constitution_hash(self) -> str:
        return self._constitution.hash

    def register_local_miner(self, axon_server: Any) -> None:
        """Register a local MinerAxonServer for testing without bittensor."""
        self._local_miners.append(axon_server)

    async def query_miners(
        self,
        deliberation: DeliberationSynapse,
        *,
        timeout: float | None = None,
    ) -> list[JudgmentSynapse]:
        """Send a governance case to all available miners.

        Returns JudgmentSynapse instances from miners that responded
        successfully. Failed responses (errors, timeouts, constitution
        mismatches) are silently filtered.

        Args:
            deliberation: The governance case to send to miners.
            timeout: Optional per-miner timeout in seconds.

        Returns:
            List of successful JudgmentSynapse responses.
        """
        if self._dendrite is not None and self._metagraph is not None:
            return await self._query_network(deliberation, timeout=timeout)
        return await self._query_local(deliberation, timeout=timeout)

    async def _query_local(
        self,
        deliberation: DeliberationSynapse,
        *,
        timeout: float | None = None,
    ) -> list[JudgmentSynapse]:
        """Query local MinerAxonServer instances directly."""
        if not self._local_miners:
            return []

        bt_syn_template = deliberation_to_bt(deliberation)

        async def _query_one(server: Any) -> JudgmentSynapse | None:
            # Each miner gets its own copy of the synapse
            syn = GovernanceDeliberation(**bt_syn_template.model_dump())
            try:
                if timeout is not None:
                    result = await asyncio.wait_for(
                        server.forward(syn), timeout=timeout,
                    )
                else:
                    result = await server.forward(syn)

                if result.has_response and result.error_message is None:
                    return bt_to_judgment(result)
            except (TimeoutError, ValueError):
                pass
            return None

        results = await asyncio.gather(
            *[_query_one(s) for s in self._local_miners],
            return_exceptions=True,
        )
        return [r for r in results if isinstance(r, JudgmentSynapse)]

    async def _query_network(
        self,
        deliberation: DeliberationSynapse,
        *,
        timeout: float | None = None,
    ) -> list[JudgmentSynapse]:
        """Query remote miners via bt.Dendrite.

        Sends the GovernanceDeliberation to all active axons in the
        metagraph and collects successful responses.
        """
        bt_syn = deliberation_to_bt(deliberation)
        if timeout is not None:
            bt_syn.deadline_seconds = int(timeout)

        axons = self._metagraph.axons  # type: ignore[union-attr]
        responses = await self._dendrite(  # type: ignore[misc]
            axons=axons,
            synapse=bt_syn,
            timeout=timeout or bt_syn.deadline_seconds,
        )

        judgments: list[JudgmentSynapse] = []
        for resp in responses:
            if not isinstance(resp, GovernanceDeliberation):
                continue
            if resp.has_response and resp.error_message is None:
                try:
                    judgments.append(bt_to_judgment(resp))
                except ValueError:
                    continue
        return judgments
