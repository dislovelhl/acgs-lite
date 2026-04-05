"""ACGS-Auth0: Constitutional Token Governance for AI Agents — Demo

Demonstrates a multi-agent LangGraph system where MACI constitutional rules
determine which agents can obtain which Token Vault credentials.

Agents:
  planner   (EXECUTIVE)  — proposes tasks, reads GitHub + Google Calendar
  executor  (IMPLEMENTER) — executes approved tasks, writes GitHub + Calendar
  auditor   (MONITOR)    — read-only audit trail access

Constitutional rules (constitution.yaml):
  EXECUTIVE  → github:["repo:read"]                   (no step-up)
  IMPLEMENTER → github:["repo:write"]                  (CIBA step-up required)
  JUDICIAL   → no external API access (MACI Golden Rule)

Run:
  python main.py                    # interactive demo
  python main.py --demo deny        # show scope denial
  python main.py --demo step-up     # show CIBA step-up flow
  python main.py --demo audit       # show constitutional audit trail

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

# ── ensure packages are importable when run from examples/ ─────────────────
_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_ROOT / "packages"))

from acgs_auth0 import MACIScopePolicy  # noqa: E402
from acgs_auth0.audit import TokenAuditLog  # noqa: E402
from acgs_auth0.exceptions import (  # noqa: E402
    ConstitutionalScopeViolation,
    MACIRoleNotPermittedError,
    StepUpAuthRequiredError,
)
from acgs_auth0.token_vault import (  # noqa: E402
    ConstitutionalTokenVault,
    TokenVaultRequest,
)

CONSTITUTION_PATH = Path(__file__).parent / "constitutions" / "default.yaml"
AUDIT_LOG_PATH = Path(__file__).parent / "audit.jsonl"


# ── Shared state ─────────────────────────────────────────────────────────────

audit_log = TokenAuditLog(file_path=AUDIT_LOG_PATH, emit_structlog=False)
policy = MACIScopePolicy.from_yaml(CONSTITUTION_PATH)
vault = ConstitutionalTokenVault(
    policy=policy,
    audit_log=audit_log,
    auth0_domain=os.environ.get("AUTH0_DOMAIN", ""),
    auth0_client_id=os.environ.get("AUTH0_CLIENT_ID", ""),
    auth0_client_secret=os.environ.get("AUTH0_CLIENT_SECRET", ""),
)


# ── Demo scenarios ───────────────────────────────────────────────────────────


async def demo_permitted_read() -> None:
    """EXECUTIVE agent successfully reads GitHub via Token Vault."""
    print("\n" + "═" * 60)
    print("🔵  DEMO: Constitutional token grant (read-only)")
    print("═" * 60)
    print("  Agent:      planner (role=EXECUTIVE)")
    print("  Connection: github")
    print("  Scopes:     [repo:read, read:user]")

    # Pre-flight validation (no network call)
    result = vault.validate(
        TokenVaultRequest(
            agent_id="planner",
            role="EXECUTIVE",
            connection="github",
            scopes=["repo:read", "read:user"],
            refresh_token="rt_placeholder",
        )
    )

    if result.permitted:
        print("\n  ✅ Constitutional gate: PASSED")
        print(f"     Permitted scopes: {result.permitted_scopes}")
        print(f"     Step-up required: {result.step_up_required}")
        print("\n  ℹ️  (Token Vault exchange would proceed here — set AUTH0_* env vars to run live)")
        audit_log.record_granted(
            agent_id="planner",
            role="EXECUTIVE",
            connection="github",
            scopes=["repo:read", "read:user"],
            user_id="auth0|demo-user",
            tool_name="list_open_issues",
        )
        print("  📋 Audit entry recorded.")
    else:
        print(f"\n  ❌ Constitutional gate: FAILED — {result.error}")


async def demo_scope_denial() -> None:
    """EXECUTIVE agent tries to write GitHub — denied by constitution."""
    print("\n" + "═" * 60)
    print("🔴  DEMO: Constitutional scope denial")
    print("═" * 60)
    print("  Agent:      planner (role=EXECUTIVE)")
    print("  Connection: github")
    print("  Scopes:     [repo:write]  ← not permitted for EXECUTIVE")

    result = vault.validate(
        TokenVaultRequest(
            agent_id="planner",
            role="EXECUTIVE",
            connection="github",
            scopes=["repo:write"],
            refresh_token="rt_placeholder",
        )
    )

    if not result.permitted:
        print("\n  🚫 Constitutional gate: DENIED")
        print(f"     Error: {result.error}")
        print(f"     Denied scopes: {result.denied_scopes}")
        print(f"     Permitted scopes for EXECUTIVE/github: {result.permitted_scopes}")
        audit_log.record_denied(
            agent_id="planner",
            role="EXECUTIVE",
            connection="github",
            scopes=["repo:write"],
            reason="scope_violation",
            error_message=str(result.error),
        )
        print("  📋 Denial recorded in constitutional audit log.")


async def demo_role_not_permitted() -> None:
    """JUDICIAL agent tries to access GitHub — role has no access."""
    print("\n" + "═" * 60)
    print("🔴  DEMO: MACI role not permitted (JUDICIAL → GitHub)")
    print("═" * 60)
    print("  Agent:      validator (role=JUDICIAL)")
    print("  Connection: github")
    print("  Note: JUDICIAL validates proposals but NEVER accesses external APIs")
    print("        (MACI Golden Rule: agents cannot validate their own output)")

    result = vault.validate(
        TokenVaultRequest(
            agent_id="validator",
            role="JUDICIAL",
            connection="github",
            scopes=["read:user"],
            refresh_token="rt_placeholder",
        )
    )

    if not result.permitted:
        print("\n  🚫 Constitutional gate: DENIED")
        print(f"     Error: {result.error}")
        print("  ✅ MACI separation enforced correctly.")


async def demo_step_up() -> None:
    """IMPLEMENTER agent requests write — triggers CIBA step-up."""
    print("\n" + "═" * 60)
    print("🟡  DEMO: CIBA step-up authentication")
    print("═" * 60)
    print("  Agent:      executor (role=IMPLEMENTER)")
    print("  Connection: github")
    print("  Scopes:     [repo:read, repo:write]  ← write requires step-up")

    result = vault.validate(
        TokenVaultRequest(
            agent_id="executor",
            role="IMPLEMENTER",
            connection="github",
            scopes=["repo:read", "repo:write"],
            refresh_token="rt_placeholder",
        )
    )

    if result.permitted:
        print("\n  ✅ Constitutional gate: PASSED")
        print(f"     Permitted scopes: {result.permitted_scopes}")
        if result.step_up_required:
            print(f"  ⚠️  Step-up required for: {result.step_up_required}")
            binding_message = (
                "executor (IMPLEMENTER) requests GitHub write access "
                "to create a pull request. Approve or deny?"
            )
            print(f"\n  📱 CIBA binding message sent to user:")
            print(f'     "{binding_message}"')
            print("\n  ⏳ Awaiting user approval on Auth0 Guardian mobile app...")
            print("     (In production: Auth0 sends push notification to user)")
            print("\n  ✅ [SIMULATED] User approved via Guardian push notification")

            audit_log.record_step_up(
                agent_id="executor",
                role="IMPLEMENTER",
                connection="github",
                scopes=["repo:write"],
                binding_message=binding_message,
                approved=True,
                user_id="auth0|demo-user",
                tool_name="create_pull_request",
            )
            print("  📋 Step-up approval recorded in constitutional audit log.")


async def demo_audit_trail() -> None:
    """Show the constitutional audit trail after all demos."""
    print("\n" + "═" * 60)
    print("📋  DEMO: Constitutional audit trail")
    print("═" * 60)
    print(f"  Total entries in session: {len(audit_log)}")
    print()
    for entry in audit_log.get_entries():
        icon = {
            "granted": "✅",
            "denied_scope_violation": "🚫",
            "denied_role_not_permitted": "🚫",
            "step_up_initiated": "⏳",
            "step_up_approved": "✅",
            "step_up_denied": "❌",
            "error": "❗",
        }.get(entry.outcome.value, "?")
        print(
            f"  {icon} [{entry.outcome.value:30s}] "
            f"agent={entry.agent_id:12s} role={entry.role:15s} "
            f"conn={entry.connection}"
        )
        if entry.step_up_binding_message:
            print(f"     ciba: {entry.step_up_binding_message[:60]}...")

    if AUDIT_LOG_PATH.exists():
        print(f"\n  Full JSONL log: {AUDIT_LOG_PATH}")


async def demo_policy_overview() -> None:
    """Print the constitutional policy in a human-readable format."""
    print("\n" + "═" * 60)
    print("📜  Constitutional Token Vault Policy")
    print("═" * 60)
    print(f"  Hash: {policy.constitutional_hash}")
    print(f"  Loaded from: {CONSTITUTION_PATH}")
    print()
    connections = set(k[0] for k in policy._rules)  # noqa: SLF001
    for conn in sorted(connections):
        print(f"  Connection: {conn}")
        roles = [k[1] for k in policy._rules if k[0] == conn]  # noqa: SLF001
        for role in sorted(roles):
            rule = policy.get_rule(connection=conn, role=role)
            assert rule is not None
            print(f"    {role:15s}: permitted={rule.permitted_scopes}")
            if rule.high_risk_scopes:
                print(f"    {'':15s}  step-up={rule.high_risk_scopes}")
        print()


# ── CLI ──────────────────────────────────────────────────────────────────────


async def main() -> None:
    parser = argparse.ArgumentParser(description="ACGS-Auth0 Constitutional Token Governance Demo")
    parser.add_argument(
        "--demo",
        choices=["all", "grant", "deny", "step-up", "audit", "policy"],
        default="all",
        help="Which demo scenario to run",
    )
    args = parser.parse_args()

    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║  ACGS-Auth0: Constitutional Token Governance for         ║")
    print("║              AI Agents (Auth0 Token Vault + MACI)        ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print(f"  Constitutional hash: {policy.constitutional_hash}")

    if args.demo in ("all", "policy"):
        await demo_policy_overview()
    if args.demo in ("all", "grant"):
        await demo_permitted_read()
    if args.demo in ("all", "deny"):
        await demo_scope_denial()
        await demo_role_not_permitted()
    if args.demo in ("all", "step-up"):
        await demo_step_up()
    if args.demo in ("all", "audit"):
        await demo_audit_trail()

    print("\n" + "═" * 60)
    print("  Demo complete.")
    print("  Set AUTH0_DOMAIN, AUTH0_CLIENT_ID, AUTH0_CLIENT_SECRET to")
    print("  run live Token Vault exchanges against your Auth0 tenant.")
    print("═" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
