# Autoresearch Agent Guide

> Scope: `autoresearch/` — benchmark optimization harness for governance behavior.

## Files

- `program.md`: experiment discipline and decision rules
- `benchmark.py`: benchmark runner
- `setup_run.py`: run setup
- `log_run.py`: append-only run logging
- `results_utils.py`: results parsing/comparison
- `governance_quality_benchmark.py`: governance-specific benchmark logic
- `constitution.yaml`: benchmark constitution
- `results.tsv`: append-only results log
- `scenarios/`: benchmark scenarios

## Workflow

1. Read `program.md`.
2. Change one variable.
3. Run the benchmark.
4. Compare against prior results.
5. Keep or revert based on measured outcome.
6. Append the result to `results.tsv`.

## Conventions

- Treat `results.tsv` as append-only.
- Keep experiments isolated and attributable.
- Use the scenario files instead of embedding scenario data in code.

## Anti-Patterns

- Do not rewrite or delete prior benchmark rows.
- Do not run multiple overlapping experiments against the same result log.
