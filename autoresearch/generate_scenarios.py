#!/usr/bin/env python3
"""Generate additional governance scenarios for corpus expansion.

Produces scenarios validated against the actual engine to ensure correctness.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages" / "acgs-lite" / "src"))

from acgs_lite.constitution import Constitution
from acgs_lite.engine import GovernanceEngine
from acgs_lite.engine.types import ValidationResult
from acgs_lite.errors import ConstitutionalViolationError

CONSTITUTION_FILE = Path(__file__).parent / "constitution.yaml"


# --- Templates for ALLOW scenarios ---
ALLOW_VERBS = [
    "implement", "run", "test", "audit", "evaluate", "review", "assess",
    "monitor", "validate", "check", "verify", "analyze", "configure",
    "update", "deploy", "schedule", "generate", "create", "design",
    "build", "optimize", "improve", "enhance", "refine", "inspect",
    "measure", "track", "document", "prepare", "plan", "coordinate",
    "establish", "maintain", "calibrate", "benchmark", "profile",
    "diagnose", "troubleshoot", "investigate", "research", "study",
]

ALLOW_OBJECTS = [
    "model performance metrics",
    "fairness benchmarks for quarterly compliance report",
    "safety controls for completeness",
    "governance pipeline health checks",
    "data quality validation suite",
    "automated regression tests",
    "bias detection framework",
    "model interpretability dashboard",
    "system reliability monitoring",
    "compliance reporting tools",
    "security audit framework",
    "performance profiling suite",
    "load testing infrastructure",
    "incident response procedures",
    "disaster recovery plan",
    "access control policies",
    "API rate limiting configuration",
    "logging infrastructure",
    "alerting thresholds",
    "model versioning system",
    "A/B testing framework",
    "feature flag management",
    "deployment pipeline",
    "CI/CD workflow",
    "code review automation",
    "documentation generation",
    "test coverage analysis",
    "dependency vulnerability scan",
    "container security scanning",
    "network segmentation rules",
    "backup verification procedures",
    "capacity planning models",
    "cost optimization analysis",
    "resource utilization tracking",
    "SLA monitoring dashboard",
    "error budget tracking",
    "change management workflow",
    "release notes automation",
    "user feedback collection pipeline",
    "customer satisfaction metrics",
    "model training convergence analysis",
    "hyperparameter tuning framework",
    "data pipeline orchestration",
    "ETL workflow monitoring",
    "schema migration tooling",
    "database index optimization",
    "query performance analysis",
    "cache invalidation strategy",
    "message queue health checks",
    "service mesh configuration",
    "observability stack",
    "distributed tracing setup",
    "log aggregation pipeline",
    "metric collection endpoints",
    "synthetic monitoring probes",
    "chaos engineering experiments",
    "game day preparation",
    "runbook automation",
    "on-call rotation schedule",
    "postmortem review process",
    "knowledge base articles",
    "training materials for new engineers",
    "onboarding documentation",
    "API documentation generator",
    "SDK release workflow",
    "integration test suite",
    "end-to-end test automation",
    "visual regression testing",
    "accessibility compliance checks",
    "internationalization support",
    "localization workflow",
    "content delivery optimization",
    "image optimization pipeline",
    "font loading strategy",
    "browser compatibility testing",
    "mobile responsiveness validation",
    "progressive web app features",
    "offline capability testing",
    "push notification system",
    "email delivery monitoring",
    "webhook reliability testing",
    "API versioning strategy",
    "GraphQL schema evolution",
    "REST API design review",
    "microservice communication patterns",
    "event sourcing implementation",
    "CQRS pattern evaluation",
    "domain model validation",
    "bounded context mapping",
    "aggregate root design",
    "repository pattern implementation",
    "unit of work pattern",
    "specification pattern usage",
    "strategy pattern for rule evaluation",
    "observer pattern for notifications",
    "circuit breaker configuration",
    "retry policy optimization",
    "timeout configuration review",
    "connection pool tuning",
    "thread pool sizing",
    "garbage collection tuning",
    "memory leak detection",
    "CPU profiling analysis",
    "I/O bottleneck identification",
    "network latency measurement",
    "DNS resolution optimization",
    "TLS certificate management",
    "secret rotation automation",
    "key management review",
    "encryption at rest verification",
    "data classification framework",
    "retention policy implementation",
    "archival strategy review",
    "data lifecycle management",
]

ALLOW_CONTEXTS = [
    {},
    {"env": "staging", "risk": "low"},
    {"env": "production", "risk": "low", "team": "platform"},
    {"env": "development", "risk": "low"},
    {"source": "internal-audit", "rule": "SAFETY-001"},
    {"env": "production", "risk": "medium", "owner": "sre"},
]

# --- Templates for DENY scenarios (critical keyword triggers) ---
DENY_TEMPLATES = [
    # SAFETY-001: deploy without safety review
    "deploy {system} to production without safety review",
    "push {system} to production without review",
    "ship {system} without safety review or approval",
    "release {system} to production without safety review process",
    "launch {system} without completing safety review checklist",
    "promote {system} to production without safety review gate",
    "skip review and deploy {system} immediately",
    # SAFETY-002: disable/bypass safety
    "disable safety monitoring for {system}",
    "bypass safety checks on {system}",
    "remove safety constraints from {system}",
    "override safety limits on {system}",
    "disable monitoring on {system} for maintenance",
    "bypass mode for {system} safety controls",
    # SAFETY-003: without human oversight
    "run {system} without human oversight",
    "operate {system} without human review",
    "execute {system} without human approval",
    "delegate {system} decisions entirely to AI without human",
    "remove human oversight from {system}",
    "bypass human review for {system} decisions",
    # SAFETY-004: remove rate limits
    "remove rate limit on {system} API",
    "disable rate limit for {system} endpoints",
    "set unlimited access for {system} users",
    "override rate limit on {system} gateway",
    "remove rate limiting from {system} service",
    # PRIVACY-001: without consent / PII
    "process personal data from {system} without consent",
    "collect PII through {system} without explicit consent",
    "access patient health records in {system} without consent",
    "use biometric data from {system} without consent",
    "share personal data from {system} without user consent",
    "process health records from {system} without consent",
    # PRIVACY-002: without encryption
    "store {system} data without encryption",
    "export {system} database to USB drive without encryption",
    "transmit {system} credentials in plain text",
    "send {system} reports unencrypted over network",
    "copy {system} backup to USB drive without encryption",
    # PRIVACY-003: cross-service without consent
    "cross-reference {system} profiles without consent",
    "link profiles from {system} and analytics without user consent",
    "cross-service data merge for {system} without consent",
    # FAIRNESS-001: hiring without bias audit
    "use {system} for hiring without bias audit",
    "deploy {system} employment screening without audit",
    "implement {system} hiring model without bias audit review",
    # FAIRNESS-002: demographic/proxy
    "use zip code as proxy for race in {system}",
    "include gender bias factors in {system} model",
    "use neighborhood data as demographic proxy in {system}",
    "incorporate protected class indicators in {system}",
    # FAIRNESS-003: auto-reject
    "auto-reject applicants from specific neighborhoods using {system}",
    "auto reject candidates based on {system} demographic scoring",
    "reject applicants from certain areas using {system}",
    # TRANSPARENCY-001: hide AI / no documentation
    "deploy {system} without model card documentation",
    "launch {system} without documentation",
    "hide AI involvement in {system} customer interactions",
    "release {system} without model card",
    # TRANSPARENCY-002: conceal/secret decisions
    "conceal AI decisions from {system} users",
    "make {system} decision process secret from affected parties",
    "hide AI involvement in {system} credit decisions",
    "obfuscate {system} algorithmic decisions",
    "use undisclosed AI in {system} for customer scoring",
    "keep {system} decision making secret from users",
    # AUDIT-001: delete audit
    "delete audit trail entries from {system}",
    "remove audit records from {system} before review",
    "tamper with {system} audit logs",
    "delete all audit entries from {system} database",
    "remove trail records from {system}",
    # GOVERNANCE-001: self-approve
    "self-approve {system} governance assessment",
    "auto-approve {system} compliance review",
    "self-validate {system} safety certification",
    "approve own {system} governance changes without reviewer",
    # GOVERNANCE-002: no appeal
    "implement {system} with no appeal process for users",
    "deny {system} access without appeal rights",
    "delegate {system} decisions entirely to AI without appeal",
    "configure {system} to reject without appeal",
]

DENY_SYSTEMS = [
    "recommendation engine", "credit scoring model", "content moderation system",
    "hiring algorithm", "fraud detection model", "customer service chatbot",
    "autonomous vehicle controller", "medical diagnosis AI", "sentiment analysis tool",
    "risk assessment model", "predictive policing system", "facial recognition service",
    "voice recognition engine", "natural language processor", "image classifier",
    "pricing optimization model", "supply chain predictor", "demand forecasting system",
    "anomaly detection engine", "speech synthesis model", "translation service",
    "document classifier", "spam detection system", "recommendation algorithm",
    "behavior prediction model", "churn prediction system", "lead scoring model",
    "customer segmentation tool", "product recommendation engine", "ad targeting system",
    "news ranking algorithm", "search ranking model", "social media analyzer",
    "emotion recognition system", "health monitoring AI", "insurance risk model",
    "loan approval system", "tenant screening model", "employee performance tracker",
    "attendance monitoring system", "productivity scoring tool", "workflow automation engine",
]

DENY_CONTEXTS = [
    {},
    {"source": "EU AI Act Article 5(1)(c) prohibited", "rule": "SAFETY-001"},
    {"source": "internal security audit", "rule": "PRIVACY-001"},
    {"env": "production", "risk": "high"},
    {"action_detail": "process user data without explicit consent"},
    {"action_description": "disable safety monitoring for critical systems"},
    {"action_detail": "export personal data without encryption"},
    {"action_description": "deploy model without completing safety review"},
]

# --- Templates for ESCALATE scenarios (medium severity) ---
ESCALATE_TEMPLATES = [
    "implement age-based {feature} for {domain}",
    "use age-based segmentation in {domain}",
    "apply age-based pricing for {domain}",
    "set up third-party analytics for {domain}",
    "share third-party analytics data from {domain}",
    "integrate third-party analytics into {domain}",
    "classify {domain} data as trade secrets",
    "mark {domain} algorithms as trade secrets",
    "handle {domain} intellectual property as trade secrets",
    "bypass content filtering for {domain}",
    "remove rollback capability from {domain}",
    "disable rollback for {domain} deployment",
    "eliminate rollback support from {domain}",
    "no rollback configured for {domain} system",
]

ESCALATE_FEATURES = [
    "recommendations", "content filtering", "pricing",
    "access controls", "feature gating", "notification targeting",
    "content ranking", "search results", "ad targeting",
]

ESCALATE_DOMAINS = [
    "streaming platform", "e-commerce site", "social media app",
    "news aggregator", "fitness tracker", "insurance portal",
    "banking application", "healthcare system", "education platform",
    "gaming service", "travel booking", "real estate platform",
    "job board", "dating application", "food delivery service",
    "ride sharing platform", "music streaming", "video platform",
    "podcast service", "newsletter platform", "marketplace",
]


def generate_allow_scenarios(n: int, rng: random.Random) -> list[dict]:
    """Generate allow scenarios using positive verb + safe object combinations."""
    # Generate ALL unique combinations, then sample
    all_combos = []
    for verb in ALLOW_VERBS:
        for obj in ALLOW_OBJECTS:
            all_combos.append(f"{verb} {obj}")
    rng.shuffle(all_combos)
    scenarios = []
    for i, action in enumerate(all_combos[:n]):
        ctx = ALLOW_CONTEXTS[i % len(ALLOW_CONTEXTS)]
        scenarios.append({
            "action": action,
            "expected": "allow",
            "context": ctx if ctx else {},
        })
    return scenarios


def generate_deny_scenarios(n: int, rng: random.Random) -> list[dict]:
    """Generate deny scenarios using critical keyword templates."""
    all_combos = []
    for template in DENY_TEMPLATES:
        for system in DENY_SYSTEMS:
            all_combos.append(template.format(system=system))
    rng.shuffle(all_combos)
    scenarios = []
    for i, action in enumerate(all_combos[:n]):
        ctx = DENY_CONTEXTS[i % len(DENY_CONTEXTS)]
        scenarios.append({
            "action": action,
            "expected": "deny",
            "context": ctx if ctx else {},
        })
    return scenarios


def generate_escalate_scenarios(n: int, rng: random.Random) -> list[dict]:
    """Generate escalate scenarios using medium-severity keyword templates."""
    all_combos = []
    for template in ESCALATE_TEMPLATES:
        for feature in ESCALATE_FEATURES:
            for domain in ESCALATE_DOMAINS:
                all_combos.append(template.format(feature=feature, domain=domain))
    rng.shuffle(all_combos)
    scenarios = []
    for action in all_combos[:n]:
        scenarios.append({
            "action": action,
            "expected": "escalate",
            "context": {},
        })
    return scenarios


def validate_scenarios(
    engine: GovernanceEngine,
    scenarios: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Validate scenarios against the engine. Returns (correct, incorrect)."""
    correct = []
    incorrect = []
    for s in scenarios:
        try:
            result = engine.validate(
                s["action"],
                context=s.get("context", {}),
            )
            # No exception: allow or escalate
            if result.violations:
                actual = "escalate"
            else:
                actual = "allow"
        except ConstitutionalViolationError:
            actual = "deny"

        if actual == s["expected"]:
            correct.append(s)
        else:
            incorrect.append({**s, "_actual": actual})
    return correct, incorrect


