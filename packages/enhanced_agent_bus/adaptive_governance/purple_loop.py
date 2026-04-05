"""Purple team loop: orchestrates red-team/blue-team adversarial improvement.

Runs iterative cycles of attack → evaluate → defend → recommend until
the bypass rate converges or max rounds are exhausted.

MACI roles enforced:
- Red team: OBSERVER (generates inputs, reads results)
- Judge: VALIDATOR (scores results)
- Blue team: PROPOSER (recommends changes)
- Human: EXECUTOR (approves/rejects via AmendmentRecommender pipeline)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .blue_team import GovernanceBlueTeam, RulePatch
from .red_team import GovernanceRedTeam, RedTeamReport

logger = logging.getLogger(__name__)


@dataclass
class PurpleTeamRound:
    """Results from a single purple team round."""

    round_number: int
    red_team_report: RedTeamReport
    patches: list[RulePatch] = field(default_factory=list)
    bypass_rate: float = 0.0


@dataclass
class PurpleTeamReport:
    """Full purple team loop results."""

    rounds: list[PurpleTeamRound] = field(default_factory=list)
    converged: bool = False

    @property
    def total_attacks(self) -> int:
        return sum(r.red_team_report.total_attacks for r in self.rounds)

    @property
    def total_bypasses(self) -> int:
        return sum(len(r.red_team_report.successful_bypasses) for r in self.rounds)

    @property
    def all_patches(self) -> list[RulePatch]:
        patches: list[RulePatch] = []
        for r in self.rounds:
            patches.extend(r.patches)
        return patches

    @property
    def final_bypass_rate(self) -> float:
        if not self.rounds:
            return 0.0
        return self.rounds[-1].bypass_rate

    @property
    def bypass_test_cases(self) -> list[dict[str, Any]]:
        """Convert successful bypasses into GovernanceTestCase-compatible dicts.

        These become permanent regression tests with expected_decision="deny".
        """
        cases: list[dict[str, Any]] = []
        seen: set[str] = set()
        for round_result in self.rounds:
            for bypass in round_result.red_team_report.successful_bypasses:
                text = bypass.attack.input_text
                if text in seen:
                    continue
                seen.add(text)
                cases.append(
                    {
                        "name": f"purple-bypass-{bypass.attack.rule_id}-{len(cases)}",
                        "input_text": text,
                        "expected_decision": "deny",
                        "expected_rules_triggered": [bypass.attack.rule_id],
                        "tags": ["purple-team", "auto-generated", bypass.attack.strategy],
                    }
                )
        return cases

    def summary(self) -> str:
        return (
            f"PurpleTeam: {len(self.rounds)} rounds, "
            f"{self.total_attacks} attacks, "
            f"{self.total_bypasses} bypasses, "
            f"final rate={self.final_bypass_rate:.0%}, "
            f"converged={self.converged}, "
            f"{len(self.all_patches)} patches proposed"
        )


class PurpleTeamLoop:
    """Orchestrates red-team/blue-team adversarial improvement cycles.

    Parameters
    ----------
    red_team:
        The ``GovernanceRedTeam`` instance.
    blue_team:
        The ``GovernanceBlueTeam`` instance.
    max_rounds:
        Maximum number of attack-defend cycles.
    convergence_threshold:
        Stop when bypass rate improvement between rounds < this value.
    attacks_per_rule:
        Number of attacks to generate per rule per round.
    """

    def __init__(
        self,
        red_team: GovernanceRedTeam,
        blue_team: GovernanceBlueTeam,
        *,
        max_rounds: int = 5,
        convergence_threshold: float = 0.05,
        attacks_per_rule: int = 10,
    ) -> None:
        self.red_team = red_team
        self.blue_team = blue_team
        self.max_rounds = max_rounds
        self.convergence_threshold = convergence_threshold
        self.attacks_per_rule = attacks_per_rule

    async def run_loop(
        self,
        target_rules: list[str] | None = None,
    ) -> PurpleTeamReport:
        """Run the full purple team loop until convergence or max rounds."""
        report = PurpleTeamReport()
        prev_bypass_rate = 1.0

        for round_num in range(1, self.max_rounds + 1):
            logger.info("purple_team_round_start", extra={"round": round_num})

            # Red team attacks
            red_report = await self.red_team.run_campaign(
                rules=target_rules,
                attacks_per_rule=self.attacks_per_rule,
            )

            # Blue team defense
            patches = self.blue_team.analyze_bypasses(red_report)

            round_result = PurpleTeamRound(
                round_number=round_num,
                red_team_report=red_report,
                patches=patches,
                bypass_rate=red_report.bypass_rate,
            )
            report.rounds.append(round_result)

            logger.info(
                "purple_team_round_complete",
                extra={
                    "round": round_num,
                    "attacks": red_report.total_attacks,
                    "bypasses": len(red_report.successful_bypasses),
                    "bypass_rate": red_report.bypass_rate,
                    "patches": len(patches),
                },
            )

            # Check convergence
            improvement = prev_bypass_rate - red_report.bypass_rate
            if improvement < self.convergence_threshold and round_num > 1:
                report.converged = True
                break

            prev_bypass_rate = red_report.bypass_rate

        return report


__all__ = [
    "PurpleTeamLoop",
    "PurpleTeamReport",
    "PurpleTeamRound",
]
