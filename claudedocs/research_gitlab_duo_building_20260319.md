# Research Report: Best Ways to Build with GitLab Duo

**Date**: 2026-03-19
**Depth**: Deep
**Confidence**: High (primary sources: official GitLab docs, GA announcements)

---

## Executive Summary

GitLab Duo has evolved from a code-completion assistant into a **full Agent Platform** (GA since January 15, 2026, GitLab 18.8+). The best ways to build with it span five tiers of increasing sophistication:

1. **AGENTS.md customization** — zero-code, per-repo AI behavior tuning
2. **Custom Agents** — system-prompt-driven specialists with tool access
3. **External Agents** — integrate Claude Code, Codex, Amazon Q, Gemini into GitLab workflows
4. **Custom Flows** — multi-agent YAML pipelines triggered by GitLab events
5. **MCP Server** — expose GitLab as a tool surface for any MCP-compatible AI client

The platform runs on **Anthropic Claude Sonnet 4** by default, supports self-hosted models, and bills via GitLab Credits.

---

## 1. AGENTS.md — Zero-Code Project Customization

**What**: A three-level configuration file (user, workspace, subdirectory) that shapes how GitLab Duo Chat and agentic flows behave per-project.

**How to use**:
- **User-level**: `~/.gitlab/duo/AGENTS.md` — personal coding preferences
- **Workspace-level**: `AGENTS.md` at repo root — team standards, project context
- **Subdirectory-level**: `path/to/module/AGENTS.md` — monorepo module-specific rules

**Best practices**:
- Document coding conventions, test frameworks, architectural decisions
- Include build/test commands the agent should use
- Specify which directories contain what (frontend, backend, shared libs)
- Changes only apply to new conversations — restart chats after updates

**Prerequisites**: Premium/Ultimate, VS Code 6.60+ or JetBrains 3.26.0+

**Relevance to ACGS**: Could embed constitutional governance rules (e.g., "All validation must go through the constitution engine. Never bypass MACI separation of powers.") so Duo agents respect governance invariants when generating code.

---

## 2. Custom Agents — System-Prompt-Driven Specialists

**What**: Agents you create through the UI with custom system prompts, selected tools, and visibility controls.

**Configuration**:
- Display name, description, system prompt
- Tool selection from built-in tool definitions (`ee/lib/ai/catalog/built_in_tool_definitions.rb`)
- Visibility: Private (managing project members) or Public (any qualifying project)
- Requires Maintainer/Owner role to create

**Surfaces**: Web UI sidebar chat, VS Code (6.47.0+), JetBrains (3.19.0+)

**Best building patterns**:
- **Compliance reviewer agent**: System prompt encodes your organization's compliance rules, given tools to read MRs and create comments
- **Architecture guardian**: Enforces module boundaries and import conventions
- **Security triage agent**: Pre-screens vulnerability reports with org-specific severity criteria
- **Onboarding assistant**: Knows repo structure, points new devs to relevant docs

**Limitation**: No SDK/API for programmatic agent creation — UI-only configuration workflow as of March 2026.

---

## 3. External Agents — Third-Party AI Integration

**What**: Integrate external AI providers (Claude Code, Codex, Amazon Q, Gemini) to operate within GitLab issues, MRs, and pipelines.

### Two Creation Approaches

**UI-Based (recommended)**: Via **Automate > Agents** in AI Catalog. Auto-provisions service account.

**Manual**: Create config files + service accounts separately. More flexible.

### Provider-Specific Setup

