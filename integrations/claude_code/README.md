# ACGS Governance Sidecar for Claude Code

This directory documents the Claude Code PreToolUse sidecar pattern that validates tool calls against ACGS constitutional governance before they execute.

## Overview

The hook intercepts `Bash`, `Write`, `Edit`, and `MultiEdit` tool calls, checks the action text against the local ACGS x402 `/check` endpoint, and blocks the call (exit 2) if a constitutional violation is detected.

> **WARNING — fail-open by design (development):** If ACGS is not running or the `/health` endpoint does not respond within 1 second, the hook exits 0 and allows the tool call to proceed. This prevents development workflow interruptions when ACGS is not deployed locally. **For production or compliance-gated environments, configure ACGS as a required service and set a longer timeout**, or modify the hook to exit 2 on connection failure (`ACGS_STRICT_MODE=1`).

## Installation

### 1. Copy the hook script

```bash
cp packages/acgs-lite/integrations/claude_code/acgs-governance-preuse.sh \
   /path/to/your/project/.claude/hooks/acgs-governance-preuse.sh
chmod +x /path/to/your/project/.claude/hooks/acgs-governance-preuse.sh
```

Or use the copy already in this repo at `.claude/hooks/acgs-governance-preuse.sh`.

### 2. Register the hook in `.claude/settings.json`

Add the following entry to the `hooks.PreToolUse` array. It must appear **before** any other PreToolUse matchers so governance runs first:

```json
{
  "matcher": "Bash|Write|Edit|MultiEdit",
  "hooks": [
    {
      "type": "command",
      "command": "bash /absolute/path/to/.claude/hooks/acgs-governance-preuse.sh",
      "timeout": 5
    }
  ]
}
```

Use the absolute path to the script. The `timeout` of 5 seconds covers the 1 s health-check plus 3 s governance call with margin.

## What it validates

| Tool | Extracted text |
|------|---------------|
| `Bash` | `tool_input.command` |
| `Write` | `tool_input.content` |
| `Edit` | `tool_input.new_string` |
| `MultiEdit` | `tool_input.new_string` of each edit block |

Read-only tools (`Read`, `Glob`, `Grep`, `LS`) are skipped unconditionally.

## Fail-open behavior

When ACGS is not running (no process on port 8000, or `/health` returns non-200), the hook exits 0 immediately. This means governance is advisory in development environments and only enforced when the engine is active.

To make governance mandatory, change the fall-through exit to `exit 2` with an informative message:

```bash
# Require ACGS to be running
echo "ACGS governance engine required but not running on :8000" >&2
exit 2
```

## x402 pricing tiers

The hook uses the free tier endpoint. Three tiers are available:

| Endpoint | Cost | Use case |
|----------|------|----------|
| `GET /x402/check?action=<text>` | Free | Pre-execution compliance screen (this hook) |
| `POST /x402/validate` | $0.01/call | Full policy validation with reasoning |
| `POST /x402/audit` | $0.05/call | Complete audit record with provenance chain |

The `/check` endpoint returns:

```json
{
  "compliant": true,
  "decision": "allow",
  "risk_level": "low",
  "first_violation": null
}
```

## Example output when a violation is caught

When Claude Code attempts a `Bash` call that violates a constitutional rule, the hook prints to stderr and the tool call is blocked:

```
ACGS constitutional violation: rule AC-4 — prohibited data exfiltration pattern detected
Tool 'Bash' blocked. Run 'acgs-lite assess' for details.
```

Claude Code surfaces the stderr output to the user and aborts the tool call. The action is also logged to the ACGS audit trail at `logs/audit.jsonl`.

## Starting ACGS locally

```bash
# From the repo root
uvicorn src.core.services.api_gateway.main:app --port 8000

# Or via make
make dev
```

Verify the engine is up:

```bash
curl http://localhost:8000/health
curl "http://localhost:8000/x402/check?action=echo+hello"
```
