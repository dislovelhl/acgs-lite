# acgs-deliberation

Deliberation, HITL, consensus, and impact-routing compatibility package for ACGS.

This package is the first extraction target from `packages/enhanced_agent_bus/`.
In this initial phase it provides a stable import surface while delegating to the
existing `enhanced_agent_bus.deliberation_layer` implementation.

Current goal:

- establish a standalone package boundary
- let new code import `acgs_deliberation`
- preserve backward compatibility for existing `enhanced_agent_bus.deliberation_layer` imports

Planned ownership:

- impact scoring
- adaptive routing
- deliberation queues
- voting and HITL workflows
- OPA guard flows used during review
