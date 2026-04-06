# acgs-governance-proxy

Cloudflare Worker that sits in front of upstream AI APIs and applies ACGS constitutional
governance before requests leave the edge.

## What This Worker Does

The governance proxy has two jobs:

- enforce ACGS validation for OpenAI-compatible API requests
- proxy public site assets and selected media files for `acgs.ai`

The worker currently recognizes these governed API endpoints:

- `/v1/chat/completions`
- `/v1/responses`
- `/v1/embeddings`

It also exposes:

- `/health` for worker health checks
- `/webhook` for GitLab webhook handling
- `/admin/constitution` to upload a constitution
- `/admin/audit` to query audit rows
- `/admin/audit/compact` to compact orphaned audit rows

Unknown `/admin/*` paths return `404` after auth succeeds, rather than falling through into the
governance flow.

## Running Locally

```bash
cd workers/governance-proxy
npm install
npm run dev
```

Core scripts:

```bash
npm run dev
npm run deploy
npm run test
```

## Configuration

Main config lives in [wrangler.toml](wrangler.toml).

Important bindings and settings:

- `CONSTITUTIONS` KV namespace for stored constitutions
- `AUDIT_DB` D1 database for persisted audit records
- `CONSTITUTIONAL_HASH` and fail-closed runtime vars
- `CompiledWasm` rule for the validator WASM bundle
- production routes for `api.acgs.ai` and `acgs.ai/*`

`ADMIN_SECRET` is intentionally not committed. Set it with:

```bash
wrangler secret put ADMIN_SECRET
```

## Seeding a Constitution

Use the helper script to generate and upload a default constitution config:

```bash
./scripts/seed-constitution.sh http://localhost:8787
```

The script:

1. builds a constitution config from Python if you do not provide one
2. uploads it to `/admin/constitution`
3. hits `/health`
4. runs one allow-case and one deny-case smoke test

## Source Layout

| Path | Role |
| --- | --- |
| `src/index.ts` | Worker entry point and request pipeline |
| `src/router.ts` | Route matching and health response helpers |
| `src/types.ts` | Worker environment and request types |
| `scripts/seed-constitution.sh` | Local/dev constitution seeding helper |
| `wasm/` | Validator runtime bundle loaded by the worker |
| `dist/` | Built worker output assets |

## Related Docs

- [Repo docs index](../../docs/README.md)
- [Repo directory map](../../docs/repo-map.md)
- [Root README](../../README.md)
