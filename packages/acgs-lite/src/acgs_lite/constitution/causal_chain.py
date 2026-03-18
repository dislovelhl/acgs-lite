"""exp231: Causal Action Chain Policy — sequence-based governance decisions.

Conditions governance decisions on *prior action sequences* per agent, not just
point-in-time evaluation.  Detects known-dangerous action chains (e.g., "read
credentials → send email" = exfiltration) and generates early warnings when a
chain is partially matched.

Motivation (from PCAS arXiv:2602.16708, Pro2Guard arXiv:2508.00500):

> Point-in-time policy evaluation treats each action independently.  An agent
> that reads sensitive data and then exports it externally has executed two
> individually-permissible actions that *together* constitute a dangerous
> sequence.  Causal chain detection conditions the Nth decision on actions
> 1..N-1, catching multi-step attack patterns that no single-action policy
> can detect.

Design
------
- **ChainStep** — a single step matcher: an action matches if any of the
  step's keywords appear in the action text.
- **ChainPattern** — an ordered sequence of steps representing a dangerous
  chain, with severity, max inter-step gap, and human-readable description.
- **ChainMatch** — result when an action completes all steps of a pattern.
- **ChainAlert** — early warning when a chain is partially matched beyond
  a configurable threshold (default ≥50% of steps).
- **ChainCheckResult** — combined output of completed matches and alerts.
- **CausalChainTracker** — per-agent sliding-window history with multi-pattern
  subsequence matching.  Tracks progress through each pattern independently.

Built-in patterns cover 8 common attack chains:
  CHAIN-001 Data Exfiltration, CHAIN-002 Audit Evasion, CHAIN-003 Privilege
  Escalation, CHAIN-004 Data Destruction, CHAIN-005 PII Leak, CHAIN-006
  Policy Tampering, CHAIN-007 Credential Theft, CHAIN-008 Shadow Deployment.

Algorithm: for each agent, maintain a sliding window of recent actions (default
50).  When a new action arrives:
  1. For each pattern, check if the action matches the *next expected step*.
  2. If matched, advance the pattern's progress counter.
  3. If all steps matched → emit ``ChainMatch`` and reset.
  4. If gap between steps exceeds ``max_gap`` → reset that pattern.
  5. If an action matches step 0, start a *new* tracking instance.
  6. If partial progress ≥ ``alert_threshold`` → emit ``ChainAlert``.

Complexity: O(P) per action where P = number of patterns.  Keyword matching
uses set intersection (O(min(|action_words|, |step_keywords|))).

Zero hot-path overhead — purely additive; the core engine is never touched.

Usage::

    from acgs_lite.constitution.causal_chain import CausalChainTracker

    tracker = CausalChainTracker.with_builtin_patterns()

    r1 = tracker.record_and_check("agent-1", "read customer database")
    assert not r1.completed  # no chain completed yet

    r2 = tracker.record_and_check("agent-1", "export data to external API")
    assert r2.completed  # CHAIN-001 Data Exfiltration matched!
    assert r2.completed[0].severity == "high"

    # Early warning: partial match detection
    tracker.record_and_check("agent-2", "disable audit logging")
    r3 = tracker.record_and_check("agent-2", "delete sensitive records")
    assert r3.alerts  # CHAIN-002 Audit Evasion 67% matched → alert
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

# ── tokenisation ──────────────────────────────────────────────────────────────

_WORD_RE = re.compile(r"[a-z0-9]+")

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
        "this",
        "that",
        "these",
        "those",
        "it",
        "its",
        "my",
        "your",
        "our",
        "their",
        "all",
        "each",
        "every",
        "some",
        "any",
        "no",
        "not",
    }
)


def _tokenize(text: str) -> frozenset[str]:
    """Extract meaningful words from action text."""
    return frozenset(
        w for w in _WORD_RE.findall(text.lower()) if w not in _STOPWORDS and len(w) > 1
    )


# ── data structures ──────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ChainStep:
    """A single step in a causal chain pattern.

    An action matches this step if the intersection of the action's keywords
    and the step's keywords is non-empty.
    """

    keywords: frozenset[str]
    label: str

    def matches(self, action_words: frozenset[str]) -> bool:
        """Return True if the action matches this step."""
        return bool(self.keywords & action_words)


@dataclass(frozen=True, slots=True)
class ChainPattern:
    """An ordered sequence of steps representing a dangerous action chain.

    Attributes:
        id: Unique pattern identifier (e.g., "CHAIN-001").
        name: Human-readable pattern name.
        steps: Ordered tuple of ChainStep matchers.
        severity: Risk severity ("critical", "high", "medium", "low").
        description: Human-readable explanation of why this chain is dangerous.
        max_gap: Maximum number of non-matching actions allowed between
            consecutive steps.  0 means steps must be contiguous.
            -1 means unlimited gap (match anywhere in window).
    """

    id: str
    name: str
    steps: tuple[ChainStep, ...]
    severity: str
    description: str
    max_gap: int = 10

    @property
    def length(self) -> int:
        """Number of steps in this chain pattern."""
        return len(self.steps)


@dataclass(frozen=True, slots=True)
class ChainMatch:
    """Result when an action completes all steps of a dangerous chain pattern."""

    pattern_id: str
    pattern_name: str
    severity: str
    matched_actions: tuple[str, ...]
    agent_id: str
    completed_at_ns: int
    description: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSON output."""
        return {
            "pattern_id": self.pattern_id,
            "pattern_name": self.pattern_name,
            "severity": self.severity,
            "matched_actions": list(self.matched_actions),
            "agent_id": self.agent_id,
            "completed_at_ns": self.completed_at_ns,
            "description": self.description,
        }


