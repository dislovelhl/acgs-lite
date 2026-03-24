# MCP Integration

> Scope: `packages/enhanced_agent_bus/mcp/` — client, routing, pooling, MACI filtering, and
> transports.

## Structure

- `client.py`: MCP client logic
- `router.py`: routing requests to tools/servers
- `pool.py`: connection pooling
- `config.py`: configuration
- `types.py`: shared MCP types
- `maci_filter.py`: MACI-aware request filtering
- `shared_bridge.py`: bridge helpers for shared integration
- `transports/`: transport implementations

## Where to Look

| Task | Location |
| ---- | -------- |
| Add/change tool routing | `router.py` |
| Transport work | `transports/` |
| Pool behavior | `pool.py` |
| MACI restrictions | `maci_filter.py` |
| Shared MCP data/types | `types.py`, `shared_bridge.py` |

## Conventions

- Keep separation-of-powers checks in the filtering path.
- Reuse pooled connections instead of one-off clients.

## Anti-Patterns

- Do not bypass `maci_filter.py`.
- Do not invent parallel MCP type definitions outside `types.py`.
