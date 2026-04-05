# ACGS-2 Autoresearch: Governance Engine Optimization

Inspired by [karpathy/autoresearch](https://github.com/karpathy/autoresearch), but adapted to a fixed ACGS-2 benchmark harness.
The agent's job is to improve the governance engine methodically: modify the hot path, run the benchmark, keep only real improvements, and discard noise.

This is a bounded optimization loop, not a general feature queue. The loop exists to improve the
benchmarkable hot path under a fixed harness and fixed correctness bar.

## What This Repo Optimizes

The benchmark measures governance quality and speed for the `acgs-lite` engine on a fixed constitutional ruleset and scenario corpus.

Primary metric:
- `composite_score` — higher is better (v2: log-scale formula, see Composite v2 below)

Hard guardrails:
- `compliance_rate` must never regress intentionally
- `false_negative_rate` must never regress intentionally
- `false_positive_rate` must never regress intentionally

Tie-breakers when `composite_score` is close (within 0.005 tie band):
- lower `p99_latency_ms`
- tighter `tail_ratio` (p99/p50)
- higher `throughput_rps`
- simpler code
- changes isolated to the actual hot path

Method priorities, in order:
1. baseline discipline
2. hypothesis quality
3. logging and keep/discard discipline
4. ablation quality
5. hot-path implementation changes

The loop has two scopes:
- `hot-path` — benchmark-facing engine work that may legitimately improve the benchmark
- `sidecar` — useful governance features with zero hot-path overhead

Hot-path optimization is the default mission. Sidecar work is allowed only when the human explicitly
asks for it or when the benchmark loop is intentionally paused. Do not let sidecar rows steer
hot-path keep/discard decisions.

## Fixed Harness

Treat these as read-only unless the human explicitly says to redefine the benchmark:

- `autoresearch/benchmark.py` — benchmark harness and scoring
- `autoresearch/constitution.yaml` — benchmark constitution
- `autoresearch/scenarios/` — scenario corpus
- benchmark scoring formula, assertions, and output format

Do not modify the benchmark to make results look better.

If you discover better real-world or sourced scenarios during research, keep them outside
`autoresearch/scenarios/` first, add tests for them, and promote them into the frozen corpus only
when the human explicitly approves a benchmark redefinition. Candidate packs should carry dataset
provenance, domain, use-case, and expected decision metadata so future promotion is auditable.

## High-Leverage Files

Read these first and focus here unless you have evidence another file is hotter:

- `packages/acgs-lite/src/acgs_lite/engine/core.py` — main validation hot path
- `packages/acgs-lite/src/acgs_lite/matcher.py` — keyword/pattern matching fast paths
- `packages/acgs-lite/src/acgs_lite/constitution/core.py` — rule representation and precomputation
- `packages/acgs-lite/src/acgs_lite/constitution/analytics.py` — intent/signal helpers used during matching
- `packages/acgs-lite/src/acgs_lite/engine/batch.py` — only if benchmark behavior points at batch-path overhead

Low-priority or usually out of scope for this benchmark:

- `packages/acgs-lite/src/acgs_lite/maci.py` — important for product scope, but not the main benchmark hot path
- `packages/acgs-lite/src/acgs_lite/audit.py` — do not touch unless you have benchmark evidence that the real path is using it
- broad repo files outside `packages/acgs-lite/src/acgs_lite/` — usually retrieval noise for this task

## Setup

1. Agree on a run tag such as `mar15`.
2. Create the branch and initialize the run with the helper:
   - `python3 autoresearch/setup_run.py --tag mar15`
3. Confirm the setup summary before editing code:
   - clean or intentionally dirty branch state
   - overall best benchmark row from `autoresearch/results.tsv`
   - best hot-path row from `autoresearch/results.tsv`
   - recent hot-path wins, recent sidecar wins, and recent discards so you do not retest the same family blindly
4. Read only the benchmark contract and hot-path files:
   - `autoresearch/benchmark.py`
   - `autoresearch/program.md`
   - `packages/acgs-lite/src/acgs_lite/engine/core.py`
   - `packages/acgs-lite/src/acgs_lite/matcher.py`
   - `packages/acgs-lite/src/acgs_lite/constitution/core.py`
   - `packages/acgs-lite/src/acgs_lite/constitution/analytics.py`
5. Inspect `autoresearch/results.tsv` only enough to understand the active hypothesis families and the current best comparable row.
6. Run the baseline before changing code:
   - `cd autoresearch && python3 benchmark.py > run.log 2>&1`
7. Parse the result:
   - `grep '^composite_score:\|^compliance_rate:\|^p99_latency_ms:\|^throughput_rps:\|^false_positive_rate:\|^false_negative_rate:' run.log`
8. Append the baseline or experiment row with the helper instead of hand-editing `results.tsv`.

Baseline discipline:
- A new hot-path branch starts by comparing against the best prior hot-path row, not the best sidecar row.
- If the benchmark is noisy, rerun the baseline once before trusting a marginal win or loss.
- If the worktree is intentionally dirty, treat the first run as a local baseline for that state before mutating code further.

## What You Can Modify

You may modify only code that plausibly changes benchmark behavior without redefining the benchmark:

- `packages/acgs-lite/src/acgs_lite/engine/core.py`
- `packages/acgs-lite/src/acgs_lite/matcher.py`
- `packages/acgs-lite/src/acgs_lite/constitution/core.py`
- `packages/acgs-lite/src/acgs_lite/constitution/analytics.py`
- closely adjacent engine files if the benchmark proves they are in the hot path

Treat `autoresearch/program.md`, `autoresearch/setup_run.py`, and `autoresearch/log_run.py` as
method files. Change them only to improve the loop discipline itself, not to make benchmark output
look better.

## What You Must Not Do

- Do not modify `autoresearch/benchmark.py`, `constitution.yaml`, or `scenarios/`.
- Do not add dependencies.
- Do not widen scope into unrelated packages.
- Do not accept a benchmark win that comes from lowered correctness.
- Do not accumulate losing commits on the branch.
- Do not use the autoresearch loop to land zero-hot-path feature work.
- Do not ask the human whether to continue once the loop is running.

## Output Format

The benchmark prints a fixed summary block like:

```text
---
compliance_rate:       1.000000
p50_latency_ms:       0.000670
p95_latency_ms:       0.002060
p99_latency_ms:       0.007860
mean_latency_ms:       0.000927
throughput_rps: 2650825.347083
false_positive_rate:       0.000000
false_negative_rate:       0.000000
composite_score:       0.838953
latency_score:       0.663571
throughput_score:       0.863056
tail_ratio:       4.076923
tail_score:       0.838091
correctness_score:       1.000000
rocs_norm:       0.828311
spec_to_artifact_score:       1.000000
rocs: 5056362.014435
rocs_governance_value:    2494.000000
rocs_compute_seconds:       0.000493
scenarios_tested:            532
correct:            532
errors:              0
rules_checked:             18
---
```

Primary decision fields:
- `composite_score` — primary, v2 log-scale formula
- `compliance_rate`
- `false_negative_rate`
- `false_positive_rate`
- `latency_score` — log₁₀(10/p99_ms) / log₁₀(100000), weight 0.25
- `throughput_score` — log₁₀(throughput) / log₁₀(10M), weight 0.20
- `tail_score` — 1 - (p99/p50 - 1) / 19, weight 0.20
- `tail_ratio` — p99/p50 (lower = more consistent)
- `p99_latency_ms`
- `throughput_rps`
- `errors`

## Composite v2 Formula

The v1 formula saturated after ~90 experiments: throughput was capped at 10K rps
(actual >1M), p99 headroom was 0.014%, and compliance/fn_rate were permanently maxed.

v2 uses log-scale metrics with meaningful gradient at µs performance:

```python
latency_score     = log₁₀(10 / p99_ms) / log₁₀(100_000)         # 0-1, log scale
throughput_score   = log₁₀(throughput) / log₁₀(10_000_000)        # 0-1, log scale
tail_score         = max(0, 1 - (p99/p50 - 1) / 19)               # 0-1, tighter=better
correctness        = compliance * (1 - fn_rate) * (1 - fp_rate)    # 0-1, multiplicative
rocs_norm          = log₁₀(rocs) / log₁₀(100_000_000)             # 0-1, log scale

composite = (
    correctness    * 0.15
    + latency_score  * 0.25
    + throughput_score * 0.20
    + tail_score       * 0.20
    + rocs_norm        * 0.10
    + (1 - fn_rate)    * 0.05
    + (1 - fp_rate)    * 0.05
)
```

Headroom at current performance: ~13% (vs 0.014% under v1).

Current best (11-trial median, exp278): composite=0.873, p99=2.45µs,
tput=1.66M rps, tail_ratio=2.4:1, allow_path=290ns, deny_path=905ns,
compliance=1.0, fn=0, fp=0.
Corpus: 3290 scenarios (expanded from 809). Noise: composite 0.91%, p99 12.2%.

Recent trajectory (post-corpus-expansion):
- exp272: stack-buffer lowercasing in Rust — FFI 185→168ns, noise reduction
- exp273: defer _rule_excs to deny/context — allow 329→304ns
- exp274: direct _count increment — allow 304→295ns
- exp275: _pooled_result in _hot[11] — neutral but cleaner
- exp278: pre-alloc exception reuse on deny-critical — deny 1200→905ns, tput +12%

Key insight: deny path (1200ns) was 4× slower than allow (300ns) due to exception
creation overhead. Pre-allocated exception re-raise with __traceback__=None
cut deny cost by 25% and boosted throughput 12%.

Improvement trajectory from v2 baseline (0.798):
- exp255/256: warmup cold-path priming → 0.856 (+0.058)
- exp259: gc.collect/freeze before warmup → 0.867 (+0.011)
- exp261: 8× warmup iterations → 0.869 (+0.002)
- exp264: deferred 11-tuple unpack → 0.868 (neutral, cleaner)
- exp265: Rust scan_hot() bitmask-only → 0.868 (neutral, architecturally correct)
- exp266: inline allow-path in validate() → 0.871 (+0.003)
- exp268: remove islower() guard → 0.870 (+0.002, throughput +19%)
- exp269: defer strict to slow paths → 0.869 (neutral, cleaner)

**Measurement floor reached**: p99 noise is 21% and composite noise is 1.3% at sub-3µs.
OS scheduling jitter dominates the latency_score dimension. Further improvements require:
1. Process isolation with CPU pinning (not feasible in library __init__)
2. Larger scenario corpus (more samples → more stable p99 percentile)
3. Architectural change: move entire validate() into Rust (eliminates Python dispatch)

Discarded experiments (instructive):
- exp257: _hot_fast(3) split — CPython inline cache neutral
- exp260: exception reuse — traceback chain caused 30% throughput regression
- exp262: action.lower() dict cache — throughput +21% but p99 +12% regression
- exp263: exception reuse v2 with __traceback__=None — p99 +5% regression

Remaining optimization axes:
- **Latency**: p99 2.84µs → 2.26µs needed for +0.005 composite (gated by noise)
- **Throughput**: 1.34M → 1.67M rps needed for +0.005 composite (approaching)
- **Tail**: ratio 2.5:1 → 2.0:1 needed for +0.005 composite (gated by noise)

Tie band widened to 0.005 (was 0.0005) to match the new formula's wider range.
Ceiling detection tight_band widened to 0.001 (was 0.0001).

## Logging Results

Log to `autoresearch/results.tsv` as tab-separated rows with this header:

```text
commit	composite	compliance	p99_ms	scope	status	description
```

Notes:
- `scope` is `hot-path` by default and separates benchmark-facing runs from sidecar work.
- Existing legacy rows without a `scope` column are inferred and upgraded by the helpers.

Status values:
- `baseline` — first comparable run for the branch or repo state
- `improved` — strictly better benchmark result that respects correctness guardrails
- `neutral-kept` — effectively tied benchmark result that is simpler or materially lowers `p99_ms`
- `discard` — completed run that did not earn promotion
- `crash` — exception, invalid output, or unusable benchmark run

Historical rows may still contain `reverted`; treat those as legacy `discard`.

Scope discipline:
- Use `python3 log_run.py ... --scope hot-path` for benchmark-facing engine work. This is the default.
- Use `python3 log_run.py ... --scope sidecar` only for explicitly out-of-loop governance features with zero hot-path overhead.
- Use `--scope any` only for historical forensics, not for promotion decisions.

Use short, hypothesis-oriented descriptions such as:
- `precompute active rule tuples`
- `skip negative-signal regex on clean allow path`
- `aho-corasick shared scanner`

Prefix descriptions with the hypothesis family when useful:
- `schedule: lower throughput sample variance`
- `matcher: aho-corasick shared scanner`
- `constitution: precompute active rule tuples`
- `method: tighter baseline tie-band`

## Keep / Discard Rules

Keep a change only if all of these hold:

1. `errors == 0`
2. `compliance_rate` does not regress
3. `false_negative_rate` does not regress
4. `false_positive_rate` does not regress
5. one of these is true:
   - `composite_score` improves clearly
   - `composite_score` is effectively tied and the code is simpler
   - `composite_score` is effectively tied and `p99_latency_ms` improves materially

Default decision policy:
- `improved`: composite beats the best comparable kept row
- `neutral-kept`: composite is within the tie band and either complexity drops or `p99_ms`
  improves enough to matter
- `discard`: completed run that fails the guardrails or adds complexity for negligible gain
- `crash`: no parseable summary, benchmark failure, or unusable output

Comparable row means:
- hot-path runs compare against prior kept hot-path rows
- sidecar runs compare against prior kept sidecar rows
- do not declare a hot-path change `improved` just because it beats an unrelated sidecar row

Complexity tax:
- Keep tiny gains only if the code is simpler or unlocks the next clear ablation.
- Discard tiny gains that add brittle machinery, extra caches, or hard-to-ablate coupling.
- Feature additions with zero hot-path impact are out of scope for this loop; land them elsewhere
  instead of labeling them wins here.

Discard changes that:
- improve one secondary metric while hurting correctness
- add complexity for negligible gain
- mix multiple unrelated ideas so the result is not interpretable
- broaden the surface into product features that the benchmark does not exercise

## Stable Measurement (run bench_stable.py near the ceiling)

When p99 variance between runs exceeds your target delta, single-run benchmarks
are unreliable. Use the multi-trial wrapper to get median metrics:

```bash
python3 autoresearch/bench_stable.py --trials 7
```

This runs the frozen harness 7 times and emits the **median** of each metric as
a standard `run.log`. The variance report tells you whether your improvement
signal is real or noise:

- `spread < target_delta` → signal is real, trust the result
- `spread >= target_delta` → noise dominates; more trials or architectural change needed

Use `bench_stable.py` output with `log_run.py` identically to a normal `run.log`.

## Ceiling Detection and Family Pivoting

A ceiling is declared when 5 consecutive runs in a scope show no `improved` result.
`setup_run.py` and `log_run.py` print a warning automatically.

Ceiling response protocol (in order):
1. **Verify with bench_stable.py** — run 7 trials to check variance. The ceiling
   may be noise, not a true local optimum.
2. **Pivot hypothesis family** — check `feature_grid.py` for unexplored families:
   ```bash
   python3 autoresearch/feature_grid.py
   ```
   The grid shows best composite per (family × scope). Unexplored families are
   labeled `(unexplored)`. Try the family with lowest best composite first.
3. **Architectural change** — if all families are explored and the ceiling holds
   across 7+ stable trials, the current architecture has reached its local optimum.
   This requires a structural change (new code path, different data structure,
   Rust kernel rewrite) rather than tuning.

Do not keep tuning the same family after a confirmed ceiling.

## Hypothesis Pre-Registration

Before each experiment, record three things internally:

```
Family:   <matcher | constitution | rust | warmup | engine | method>
Metric:   <composite | p99_ms | simplicity>
Discard:  <what outcome would falsify this hypothesis>
```

If you cannot state all three clearly, the experiment is not ready. Pre-registration
prevents HARKing (reinterpreting results post-hoc to match a different hypothesis).

## Experiment Method

Run disciplined ablations, not random edits. Each commit should test one hypothesis family.

Good experiment families:
- method and measurement discipline
- engine fast-path control flow
- matcher keyword/path selection
- constitution precomputation and rule representation
- avoid repeated attribute lookups and object allocation in `validate()`
- precompute rule state once at engine or rule construction time
- shorten allow-path execution
- reduce regex work on common clean inputs
- collapse duplicate scans into one pass
- replace Python bookkeeping with simpler immutable or slotted structures
- remove dead or duplicated work from the hot path

Avoid early on:
- semantic matching features
- large architecture rewrites
- product-surface additions not exercised by the benchmark
- changes to audit persistence unless proven hot in the benchmarked path

When a compound idea looks promising:
1. run the full idea once
2. remove one ingredient in the next run to find the real source of the gain

Before each run, write down internally:
1. hypothesis family
2. expected winning metric (`composite`, `p99_ms`, or simplicity at a tie)
3. what would count as a discard

If you cannot state those three points clearly, the experiment is not ready.

Crash taxonomy to log mentally before retrying:
- syntax or missing import
- shape mismatch
- OOM or allocation regression
- numerical or timing instability
- benchmark contract violation

Retry only trivial implementation mistakes. Log the rest and move on.

## The Loop

LOOP FOREVER:

1. Read current branch, current best result, and the last few winning experiments.
2. Pick one hypothesis family.
3. Make the smallest change that tests that hypothesis.
4. Commit the change.
5. Run the benchmark with redirected output:
   - `cd autoresearch && python3 benchmark.py > run.log 2>&1`
6. Parse the metrics.
7. If the run crashed or the summary block is missing, inspect:
   - `tail -n 50 run.log`
8. Append a row to `results.tsv` using the helper:
   - `python3 log_run.py run.log --commit "$(git rev-parse --short HEAD || echo uncommitted)" --description "short hypothesis"`
   - hot-path runs rely on the default comparable scope
   - sidecar runs must say `--scope sidecar`
   - do not hand-edit `results.tsv`; the helper will preserve or migrate the canonical header
9. Ask the helper for the shell-friendly recommendation when needed:
   - `python3 log_run.py run.log --recommend`
10. If the result is `improved` or `neutral-kept`, keep the commit and advance.
11. If the result is `discard` or `crash`, reset to the previous kept commit.
12. Continue immediately with the next hypothesis family.

If the last few kept rows are all sidecar work, explicitly pivot back to a hot-path family before making another benchmark-facing decision.

## Autonomy Rule

Once the experiment loop has started, do not stop to ask for permission to continue. Keep iterating until the human interrupts you.
