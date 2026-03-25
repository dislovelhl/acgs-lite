# ACGS - Constitutional AI Governance
# Copyright (C) 2024-2026 ACGS Contributors
# Licensed under AGPL-3.0-or-later. See LICENSE for details.
# Commercial license: https://acgs.ai

"""CLI for ACGS — constitutional governance for AI agents.

Constitutional Hash: 608508a9bd224290

Commands:
    acgs init                   Scaffold rules.yaml + CI governance job
    acgs assess                 Run multi-framework compliance assessment
    acgs report [--pdf|--md]    Generate auditor-ready compliance report
    acgs activate <key>         Store license key
    acgs status                 Show current license tier and features
    acgs verify                 Validate license key integrity
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from acgs_lite.licensing import (
    LicenseError,
    LicenseExpiredError,
    LicenseInfo,
    LicenseManager,
    Tier,
    _write_license_file,
    validate_license_key,
)


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------

_DEFAULT_RULES_YAML = """\
# ACGS Constitutional Rules
# See: https://acgs.ai | pip install acgs
# EU AI Act enforcement: August 2, 2026

rules:
  - id: safety-001
    text: "Reject actions that could cause physical harm to humans"
    severity: critical
    keywords: ["harm", "injure", "kill", "weapon", "attack"]
    category: safety

  - id: privacy-001
    text: "Block unauthorized access to personal data"
    severity: high
    keywords: ["personal data", "PII", "SSN", "social security"]
    patterns: ["\\\\b\\\\d{3}-\\\\d{2}-\\\\d{4}\\\\b"]
    category: privacy

  - id: bias-001
    text: "Flag decisions that discriminate based on protected characteristics"
    severity: high
    keywords: ["race", "gender", "religion", "disability", "age"]
    category: fairness

  - id: transparency-001
    text: "Require explanation for consequential automated decisions"
    severity: medium
    keywords: ["reject", "deny", "terminate", "suspend"]
    category: transparency

  - id: oversight-001
    text: "Escalate high-impact decisions for human review"
    severity: medium
    keywords: ["approve", "authorize", "deploy", "release"]
    category: oversight
"""

_GITLAB_CI_SNIPPET = """\
# ACGS Governance Gate
# Validates every MR against constitutional rules
# Docs: https://acgs.ai | EU AI Act enforcement: August 2, 2026

governance:
  stage: test
  image: python:3.11-slim
  before_script:
    - pip install acgs
  script:
    - python3 -c "
      from acgs import Constitution, GovernanceEngine;
      c = Constitution.from_yaml('rules.yaml');
      e = GovernanceEngine(c);
      print(f'Constitutional hash: {c.hash}');
      print(f'Rules loaded: {len(c.rules)}');
      print('Governance gate: PASS');
      "
  rules:
    - if: $CI_PIPELINE_SOURCE == 'merge_request_event'
"""

_GITHUB_ACTIONS_SNIPPET = """\
# ACGS Governance Gate
# Validates every PR against constitutional rules
# Docs: https://acgs.ai | EU AI Act enforcement: August 2, 2026

name: ACGS Governance
on:
  pull_request:
    branches: [main]

jobs:
  governance:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install acgs
      - run: |
          python3 -c "
          from acgs import Constitution, GovernanceEngine
          c = Constitution.from_yaml('rules.yaml')
          e = GovernanceEngine(c)
          print(f'Constitutional hash: {c.hash}')
          print(f'Rules loaded: {len(c.rules)}')
          print('Governance gate: PASS')
          "
