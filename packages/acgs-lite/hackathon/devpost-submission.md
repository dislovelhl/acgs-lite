# DevPost Submission — Constitutional Sentinel

> GitLab AI Hackathon 2026
> Deadline: March 25, 2026 @ 2:00pm EDT

---

## Project Name

Constitutional Sentinel

## Tagline

Constitutional governance for AI agents — separation of powers, tamper-evident audit trails, and nanosecond-scale validation for every AI-generated merge request.

## Inspiration

AI coding assistants now generate a significant portion of new code. But they operate without awareness of compliance rules, security policies, or regulatory requirements. An AI agent can hardcode credentials, leak PII, or write destructive SQL — and if the only check is the developer who prompted it, violations slip through.

We built the Constitutional Sentinel to solve this: an independent governance agent that enforces constitutional rules on every merge request, with cryptographic proof of which rules were applied.

## What it does

The Constitutional Sentinel is a GitLab Duo agent that validates every AI-generated merge request against a set of constitutional governance rules. It:

- **Validates every diff line** against 10+ constitutional rules covering credentials, PII, destructive SQL, CI pipeline integrity, and MACI separation of powers
- **Posts inline violation comments** directly on the lines that violate rules — not just a summary, but precise locations
- **Generates governance reports** with risk scores, violation counts, and tamper-evident constitutional hashes
- **Blocks merges** when CRITICAL or HIGH violations are found, with remediation guidance
- **Enforces MACI separation of powers** — the code author (Proposer) cannot approve their own merge request; the Sentinel (Validator) reviews independently; a human (Executor) performs the merge
- **Maintains a cryptographic audit trail** — every validation result embeds a constitutional hash proving which exact rules were enforced

## How we built it

### Engine: ACGS-Lite
The governance engine is built in Python with an optional Rust/PyO3 backend for performance-critical paths. The Rust backend achieves **560ns P50 per line** validation — governance completes before the GitLab page finishes loading.

### Constitution Format
Rules are defined in a portable YAML file (`constitution.yaml`). Organizations can define their own rules: HIPAA, SOC 2, PCI-DSS, internal security policies. Each rule has an ID, severity, category, keywords, and regex patterns.

### GitLab Integration
- **Webhook handler** receives MR events from GitLab
- **Diff parser** extracts added lines from MR changes
- **Governance bot** validates each line, posts inline comments, and generates summary reports
- **CI pipeline job** can run the Sentinel as part of any `.gitlab-ci.yml`

### Cloud Run Deployment
The Sentinel runs as a stateless container on Google Cloud Run:
- Auto-scales from 0 to handle MR bursts
- Health endpoint returns constitutional hash and rules count
- Governance summary endpoint provides compliance posture for dashboards

### MACI Architecture
Minimum Authority Constitutional Independence — three strictly separated roles:
- **Proposer**: AI agent (GitLab Duo) that writes code and opens MRs
- **Validator**: Constitutional Sentinel that independently reviews for compliance
- **Executor**: Human who decides whether to merge after governance clearance

No agent validates its own output. This is separation of powers applied to AI governance.

## Challenges we ran into

- **Balancing speed and accuracy**: The engine needs to validate entire diffs in milliseconds while maintaining zero false negatives for critical rules (credentials, PII). The Rust backend solved the speed problem; careful regex patterns solved accuracy.
- **GitLab API integration**: Posting inline comments at the correct diff line positions required parsing the unified diff format and mapping back to file line numbers.
- **Constitutional hash stability**: The hash must change when rules change but remain stable across identical constitutions. We compute it from sorted rule IDs + severities + texts.

## Accomplishments we're proud of

- **12 violations caught in a single demo MR** — every deliberately planted violation detected with zero false positives
- **560ns per line P50 validation** — governance is faster than page load
- **30/30 eval suite passing** — comprehensive capability and regression evals covering all integration points
- **3,820+ tests** in the full ACGS test suite
- **Tamper-evident audit trail** — hash-chained entries prove governance decisions can't be retroactively altered

## What we learned

- AI governance needs to be **structural, not advisory** — it's not enough to suggest best practices; you need an independent agent with the authority to block merges
- **Separation of powers** is as important for AI systems as it is for governments — no agent should validate its own output
- **Constitutional hashing** provides a practical mechanism for compliance auditing — auditors can verify exactly which rules were in force for any historical decision
- **Speed matters** for developer adoption — if governance adds latency, developers will bypass it

## What's next

- **GitLab Duo Flow integration** — register the Sentinel as a native Duo Flow for seamless agentic orchestration
- **MCP server** — expose governance tools via Model Context Protocol for any AI agent to call
- **EU AI Act compliance mapping** — map constitutional rules to EU AI Act risk categories for regulatory alignment
- **Multi-project governance** — a single Sentinel instance governing an entire GitLab group

## Built with

- Python 3.11+
- Rust (PyO3) — optional high-performance validation backend
- Google Cloud Run — serverless deployment
- GitLab API — MR webhooks, diff parsing, inline comments
- Starlette/Uvicorn — async HTTP server
- YAML — constitutional rule definitions
- ACGS-Lite — constitutional governance engine

## Try it out

- **GitLab Project**: https://gitlab.com/martin664/constitutional-sentinel-demo
- **Live Demo MR**: https://gitlab.com/martin664/constitutional-sentinel-demo/-/merge_requests/1
- **Cloud Run Health**: https://acgs-sentinel-208702602468.us-central1.run.app/health (requires GCP auth)
- **Constitution**: See `constitution.yaml` in the repo root

---

## Submission Checklist

- [ ] Project in GitLab AI Hackathon group (fork/transfer needed)
- [ ] Video uploaded to YouTube (public, 3 min max)
- [ ] Open-source license in repo
- [ ] AGENTS.md in repo root
- [ ] .gitlab-ci.yml with sentinel stage
- [ ] All source code in the project
- [ ] DevPost submission form filled out
