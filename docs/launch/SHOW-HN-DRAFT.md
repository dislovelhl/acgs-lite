# Show HN Draft

Practical launch document. Copy the title and body directly into the HN submission form.
The FAQ section is for the founder to reference when responding to comments.

---

## Title (80 chars max)

```
Show HN: ACGS – Constitutional governance for AI agents (HTTPS for AI)
```

72 characters. Fits.

---

## Submission Text (~2000 chars)

Copy everything between the START and END markers into the HN text field.

--- START ---

ACGS is a runtime governance layer for AI agents. You define rules in YAML
(keywords, regex, severity levels), wrap your agent in five lines, and every
action gets validated before execution with results recorded in a SHA-256
chain-verified audit trail. It enforces structural separation between the agent
proposing an action and the system validating it (what we call MACI --
Proposer/Validator/Executor/Observer roles that cannot be collapsed).

The problem: agents are moving from answering questions to taking actions.
Orchestration frameworks handle flow, guardrails handle output quality, but
nothing governs what an agent is allowed to do at runtime -- or leaves behind
evidence that it was governed. The EU AI Act takes full enforcement in August
2026 with fines up to 7% of global revenue, and most production agent
deployments have zero infrastructure for proving compliance.

Try it:

    pip install acgs-lite

    from acgs_lite import Constitution, GovernedAgent

    constitution = Constitution.from_template("general")
    agent = GovernedAgent(my_agent, constitution=constitution)
    result = agent.run("process this request")  # governed

What makes it different from existing tools:

- 560ns P50 validation latency on the Rust/PyO3 hot path (Aho-Corasick pattern
  matching). Pure Python path is slower -- run `make bench` on your hardware.
- 9 regulatory framework mappings (EU AI Act, NIST AI RMF, GDPR Art. 22, SOC 2,
  HIPAA, ISO 42001, ECOA/FCRA, NYC LL 144, OECD AI) with structured compliance
  report output. 125 checklist items, 72 auto-populated.
- Integrations for 11 platforms: Anthropic, OpenAI, MCP, LangChain, LiteLLM,
  LlamaIndex, AutoGen, CrewAI, Google GenAI, GitLab CI, A2A.
- MACI separation of powers -- agents cannot validate their own output. This is
  a structural constraint, not a policy check.
- Tamper-evident audit trail with constitutional hashing.
- 3,874 tests passing. Apache-2.0 licensed.

Limitations worth being honest about: rule-based matching is deterministic but
not semantic. If you need LLM-based content understanding (toxicity detection,
nuanced intent classification), tools like Guardrails AI or LlamaGuard are
better suited. ACGS governs actions and process; it does not replace content
safety. The compliance mappings are a starting point for structured evidence, not
a substitute for legal counsel. Single-maintainer project -- bus factor is 1.

Built entirely through conversation with Claude by a non-technical founder.

Would love feedback on: (1) the API design, (2) which regulatory frameworks
matter most to your team, and (3) whether the MACI separation model maps to how
you think about agent trust boundaries.

Repo: https://github.com/acgs2_admin/acgs
PyPI: https://pypi.org/project/acgs-lite/

--- END ---

Character count: ~1,950 (within the ~2,000 target).

---

## Anticipated HN Comments and Responses

### "Rule-based is too simple for real governance"

> Fair point. ACGS is deterministic by design -- keyword matching, regex, and
> Aho-Corasick pattern scanning. It does not do semantic analysis or LLM-based
> content understanding. That is intentional for this layer: regulatory and
> institutional controls need determinism and traceability. When an auditor asks
> "why was this action blocked?", the answer should be a rule ID and a matched
> pattern, not "the safety model thought it was risky with 73% confidence."
> For content-level safety (toxicity, prompt injection), you would pair ACGS with
> something like Guardrails AI or LlamaGuard. Different layers solving different
> problems.

### "Why not just use OPA?"

> OPA is excellent for infrastructure policy (Kubernetes admission, API
> authorization). It was not built for AI agent governance. The differences that
> matter: (1) ACGS has regulatory framework mappings for 9 compliance standards
> that OPA has no concept of, (2) the MACI architecture enforces structural
> role separation between proposer and validator -- which is an AI-specific
> concern, not a generic policy concern, (3) the constitutional model (YAML
> rules with severity, keywords, and audit chaining) is more intuitive for
> governance authors than Rego. That said, if you already have OPA for
> infrastructure, keep it. ACGS sits at the agent action layer, not the
> infrastructure layer.

### "AGPL / license concerns"

> ACGS is Apache-2.0 licensed. An earlier version was AGPL, but it was
> relicensed to Apache-2.0 to remove adoption friction. No CLA, no commercial
> dual-license. Straightforward open source.

