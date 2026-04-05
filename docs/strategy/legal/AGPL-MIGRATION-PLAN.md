# AGPL-3.0 License Migration Plan

**Date:** 2026-03-19
**Status:** Pre-execution
**Decision:** AGPL-3.0 + Commercial Dual License (confirmed)
**Timeline:** Week 1 of launch

> Historical planning note: this document captures the pre-migration plan. The repository is now
> licensed under `AGPL-3.0-or-later`, and the public PyPI package name is `acgs`.

---

## 1. What Changes

| Component | Current License | New License |
|-----------|----------------|-------------|
| `packages/acgs-lite/` | Apache-2.0 | AGPL-3.0 |
| `packages/enhanced_agent_bus/` | Apache-2.0 | AGPL-3.0 |
| `src/core/` | Apache-2.0 | AGPL-3.0 |
| `propriety-ai/` | Not licensed (private) | Proprietary (unchanged) |
| Root project | Apache-2.0 | AGPL-3.0 |

## 2. Files to Change

### Replace

| File | Action |
|------|--------|
| `/LICENSE` | Replace Apache-2.0 full text with AGPL-3.0 full text |
| `/pyproject.toml` | Change `license = "Apache-2.0"` to `license = "AGPL-3.0-or-later"` |
| `packages/acgs-lite/pyproject.toml` | Same |
| `packages/enhanced_agent_bus/pyproject.toml` | Same |
| `packages/acgs-lite/README.md` | Update license badge and footer |

### Add

| File | Content |
|------|---------|
| `/LICENSE-COMMERCIAL` | Commercial license header (see Section 5) |
| `/CLA.md` | Contributor License Agreement (see Section 6) |
| `/docs/strategy/legal/AGPL-FAQ.md` | Enterprise FAQ (see separate document) |
| `/.github/PULL_REQUEST_TEMPLATE.md` | Add CLA checkbox |

### Update Headers

Add AGPL header to all `.py` source files:

```python
# ACGS — Advanced Constitutional Governance System
# Copyright (C) 2024-2026 Martin [Last Name]
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#
# Commercial licensing available at https://propriety.ai/license
```

**Scope:** All files under `packages/` and `src/`. Exclude test files, config files, and `propriety-ai/`.

## 3. Communication Plan

### Pre-Migration (1 week before)

1. **GitHub Discussion post:** "ACGS is moving to AGPL-3.0 — here's why and what it means for you"
   - Explain the cloud provider protection rationale
   - Link to AGPL-FAQ.md
   - Emphasize: internal use is unaffected; commercial license available for SaaS embedding
   - 2-week comment period before execution

2. **README update:** Add notice: "Starting [date], ACGS will be licensed under AGPL-3.0. See [discussion link] for details."

### Migration Day

1. Replace LICENSE file
2. Update all pyproject.toml license fields
3. Add AGPL headers to source files (automated script)
4. Push CLA.md and LICENSE-COMMERCIAL
5. Tag release: `v3.1.0-agpl`
6. GitHub Release notes explaining the change

### Post-Migration

1. Monitor GitHub Issues/Discussions for questions
2. Respond to all license-related questions within 24 hours
3. Track any contributor departures (metric: contributor count before vs after)

## 4. Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Contributor backlash | 2-week advance notice; clear explanation; CLA is standard practice |
| Fork by cloud provider | AGPL is the protection; fork without commercial license violates AGPL for SaaS use |
| Enterprise adoption slowdown | Commercial license available; AGPL FAQ addresses common concerns |
| Existing Apache-2.0 users | Apache-2.0 applies to all code released BEFORE the migration. Only new versions are AGPL |

## 5. Commercial License Header

```
ACGS Commercial License

This is a commercial license for ACGS (Advanced Constitutional Governance System).
It permits use of ACGS without the obligations of the AGPL-3.0 license.

This license is available to organizations that:
- Embed ACGS in SaaS products served to external users
- Require proprietary modifications without source disclosure
- Need license terms incompatible with AGPL-3.0

Commercial licenses are included in ACGS Team and Enterprise tiers.
For standalone commercial licensing, contact: license@propriety.ai

Terms: https://propriety.ai/license/commercial
```

## 6. Contributor License Agreement (Summary)

The CLA grants ACGS the right to:
1. Distribute contributions under AGPL-3.0
2. Distribute contributions under a commercial license (dual licensing)
3. Relicense contributions under future OSI-approved licenses

The CLA does NOT:
1. Transfer copyright (contributor retains copyright)
2. Restrict contributor's own use of their contribution
3. Apply retroactively to pre-CLA contributions

**Implementation:** Use CLA Assistant (GitHub App) or a simple DCO (Developer Certificate of Origin) with sign-off. CLA Assistant is preferred for dual-licensing rights.

## 7. Automated Migration Script (Outline)

```bash
#!/bin/bash
# agpl-migrate.sh — Execute AGPL migration

# 1. Replace LICENSE
cp docs/strategy/legal/AGPL-3.0.txt LICENSE

# 2. Update pyproject.toml files
for f in pyproject.toml packages/*/pyproject.toml; do
  sed -i 's/license = "Apache-2.0"/license = "AGPL-3.0-or-later"/' "$f"
done

# 3. Add AGPL headers to Python source files
find packages/ src/ -name "*.py" -not -path "*/tests/*" -not -name "__init__.py" | while read f; do
  # Prepend AGPL header if not already present
  if ! grep -q "GNU Affero General Public License" "$f"; then
    cat docs/strategy/legal/agpl-header.txt "$f" > "$f.tmp" && mv "$f.tmp" "$f"
  fi
done

# 4. Commit
git add -A
git commit -m "license: migrate from Apache-2.0 to AGPL-3.0 + commercial dual license

AGPL-3.0 prevents cloud provider strip-mining while remaining OSI-compliant.
Commercial license available for SaaS embedding (Team/Enterprise tiers).
See docs/strategy/legal/AGPL-FAQ.md for details."

# 5. Tag
git tag -a v3.1.0-agpl -m "AGPL-3.0 migration"
```

## 8. Legal Checklist

- [ ] Confirm all existing contributors' code is Apache-2.0 (relicensable by project owner)
- [ ] Verify no third-party dependencies have GPL-incompatible licenses
- [ ] Draft CLA document (use established template: Apache CLA or Canonical CLA)
- [ ] Register CLA Assistant GitHub App on repository
- [ ] Prepare AGPL-3.0 full text file
- [ ] Draft commercial license terms (or use placeholder pending legal review)
- [ ] Budget: $3K-5K for legal review of CLA + commercial license terms
- [ ] Trademark: File "ACGS" and "Propriety" trademark applications (budget: $1K-2K)
