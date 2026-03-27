# ACGS Launch Pack

**Date:** 2026-03-27
**Purpose:** founder-style launch copy in English and Chinese
**Status:** draft

---

## Core Launch Line

**Guardrails filter outputs. ACGS governs actions.**

---

## English

### Short Launch Post

AI agents are moving from answering questions to taking actions.

That changes the control problem.

The question is no longer only whether the output is safe. It is:
- who proposed the action
- who validated it
- what rules were active
- whether governance can later be proven

ACGS is a constitutional governance layer for agentic systems:
- machine-readable constitutional rules
- runtime action governance
- structural anti-self-validation
- tamper-evident audit evidence
- compliance-oriented outputs

This is not another dashboard, another prompt filter, or another orchestration framework.

It is governance inside the runtime.

### LinkedIn Version

Most AI infrastructure today helps agents do more.

Almost none of it constrains what those agents are allowed to do.

That is the gap ACGS is built for.

ACGS is the constitutional governance layer for AI agents:
- define machine-readable rules
- govern actions before execution
- keep proposer and validator roles separate
- leave behind tamper-evident audit evidence
- produce outputs compliance and security teams can review

Guardrails tools help with unsafe inputs and outputs.
Agent frameworks help with orchestration.
Governance platforms help with oversight.

ACGS sits in the missing middle:
**governance inside execution.**

If AI agents can approve, deploy, deny, escalate, or execute, they need more than prompts.
They need a constitution.

### X / Short Version

AI agents can take actions. They need a constitution.

ACGS is a runtime governance layer for agentic systems:
- machine-readable rules
- anti-self-validation by architecture
- tamper-evident audit
- compliance-oriented outputs

Guardrails filter outputs.  
ACGS governs actions.

### Hacker News Version

We built ACGS around a simple thesis:

LLM safety is not enough once agents start acting in the world.

At that point, the real questions are institutional:
- who proposed the action?
- who validated it?
- who was allowed to execute it?
- which rule set was active?
- can you prove governance actually happened?

ACGS is an attempt to make those answers executable.

It is not a generic GRC dashboard.
It is not just an input/output guardrails library.
It is not an orchestration framework.

It is a constitutional governance layer for AI agents.

```bash
pip install acgs-lite
```

```python
from acgs_lite import Constitution, GovernedAgent

constitution = Constitution.from_yaml("rules.yaml")
agent = GovernedAgent(my_agent, constitution=constitution)
```

If you want runtime governance instead of only runtime filtering, that is the category ACGS is trying to build.

---

## 中文

### 短版发布文案

AI 正在从“回答问题”走向“采取行动”。

问题也因此改变了。

关键已经不只是输出是否安全，而是：
- 谁提出动作
- 谁验证动作
- 当时生效的是哪套规则
- 事后能不能证明治理真的发生过

ACGS 是面向 agentic systems 的宪政式治理层：
- 机器可执行的宪法规则
- 运行时动作治理
- 架构级防自我验证
- 防篡改审计证据
- 面向合规的输出结果

它不是又一个 dashboard，不是又一个 prompt filter，也不是又一个 orchestration framework。

它是嵌在 runtime 里的治理层。

### 中文社媒版

大多数 AI 基础设施都在帮助 agents 做更多事。

几乎没有基础设施真正约束 agents 被允许做什么。

这就是 ACGS 要补上的缺口。

ACGS 是面向 AI agents 的宪政式治理层：
- 定义机器可执行规则
- 在动作执行前做治理判断
- 用架构防止自我验证
- 把每次治理结果写进防篡改审计链
- 输出可被合规与安全团队消费的证据

Guardrails 过滤输出。  
ACGS 治理动作。

如果 AI agents 能审批、部署、拒绝、升级、执行，它们就需要的不只是 prompts。

它们需要一部宪法。

### 中文极短版

AI agents 能执行动作，就需要宪法。

ACGS 是面向 agentic systems 的 runtime governance layer：
- 动作执行前规则校验
- 架构级防自我验证
- 防篡改审计证据
- 面向合规的输出结果

Guardrails 过滤输出。  
ACGS 治理动作。
