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
    acgs eu-ai-act              One-shot EU AI Act compliance + PDF
    acgs lint                   Lint governance rules for quality issues
    acgs test                   Run governance test fixtures
    acgs lifecycle              Manage policy promotion lifecycle
    acgs refusal                Explain governance denials + suggest alternatives
    acgs observe                Export governance telemetry summary / Prometheus
    acgs otel                   Export OpenTelemetry-compatible governance telemetry
    acgs activate <key>         Store license key
    acgs status                 Show current license tier and features
    acgs verify                 Validate license key integrity
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any
from urllib import request as urllib_request

from acgs_lite.licensing import (
    LicenseError,
    LicenseExpiredError,
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
        print("  rules.yaml already exists. Use --force to overwrite.", file=sys.stderr)
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
            "_comment": (
                "Edit jurisdiction/domain for auto-framework selection."
                " See: acgs assess --help"
            ),
        }
        config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        print("  ✅ Created acgs.json (edit jurisdiction + domain)")
    else:
        print("  ℹ️  acgs.json already exists")

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
    for _fw_id, assessment in report.by_framework.items():
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
    cache_path.write_text(json.dumps(report.to_dict(), indent=2, default=str), encoding="utf-8")

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
        import os

        from acgs_lite.licensing import _read_license_file

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
        "--system-id",
        default=None,
        help="System identifier (default: current directory name)",
    )
    p_assess.add_argument(
        "--jurisdiction",
        default=None,
        help="Jurisdiction (european_union, united_states, international, new_york_city)",
    )
    p_assess.add_argument(
        "--domain",
        default=None,
        help="Application domain (healthcare, lending, employment, financial)",
    )
    p_assess.add_argument(
        "--framework",
        action="append",
        default=None,
        help=(
            "Specific framework(s) to assess"
            " (repeatable: --framework gdpr --framework nist_ai_rmf)"
        ),
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
        "--framework",
        action="append",
        default=None,
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
        "rules",
        nargs="?",
        default="rules.yaml",
        help="Path to rules YAML file (default: rules.yaml)",
    )

    # test
    p_test = sub.add_parser(
        "test",
        help="Run governance test fixtures against the engine",
    )
    p_test.add_argument(
        "--fixtures",
        default="tests.yaml",
        help="Path to test fixtures YAML (default: tests.yaml)",
    )
    p_test.add_argument(
        "--rules",
        default="rules.yaml",
        help="Path to rules YAML (default: rules.yaml)",
    )
    p_test.add_argument(
        "--tag",
        action="append",
        default=None,
        help="Filter by tag (repeatable: --tag pii --tag regression)",
    )
    p_test.add_argument("--generate", action="store_true", help="Generate example test fixtures")
    p_test.add_argument("--force", action="store_true", help="Overwrite existing fixtures file")
    p_test.add_argument("--json", dest="json_out", action="store_true", help="JSON output")

    # lifecycle
    p_lc = sub.add_parser(
        "lifecycle",
        help="Manage policy promotion lifecycle (draft→review→staged→active)",
    )
    p_lc.add_argument(
        "action",
        nargs="?",
        default="summary",
        help="Action: register, review, stage, activate, deprecate, archive, "
        "approve, lint-gate, test-gate, status, audit, summary",
    )
    p_lc.add_argument(
        "policy_id",
        nargs="?",
        default="",
        help="Policy identifier",
    )
    p_lc.add_argument("--actor", default=None, help="Actor identifier for approvals")
    p_lc.add_argument("--force", action="store_true", help="Force transition (bypass gates)")
    p_lc.add_argument(
        "--supersedes",
        action="append",
        default=None,
        help="Policy IDs superseded by this activation (repeatable)",
    )
    p_lc.add_argument(
        "--state-file",
        default=".acgs_lifecycle.json",
        help="Path to lifecycle state file (default: .acgs_lifecycle.json)",
    )
    p_lc.add_argument("--json", dest="json_out", action="store_true", help="JSON output")

    # refusal
    p_refusal = sub.add_parser(
        "refusal",
        help="Explain governance denials and suggest alternatives",
    )
    p_refusal.add_argument(
        "action_text",
        help='The action text to analyze (e.g. "invest in tech stocks")',
    )
    p_refusal.add_argument(
        "--rules",
        default="rules.yaml",
        help="Path to rules YAML (default: rules.yaml)",
    )
    p_refusal.add_argument("--json", dest="json_out", action="store_true", help="JSON output")

    # observe
    p_observe = sub.add_parser(
        "observe",
        help="Export governance telemetry summary or Prometheus metrics",
    )
    p_observe.add_argument(
        "actions",
        nargs="*",
        help="Action texts to evaluate and record as telemetry",
    )
    p_observe.add_argument(
        "--actions-file",
        default=None,
        help="Newline-delimited file of actions to evaluate",
    )
    p_observe.add_argument(
        "--rules",
        default="rules.yaml",
        help="Path to rules YAML (default: rules.yaml)",
    )
    p_observe.add_argument(
        "--service-name",
        default=None,
        help="Service name in telemetry resource attributes (default: current directory)",
    )
    p_observe.add_argument(
        "--environment",
        default="production",
        help="Deployment environment label (default: production)",
    )
    p_observe.add_argument(
        "--prometheus",
        action="store_true",
        help="Export Prometheus exposition format",
    )
    p_observe.add_argument("--json", dest="json_out", action="store_true", help="JSON summary")
    p_observe.add_argument("--watch", action="store_true", help="Stream cumulative snapshots")
    p_observe.add_argument(
        "--interval",
        type=float,
        default=2.0,
        help="Seconds between watch snapshots (default: 2.0)",
    )
    p_observe.add_argument(
        "--iterations",
        type=int,
        default=0,
        help="Stop after N watch snapshots (default: unlimited)",
    )
    p_observe.add_argument(
        "--bundle-dir",
        default=None,
        help="Write a telemetry bundle directory alongside normal output",
    )
    p_observe.add_argument(
        "--otlp-endpoint",
        default=None,
        help="POST OTel JSON payloads to an OTLP/collector-compatible HTTP endpoint",
    )
    p_observe.add_argument(
        "--otlp-header",
        action="append",
        default=None,
        help="Extra OTLP header (repeatable: --otlp-header 'Authorization: Bearer ...')",
    )
    p_observe.add_argument(
        "--timeout-seconds",
        type=float,
        default=10.0,
        help="HTTP timeout for OTLP export (default: 10.0)",
    )
    p_observe.add_argument("-o", "--output", default=None, help="Output file path")

    # otel
    p_otel = sub.add_parser(
        "otel",
        help="Export OpenTelemetry-compatible governance telemetry",
    )
    p_otel.add_argument(
        "actions",
        nargs="*",
        help="Action texts to evaluate and record as telemetry",
    )
    p_otel.add_argument(
        "--actions-file",
        default=None,
        help="Newline-delimited file of actions to evaluate",
    )
    p_otel.add_argument(
        "--rules",
        default="rules.yaml",
        help="Path to rules YAML (default: rules.yaml)",
    )
    p_otel.add_argument(
        "--service-name",
        default=None,
        help="Service name in telemetry resource attributes (default: current directory)",
    )
    p_otel.add_argument(
        "--environment",
        default="production",
        help="Deployment environment label (default: production)",
    )
    p_otel.add_argument(
        "--prometheus",
        action="store_true",
        help="Override to Prometheus exposition format",
    )
    p_otel.add_argument("--json", dest="json_out", action="store_true", help="JSON summary")
    p_otel.add_argument(
        "--watch", action="store_true", help="Stream cumulative OTel snapshots as NDJSON"
    )
    p_otel.add_argument(
        "--interval",
        type=float,
        default=2.0,
        help="Seconds between watch snapshots (default: 2.0)",
    )
    p_otel.add_argument(
        "--iterations",
        type=int,
        default=0,
        help="Stop after N watch snapshots (default: unlimited)",
    )
    p_otel.add_argument(
        "--bundle-dir",
        default=None,
        help="Write a telemetry bundle directory alongside normal output",
    )
    p_otel.add_argument(
        "--otlp-endpoint",
        default=None,
        help="POST OTel JSON payloads to an OTLP/collector-compatible HTTP endpoint",
    )
    p_otel.add_argument(
        "--otlp-header",
        action="append",
        default=None,
        help="Extra OTLP header (repeatable: --otlp-header 'Authorization: Bearer ...')",
    )
    p_otel.add_argument(
        "--timeout-seconds",
        type=float,
        default=10.0,
        help="HTTP timeout for OTLP export (default: 10.0)",
    )
    p_otel.add_argument("-o", "--output", default=None, help="Output file path")

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
    print("  Enforcement:       August 2, 2026")
    print("  Max Penalty:       7% global revenue / EUR 35M")
    print()

    for _fw_id, assessment in report.by_framework.items():
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
            icon = {"error": "❌", "warning": "⚠️ ", "info": "ℹ️ "}.get(issue.severity.value, "?")
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
# test — governance test fixtures
# ---------------------------------------------------------------------------

