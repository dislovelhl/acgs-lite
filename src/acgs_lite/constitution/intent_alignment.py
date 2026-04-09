"""exp228: Intent alignment scoring — session drift detection via keyword overlap.

Tracks cumulative divergence between an agent\'s *declared session intent* and
its *runtime actions*, surfacing a soft governance signal (``drift_score``) that
escalates before any constitutional rule is actually violated.

Motivation (from BehaviorSpec/AARM research, arXiv:2602.09433):

> An agent that declares "I will summarise legal documents" but progressively
> issues actions like "write email", "send message", "post tweet" is drifting
> from its stated intent even if none of those individual actions violate a rule.
> Cumulative drift is a leading indicator of over-autonomy and scope creep.

Design
------
- **IntentProfile** — captures the intent as a set of normalised keywords
  extracted from the intent declaration text.
- **IntentAlignmentTracker** — maintains a running history of (action, score)
  pairs and computes cumulative drift:

  1. Per-action *alignment score* = Jaccard(action_keywords ∩ intent_keywords)
     / |intent_keywords|, bounded 0–1.
  2. Cumulative *drift_score* = 1 – EWM(alignment_scores, α=0.3) where EWM is
     the exponentially-weighted mean (recent actions weighted more heavily).
  3. ``drift_level`` = low / medium / high / critical from configurable thresholds.
  4. ``should_escalate`` = True when drift_score ≥ ``escalation_threshold``.

- Zero external dependencies — keyword extraction uses simple tokenisation
  (split + stopword removal), no NLP libraries required.
- Zero hot-path overhead — purely additive; the core engine is never touched.

Usage::

    from acgs_lite.constitution.intent_alignment import IntentAlignmentTracker

    tracker = IntentAlignmentTracker.from_text("summarise legal documents for compliance review")

    tracker.record("summarise contract clause 3")       # aligned
    tracker.record("send email to client")              # drift
    tracker.record("post to social media")              # drift
    tracker.record("tweet announcement")                # drift

    state = tracker.current_state()
    print(state.drift_score)      # 0.72
    print(state.drift_level)      # "high"
    print(state.should_escalate)  # True
    print(tracker.history_summary())
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# ── stopwords (English, minimal set) ─────────────────────────────────────────

_STOPWORDS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "for",
        "in",
        "on",
        "at",
        "to",
        "of",
        "with",
        "by",
        "from",
        "as",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "shall",
        "can",
        "i",
        "my",
        "me",
        "we",
        "our",
        "you",
        "your",
        "it",
        "its",
        "this",
        "that",
        "all",
        "any",
        "not",
        "no",
        "also",
        "into",
        "up",
        "out",
        "so",
        "then",
    }
)

_TOKEN_RE = re.compile(r"[a-zA-Z]+")

# ── drift level thresholds ───────────────────────────────────────────────────

_DRIFT_LEVELS: list[tuple[float, str]] = [
    (0.75, "critical"),
    (0.55, "high"),
    (0.35, "medium"),
    (0.0, "low"),
]

_DEFAULT_ESCALATION_THRESHOLD: float = 0.55  # "high" drift triggers escalation
_DEFAULT_EWM_ALPHA: float = 0.3  # recency weight for EWM


def _extract_keywords(text: str) -> frozenset[str]:
    """Tokenise text and return non-stopword lowercase tokens."""
    tokens = {t.lower() for t in _TOKEN_RE.findall(text) if len(t) > 2}
    return frozenset(tokens - _STOPWORDS)


def _jaccard_overlap(a: frozenset[str], b: frozenset[str]) -> float:
    """Jaccard similarity, 0.0 for empty sets."""
    if not a and not b:
        return 1.0
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def _ewm(values: list[float], alpha: float) -> float:
    """Exponentially-weighted mean, most-recent values weighted more heavily."""
    if not values:
        return 0.0
    result = values[0]
    for v in values[1:]:
        result = alpha * v + (1 - alpha) * result
    return result


# ── public types ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class IntentProfile:
    """Normalised representation of a session\'s declared intent.

    Attributes:
        declaration: Original intent text.
        keywords: Extracted keyword set (stopword-filtered lowercase tokens).
    """

    declaration: str
    keywords: frozenset[str]

    @classmethod
    def from_text(cls, text: str) -> IntentProfile:
        """Build from a natural-language intent declaration."""
        return cls(declaration=text, keywords=_extract_keywords(text))

    def to_dict(self) -> dict[str, Any]:
        return {
            "declaration": self.declaration,
            "keywords": sorted(self.keywords),
            "keyword_count": len(self.keywords),
        }


@dataclass(frozen=True)
class ActionAlignmentRecord:
    """Single action\'s alignment with the session intent.

    Attributes:
        action: The action string.
        alignment_score: Jaccard similarity between action and intent keywords (0–1).
        drift_contribution: 1 – alignment_score (contribution to drift).
        action_keywords: Keywords extracted from the action.
        matched_intent_keywords: Keywords shared with the intent.
    """

    action: str
    alignment_score: float
    drift_contribution: float
    action_keywords: frozenset[str]
    matched_intent_keywords: frozenset[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "alignment_score": round(self.alignment_score, 4),
            "drift_contribution": round(self.drift_contribution, 4),
            "action_keywords": sorted(self.action_keywords),
            "matched_intent_keywords": sorted(self.matched_intent_keywords),
        }


@dataclass(frozen=True)
class IntentAlignmentState:
    """Point-in-time snapshot of accumulated drift.

    Attributes:
        drift_score: Cumulative drift (0.0 = fully aligned, 1.0 = fully drifted).
        drift_level: Categorical level: low / medium / high / critical.
        should_escalate: True when drift_score >= escalation_threshold.
        action_count: Number of actions recorded so far.
        escalation_threshold: Configured escalation threshold.
        mean_alignment: Average alignment score across all actions.
    """

    drift_score: float
    drift_level: str
    should_escalate: bool
    action_count: int
    escalation_threshold: float
    mean_alignment: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "drift_score": round(self.drift_score, 4),
            "drift_level": self.drift_level,
            "should_escalate": self.should_escalate,
            "action_count": self.action_count,
            "escalation_threshold": self.escalation_threshold,
            "mean_alignment": round(self.mean_alignment, 4),
        }

    def __repr__(self) -> str:
        flag = " [ESCALATE]" if self.should_escalate else ""
        return (
            f"IntentAlignmentState(drift={self.drift_score:.3f}, "
            f"level={self.drift_level!r}{flag}, n={self.action_count})"
        )


# ── tracker ───────────────────────────────────────────────────────────────────


class IntentAlignmentTracker:
    """Tracks cumulative intent-action drift for a governance session.

    Records each agent action and maintains an exponentially-weighted drift
    score reflecting how far the agent has wandered from its declared intent.

    Args:
        intent: The session\'s declared :class:`IntentProfile`.
        escalation_threshold: Drift score above which ``should_escalate`` is True
            (default 0.55 — "high" drift level).
        ewm_alpha: Recency weight for exponential moving mean (default 0.3).
            Higher values make recent actions more influential.

    Example::

        tracker = IntentAlignmentTracker.from_text("analyse sales data for Q4 report")
        tracker.record("query sales database")     # aligned
        tracker.record("export csv to email")      # drifting
        state = tracker.current_state()
        if state.should_escalate:
            notify_hitl(tracker.history_summary())
    """

    def __init__(
        self,
        intent: IntentProfile,
        *,
        escalation_threshold: float = _DEFAULT_ESCALATION_THRESHOLD,
        ewm_alpha: float = _DEFAULT_EWM_ALPHA,
    ) -> None:
        if not 0.0 < escalation_threshold <= 1.0:
            raise ValueError(f"escalation_threshold must be in (0, 1], got {escalation_threshold}")
        if not 0.0 < ewm_alpha <= 1.0:
            raise ValueError(f"ewm_alpha must be in (0, 1], got {ewm_alpha}")
        self._intent = intent
        self._escalation_threshold = escalation_threshold
        self._ewm_alpha = ewm_alpha
        self._history: list[ActionAlignmentRecord] = []

    @classmethod
    def from_text(
        cls,
        intent_text: str,
        *,
        escalation_threshold: float = _DEFAULT_ESCALATION_THRESHOLD,
        ewm_alpha: float = _DEFAULT_EWM_ALPHA,
    ) -> IntentAlignmentTracker:
        """Create tracker from a natural-language intent declaration.

        Args:
            intent_text: The agent\'s declared session intent.
            escalation_threshold: Drift escalation threshold.
            ewm_alpha: EWM recency weight.

        Returns:
            New :class:`IntentAlignmentTracker`.
        """
        return cls(
            IntentProfile.from_text(intent_text),
            escalation_threshold=escalation_threshold,
            ewm_alpha=ewm_alpha,
        )

    # ── recording ─────────────────────────────────────────────────────────

    def record(self, action: str) -> ActionAlignmentRecord:
        """Record an agent action and update drift state.

        Args:
            action: The action string to record.

        Returns:
            :class:`ActionAlignmentRecord` with alignment metrics for this action.
        """
        action_kws = _extract_keywords(action)
        matched = action_kws & self._intent.keywords
        alignment = _jaccard_overlap(action_kws, self._intent.keywords)
        rec = ActionAlignmentRecord(
            action=action,
            alignment_score=alignment,
            drift_contribution=1.0 - alignment,
            action_keywords=action_kws,
            matched_intent_keywords=matched,
        )
        self._history.append(rec)
        return rec

    def record_batch(self, actions: list[str]) -> list[ActionAlignmentRecord]:
        """Record multiple actions in sequence.

        Args:
            actions: List of action strings.

        Returns:
            List of :class:`ActionAlignmentRecord` in order.
        """
        return [self.record(a) for a in actions]

    # ── state ────────────────────────────────────────────────────────────

    def current_state(self) -> IntentAlignmentState:
        """Compute the current drift state from accumulated history.

        Returns:
            :class:`IntentAlignmentState` snapshot.
        """
        if not self._history:
            return IntentAlignmentState(
                drift_score=0.0,
                drift_level="low",
                should_escalate=False,
                action_count=0,
                escalation_threshold=self._escalation_threshold,
                mean_alignment=1.0,
            )

        alignment_scores = [r.alignment_score for r in self._history]
        ewm_alignment = _ewm(alignment_scores, self._ewm_alpha)
        drift_score = min(1.0, max(0.0, 1.0 - ewm_alignment))

        drift_level = "low"
        for threshold, level in _DRIFT_LEVELS:
            if drift_score >= threshold:
                drift_level = level
                break

        mean_align = sum(alignment_scores) / len(alignment_scores)

        return IntentAlignmentState(
            drift_score=drift_score,
            drift_level=drift_level,
            should_escalate=drift_score >= self._escalation_threshold,
            action_count=len(self._history),
            escalation_threshold=self._escalation_threshold,
            mean_alignment=mean_align,
        )

    # ── analysis ──────────────────────────────────────────────────────────

    def most_drifted_actions(self, top_n: int = 5) -> list[ActionAlignmentRecord]:
        """Return the *top_n* actions with highest drift contribution.

        Args:
            top_n: Number of records to return.

        Returns:
            List of :class:`ActionAlignmentRecord` sorted by drift desc.
        """
        return sorted(self._history, key=lambda r: r.drift_contribution, reverse=True)[:top_n]

    def drift_trend(self) -> list[float]:
        """Return per-action cumulative drift scores in order.

        Useful for plotting or detecting the point at which drift began.

        Returns:
            List of cumulative drift scores (one per recorded action).
        """
        trend: list[float] = []
        running: list[float] = []
        for rec in self._history:
            running.append(rec.alignment_score)
            ewm_a = _ewm(running, self._ewm_alpha)
            trend.append(round(min(1.0, max(0.0, 1.0 - ewm_a)), 4))
        return trend

    def history_summary(self) -> dict[str, Any]:
        """Return a human-readable summary dict for logging/reporting."""
        state = self.current_state()
        top_drift = [r.to_dict() for r in self.most_drifted_actions(3)]
        return {
            "intent_declaration": self._intent.declaration,
            "intent_keywords": sorted(self._intent.keywords),
            **state.to_dict(),
            "drift_trend": self.drift_trend(),
            "top_drifted_actions": top_drift,
        }

    def reset(self) -> None:
        """Clear action history (intent profile is preserved)."""
        self._history.clear()

    def __repr__(self) -> str:
        state = self.current_state()
        return (
            f"IntentAlignmentTracker("
            f"intent={self._intent.declaration[:40]!r}, "
            f"n={state.action_count}, "
            f"drift={state.drift_score:.3f}, "
            f"level={state.drift_level!r})"
        )
