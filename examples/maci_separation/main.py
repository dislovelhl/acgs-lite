"""
Example: MACI Separation of Powers
=====================================
The MACI (Multi-Agent Constitutional Infrastructure) pattern enforces
constitutional separation of powers: Proposer → Validator → Executor.
Golden Rule: agents NEVER validate their own output.

Run:
    python examples/maci_separation/main.py
"""

from acgs_lite import MACIEnforcer, MACIRole, MACIViolationError


def demo_basic_roles() -> None:
    """Each agent role can only perform its sanctioned operations."""
    print("\n── 1. Role-Based Operation Gates ─────────────────────────────")
    enforcer = MACIEnforcer()
    enforcer.assign_role("agent-proposer", MACIRole.PROPOSER)
    enforcer.assign_role("agent-validator", MACIRole.VALIDATOR)
    enforcer.assign_role("agent-executor", MACIRole.EXECUTOR)
    enforcer.assign_role("agent-observer", MACIRole.OBSERVER)

    cases = [
        ("agent-proposer", "propose", True, "Proposer drafts a change"),
        ("agent-proposer", "validate", False, "Proposer tries to self-validate"),
        ("agent-validator", "validate", True, "Validator reviews the proposal"),
        ("agent-validator", "execute", False, "Validator tries to execute"),
        ("agent-executor", "execute", True, "Executor applies approved action"),
        ("agent-executor", "propose", False, "Executor tries to propose"),
        ("agent-observer", "read", True, "Observer reads audit log"),
        ("agent-observer", "execute", False, "Observer tries to execute"),
    ]

    for agent_id, operation, allowed, label in cases:
        try:
            enforcer.check(agent_id, operation)
            icon = "✅" if allowed else "❌ SHOULD HAVE BLOCKED"
            print(f"  {icon}  {label}")
        except MACIViolationError as exc:
            icon = "🚫" if not allowed else "❌ SHOULD HAVE ALLOWED"
            print(f"  {icon}  {label} — {exc}")


def demo_constitutional_amendment_workflow() -> None:
    """Simulate a full propose → validate → execute cycle."""
    print("\n── 2. Constitutional Amendment Workflow ───────────────────────")
    enforcer = MACIEnforcer()
    enforcer.assign_role("drafter-agent", MACIRole.PROPOSER)
    enforcer.assign_role("review-agent", MACIRole.VALIDATOR)
    enforcer.assign_role("deploy-agent", MACIRole.EXECUTOR)

    proposal = "Add rule: agents must not access raw PII without audit log"
    print(f'  Proposal: "{proposal}"')

    # Step 1: Proposer submits
    enforcer.check("drafter-agent", "propose")
    print("  Step 1 ✅  drafter-agent PROPOSER → propose (draft submitted)")

    # Step 2: Independent validator reviews (not the proposer!)
    enforcer.check("review-agent", "validate")
    print("  Step 2 ✅  review-agent  VALIDATOR → validate (independent review passed)")

    # Step 3: Executor applies
    enforcer.check("deploy-agent", "execute")
    print("  Step 3 ✅  deploy-agent  EXECUTOR → execute (amendment applied)")

    # Violation: drafter tries to bypass validation and execute directly
    try:
        enforcer.check("drafter-agent", "execute")
        print("  ❌  Should have blocked self-execution!")
    except MACIViolationError:
        print("  🚫  BLOCKED: drafter-agent cannot bypass Validator (execute denied for PROPOSER)")


def demo_self_validation_prevention() -> None:
    """check_no_self_validation raises when agent proposes AND validates."""
    print("\n── 3. Self-Validation Prevention ─────────────────────────────")
    enforcer = MACIEnforcer()
    enforcer.assign_role("alpha", MACIRole.PROPOSER)

    # alpha proposes — recorded in audit log
    enforcer.check("alpha", "propose")

    # alpha tries to also validate its own output
    try:
        # proposer_id == validator_id → self-validation violation
        enforcer.check_no_self_validation(proposer_id="alpha", validator_id="alpha")
        print("  ❌  Should have caught self-validation!")
    except MACIViolationError as exc:
        print(f"  🚫  Self-validation caught: {exc}")

    # Different agent validates — fine
    enforcer.assign_role("beta", MACIRole.VALIDATOR)
    enforcer.check_no_self_validation(proposer_id="alpha", validator_id="beta")
    print("  ✅  beta validates alpha's proposal — independent review OK")


def demo_summary() -> None:
    """Print enforcer audit summary."""
    print("\n── 4. Audit Summary ──────────────────────────────────────────")
    enforcer = MACIEnforcer()
    enforcer.assign_role("a", MACIRole.PROPOSER)
    enforcer.assign_role("b", MACIRole.VALIDATOR)

    enforcer.check("a", "propose")
    enforcer.check("b", "validate")
    try:
        enforcer.check("a", "validate")
    except MACIViolationError:
        pass

    summary = enforcer.summary()
    print(f"  Total checks  : {summary.get('checks_total', '?')}")
    print(f"  Checks denied : {summary.get('checks_denied', '?')}")
    print(f"  Agents        : {summary.get('agents', '?')}")


if __name__ == "__main__":
    print("=" * 55)
    print("  MACI Separation of Powers Demo")
    print("=" * 55)

    demo_basic_roles()
    demo_constitutional_amendment_workflow()
    demo_self_validation_prevention()
    demo_summary()

    print("\nDone. Golden Rule enforced: agents never validate their own output.")
