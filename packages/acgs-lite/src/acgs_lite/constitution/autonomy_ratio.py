"""exp230: Write-to-Draft ratio governance metric — leading over-autonomy indicator.

Tracks the ratio of *committing* (destructive/irreversible) actions vs
*proposing* (draft/reversible) actions per agent session as a leading
indicator of over-autonomy.

Motivation (from Airia Agent Constraints research, 2025):

> An agent's ratio of "commit" actions vs "draft/propose" actions is a
> strong leading indicator of scope creep and over-autonomy — the agent is
> acting without sufficient checkpointing or human oversight.  Rising ratios
> surface as a posture signal *before* any policy is actually violated.

Design
------
``ActionCommitmentClassifier`` labels each action as one of:

- ``COMMIT`` — irreversible / high-commitment (delete, write, send, execute, deploy)
- ``PROPOSE`` — draft / reversible (draft, propose, preview, simulate, check, review)
- ``NEUTRAL`` — neither clearly commit nor propose (read, list, query, analyse)

``CommitmentRatioTracker`` maintains a per-session rolling history and
computes:

- ``commit_ratio`` = commits / (commits + proposes), 0.0 if no proposes
- ``draft_deficit`` = max(0, commits - proposes) — raw excess commit count
- ``ratio_level`` = low / medium / high / critical from configurable thresholds
- ``should_flag`` = True when commit_ratio ≥ ``flag_threshold``

Usage::

    from acgs_lite.constitution.autonomy_ratio import CommitmentRatioTracker

    tracker = CommitmentRatioTracker(agent_id="agent-alpha")
    tracker.record("draft email to client")      # PROPOSE
    tracker.record("preview changes")            # PROPOSE
    tracker.record("send email to all contacts") # COMMIT
    tracker.record("delete old records")         # COMMIT
    tracker.record("deploy to production")       # COMMIT

    state = tracker.current_state()
    print(state.commit_ratio)   # 0.6
    print(state.ratio_level)    # "high"
    print(state.should_flag)    # True
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

# ── action classification ─────────────────────────────────────────────────────

_COMMIT_KEYWORDS: frozenset[str] = frozenset(
    {
        "send",
        "delete",
        "remove",
        "drop",
        "destroy",
        "deploy",
        "execute",
        "run",
        "write",
        "save",
        "store",
        "commit",
        "push",
        "publish",
        "post",
        "submit",
        "apply",
        "update",
        "patch",
        "modify",
        "alter",
        "overwrite",
        "grant",
        "revoke",
        "create",
        "insert",
        "merge",
        "migrate",
        "rollout",
        "broadcast",
        "release",
        "terminate",
        "kill",
        "stop",
        "start",
        "trigger",
    }
)

_PROPOSE_KEYWORDS: frozenset[str] = frozenset(
    {
        "draft",
        "propose",
        "plan",
        "preview",
        "simulate",
        "check",
        "review",
        "analyse",
        "analyze",
        "estimate",
        "suggest",
        "recommend",
        "evaluate",
        "assess",
        "test",
        "validate",
        "verify",
        "inspect",
        "examine",
        "audit",
        "sketch",
        "outline",
        "prototype",
        "mock",
        "sandbox",
        "explore",
        "search",
        "query",
        "list",
        "read",
        "fetch",
        "get",
        "show",
        "describe",
        "explain",
        "compare",
        "diff",
        "report",
    }
)

_TOKEN_RE = re.compile(r"[a-zA-Z]+")


class ActionCommitment(str, Enum):
    """Classification of an agent action by commitment level."""

    COMMIT = "commit"
    PROPOSE = "propose"
    NEUTRAL = "neutral"


def classify_action(action: str) -> ActionCommitment:
    """Classify an action as COMMIT, PROPOSE, or NEUTRAL.

    Uses first-match priority: COMMIT keywords checked first (more dangerous
    to misclassify), then PROPOSE.

    Args:
        action: The action string.

    Returns:
        :class:`ActionCommitment` classification.
    """
    tokens = {t.lower() for t in _TOKEN_RE.findall(action)}
    if tokens & _COMMIT_KEYWORDS:
        return ActionCommitment.COMMIT
    if tokens & _PROPOSE_KEYWORDS:
        return ActionCommitment.PROPOSE
    return ActionCommitment.NEUTRAL


# ── ratio thresholds ─────────────────────────────────────────────────────────

_RATIO_LEVELS: list[tuple[float, str]] = [
    (0.80, "critical"),
    (0.60, "high"),
    (0.40, "medium"),
    (0.0, "low"),
]

_DEFAULT_FLAG_THRESHOLD: float = 0.60  # "high" triggers flagging


@dataclass(frozen=True)
class ActionRecord:
    """Single action with its commitment classification.

    Attributes:
        action: Original action string.
        commitment: COMMIT / PROPOSE / NEUTRAL.
        matched_keywords: Keywords that drove the classification.
    """

    action: str
    commitment: ActionCommitment
    matched_keywords: frozenset[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "commitment": self.commitment.value,
            "matched_keywords": sorted(self.matched_keywords),
        }


@dataclass(frozen=True)
class CommitmentRatioState:
    """Point-in-time snapshot of commit/propose ratio.

    Attributes:
        commit_count: Total COMMIT actions recorded.
        propose_count: Total PROPOSE actions recorded.
        neutral_count: Total NEUTRAL actions recorded.
        commit_ratio: commits / (commits + proposes), 0.0 if no classifiable actions.
        draft_deficit: max(0, commits - proposes) — raw excess commit count.
        ratio_level: Categorical level: low / medium / high / critical.
        should_flag: True when commit_ratio >= flag_threshold.
        flag_threshold: Configured flag threshold.
        total_actions: Total actions (all classifications).
    """

    commit_count: int
    propose_count: int
    neutral_count: int
    commit_ratio: float
    draft_deficit: int
    ratio_level: str
    should_flag: bool
    flag_threshold: float
    total_actions: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "commit_count": self.commit_count,
            "propose_count": self.propose_count,
            "neutral_count": self.neutral_count,
            "commit_ratio": round(self.commit_ratio, 4),
            "draft_deficit": self.draft_deficit,
            "ratio_level": self.ratio_level,
            "should_flag": self.should_flag,
            "flag_threshold": self.flag_threshold,
            "total_actions": self.total_actions,
        }

    def __repr__(self) -> str:
        flag = " [FLAG]" if self.should_flag else ""
        return (
            f"CommitmentRatioState(ratio={self.commit_ratio:.2f}, "
            f"level={self.ratio_level!r}{flag}, "
            f"commits={self.commit_count}, proposes={self.propose_count})"
        )


class CommitmentRatioTracker:
    """Tracks commit/propose ratio for a single agent session.

    Args:
        agent_id: Identifier for the tracked agent.
        flag_threshold: Commit ratio above which ``should_flag`` is True
            (default 0.60 — "high" level).

    Example::

        tracker = CommitmentRatioTracker("agent-alpha")
        tracker.record("draft report")
        tracker.record("send to all users")
        state = tracker.current_state()
        if state.should_flag:
            alert_governance(tracker.summary())
    """

    def __init__(
        self,
        agent_id: str = "",
        *,
        flag_threshold: float = _DEFAULT_FLAG_THRESHOLD,
    ) -> None:
        if not 0.0 < flag_threshold <= 1.0:
            raise ValueError(f"flag_threshold must be in (0, 1], got {flag_threshold}")
        self._agent_id = agent_id
        self._flag_threshold = flag_threshold
        self._history: list[ActionRecord] = []

    @property
    def agent_id(self) -> str:
        """Return the agent identifier for this tracker."""
        return self._agent_id

    def record(self, action: str) -> ActionRecord:
        """Record an action and return its classification.

        Args:
            action: The action string.

        Returns:
            :class:`ActionRecord` with commitment classification.
        """
        tokens = {t.lower() for t in _TOKEN_RE.findall(action)}
        commitment = classify_action(action)
        matched: frozenset[str]
        if commitment == ActionCommitment.COMMIT:
            matched = frozenset(tokens & _COMMIT_KEYWORDS)
        elif commitment == ActionCommitment.PROPOSE:
            matched = frozenset(tokens & _PROPOSE_KEYWORDS)
        else:
            matched = frozenset()
        rec = ActionRecord(action=action, commitment=commitment, matched_keywords=matched)
        self._history.append(rec)
        return rec

    def record_batch(self, actions: list[str]) -> list[ActionRecord]:
        """Record multiple actions in sequence."""
        return [self.record(a) for a in actions]

    def current_state(self) -> CommitmentRatioState:
        """Compute the current commit/propose ratio state."""
        commits = sum(1 for r in self._history if r.commitment == ActionCommitment.COMMIT)
        proposes = sum(1 for r in self._history if r.commitment == ActionCommitment.PROPOSE)
        neutrals = sum(1 for r in self._history if r.commitment == ActionCommitment.NEUTRAL)
        classifiable = commits + proposes
        ratio = commits / classifiable if classifiable > 0 else 0.0
        deficit = max(0, commits - proposes)

        level = "low"
        for threshold, lv in _RATIO_LEVELS:
            if ratio >= threshold:
                level = lv
                break

        return CommitmentRatioState(
            commit_count=commits,
            propose_count=proposes,
            neutral_count=neutrals,
            commit_ratio=ratio,
            draft_deficit=deficit,
            ratio_level=level,
            should_flag=ratio >= self._flag_threshold,
            flag_threshold=self._flag_threshold,
            total_actions=len(self._history),
        )

    def most_committing_actions(self, top_n: int = 5) -> list[ActionRecord]:
        """Return the top *top_n* COMMIT actions."""
        return [r for r in self._history if r.commitment == ActionCommitment.COMMIT][:top_n]

    def summary(self) -> dict[str, Any]:
        """Return a summary dict for logging/reporting."""
        state = self.current_state()
        return {
            "agent_id": self._agent_id,
            **state.to_dict(),
            "top_commit_actions": [r.action for r in self.most_committing_actions(5)],
        }

    def reset(self) -> None:
        """Clear action history."""
        self._history.clear()

    def __repr__(self) -> str:
        state = self.current_state()
        return (
            f"CommitmentRatioTracker("
            f"agent={self._agent_id!r}, "
            f"n={state.total_actions}, "
            f"ratio={state.commit_ratio:.2f}, "
            f"level={state.ratio_level!r})"
        )
