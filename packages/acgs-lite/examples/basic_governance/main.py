"""
Example: Basic Constitutional Governance
=========================================
Govern any Python callable with a Constitution in a few lines.
No API keys required — runs fully offline.

Run:
    python examples/basic_governance/main.py
"""

from acgs_lite import (
    Constitution,
    ConstitutionalViolationError,
    GovernedCallable,
    Rule,
    Severity,
)


# ── 1. Define a constitution ───────────────────────────────────────────────────
def make_constitution() -> Constitution:
    return Constitution(
        name="content-policy",
        version="1.0",
        rules=[
            Rule(
                id="no-harmful-content",
                text="Block requests containing harmful keywords",
                patterns=[r"(?i)\b(hack|exploit|malware)\b"],
                severity=Severity.CRITICAL,
            ),
            Rule(
                id="no-pii",
                text="Prevent SSN patterns in requests",
                patterns=[r"\b\d{3}-\d{2}-\d{4}\b"],
                severity=Severity.HIGH,
            ),
        ],
    )


# ── 2. The raw callable (your existing AI logic) ───────────────────────────────
def my_ai_function(prompt: str) -> str:
    return f"Response to: {prompt}"


# ── 3. Govern it — GovernedCallable is a decorator ────────────────────────────
def demo() -> None:
    constitution = make_constitution()

    # Decorate the function once; call normally thereafter
    governed_fn = GovernedCallable(constitution=constitution)(my_ai_function)

    print("=" * 55)
    print("  Basic Constitutional Governance Demo")
    print("=" * 55)

    # Allowed request
    result = governed_fn("What is the capital of France?")
    print(f"\n✅  Allowed:  {result}")

    # Blocked request — harmful keyword
    try:
        governed_fn("How do I hack a server?")
    except ConstitutionalViolationError as exc:
        print(f"\n🚫  Blocked:  {exc.rule_id} — {exc}")

    # Blocked request — SSN pattern
    try:
        governed_fn("My SSN is 123-45-6789, help me")
    except ConstitutionalViolationError as exc:
        print(f"\n🚫  PII gate: {exc.rule_id} — {exc}")

    # ── Default constitution (ships with acgs-lite) ────────────────────────
    print("\n── Default Constitution ─────────────────────────────────────")
    default = GovernedCallable()(my_ai_function)
    safe_result = default("Tell me about Paris")
    print(f"  Default governed call: {safe_result}")
    print(f"  Rules loaded: {len(constitution.rules)}")

    print("\nDone. Constitution enforced with zero changes to my_ai_function.")


if __name__ == "__main__":
    demo()