| Provider | Credential Model | Key Config |
|----------|-----------------|------------|
| Claude Code | GitLab-managed (AI Gateway) | `injectGatewayToken: true` |
| OpenAI Codex | GitLab-managed (AI Gateway) | `injectGatewayToken: true` |
| Amazon Q | Self-managed CI/CD vars | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` |
| Gemini | Self-managed CI/CD vars | `GOOGLE_CREDENTIALS`, `GOOGLE_CLOUD_PROJECT` |

### Trigger Types
- **Mention**: `@ai-agent-service-account Can you review this?`
- **Assign**: Triggered when assigned to issue/MR
- **Assign reviewer**: Triggered when assigned as MR reviewer

### Service Accounts
- Auto-created as `ai-<agent>-<group>`
- Receive Developer role permissions
- Use composite identity (user memberships + service account permissions)

### Security Considerations
- External agents **lack prompt injection scanning** available to built-in agents
- Network calls expose data to third-party provider policies
- No sandboxing beyond GitLab's standard permission model

**Best building pattern**: Use Claude Code as an external agent for deep code analysis tasks, triggered on MR assignment. The agent reads the diff, analyzes against your `AGENTS.md` standards, and posts structured review comments.

---

## 4. Custom Flows — Multi-Agent YAML Pipelines

**What**: Combine agents into guided, event-triggered automation sequences. Custom flows are in **beta**.

### Configuration

```
.gitlab/duo/agent-config.yml
```

Uses the **flow registry v1 specification** (maintained at `gitlab-org/modelops/applied-ml/code-suggestions/ai-assist/-/blob/main/docs/flow_registry/v1.md`).

### Available Triggers
1. **Mention** — comment mention of service account
2. **Assign** — assignment to issue/MR
3. **Assign reviewer** — assigned as MR reviewer
4. **Pipeline events** — `created`, `started`, `succeeded`, `failed`

### Built-in Flows (GA)
- **Software Development Flow** — end-to-end feature delivery
- **Developer Flow** — issue-to-MR conversion
- **Fix CI/CD Pipeline Flow** — automated pipeline troubleshooting
- **Code Review Flow** — structured review automation
- **SAST Vulnerability Flow** — security finding triage
- **False Positive Detection Flow** — reduce SAST noise

### Best Building Patterns

**CI/CD Self-Healing**: Trigger a flow on `pipeline.failed` that runs Root Cause Analysis, proposes a fix, creates a branch, and opens an MR.

**Code Modernization Pipeline**: Chain a refactoring agent with a test-generation agent and a review agent — flow executes the same way every time under your identity and rules.

**Governance-Aware Development**: Flow triggered on MR creation that runs constitutional validation, checks MACI separation of powers, and blocks merge if violations detected.

### Setup Scripts
Define setup scripts that run before flow execution (install dependencies, configure environments).

---

## 5. MCP Server — GitLab as AI Tool Surface

**What**: Standardized MCP interface that lets any MCP-compatible AI tool (Claude Desktop, Claude Code, Cursor, etc.) interact with your GitLab instance.

### Transport Options
- **HTTP transport** (recommended) — direct connection, no dependencies
- **stdio transport** — via `mcp-remote` proxy

### Available Tools (15 as of GitLab 18.10)

| Tool | Capability | Since |
|------|-----------|-------|
| `create_issue` | Create issues with full metadata | 18.5 |
| `get_issue` | Retrieve issue details | 18.5 |
| `create_merge_request` | Create MRs with assignees, reviewers | 18.5/18.8 |
| `get_merge_request` | Fetch MR details | 18.5 |
| `get_merge_request_commits` | List MR commits | 18.5 |
| `get_merge_request_diffs` | Retrieve file changes | 18.5 |
| `get_merge_request_pipelines` | Show MR pipelines | 18.5 |
| `get_pipeline_jobs` | Extract CI/CD jobs | 18.5 |
| `manage_pipeline` | List/create/retry/cancel pipelines | 18.10 |
| `create_workitem_note` | Add comments to work items | 18.7 |
| `get_workitem_notes` | Retrieve work item comments | 18.7 |
| `search` | Instance-wide search | 18.5/18.8 |
| `search_labels` | Find labels in projects/groups | 18.9 |
| `semantic_code_search` | AI-powered code discovery (beta) | 18.7 |
| `get_mcp_server_version` | Server version info | 18.5 |

### Dual MCP Architecture

GitLab supports **two complementary MCP workflows**:

1. **MCP Server** — GitLab exposes tools for external AI clients
2. **MCP Client** — Duo Agent Platform consumes external MCP tools/services

This means you can both **use GitLab from Claude Code** and **extend Duo agents with external tool servers**.

### Best Building Pattern

Configure Claude Code with the GitLab MCP server to create a unified workflow: Claude Code reads issues via MCP, implements changes locally, creates MRs via MCP, and monitors pipeline status — all without leaving the terminal.

---

## 6. Architecture Patterns for Building

### Pattern A: AGENTS.md + Built-in Flows (Low Effort, High Value)

```
AGENTS.md (repo root)
├── Project context, conventions, test commands
├── Module structure for monorepo
└── Governance rules (constitutional validation requirements)

Built-in flows:
├── Developer Flow → issue-to-MR
├── Code Review Flow → automated review
└── Fix CI/CD Flow → self-healing pipelines
```

**Best for**: Teams starting with Duo. Zero config beyond `AGENTS.md`.

### Pattern B: Custom Agents + External Agents (Medium Effort)

```
Custom Agents:
├── Compliance Reviewer (system prompt with org rules)
├── Architecture Guardian (enforces module boundaries)
└── Security Triage (pre-screens vulnerabilities)

