## Change Summary

- What changed:
- Why now:

## Risk Assessment

- Risk: `low | medium | high`
- Blast radius:
- Compatibility: `no public API change | additive | breaking`
- Migration note: `not needed | docs/migrations/<version>.md`

## Evidence

- Local verification:
  - [ ] `make policy`
  - [ ] `uv run make lint`
  - [ ] `uv run make typecheck`
  - [ ] `uv run make test-cov`
- CI / artifacts:
- Screenshots, logs, benchmarks, or audit output:

## Governance Mapping

- Rules touched: `R-XXX`
- Policy tests:
  - `tests/policy/test_no_secrets_in_diff.py`
  - `tests/policy/test_api_breaking_changes_require_notice.py`
  - `tests/policy/test_governance_tags_present.py`
- Runtime governance impact:

## Rollback Plan

- Revert command or release rollback:
- Expected recovery time:
- Data / audit-log implications:

## CLA / Rights

- [ ] I certify that I have the right to submit this contribution and that it may be licensed under the repository license.
- [ ] I did not knowingly include secrets, credentials, private keys, proprietary datasets, or third-party code without compatible licensing.
- [ ] If this work was created for an employer or client, I have authority to submit it.
