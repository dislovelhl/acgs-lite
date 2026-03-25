# ACGS-2 Diligence Appendix

**Project:** Advanced Constitutional Governance System (ACGS-2)  
**Prepared:** 2026-03-25  
**Purpose:** Technical diligence companion to investor-facing materials

---

## 1. Purpose of This Appendix

This appendix is meant to help investors and technical diligence reviewers separate:

- what is directly implemented,
- what is benchmarked,
- what appears partially integrated,
- and what is best treated as research direction rather than fully validated product capability.

That distinction is essential for evaluating ACGS-2 fairly.

---

## 2. High-Confidence Repo-Backed Capabilities

The following appear strongly supported by checked-in code and repo-local review artifacts.

### 2.1 Executable constitutions

The project models governance rules as runtime artifacts rather than static documentation.

**Key anchors**
- `packages/acgs-lite/src/acgs_lite/constitution/constitution.py`
- `packages/acgs-lite/src/acgs_lite/governed.py`

**Why it matters**
This is foundational to the project’s claim that governance is operationalized in software.

---

### 2.2 Runtime enforcement wrapper

`GovernedAgent` and related code paths indicate governance can wrap agent/callable execution directly.

**Key anchors**
- `packages/acgs-lite/src/acgs_lite/governed.py`
- `packages/acgs-lite/src/acgs_lite/engine/`

**Why it matters**
It supports the thesis that governance is part of the execution boundary, not only a manual review process.

---

### 2.3 Separation of powers / anti-self-validation

The MACI layer appears to implement explicit role boundaries and checks against self-validation.

**Key anchors**
- `packages/acgs-lite/src/acgs_lite/maci.py`
- related runtime/orchestration references in `packages/enhanced_agent_bus/`

**Why it matters**
This is one of the project’s most differentiated architectural choices and directly relevant to agentic risk containment.

---

### 2.4 High-performance governance path

The matcher and engine layers show evidence of hot-path optimization via keyword indexing, Aho-Corasick strategy, Bloom-filter-like early exits, and optional Rust acceleration.

**Key anchors**
- `packages/acgs-lite/src/acgs_lite/matcher.py`
- `packages/acgs-lite/rust/`
- `autoresearch/program.md`
- `autoresearch/results.tsv`

**Why it matters**
Governance infrastructure only matters commercially if it can remain in the execution path.

---

### 2.5 Audit integrity

The repo includes tamper-evident audit chain logic.

**Key anchors**
- `packages/acgs-lite/src/acgs_lite/audit.py`

**Why it matters**
This supports trust, traceability, and post hoc review in regulated or high-trust deployments.

---

### 2.6 Governance-of-governance

The repo includes constitutional invariants, activation controls, and rollback-related subsystems.

**Key anchors**
- `packages/enhanced_agent_bus/constitutional/invariant_guard.py`
- `packages/enhanced_agent_bus/constitutional/activation_saga.py`
- `packages/enhanced_agent_bus/constitutional/rollback_engine.py`

**Why it matters**
This is a strong signal that the project is thinking in terms of control-plane infrastructure rather than one-shot policy evaluation.

---

### 2.7 Compliance-aware mapping

The project includes multi-framework compliance support.

**Key anchors**
- `packages/acgs-lite/src/acgs_lite/compliance/multi_framework.py`
- related framework/checklist modules under `packages/acgs-lite/src/acgs_lite/`

**Why it matters**
This improves enterprise and regulated-market relevance.

---

### 2.8 Integration orientation

The repo includes integration paths for MCP, GitLab, policy systems, and runtime tool/message routing.

**Key anchors**
- `packages/acgs-lite/src/acgs_lite/integrations/mcp_server.py`
- `packages/acgs-lite/src/acgs_lite/integrations/gitlab.py`
- `packages/enhanced_agent_bus/message_processor.py`
- `packages/enhanced_agent_bus/opa_client/core.py`

**Why it matters**
This suggests the project is intended for insertion into real operational workflows, not only research demos.

---

## 3. Benchmark Interpretation

### 3.1 What is clearly supported

Repo-local benchmark artifacts support the following statements:

- the project maintains a governance-specific benchmark harness in `autoresearch/`
- the harness uses a fixed scenario corpus and explicit scoring discipline
- logs record multiple high-throughput, low-latency runs with full benchmark compliance
- the benchmark currently references **809 scenarios** and **18 rules checked** in checked-in logs

### 3.2 Strongest observed performance signal

A checked-in result associated with exp254 records approximately:

- `throughput_rps`: **1,125,948.608354**
- `p99_ms`: **0.003920**
- `compliance_rate`: **1.000000**
- `scenarios_tested`: **809**
- `composite_score`: **0.999882**

### 3.3 Why this should be presented carefully

The same results log also shows:

- exp254 was marked **discard**,
- rerun performance degraded,
- nearby notes describe a performance ceiling and sensitivity to jitter.

### 3.4 Recommended investor-safe wording

Use:

> “The benchmark harness recorded a best observed run above 1.1M requests/sec at microsecond-scale p99 latency over 809 scenarios with full benchmark compliance, though that specific run was not retained as the stable comparable baseline due to rerun instability.”

