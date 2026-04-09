# Lean Runtime Wrapper Example

Use this example when you want `acgs-lite` to validate Lean proofs inside a real Lean/Lake project.

## Files

- `lean-wrapper.sh` — minimal wrapper script for `ACGS_LEAN_CMD`

## Why use a wrapper?

`ACGS_LEAN_CMD` intentionally rejects shell pipelines/chaining for safety and predictability.
If your runtime setup needs extra shell logic, put it in an executable wrapper script and point
`ACGS_LEAN_CMD` at that script.

## Setup

```bash
chmod +x examples/lean_runtime/lean-wrapper.sh

export ACGS_LEAN_CMD="$(pwd)/examples/lean_runtime/lean-wrapper.sh"
export ACGS_LEAN_WORKDIR="/absolute/path/to/your/lean-project"

acgs lean-smoke
acgs lean-smoke --json
```

## Preferred alternative: exact JSON-array command

If you do not need any shell logic, prefer the exact command form:

```bash
export ACGS_LEAN_CMD='["lake", "env", "lean"]'
export ACGS_LEAN_WORKDIR="/absolute/path/to/your/lean-project"
acgs lean-smoke
```

## Optional CI integration

To enable the real-toolchain integration test:

```bash
export LEAN_INTEGRATION=1
export ACGS_LEAN_CMD='["lake", "env", "lean"]'
export ACGS_LEAN_WORKDIR="/absolute/path/to/your/lean-project"
pytest tests/test_lean_verify.py -q --import-mode=importlib -k real_toolchain
```
