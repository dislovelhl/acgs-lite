"""Constitution deployer: applies approved rules and rotates the constitutional hash."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from acgs_lite.constitution.constitution import Constitution
    from acgs_lite.engine.synthesis import SuggestedRule

logger = logging.getLogger(__name__)


class ConstitutionDeployer:
    """Applies approved governance proposals to the live constitution."""

    APPROVAL_CONFIDENCE_THRESHOLD: float = 0.67

    def deploy_approved_rules(
        self,
        current_constitution: Constitution,
        approved_rules: list[SuggestedRule],
        nmc_confidence: float,
    ) -> tuple[Constitution, str]:
        """Apply approved rules, compute new hash.

        Returns:
            (new_constitution, new_canonical_hash)
        Raises:
            ValueError: if confidence below threshold.
        """
        if nmc_confidence < self.APPROVAL_CONFIDENCE_THRESHOLD:
            raise ValueError(
                f"NMC confidence {nmc_confidence:.0%} below required "
                f"{self.APPROVAL_CONFIDENCE_THRESHOLD:.0%}"
            )

        # Import here to avoid circular at module load time
        from acgs_lite.constitution.constitution import Constitution  # noqa: F401
        from acgs_lite.constitution.rule import Rule

        new_rules = list(current_constitution.rules)
        for sr in approved_rules:
            new_rule = Rule(
                id=sr.rule_id,
                text=sr.rule_text,
                severity=sr.severity,
                category=sr.category,
                keywords=list(sr.keywords),
                tags=["synthesized", f"nmc-{nmc_confidence:.0%}"],
            )
            new_rules.append(new_rule)
            logger.info("Deploying synthesized rule %s", sr.rule_id)

        new_constitution = current_constitution.model_copy(update={"rules": new_rules})
        new_hash = new_constitution.hash
        logger.info(
            "Constitution updated: rules_added=%d new_hash=%s",
            len(approved_rules),
            new_hash,
        )
        return new_constitution, new_hash