External Agents:
├── Claude Code (deep code analysis on MR assignment)
└── Codex (bulk refactoring on mention)
```

**Best for**: Teams with specific workflow requirements beyond built-in capabilities.

### Pattern C: Full Platform — Flows + MCP + External Agents (High Effort, Maximum Control)

```
Custom Flows (YAML):
├── Governance validation pipeline (on MR create)
├── Security scan → triage → fix → review chain
└── Release readiness assessment (on pipeline.succeeded)

MCP Integration:
├── GitLab MCP Server → Claude Code/Desktop
├── External MCP servers → Duo Agent Platform
└── Bidirectional tool access

External Agents:
├── Claude Code (implementation)
├── Amazon Q (AWS-specific tasks)
└── Custom service account agents
```

**Best for**: Platform teams building AI-augmented DevSecOps at scale.

---

## 7. Key Recommendations

### Do First (Quick Wins)
1. **Create `AGENTS.md`** in every active repo — immediate quality improvement in Duo Chat responses
2. **Enable built-in flows** (Developer, Code Review, Fix CI/CD) — instant automation
3. **Connect GitLab MCP server** to your local AI tools (Claude Code, Cursor)

### Do Next (Medium-Term)
4. **Build 2-3 custom agents** for your highest-friction workflows (compliance, architecture review)
5. **Create an external Claude Code agent** for deep MR analysis
6. **Experiment with custom flows** for multi-step automation

### Do Later (Strategic)
7. **Build bidirectional MCP integration** — GitLab as both server and client
8. **Create governance-aware flows** that enforce constitutional validation
9. **Integrate Knowledge Graph** for enhanced code understanding

### Watch Out For
- **Prompt injection risk**: External agents lack GitLab's built-in prompt injection scanning. Validate outputs.
- **Credit consumption**: GA features consume GitLab Credits. Monitor usage, especially with flows that trigger frequently.
- **Beta stability**: Custom flows and MCP client are beta — expect breaking changes.
- **Context freshness**: `AGENTS.md` changes only apply to new conversations. Restart chats.

---

## 8. Relevance to ACGS Project

The GitLab Duo Agent Platform maps well to ACGS's constitutional governance model:

| ACGS Concept | GitLab Duo Mapping |
|-------------|-------------------|
| Constitutional validation | Custom agent with constitution rules in system prompt |
| MACI separation of powers | Separate agents for Proposer/Validator/Executor roles |
| Bounded self-evolution | Custom flow that proposes amendments → validates → merges |
| Compliance mapping | AGENTS.md with regulatory requirements |
| Governance pipeline | Custom flow triggered on MR with validation chain |

---

## Sources

- [GitLab Duo Agent Platform Docs](https://docs.gitlab.com/user/duo_agent_platform/)
- [Custom Agents](https://docs.gitlab.com/user/duo_agent_platform/agents/custom/)
- [External Agents](https://docs.gitlab.com/user/duo_agent_platform/agents/external/)
- [Custom Flows](https://docs.gitlab.com/user/duo_agent_platform/flows/custom/)
- [AGENTS.md Customization](https://docs.gitlab.com/user/duo_agent_platform/customize/agents_md/)
- [GitLab MCP Server Tools](https://docs.gitlab.com/user/gitlab_duo/model_context_protocol/mcp_server_tools/)
- [GitLab MCP Overview](https://docs.gitlab.com/user/gitlab_duo/model_context_protocol/)
- [GitLab Duo Use Cases](https://docs.gitlab.com/user/gitlab_duo/use_cases/)
- [Getting Started Guide](https://docs.gitlab.com/user/get_started/get_started_agent_platform/)
- [Development Architecture](https://docs.gitlab.com/development/duo_agent_platform/)
- [Flow Execution Configuration](https://docs.gitlab.com/user/duo_agent_platform/flows/execution/)
- [GitLab Duo Agent Platform GA Announcement](https://cloudfresh.com/en/news/gitlab-duo-agent-platform-is-now-generally-available/)
- [GitLab 2025-2026 Release Highlights](https://www.almtoolbox.com/blog/gitlab-2025-release-highlights-ai-cicd-devsecops/)
- [GitLab Duo Review (2026)](https://zencoder.ai/blog/gitlab-copilot-review)