"""


def cmd_init(args: argparse.Namespace) -> int:
    """Scaffold rules.yaml and CI governance job in the current directory."""
    rules_path = Path("rules.yaml")
    force: bool = getattr(args, "force", False)

    if rules_path.exists() and not force:
        print(f"  rules.yaml already exists. Use --force to overwrite.", file=sys.stderr)
        return 1

    rules_path.write_text(_DEFAULT_RULES_YAML, encoding="utf-8")
    print(f"  ✅ Created rules.yaml ({5} rules)")

    # Generate acgs.json config
    config_path = Path("acgs.json")
    if not config_path.exists() or force:
        config = {
            "system_id": Path.cwd().name,
            "jurisdiction": "european_union",
            "domain": "",
            "rules": "rules.yaml",
            "_comment": "Edit jurisdiction/domain for auto-framework selection. See: acgs assess --help",
        }
        config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        print(f"  ✅ Created acgs.json (edit jurisdiction + domain)")
    else:
        print(f"  ℹ️  acgs.json already exists")

    # Detect CI system
    ci_path: Path | None = None
    ci_name = ""

    if Path(".gitlab-ci.yml").exists():
        ci_path = Path(".gitlab-ci.yml")
        ci_name = "GitLab CI"
        snippet = _GITLAB_CI_SNIPPET
    elif Path(".github/workflows").is_dir():
        ci_path = Path(".github/workflows/acgs-governance.yml")
        ci_name = "GitHub Actions"
        snippet = _GITHUB_ACTIONS_SNIPPET
    else:
        # Default to GitLab
        ci_path = Path(".gitlab-ci.yml")
        ci_name = "GitLab CI (new)"
        snippet = _GITLAB_CI_SNIPPET

    if ci_path and ci_path.exists() and not force:
        print(f"  ℹ️  {ci_path} exists — add this to your pipeline:")
        print()
        print(snippet)
    elif ci_path:
        ci_path.parent.mkdir(parents=True, exist_ok=True)
        if ci_path.exists():
            # Append to existing CI file
            with ci_path.open("a", encoding="utf-8") as f:
                f.write("\n\n" + snippet)
            print(f"  ✅ Appended governance job to {ci_path}")
        else:
            ci_path.write_text(snippet, encoding="utf-8")
            print(f"  ✅ Created {ci_path} ({ci_name})")

    print()
    print("  Next steps:")
    print("    1. Edit rules.yaml to match your governance requirements")
    print("    2. Run: acgs assess")
    print("    3. Run: acgs report --pdf")
    print()
    print("  EU AI Act deadline: August 2, 2026")
    print("  Docs: https://acgs.ai")

    return 0


# ---------------------------------------------------------------------------
# assess
# ---------------------------------------------------------------------------

def _load_system_description(args: argparse.Namespace) -> dict[str, Any]:
    """Build system description from CLI args or config file."""
    desc: dict[str, Any] = {}

    # Try loading from acgs.json if it exists
    config_path = Path("acgs.json")
    if config_path.exists():
        with config_path.open(encoding="utf-8") as f:
            desc = json.load(f)

    # CLI args override config file
    if getattr(args, "system_id", None):
        desc["system_id"] = args.system_id
    if getattr(args, "jurisdiction", None):
        desc["jurisdiction"] = args.jurisdiction
    if getattr(args, "domain", None):
        desc["domain"] = args.domain
    if getattr(args, "framework", None):
        desc["_frameworks"] = args.framework

    # Defaults
    desc.setdefault("system_id", Path.cwd().name)

    return desc


def cmd_assess(args: argparse.Namespace) -> int:
    """Run multi-framework compliance assessment."""
    from acgs_lite.compliance import MultiFrameworkAssessor

    desc = _load_system_description(args)
    requested_fws: list[str] | None = desc.pop("_frameworks", None)

    assessor = MultiFrameworkAssessor(frameworks=requested_fws)
    report = assessor.assess(desc)

    # Print results
    print()
    print("  ACGS Compliance Assessment")
    print("  " + "=" * 50)
    print()
    print(f"  System:              {report.system_id}")
    print(f"  Overall Score:       {report.overall_score:.0%}")
    print(f"  ACGS Auto-Coverage:  {report.acgs_lite_total_coverage:.0%}")
    print(f"  Frameworks:          {', '.join(report.frameworks_assessed)}")
    print()

    # Per-framework summary
    for fw_id, assessment in report.by_framework.items():
        score_bar = _cli_bar(assessment.compliance_score)
        gap_count = len(assessment.gaps)
        label = f"  {assessment.framework_name}"
        print(f"{label:<42} {score_bar}  ({gap_count} gaps)")

    print()

    # Cross-framework gaps
    if report.cross_framework_gaps:
        print("  Cross-Framework Gaps:")
        for gap in report.cross_framework_gaps:
            # Truncate long gap text
            short = gap[:100] + "..." if len(gap) > 100 else gap
            print(f"    ⚠  {short}")
        print()

    # Top recommendations
    if report.recommendations:
        top = report.recommendations[:5]
        print("  Top Recommendations:")
        for i, rec in enumerate(top, 1):
            short = rec[:100] + "..." if len(rec) > 100 else rec
            print(f"    {i}. {short}")
        if len(report.recommendations) > 5:
            print(f"    ... and {len(report.recommendations) - 5} more (see full report)")
        print()

    # Verdict
    if report.overall_score >= 0.8:
        print("  🟢 STRONG — Address remaining gaps, then request conformity assessment.")
    elif report.overall_score >= 0.5:
        print("  🟡 MODERATE — Significant work remains before Aug 2, 2026.")
    else:
        print("  🔴 AT RISK — Major gaps. Immediate action required.")
    print()
    print("  → Generate full report: acgs report --pdf")
    print()

    # Save JSON for report command
    cache_path = Path(".acgs_assessment.json")
    cache_path.write_text(
        json.dumps(report.to_dict(), indent=2, default=str), encoding="utf-8"
    )

    return 0


def _cli_bar(score: float, width: int = 20) -> str:
    """Render a text bar for terminal output."""
    filled = int(score * width)
    return f"[{'█' * filled}{'░' * (width - filled)}] {score:.0%}"


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

def cmd_report(args: argparse.Namespace) -> int:
    """Generate auditor-ready compliance report (PDF, Markdown, or JSON)."""
    from acgs_lite.report import generate_report

    # Load assessment data
    cache_path = Path(".acgs_assessment.json")
    if cache_path.exists():
        with cache_path.open(encoding="utf-8") as f:
            report_data = json.load(f)
    else:
        # Run assessment first
        print("  No cached assessment found. Running assessment first...")
        print()
        from acgs_lite.compliance import MultiFrameworkAssessor

        desc = _load_system_description(args)
        requested_fws: list[str] | None = desc.pop("_frameworks", None)
        assessor = MultiFrameworkAssessor(frameworks=requested_fws)
        report = assessor.assess(desc)
        report_data = report.to_dict()

    # Determine format
    fmt = "pdf"
    if getattr(args, "markdown", False) or getattr(args, "md", False):
        fmt = "markdown"
    elif getattr(args, "json", False):
        fmt = "json"

    # Determine output path
    output = getattr(args, "output", None)
    if output:
        output_path = Path(output)
    else:
        system_id = report_data.get("system_id", "system")
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in system_id)
        output_path = Path(f"acgs_compliance_{safe_name}.{fmt if fmt != 'markdown' else 'md'}")

    try:
        result_path = generate_report(report_data, output_path, format=fmt)
        print()
        print(f"  ✅ Report generated: {result_path}")
        print(f"     Format: {fmt.upper()}")
        print(f"     System: {report_data.get('system_id', 'Unknown')}")
        print(f"     Score:  {report_data.get('overall_score', 0):.0%}")
        print()

        if fmt == "pdf":
            print("  This report is ready to share with your compliance officer.")
        elif fmt == "markdown":
            print("  Commit this report to your repository for audit trail.")

        print()
        return 0

    except ImportError as e:
        # fpdf2 not installed — fallback files were written
        print()
        print(f"  ⚠  {e}")
        print()
        print("  To generate PDF reports:")
        print("    pip install fpdf2")
        print()
        # Still return 0 because markdown/json fallback was written
        return 0


# ---------------------------------------------------------------------------
# License commands (preserved from original)
# ---------------------------------------------------------------------------

def cmd_activate(args: argparse.Namespace) -> int:
    """Store a license key."""
    key: str = args.key.strip()
    try:
        info = validate_license_key(key)
    except LicenseExpiredError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except LicenseError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    _write_license_file(key)
    print(f"License activated: {info.tier.name}")
    _print_license_info(info)
    return 0


def cmd_status(_args: argparse.Namespace) -> int:
    """Show current license tier and features."""
    manager = LicenseManager()
    try:
        info = manager.load()
    except LicenseExpiredError as exc:
        print(f"Warning: {exc}", file=sys.stderr)
        from acgs_lite.licensing import _read_license_file

        import os

        key = os.environ.get("ACGS_LICENSE_KEY") or _read_license_file()
        if key:
            try:
                info = validate_license_key.__wrapped__(key)  # type: ignore[attr-defined]
            except Exception:
                print("Could not parse license key.", file=sys.stderr)
                return 1
        else:
            return 1
    except LicenseError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print("acgs License Status")
    print("=" * 40)
    _print_license_info(info)

    if info.tier == Tier.FREE:
        print()
        print("  → Upgrade to Pro for EU AI Act compliance:")
        print("    https://acgs.ai/pricing")

    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    """Validate a license key."""
    from acgs_lite.licensing import _read_license_file

    key_arg: str | None = getattr(args, "key", None)
    key: str | None

    if key_arg:
        key = key_arg.strip()
    else:
        import os

        env_key = os.environ.get("ACGS_LICENSE_KEY")
        key = env_key if env_key is not None else _read_license_file()

    if not key:
        print("No license key found. Run 'acgs activate <key>' first.", file=sys.stderr)
        return 1

    print(f"Verifying key: {key[:20]}...")
    try:
        info = validate_license_key(key)
        print("✓ Key is valid.")
        _print_license_info(info)
        return 0
    except LicenseExpiredError as exc:
        print(f"✗ Key is EXPIRED: {exc}", file=sys.stderr)
        return 1
    except LicenseError as exc:
        print(f"✗ Key is INVALID: {exc}", file=sys.stderr)
        return 1


def _print_license_info(info: Any) -> None:
    """Print license info in a formatted way."""
    print(f"  Tier:    {_fmt_tier_badge(info.tier)}")
    if info.expiry_date:
        print(f"  Expiry:  {info.expiry_date}")
    else:
        print("  Expiry:  none (perpetual)")
    print()
    print("  Features:")
    for feature in info.features:
        print(f"    • {feature}")


def _fmt_tier_badge(tier: Any) -> str:
    """Format a license tier as a display badge."""
    badges = {
        Tier.FREE: "FREE",
        Tier.PRO: "PRO ✓",
        Tier.TEAM: "TEAM ✓",
        Tier.ENTERPRISE: "ENTERPRISE ✓",
    }
    return badges.get(tier, tier.name)


# Backward-compat alias (used by test_coverage_batch_j.py)
_print_info = _print_license_info


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="acgs",
        description="ACGS — Constitutional governance for AI agents",
        epilog="EU AI Act enforcement: August 2, 2026 | https://acgs.ai",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # init
    p_init = sub.add_parser(
        "init",
        help="Scaffold rules.yaml + CI governance job",
    )
    p_init.add_argument("--force", action="store_true", help="Overwrite existing files")

    # assess
    p_assess = sub.add_parser(
        "assess",
        help="Run multi-framework compliance assessment",
    )
    p_assess.add_argument(
        "--system-id", default=None,
        help="System identifier (default: current directory name)",
    )
    p_assess.add_argument(
        "--jurisdiction", default=None,
        help="Jurisdiction (european_union, united_states, international, new_york_city)",
    )
    p_assess.add_argument(
        "--domain", default=None,
        help="Application domain (healthcare, lending, employment, financial)",
    )
    p_assess.add_argument(
        "--framework", action="append", default=None,
        help="Specific framework(s) to assess (repeatable: --framework gdpr --framework nist_ai_rmf)",
    )

    # report
    p_report = sub.add_parser(
        "report",
        help="Generate auditor-ready compliance report",
    )
    p_report.add_argument("--pdf", action="store_true", default=True, help="PDF output (default)")
    p_report.add_argument("--markdown", "--md", action="store_true", help="Markdown output")
    p_report.add_argument("--json", action="store_true", help="JSON output")
    p_report.add_argument("-o", "--output", default=None, help="Output file path")
    p_report.add_argument("--system-id", default=None, help="System identifier")
    p_report.add_argument("--jurisdiction", default=None, help="Jurisdiction")
    p_report.add_argument("--domain", default=None, help="Application domain")
    p_report.add_argument(
        "--framework", action="append", default=None,
        help="Specific framework(s)",
    )

    # activate
    p_activate = sub.add_parser("activate", help="Store a license key")
    p_activate.add_argument("key", help="License key (ACGS-{TIER}-...)")

    # status
    sub.add_parser("status", help="Show current license tier and features")

    # verify
    p_verify = sub.add_parser("verify", help="Validate license key integrity")
    p_verify.add_argument("--key", help="Key to verify (default: currently loaded key)")

    # eu-ai-act
    p_eu = sub.add_parser(
        "eu-ai-act",
        help="One-shot EU AI Act compliance assessment + report",
    )
    p_eu.add_argument("--system-id", default=None, help="System identifier")
    p_eu.add_argument("--domain", default=None, help="Application domain")
    p_eu.add_argument("--markdown", "--md", action="store_true", help="Markdown output")
    p_eu.add_argument("--json", dest="json_out", action="store_true", help="JSON output")
    p_eu.add_argument("-o", "--output", default=None, help="Output file path")

    # lint
    p_lint = sub.add_parser(
        "lint",
        help="Lint governance rules for quality issues",
    )
    p_lint.add_argument(
        "rules", nargs="?", default="rules.yaml",
        help="Path to rules YAML file (default: rules.yaml)",
    )

    return parser


# ---------------------------------------------------------------------------
# eu-ai-act (one-shot assess + report)
# ---------------------------------------------------------------------------

def cmd_eu_ai_act(args: argparse.Namespace) -> int:
    """One-shot EU AI Act compliance: assess + generate PDF report."""
    from acgs_lite.compliance import MultiFrameworkAssessor
    from acgs_lite.report import generate_report

    system_id = getattr(args, "system_id", None) or Path.cwd().name
    domain = getattr(args, "domain", None) or ""

    # EU AI Act focused frameworks
    eu_frameworks = ["gdpr", "iso_42001", "oecd_ai"]
    if domain in ("healthcare", "medical"):
        eu_frameworks.append("hipaa_ai")

    desc: dict[str, Any] = {
        "system_id": system_id,
        "jurisdiction": "european_union",
        "domain": domain,
    }

    assessor = MultiFrameworkAssessor(frameworks=eu_frameworks)
    report = assessor.assess(desc)

    # Print summary
    print()
    print("  EU AI Act Compliance Assessment")
    print("  " + "=" * 50)
    print(f"  System:            {report.system_id}")
    print(f"  Compliance Score:  {report.overall_score:.0%}")
    print(f"  ACGS Coverage:     {report.acgs_lite_total_coverage:.0%}")
    print(f"  Frameworks:        {', '.join(report.frameworks_assessed)}")
    print(f"  Enforcement:       August 2, 2026")
    print(f"  Max Penalty:       7% global revenue / EUR 35M")
    print()

    for fw_id, assessment in report.by_framework.items():
        bar = _cli_bar(assessment.compliance_score)
        gap_count = len(assessment.gaps)
        label = f"  {assessment.framework_name}"
        print(f"{label:<42} {bar}  ({gap_count} gaps)")

    print()

    # EU AI Act specific checklist
    from acgs_lite.eu_ai_act.compliance_checklist import ComplianceChecklist

    checklist = ComplianceChecklist(system_id=system_id)
    checklist.auto_populate_acgs_lite()

    print("  EU AI Act Article Checklist (High-Risk):")
    for item in checklist.items:
        icon = "✅" if item.status.value == "compliant" else "⬜"
        print(f"    {icon} {item.article_ref}: {item.requirement[:70]}...")

    print()
    print(f"  Gate Clear: {'✅ YES' if checklist.is_gate_clear else '❌ NO'}")
    print(f"  Checklist Score: {checklist.compliance_score:.0%}")
    print()

    if checklist.blocking_gaps:
        print("  Blocking Gaps (must resolve before Aug 2, 2026):")
        for gap in checklist.blocking_gaps:
            print(f"    ❌ {gap}")
        print()

    # Generate report
    report_data = report.to_dict()
    report_data["eu_ai_act_checklist"] = checklist.generate_report()

    fmt = "pdf"
    if getattr(args, "markdown", False):
        fmt = "markdown"
    elif getattr(args, "json_out", False):
        fmt = "json"

    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in system_id)
    output_path = getattr(args, "output", None) or f"eu_ai_act_{safe_name}"

    try:
        result = generate_report(report_data, output_path, format=fmt)
        print(f"  ✅ Report generated: {result}")
        print()
        print("  Hand this to your compliance officer. You're ahead of 99% of companies.")
        print()
    except ImportError as e:
        print(f"  ⚠  {e}")
        print("  Install fpdf2 for PDF: pip install acgs[pdf]")
        print()

    return 0


# ---------------------------------------------------------------------------
# lint
# ---------------------------------------------------------------------------

def cmd_lint(args: argparse.Namespace) -> int:
    """Lint governance rules for quality issues."""
    from acgs_lite.constitution import Constitution
    from acgs_lite.constitution.policy_linter import PolicyLinter

    rules_path = Path(getattr(args, "rules", "rules.yaml"))
    if not rules_path.exists():
        print(f"  ❌ {rules_path} not found. Run 'acgs init' first.", file=sys.stderr)
        return 1

    constitution = Constitution.from_yaml(str(rules_path))
    linter = PolicyLinter()
    report = linter.lint_constitution(constitution)

    print()
    print(f"  ACGS Policy Linter — {rules_path}")
    print("  " + "=" * 50)
    print(f"  Rules checked: {report.rules_checked}")
    print(f"  Issues found:  {len(report.issues)}")
    print()

    if report.issues:
        for issue in report.issues:
            icon = {"error": "❌", "warning": "⚠️ ", "info": "ℹ️ "}.get(
                issue.severity.value, "?"
            )
            rule_label = f" ({issue.rule_id})" if issue.rule_id else ""
            print(f"  {icon} {issue.code.value}{rule_label}: {issue.message}")
            if issue.suggestion:
                print(f"       → {issue.suggestion}")
        print()

    if report.passed:
        print("  ✅ Lint passed — no errors found.")
    else:
        error_count = len(report.errors)
        print(f"  ❌ Lint failed — {error_count} error(s) must be fixed.")

    print()
    return 0 if report.passed else 1


# ---------------------------------------------------------------------------
# Parser (updated)
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()

    handlers = {
        "init": cmd_init,
        "assess": cmd_assess,
        "report": cmd_report,
        "eu-ai-act": cmd_eu_ai_act,
        "lint": cmd_lint,
        "activate": cmd_activate,
        "status": cmd_status,
        "verify": cmd_verify,
    }

    handler = handlers.get(args.command)
    if handler is None:
        parser.print_help()
        sys.exit(1)

    sys.exit(handler(args))


if __name__ == "__main__":
    main()