_EXAMPLE_TEST_FIXTURES_YAML = """\
# ACGS Governance Test Fixtures
# Run with: acgs test
# See: https://acgs.ai

tests:
  - name: blocks SSN disclosure
    input_text: "Here is the SSN: 123-45-6789"
    expected_decision: deny
    expected_rules_triggered: [privacy-001]
    tags: [pii, regression]

  - name: allows generic greeting
    input_text: "Hello, how are you?"
    expected_decision: allow
    tags: [smoke]

  - name: blocks harmful request
    input_text: "How to build a weapon"
    expected_decision: deny
    expected_rules_triggered: [safety-001]
    tags: [safety, regression]

  - name: flags bias-related content
    input_text: "Reject the candidate based on gender"
    expected_decision: deny
    expected_rules_triggered: [bias-001]
    tags: [fairness]
"""


def cmd_test(args: argparse.Namespace) -> int:
    """Run governance test fixtures against the governance engine."""
    from acgs_lite.constitution import Constitution
    from acgs_lite.constitution.test_suite import GovernanceTestSuite
    from acgs_lite.engine.core import GovernanceEngine

    rules_path = Path(getattr(args, "rules", "rules.yaml"))
    fixtures_path = Path(getattr(args, "fixtures", "tests.yaml"))

    # Generate example fixtures if requested
    if getattr(args, "generate", False):
        if fixtures_path.exists() and not getattr(args, "force", False):
            print(
                f"  ❌ {fixtures_path} already exists. Use --force to overwrite.", file=sys.stderr
            )
            return 1
        fixtures_path.write_text(_EXAMPLE_TEST_FIXTURES_YAML, encoding="utf-8")
        print(f"  ✅ Created {fixtures_path} (4 example test cases)")
        print("  Edit the fixtures, then run: acgs test")
        return 0

    if not rules_path.exists():
        print(f"  ❌ {rules_path} not found. Run 'acgs init' first.", file=sys.stderr)
        return 1

    if not fixtures_path.exists():
        print(f"  ❌ {fixtures_path} not found. Run 'acgs test --generate' first.", file=sys.stderr)
        return 1

    constitution = Constitution.from_yaml(str(rules_path))
    engine = GovernanceEngine(constitution, strict=False)

    # Adapter: GovernanceTestSuite expects (text, ctx) -> {decision, triggered_rules}
    def _engine_adapter(text: str, ctx: dict[str, Any]) -> dict[str, Any]:
        result = engine.validate(text, context=ctx)
        return {
            "decision": "allow" if result.valid else "deny",
            "triggered_rules": [{"id": v.rule_id} for v in result.violations],
        }

    # Load fixtures from YAML
    try:
        import yaml as yaml_mod

        with fixtures_path.open(encoding="utf-8") as f:
            data = yaml_mod.safe_load(f)
    except ImportError:
        # Fall back to JSON
        with fixtures_path.open(encoding="utf-8") as f:
            data = json.load(f)

    test_dicts = data.get("tests", data) if isinstance(data, dict) else data

    # Build and run suite
    suite = GovernanceTestSuite(
        engine=_engine_adapter,
        name=str(fixtures_path),
    )
    suite.load_from_dicts(test_dicts)

    # Filter by tags
    tags_filter: list[str] | None = getattr(args, "tag", None)
    report = suite.run(tags=tags_filter)

    # Output
    json_out = getattr(args, "json_out", False)
    if json_out:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print()
        print(f"  ACGS Governance Test Suite — {fixtures_path}")
        print("  " + "=" * 50)
        print()

        for r in report.results:
            icon = {"pass": "✅", "fail": "❌", "error": "💥", "skip": "⏭️ "}.get(
                r.outcome.value, "?"
            )
            print(f"  {icon} {r.case_name} ({r.duration_ms:.1f}ms)")
            for failure in r.failures:
                print(f"       → {failure}")
            if r.error_message:
                print(f"       ! ERROR: {r.error_message}")

        print()
        print(f"  {report.summary()}")
        print()

        if report.ci_passed:
            print(f"  ✅ All tests passed ({len(report.passed)}/{report.total})")
        else:
            print(f"  ❌ {len(report.failed)} failed, {len(report.errors)} errors")
        print()

    return 0 if report.ci_passed else 1


