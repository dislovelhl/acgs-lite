# ACGS Constitutional Governance Agent

This directory contains GitLab Duo integration assets for an ACGS-backed governance review agent.

## What the Agent Does

- reviews merge request diffs against constitutional rules
- checks separation of powers / self-approval risks
- reports governance findings back into the MR flow
- can layer AI-governance compliance checks on top of rule validation

## Files in This Directory

| File | Purpose |
| ---- | ------- |
| `flows/governance-agent.yaml` | external agent flow |
| `flows/governance-review.yaml` | review flow |
| `agent-config.yml` | runner configuration |
| `.gitlab-ci.yml` | CI integration |
| `chat-rules.md` | Duo chat rules |
| `AGENTS.md` | this guide |

## How to Interact With the Agent

- automatic MR triggers through the configured flow/CI path
- manual re-review by invoking the flow or mentioning the agent according to your GitLab setup

## Conventions

- Keep constitutional hash and rule configuration aligned with the actual deployed constitution.
- Keep proposer, validator, and executor roles separate in the flow design.
- Update the flow/config files together when changing the integration contract.

## Troubleshooting

- If the agent does not trigger, verify the flow registration and runner wiring.
- If the constitutional hash changes, update the paired configuration to match the active ruleset.
- If MACI checks are noisy for service accounts, treat exemptions as configuration, not ad hoc code.
