# Governance Pipeline Visualization — System Design

**Date:** 2026-03-19 | **Status:** Proposed | **Constitutional Hash:** 608508a9bd224290

## 1. Overview

Add an interactive, real-time governance pipeline visualization to the existing `propriety-ai` dashboard. Users see the 4-stage governance pipeline as a live flow diagram with per-stage latency sparklines, throughput gauges, and drill-down panels — all fed by SSE streaming and existing capacity metrics.

### Design Goals
- **Easy to use**: Zero-config, auto-connects to existing SSE endpoint, works with demo fallback
- **Visualize**: Interactive pipeline flow (React Flow) + time-series charts (Recharts)
- **Optimization**: Surface bottlenecks, highlight SLA breaches, show scaling recommendations

### Non-Goals
- No new backend services (uses existing API endpoints)
- No database changes
- No authentication changes

---

## 2. Architecture

### 2.1 Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│  Backend (existing, no changes needed for MVP)                  │
│                                                                 │
│  GET /api/v1/governance/events  ──SSE──►  GovernanceFeed (exists)│
│  GET /api/v1/governance/status  ──JSON──► ComplianceCards (exists)│
│  GET /api/v1/health/dashboard   ──JSON──► HealthPanel (exists)  │
│                                                                 │
│  NEW: GET /api/v1/pipeline/metrics ──JSON──► PipelineViz (new)  │
│        Returns CapacitySnapshot + per-layer TimeoutBudget data  │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│  Frontend (propriety-ai)                                        │
│                                                                 │
│  /dashboard (existing page, add new tab)                        │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  Tab: "Overview" (current dashboard)                        ││
│  │  Tab: "Pipeline" (NEW — pipeline visualization)             ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                 │
│  Pipeline Tab Layout:                                           │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  [KPI Bar] — Total RPS | P99 Latency | SLA Status | Uptime ││
│  ├─────────────────────────────────────────────────────────────┤│
│  │  [Pipeline Flow] — React Flow: 4 stages with animated edges ││
│  │   MACI → Tenant → Impact → Constitutional                  ││
│  │   Each node shows: name, P99, throughput, status indicator  ││
│  ├─────────────────────────────────────────────────────────────┤│
│  │  [Detail Panel] — Click a stage to see:                     ││
│  │   • Latency chart (P50/P95/P99 over time)                  ││
│  │   • Throughput chart (RPS over time)                        ││
│  │   • Recent violations for this stage                        ││
│  │   • Timeout budget remaining                                ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 New Dependencies (Frontend Only)

| Package | Version | Size | Purpose |
|---------|---------|------|---------|
| `recharts` | ^2.15 | ~180KB | Area/line/bar charts for latency + throughput |
| `@xyflow/react` | ^12 | ~120KB | Interactive pipeline flow diagram |
| `@dagrejs/dagre` | ^1 | ~30KB | Auto-layout for React Flow nodes |

Total addition: ~330KB (pre-gzip), ~90KB gzipped.

### 2.3 New Backend Endpoint

One new endpoint aggregates existing metrics into a pipeline-friendly shape:

```
GET /api/v1/pipeline/metrics
```

**Response Schema:**
```typescript
interface PipelineMetricsResponse {
  timestamp: string                    // ISO8601
  constitutional_hash: string          // "608508a9bd224290"
  total_sla_ms: number                 // 50.0 (from TimeoutBudgetManager)
  total_elapsed_ms: number             // current total elapsed
  sla_status: "healthy" | "warning" | "critical"

  stages: PipelineStage[]             // 4 stages in order

  throughput: {
    current_rps: number
    peak_rps: number
    avg_rps: number
    total_requests: number
  }

  scaling_recommendation: {
    direction: "scale_up" | "scale_down" | "maintain"
    urgency: "immediate" | "soon" | "none"
    reasons: string[]
  }
}

interface PipelineStage {
  id: string                           // "layer1_validation", etc.
  name: string                         // "MACI Enforcement", etc.
  order: number                        // 1-4
  budget_ms: number                    // allocated timeout

  latency: {
    p50_ms: number
    p95_ms: number
    p99_ms: number
    avg_ms: number
    sample_count: number
  }

  status: "healthy" | "warning" | "critical"
  sla_compliant: boolean

  recent_violations: number            // violations in last 5 min
  total_processed: number              // total items through this stage
}
```

**Implementation**: New route file `src/core/services/api_gateway/routes/pipeline_metrics.py` that reads from `TimeoutBudgetManager.get_budget_report()` and `EnhancedAgentBusCapacityMetrics.get_capacity_snapshot()`. Falls back to demo data when services are offline (same pattern as existing endpoints).

---

## 3. Component Design

### 3.1 File Structure (New Files)

```
propriety-ai/
├── components/
│   └── dashboard/
│       ├── pipeline-viz.tsx          # Main pipeline visualization container
│       ├── pipeline-flow.tsx         # React Flow pipeline diagram
│       ├── pipeline-kpi-bar.tsx      # Top KPI summary bar
│       ├── stage-detail-panel.tsx    # Drill-down panel for selected stage
│       └── latency-chart.tsx         # Recharts latency time-series
├── lib/
│   └── api-client.ts                # Add: fetchPipelineMetrics()
│   └── use-pipeline-metrics.ts      # Custom hook: polling + state
└── src/pages/
    └── Dashboard.tsx                 # Modify: add Pipeline tab
```

