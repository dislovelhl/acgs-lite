# ACGS Dashboard

React + Vite governance dashboard for `acgs-lite` and the enhanced agent bus.

## Pages

| Route | Page | Description |
|---|---|---|
| `/` | Dashboard | System health overview, recent audit events, rule summary |
| `/rules` | Rules | Browse and search active constitutional rules |
| `/builder` | Rule Builder | Create and edit governance rules |
| `/playground` | Playground | Evaluate actions against the constitution interactively |
| `/audit` | Audit | Tamper-evident audit log viewer |
| `/graph` | Rule Graph | Inter-rule dependency visualization |

## Running locally

```bash
cd packages/acgs-dashboard
npm install
npm run dev        # dev server at http://localhost:5173
npm run build      # production build → dist/
```

The dashboard connects to the `acgs-lite` governance server and the API gateway:

```bash
# In a separate terminal:
uvicorn "acgs_lite.server:create_governance_app" --factory --host 0.0.0.0 --port 8000
```

Set these in `.env.local` when you need non-default targets:

```bash
VITE_ACGS_LITE_URL=http://localhost:8000
VITE_GATEWAY_URL=http://localhost:8000/api
```

Demo fallback is now explicit opt-in so backend/auth failures are not silently
presented as healthy demo data:

```bash
VITE_ENABLE_DEMO_FALLBACK=true
```

## Stack

- React + TypeScript
- Vite
- Tailwind CSS
- Recharts (audit/metric charts)
- React Router v6

## Status

Buildable and functional. Backend integration targets `acgs_lite.server` REST API
(`/validate`, `/stats`, `/governance/*`) plus API gateway routes under `/api/*`.