### "One person built this?"

> Yes. I am a non-technical founder who could not write a for loop two years
> ago. The entire codebase -- 3,874 passing tests, the Rust hot path, the MACI
> architecture -- was built through conversation with Claude. I consider this
> both the strongest argument for why AI agents need governance and an honest
> disclosure about the project's bus factor. The code can be inspected directly.
> Contributions are welcome.

### "How is this different from Guardrails AI?"

> Different layers. Guardrails AI focuses on LLM output quality -- validators
> that check whether a response meets format/content/safety expectations.
> ACGS focuses on runtime governance: who is allowed to take which actions, with
> what approvals, and what evidence is left behind. Guardrails validates
> outputs. ACGS governs actions. In practice they are complementary. If you are
> building an agent that takes real-world actions (not just generating text), you
> want both: Guardrails for output quality, ACGS for action governance.

### "560ns seems too good to be true"

> The 560ns P50 number is specifically from the optional Rust/PyO3 hot path
> using Aho-Corasick pattern matching, measured via `make bench` on the repo.
> It is the pattern-matching step only, not end-to-end agent governance overhead.
> The pure Python path is meaningfully slower (expect low-millisecond range
> depending on rule complexity and hardware). I should be clearer about this in
> the README. The point is not "governance is free" -- it is "governance can be
> cheap enough that teams do not disable it in production hot paths."

### "What prevents someone from just skipping the governance layer?"

> Nothing, architecturally. ACGS is a library, not a hypervisor. If you control
> the code, you can bypass it. The value is in making governance the default
> path rather than an afterthought. The MACI separation means the governed agent
> API structurally routes through validation -- you would have to actively remove
> it, not accidentally skip it. For environments where bypass prevention is
> critical, you would pair this with infrastructure-level controls (network
> policies, IAM, etc.). ACGS is the governance logic layer, not the enforcement
> perimeter.

### "3,874 tests but what is the actual coverage?"

> Repository-wide coverage threshold is 70% (fail_under = 70 in pytest config).
> The enhanced_agent_bus package targets 80%. Happy to improve this. The test
> suite includes unit, integration, constitutional, MACI, and compliance tests.
> Run `make test` to see for yourself.

### "This is just a YAML config validator with extra steps"

> I understand the skepticism. The YAML rules are the definition layer, but the
> system does more than validate config: (1) MACI enforces role separation at
> runtime -- the proposing agent structurally cannot act as its own validator,
> (2) every validation decision is recorded in a SHA-256 chained audit trail
> with constitutional hashing, (3) the compliance module maps governance state
> to 9 regulatory frameworks with structured report output. Whether that
> qualifies as "extra steps" or "missing infrastructure" depends on whether you
> need to prove governance to an auditor. If you do not, then yes, it is
> probably over-engineered for your use case.

---

## Timing Recommendation

### Best days and times to post on Hacker News

**Optimal window:** Tuesday, Wednesday, or Thursday between 8:00-10:00 AM Eastern (5:00-7:00 AM Pacific, 13:00-15:00 UTC).

**Why:**
- HN traffic peaks during US working hours on weekdays. The front page turns
  over fastest on weekdays, but the upvote-to-visibility ratio is best
  mid-morning Eastern when both US coasts and Europe are active.
- Monday is crowded with weekend project launches. Friday afternoon loses
  momentum into the weekend.
- Tuesday-Thursday mornings give the best 12-hour runway for accumulating
  upvotes before traffic drops off.

**Avoid:**
- Weekends (lower traffic, but also lower competition -- use only if the post
  is very niche).
- Friday after 2 PM Eastern.
- Monday before 9 AM Eastern (competes with Show HN backlog from the weekend).
- Major tech news days (Apple events, big acquisitions, etc.) -- check the front
  page before posting.

**Specific recommendation:** Post on a **Tuesday or Wednesday at 9:00 AM Eastern**.
This gives the US East Coast their morning coffee reading, catches Europe in the
afternoon, and gives US West Coast time to engage as they come online.

### Post-submission checklist

1. Post the submission. Do not self-upvote from other accounts (HN detects this).
2. Be present for the first 2-3 hours to respond to comments quickly. Fast,
   substantive founder responses are the single biggest factor in keeping a
   Show HN alive.
3. Responses should be technical, specific, and honest about limitations.
   Acknowledge good criticism. Do not be defensive.
4. If someone asks a question covered in the FAQ above, adapt the response to
   their specific framing -- do not paste canned answers.
5. If the post does not gain traction in the first hour, do not delete and
   repost. HN penalizes this. Try again the following week.