### 3.2 Component Specifications

#### `PipelineViz` (Container)
- Props: none (self-contained)
- Fetches metrics via `usePipelineMetrics()` hook (10s poll interval)
- Manages `selectedStage` state
- Renders: `PipelineKpiBar` + `PipelineFlow` + `StageDetailPanel`
- Demo fallback: generates realistic fake metrics matching the 4-layer budget

#### `PipelineKpiBar` (Summary)
- Props: `metrics: PipelineMetricsResponse`
- 4 KPI cards in a row:
  - **Total RPS**: current_rps with sparkline trend
  - **P99 Latency**: total P99 with SLA indicator (green < 5ms, yellow < 10ms, red > 10ms)
  - **SLA Status**: badge showing healthy/warning/critical
  - **Scaling**: recommendation badge with urgency color
- Uses existing Tailwind `glass` utility for card backgrounds
- Framer Motion entrance animation (consistent with existing dashboard)

#### `PipelineFlow` (React Flow Diagram)
- Props: `stages: PipelineStage[]`, `onStageSelect: (id: string) => void`
- 4 custom nodes laid out left-to-right via dagre
- Each node renders:
  - Stage name (bold)
  - Status dot (green/yellow/red)
  - P99 latency value
  - Throughput (items/s)
  - Mini progress bar showing budget usage (elapsed / budget)
- Animated edges between nodes showing data flow direction
- Selected node gets a glowing border (using existing `neon-glow` utility)
- Node dimensions: 200x120px
- Edge type: smoothstep with animated dash pattern

**Node Color Mapping:**
```
healthy  → border-governance (neon green)
warning  → border-warning (amber)
critical → border-destructive (red)
```

#### `StageDetailPanel` (Drill-Down)
- Props: `stage: PipelineStage`, `history: PipelineStage[]` (last N snapshots)
- Renders below the flow diagram when a stage is selected
- Contains 2 charts side-by-side (lg:grid-cols-2):
  - **Latency Chart**: Recharts AreaChart showing P50/P95/P99 over time
  - **Budget Chart**: Recharts BarChart showing elapsed vs budget with threshold line
- Below charts: recent violations list (if any)
- Close button to deselect
- Glass card with entrance animation

#### `LatencyChart` (Recharts Component)
- Props: `data: {time: string, p50: number, p95: number, p99: number}[]`, `budgetMs: number`
- Recharts `AreaChart` with:
  - 3 stacked areas (P50 solid, P95 semi-transparent, P99 line only)
  - ReferenceLine at `budgetMs` (red dashed)
  - Tooltip showing exact values
  - Responsive container
- Color palette uses existing theme tokens:
  - P50: `oklch(0.88 0.20 155)` (governance green)
  - P95: `oklch(0.78 0.14 75)` (warning amber)
  - P99: `oklch(0.60 0.20 25)` (destructive red)

### 3.3 Dashboard Tab Integration

Modify `Dashboard.tsx` to add a tabbed interface:

```tsx
<Tabs defaultValue="overview">
  <TabsList>
    <TabsTrigger value="overview">Overview</TabsTrigger>
    <TabsTrigger value="pipeline">Pipeline</TabsTrigger>
  </TabsList>
  <TabsContent value="overview">
    {/* existing: HealthPanel, ComplianceCards, GovernanceFeed, AuditTrail */}
  </TabsContent>
  <TabsContent value="pipeline">
    <PipelineViz />
  </TabsContent>
</Tabs>
```

Uses existing Radix `@radix-ui/react-tabs` (already installed).

---

## 4. Custom Hook: `usePipelineMetrics`

```typescript
interface UsePipelineMetricsReturn {
  metrics: PipelineMetricsResponse | null
  history: PipelineMetricsResponse[]    // last 60 snapshots (10min at 10s interval)
  isLoading: boolean
  error: string | null
  isDemo: boolean                       // true when using fallback data
}

function usePipelineMetrics(pollIntervalMs: number = 10_000): UsePipelineMetricsReturn
```

- Polls `fetchPipelineMetrics()` every `pollIntervalMs`
- Maintains rolling history buffer (max 60 entries = 10 minutes)
- Falls back to demo data generator after 2s timeout (same pattern as `GovernanceFeed`)
- Cleans up interval on unmount

---

## 5. Demo Data Generator

For offline/development mode, generates realistic metrics that match the 4-layer timeout budget:

```typescript
function generateDemoMetrics(): PipelineMetricsResponse {
  return {
    timestamp: new Date().toISOString(),
    constitutional_hash: CONSTITUTIONAL_HASH,
    total_sla_ms: 50.0,
    total_elapsed_ms: randomBetween(8, 45),
    sla_status: "healthy",
    stages: [
      {
        id: "layer1_validation",
        name: "MACI Enforcement",
        order: 1,
        budget_ms: 5.0,
        latency: { p50_ms: 0.08, p95_ms: 0.09, p99_ms: 0.103, avg_ms: 0.085, sample_count: 15423 },
        status: "healthy",
        sla_compliant: true,
        recent_violations: 37,
        total_processed: 15423
      },
      {
        id: "layer2_deliberation",
        name: "Tenant Validation",
        order: 2,
        budget_ms: 20.0,
        latency: { p50_ms: 1.2, p95_ms: 2.1, p99_ms: 3.8, avg_ms: 1.5, sample_count: 15386 },
        status: "healthy",
        sla_compliant: true,
        recent_violations: 0,
        total_processed: 15386
      },
      {
        id: "layer3_policy",
        name: "Impact Analysis",
        order: 3,
        budget_ms: 10.0,
        latency: { p50_ms: 0.5, p95_ms: 1.8, p99_ms: 4.2, avg_ms: 0.9, sample_count: 15380 },
        status: "healthy",
        sla_compliant: true,
        recent_violations: 6,
        total_processed: 15380
      },
      {
        id: "layer4_audit",
        name: "Constitutional Check",
        order: 4,
        budget_ms: 15.0,
        latency: { p50_ms: 3.1, p95_ms: 8.5, p99_ms: 12.3, avg_ms: 4.2, sample_count: 15371 },
        status: "warning",
        sla_compliant: true,
        recent_violations: 9,
        total_processed: 15371
      }
    ],
    throughput: { current_rps: 5066, peak_rps: 7200, avg_rps: 4800, total_requests: 61560 },
    scaling_recommendation: { direction: "maintain", urgency: "none", reasons: [] }
  }
}
```

Adds random jitter (+-15%) on each poll to simulate real variance.

---

## 6. Styling & Theme Integration

All new components use the existing theme tokens from `globals.css`:

| Token | Usage |
|-------|-------|
| `--color-governance` | Healthy status, P50 latency line |
| `--color-warning` | Warning status, P95 latency line |
| `--color-destructive` | Critical status, P99 latency line, SLA breach |
| `glass` utility | Card backgrounds |
| `neon-glow` utility | Selected node highlight |
| `chart-gradient` utility | Chart area fills |
| JetBrains Mono | Numeric values (latency, RPS) |
| DM Sans | Labels, titles |

React Flow nodes use `glass-edge` background for the dark glassmorphic look consistent with the rest of the dashboard.

---

## 7. Responsive Behavior

| Breakpoint | Layout |
|-----------|--------|
| Mobile (<640px) | KPI: 2x2 grid, Flow: vertical (top-to-bottom), Detail: stacked charts |
| Tablet (640-1024px) | KPI: 4-col, Flow: horizontal, Detail: stacked charts |
| Desktop (>1024px) | KPI: 4-col, Flow: horizontal, Detail: side-by-side charts |

React Flow uses `fitView` to auto-scale. Dagre layout direction switches from `LR` (desktop) to `TB` (mobile) based on container width.

---

## 8. Implementation Plan

| Phase | Files | Effort |
|-------|-------|--------|
| **1. Dependencies** | `package.json` | 5 min |
| **2. API Client** | `lib/api-client.ts`, `lib/use-pipeline-metrics.ts` | 30 min |
| **3. Backend Endpoint** | `routes/pipeline_metrics.py`, `main.py` | 45 min |
| **4. KPI Bar** | `components/dashboard/pipeline-kpi-bar.tsx` | 30 min |
| **5. Pipeline Flow** | `components/dashboard/pipeline-flow.tsx` | 60 min |
| **6. Detail Panel** | `components/dashboard/stage-detail-panel.tsx`, `latency-chart.tsx` | 45 min |
| **7. Container + Tab** | `pipeline-viz.tsx`, modify `Dashboard.tsx` | 30 min |
| **8. Polish** | Animations, responsive, demo data jitter | 30 min |

**Total estimated: ~4.5 hours**

### Implementation Order
1. Install deps + create API types
2. Build backend endpoint (or wire demo data first)
3. Build bottom-up: LatencyChart → StageDetailPanel → PipelineFlow → PipelineKpiBar → PipelineViz
4. Wire into Dashboard.tsx with tabs
5. Test responsive behavior
6. Add demo data fallback

---

## 9. Success Criteria

- [ ] Pipeline tab loads in < 200ms (no layout shift)
- [ ] Metrics poll every 10s without memory leak
- [ ] Demo mode activates after 2s timeout (no blank screen)
- [ ] All 4 stages render with correct data from existing metrics
- [ ] Clicking a stage shows detail panel with latency history
- [ ] SLA breach (P99 > budget) shows red indicator + warning
- [ ] Responsive layout works at 375px (mobile) through 1920px (desktop)
- [ ] No new lint warnings (`make lint` passes)
- [ ] Existing dashboard tests unaffected
- [ ] Bundle size increase < 150KB gzipped

---

## 10. Future Extensions (Not In Scope)

- WebSocket upgrade for sub-second updates
- MACI role graph visualization (separate feature)
- Deliberation phase Sankey diagram
- Historical playback (scrub timeline)
- Alert configuration UI
- Export metrics to CSV/PDF
