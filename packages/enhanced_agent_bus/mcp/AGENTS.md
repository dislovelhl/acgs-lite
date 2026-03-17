# MCP Integration

> Scope: `src/core/enhanced_agent_bus/mcp/` — 10 files. Model Context Protocol client, routing, MACI filtering.

## STRUCTURE

```
mcp/
├── client.py        # MCP client for tool invocation
├── router.py        # Route MCP requests to appropriate tools
├── pool.py          # Connection pool management
├── config.py        # MCP server configuration
├── types.py         # MCP type definitions (includes FORBIDDEN status for MACI restrictions)
├── maci_filter.py   # MACI role enforcement — agents NEVER validate their own output
└── transports/      # Transport layer implementations (stdio, SSE, etc.)
```

## WHERE TO LOOK

| Task                   | Location         |
| ---------------------- | ---------------- |
| Add MCP tool           | `router.py`      |
| Change transport       | `transports/`    |
| Modify MACI filtering  | `maci_filter.py` |
| Connection pool tuning | `pool.py`        |

## CONVENTIONS

- `maci_filter.py` enforces separation of powers — independent validator, never self-validates.
- `types.py` defines `FORBIDDEN` status for MACI role restriction responses.
- Connection pooling mandatory — never create one-off MCP connections.

## ANTI-PATTERNS

- Do not bypass `maci_filter.py` for tool invocations.
- Do not import MCP types from `_ext_mcp.py` directly — use this module's `types.py`.
