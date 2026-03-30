"""Constitutional Swarm Validator — Bittensor validator runtime.

Wraps ConstitutionalMesh + GovernanceManifold into a Bittensor-compatible
validator that:
  1. Receives miner judgments (JudgmentSynapse)
  2. Runs full mesh validation (DNA pre-check + peer votes + Merkle proof)
  3. Updates trust manifold (Sinkhorn-Knopp projection)
  4. Returns grading result with cryptographic proof (ValidationSynapse)
  5. Computes TAO emission weights from projected trust matrix

Bittensor SDK is NOT required — this module uses constitutional_swarm
primitives only.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from acgs_lite import Constitution

from constitutional_swarm.bittensor.protocol import (
    TIER_TAO_MULTIPLIER,
    MinerTier,
    ValidatorConfig,
)
from constitutional_swarm.bittensor.synapses import JudgmentSynapse, ValidationSynapse
from constitutional_swarm.mesh import ConstitutionalMesh, MeshResult


@dataclass
class ValidatorStats:
    """Runtime statistics for a constitutional validator."""

    validations_performed: int = 0
    judgments_accepted: int = 0
    judgments_rejected: int = 0
    total_validation_time_ms: float = 0.0
    constitution_mismatches: int = 0

    @property
    def acceptance_rate(self) -> float:
        if self.validations_performed == 0:
            return 0.0
        return self.judgments_accepted / self.validations_performed

    @property
    def avg_validation_ms(self) -> float:
        if self.validations_performed == 0:
            return 0.0
        return self.total_validation_time_ms / self.validations_performed


class UnknownMinerError(ValueError):
    """Raised when an unregistered miner submits a judgment."""


class ConstitutionalValidator:
    """Bittensor validator runtime for constitutional governance subnet.

    Usage:
        validator = ConstitutionalValidator(
            config=ValidatorConfig(constitution_path="governance.yaml"),
        )
        # Register miners as mesh participants
        validator.register_miner("miner-01", domain="privacy")
        validator.register_miner("miner-02", domain="privacy")
        validator.register_miner("miner-03", domain="finance")

        # Validate a miner's judgment
        result = validator.validate(judgment_synapse)

        # Get TAO emission weights
        weights = validator.compute_emission_weights()
    """

    def __init__(self, config: ValidatorConfig) -> None:
        self._config = config
        self._constitution = Constitution.from_yaml(config.constitution_path)
        self._mesh = ConstitutionalMesh(
            self._constitution,
            peers_per_validation=config.peers_per_validation,
            quorum=config.quorum,
            use_manifold=config.use_manifold,
        )
        self._stats = ValidatorStats()
        self._known_miners: set[str] = set()
        self._miner_tiers: dict[str, MinerTier] = {}
        self._miner_domains: dict[str, str] = {}
        self._previous_hash: str | None = None

    @property
    def constitution_hash(self) -> str:
        return self._constitution.hash

    @property
    def previous_hash(self) -> str | None:
        return self._previous_hash

    def rotate_constitution(self, new_constitution: Constitution) -> None:
        """Rotate to a new constitution, preserving the old hash as a grace window.

        During the grace window, synapses matching either the current or
        previous constitution hash are accepted. Call this again to close
        the window (the previous hash advances to the now-old current hash).
        """
        old_hash = self._constitution.hash
        self._constitution = new_constitution
        self._mesh = ConstitutionalMesh(
            new_constitution,
            peers_per_validation=self._config.peers_per_validation,
            quorum=self._config.quorum,
            use_manifold=self._config.use_manifold,
        )
        # Re-register all known miners in the new mesh
        for miner_uid in self._known_miners:
            domain = self._miner_domains.get(miner_uid, "")
            self._mesh.register_agent(miner_uid, domain=domain)
        self._previous_hash = old_hash

    @property
    def stats(self) -> ValidatorStats:
        return self._stats

    @property
    def mesh(self) -> ConstitutionalMesh:
        return self._mesh

    def register_miner(
        self,
        miner_uid: str,
        domain: str = "",
        tier: MinerTier = MinerTier.APPRENTICE,
    ) -> None:
        """Register a miner as a mesh participant.

        Adds the miner to the known set, mesh, tier map, and domain map.
        Only miners registered via this method may submit judgments.
        """
        self._known_miners = self._known_miners | {miner_uid}
        self._mesh.register_agent(miner_uid, domain=domain)
        self._miner_tiers = {**self._miner_tiers, miner_uid: tier}
        self._miner_domains = {**self._miner_domains, miner_uid: domain}

    def unregister_miner(self, miner_uid: str) -> None:
        """Remove a miner from the mesh."""
        self._mesh.unregister_agent(miner_uid)
        self._known_miners = self._known_miners - {miner_uid}
        self._miner_tiers = {k: v for k, v in self._miner_tiers.items() if k != miner_uid}
        self._miner_domains = {k: v for k, v in self._miner_domains.items() if k != miner_uid}

    def validate(self, synapse: JudgmentSynapse) -> ValidationSynapse:
        """Validate a miner's governance judgment.

        Steps:
          1. Verify constitution hash matches (current or previous during rollover)
          2. Reject unknown miners (must be pre-registered)
          3. Run full mesh validation (DNA + peers + Merkle proof)
          4. Return ValidationSynapse with proof

        The mesh internally:
          a. Runs DNA pre-check on the judgment content (443ns)
          b. Assigns random peers (excluding the miner — MACI)
          c. Each peer validates via their own DNA
          d. Quorum decides acceptance
          e. Generates Merkle proof
          f. Updates reputation scores
          g. Projects trust onto governance manifold

        Raises:
            UnknownMinerError: If the miner is not pre-registered.
        """
        start = time.monotonic()

        # Step 1: Verify constitution hash (accept current or previous during rollover)
        accepted_hashes = {self._constitution.hash}
        if self._previous_hash is not None:
            accepted_hashes = accepted_hashes | {self._previous_hash}

        if synapse.constitutional_hash not in accepted_hashes:
            self._stats.constitution_mismatches += 1
            return ValidationSynapse(
                task_id=synapse.task_id,
                assignment_id="",
                accepted=False,
                votes_for=0,
                votes_against=0,
                quorum_met=False,
                constitutional_hash=self._constitution.hash,
            )

        # Step 2: Reject unknown miners — no auto-registration
        if synapse.miner_uid not in self._known_miners:
            raise UnknownMinerError(
                f"Miner {synapse.miner_uid!r} is not registered. "
                f"Call register_miner() before submitting judgments."
            )

        # Step 3: Full mesh validation
        result = self._mesh.full_validation(
            producer_id=synapse.miner_uid,
            content=synapse.judgment,
            artifact_id=synapse.artifact_hash,
        )

        elapsed_ms = (time.monotonic() - start) * 1000
        self._stats.total_validation_time_ms += elapsed_ms
        self._stats.validations_performed += 1

        if result.accepted:
            self._stats.judgments_accepted += 1
        else:
            self._stats.judgments_rejected += 1

        # Step 4: Build ValidationSynapse
        return self._result_to_synapse(synapse.task_id, result)

    def compute_emission_weights(
        self,
        miner_uids: list[str] | None = None,
    ) -> dict[str, float]:
        """Compute TAO emission weights from the governance manifold.

        Weight formula:
          base_weight = manifold trust (column sum in projected matrix)
          tier_multiplier = TIER_TAO_MULTIPLIER[miner_tier]
          reputation = mesh reputation score
          final_weight = base_weight * tier_multiplier * reputation

        Returns normalized weights (sum to 1.0).
        """
        uids = miner_uids or list(self._miner_tiers.keys())
        if not uids:
            return {}

        raw_weights: dict[str, float] = {}
        for uid in uids:
            # Base: reputation from mesh
            try:
                reputation = self._mesh.get_reputation(uid)
            except KeyError:
                reputation = 1.0

            # Tier multiplier
            tier = self._miner_tiers.get(uid, MinerTier.APPRENTICE)
            multiplier = TIER_TAO_MULTIPLIER[tier]

            raw_weights[uid] = reputation * multiplier

        # Normalize to sum to 1.0
        total = sum(raw_weights.values())
        if total == 0:
            return {uid: 1.0 / len(uids) for uid in uids}
        return {uid: w / total for uid, w in raw_weights.items()}

    def get_miner_reputation(self, miner_uid: str) -> float:
        """Get a miner's current reputation score."""
        return self._mesh.get_reputation(miner_uid)

    def summary(self) -> dict[str, Any]:
        """Combined validator + mesh + manifold statistics."""
        return {
            "validator_stats": {
                "validations": self._stats.validations_performed,
                "accepted": self._stats.judgments_accepted,
                "rejected": self._stats.judgments_rejected,
                "acceptance_rate": self._stats.acceptance_rate,
                "avg_validation_ms": self._stats.avg_validation_ms,
            },
            "mesh": self._mesh.summary(),
            "manifold": self._mesh.manifold_summary(),
            "registered_miners": len(self._miner_tiers),
            "constitution_hash": self._constitution.hash,
        }

    def _result_to_synapse(
        self,
        task_id: str,
        result: MeshResult,
    ) -> ValidationSynapse:
        proof = result.proof
        return ValidationSynapse(
            task_id=task_id,
            assignment_id=result.assignment_id,
            accepted=result.accepted,
            votes_for=result.votes_for,
            votes_against=result.votes_against,
            quorum_met=result.quorum_met,
            proof_root_hash=proof.root_hash if proof else "",
            proof_vote_hashes=proof.vote_hashes if proof else (),
            proof_content_hash=proof.content_hash if proof else "",
            constitutional_hash=result.constitutional_hash,
            trust_update=self._mesh.manifold_summary() or {},
        )
