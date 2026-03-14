"""Constitutional rules — the core of ACGS-Lite.

A Constitution is a set of Rules that govern agent behavior.
Rules can be loaded from YAML, dicts, or created programmatically.

Constitutional Hash: cdd01ef066bc6cf2
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .core import Rule

# Pre-compile negative verb detection as a single regex at module load time.
# This avoids re-scanning the frozenset on every matches() call.
_NEGATIVE_VERBS_LIST = (
    "without",
    "disable",
    "bypass",
    "remove",
    "skip",
    "no ",
    "delete",
    "override",
    "hide",
    "obfuscate",
    "auto-reject",
    "self-approve",
    "self-validate",
    "delegate entirely",
    "store biometric",
    "export customer",
    "cross-reference",
    "let ai system self",
    "process customer pii",
    "use zip code",
    "deploy loan approval model with known",
    "deploy hiring model without",
)
_NEGATIVE_VERBS_RE = re.compile(
    "|".join(re.escape(v) for v in _NEGATIVE_VERBS_LIST),
    re.IGNORECASE,
)

_POSITIVE_VERBS_SET = frozenset(
    {
        "run",
        "test",
        "generate",
        "create",
        "schedule",
        "implement",
        "log",
        "enable",
        "assign",
        "establish",
        "publish",
        "disclose",
        "build",
        "review",
        "audit",
        "check",
        "verify",
        "assess",
        "evaluate",
        "report",
        "document",
        "plan",
        "prepare",
        "anonymize",
        "share",
        "update",
        "optimize",
        "parallelize",
        "consolidate",
        "migrate",
    }
)

_KW_NEGATIVE_RE = re.compile(
    r"without|disable|bypass|remove|skip|delete|override|hide|"
    r"auto-reject|self-approve|proxy for",
    re.IGNORECASE,
)


def classify_action_intent(action: str) -> dict[str, Any]:
    """exp101: Classify an action's intent for downstream governance decisions.

    Detects whether an action is constructive (testing, auditing, implementing)
    or potentially harmful (disabling, bypassing, removing). Downstream agents
    and orchestrators use this to understand the intent behind an action
    independently of rule matching.

    Args:
        action: The action text to classify.

    Returns:
        dict with keys:
            - ``has_negative_verb``: True if action contains violation-indicating verbs
            - ``has_positive_verb``: True if action starts with constructive verbs
            - ``intent``: "constructive" | "potentially_harmful" | "neutral"
            - ``detected_verbs``: list of specific verbs detected
            - ``confidence``: float 0.0-1.0 based on signal strength
    """
    text_lower = action.lower()
    neg_match = _NEGATIVE_VERBS_RE.search(text_lower)
    has_neg = bool(neg_match)

    words = text_lower.split()[:4]
    pos_matches = [w for w in words if w in _POSITIVE_VERBS_SET]
    has_pos = bool(pos_matches) and not has_neg

    detected: list[str] = []
    if neg_match:
        detected.append(neg_match.group(0))
    detected.extend(pos_matches)

    if has_neg:
        intent = "potentially_harmful"
        confidence = 0.85
    elif has_pos:
        intent = "constructive"
        confidence = 0.8
    else:
        intent = "neutral"
        confidence = 0.5

    return {
        "has_negative_verb": has_neg,
        "has_positive_verb": has_pos,
        "intent": intent,
        "detected_verbs": detected,
        "confidence": confidence,
    }


# exp94: Pre-compiled risk signal patterns for context scoring.
# Weights: higher = riskier context environment.
_CONTEXT_RISK_SIGNALS: tuple[tuple[re.Pattern[str], float, str], ...] = (
    (re.compile(r"production|prod\b|live\b", re.IGNORECASE), 0.9, "production_environment"),
    (re.compile(r"customer|user.?data|pii|personal", re.IGNORECASE), 0.85, "personal_data"),
    (re.compile(r"financ|payment|billing|credit", re.IGNORECASE), 0.8, "financial_data"),
    (re.compile(r"admin|root|superuser|privileg", re.IGNORECASE), 0.75, "elevated_privilege"),
    (re.compile(r"secret|credential|token|key\b", re.IGNORECASE), 0.7, "sensitive_credential"),
    (re.compile(r"compliance|regulat|gdpr|hipaa|sox", re.IGNORECASE), 0.65, "regulatory_scope"),
    (re.compile(r"staging|pre.?prod|canary", re.IGNORECASE), 0.4, "pre_production"),
    (re.compile(r"test|sandbox|dev\b|local", re.IGNORECASE), 0.1, "test_environment"),
)


def score_context_risk(context: dict[str, Any]) -> dict[str, Any]:
    """exp94: Score a context dict for risk signals.

    Scans both keys and values of the context dict for risk-indicating
    patterns. Returns a composite risk score (0.0–1.0), the matched
    signals, and a recommended handling tier.

    Downstream agents and orchestrators use this to modulate governance
    strictness based on the operational context (e.g., production +
    customer data = maximum strictness; test sandbox = relaxed).

    Args:
        context: The context dict passed to validate(). May be empty.

    Returns:
        dict with keys:
            - ``risk_score``: float 0.0–1.0 (max of matched signal weights)
            - ``signals``: list of matched signal names
            - ``handling_tier``: "maximum" | "elevated" | "standard" | "relaxed"
    """
    if not context:
        return {"risk_score": 0.0, "signals": [], "handling_tier": "standard"}

    # Flatten context to a single searchable string
    parts: list[str] = []
    for k, v in context.items():
        parts.append(str(k))
        parts.append(str(v))
    text = " ".join(parts)

    max_score = 0.0
    signals: list[str] = []

    for pattern, weight, name in _CONTEXT_RISK_SIGNALS:
        if pattern.search(text):
            signals.append(name)
            if weight > max_score:
                max_score = weight

    if max_score >= 0.7:
        tier = "maximum"
    elif max_score >= 0.4:
        tier = "elevated"
    elif max_score > 0.0:
        tier = "relaxed"
    else:
        tier = "standard"

    return {"risk_score": max_score, "signals": signals, "handling_tier": tier}


def governance_decision_report(
    action: str,
    context: dict[str, Any] | None = None,
    rules: Sequence[Rule] | None = None,
) -> dict[str, Any]:
    """exp97: Generate a comprehensive governance report for an action.

    Composes match_detail() + score_context_risk() into a single actionable
    report. Downstream orchestrators call this instead of invoking each
    governance function separately.

    Args:
        action: The action text to evaluate.
        context: Optional context dict for risk scoring.
        rules: Rules to check against. If None, uses empty list.

    Returns:
        dict with keys:
            - ``action``: the input action text
            - ``context_risk``: output of score_context_risk()
            - ``triggered_rules``: list of match_detail() results where matched=True
            - ``rule_count_checked``: total rules evaluated
            - ``decision_hint``: "allow" | "deny" | "escalate" based on triggered rules
            - ``max_severity``: highest severity among triggered rules (or None)
    """
    context_risk = score_context_risk(context or {})

    triggered: list[dict[str, Any]] = []
    max_sev: str | None = None
    sev_order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    max_sev_rank = 0
    checked = 0

    for rule in rules or []:
        checked += 1
        detail = rule.match_detail(action)
        if detail["matched"]:
            triggered.append(detail)
            rank = sev_order.get(detail["severity"], 0)
            if rank > max_sev_rank:
                max_sev_rank = rank
                max_sev = detail["severity"]

    if not triggered:
        hint = "allow"
    elif max_sev in ("critical", "high"):
        hint = "deny"
    else:
        hint = "escalate"

    return {
        "action": action,
        "context_risk": context_risk,
        "triggered_rules": triggered,
        "rule_count_checked": checked,
        "decision_hint": hint,
        "max_severity": max_sev,
    }
