# ACGS-Lite: Constitutional Governance for AI in GitLab

## We Built the Engine Without the Brakes

$203 billion was invested in AI in 2025. Less than 1% went to governance infrastructure.

A single mother applies for a mortgage. 742 credit score. 12 years of stable employment. 28% debt-to-income ratio. The AI system rejects her application in 340 milliseconds. "Risk score insufficient." No human review. No appeal process. No explanation she can challenge.

This is not a hypothetical. This is Tuesday.

If machines are deciding our fate, who constrains the machines?

Every institution that wields power eventually gets a constitution. The Magna Carta constrained kings. Democratic constitutions constrained governments. Dodd-Frank constrained banks. AI is next -- and the EU AI Act enforcement deadline in August 2026 makes "next" mean "now," with fines up to 7% of global revenue for non-compliance.

Think of ACGS-Lite as **HTTPS for AI**. The web could not scale commercially until SSL/TLS gave users a reason to trust it. AI cannot scale into healthcare, finance, hiring, or any regulated domain without constitutional proof that decisions are bounded, auditable, and reversible.

Explainability tells you what happened. **Governance ensures it doesn't happen wrong in the first place.**

---

## What It Does

ACGS-Lite brings constitutional governance directly into GitLab's software development lifecycle. It is a governance engine -- built in Python and Rust -- that validates every AI-assisted action against constitutional principles before that action takes effect.

Three principles from democratic governance, applied to AI systems:

**Separation of Powers.** The entity that proposes a change cannot approve it. ACGS-Lite enforces MACI (Multi-Agent Constitutional Infrastructure) roles -- Proposer, Validator, Executor -- so an MR author can never approve their own merge request when AI agents are involved.

**Checks and Balances.** Every AI decision passes through constitutional validation. 97% of decisions are verified in under a millisecond. 3% are escalated to humans. The 97% saves millions in operational cost. The 3% is where governance actually happens.

**Due Process.** Every validation produces a tamper-evident SHA-256 audit record. Every escalation carries a recommended SLA. Every decision can be reviewed, challenged, and reversed.

### GitLab Integration (Four Layers)

1. **GitLab Duo Agent Flow** -- External agent triggered on MR events (@mentions, reviewer assignment). Validates diffs, commit messages, and code changes against the constitution. Posts inline violation comments on MR diffs.

2. **CI/CD Pipeline** -- Four governance jobs: constitutional validation, MACI separation check, hash verification, EU AI Act compliance report (Articles 12-14).

3. **MCP Server for Duo Chat** -- Five governance tools so developers can query posture directly: "What's our compliance status?" "Which rules apply here?"

4. **Webhook Handler** -- Real-time governance on GitLab events with context-aware risk scoring (production vs staging vs test).

### The Engine

- **560ns P50** validation latency (Rust/PyO3)
- **9 regulatory frameworks** -- EU AI Act, NIST AI RMF, ISO 42001, GDPR, SOC 2, HIPAA, ECOA/FCRA, NYC LL144, OECD AI Principles
- **125 compliance checklist items**, 72 auto-populated by ACGS-Lite
- **5-tier escalation** with SLA recommendations
- **Context risk scoring** that modulates strictness by environment
- **Constitutional hash** -- tampering is detectable
- **11 platform integrations** -- Anthropic, OpenAI, LangChain, LiteLLM, Google GenAI, and more
- **282 tests** across unit, integration, compliance, and constitutional suites
- **MultiFrameworkAssessor** -- jurisdiction-aware cross-framework gap analysis

---

## How We Built It

Here is the part that matters most.

**I have zero technical background.** No CS degree, no bootcamp, no years writing code. Two years ago I could not have told you what a function signature was.

**I built the entire ACGS-2 platform using Claude.** Not a single line was written by hand.

Every line of Python. Every line of Rust. The PyO3 bindings. The MCP server. The CI/CD pipeline. The 282 tests. The constitutional hash verification. The MACI enforcement layer. All of it -- through conversation with an AI that could write code I could not.

I am not a developer who used AI to go faster. I am a non-developer who used AI to go from zero to a production governance engine.

That distinction matters because it is the strongest possible argument for why AI governance is urgent: **the tool is so powerful that someone with no programming background can build enterprise-grade infrastructure with it.** That power needs constitutional constraints.

But it is also a democratic argument. We spent three centuries building constitutional constraints for human power because unconstrained power proved unsustainable. Kings resisted constitutions until revolution forced the issue. Financial institutions resisted regulation until systemic collapse demanded it. The question was never whether power would be constrained -- it was whether the constraints would be built by the people affected or imposed after the damage was done.

AI governance should not be the exclusive domain of the companies deploying AI. The people affected by algorithmic decisions -- the single mother denied a mortgage, the patient denied treatment, the candidate screened out -- deserve governance infrastructure they can inspect, understand, and hold accountable. **The most important governance infrastructure for AI should be built by the people who need it most, not just the people who already know how to code.**

The system that constrains the machines was built by the machines. And that is exactly why we need constitutional governance -- because if AI can build its own governance engine, it can certainly build systems without one.

**Development stack:** Claude (Anthropic) as primary development partner via Claude Code CLI. Test-driven development -- tests written before implementation. 97 optimization experiments achieving 37x latency improvement. Rust for performance-critical paths. The autoresearch loop runs 532 benchmark scenarios at 100% constitutional compliance.

---

## Challenges We Ran Into

**The governance paradox.** Building a system that constrains AI using AI creates a bootstrapping problem. The answer is the same as democratic constitutions: the constitution is separate from the governed entity, with its own integrity verification (hash), separation of powers (MACI), and audit trail.

**Nanosecond-scale validation.** Governance that slows workflows will be disabled. Sub-microsecond validation required Rust for the hot path and careful PyO3 optimization.

**EU AI Act interpretation.** The Act is law, not a technical specification. Translating Articles 12-14 into executable validation rules required legal research through hundreds of conversations with Claude about regulatory intent.

---

## What We Learned

Governance is not a feature. It is infrastructure. You do not add HTTPS to a website as a feature -- you build on a platform that provides it. AI governance works the same way.

The 97/3 split is real. Almost all AI decisions are routine. The small percentage needing human judgment is where governance value lives. The engine's job is ensuring human judgment is applied where it matters.

AI-assisted development, combined with rigorous testing, can produce systems exceeding what a solo developer builds manually. The 282 tests exist because Claude and I had long conversations about edge cases and attack vectors I would never have considered alone.

---

## What's Next

**August 2026 is the EU AI Act enforcement deadline.** Organizations deploying high-risk AI need governance infrastructure before that date.

- GitLab-native package installable from marketplace
- Multi-repository governance spanning GitLab groups
- Governance-as-Code -- constitutions in YAML, version-controlled alongside code
- Real-time compliance dashboard in GitLab
- Blockchain-anchored audit for independently verifiable evidence

---

## Built With

Python, Rust, PyO3, GitLab Duo Agent Platform, GitLab CI/CD, Model Context Protocol (MCP), Claude (Anthropic), SHA-256 cryptographic audit, EU AI Act Articles 12-14