@dataclass(frozen=True, slots=True)
class ChainAlert:
    """Early warning for a partially matched chain that exceeds the alert threshold."""

    pattern_id: str
    pattern_name: str
    severity: str
    progress: float  # 0.0 to 1.0
    steps_matched: int
    total_steps: int
    matched_actions: tuple[str, ...]
    agent_id: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSON output."""
        return {
            "pattern_id": self.pattern_id,
            "pattern_name": self.pattern_name,
            "severity": self.severity,
            "progress": round(self.progress, 3),
            "steps_matched": self.steps_matched,
            "total_steps": self.total_steps,
            "matched_actions": list(self.matched_actions),
            "agent_id": self.agent_id,
        }


@dataclass(frozen=True, slots=True)
class ChainCheckResult:
    """Combined output from a single record_and_check() call."""

    completed: tuple[ChainMatch, ...]
    alerts: tuple[ChainAlert, ...]
    action: str
    agent_id: str

    @property
    def has_matches(self) -> bool:
        """True if any chain was fully completed."""
        return len(self.completed) > 0

    @property
    def has_alerts(self) -> bool:
        """True if any partial chain exceeded the alert threshold."""
        return len(self.alerts) > 0

    @property
    def highest_severity(self) -> str:
        """Highest severity across all matches and alerts, or empty string."""
        _ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        severities: list[str] = [m.severity for m in self.completed]
        severities.extend(a.severity for a in self.alerts)
        if not severities:
            return ""
        return min(severities, key=lambda s: _ORDER.get(s, 99))

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSON output."""
        return {
            "completed": [m.to_dict() for m in self.completed],
            "alerts": [a.to_dict() for a in self.alerts],
            "action": self.action,
            "agent_id": self.agent_id,
            "has_matches": self.has_matches,
            "has_alerts": self.has_alerts,
            "highest_severity": self.highest_severity,
        }


# ── internal state ────────────────────────────────────────────────────────────


@dataclass(slots=True)
class _PatternProgress:
    """Mutable tracking state for one pattern within one agent."""

    steps_matched: int = 0
    matched_actions: list[str] = field(default_factory=list)
    gap_since_last: int = 0
    started_at_ns: int = 0


@dataclass(slots=True)
class _AgentState:
    """Mutable per-agent state: action history and pattern progress."""

    history: list[str] = field(default_factory=list)
    progress: dict[str, _PatternProgress] = field(default_factory=dict)
    completed_count: int = 0
    alert_count: int = 0


# ── built-in dangerous chain patterns ─────────────────────────────────────────