Avoid:

- “validated production throughput of 1.1M+ RPS”
- “stable 3.9us p99 in production”
- “proven at scale” unless tied to a real deployment workload

---

## 4. Areas That Look Real but Need Maturity Qualification

These subsystems appear substantial, but should be presented as uneven-maturity or further-diligence-required areas rather than fully de-risked product capabilities.

### 4.1 Advanced formal verification / policy generation

**Key anchors**
- `src/core/shared/policy/unified_generator.py`
- verification-related modules in `packages/enhanced_agent_bus/`

**Caution**
Promising, but likely not the same maturity level as the core executable-governance and runtime-enforcement path.

---

### 4.2 Long-context / Mamba-inspired processing

**Key anchors**
- `packages/enhanced_agent_bus/mamba2_hybrid_processor.py`
- `packages/enhanced_agent_bus/context_memory/...`

**Caution**
This appears implemented and research-linked, but investor materials should not imply broadly proven 4M-token production governance performance without clearer end-to-end validation.

---

### 4.3 Democratic constitutional governance / CCAI

**Key anchors**
- `packages/enhanced_agent_bus/governance/ccai_framework.py`
- related governance modules/tests

**Caution**
Interesting and differentiated, but likely better framed as advanced governance functionality and research positioning rather than the primary near-term commercial wedge.

---

### 4.4 Broad “breakthrough stack” synthesis

**Key anchors**
- `src/research/docs/research/breakthrough_2025/synthesis_acgs2_breakthrough_architecture_2025.md`

**Caution**
This document is useful for roadmap and technical vision, but should not be treated as equivalent to end-to-end production validation of every listed subsystem.

---

## 5. Suggested Claims Discipline

### Safe claims

- “ACGS-2 operationalizes AI governance as runtime software infrastructure.”
- “The system implements executable constitutions, separation of powers, audit integrity, rollback-aware governance evolution, and compliance-oriented integration.”
- “The repo includes a real benchmark harness with strong best observed hot-path performance.”
- “The architecture is designed to sit above model vendors and agent frameworks.”

### Claims to scope carefully

- “formal guarantees” → specify which subsystem and under what assumptions
- “validated breakthrough” → only if tied to specific benchmark, module, or deployment evidence
- “4M+ context” → present as architecture/prototype capability unless deployment evidence is supplied
- “solves self-verification” → prefer “implements anti-self-validation through role separation”

### Claims to avoid in investor materials

- “solved alignment”
- “first system to guarantee human values”
- “fully production-proven across all subsystems”
- “benchmark results are production SLOs”

---

## 6. Suggested Diligence Workstreams

### 6.1 Architecture review

Goal: determine what is core vs peripheral.

Questions:
- Which modules are on the critical path to productization?
- Which capabilities are genuinely used in default flows vs present as optional or research subsystems?
- Where are the largest complexity concentrations?

---

### 6.2 Benchmark reproducibility review

Goal: determine how portable and repeatable the performance claims are.

Questions:
- What hardware and software stack were benchmark numbers captured on?
- What variance appears across reruns and machines?
- What is the stable retained baseline vs best observed ceiling?
- What workloads best approximate customer reality?

---

### 6.3 Productization review

Goal: determine near-term commercial shape.

Questions:
- Is the initial product a library, gateway, hosted control plane, or hybrid?
- What are the first buyer personas?
- What integrations are most market-relevant in the next 12 months?
- What is the shortest path to trust-critical production deployment?

---

### 6.4 Security and trust review

Goal: validate that governance posture is real under failure conditions.

Questions:
- Which paths are fail-closed?
- How are policy changes authenticated, versioned, and rolled back?
- What attack surfaces exist around role assignment, policy mutation, and audit integrity?
- How does the system behave when optional dependencies fail or degrade?

---

### 6.5 Commercial moat review

Goal: assess defensibility.

Questions:
- Is the moat in architecture, integrations, benchmarked performance, compliance mapping, or workflow embedding?
- How quickly could a capable competitor replicate the visible core?
- What portion of the value comes from code vs trust, process, and ecosystem placement?

---

## 7. What Would Increase Confidence Materially

The following would materially strengthen investor confidence:

1. A package-by-package maturity matrix
2. Reproducible benchmark appendix with hardware/software profile
3. Real pilot evidence or internal deployment case studies
4. Clear product packaging and deployment model
5. Narrow vertical or wedge strategy with named buyer pains
6. A stable set of customer-facing performance claims
7. Separation of “research roadmap” from “shipping product” in all external materials

---

## 8. Recommended Bottom-Line View

From a diligence perspective, the strongest reading is:

- There is **real technical substance** here.
- The project’s **core governance architecture appears differentiated**.
- The **system-level thesis is more credible than broad AI-safety rhetoric**.
- Some advanced subsystems likely require maturity discounting.
- The biggest remaining question is not whether there is code, but whether the team can **package, focus, and commercialize the right wedge**.

That is a healthy place for diligence to begin.
