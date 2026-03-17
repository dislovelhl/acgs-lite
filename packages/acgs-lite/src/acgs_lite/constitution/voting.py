"""exp179: Condorcet ranked-choice voting for multi-stakeholder governance.

Enables collaborative policy decisions where multiple agents or humans
rank alternatives. Pairwise comparison finds the Condorcet winner (the
option that beats every other option head-to-head), with Smith set
fallback when no pure winner exists.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any


class BallotStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class PolicyBallot:
    """A single voter's ranked preference over policy options.

    Args:
        voter_id: Identifier of the voter.
        ranking: Ordered list of option IDs, most preferred first.
        weight: Vote weight (default 1.0, supports quadratic/delegated).
        timestamp: ISO-8601 submission time.
    """

    __slots__ = ("voter_id", "ranking", "weight", "timestamp", "metadata")

    def __init__(
        self,
        *,
        voter_id: str,
        ranking: list[str],
        weight: float = 1.0,
        timestamp: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not ranking:
            raise ValueError("Ranking must contain at least one option")
        if len(ranking) != len(set(ranking)):
            raise ValueError("Ranking contains duplicate options")
        self.voter_id = voter_id
        self.ranking = list(ranking)
        self.weight = weight
        self.timestamp = timestamp or datetime.now(timezone.utc).isoformat()
        self.metadata = metadata or {}

    def prefers(self, a: str, b: str) -> int:
        """Return 1 if voter prefers a over b, -1 if b over a, 0 if tied."""
        a_in = a in self.ranking
        b_in = b in self.ranking
        if a_in and b_in:
            return 1 if self.ranking.index(a) < self.ranking.index(b) else -1
        if a_in:
            return 1
        if b_in:
            return -1
        return 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "voter_id": self.voter_id,
            "ranking": self.ranking,
            "weight": self.weight,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }

    def __repr__(self) -> str:
        return f"PolicyBallot({self.voter_id!r}, ranking={self.ranking!r})"


class CondorcetVoting:
    """Condorcet ranked-choice voting for governance policy decisions.

    Collects ranked ballots from voters and determines the winner via
    pairwise comparison. If a Condorcet winner exists (beats all others
    head-to-head), it is returned. Otherwise, the Smith set (smallest
    set of candidates that beat all non-members) is reported.

    Args:
        question: The policy decision being voted on.
        options: List of option IDs voters can rank.
        quorum: Minimum number of ballots required to close.

    Usage::

        vote = CondorcetVoting(
            question="Which severity for SAFE-005?",
            options=["critical", "high", "medium"],
            quorum=3,
        )
        vote.cast(voter_id="alice", ranking=["critical", "high", "medium"])
        vote.cast(voter_id="bob", ranking=["high", "critical", "medium"])
        vote.cast(voter_id="carol", ranking=["critical", "medium", "high"])
        result = vote.resolve()
        # result["winner"] == "critical"
    """

    __slots__ = (
        "question",
        "options",
        "quorum",
        "status",
        "_ballots",
        "_created_at",
        "_closed_at",
        "_result",
    )

    def __init__(
        self,
        *,
        question: str,
        options: list[str],
        quorum: int = 1,
    ) -> None:
        if len(options) < 2:
            raise ValueError("Need at least 2 options")
        if len(options) != len(set(options)):
            raise ValueError("Duplicate options")
        self.question = question
        self.options = list(options)
        self.quorum = max(1, quorum)
        self.status = BallotStatus.OPEN
        self._ballots: dict[str, PolicyBallot] = {}
        self._created_at = datetime.now(timezone.utc).isoformat()
        self._closed_at = ""
        self._result: dict[str, Any] | None = None

    def cast(
        self,
        *,
        voter_id: str,
        ranking: list[str],
        weight: float = 1.0,
        metadata: dict[str, Any] | None = None,
    ) -> PolicyBallot:
        """Cast or update a ranked ballot.

        Args:
            voter_id: Voter identifier.
            ranking: Options ranked most-preferred first.
            weight: Vote weight (default 1.0).
            metadata: Optional voter metadata.

        Returns:
            The submitted PolicyBallot.

        Raises:
            ValueError: If voting is closed or options are invalid.
        """
        if self.status != BallotStatus.OPEN:
            raise ValueError(f"Voting is {self.status.value}")
        for opt in ranking:
            if opt not in self.options:
                raise ValueError(f"Unknown option: {opt!r}")

        ballot = PolicyBallot(
            voter_id=voter_id,
            ranking=ranking,
            weight=weight,
            metadata=metadata,
        )
        self._ballots[voter_id] = ballot
        return ballot

    def _build_pairwise_matrix(self) -> dict[str, dict[str, float]]:
        """Build weighted pairwise preference matrix."""
        matrix: dict[str, dict[str, float]] = {
            a: {b: 0.0 for b in self.options} for a in self.options
        }
        for ballot in self._ballots.values():
            for i, a in enumerate(self.options):
                for j, b in enumerate(self.options):
                    if i >= j:
                        continue
                    pref = ballot.prefers(a, b)
                    if pref > 0:
                        matrix[a][b] += ballot.weight
                    elif pref < 0:
                        matrix[b][a] += ballot.weight
        return matrix

    def _find_condorcet_winner(self, matrix: dict[str, dict[str, float]]) -> str | None:
        """Find option that beats all others in pairwise comparison."""
        for candidate in self.options:
            if all(
                matrix[candidate][other] > matrix[other][candidate]
                for other in self.options
                if other != candidate
            ):
                return candidate
        return None

    def _find_smith_set(self, matrix: dict[str, dict[str, float]]) -> list[str]:
        """Find the Smith set (smallest dominating set)."""
        opts = list(self.options)
        n = len(opts)

        def beats(a: str, b: str) -> bool:
            return matrix[a][b] > matrix[b][a]

        smith: set[str] = set(opts)
        changed = True
        while changed:
            changed = False
            for candidate in list(smith):
                beaten_by_outside = False
                for other in opts:
                    if other not in smith and beats(other, candidate):
                        beaten_by_outside = True
                        break
                if beaten_by_outside:
                    continue
                can_remove = True
                for remaining in smith:
                    if remaining == candidate:
                        continue
                    if not beats(remaining, candidate) and remaining in smith:
                        can_remove = False
                        break
                if can_remove and len(smith) > 1:
                    _non_smith_beats_all = True
                    for other in smith:
                        if other == candidate:
                            continue
                        if not all(
                            beats(other, ext)
                            for ext in opts
                            if ext not in smith or ext == candidate
                        ):
                            _non_smith_beats_all = False
                            break

        # Simpler approach: iteratively remove dominated candidates
        smith = set(opts)
        for _ in range(n):
            to_remove: set[str] = set()
            for candidate in smith:
                if all(
                    matrix[other][candidate] > matrix[candidate][other]
                    for other in smith
                    if other != candidate
                ):
                    to_remove.add(candidate)
            if to_remove and len(smith) - len(to_remove) >= 1:
                smith -= to_remove
            else:
                break

        return sorted(smith)

    def resolve(self) -> dict[str, Any]:
        """Close voting and determine the winner.

        Returns:
            dict with ``winner`` (str or None), ``smith_set`` (list),
            ``pairwise_matrix``, ``ballot_count``, ``quorum_met``,
            ``method`` (``"condorcet"`` or ``"smith_set"``).

        Raises:
            ValueError: If already resolved or cancelled.
        """
        if self.status == BallotStatus.CLOSED:
            if self._result:
                return self._result
            raise ValueError("Already resolved")
        if self.status == BallotStatus.CANCELLED:
            raise ValueError("Voting was cancelled")

        self.status = BallotStatus.CLOSED
        self._closed_at = datetime.now(timezone.utc).isoformat()

        quorum_met = len(self._ballots) >= self.quorum
        matrix = self._build_pairwise_matrix()

        if not quorum_met:
            self._result = {
                "winner": None,
                "smith_set": [],
                "method": "quorum_not_met",
                "pairwise_matrix": matrix,
                "ballot_count": len(self._ballots),
                "quorum": self.quorum,
                "quorum_met": False,
                "question": self.question,
            }
            return self._result

        winner = self._find_condorcet_winner(matrix)
        smith = self._find_smith_set(matrix)

        pairwise_summary: dict[str, dict[str, str]] = {}
        for a in self.options:
            pairwise_summary[a] = {}
            for b in self.options:
                if a == b:
                    continue
                ma, mb = matrix[a][b], matrix[b][a]
                pairwise_summary[a][b] = f"{ma:.1f}-{mb:.1f}"

        self._result = {
            "winner": winner,
            "smith_set": smith,
            "method": "condorcet" if winner else "smith_set",
            "pairwise_matrix": matrix,
            "pairwise_summary": pairwise_summary,
            "ballot_count": len(self._ballots),
            "quorum": self.quorum,
            "quorum_met": True,
            "question": self.question,
        }
        return self._result

    def cancel(self, reason: str = "") -> None:
        if self.status != BallotStatus.OPEN:
            raise ValueError(f"Cannot cancel: status is {self.status.value}")
        self.status = BallotStatus.CANCELLED
        self._closed_at = datetime.now(timezone.utc).isoformat()

    def ballots(self) -> list[PolicyBallot]:
        return list(self._ballots.values())

    def summary(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "options": self.options,
            "status": self.status.value,
            "ballot_count": len(self._ballots),
            "quorum": self.quorum,
            "quorum_met": len(self._ballots) >= self.quorum,
            "voters": sorted(self._ballots.keys()),
            "created_at": self._created_at,
            "closed_at": self._closed_at,
            "has_result": self._result is not None,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.summary(),
            "ballots": [b.to_dict() for b in self._ballots.values()],
            "result": self._result,
        }

    def __repr__(self) -> str:
        return (
            f"CondorcetVoting({self.question!r}, "
            f"options={self.options!r}, "
            f"{self.status.value}, "
            f"{len(self._ballots)}/{self.quorum} ballots)"
        )
