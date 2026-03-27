"""Reporting and scoring helpers for constitutions."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .constitution import Constitution


def get_governance_metrics(constitution: Constitution) -> dict[str, Any]:
    """exp163: Real-time governance performance metrics dashboard.

    Provides comprehensive metrics about constitution health, rule distribution,
    complexity analysis, and governance effectiveness indicators. Useful for
    monitoring and optimizing governance systems.

    Returns:
        dict with keys:
            - ``rule_counts``: breakdown by severity, category, status
            - ``complexity_metrics``: keyword density, dependency depth, etc.
            - ``health_indicators``: conflicts, orphans, validation status
            - ``usage_patterns``: rule activation frequency estimates
    """
    # Rule counts by severity
    severity_counts: dict[str, int] = {}
    for rule in constitution.rules:
        sev = rule.severity.value
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    # Rule counts by category
    category_counts: dict[str, int] = {}
    for rule in constitution.rules:
        cat = rule.category or "uncategorized"
        category_counts[cat] = category_counts.get(cat, 0) + 1

    # Status breakdown
    enabled_count = sum(1 for r in constitution.rules if r.enabled)
    hardcoded_count = sum(1 for r in constitution.rules if r.hardcoded)

    # Complexity metrics
    total_keywords = sum(len(r.keywords) for r in constitution.rules)
    avg_keywords_per_rule = total_keywords / len(constitution.rules) if constitution.rules else 0

    # Dependency analysis
    explicit_deps = sum(len(r.depends_on) for r in constitution.rules)
    dep_graph = constitution.dependency_graph()
    orphan_rules = len(dep_graph["orphans"])
    root_rules = len(dep_graph["roots"])

    # Health indicators
    conflicts = constitution.detect_semantic_conflicts()
    conflict_count = len(conflicts) if isinstance(conflicts, list) else 0

    # Validation status (would be populated from validation history)
    validation_status = "valid"  # assume valid since we validate on load

    # Usage pattern estimates (based on rule characteristics)
    high_impact_rules = sum(
        1 for r in constitution.rules if r.severity.value in ["high", "critical"]
    )
    low_impact_rules = sum(1 for r in constitution.rules if r.severity.value in ["info", "low"])

    return {
        "rule_counts": {
            "total": len(constitution.rules),
            "by_severity": severity_counts,
            "by_category": category_counts,
            "enabled": enabled_count,
            "disabled": len(constitution.rules) - enabled_count,
            "hardcoded": hardcoded_count,
        },
        "complexity_metrics": {
            "avg_keywords_per_rule": round(avg_keywords_per_rule, 2),
            "total_keywords": total_keywords,
            "explicit_dependencies": explicit_deps,
            "dependency_depth": len(dep_graph["edges"]),
        },
        "health_indicators": {
            "orphan_rules": orphan_rules,
            "root_rules": root_rules,
            "semantic_conflicts": conflict_count,
            "validation_status": validation_status,
        },
        "usage_patterns": {
            "high_impact_rules": high_impact_rules,
            "low_impact_rules": low_impact_rules,
            "estimated_coverage": round((enabled_count / len(constitution.rules)) * 100, 1)
            if constitution.rules
            else 0,
        },
    }


def health_score(constitution: Constitution) -> dict[str, Any]:
    """exp130: Composite governance quality metric for this constitution.

    Evaluates constitution quality across five dimensions and returns a
    weighted composite score (0.0 - 1.0).  Useful for CI/CD quality gates,
    operator dashboards, and inter-constitution comparison.

    Dimensions (equal weight, 0.0-1.0 each):

    1. **Documentation** — fraction of rules with non-empty text, category,
       and at least one tag.
    2. **Specificity** — average keyword count per rule (more specific rules
       are harder to bypass); capped at 3 keywords for full score.
    3. **Conflict-freedom** — penalty for pairs of rules with identical
       keywords but different severities (conflicts found by
       :meth:`detect_conflicts`).
    4. **Dependency soundness** — fraction of ``depends_on`` references that
       resolve to real rule IDs.
    5. **Coverage** — fraction of rules that have at least one keyword or
       pattern (purely abstract rules without any detection signal score 0).

    Returns:
        dict with keys:

        - ``composite``: weighted average (0.0 - 1.0)
        - ``documentation``: documentation sub-score
        - ``specificity``: specificity sub-score
        - ``conflict_freedom``: conflict-freedom sub-score
        - ``dependency_soundness``: dependency soundness sub-score
        - ``coverage``: coverage sub-score
        - ``rule_count``: total active rules evaluated
        - ``grade``: letter grade (A >= 0.9, B >= 0.75, C >= 0.6, D >= 0.45, F)

    Example::

        score = health_score(constitution)
        if score["composite"] < 0.7:
            raise RuntimeError(f"Constitution quality too low: {score['grade']}")
    """
    active = constitution.active_rules()
    n = len(active)
    if n == 0:
        return {
            "composite": 0.0,
            "documentation": 0.0,
            "specificity": 0.0,
            "conflict_freedom": 1.0,
            "dependency_soundness": 1.0,
            "coverage": 0.0,
            "rule_count": 0,
            "grade": "F",
        }

    rule_ids = {r.id for r in constitution.rules}

    # 1. Documentation: text + category + >=1 tag
    doc_scores = [
        (1.0 if r.text.strip() else 0.0) * 0.4
        + (1.0 if r.category and r.category != "general" else 0.3) * 0.3
        + (1.0 if r.tags else 0.0) * 0.3
        for r in active
    ]
    documentation = sum(doc_scores) / n

    # 2. Specificity: avg keyword count (saturates at 3)
    specificity = min(
        1.0,
        sum(min(len(r.keywords), 3) / 3.0 for r in active) / n,
    )

    # 3. Conflict-freedom: each conflict pair reduces score
    try:
        conflicts = constitution.detect_conflicts()
        num_conflicts = len(conflicts.get("conflicts", []))
        # Penalty: each conflict costs 0.1, floor at 0
        conflict_freedom = max(0.0, 1.0 - num_conflicts * 0.1)
    except (AttributeError, TypeError, RuntimeError):
        conflict_freedom = 1.0  # can't assess — assume clean

    # 4. Dependency soundness: fraction of depends_on refs that resolve
    total_deps = sum(len(r.depends_on) for r in active)
    if total_deps == 0:
        dependency_soundness = 1.0
    else:
        valid_deps = sum(sum(1 for dep in r.depends_on if dep in rule_ids) for r in active)
        dependency_soundness = valid_deps / total_deps

    # 5. Coverage: fraction of rules with >=1 keyword or pattern
    cov = sum(1.0 if (r.keywords or r.patterns) else 0.0 for r in active) / n

    composite = (documentation + specificity + conflict_freedom + dependency_soundness + cov) / 5.0

    if composite >= 0.9:
        grade = "A"
    elif composite >= 0.75:
        grade = "B"
    elif composite >= 0.6:
        grade = "C"
    elif composite >= 0.45:
        grade = "D"
    else:
        grade = "F"

    return {
        "composite": round(composite, 4),
        "documentation": round(documentation, 4),
        "specificity": round(specificity, 4),
        "conflict_freedom": round(conflict_freedom, 4),
        "dependency_soundness": round(dependency_soundness, 4),
        "coverage": round(cov, 4),
        "rule_count": n,
        "grade": grade,
    }


def maturity_level(constitution: Constitution) -> dict[str, Any]:
    """exp139: Score governance maturity on a 1-5 capability scale.

    Evaluates the constitution against a progressive maturity model.
    Each level builds on the previous, assessing increasingly sophisticated
    governance capabilities.

    Maturity Levels:

    1. **Initial** — Rules exist with basic keywords and categories.
    2. **Managed** — Rules have documentation (text, tags) and severity variety.
    3. **Defined** — Rules use advanced features: dependencies, priorities,
       workflow actions, conditions.
    4. **Quantitatively Managed** — Constitution uses analytic features:
       versioning (rule_history), conflict detection, health/coverage tooling.
    5. **Optimising** — Constitution uses all advanced governance features:
       temporal validity, embeddings, inheritance, templates, changelog.

    Returns:
        dict with keys:

        - ``level``: achieved maturity level (1-5)
        - ``label``: human-readable level name
        - ``score``: continuous score 0.0-5.0 for partial credit
        - ``criteria``: per-level pass/fail breakdown
        - ``next_level_gaps``: list of unmet criteria for the next level

    Example::

        m = maturity_level(constitution)
        print(f"Maturity: Level {m['level']} - {m['label']}")
        if m['level'] < 3:
            print("Gaps:", m['next_level_gaps'])
    """
    active = constitution.active_rules()
    n = len(active)
    all_rules = constitution.rules

    criteria: dict[str, bool] = {}

    # -- Level 1: Initial ------------------------------------------------
    criteria["has_rules"] = n >= 1
    criteria["has_keywords"] = any(r.keywords for r in active)
    criteria["has_categories"] = any(r.category for r in active)
    level1 = all(criteria[k] for k in ["has_rules", "has_keywords", "has_categories"])

    # -- Level 2: Managed ------------------------------------------------
    criteria["has_rule_text"] = any(r.text.strip() for r in active)
    criteria["has_tags"] = any(r.tags for r in active)
    criteria["has_severity_variety"] = len({r.severity for r in active}) >= 2
    criteria["has_multiple_categories"] = len({r.category for r in active}) >= 2
    level2 = level1 and all(
        criteria[k]
        for k in [
            "has_rule_text",
            "has_tags",
            "has_severity_variety",
            "has_multiple_categories",
        ]
    )

    # -- Level 3: Defined ------------------------------------------------
    criteria["uses_dependencies"] = any(r.depends_on for r in all_rules)
    criteria["uses_priorities"] = any(r.priority != 0 for r in all_rules)
    criteria["uses_workflow_actions"] = any(r.workflow_action for r in active)
    criteria["uses_conditions"] = any(r.condition for r in all_rules)
    level3 = level2 and all(
        criteria[k]
        for k in [
            "uses_dependencies",
            "uses_priorities",
            "uses_workflow_actions",
            "uses_conditions",
        ]
    )

    # -- Level 4: Quantitatively Managed ---------------------------------
    criteria["uses_versioning"] = bool(constitution.rule_history)
    criteria["uses_changelog"] = bool(constitution.changelog)
    criteria["has_conflict_detection"] = hasattr(constitution, "detect_conflicts")
    criteria["has_health_tooling"] = hasattr(constitution, "health_score")
    level4 = level3 and all(
        criteria[k]
        for k in [
            "uses_versioning",
            "uses_changelog",
            "has_conflict_detection",
            "has_health_tooling",
        ]
    )

    # -- Level 5: Optimising ---------------------------------------------
    criteria["uses_temporal"] = any(
        getattr(r, "valid_from", None) or getattr(r, "valid_until", None) for r in all_rules
    )
    criteria["uses_embeddings"] = any(getattr(r, "embedding", None) for r in all_rules)
    criteria["uses_deprecation"] = any(r.deprecated for r in all_rules)
    criteria["has_regulatory_tooling"] = hasattr(constitution, "regulatory_alignment")
    level5 = level4 and all(
        criteria[k]
        for k in [
            "uses_temporal",
            "uses_embeddings",
            "uses_deprecation",
            "has_regulatory_tooling",
        ]
    )

    # Determine achieved level
    if level5:
        level, label = 5, "Optimising"
    elif level4:
        level, label = 4, "Quantitatively Managed"
    elif level3:
        level, label = 3, "Defined"
    elif level2:
        level, label = 2, "Managed"
    elif level1:
        level, label = 1, "Initial"
    else:
        level, label = 0, "Ad hoc"

    # Continuous score: base + partial credit from next level
    level_keys = {
        1: ["has_rules", "has_keywords", "has_categories"],
        2: [
            "has_rule_text",
            "has_tags",
            "has_severity_variety",
            "has_multiple_categories",
        ],
        3: [
            "uses_dependencies",
            "uses_priorities",
            "uses_workflow_actions",
            "uses_conditions",
        ],
        4: [
            "uses_versioning",
            "uses_changelog",
            "has_conflict_detection",
            "has_health_tooling",
        ],
        5: [
            "uses_temporal",
            "uses_embeddings",
            "uses_deprecation",
            "has_regulatory_tooling",
        ],
    }
    partial = 0.0
    if level < 5:
        next_keys = level_keys.get(level + 1, [])
        if next_keys:
            partial = sum(1 for k in next_keys if criteria.get(k)) / len(next_keys)
    score = round(level + partial, 2)

    # Next-level gaps
    next_gaps: list[str] = []
    if level < 5:
        next_keys = level_keys.get(level + 1, [])
        next_gaps = [k for k in next_keys if not criteria.get(k)]

    return {
        "level": level,
        "label": label,
        "score": score,
        "criteria": criteria,
        "next_level_gaps": next_gaps,
    }


def coverage_gaps(constitution: Constitution) -> dict[str, Any]:
    """exp134: Identify governance domains and categories with thin or zero coverage.

    Scans the constitution for governance blind spots — areas where agents
    may act without any rule checking their behaviour.  Returns three levels
    of concern:

    - **uncovered_domains**: High-level governance domains (safety, privacy,
      fairness, transparency, security) for which *no* active rule exists
      whose category or keywords signal that domain.
    - **thin_categories**: Categories with fewer than ``min_rules`` (default 2)
      active rules — likely under-specified.
    - **disabled_only_categories**: Categories where every rule is disabled,
      leaving the category entirely unenforced.

    Returns:
        dict with keys:

        - ``uncovered_domains``: list of domain names with zero active rule
          coverage (based on :attr:`_DOMAIN_SIGNAL_MAP`).
        - ``thin_categories``: dict mapping category -> active rule count for
          categories with 1-(min_rules-1) active rules.
        - ``disabled_only_categories``: list of categories that have rules
          but all are disabled.
        - ``total_categories``: total distinct categories across all rules.
        - ``coverage_score``: fraction of known domains that are covered
          (0.0 - 1.0).
        - ``min_rules``: threshold used for thin-category detection.

    Example::

        gaps = coverage_gaps(constitution)
        if gaps["uncovered_domains"]:
            warnings.warn(f"No rules for: {gaps['uncovered_domains']}")
    """
    min_rules = 2
    active = constitution.active_rules()
    all_rules = constitution.rules

    # -- Domain coverage --------------------------------------------------
    # A domain is "covered" if >=1 active rule has a category or keyword
    # matching that domain's signal set.
    domain_covered: dict[str, bool] = {}
    for domain, signals in constitution._DOMAIN_SIGNAL_MAP.items():
        signal_cats: set[str] = signals.get("categories", set())
        signal_kws: set[str] = signals.get("keywords", set())
        covered = any(
            r.category in signal_cats or bool(signal_kws & {kw.lower() for kw in r.keywords})
            for r in active
        )
        domain_covered[domain] = covered

    uncovered_domains = sorted(d for d, v in domain_covered.items() if not v)
    covered_count = sum(1 for v in domain_covered.values() if v)
    coverage_score_val = covered_count / len(domain_covered) if domain_covered else 1.0

    # -- Category analysis ------------------------------------------------
    # Count active rules per category
    cat_active: dict[str, int] = {}
    cat_total: dict[str, int] = {}
    for r in all_rules:
        cat = r.category or "general"
        cat_total[cat] = cat_total.get(cat, 0) + 1
        if r.enabled:
            cat_active[cat] = cat_active.get(cat, 0) + 1

    thin_categories = {cat: count for cat, count in cat_active.items() if 0 < count < min_rules}
    disabled_only_categories = sorted(cat for cat in cat_total if cat_active.get(cat, 0) == 0)

    return {
        "uncovered_domains": uncovered_domains,
        "thin_categories": thin_categories,
        "disabled_only_categories": disabled_only_categories,
        "total_categories": len(cat_total),
        "coverage_score": round(coverage_score_val, 4),
        "min_rules": min_rules,
    }


def full_report(
    constitution: Constitution,
    *,
    regulatory_framework: str = "soc2",
    similarity_threshold: float = 0.7,
    include_similar_rules: bool = True,
) -> dict[str, Any]:
    """exp140: Comprehensive governance report combining all analytical dimensions.

    Bundles the outputs of multiple analytical methods into a single
    JSON-serializable dict.  Designed for CI/CD quality gates,
    governance dashboards, and compliance documentation exports.

    Args:
        regulatory_framework: Framework for :meth:`regulatory_alignment`
            — one of ``"soc2"``, ``"hipaa"``, ``"gdpr"``, ``"iso27001"``.
        similarity_threshold: Minimum Jaccard similarity for
            :meth:`find_similar_rules`. Default 0.7.
        include_similar_rules: If True, include near-duplicate analysis
            (O(n^2) — disable for large constitutions with >100 rules).

    Returns:
        dict with top-level keys:

        - ``identity``: constitution name, version, description, hash,
          rule_count, active_rule_count, generated_at (ISO timestamp)
        - ``health``: output of :func:`health_score`
        - ``maturity``: output of :func:`maturity_level`
        - ``coverage``: output of :func:`coverage_gaps`
        - ``regulatory``: output of :meth:`regulatory_alignment`
        - ``deprecation``: output of :meth:`deprecation_report`
        - ``similar_rules``: output of :meth:`find_similar_rules`
          (empty list if ``include_similar_rules=False``)
        - ``changelog_summary``: output of :meth:`changelog_summary`

    Example::

        report = full_report(constitution, regulatory_framework="gdpr")
        if report["health"]["composite"] < 0.7:
            raise ValueError("Constitution quality gate failed")
        print(f"Maturity: {report['maturity']['label']}")
    """
    ts = datetime.now(timezone.utc).isoformat()
    active = constitution.active_rules()

    identity = {
        "name": constitution.name,
        "version": constitution.version,
        "description": constitution.description,
        "hash": constitution.hash,
        "rule_count": len(constitution.rules),
        "active_rule_count": len(active),
        "generated_at": ts,
    }

    similar: list[dict[str, Any]] = []
    if include_similar_rules:
        similar = constitution.find_similar_rules(threshold=similarity_threshold)

    try:
        regulatory = constitution.regulatory_alignment(regulatory_framework)
    except ValueError:
        regulatory = {"error": f"Unknown framework: {regulatory_framework}"}

    return {
        "identity": identity,
        "health": health_score(constitution),
        "maturity": maturity_level(constitution),
        "coverage": coverage_gaps(constitution),
        "regulatory": regulatory,
        "deprecation": constitution.deprecation_report(),
        "similar_rules": similar,
        "changelog_summary": constitution.changelog_summary(),
    }


def compliance_report(constitution: Constitution, *, framework: str = "soc2") -> dict[str, Any]:
    """exp145: Regulatory-focused compliance report for legal/audit consumers.

    Builds a concise, framework-centric compliance report by composing
    :meth:`regulatory_alignment`, :func:`posture_score`,
    :func:`coverage_gaps`, and :func:`health_score`.  Designed for export
    into human-readable compliance documents without requiring callers to
    manually stitch multiple analytical outputs together.

    Args:
        framework: Regulatory framework to assess. Passed through to
            :meth:`regulatory_alignment`. One of ``"soc2"``, ``"hipaa"``,
            ``"gdpr"``, ``"iso27001"``. Case-insensitive.

    Returns:
        dict with keys:

        - ``summary``: high-level numeric scores and pass/fail flags
        - ``regulatory_alignment``: output of :meth:`regulatory_alignment`
        - ``governance_posture``: output of :func:`posture_score`
        - ``health``: output of :func:`health_score`
        - ``coverage``: output of :func:`coverage_gaps`
        - ``recommended_actions``: textual recommendations focusing on
          uncovered controls and low-scoring posture dimensions

    The method intentionally avoids touching the hot validation path; it
    only consumes cached analytical summaries.
    """
    try:
        reg = constitution.regulatory_alignment(framework)
    except ValueError as exc:
        return {
            "summary": {
                "framework": framework.lower(),
                "error": str(exc),
            },
            "regulatory_alignment": {},
            "governance_posture": {},
            "health": {},
            "coverage": {},
            "recommended_actions": [
                "Select one of the supported frameworks: soc2, hipaa, gdpr, iso27001."
            ],
        }

    posture = posture_score(constitution)
    h = health_score(constitution)
    cov = coverage_gaps(constitution)

    alignment_score = float(reg.get("alignment_score", 0.0))
    uncovered_controls: list[str] = list(reg.get("uncovered_controls", []))

    recommendations: list[str] = []

    if uncovered_controls:
        recommendations.append(
            "Define or refine rules to cover uncovered controls: "
            + ", ".join(sorted(uncovered_controls))
        )

    if posture.get("grade") in {"C", "D", "F", None}:
        recommendations.append(
            "Improve overall governance posture by addressing health, coverage, "
            "and maturity gaps highlighted in the posture_score breakdown."
        )

    if h.get("composite", 1.0) < 0.7:
        recommendations.append(
            "Strengthen rule documentation, specificity, and dependency structure "
            "to raise the health_score composite above 0.7."
        )

    if cov.get("coverage_score", 1.0) < 0.7:
        recommendations.append(
            "Increase coverage of key governance domains (safety, privacy, "
            "transparency, fairness, accountability) until coverage_score "
            "is at least 0.7."
        )

    summary = {
        "framework": reg.get("framework", framework.lower()),
        "alignment_score": alignment_score,
        "alignment_percent": round(alignment_score * 100.0, 1),
        "posture_score": posture.get("posture"),
        "posture_grade": posture.get("grade"),
        "posture_ci_pass": posture.get("ci_pass"),
        "uncovered_controls": uncovered_controls,
        "total_controls": reg.get("total_controls", 0),
    }

    return {
        "summary": summary,
        "regulatory_alignment": reg,
        "governance_posture": posture,
        "health": h,
        "coverage": cov,
        "recommended_actions": recommendations,
    }


def posture_score(constitution: Constitution, ci_threshold: float = 0.70) -> dict[str, Any]:
    """exp139: Unified governance posture score for CI/CD gates and dashboards.

    Combines three independent quality axes into a single normalised score:

    1. **Health** (40%) — :func:`health_score` composite (docs, specificity,
       conflict-freedom, dependency soundness, keyword coverage).
    2. **Coverage** (35%) — domain coverage from :func:`coverage_gaps`;
       penalises missing or weak governance domains.
    3. **Maturity** (25%) — :func:`maturity_level` score normalised 0-1
       (CMMI-style 0-5 -> 0-1).

    Inspired by the NIST AI Risk Management Framework composite risk metrics
    and agentic AI governance lifecycle management research (2025-2026).

    Args:
        ci_threshold: Minimum posture score for ``ci_pass`` to be True.
                      Default 0.70. Set higher for stricter environments.

    Returns:
        dict with keys:

        - ``posture``: composite 0.0-1.0 weighted score
        - ``grade``: letter grade (A+ >= 0.95, A >= 0.90, B >= 0.75,
          C >= 0.60, D >= 0.45, F < 0.45)
        - ``health``: health sub-score (0-1)
        - ``coverage``: coverage sub-score (0-1)
        - ``maturity``: maturity sub-score (0-1, raw 0-5 normalised)
        - ``recommendations``: list of actionable improvement suggestions
        - ``ci_pass``: bool -- True if posture >= *ci_threshold*

    Example::

        result = posture_score(constitution, ci_threshold=0.80)
        if not result["ci_pass"]:
            raise SystemExit(
                f"Governance posture below CI threshold: {result['grade']}"
            )
    """
    # -- health sub-score -------------------------------------------------
    hs = health_score(constitution)
    health_val = float(hs.get("composite", 0.0))

    # -- coverage sub-score -----------------------------------------------
    cg: dict[str, Any] = {}
    try:
        cg = coverage_gaps(constitution)
        coverage_score_raw = float(cg.get("coverage_score", 0.0))
        coverage_val = min(1.0, max(0.0, coverage_score_raw))
    except (KeyError, TypeError, ValueError):
        coverage_val = 0.5  # can't assess — neutral

    # -- maturity sub-score -----------------------------------------------
    ml: dict[str, Any] = {}
    try:
        ml = maturity_level(constitution)
        raw_level = float(ml.get("score", 0.0))  # 0.0-5.0
        maturity_val = min(1.0, raw_level / 5.0)
    except (KeyError, TypeError, ValueError):
        maturity_val = 0.0

    # -- weighted composite -----------------------------------------------
    posture = round(health_val * 0.40 + coverage_val * 0.35 + maturity_val * 0.25, 4)

    if posture >= 0.95:
        grade = "A+"
    elif posture >= 0.90:
        grade = "A"
    elif posture >= 0.75:
        grade = "B"
    elif posture >= 0.60:
        grade = "C"
    elif posture >= 0.45:
        grade = "D"
    else:
        grade = "F"

    # -- actionable recommendations ---------------------------------------
    recommendations: list[str] = []
    if health_val < 0.7:
        hs_grade = hs.get("grade", "?")
        recommendations.append(
            f"Improve health score ({hs_grade}) — add tags/keywords/category to rules."
        )
    if coverage_val < 0.7:
        try:
            missing = cg.get("missing_domains", [])
            weak = cg.get("weak_domains", [])
            if missing:
                recommendations.append(f"Add rules covering missing domains: {', '.join(missing)}.")
            elif weak:
                recommendations.append(f"Expand thin governance domains: {', '.join(weak)}.")
            else:
                recommendations.append("Improve domain coverage breadth.")
        except (KeyError, TypeError, AttributeError):
            recommendations.append("Audit governance domain coverage.")
    if maturity_val < 0.6:
        try:
            gaps = ml.get("next_level_gaps", [])
            if gaps:
                recommendations.append(f"Advance maturity by addressing: {', '.join(gaps[:3])}.")
            else:
                recommendations.append("Advance governance maturity level.")
        except (KeyError, TypeError, AttributeError):
            recommendations.append("Advance governance maturity level.")

    return {
        "posture": posture,
        "grade": grade,
        "health": round(health_val, 4),
        "coverage": round(coverage_val, 4),
        "maturity": round(maturity_val, 4),
        "recommendations": recommendations,
        "ci_pass": posture >= ci_threshold,
    }
