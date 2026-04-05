# Subnet Concept Document

## Constitutional AI Governance: Human-in-the-Loop Deliberation on Bittensor

A decentralized subnet where miners provide human judgment for the governance decisions
AI cannot make alone.

*Draft -- March 2026. For Discussion Purposes Only.*

---

## Executive Summary

The ACGS-2 constitutional governance engine resolves 97% of AI governance decisions
autonomously in under one millisecond. The remaining 3% -- involving value conflicts,
ambiguous contexts, and irreconcilable stakeholder positions -- are escalated by design to
human deliberation, because no algorithm can substitute for genuine normative judgment.

This document proposes a Bittensor subnet that operationalizes that escalation path. The
subnet owner runs the ACGS-2 governance infrastructure on decentralized compute, while
miners are incentivized to provide the human deliberation needed for the hardest 3% of
governance decisions. Validators assess the quality and legitimacy of miner contributions,
and the TAO incentive mechanism ensures high-quality human reasoning is rewarded.

The result is a decentralized, incentive-aligned system for constitutional AI governance
that combines machine efficiency with human wisdom -- and a commercially viable platform
offered to corporations, institutions, and governments as AI-compliant infrastructure.

---

## The Problem: AI Governance Has a Human-Shaped Hole

The ACGS-2 system processes governance decisions through automated compliance checking at
nanosecond-scale latency (560ns P50 on the Rust hot path). It scores every decision across
seven governance vectors -- safety, security, privacy, fairness, reliability, transparency,
and efficiency -- and routes decisions into three tiers:

| Tier | Impact Score | Handling | Share |
|------|-------------|----------|-------|
| LOW | < 0.3 | Fully automated, sub-millisecond | ~97% |
| MEDIUM | 0.3 -- 0.8 | Auto-remediation with 15-minute human override window | ~2% |
| HIGH | >= 0.8 | Requires human approval before delivery | ~1% |

The MEDIUM and HIGH tiers represent cases where the automated system detects that it
cannot make the decision alone. These include:

- **Constitutional conflicts** -- multiple principles contradict each other (e.g., privacy
  vs. transparency). Resolving these requires value judgments, not logic.
- **Context sensitivity** -- the situation requires nuance that impact scoring alone
  cannot capture. Human contextual understanding is needed.
- **Stakeholder irreconcilability** -- different groups want fundamentally incompatible
  outcomes. Only human arbitration can navigate this.
- **Novel edge cases** -- entirely new situations the system has never encountered. Human
  precedent-setting is required.

These categories are a working taxonomy for the types of escalation the system produces.
Quantifying their relative frequency is an open research question that the subnet itself
would help answer as governance decisions accumulate.

These are not engineering bugs to be fixed with more data. They are the boundaries where
automated governance must yield to human deliberation. This subnet turns that requirement
into an economic opportunity.

---

## The Proposal: A Bittensor Subnet for Constitutional Deliberation

### Core Concept

The subnet operates as a decentralized constitutional court for AI systems. The subnet
owner runs the ACGS-2 governance infrastructure -- the automated engine that handles the
routine ~97% of compliance checks -- on decentralized compute sourced from other Bittensor
subnets. When the system encounters a case it cannot resolve autonomously (the MEDIUM and
HIGH tiers), it packages the case as a `DeliberationTask` and broadcasts it to miners on
the subnet for human deliberation.

### How It Works

#### The Subnet Owner: Running the Constitution

The subnet owner is responsible for operating and maintaining the ACGS-2 constitutional
governance infrastructure. This includes:

- **Hosting the constitutional framework** -- the set of principles, weights, and rules
  that define the governance constitution. Custom constitutions are defined as YAML
  documents via the `ConstitutionBuilder` API.
- **Running the verification pipeline** -- formal verification via Z3 SMT solver for
  policy constraint checking, multi-dimensional impact scoring across seven governance
  vectors, and Polis-style democratic deliberation for stakeholder consensus.
- **Detecting escalation cases** -- the `AdaptiveRouter` automatically identifies when a
  governance decision's impact score exceeds the escalation threshold and routes it to the
  deliberation path.
- **Packaging deliberation tasks** -- structuring the unresolved case as a
  `DeliberationTask` with all relevant context (message content, impact scores, competing
  principles, stakeholder positions) and dispatching it to miners.
- **Maintaining the constitutional hash** -- the cryptographic hash (`608508a9bd224290`)
  of the constitutional rule set, ensuring rule-set integrity is verifiable at any point.
  Individual governance decisions are recorded in the `AuditLog` with validation outcomes
  and the constitutional hash attached.

#### The Miners: Providing Human Judgment

Miners on this subnet are not running GPU workloads -- they are providing human
deliberation. When the ACGS-2 system escalates a case, miners receive a structured
deliberation package and are asked to:

- **Analyze the conflict** -- review the competing constitutional principles and
  understand why the automated system could not resolve them.
