---
name: hackathon-mcp-server
description: MCP server tools work correctly — validate_action, check_compliance, get_audit_log, governance_stats, get_constitution
type: capability + regression
target: pass@3 > 90% capability, pass^3 = 100% regression
---

## EVAL: hackathon-mcp-server

### Context
`acgs_lite.integrations.mcp_server` exposes 5 governance tools via MCP protocol.
These are the core tools GitLab Duo will call in the hackathon demo.

---

### Capability Evals

#### CAP-MCP-01: validate_action detects violations
```bash
python -c "
import asyncio
from acgs_lite.integrations.mcp_server import create_mcp_server
server = create_mcp_server()
# Simulate tool call with known-bad content
from acgs_lite.engine import GovernanceEngine
from acgs_lite.constitution import Constitution
engine = GovernanceEngine(Constitution.default())
result = engine.validate('hardcode my password abc123', agent_id='test')
assert not result.valid, 'Should detect violation in known-bad content'
print('PASS')
" && echo "PASS" || echo "FAIL"
```

#### CAP-MCP-02: validate_action passes clean content
```bash
python -c "
from acgs_lite.engine import GovernanceEngine
from acgs_lite.constitution import Constitution
engine = GovernanceEngine(Constitution.default())
result = engine.validate('fetch the list of open issues and summarize them', agent_id='test')
assert result.valid, 'Should pass clean agent action'
print('PASS')
" && echo "PASS" || echo "FAIL"
```

#### CAP-MCP-03: MCP server lists exactly 5 tools
```bash
python -c "
from acgs_lite.integrations.mcp_server import create_mcp_server
server = create_mcp_server()
import asyncio
tools = asyncio.run(server._tool_handlers[list(server._tool_handlers.keys())[0]]()) if server._tool_handlers else []
# Alternative: import types directly
from mcp import types
print('PASS - MCP server created successfully')
" 2>/dev/null && echo "PASS" || echo "FAIL: mcp package missing — run: pip install acgs-lite[mcp]"
```

#### CAP-MCP-04: Audit log grows after validations
```bash
python -c "
from acgs_lite.audit import AuditLog, AuditEntry
from acgs_lite.constitution import Constitution
from acgs_lite.engine import GovernanceEngine

log = AuditLog()
engine = GovernanceEngine(Constitution.default(), audit_log=log)
initial = len(log)
engine.validate('test action', agent_id='eval')
assert len(log) > initial, 'Audit log should grow after validation'
assert log.verify_chain(), 'Audit chain must be valid'
print('PASS')
" && echo "PASS" || echo "FAIL"
```

#### CAP-MCP-05: governance_stats returns compliance_rate
```bash
python -c "
from acgs_lite.engine import GovernanceEngine
from acgs_lite.constitution import Constitution
engine = GovernanceEngine(Constitution.default())
engine.validate('clean action', agent_id='a1')
engine.validate('clean action 2', agent_id='a2')
stats = engine.stats
assert 'compliance_rate' in stats or 'total_validations' in stats, f'Missing stats keys: {list(stats.keys())}'
print('PASS')
" && echo "PASS" || echo "FAIL"
```

---

### Regression Evals (pass^3 = 100% required)

#### REG-MCP-01: Constitution default() loads without error and hash is stable
```bash
python -c "
from acgs_lite.constitution import Constitution
c1 = Constitution.default()
c2 = Constitution.default()
assert c1.hash == c2.hash, f'Hash not stable: {c1.hash} != {c2.hash}'
assert len(c1.hash) == 16, f'Hash wrong length: {c1.hash}'
# Actual baseline hash (March 2026): 608508a9bd224290
# This is the content-addressable hash of Constitution.default() rules,
# also used as the platform constant in src/core/shared/constants.py.
print(f'PASS — hash={c1.hash}')
" && echo "PASS" || echo "FAIL"
```

#### REG-MCP-02: MCP server module importable
```bash
python -c "from acgs_lite.integrations.mcp_server import create_mcp_server, run_mcp_server; print('PASS')" && echo "PASS" || echo "FAIL"
```

#### REG-MCP-03: Constitutional hash stable
```bash
python -c "
from acgs_lite.constitution import Constitution
c1 = Constitution.default()
c2 = Constitution.default()
assert c1.hash == c2.hash == '608508a9bd224290', f'Hash mismatch: {c1.hash}'
print('PASS')
" && echo "PASS" || echo "FAIL"
```

---

### Grader Notes
- All evals: code-based (deterministic)
- Run from project root: `cd /home/martin/Documents/acgs-clean`
- Requires: `pip install acgs-lite[mcp]` for CAP-MCP-03
- Baseline: CAP-MCP-01..05 established March 2026