def builtin_patterns() -> tuple[ChainPattern, ...]:
    """Return 8 built-in dangerous action chain patterns.

    These cover common multi-step attack vectors in AI agent environments.
    """
    return (
        ChainPattern(
            id="CHAIN-001",
            name="Data Exfiltration",
            steps=(
                ChainStep(
                    frozenset({"read", "access", "query", "fetch", "retrieve", "get"}),
                    "data_access",
                ),
                ChainStep(
                    frozenset({"export", "send", "upload", "transfer", "post", "forward"}),
                    "data_export",
                ),
            ),
            severity="high",
            description=(
                "Agent accesses data then exports/sends it externally — "
                "potential data exfiltration chain"
            ),
            max_gap=5,
        ),
        ChainPattern(
            id="CHAIN-002",
            name="Audit Evasion",
            steps=(
                ChainStep(
                    frozenset({"disable", "stop", "pause", "suppress", "mute"}),
                    "disable_audit",
                ),
                ChainStep(
                    frozenset({"execute", "run", "delete", "modify", "write", "drop"}),
                    "unaudited_action",
                ),
                ChainStep(
                    frozenset({"enable", "start", "resume", "restore", "unmute"}),
                    "restore_audit",
                ),
            ),
            severity="critical",
            description=(
                "Agent disables logging/auditing, performs sensitive action, "
                "then re-enables — classic audit evasion pattern"
            ),
            max_gap=3,
        ),
        ChainPattern(
            id="CHAIN-003",
            name="Privilege Escalation",
            steps=(
                ChainStep(
                    frozenset({"create", "add", "register"}),
                    "create_entity",
                ),
                ChainStep(
                    frozenset({"grant", "assign", "elevate", "promote", "admin"}),
                    "grant_privilege",
                ),
                ChainStep(
                    frozenset({"deploy", "execute", "run", "apply"}),
                    "privileged_action",
                ),
            ),
            severity="critical",
            description=(
                "Agent creates entity, grants elevated privileges, then "
                "executes with those privileges — privilege escalation chain"
            ),
            max_gap=5,
        ),
        ChainPattern(
            id="CHAIN-004",
            name="Data Destruction",
            steps=(
                ChainStep(
                    frozenset({"read", "access", "list", "enumerate", "scan"}),
                    "data_discovery",
                ),
                ChainStep(
                    frozenset({"export", "backup", "copy", "snapshot"}),
                    "data_copy",
                ),
                ChainStep(
                    frozenset({"delete", "drop", "truncate", "destroy", "purge", "wipe"}),
                    "data_destroy",
                ),
            ),
            severity="critical",
            description=(
                "Agent discovers data, copies it, then destroys the original — "
                "ransomware/sabotage pattern"
            ),
            max_gap=5,
        ),
        ChainPattern(
            id="CHAIN-005",
            name="PII Leak",
            steps=(
                ChainStep(
                    frozenset({"query", "fetch", "read", "access", "search"}),
                    "pii_access",
                ),
                ChainStep(
                    frozenset({"log", "print", "display", "render", "output", "write"}),
                    "pii_exposure",
                ),
            ),
            severity="high",
            description=(
                "Agent accesses PII-containing data then logs/displays it — potential privacy leak"
            ),
            max_gap=3,
        ),
        ChainPattern(
            id="CHAIN-006",
            name="Policy Tampering",
            steps=(
                ChainStep(
                    frozenset({"read", "inspect", "query", "get"}),
                    "policy_read",
                ),
                ChainStep(
                    frozenset({"modify", "update", "patch", "amend", "override"}),
                    "policy_modify",
                ),
                ChainStep(
                    frozenset({"approve", "validate", "accept", "confirm"}),
                    "self_approve",
                ),
            ),
            severity="critical",
            description=(
                "Agent reads policy, modifies it, then self-approves — "
                "MACI separation-of-powers violation chain"
            ),
            max_gap=5,
        ),
        ChainPattern(
            id="CHAIN-007",
            name="Credential Theft",
            steps=(
                ChainStep(
                    frozenset({"read", "access", "fetch", "retrieve", "decrypt"}),
                    "credential_access",
                ),
                ChainStep(
                    frozenset({"encode", "encrypt", "obfuscate", "base64", "compress"}),
                    "credential_encode",
                ),
                ChainStep(
                    frozenset({"send", "post", "upload", "transfer", "webhook"}),
                    "credential_exfil",
                ),
            ),
            severity="critical",
            description=(
                "Agent accesses credentials, encodes/obfuscates them, then "
                "sends externally — credential theft chain"
            ),
            max_gap=5,
        ),
        ChainPattern(
            id="CHAIN-008",
            name="Shadow Deployment",
            steps=(
                ChainStep(
                    frozenset({"build", "compile", "package", "bundle"}),
                    "build_artifact",
                ),
                ChainStep(
                    frozenset({"deploy", "push", "publish", "release", "install"}),
                    "deploy_artifact",
                ),
            ),
            severity="medium",
            description=(
                "Agent builds then deploys without review/approval step — "
                "shadow deployment bypassing CI/CD governance"
            ),
            max_gap=3,
        ),
    )


