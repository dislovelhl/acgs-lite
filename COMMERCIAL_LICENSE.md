# ACGS Commercial License

## Overview

ACGS is dual-licensed:

- **AGPL-3.0** for open-source use (free)
- **Commercial License** for proprietary/closed-source use (paid)

## When You Need a Commercial License

The AGPL-3.0 requires that if you use ACGS as part of a network service (SaaS, API, cloud platform), you must release the complete source code of that service under the AGPL-3.0.

**You need a commercial license if:**

- You embed ACGS in a proprietary SaaS product served to external users
- You offer ACGS functionality as a managed service or API
- You cannot comply with AGPL-3.0 source disclosure requirements
- Your legal team prohibits AGPL dependencies

**You do NOT need a commercial license if:**

- You use ACGS for internal-only AI pipelines (not exposed over a network to third parties)
- You use ACGS in CI/CD pipelines (output is pass/fail, not a network service)
- You deploy ACGS on-premises for internal use only
- You are building open-source software under an AGPL-compatible license
- You are using ACGS for research, education, or personal projects

## Commercial License Tiers

| Tier | Use Case | Contact |
|------|----------|---------|
| **Startup** | Small teams (<50 people), single product | hello@acgs.ai |
| **Enterprise** | Large organizations, multiple products | hello@acgs.ai |
| **OEM** | Embedding ACGS in a redistributed product | hello@acgs.ai |

## What the Commercial License Includes

- Exemption from all AGPL-3.0 obligations
- Right to use ACGS in proprietary, closed-source software
- Right to distribute ACGS as part of a commercial product
- No source code disclosure requirements
- Priority support options available

## How to Purchase

Contact hello@acgs.ai with:

1. Your company name and size
2. How you intend to use ACGS
3. Whether you need support/SLA

## FAQ

**Q: Is the AGPL "viral"? Will it infect my entire codebase?**
A: The AGPL applies to ACGS and modifications to it. Your application that calls ACGS via its Python API is not a derivative work. The AGPL triggers when you provide ACGS functionality over a network to external users — in that case, you must share the source of the complete service, or purchase a commercial license.

**Q: We use ACGS internally. Do we need a commercial license?**
A: No. Internal use (not exposed to third parties over a network) does not trigger the AGPL.

**Q: We run ACGS in our CI/CD pipeline. Is that covered?**
A: Yes, CI/CD runs internally. The output is a pass/fail result, not a network service. No commercial license needed.

**Q: Our legal team blanket-rejects AGPL. What do we do?**
A: Purchase a commercial license. It removes all AGPL obligations. This is the standard approach used by companies like MongoDB, Grafana, and Confluent.

**Q: Can we evaluate ACGS before purchasing?**
A: Yes. The AGPL allows full use for evaluation. You only need a commercial license when you deploy in a way that triggers the AGPL's network-use provision.

## Contact

Email: hello@acgs.ai
Website: https://acgs.ai
