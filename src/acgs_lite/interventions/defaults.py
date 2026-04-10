"""Default intervention rules per vertical.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from acgs_lite.interventions.actions import InterventionAction, InterventionRule


def get_default_rules(vertical: str = "general") -> list[InterventionRule]:
    """Return default intervention rules for the given vertical.

    Args:
        vertical: "legal", "healthcare", "igaming", or "general"

    Returns:
        List of InterventionRule sorted by priority.
    """
    rules: list[InterventionRule] = []

    # General: ESCALATE on high-risk DENY
    rules.append(
        InterventionRule(
            rule_id="general-escalate-deny",
            name="Escalate high-risk denied decisions for review",
            action=InterventionAction.ESCALATE,
            condition={"and": [{"verdict": "deny"}, {"risk_score_gte": 0.7}]},
            priority=50,
        )
    )

    if vertical == "legal":
        rules.append(
            InterventionRule(
                rule_id="legal-escalate-any-deny",
                name="Legal: all denied decisions require review",
                action=InterventionAction.ESCALATE,
                condition={"verdict": "deny"},
                priority=10,
            )
        )
        rules.append(
            InterventionRule(
                rule_id="legal-log-conditional",
                name="Legal: log conditional decisions",
                action=InterventionAction.LOG_ONLY,
                condition={"verdict": "conditional"},
                priority=20,
            )
        )

    elif vertical == "healthcare":
        rules.append(
            InterventionRule(
                rule_id="healthcare-block-phi-deny",
                name="Healthcare: block when PHI_GUARD unsatisfied and verdict is deny",
                action=InterventionAction.BLOCK,
                condition={"and": [{"verdict": "deny"}, {"has_violated_rule": "PHI_GUARD"}]},
                priority=5,
            )
        )
        rules.append(
            InterventionRule(
                rule_id="healthcare-escalate-phi",
                name="Healthcare: escalate any PHI obligation",
                action=InterventionAction.ESCALATE,
                condition={"has_obligation_type": "phi_guard"},
                priority=20,
            )
        )

    elif vertical == "igaming":
        rules.append(
            InterventionRule(
                rule_id="igaming-cooloff-spend-limit",
                name="iGaming: cool-off when spend limit obligation present",
                action=InterventionAction.COOL_OFF,
                condition={"has_obligation_type": "spend_limit"},
                priority=5,
                metadata={"duration_seconds": 86400},  # 24h
            )
        )
        rules.append(
            InterventionRule(
                rule_id="igaming-escalate-deny",
                name="iGaming: escalate denied decisions",
                action=InterventionAction.ESCALATE,
                condition={"verdict": "deny"},
                priority=10,
            )
        )
        rules.append(
            InterventionRule(
                rule_id="igaming-throttle-rapid",
                name="iGaming: throttle rapid consecutive decisions",
                action=InterventionAction.THROTTLE,
                condition={"framework_in": ["igaming"]},
                priority=30,
                metadata={"window_seconds": 60, "max_requests": 20},
            )
        )

    return sorted(rules, key=lambda r: r.priority)