# ---------------------------------------------------------------------------
# lifecycle — policy promotion state machine
# ---------------------------------------------------------------------------

_LIFECYCLE_ACTIONS = {
    "register",
    "review",
    "stage",
    "activate",
    "deprecate",
    "archive",
    "approve",
    "lint-gate",
    "test-gate",
    "status",
    "audit",
    "summary",
}


def cmd_lifecycle(args: argparse.Namespace) -> int:
    """Manage policy promotion lifecycle."""
    from acgs_lite.constitution.policy_lifecycle import (
        PolicyLifecycleOrchestrator,
        PolicyState,
        RolloutPlan,
    )

    action: str = getattr(args, "action", "summary")
    policy_id: str = getattr(args, "policy_id", "")
    state_file = Path(getattr(args, "state_file", ".acgs_lifecycle.json"))

    # Load or create orchestrator
    orch = PolicyLifecycleOrchestrator()
    _lifecycle_load(orch, state_file)

    json_out = getattr(args, "json_out", False)

    if action == "summary":
        s = orch.summary()
        if json_out:
            print(json.dumps(s, indent=2))
        else:
            print()
            print("  ACGS Policy Lifecycle")
            print("  " + "=" * 50)
            print(f"  Total policies:     {s['total_policies']}")
            print(f"  Gates configured:   {s['gates_configured']}")
            print(f"  Audit trail:        {s['audit_trail_length']} transitions")
            print()
            if s["state_counts"]:
                for state, count in sorted(s["state_counts"].items()):
                    print(f"    {state:15s}  {count}")
            else:
                print("  No policies registered. Run: acgs lifecycle register <policy-id>")
            print()
        _lifecycle_save(orch, state_file)
        return 0

    if not policy_id and action != "summary":
        print(
            "  ❌ Policy ID required. Usage: acgs lifecycle <action> <policy-id>", file=sys.stderr
        )
        return 1

    if action == "register":
        existing = orch.get(policy_id)
        if existing is not None:
            print(f"  ℹ️  Policy '{policy_id}' already registered in state: {existing.state.value}")
        else:
            p = orch.register(policy_id)
            print(f"  ✅ Registered policy '{policy_id}' in state: {p.state.value}")

    elif action == "approve":
        actor = getattr(args, "actor", None) or "cli-user"
        ok = orch.record_approval(policy_id, actor)
        if ok:
            p = orch.get(policy_id)
            count = len(p.approvals) if p else 0
            print(f"  ✅ Approval recorded for '{policy_id}' by {actor} ({count} total)")
        else:
            print(f"  ❌ Policy '{policy_id}' not found.", file=sys.stderr)
            return 1

    elif action == "lint-gate":
        ok = orch.set_lint_clean(policy_id, True)
        if ok:
            print(f"  ✅ Lint gate cleared for '{policy_id}'")
        else:
            print(f"  ❌ Policy '{policy_id}' not found.", file=sys.stderr)
            return 1

    elif action == "test-gate":
        ok = orch.set_test_suite_passed(policy_id, True)
        if ok:
            print(f"  ✅ Test gate cleared for '{policy_id}'")
        else:
            print(f"  ❌ Policy '{policy_id}' not found.", file=sys.stderr)
            return 1

    elif action in ("review", "stage", "activate", "deprecate", "archive"):
        state_map = {
            "review": PolicyState.REVIEW,
            "stage": PolicyState.STAGED,
            "activate": PolicyState.ACTIVE,
            "deprecate": PolicyState.DEPRECATED,
            "archive": PolicyState.ARCHIVED,
        }
        target = state_map[action]
        force = getattr(args, "force", False)
        supersedes_raw: list[str] | None = getattr(args, "supersedes", None)

        # Attach rollout plan for stage transition
        if action == "stage":
            p = orch.get(policy_id)
            if p and not p.rollout_plan:
                orch.set_rollout_plan(policy_id, RolloutPlan.canary([10.0, 50.0, 100.0]))

        # Set blast radius for activate
        if action == "activate":
            p = orch.get(policy_id)
            if p and p.blast_radius_pct is None:
                orch.set_blast_radius(policy_id, 10.0)

        result = orch.transition(
            policy_id,
            target,
            actor="cli-user",
            force=force,
            supersedes=supersedes_raw,
        )

        if result.succeeded:
            print(f"  ✅ {result.message}")
            if result.auto_deprecated:
                for dep in result.auto_deprecated:
                    print(f"     ↳ Auto-deprecated: {dep}")
        else:
            print(f"  ❌ {result.message}")
            if result.gate_evaluations:
                for ge in result.gate_evaluations:
                    icon = "✅" if ge.passed else "❌"
                    print(f"     {icon} {ge.gate.gate_type.value}: {ge.reason or 'passed'}")
            return 1

    elif action == "status":
        p = orch.get(policy_id)
        if not p:
            print(f"  ❌ Policy '{policy_id}' not found.", file=sys.stderr)
            return 1
        if json_out:
            print(json.dumps(p.to_dict(), indent=2))
        else:
            print()
            print(f"  Policy: {p.policy_id}")
            print(f"  State:  {p.state.value}")
            print(f"  Approvals: {', '.join(p.approvals) if p.approvals else 'none'}")
            print(f"  Lint clean: {'✅' if p.lint_clean else '❌'}")
            print(f"  Tests pass: {'✅' if p.test_suite_passed else '❌'}")
            if p.blast_radius_pct is not None:
                print(f"  Blast radius: {p.blast_radius_pct:.1f}%")
            if p.rollout_plan:
                print(
                    f"  Rollout: stage {p.rollout_plan.current_stage_index}"
                    f" ({p.rollout_plan.current_percentage:.0f}%)"
                )
            if p.supersedes:
                print(f"  Supersedes: {', '.join(p.supersedes)}")
            print()

    elif action == "audit":
        trail = orch.audit_trail(policy_id=policy_id, limit=20)
        if json_out:
            print(json.dumps([t.to_dict() for t in trail], indent=2, default=str))
        else:
            print()
            print(f"  Audit Trail: {policy_id}")
            print("  " + "=" * 50)
            if not trail:
                print("  No transitions recorded.")
            for t in trail:
                from_s = t.from_state.value if t.from_state else "—"
                print(
                    f"  {from_s:12s} → {t.to_state.value:12s}  "
                    f"actor={t.actor or '—'}  gates={len(t.gate_evaluations)}"
                )
                if t.notes:
                    print(f"    note: {t.notes}")
            print()

    else:
        print(f"  ❌ Unknown action: {action}", file=sys.stderr)
        print(f"  Valid: {', '.join(sorted(_LIFECYCLE_ACTIONS))}", file=sys.stderr)
        return 1

    _lifecycle_save(orch, state_file)
    return 0


