## EVAL: acgs-cli-observability-demo

### Capability Evals
1. `acgs observe --watch` streams repeated telemetry snapshots with bounded iteration support.
2. `acgs otel --otlp-endpoint ...` can export telemetry payloads to an OTLP/collector-compatible HTTP endpoint.
3. `acgs otel --bundle-dir ...` writes a portable telemetry bundle (OTel JSON + Prometheus + summary metadata).
4. A checked-in demo script exercises all five sidecars: lint, test, lifecycle, refusal, observability.

### Regression Evals
1. Existing CLI commands (`init`, `assess`, `report`, `eu-ai-act`, `lint`, `test`, `lifecycle`, `refusal`, `observe`, `otel`) still parse and run.
2. `packages/acgs-lite/tests/test_cli_governance.py` passes with `--import-mode=importlib`.
3. `packages/acgs-lite/tests/` passes with `--import-mode=importlib`.

### Deterministic Graders
```bash
python3 -m pytest packages/acgs-lite/tests/test_cli_governance.py --import-mode=importlib -q
python3 -m pytest packages/acgs-lite/tests/ --import-mode=importlib -q --tb=no
bash packages/acgs-lite/examples/demo_cli_sidecars.sh
```

### Success Criteria
- Capability evals pass.
- Regression evals pass.
- No unrelated files are staged or modified by the feature itself.