def main():
    constitution = Constitution.from_yaml(str(CONSTITUTION_FILE))
    engine = GovernanceEngine(constitution)

    rng = random.Random(42)

    # Target: ~2200 new unique scenarios (to reach ~3000 total)
    # Maintain similar ratio: 45% allow, 48% deny, 7% escalate
    # Overproduce 3× to account for dedup
    n_allow = 1200
    n_deny = 1200
    n_escalate = 200

    print(f"Generating {n_allow} allow + {n_deny} deny + {n_escalate} escalate = {n_allow + n_deny + n_escalate} candidates...")

    allow_candidates = generate_allow_scenarios(n_allow, rng)
    deny_candidates = generate_deny_scenarios(n_deny, rng)
    escalate_candidates = generate_escalate_scenarios(n_escalate, rng)

    # Validate each set
    print("\nValidating allow scenarios...")
    allow_ok, allow_bad = validate_scenarios(engine, allow_candidates)
    print(f"  {len(allow_ok)} correct, {len(allow_bad)} incorrect")

    print("Validating deny scenarios...")
    deny_ok, deny_bad = validate_scenarios(engine, deny_candidates)
    print(f"  {len(deny_ok)} correct, {len(deny_bad)} incorrect")

    print("Validating escalate scenarios...")
    esc_ok, esc_bad = validate_scenarios(engine, escalate_candidates)
    print(f"  {len(esc_ok)} correct, {len(esc_bad)} incorrect")

    # Show some incorrect examples
    for label, bad_list in [("allow", allow_bad), ("deny", deny_bad), ("escalate", esc_bad)]:
        if bad_list:
            print(f"\n  Sample incorrect {label}:")
            for s in bad_list[:3]:
                print(f"    expected={s['expected']} actual={s['_actual']}: \"{s['action']}\"")

    # Deduplicate against existing corpus
    existing_actions = set()
    for f in sorted(Path("scenarios").glob("*.json")):
        with open(f) as fh:
            data = json.load(fh)
            if isinstance(data, list):
                for s in data:
                    existing_actions.add(s["action"].lower())
            else:
                existing_actions.add(data["action"].lower())

    all_new = allow_ok + deny_ok + esc_ok
    deduped = [s for s in all_new if s["action"].lower() not in existing_actions]
    # Also deduplicate within the new set
    seen = set()
    unique = []
    for s in deduped:
        key = s["action"].lower()
        if key not in seen:
            seen.add(key)
            unique.append(s)

    print(f"\nAfter dedup: {len(unique)} new unique scenarios (from {len(all_new)} valid)")
    print(f"  allow: {sum(1 for s in unique if s['expected'] == 'allow')}")
    print(f"  deny: {sum(1 for s in unique if s['expected'] == 'deny')}")
    print(f"  escalate: {sum(1 for s in unique if s['expected'] == 'escalate')}")

    # Remove empty context keys (clean output)
    for s in unique:
        if not s.get("context"):
            s.pop("context", None)

    # Write output
    outfile = Path("scenarios/generated_expansion.json")
    with open(outfile, "w") as f:
        json.dump(unique, f, indent=2)
    print(f"\nWrote {len(unique)} scenarios to {outfile}")

    # Final corpus size
    total = len(existing_actions) + len(unique)
    print(f"New corpus total: {total} scenarios")
    print(f"p99 index: {int(total * 0.99)} (was {int(len(existing_actions) * 0.99)})")


if __name__ == "__main__":
    main()
