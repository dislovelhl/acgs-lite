import { motion, AnimatePresence } from "framer-motion"
import { X, AlertTriangle, Clock, Target } from "lucide-react"
import { LatencyChart } from "./latency-chart"
import type { PipelineStage, PipelineMetrics } from "@/lib/pipeline-types"

interface Props {
  stage: PipelineStage | null
  history: PipelineMetrics[]
  onClose: () => void
}

function formatMs(ms: number): string {
  if (ms < 1) return `${(ms * 1000).toFixed(0)}us`
  return `${ms.toFixed(2)}ms`
}

export function StageDetailPanel({ stage, history, onClose }: Props) {
  if (!stage) return null

  const chartData = history.map((snapshot) => {
    const s = snapshot.stages.find((st) => st.id === stage.id)
    return {
      time: snapshot.timestamp,
      p50: s?.latency.p50_ms ?? 0,
      p95: s?.latency.p95_ms ?? 0,
      p99: s?.latency.p99_ms ?? 0,
    }
  })

  const budgetUsed = stage.latency.p99_ms / stage.budget_ms
  const budgetPct = Math.min(budgetUsed * 100, 100)
  const budgetColor =
    budgetUsed < 0.6
      ? "bg-governance"
      : budgetUsed < 0.85
        ? "bg-warning"
        : "bg-destructive"

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: 12, height: 0 }}
        animate={{ opacity: 1, y: 0, height: "auto" }}
        exit={{ opacity: 0, y: -8, height: 0 }}
        transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
        className="rounded-xl border border-border/40 glass-edge overflow-hidden"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-border/30">
          <div className="flex items-center gap-3">
            <span
              className={`w-2 h-2 rounded-full ${
                stage.status === "healthy"
                  ? "bg-governance"
                  : stage.status === "warning"
                    ? "bg-warning"
                    : "bg-destructive"
              }`}
            />
            <span className="font-mono text-sm text-foreground">
              {stage.name}
            </span>
            <span className="font-mono text-[10px] text-muted-foreground/40">
              Layer {stage.order}
            </span>
          </div>
          <button
            onClick={onClose}
            className="w-7 h-7 rounded-md flex items-center justify-center hover:bg-card/60 transition-colors"
            aria-label="Close details"
          >
            <X className="w-4 h-4 text-muted-foreground" />
          </button>
        </div>

        {/* Stats row */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 px-5 py-4">
          <div className="flex items-center gap-2">
            <Clock className="w-3.5 h-3.5 text-governance" />
            <div className="flex flex-col">
              <span className="font-mono text-[9px] text-muted-foreground/50 uppercase">P99 Latency</span>
              <span className="font-mono text-sm text-foreground">{formatMs(stage.latency.p99_ms)}</span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Target className="w-3.5 h-3.5 text-governance" />
            <div className="flex flex-col">
              <span className="font-mono text-[9px] text-muted-foreground/50 uppercase">Budget</span>
              <span className="font-mono text-sm text-foreground">{stage.budget_ms}ms</span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-3.5 h-3.5 text-warning" />
            <div className="flex flex-col">
              <span className="font-mono text-[9px] text-muted-foreground/50 uppercase">Violations (5m)</span>
              <span className="font-mono text-sm text-foreground">{stage.recent_violations}</span>
            </div>
          </div>
          <div className="flex flex-col">
            <span className="font-mono text-[9px] text-muted-foreground/50 uppercase">Processed</span>
            <span className="font-mono text-sm text-foreground">
              {stage.total_processed.toLocaleString()}
            </span>
          </div>
        </div>

        {/* Budget usage bar */}
        <div className="px-5 pb-4">
          <div className="flex items-center justify-between mb-1.5">
            <span className="font-mono text-[9px] text-muted-foreground/50 uppercase">
              Budget Usage (P99)
            </span>
            <span className="font-mono text-[10px] text-muted-foreground">
              {formatMs(stage.latency.p99_ms)} / {stage.budget_ms}ms ({budgetPct.toFixed(0)}%)
            </span>
          </div>
          <div className="h-1.5 rounded-full bg-card/80 overflow-hidden">
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${budgetPct}%` }}
              transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
              className={`h-full rounded-full ${budgetColor}`}
            />
          </div>
        </div>

        {/* Latency chart */}
        <div className="px-5 pb-5">
          <LatencyChart
            data={chartData}
            budgetMs={stage.budget_ms}
            title="Latency Trend"
          />
        </div>
      </motion.div>
    </AnimatePresence>
  )
}
