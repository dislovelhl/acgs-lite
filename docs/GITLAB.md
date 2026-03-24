# GitLab Duo Integration

ACGS-Lite integrates directly into the GitLab development workflow as a governance layer for merge requests, CI/CD pipelines, and Duo Chat.

## How It Works

1. **MR Webhook** -- GitLab fires a merge request event (open, update, reopen)
2. **Constitutional Validation** -- every diff line, commit message, and MR description is validated against your constitutional rules
3. **MACI Enforcement** -- the MR author cannot also be the approver (separation of powers, enforced automatically)
4. **Inline Violations** -- governance findings appear as inline diff comments on the exact line
5. **Approve or Block** -- the bot approves clean MRs and blocks those with violations
6. **Audit Trail** -- every governance decision is cryptographically chained

## CI/CD Pipeline Stage

Add a governance gate to any pipeline:

```yaml
# .gitlab-ci.yml
governance:
  stage: test
  image: python:3.11-slim
  before_script:
    - pip install acgs-lite
  script:
    - acgs-lite validate --constitution rules.yaml --mr $CI_MERGE_REQUEST_IID
  rules:
    - if: $CI_PIPELINE_SOURCE == 'merge_request_event'
```

## MCP Server for Duo Chat

ACGS-Lite ships as a Model Context Protocol server. Connect it to GitLab Duo Chat and any MCP-compatible client:

```bash
python -m acgs_lite.integrations.mcp_server
```

Exposes five governance tools: `validate_action`, `get_constitution`, `get_audit_log`, `check_compliance`, `governance_stats`.

## Webhook Handler

```python
from acgs_lite.integrations.gitlab import GitLabGovernanceBot, GitLabWebhookHandler

bot = GitLabGovernanceBot(
    token=os.environ["GITLAB_TOKEN"],
    project_id=12345,
    constitution=Constitution.from_yaml("rules.yaml"),
)
handler = GitLabWebhookHandler(webhook_secret="my-secret", bot=bot)
# Mount handler.handle on POST /webhook
```

## GitLab-Specific Features

- `GitLabGovernanceBot` -- validates MRs against constitutional rules
- `GitLabWebhookHandler` -- Starlette-compatible webhook receiver
- `GitLabMACIEnforcer` -- maps MR roles to MACI roles (author=Proposer, reviewer=Validator, merger=Executor)
- Inline diff comments on violation lines
- Auto-approve or block based on governance results
- CI/CD pipeline stage generation
- MCP server for Duo Chat integration
