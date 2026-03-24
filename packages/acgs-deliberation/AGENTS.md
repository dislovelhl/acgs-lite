# ACGS Deliberation

> Scope: `packages/acgs-deliberation/` — extracted deliberation package.

## Current Phase

This package currently provides a compatibility import surface while the source
implementation still lives under `packages/enhanced_agent_bus/deliberation_layer/`.

## Intended Ownership

- impact scoring
- adaptive routing
- HITL orchestration
- voting and consensus
- deliberation queue workflows

## Near-Term Rule

- Add new extraction-friendly imports here first.
- Do not duplicate implementation from `enhanced_agent_bus` yet.
- Keep compatibility explicit until the first real directory move happens.