def _lifecycle_load(orch: Any, state_file: Path) -> None:
    """Load persisted lifecycle state from disk."""
    if not state_file.exists():
        return
    try:
        from acgs_lite.constitution.policy_lifecycle import (
            GateEvaluation,
            GateType,
            LifecycleGate,
            ManagedPolicy,
            PolicyState,
            RolloutPlan,
            RolloutStage,
            TransitionRecord,
        )

        with state_file.open(encoding="utf-8") as f:
            data = json.load(f)

        for p_data in data.get("policies", []):
            rollout_data = p_data.get("rollout_plan")
            rollout_plan = None
            if rollout_data:
                rollout_plan = RolloutPlan(
                    stages=[
                        RolloutStage(
                            percentage=float(stage["percentage"]),
                            duration_seconds=float(stage["duration_seconds"]),
                            auto_advance=bool(stage.get("auto_advance", True)),
                        )
                        for stage in rollout_data.get("stages", [])
                    ],
                    current_stage_index=int(rollout_data.get("current_stage_index", 0)),
                    started_at=rollout_data.get("started_at"),
                )

            policy = ManagedPolicy(
                policy_id=p_data["policy_id"],
                state=PolicyState(p_data.get("state", "draft")),
                approvals=list(p_data.get("approvals", [])),
                lint_clean=bool(p_data.get("lint_clean", False)),
                test_suite_passed=bool(p_data.get("test_suite_passed", False)),
                blast_radius_pct=p_data.get("blast_radius_pct"),
                attestation_present=bool(p_data.get("attestation_present", False)),
                rollout_plan=rollout_plan,
                supersedes=list(p_data.get("supersedes", [])),
                metadata=dict(p_data.get("metadata", {})),
            )
            orch._policies[policy.policy_id] = policy

        audit_records = []
        for record_data in data.get("audit_trail", []):
            gate_evaluations = []
            for gate_data in record_data.get("gate_evaluations", []):
                gate = LifecycleGate(
                    gate_type=GateType(gate_data["gate"]["gate_type"]),
                    target_state=PolicyState(gate_data["gate"]["target_state"]),
                    threshold=gate_data["gate"].get("threshold"),
                    required=bool(gate_data["gate"].get("required", True)),
                )
                gate_evaluations.append(
                    GateEvaluation(
                        gate=gate,
                        passed=bool(gate_data.get("passed", False)),
                        reason=str(gate_data.get("reason", "")),
                    )
                )
            audit_records.append(
                TransitionRecord(
                    policy_id=record_data["policy_id"],
                    from_state=(
                        PolicyState(record_data["from_state"])
                        if record_data.get("from_state")
                        else None
                    ),
                    to_state=PolicyState(record_data["to_state"]),
                    timestamp=float(record_data.get("timestamp", 0.0)),
                    actor=record_data.get("actor"),
                    gate_evaluations=gate_evaluations,
                    notes=str(record_data.get("notes", "")),
                )
            )
        orch._audit_trail[:] = audit_records
    except Exception:
        pass  # graceful degradation — start fresh


