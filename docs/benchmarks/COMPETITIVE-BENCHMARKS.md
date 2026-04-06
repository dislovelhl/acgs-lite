# ACGS Competitive Benchmarks

**Last updated:** 2026-04-06
**Constitutional Hash:** `608508a9bd224290`

> **Honesty disclaimer:** This document is maintained by the ACGS project. We have done our best
> to be accurate and transparent about data sources, but you should verify claims independently.
> Numbers marked **(measured)** come from our test suite. Numbers marked **(published)** come from
> the competitor's own documentation or blog posts. Numbers marked **(estimated)** are inferred
> from architecture and public information and should be treated as rough approximations.

---

## 1. Methodology

### What We Measured

| Metric | Description |
|--------|-------------|
| **P50 latency** | Median wall-clock time for a single `engine.validate()` call |
| **P95 latency** | 95th percentile latency |
| **P99 latency** | 99th percentile latency |
| **Throughput** | Validations per second (single-threaded, sequential calls) |
| **Memory usage** | RSS delta after engine construction + 10K validations |
| **Startup time** | Time to construct `GovernanceEngine` from a `Constitution` |

### How We Measured

- **Tool:** `pytest-benchmark` (pytest plugin using `timeit`-style calibration)
- **Python:** CPython 3.11+ (PyO3 abi3 stable ABI)
- **Rust toolchain:** stable, `--release` with LTO and `opt-level = 3`
- **Iterations:** pytest-benchmark auto-calibrates; minimum 5 rounds, 1000+ iterations per round
- **Warm-up:** 3 warm-up rounds discarded before measurement (plus the engine's own JIT warm-up loop for the Rust path -- see `core.py` lines 298-329)
- **Hardware:** Results vary by machine. The canonical 560ns P50 claim was measured on an AMD Ryzen 9 / Apple M-series class machine. **Always run on your own hardware before quoting latency.**
- **OS:** Linux (Fedora 43, kernel 6.19) and macOS (Apple Silicon)
- **Isolation:** No other CPU-intensive processes. `pytest-benchmark` uses `timer=time.perf_counter_ns` where available.

### Reproducibility

All benchmarks can be reproduced with:

```bash
# From repo root
git clone https://github.com/<org>/acgs-clean.git
cd acgs-clean

# Install with Rust acceleration (optional but recommended)
cd packages/acgs-lite/rust && maturin develop --release && cd ../../..

# Install Python deps
pip install -e packages/acgs-lite[dev]

# Run benchmarks
make bench

# Or directly:
python -m pytest packages/acgs-lite/tests/test_benchmark_engine.py \
    -m benchmark -v --import-mode=importlib --benchmark-json=benchmark-results.json
```

The `--benchmark-json` flag produces a machine-readable JSON file for CI regression tracking.

---

## 2. ACGS Benchmarks

### 2.1 Benchmark Test Suite

The benchmark suite lives at `packages/acgs-lite/tests/test_benchmark_engine.py` and covers
three scenarios:

| Test | What it measures |
|------|-----------------|
| `test_engine_construction_default_constitution` | Engine startup from default constitution (6 rules) |
| `test_validate_allow_path_default_constitution` | Validation of a benign action (allow path) |
| `test_validate_deny_path_default_constitution` | Validation of a violating action (deny path) |

### 2.2 Historical Benchmark Samples

From `examples/bench_sample/` (autoresearch experiment runs):

| Run | P50 (us) | P99 (us) | Score |
|-----|----------|----------|-------|
| exp001 | 2.8 | 12.1 | 0.91 |
| exp002 | 2.5 | 10.4 | 0.93 |
| exp003 | 2.3 | 8.9 | 0.95 |
| exp004 | 2.4 | 9.2 | 0.94 |
| exp005 | 2.2 | 8.1 | 0.96 |

These are end-to-end Python-level measurements including PyO3 FFI crossing overhead.

### 2.3 Rust Hot Path (PyO3)

When `acgs_lite_rust` is installed, the engine dispatches to a Rust validator that uses:

- **Aho-Corasick automaton** (`aho-corasick` 1.1) for O(N) multi-pattern keyword matching
- **Bitmask deduplication** (u64) for O(1) fired-rule tracking
- **Pre-allocated exceptions** to avoid Python object construction on deny paths
- **Anchor dispatch** to skip regex evaluation when anchor words are absent

Architecture: `GovernanceValidator` (Rust, `validator.rs`) exposes two methods:
- `validate_hot(text_lower)` -> `(decision: int, data: int)` -- minimal FFI, legacy bitmask path
- `validate_full(text_lower, context_pairs)` -> `(decision, violations, blocking)` -- structured output

**Claimed performance (Rust hot path, 6 rules, allow path):**

| Metric | Value | Source |
|--------|-------|--------|
| P50 latency | ~560ns | **(measured)** autoresearch experiments |
| P99 latency | ~8-12us | **(measured)** bench_sample data |
| Throughput | ~1.8-2.8M validations/sec | **(derived)** from P50 latency |

> **Important caveat:** The 560ns figure is the Rust `validate_hot` path with a 6-rule default
> constitution on the allow path (no violations triggered). Deny paths are slower due to exception
> construction. Real-world latency depends on rule count, pattern complexity, action string length,
> and whether context fields require additional validation passes.

### 2.4 Python-Only Path

When the Rust extension is not installed, the engine falls back to:

1. **pyahocorasick** C extension (if installed) for keyword scanning
2. **Pure Python regex** fallback if neither Rust nor pyahocorasick is available

**Estimated performance (Python path, 6 rules):**

| Metric | Value | Source |
|--------|-------|--------|
| P50 latency | ~3-10us | **(estimated)** from architecture (10-20x Rust overhead) |
| P99 latency | ~20-50us | **(estimated)** |
| Throughput | ~100K-300K validations/sec | **(estimated)** |

> These are estimates based on typical Python/C FFI overhead ratios. Run `make bench` without
> the Rust extension installed to get actual numbers for your platform.

### 2.5 Memoization Cache

The `MemoizedConstitution` wrapper (`constitution/memoization.py`) provides an LRU cache
keyed on SHA-256(action + sorted_context):

| Metric | Cache Miss | Cache Hit |
|--------|-----------|-----------|
| Latency | Same as engine path | ~100-200ns **(estimated)** (dict lookup + SHA-256 check) |
| Throughput | Same as engine path | ~5-10M lookups/sec **(estimated)** |

The cache is useful for workloads with high action repetition (health checks, monitoring
queries, recurring agent operations). It is not useful for workloads where every action
string is unique.

### 2.6 Scaling by Rule Set Size

The Rust validator uses a u64 bitmask, which hard-limits the hot path to **63 rules maximum**.
Constitutions larger than 63 rules fall back to the Python path.

| Rule Count | Path | Expected Latency Impact |
|------------|------|------------------------|
| 6 (default) | Rust | Baseline (~560ns P50) |
| 10 | Rust | ~1.1x baseline **(estimated)** -- more AC patterns, linear in input |
| 50 | Rust | ~2-3x baseline **(estimated)** -- more regex anchors to check |
| 63 | Rust | ~3-4x baseline **(estimated)** -- bitmask limit |
| 64+ | Python fallback | ~10-20x baseline **(estimated)** -- no Rust acceleration |
| 100 | Python | ~15-25x baseline **(estimated)** |
| 1000 | Python | Not benchmarked; expect proportional scaling with pattern count |

> **Limitation:** We have not yet built synthetic constitutions at 100 or 1000 rules for
> benchmarking. The estimates above are extrapolations. Contributions welcome.

---

## 3. Competitor Comparison Table

### 3.1 Performance

| Metric | ACGS (Rust) | ACGS (Python) | Guardrails AI | NeMo Guardrails | OPA (Rego) | LlamaGuard |
|--------|-------------|---------------|---------------|-----------------|------------|------------|
| **P50 latency** | ~560ns **(measured)** | ~3-10us **(estimated)** | ~5-50ms **(estimated)** | ~10-100ms **(estimated)** | ~0.1-5ms **(published)** | ~100-500ms **(estimated)** |
| **Throughput** | ~1.8M/s **(derived)** | ~100-300K/s **(estimated)** | ~20-200/s **(estimated)** | ~10-100/s **(estimated)** | ~200-10K/s **(published)** | ~2-10/s **(estimated)** |
| **Memory (engine)** | ~2-5MB **(estimated)** | ~5-15MB **(estimated)** | ~50-200MB **(estimated)** | ~500MB-2GB **(estimated)** | ~10-50MB **(published)** | ~2-8GB **(estimated)** |
| **Startup time** | ~1-5ms **(estimated)** | ~5-20ms **(estimated)** | ~100-500ms **(estimated)** | ~2-10s **(estimated)** | ~10-100ms **(published)** | ~10-30s **(estimated)** |
| **Requires GPU** | No | No | No | No (but NVIDIA-optimized) | No | Yes |

**Source notes:**

- **ACGS (Rust):** `make bench` on the default 6-rule constitution. The 560ns claim is for the allow path. Deny paths are 2-5x slower due to exception/violation construction.
- **ACGS (Python):** Not yet formally benchmarked without the Rust extension. Estimates based on typical Python/C-extension overhead ratios.
- **Guardrails AI:** Latency depends heavily on which validators are active. Simple regex validators are fast (~5ms). LLM-based validators (e.g., toxicity via OpenAI) add network round-trip time (50ms+). No official latency benchmarks published as of 2026-04.
- **NeMo Guardrails:** Uses NIM microservices that run LLM inference. Latency is dominated by model inference time. NVIDIA publishes throughput for NIM containers but not for the guardrails layer specifically.
- **OPA:** Well-benchmarked. The OPA team publishes [benchmark results](https://www.openpolicyagent.org/docs/latest/policy-performance/). Simple Rego policies evaluate in ~0.1ms; complex policies with large data sets can take 1-5ms. OPA's Go runtime is highly optimized.
- **LlamaGuard:** Runs model inference (LlamaGuard 3 is an 8B parameter model). Latency is GPU-dependent. On an A100, expect ~100-200ms per classification. CPU inference is impractical for production use.

### 3.2 Why This Comparison Is Unfair (Read This)

**ACGS and OPA are rule-based systems.** They evaluate deterministic rules against input text.
Low latency is expected because the operation is fundamentally string matching + regex.

**Guardrails AI, NeMo Guardrails, and LlamaGuard are (at least partially) LLM-based systems.**
They perform semantic understanding, content classification, or model inference. Comparing their
latency to a rule engine is like comparing a database index lookup to a full-text search -- the
operations are categorically different.

**What rule-based systems cannot do:**
- Detect novel attack patterns not covered by explicit rules
- Understand semantic intent (sarcasm, coded language, context-dependent meaning)
- Classify content quality or safety without pre-defined patterns
- Adapt to new threat categories without rule updates

**What LLM-based systems cannot do:**
- Provide deterministic, reproducible decisions
- Operate at sub-millisecond latency
- Run without GPU/API infrastructure
- Guarantee the same output for the same input across model versions

The right architecture for most production systems is **both**: ACGS for deterministic
governance rules (compliance, audit, MACI separation) with an LLM-based system for
content safety where semantic understanding is required.

---

## 4. Feature Comparison Matrix

| Feature | ACGS | Guardrails AI | NeMo Guardrails | OPA/Styra | LlamaGuard |
|---------|------|---------------|-----------------|-----------|------------|
| **Regulatory frameworks** | 9 (EU AI Act, GDPR, SOX, HIPAA, PCI-DSS, NIST AI RMF, ISO 42001, FDA 21 CFR, CCPA) | None (PII/toxicity validators, no regulatory mapping) | None | None (general policy) | None |
| **EU AI Act coverage** | Articles 12, 13, 14 with structured output | No | No | No | No |
| **Audit trail** | Cryptographic chain (tamper-evident, hash-linked) | Basic logging | Basic logging | Decision logs | None |
| **Constitutional hash** | Yes (`608508a9bd224290`) -- tamper-evident rule versioning | No | No | No | No |
| **MACI separation** | Yes (Proposer/Validator/Executor roles enforced) | No | No | No | No |
| **Formal verification** | Rule dependency DAG + hash verification | No | No | Partial (Rego type checking) | No |
| **Role separation enforcement** | MACI: agents cannot validate own output | No | No | RBAC (different mechanism) | No |
| **Semantic content safety** | Keyword + regex only | LLM-based validators (50+) | LLM-based NIM microservices | N/A | Model-based classification |
| **License** | AGPL-3.0-or-later + commercial | Apache-2.0 | Apache-2.0 | Apache-2.0 | Llama Community License |
| **Python SDK** | Yes (pip install acgs-lite) | Yes (pip install guardrails-ai) | Yes (pip install nemoguardrails) | Yes (via REST API) | Yes (via transformers) |
| **Rust acceleration** | Yes (PyO3 native extension) | No | No (CUDA/TensorRT) | Go native | No (PyTorch) |
| **Offline/airgapped** | Yes (no network required) | Partial (some validators need API keys) | No (NIM requires network) | Yes | Yes (if model is local) |
| **Platform integrations** | 13 | 50+ validators | NVIDIA stack | Kubernetes-native | Llama ecosystem |
| **Team size** | 1 | ~10 | NVIDIA team | ~100 (Styra) | Meta AI team |
| **Funding** | Bootstrapped | $7.5M seed | NVIDIA-backed | $64M total (Styra) | Meta-backed |

### Where Competitors Are Stronger

This section exists because intellectual honesty matters more than marketing.

| Area | Who Wins | Why |
|------|----------|-----|
| **Semantic safety** | Guardrails AI, NeMo, LlamaGuard | LLM-based understanding catches things regex cannot (coded language, sarcasm, novel attacks) |
| **Community size** | Guardrails AI, OPA | Guardrails has 50+ community validators and active Discord. OPA is CNCF-graduated with massive Kubernetes adoption. |
| **Enterprise support** | OPA/Styra, NeMo | Styra has enterprise sales teams. NVIDIA bundles NeMo with AI Enterprise support contracts. |
| **Content filtering breadth** | Guardrails AI | 50+ validators covering PII, toxicity, hallucination, bias, etc. ACGS has keyword/regex only. |
| **Ecosystem lock-in** | LlamaGuard | Free, deeply integrated with Llama ecosystem. Zero marginal cost for Llama users. |
| **General-purpose policy** | OPA | Rego is a full policy language. ACGS is AI-governance specific. OPA can do anything. |
| **Marketing and awareness** | Everyone else | ACGS is a one-person bootstrapped project. Recognition is near zero outside this repo. |

---

## 5. How to Run

### 5.1 ACGS Benchmarks

```bash
# Prerequisites
git clone https://github.com/<org>/acgs-clean.git
cd acgs-clean
pip install -e packages/acgs-lite[dev]

# Optional: Install Rust acceleration
cd packages/acgs-lite/rust
maturin develop --release
cd ../../..

# Run benchmark suite
make bench

# Run with JSON output for CI tracking
python -m pytest packages/acgs-lite/tests/test_benchmark_engine.py \
    -m benchmark -v --import-mode=importlib \
    --benchmark-json=benchmark-results.json

# Run without Rust to measure Python-only path
pip uninstall acgs_lite_rust -y
make bench
```

### 5.2 Verifying Rust vs Python Path

```python
from acgs_lite.engine.rust import _HAS_RUST
print(f"Rust acceleration: {_HAS_RUST}")

from acgs_lite.constitution import Constitution
from acgs_lite.engine import GovernanceEngine

engine = GovernanceEngine(Constitution.default(), strict=False)
print(f"Rust validator: {engine._rust_validator is not None}")
```

### 5.3 Memoization Benchmarks

```python
import time
from acgs_lite.constitution import Constitution
from acgs_lite.constitution.memoization import MemoizedConstitution

c = Constitution.default()
mc = MemoizedConstitution(c, maxsize=1024)

# Warm the cache
mc.validate("check compliance status")

# Benchmark cache hits
N = 100_000
start = time.perf_counter_ns()
for _ in range(N):
    mc.validate("check compliance status")
elapsed_ns = time.perf_counter_ns() - start

print(f"Cache hit latency: {elapsed_ns / N:.0f}ns per call")
print(f"Throughput: {N / (elapsed_ns / 1e9):,.0f} lookups/sec")
print(f"Stats: {mc.cache_stats()}")
```

### 5.4 Custom Rule Count Benchmarks

```python
import time
from acgs_lite.constitution import Constitution, Rule, Severity
from acgs_lite.engine import GovernanceEngine

def make_constitution(n_rules: int) -> Constitution:
    """Generate a synthetic constitution with n_rules rules."""
    rules = [
        Rule(
            id=f"BENCH-{i:04d}",
            text=f"Benchmark rule {i} for performance testing",
            severity=Severity.MEDIUM,
            keywords=[f"benchword{i}", f"testterm{i}"],
            category="benchmark",
        )
        for i in range(n_rules)
    ]
    return Constitution(name="benchmark", rules=rules)

for n in [6, 10, 25, 50, 63]:
    c = make_constitution(n)
    engine = GovernanceEngine(c, strict=False)
    action = "review quarterly compliance dashboard and prepare audit summary"

    # Warm-up
    for _ in range(100):
        engine.validate(action, agent_id="bench")

    # Measure
    N = 10_000
    start = time.perf_counter_ns()
    for _ in range(N):
        engine.validate(action, agent_id="bench")
    elapsed_ns = time.perf_counter_ns() - start

    print(f"{n:>4} rules: P50 ~{elapsed_ns / N:.0f}ns, throughput ~{N / (elapsed_ns / 1e9):,.0f}/s")
```

> **Note:** The Rust hot path has a hard limit of 63 rules (u64 bitmask). Constitutions with
> 64+ rules will fall back to the Python path. The synthetic benchmark above does not test
> deny paths -- add violating keywords to the action string for deny-path benchmarks.

---

## 6. Caveats and Honest Limitations

### 6.1 What Our Benchmarks Do Not Measure

- **Semantic safety quality:** ACGS uses keyword + regex matching. It cannot detect novel or
  semantically complex unsafe content that falls outside predefined patterns. LLM-based systems
  (Guardrails AI, NeMo, LlamaGuard) are fundamentally better at this.
- **Content filtering accuracy:** We have no F1/precision/recall measurements for ACGS rule
  matching against standard safety benchmarks (ToxiGen, RealToxicityPrompts, etc.). This is
  because ACGS rules are governance-focused (compliance, audit, MACI), not content-safety focused.
- **Multi-model orchestration overhead:** In real deployments, ACGS sits in an agent pipeline.
  The end-to-end overhead includes network hops, serialization, and other middleware -- not just
  the validation call itself.
- **Cold-start latency under load:** We benchmark warm-path latency. In serverless or
  auto-scaling environments, cold-start (engine construction + Rust module loading) matters and
  is not captured in our P50/P99 numbers.

### 6.2 Apples-to-Oranges Disclaimers

| Comparison | Why it is misleading |
|------------|---------------------|
| ACGS vs LlamaGuard latency | LlamaGuard runs an 8B parameter model. Comparing its inference time to string matching is meaningless. They solve different problems. |
| ACGS vs NeMo Guardrails throughput | NeMo uses GPU-accelerated NIM microservices. ACGS uses CPU-only rule evaluation. Different resource profiles, different cost curves. |
| ACGS vs OPA latency | Closest valid comparison. Both are deterministic rule engines. But OPA's Rego is a full policy language with partial evaluation, data binding, and module imports. ACGS rules are simpler (keyword + regex + severity). |
| ACGS vs Guardrails AI latency | Depends entirely on which Guardrails validators are active. A regex-only Guardrails pipeline is comparable to ACGS. An LLM-validator pipeline is 1000x slower but does something ACGS cannot. |

### 6.3 Where ACGS Is Likely Slower or Worse

- **Large rule sets (64+ rules):** The Rust bitmask path tops out at 63 rules. Organizations
  with hundreds of policy rules will hit the Python fallback path, erasing the Rust advantage.
- **Dynamic rule evaluation:** ACGS evaluates all active rules on every call. OPA's partial
  evaluation can skip irrelevant rules based on input structure, which may be faster for large
  policy sets with sparse matching.
- **Network-distributed validation:** ACGS is an in-process library. If you need a centralized
  policy service (like Styra DAS or NVIDIA NIM), you need to wrap ACGS in an API server yourself.
  OPA and NeMo provide this out of the box.
- **Content safety coverage:** ACGS has 6 default rules and 5 per-domain template. Guardrails AI
  has 50+ community validators. For content safety (not governance compliance), Guardrails AI
  covers more ground with less configuration effort.

### 6.4 Data Source Transparency

| Competitor | Data Source | Confidence |
|------------|------------|------------|
| **Guardrails AI** | Architecture analysis (Python validators, optional LLM calls). No official benchmarks published. Revenue estimate ($1.1M) from third-party sources. | Low -- estimated from architecture |
| **NeMo Guardrails** | NVIDIA NIM documentation and blog posts. Latency dominated by model inference. No guardrails-specific benchmarks published. | Low -- estimated from NIM specs |
| **OPA/Styra** | OPA publishes [official benchmarks](https://www.openpolicyagent.org/docs/latest/policy-performance/). Rego evaluation is well-characterized. Styra DAS adds network overhead. | High -- published by project |
| **LlamaGuard** | Meta's model cards and community benchmarks. Latency depends on GPU, batch size, and quantization. | Medium -- published model specs, variable hardware |

### 6.5 Rust Path Limitations

- Maximum 63 rules per constitution (u64 bitmask)
- Maximum 63 anchor dispatch entries (u64 bitmask)
- PyO3 abi3 stable ABI: compatible with Python 3.8+ but does not use version-specific optimizations
- Regex patterns are re-compiled on engine construction (not cached across engines)
- Context field validation (`validate_full`) requires additional Aho-Corasick scans per context value

---

## 7. Reproducing Competitor Numbers

We do not publish benchmark code for competitor products because:

1. **License compliance:** Running competitors' code in our benchmark suite could create
   licensing complications.
2. **Fairness:** Default configurations may not represent best-case performance. Each product
   has optimization knobs we may not be aware of.
3. **Maintenance:** Competitor APIs change. Stale benchmarks are worse than no benchmarks.

If you want to verify competitor performance claims yourself:

```bash
# Guardrails AI
pip install guardrails-ai
# See: https://docs.guardrailsai.com/

# NeMo Guardrails
pip install nemoguardrails
# See: https://docs.nvidia.com/nemo/guardrails/

# OPA
# Download binary from https://www.openpolicyagent.org/docs/latest/#running-opa
# See benchmarks: https://www.openpolicyagent.org/docs/latest/policy-performance/

# LlamaGuard
pip install transformers torch
# See: https://huggingface.co/meta-llama/Llama-Guard-3-8B
```

---

## 8. Contributing

To improve these benchmarks:

1. **Run on your hardware** and submit results via PR with your CPU model, OS, and Python version.
2. **Add rule-count scaling tests** with synthetic constitutions at 10, 25, 50, 63, 100, and 500 rules.
3. **Add deny-path benchmarks** that measure exception construction overhead.
4. **Add context-validation benchmarks** that test `validate_full` with governance context fields.
5. **Independently benchmark competitors** and submit results with methodology documentation.

All contributed benchmarks must include:
- Hardware specs (CPU model, RAM, GPU if applicable)
- Software versions (Python, Rust toolchain, OS, kernel)
- Exact commands to reproduce
- Raw data (JSON or CSV) alongside summary statistics
