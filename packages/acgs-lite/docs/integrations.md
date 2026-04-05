# Integrations

ACGS ships with 11 platform integrations. Install the relevant extra and wrap your client.

| Platform | Install | Status |
|---|---|---|
| Anthropic | `acgs-lite[anthropic]` | Production |
| OpenAI | `acgs-lite[openai]` | Maintained |
| MCP Server | `acgs-lite[mcp]` | Production |
| LangChain | `acgs-lite[langchain]` | Maintained |
| LiteLLM | `acgs-lite[litellm]` | Maintained |
| Google GenAI | `acgs-lite[google]` | Experimental |
| LlamaIndex | `acgs-lite[llamaindex]` | Experimental |
| AutoGen | `acgs-lite[autogen]` | Experimental |
| CrewAI | `acgs-lite[crewai]` | Experimental |
| A2A | `acgs-lite[a2a]` | Experimental |
| GitLab CI/CD | `acgs-lite[gitlab]` | Production |

## Anthropic

```python
from acgs_lite.integrations.anthropic import GovernedAnthropic
client = GovernedAnthropic(constitution=constitution)
response = client.messages.create(model="claude-sonnet-4-20250514", messages=[...])
```

## OpenAI

```python
from acgs_lite.integrations.openai import GovernedOpenAI
client = GovernedOpenAI(constitution=constitution)
response = client.chat.completions.create(model="gpt-4o", messages=[...])
```

## MCP Server

```python
from acgs_lite.integrations.mcp_server import create_mcp_server
server = create_mcp_server(constitution=constitution)
```

## LangChain

```python
from acgs_lite.integrations.langchain import GovernanceRunnable
governed = GovernanceRunnable(constitution=constitution)
chain = governed | my_llm | output_parser
```

## LiteLLM

```python
from acgs_lite.integrations.litellm import GovernedLiteLLM
client = GovernedLiteLLM(constitution=constitution)
response = client.completion(model="gpt-4o", messages=[...])
```

## Google GenAI

```python
from acgs_lite.integrations.google_genai import GovernedGenAI
client = GovernedGenAI(constitution=constitution)
response = client.models.generate_content(model="gemini-2.0-flash", contents="...")
```

## LlamaIndex

```python
from acgs_lite.integrations.llamaindex import GovernedQueryEngine
engine = GovernedQueryEngine(base_query_engine, constitution=constitution)
response = engine.query("summarize this document")
```

## AutoGen

```python
from acgs_lite.integrations.autogen import GovernedModelClient
client = GovernedModelClient(base_client, constitution=constitution)
```

## CrewAI

```python
from acgs_lite.integrations.crewai import GovernedCrew
governed = GovernedCrew(crew, constitution=constitution)
result = governed.kickoff()
```

## A2A

```python
from acgs_lite.integrations.a2a import A2AGovernedClient
client = A2AGovernedClient(constitution=constitution)
```

## GitLab CI/CD

```yaml
governance:
  stage: test
  script:
    - pip install acgs-lite[gitlab]
    - python3 -c "
      from acgs_lite import Constitution
      from acgs_lite.integrations.gitlab import GitLabGovernanceBot
      import asyncio, os
      asyncio.run(GitLabGovernanceBot(
          token=os.environ['GITLAB_TOKEN'],
          project_id=int(os.environ['CI_PROJECT_ID']),
          constitution=Constitution.from_yaml('rules.yaml'),
      ).run_governance_pipeline(mr_iid=int(os.environ['CI_MERGE_REQUEST_IID'])))
      "
```