# ── tracker ───────────────────────────────────────────────────────────────────


class CausalChainTracker:
    """Per-agent action history and dangerous sequence detection.

    Tracks a sliding window of recent actions for each agent and checks
    incoming actions against a set of chain patterns.  Reports both
    completed chain matches and early warnings for partial matches.

    Thread safety: NOT thread-safe.  Use one tracker per thread/coroutine
    or add external synchronisation.

    Attributes:
        patterns: Tuple of ChainPattern definitions to match against.
        window_size: Maximum action history per agent (FIFO eviction).
        alert_threshold: Fraction of chain steps that must be matched
            before an alert is generated (default 0.5 = 50%).
    """

    __slots__ = ("patterns", "window_size", "alert_threshold", "_agents")

    def __init__(
        self,
        patterns: list[ChainPattern] | tuple[ChainPattern, ...],
        *,
        window_size: int = 50,
        alert_threshold: float = 0.5,
    ) -> None:
        self.patterns: tuple[ChainPattern, ...] = tuple(patterns)
        self.window_size = max(1, window_size)
        self.alert_threshold = max(0.0, min(1.0, alert_threshold))
        self._agents: dict[str, _AgentState] = {}

    # ── constructors ──────────────────────────────────────────────────────

    @classmethod
    def with_builtin_patterns(
        cls,
        *,
        extra_patterns: list[ChainPattern] | None = None,
        window_size: int = 50,
        alert_threshold: float = 0.5,
    ) -> CausalChainTracker:
        """Create a tracker with the 8 built-in dangerous chain patterns.

        Args:
            extra_patterns: Additional custom patterns to include.
            window_size: Maximum action history per agent.
            alert_threshold: Alert when chain is this fraction matched.

        Returns:
            CausalChainTracker with built-in + optional extra patterns.
        """
        patterns: list[ChainPattern] = list(builtin_patterns())
        if extra_patterns:
            patterns.extend(extra_patterns)
        return cls(patterns, window_size=window_size, alert_threshold=alert_threshold)

    # ── core API ──────────────────────────────────────────────────────────

    def record_and_check(self, agent_id: str, action: str) -> ChainCheckResult:
        """Record an action and check for dangerous chain matches.

        Args:
            agent_id: Identifier for the agent performing the action.
            action: The action text to evaluate.

        Returns:
            ChainCheckResult with any completed matches and alerts.
        """
        state = self._ensure_agent(agent_id)
        now_ns = time.monotonic_ns()

        # Add to history (FIFO eviction)
        state.history.append(action)
        if len(state.history) > self.window_size:
            state.history.pop(0)

        action_words = _tokenize(action)
        completed: list[ChainMatch] = []
        alerts: list[ChainAlert] = []

        for pattern in self.patterns:
            prog = state.progress.get(pattern.id)
            if prog is None:
                prog = _PatternProgress()
                state.progress[pattern.id] = prog

            current_step_idx = prog.steps_matched

            # Check if action matches the next expected step
            if current_step_idx < pattern.length:
                step = pattern.steps[current_step_idx]
                if step.matches(action_words):
                    # Step matched — advance progress
                    prog.steps_matched += 1
                    prog.matched_actions.append(action)
                    prog.gap_since_last = 0
                    if prog.started_at_ns == 0:
                        prog.started_at_ns = now_ns

                    if prog.steps_matched >= pattern.length:
                        # Chain fully matched!
                        completed.append(
                            ChainMatch(
                                pattern_id=pattern.id,
                                pattern_name=pattern.name,
                                severity=pattern.severity,
                                matched_actions=tuple(prog.matched_actions),
                                agent_id=agent_id,
                                completed_at_ns=now_ns,
                                description=pattern.description,
                            )
                        )
                        state.completed_count += 1
                        # Reset this pattern's progress
                        self._reset_pattern(prog)
                else:
                    # No match on expected step — handle gap
                    if current_step_idx > 0:
                        prog.gap_since_last += 1
                        if pattern.max_gap >= 0 and prog.gap_since_last > pattern.max_gap:
                            # Gap exceeded — reset and check if action starts fresh
                            self._reset_pattern(prog)
                            if pattern.steps[0].matches(action_words):
                                prog.steps_matched = 1
                                prog.matched_actions.append(action)
                                prog.started_at_ns = now_ns
                    else:
                        # Not yet started — check if action starts this pattern
                        if pattern.steps[0].matches(action_words):
                            prog.steps_matched = 1
                            prog.matched_actions.append(action)
                            prog.gap_since_last = 0
                            prog.started_at_ns = now_ns

            # Generate alert if partial match exceeds threshold
            if prog.steps_matched > 0 and prog.steps_matched < pattern.length:
                fraction = prog.steps_matched / pattern.length
                if fraction >= self.alert_threshold:
                    alerts.append(
                        ChainAlert(
                            pattern_id=pattern.id,
                            pattern_name=pattern.name,
                            severity=pattern.severity,
                            progress=fraction,
                            steps_matched=prog.steps_matched,
                            total_steps=pattern.length,
                            matched_actions=tuple(prog.matched_actions),
                            agent_id=agent_id,
                        )
                    )
                    state.alert_count += 1

        return ChainCheckResult(
            completed=tuple(completed),
            alerts=tuple(alerts),
            action=action,
            agent_id=agent_id,
        )

    def active_chains(self, agent_id: str) -> list[ChainAlert]:
        """Return all in-progress (partially matched) chains for an agent.

        Useful for dashboard/monitoring to see which chains are "warming up"
        even before the alert threshold is reached.
        """
        state = self._agents.get(agent_id)
        if state is None:
            return []

        result: list[ChainAlert] = []
        patterns_by_id = {p.id: p for p in self.patterns}

        for pid, prog in state.progress.items():
            if prog.steps_matched > 0:
                pattern = patterns_by_id.get(pid)
                if pattern is None:
                    continue
                result.append(
                    ChainAlert(
                        pattern_id=pattern.id,
                        pattern_name=pattern.name,
                        severity=pattern.severity,
                        progress=prog.steps_matched / pattern.length,
                        steps_matched=prog.steps_matched,
                        total_steps=pattern.length,
                        matched_actions=tuple(prog.matched_actions),
                        agent_id=agent_id,
                    )
                )
        return result

    def agent_history(self, agent_id: str) -> tuple[str, ...]:
        """Return the action history for an agent (oldest first)."""
        state = self._agents.get(agent_id)
        if state is None:
            return ()
        return tuple(state.history)

    def reset_agent(self, agent_id: str) -> None:
        """Clear all tracking state for an agent (e.g., session end)."""
        self._agents.pop(agent_id, None)

    def summary(self) -> dict[str, Any]:
        """Aggregate summary across all tracked agents.

        Returns:
            Dict with agent_count, total_completed, total_alerts,
            and per-agent breakdown.
        """
        agents_summary: dict[str, dict[str, Any]] = {}
        total_completed = 0
        total_alerts = 0

        for aid, state in self._agents.items():
            total_completed += state.completed_count
            total_alerts += state.alert_count
            active = [pid for pid, prog in state.progress.items() if prog.steps_matched > 0]
            agents_summary[aid] = {
                "history_length": len(state.history),
                "completed_chains": state.completed_count,
                "alerts_generated": state.alert_count,
                "active_patterns": active,
            }

        return {
            "agent_count": len(self._agents),
            "total_completed": total_completed,
            "total_alerts": total_alerts,
            "pattern_count": len(self.patterns),
            "agents": agents_summary,
        }

    # ── internals ─────────────────────────────────────────────────────────

    def _ensure_agent(self, agent_id: str) -> _AgentState:
        """Get or create agent state."""
        state = self._agents.get(agent_id)
        if state is None:
            state = _AgentState()
            self._agents[agent_id] = state
        return state

    @staticmethod
    def _reset_pattern(prog: _PatternProgress) -> None:
        """Reset a pattern's progress to initial state."""
        prog.steps_matched = 0
        prog.matched_actions.clear()
        prog.gap_since_last = 0
        prog.started_at_ns = 0