- **Provide a reasoned judgment** -- submit a decision along with a written rationale
  explaining the reasoning, tradeoffs considered, and the values prioritized. The
  `DeliberationTask` structure captures `human_decision` and `human_reasoning` fields.
- **Represent stakeholder perspectives** -- demonstrate engagement with the positions of
  all affected parties, not just one side.
- **Set precedent** -- for edge cases, their judgment may become part of the governance
  record, informing future automated decisions.

#### The Validators: Ensuring Quality and Legitimacy

Validators assess miner responses against multiple quality criteria:

- **Reasoning quality** -- is the rationale coherent, well-structured, and logically
  sound?
- **Stakeholder coverage** -- does the response engage with all affected parties?
- **Constitutional consistency** -- does the judgment align with the broader
  constitutional framework?
- **Deliberative authenticity** -- does the response reflect genuine human deliberation
  rather than AI-generated output?
- **Precedent compatibility** -- does the judgment create reasonable precedent for future
  cases?

---

## Why Bittensor?

### Incentive Alignment

The TAO incentive mechanism naturally rewards high-quality human reasoning. Miners who
provide thoughtful, well-reasoned governance judgments earn more than those who submit
superficial responses. This creates an economic market for human wisdom -- something that
has no equivalent in centralized systems.

### Decentralized Legitimacy

One of the core criticisms of Constitutional AI is the "synthetic constitution problem" --
constitutions written by a small group of developers lack democratic legitimacy. A
Bittensor subnet distributes interpretive authority across a decentralized network of
miners worldwide, directly addressing this concern.

### Decentralized Compute

The ACGS-2 infrastructure requires compute resources for running its verification
pipeline. Rather than relying on centralized cloud providers, the subnet owner can source
this compute from other Bittensor subnets, keeping the entire system within the
decentralized ecosystem.

### On-Chain Audit Trail

Today, the ACGS-2 system maintains a local tamper-evident audit log with SHA-256 hash
chaining and HMAC-signed compliance certificates. The constitutional hash guarantees
rule-set integrity. Deploying on Bittensor extends this to a truly decentralized audit
trail: every governance decision -- both the automated ~97% and the human-deliberated ~3%
-- is recorded on-chain with full traceability. The constitutional hash mechanism, combined
with Bittensor's blockchain, creates an immutable, distributed audit trail that no single
party controls.

---

## Revenue Model: How This Generates Value

Beyond TAO emissions, this subnet has clear pathways to generate external revenue by
offering services that organizations increasingly need but struggle to build in-house.

### 1. AI-Compliant Compute: Infrastructure as a Service (IaaS)

The primary commercial offering is an AI-compliant compute service. Corporations,
institutions, and governments developing AI systems face growing regulatory pressure -- the
EU AI Act, NIST AI Risk Management Framework, OECD AI Principles, and sector-specific
mandates -- to demonstrate that their AI is governed, auditable, and compliant.

This subnet offers that infrastructure as a service. Clients connect their AI pipeline to
the subnet and receive:

- **Automated constitutional compliance checking** for every AI decision or output,
  running on decentralized compute with sub-millisecond latency (560ns P50 on the Rust
  hot path for rule validation).
- **Human-in-the-loop resolution** for edge cases and value conflicts, provided by the
  miner network -- no need for the client to staff an internal ethics board for routine
  decisions.
- **Cryptographic audit trails** documenting every governance decision for regulatory
  reporting, with the constitutional hash and on-chain records serving as tamper-proof
  evidence of compliance.
- **Customizable constitutional frameworks** -- clients define their own governance
  principles as YAML constitutions via the `ConstitutionBuilder` API, and the subnet
  enforces them. Nine pre-built compliance frameworks are available out of the box: EU AI
  Act, NIST AI RMF, ISO 42001, GDPR, HIPAA, OECD AI Principles, NYC LL144, SOC2, and US
  Fair Lending.

Pricing: pay-per-decision, tiered subscription by volume and complexity, or enterprise
contracts with dedicated miner pools for guaranteed response times.

### 2. Governance Certification and Compliance Reporting

As AI regulation matures, organizations will need to demonstrate compliance to external
regulators, auditors, partners, and the public.

- **Continuous compliance monitoring** -- the subnet evaluates a client's AI system
  against their governance constitution and generates operational governance metrics
  (allow/deny rates, escalation frequency, override rates).
- **Audit-ready reports** -- structured documentation packages generated by the report
  engine, mapping governance decisions to specific regulatory requirements (EU AI Act
  articles, NIST framework categories, etc.) with cross-framework gap analysis.
- **On-chain compliance attestations** -- governance decisions recorded on Bittensor's
  chain provide verifiable, third-party evidence that an AI system met constitutional
  standards over a defined period. Because attestations are decentralized, they are harder
  to game or falsify compared to self-reported compliance.
- **Incident response records** -- when the system flags a violation or escalates to
  human review, the full resolution chain is documented and available for regulatory
  inquiry.

Pricing: annual certification fees, per-audit charges, or bundled with IaaS as a premium
tier.

