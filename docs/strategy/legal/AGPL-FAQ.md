# AGPL-3.0 FAQ for ACGS Users

**Audience:** Developers and enterprise legal teams evaluating ACGS
**Last updated:** 2026-03-19

---

## General

### Why did ACGS switch from Apache-2.0 to AGPL-3.0?

Apache-2.0 allows cloud providers to take ACGS, offer it as a managed service, and contribute nothing back. This is not theoretical — it happened to Elasticsearch (AWS forked to OpenSearch), Redis (AWS/Google backed Valkey fork), and HashiCorp (cloud providers offered Terraform-as-a-service). AGPL-3.0 prevents this while remaining a fully OSI-approved open-source license.

### Is AGPL-3.0 really open source?

Yes. AGPL-3.0 is approved by the Open Source Initiative (OSI), the Free Software Foundation (FSF), and Debian. It meets all 10 criteria of the Open Source Definition. It is the same license used by Grafana ($270M ARR), MongoDB (before SSPL), and Nextcloud.

### Can I still use ACGS for free?

Yes. The complete ACGS engine is free to use under AGPL-3.0. There are no feature restrictions in the open-source version.

---

## For Developers

### I use ACGS in my internal AI pipeline. Do I need to do anything?

**No.** AGPL obligations only apply when you provide the software to third parties over a network. Internal use — even across teams, departments, or offices within your organization — does not trigger AGPL.

### I use ACGS in my CI/CD pipeline (GitLab/GitHub Actions). Does AGPL apply?

**No.** CI/CD pipelines run internally. The output (pass/fail governance check) is not "conveying" the software to external users. This is standard internal use.

### I modified ACGS for my team's internal use. Do I need to publish my changes?

**No.** AGPL only requires source disclosure when you provide the modified software to external users over a network. Internal modifications for internal use have zero AGPL obligations.

### I'm building an open-source project that uses ACGS as a dependency. What do I need to do?

If your project is also AGPL-3.0 or GPL-3.0 compatible, nothing special — standard open-source practices apply. If your project uses a permissive license (MIT, Apache-2.0), you'll need to either:
1. License your project under AGPL-3.0 (or a compatible license), or
2. Obtain a commercial license from ACGS for your specific use case

### Can I use ACGS as a library in my application without my entire application becoming AGPL?

This is the most nuanced question. The FSF's position is that linking to an AGPL library makes the combined work subject to AGPL. However, if ACGS is called via a network API (e.g., the ACGS MCP server or REST API), your application is **not** a derivative work and AGPL does not apply to your code.

**Recommended approach:** If you want to avoid AGPL questions entirely, use ACGS via its MCP server or REST API endpoint rather than as an embedded Python import.

---

## For Enterprise Legal Teams

### Our policy prohibits AGPL dependencies. What are our options?

We offer a **commercial license** that removes all AGPL obligations. Commercial licenses are included in ACGS Team ($999/month) and Enterprise (custom) tiers. For standalone commercial licensing inquiries: license@propriety.ai

### Does AGPL apply if we use ACGS internally only?

**No.** AGPL Section 13 (the "network interaction" clause) only applies when users interact with the software remotely over a network. All internal use — development, testing, staging, production infrastructure serving only your employees — is exempt from AGPL disclosure requirements.

### We embed ACGS in our SaaS product. Does AGPL apply?

**Yes.** If your SaaS product makes ACGS functionality available to external users over a network, AGPL Section 13 requires you to make the Corresponding Source available to those users. Options:

1. **Comply with AGPL:** Make your ACGS-related source code available (not your entire application — only the ACGS components and modifications)
2. **Commercial license:** Purchase a Team or Enterprise tier, which includes a commercial license removing AGPL obligations
3. **API isolation:** Use ACGS as a separate microservice called via REST/MCP, keeping it architecturally isolated from your proprietary code

### What about "AGPL contamination" — does it spread to our entire codebase?

AGPL applies to the ACGS library and any modifications you make to it. It does **not** automatically apply to your application that calls ACGS through a well-defined API. The key factors:

| Usage Pattern | AGPL Applies To |
|---------------|-----------------|
| Import ACGS as Python library, modify ACGS source | Your modifications to ACGS |
| Import ACGS as Python library, no modifications | ACGS itself (your code is a separate work under most interpretations) |
| Call ACGS via REST API / MCP server | Nothing in your application |
| Fork ACGS and redistribute | Your fork of ACGS |

**Note:** This FAQ provides general guidance, not legal advice. Consult your legal team for your specific use case.

### What does the commercial license cover?

The commercial license grants:
- Right to use ACGS without AGPL obligations
- Right to embed ACGS in proprietary SaaS products
- Right to modify ACGS without source disclosure
- Priority support and SLA guarantees
- All features in the corresponding tier (Team or Enterprise)

The commercial license does NOT grant:
- Right to sublicense ACGS to third parties
- Right to redistribute ACGS under a different license
- Ownership of ACGS intellectual property

### Is there a CLA for contributors?

Yes. All contributors to ACGS sign a Contributor License Agreement (CLA) that grants ACGS the right to distribute contributions under both AGPL-3.0 and commercial licenses. Contributors retain copyright to their contributions. This is standard practice for dual-licensed open-source projects (used by MongoDB, Grafana, GitLab, and others).

---

## Quick Reference

| Your Use Case | AGPL Triggered? | Action Needed |
|---------------|-----------------|---------------|
| Internal AI pipeline | No | None |
| CI/CD governance gate | No | None |
| On-premise deployment | No | None |
| Development and testing | No | None |
| SaaS product (external users) | **Yes** | Comply with AGPL or purchase commercial license |
| Managed service offering | **Yes** | Purchase commercial license |
| Open-source project (AGPL-compatible) | Yes (compatible) | License under AGPL or compatible |
| Open-source project (permissive license) | Yes (incompatible) | Relicense or purchase commercial license |
| Academic / research use | No (typically internal) | None |
| Consulting / professional services | No (typically internal) | None |

---

## Contact

- Commercial licensing: license@propriety.ai
- License questions: legal@propriety.ai
- General support: support@propriety.ai
