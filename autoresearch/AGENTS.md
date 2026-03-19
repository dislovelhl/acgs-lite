# Autoresearch Agent Guide

Use this directory for benchmark optimization work driven by `autoresearch/program.md`.

## Purpose / Big Picture

- Keep experiment loops small, reproducible, and easy to compare against prior runs.
- Treat `program.md` and `results.tsv` as the primary working artifacts.

## Progress

- Current focus: keep the benchmark loop documented and reproducible.
- Track the next experiment, the expected change, and the observed result.

## Decision Log

- Prefer the smallest change that can be validated by the benchmark loop.
- Revert or annotate experiments that do not improve the target metric.

## Outcomes & Retrospective

- Record what changed, what improved, and what regressed after each run.
- Note any new failure mode or setup issue so the next run starts faster.