### 3. Governance Intelligence: Case Law as a Data Product

Over time, the subnet accumulates something no other system has: a growing corpus of real
governance decisions made by humans on real AI conflicts. Every miner judgment, validator
assessment, and precedent-setting resolution becomes part of an evolving body of AI
governance case law.

- **Governance benchmarking datasets** -- anonymized, structured collections of
  governance scenarios and human-resolved outcomes, sold to AI research labs and academic
  institutions.
- **Industry-specific governance playbooks** -- curated collections of precedent
  decisions for specific sectors (healthcare AI, financial services, public sector).
- **Trend analysis and risk intelligence** -- aggregated insights on which types of
  governance conflicts are increasing and where new regulatory guidance may be needed.
- **Constitutional framework consulting** -- leveraging the accumulated case law to
  advise organizations on how to draft their own AI constitutions.

This revenue stream has a compounding advantage: the more governance decisions the subnet
processes, the more valuable the dataset becomes. Privacy-preserving techniques ensure
client-specific data remains confidential while aggregate governance patterns are
monetizable.

### Revenue Summary

| Revenue Stream | Target Customer | Pricing Model | Time to Revenue |
|----------------|----------------|---------------|-----------------|
| AI-Compliant Compute (IaaS) | Corporations, governments | Pay-per-decision or subscription | Near-term |
| Governance Certification | Regulated industries | Annual fees or per-audit | Medium-term |
| Governance Intelligence | AI labs, researchers | Data licensing or subscription | Long-term |

---

## Value Proposition

### For the Bittensor Ecosystem

- Introduces a novel subnet category: human reasoning as a service, rather than purely
  computational tasks.
- Creates demand for compute from other subnets (for running the ACGS-2 infrastructure).
- Brings external revenue into the ecosystem through commercial IaaS, certification, and
  data products.
- Positions Bittensor as infrastructure for AI governance, not just AI performance.

### For AI Developers and Deployers

- Provides an accessible, decentralized governance layer that integrates into any AI
  system.
- Offers auditable compliance for regulatory environments (EU AI Act, OECD Principles,
  etc.) across nine pre-built frameworks.
- Reduces the burden of internal governance by outsourcing the hardest decisions to a
  qualified, incentivized network.

### For Miners

- Earn TAO for providing human judgment and reasoning -- no GPU required.
- Participate in meaningful governance work that directly shapes how AI systems behave.
- Low hardware barrier to entry -- what matters is the quality of your reasoning, not the
  power of your machine.

---

## Open Questions and Considerations

This is an early-stage concept. Several important questions remain open for community
discussion:

### Sybil Resistance and Gaming

How do we ensure miners are providing genuine human deliberation and not farming responses
with AI? Validators must be equipped to distinguish authentic reasoning from synthetic
output. This is critical to the subnet's legitimacy.

### Miner Qualification

Should miners need any domain expertise to participate, or is general human judgment
sufficient? Some governance scenarios may require legal, ethical, or cultural knowledge.
The subnet could implement tiered tasks based on complexity.

### Deliberation Time vs. Latency

The ACGS-2 system's three-tier routing already handles this partially: MEDIUM-tier
decisions allow a 15-minute human override window, while HIGH-tier decisions block until
human approval. Finding the right cadence for the subnet -- balancing deliberation quality
against governance latency -- is a design challenge.

### Constitutional Evolution

As miner judgments accumulate, they effectively become case law -- precedent that shapes
future automated decisions. How should this feedback loop be governed? Who decides when a
miner's judgment becomes part of the constitution itself?

### MACI Enforcement on the Subnet

The ACGS-2 codebase enforces MACI (Minimal Anti-Collusion Infrastructure) separation of
powers: proposers cannot validate their own output, and validators cannot execute. Mapping
these roles onto Bittensor's miner/validator architecture requires careful design to
preserve the separation guarantees.

### Cross-Subnet Compute

The proposal assumes the subnet owner can source compute from other Bittensor subnets for
the ACGS-2 infrastructure. The mechanics of cross-subnet resource sharing and pricing
would need to be worked out in collaboration with the broader Bittensor community.

---

## Conclusion

The ACGS-2 system's most important feature is not that automated governance works -- it's
that the system knows when it doesn't work. The `AdaptiveRouter`'s ability to score
governance risk across seven dimensions and escalate to humans when impact exceeds its
threshold is a design feature, not a failure mode.

Bittensor provides the infrastructure to operationalize this insight at scale. By creating
a subnet where miners are incentivized to provide high-quality human judgment for the cases
AI cannot resolve, we build a system that is both decentralized and democratically
legitimate -- addressing the two biggest criticisms of existing constitutional AI
approaches.

With clear revenue pathways through AI-compliant compute services, governance
certification, and governance intelligence data products, this subnet is not just a
research experiment -- it is a commercially viable platform serving a market that is
growing as fast as AI regulation itself.

The ~97% is handled by machines. The ~3% is handled by humans. And the entire system is
governed by incentives that reward getting it right.