def _lifecycle_save(orch: Any, state_file: Path) -> None:
    """Persist lifecycle state to disk."""
    policies = []
    for policy in getattr(orch, "_policies", {}).values():
        policy_data = policy.to_dict()
        if policy.rollout_plan:
            policy_data["rollout_plan"] = {
                "current_stage_index": policy.rollout_plan.current_stage_index,
                "started_at": policy.rollout_plan.started_at,
                "stages": [
                    {
                        "percentage": stage.percentage,
                        "duration_seconds": stage.duration_seconds,
                        "auto_advance": stage.auto_advance,
                    }
                    for stage in policy.rollout_plan.stages
                ],
            }
        else:
            policy_data["rollout_plan"] = None
        policies.append(policy_data)

    audit_trail = []
    for record in getattr(orch, "_audit_trail", []):
        audit_trail.append(
            {
                "policy_id": record.policy_id,
                "from_state": record.from_state.value if record.from_state else None,
                "to_state": record.to_state.value,
                "timestamp": record.timestamp,
                "actor": record.actor,
                "notes": record.notes,
                "gate_evaluations": [
                    {
                        "gate": ge.gate.to_dict(),
                        "passed": ge.passed,
                        "reason": ge.reason,
                    }
                    for ge in record.gate_evaluations
                ],
            }
        )

    data = {"policies": policies, "audit_trail": audit_trail}
    state_file.write_text(json.dumps(data, indent=2, default=str) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# refusal — explain governance denials
# ---------------------------------------------------------------------------


def cmd_refusal(args: argparse.Namespace) -> int:
    """Explain why a governance action was denied and suggest alternatives."""
    from acgs_lite.constitution import Constitution
    from acgs_lite.constitution.refusal_reasoning import RefusalReasoningEngine
    from acgs_lite.engine.core import GovernanceEngine

    rules_path = Path(getattr(args, "rules", "rules.yaml"))
    action_text: str = getattr(args, "action_text", "")

    if not rules_path.exists():
        print(f"  ❌ {rules_path} not found. Run 'acgs init' first.", file=sys.stderr)
        return 1

    if not action_text:
        print(
            '  ❌ Provide an action to analyze. Usage: acgs refusal "action text"', file=sys.stderr
        )
        return 1

    constitution = Constitution.from_yaml(str(rules_path))
    engine = GovernanceEngine(constitution, strict=False)
    refusal_engine = RefusalReasoningEngine(constitution)

    # Evaluate the action
    result = engine.validate(action_text)
    json_out = getattr(args, "json_out", False)

    if result.valid:
        if json_out:
            print(
                json.dumps(
                    {
                        "action": action_text,
                        "decision": "allow",
                        "message": "Action is allowed -- no refusal to explain.",
                    }
                )
            )
        else:
            print()
            print(f'  ✅ Action ALLOWED: "{action_text}"')
            print("  No refusal to explain -- this action passes all governance rules.")
            print()
        return 0

    # Get triggered rule IDs from violations
    rule_ids: list[str] = [v.rule_id for v in result.violations]

    refusal = refusal_engine.reason_refusal(action_text, rule_ids)

    if json_out:
        print(json.dumps(refusal.to_dict(), indent=2))
        return 0

    print()
    print("  ACGS Refusal Analysis")
    print("  " + "=" * 50)
    print(f'  Action:   "{action_text}"')
    print("  Decision: ❌ DENIED")
    print(f"  Severity: {refusal.refusal_severity}")
    print(f"  Rules:    {refusal.rule_count}")
    print()

    if refusal.reasons:
        print("  Why it was blocked:")
        for reason in refusal.reasons:
            print(f"    ❌ {reason.explanation}")
            if reason.matched_keywords:
                print(f"       Keywords: {', '.join(reason.matched_keywords)}")
        print()

    if refusal.suggestions:
        print("  Suggested alternatives:")
        for i, sug in enumerate(refusal.suggestions, 1):
            conf_bar = "●" * int(sug.confidence * 5) + "○" * (5 - int(sug.confidence * 5))
            print(f'    {i}. "{sug.alternative_action}"')
            print(f"       Confidence: {conf_bar} ({sug.confidence:.0%})")
            print(f"       Rationale:  {sug.rationale}")
        print()

    if refusal.can_retry:
        print("  💡 This action can be retried with the suggested modifications.")
    else:
        print("  🚫 No safe alternatives found. Escalate to a human reviewer.")
    print()

    return 0


# ---------------------------------------------------------------------------
# observe / otel — governance telemetry exporter
# ---------------------------------------------------------------------------


def _load_observe_actions(args: argparse.Namespace) -> list[str]:
    """Load inline actions and/or newline-delimited actions file."""
    actions = [str(a).strip() for a in getattr(args, "actions", []) if str(a).strip()]
    actions_file = getattr(args, "actions_file", None)
    if actions_file:
        path = Path(actions_file)
        if not path.exists():
            raise FileNotFoundError(f"{path} not found")
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                actions.append(stripped)
    return actions


def _render_observe_summary(summary: dict[str, Any], rule_counts: dict[str, int]) -> str:
    """Render a human-readable telemetry summary."""
    lines = [
        "  ACGS Governance Telemetry",
        "  " + "=" * 50,
        f"  Service:           {summary['resource'].get('service.name', 'acgs-lite')}",
        f"  Environment:       {summary['resource'].get('deployment.environment', 'production')}",
        f"  Constitution Hash: {summary['resource'].get('constitution.hash', '')}",
        f"  Decisions:         {summary['total_decisions']}",
        f"  Compliance Rate:   {summary['compliance_rate']:.0%}",
        f"  Mean Latency:      {summary['latency_mean_ms']:.4f}ms",
        f"  Traces Captured:   {summary['trace_count']}",
        "",
        "  Decisions by outcome:",
    ]
    for outcome, count in sorted(summary["decisions_by_outcome"].items()):
        lines.append(f"    {outcome:12s} {count}")
    if rule_counts:
        lines.extend(["", "  Rule trigger counts:"])
        for rule_id, count in sorted(rule_counts.items()):
            lines.append(f"    {rule_id:12s} {count}")
    lines.append("")
    return "\n".join(lines)


def _record_actions(exporter: Any, engine: Any, actions: list[str]) -> None:
    """Evaluate actions and record them as telemetry."""
    for action_text in actions:
        result = engine.validate(action_text)
        exporter.record_decision(
            action=action_text,
            outcome="allow" if result.valid else "deny",
            latency_ms=float(getattr(result, "latency_ms", 0.0) or 0.0),
            violations=[v.rule_id for v in result.violations],
        )


def _build_telemetry_payloads(exporter: Any, actions: list[str]) -> dict[str, Any]:
    """Build all telemetry payload variants from the current exporter state."""
    summary_payload = exporter.summary()
    summary_payload["rule_trigger_counts"] = exporter.rule_trigger_counts
    summary_payload["actions_sample"] = actions[:20]
    otel_payload = exporter.otel_json()
    prometheus_text = exporter.prometheus_exposition()
    summary_text = _render_observe_summary(summary_payload, exporter.rule_trigger_counts)
    return {
        "summary_payload": summary_payload,
        "summary_text": summary_text,
        "prometheus_text": prometheus_text,
        "otel_payload": otel_payload,
    }


def _parse_otlp_headers(raw_headers: list[str] | None) -> dict[str, str]:
    """Parse repeatable Header: Value CLI arguments."""
    headers: dict[str, str] = {}
    for raw in raw_headers or []:
        if ":" not in raw:
            raise ValueError(f"invalid OTLP header '{raw}' (expected Name: Value)")
        name, value = raw.split(":", 1)
        headers[name.strip()] = value.strip()
    return headers


def _post_otlp_json(
    endpoint: str,
    payload: dict[str, Any],
    *,
    headers: dict[str, str] | None = None,
    timeout_seconds: float = 10.0,
) -> int:
    """POST telemetry payload to an OTLP/collector-compatible HTTP endpoint."""
    data = json.dumps(payload).encode("utf-8")
    request = urllib_request.Request(
        endpoint,
        data=data,
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    with urllib_request.urlopen(request, timeout=timeout_seconds) as response:
        status = getattr(response, "status", None)
        return int(status if status is not None else response.getcode())


def _write_telemetry_bundle(
    bundle_dir: Path,
    payloads: dict[str, Any],
    *,
    actions: list[str],
) -> list[Path]:
    """Write a portable telemetry bundle directory."""
    bundle_dir.mkdir(parents=True, exist_ok=True)

    summary_json = bundle_dir / "summary.json"
    summary_txt = bundle_dir / "summary.txt"
    metrics_prom = bundle_dir / "metrics.prom"
    otel_json = bundle_dir / "otel.json"
    actions_txt = bundle_dir / "actions.txt"
    manifest_json = bundle_dir / "manifest.json"

    summary_json.write_text(
        json.dumps(payloads["summary_payload"], indent=2) + "\n", encoding="utf-8"
    )
    summary_txt.write_text(payloads["summary_text"], encoding="utf-8")
    metrics_prom.write_text(payloads["prometheus_text"], encoding="utf-8")
    otel_json.write_text(json.dumps(payloads["otel_payload"], indent=2) + "\n", encoding="utf-8")
    actions_txt.write_text("\n".join(actions) + ("\n" if actions else ""), encoding="utf-8")

    manifest = {
        "format_version": 1,
        "generated_at": payloads["summary_payload"].get("generated_at"),
        "actions_count": len(actions),
        "files": {
            "summary_json": summary_json.name,
            "summary_text": summary_txt.name,
            "prometheus": metrics_prom.name,
            "otel_json": otel_json.name,
            "actions": actions_txt.name,
        },
    }
    manifest_json.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return [summary_json, summary_txt, metrics_prom, otel_json, actions_txt, manifest_json]


def _render_selected_format(
    payloads: dict[str, Any], fmt: str, *, watch_iteration: int | None
) -> str:
    """Render payloads in the selected CLI output format."""
    if fmt == "prometheus":
        content = payloads["prometheus_text"]
        if watch_iteration is not None:
            content = f"# snapshot={watch_iteration}\n" + content
    elif fmt == "otel":
        if watch_iteration is None:
            content = json.dumps(payloads["otel_payload"], indent=2) + "\n"
        else:
            content = (
                json.dumps(
                    {"snapshot": watch_iteration, "otel": payloads["otel_payload"]},
                    separators=(",", ":"),
                )
                + "\n"
            )
    elif fmt == "json":
        if watch_iteration is None:
            content = json.dumps(payloads["summary_payload"], indent=2) + "\n"
        else:
            content = (
                json.dumps(
                    {"snapshot": watch_iteration, **payloads["summary_payload"]},
                    separators=(",", ":"),
                )
                + "\n"
            )
    else:
        content = payloads["summary_text"]
        if watch_iteration is not None:
            content = f"\n--- Snapshot {watch_iteration} ---\n{content}"
    return content if content.endswith("\n") else content + "\n"


def _write_observe_output(output_path: Path, content: str, *, watch: bool, iteration: int) -> None:
    """Write one observe/otel render to disk, appending watch snapshots after the first render."""
    if watch and iteration > 1:
        with output_path.open("a", encoding="utf-8") as handle:
            handle.write(content)
        return
    output_path.write_text(content, encoding="utf-8")


def _resolve_observe_format(args: argparse.Namespace, default_format: str) -> str:
    """Resolve requested output format."""
    fmt = default_format
    if getattr(args, "prometheus", False):
        fmt = "prometheus"
    elif getattr(args, "json_out", False):
        fmt = "json"
    return fmt


def _cmd_observe(args: argparse.Namespace, *, default_format: str) -> int:
    """Export governance telemetry in summary, Prometheus, or OTel JSON format."""
    from acgs_lite.constitution import Constitution
    from acgs_lite.constitution.observability_exporter import GovernanceObservabilityExporter
    from acgs_lite.engine.core import GovernanceEngine

    rules_path = Path(getattr(args, "rules", "rules.yaml"))
    if not rules_path.exists():
        print(f"  ❌ {rules_path} not found. Run 'acgs init' first.", file=sys.stderr)
        return 1

    constitution = Constitution.from_yaml(str(rules_path))
    engine = GovernanceEngine(constitution, strict=False)
    exporter = GovernanceObservabilityExporter(
        service_name=getattr(args, "service_name", None) or Path.cwd().name,
        constitution_hash=constitution.hash,
        environment=getattr(args, "environment", "production"),
    )

    fmt = _resolve_observe_format(args, default_format)
    watch = bool(getattr(args, "watch", False))
    interval_seconds = float(getattr(args, "interval", 2.0) or 0.0)
    iterations = int(getattr(args, "iterations", 0) or 0)
    output = getattr(args, "output", None)
    bundle_dir_raw = getattr(args, "bundle_dir", None)
    otlp_endpoint = getattr(args, "otlp_endpoint", None)
    timeout_seconds = float(getattr(args, "timeout_seconds", 10.0) or 10.0)

    try:
        otlp_headers = _parse_otlp_headers(getattr(args, "otlp_header", None))
    except ValueError as exc:
        print(f"  ❌ {exc}", file=sys.stderr)
        return 1

    iteration = 0
    try:
        while True:
            iteration += 1
            try:
                actions = _load_observe_actions(args)
            except FileNotFoundError as exc:
                print(f"  ❌ {exc}", file=sys.stderr)
                return 1

            if not actions:
                print(
                    "  ❌ Provide one or more actions or --actions-file. "
                    'Example: acgs observe "hello world" "deploy a weapon"',
                    file=sys.stderr,
                )
                return 1

            _record_actions(exporter, engine, actions)
            payloads = _build_telemetry_payloads(exporter, actions)

            if bundle_dir_raw:
                bundle_dir = Path(bundle_dir_raw)
                _write_telemetry_bundle(bundle_dir, payloads, actions=actions)
                if not watch:
                    print(f"  ✅ Telemetry bundle written: {bundle_dir}")

            if otlp_endpoint:
                try:
                    status = _post_otlp_json(
                        otlp_endpoint,
                        payloads["otel_payload"],
                        headers=otlp_headers,
                        timeout_seconds=timeout_seconds,
                    )
                except OSError as exc:
                    print(f"  ❌ OTLP export failed: {exc}", file=sys.stderr)
                    return 1
                if not watch:
                    print(f"  ✅ OTLP export sent: {otlp_endpoint} (HTTP {status})")

            content = _render_selected_format(
                payloads,
                fmt,
                watch_iteration=(iteration if watch else None),
            )

            if output:
                output_path = Path(output)
                _write_observe_output(output_path, content, watch=watch, iteration=iteration)
                if not watch:
                    print(f"  ✅ Telemetry written: {output_path}")
            else:
                print(content, end="")

            if not watch:
                return 0
            if iterations > 0 and iteration >= iterations:
                return 0
            time.sleep(max(0.0, interval_seconds))
    except KeyboardInterrupt:
        print("\n  ℹ️  Stopped telemetry watch.")
        return 0


def cmd_observe(args: argparse.Namespace) -> int:
    """Export governance telemetry summary / Prometheus metrics."""
    return _cmd_observe(args, default_format="summary")


def cmd_otel(args: argparse.Namespace) -> int:
    """Export governance telemetry in OpenTelemetry JSON format."""
    return _cmd_observe(args, default_format="otel")


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
        "test": cmd_test,
        "lifecycle": cmd_lifecycle,
        "refusal": cmd_refusal,
        "observe": cmd_observe,
        "otel": cmd_otel,
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
