import { motion } from "framer-motion"
import { Gauge, Timer, ShieldCheck, TrendingUp } from "lucide-react"
import type { PipelineMetrics } from "@/lib/pipeline-types"

const STATUS_COLOR: Record<string, string> = {
  healthy: "text-governance bg-governance/15 border-governance/25",
  warning: "text-warning bg-warning/15 border-warning/25",
  critical: "text-destructive bg-destructive/15 border-destructive/25",
}

const URGENCY_COLOR: Record<string, string> = {
  none: "text-governance bg-governance/15 border-governance/25",
  soon: "text-warning bg-warning/15 border-warning/25",
  immediate: "text-destructive bg-destructive/15 border-destructive/25",
}

function formatRps(rps: number): string {
  if (rps >= 1000) return `${(rps / 1000).toFixed(1)}K`
  return rps.toFixed(0)
}

function formatLatency(ms: number): string {
  if (ms < 1) return `${(ms * 1000).toFixed(0)}us`
  if (ms < 100) return `${ms.toFixed(1)}ms`
  return `${ms.toFixed(0)}ms`
}

interface Props {
  metrics: PipelineMetrics
}

export function PipelineKpiBar({ metrics }: Props) {
  const totalP99 = metrics.stages.reduce(
    (max, s) => Math.max(max, s.latency.p99_ms),
    0,
  )

  const cards = [
    {
      label: "Throughput",
      value: `${formatRps(metrics.throughput.current_rps)} RPS`,
      sub: `Peak: ${formatRps(metrics.throughput.peak_rps)}`,
      icon: Gauge,
    },
    {
      label: "Max P99",
      value: formatLatency(totalP99),
      sub: `SLA: <${metrics.total_sla_ms}ms`,
      icon: Timer,
    },
    {
      label: "SLA Status",
      value: metrics.sla_status.charAt(0).toUpperCase() + metrics.sla_status.slice(1),
      sub: `${metrics.total_elapsed_ms.toFixed(1)}ms / ${metrics.total_sla_ms}ms`,
      icon: ShieldCheck,
      statusKey: metrics.sla_status,
    },
    {
      label: "Scaling",
      value: metrics.scaling_recommendation.direction === "maintain"
        ? "Stable"
        : metrics.scaling_recommendation.direction === "scale_up"
          ? "Scale Up"
          : "Scale Down",
      sub: metrics.scaling_recommendation.reasons[0] ?? "No action needed",
      icon: TrendingUp,
      urgencyKey: metrics.scaling_recommendation.urgency,
    },
  ]

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      {cards.map((card, i) => (
        <motion.div
          key={card.label}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, delay: i * 0.06 }}
          className="rounded-xl border border-border/40 glass-edge p-4 flex items-start gap-3"
        >
          <div
            className={`w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 ${
              card.statusKey
                ? STATUS_COLOR[card.statusKey]
                : card.urgencyKey
                  ? URGENCY_COLOR[card.urgencyKey]
                  : "bg-governance/15 border border-governance/25"
            }`}
          >
            <card.icon className="w-4 h-4" />
          </div>
          <div className="flex flex-col gap-0.5 min-w-0">
            <span className="font-mono text-[10px] tracking-[0.2em] text-muted-foreground/50 uppercase">
              {card.label}
            </span>
            <span className="font-mono text-lg font-medium text-foreground leading-tight">
              {card.value}
            </span>
            <span className="font-mono text-[10px] text-muted-foreground/60 truncate">
              {card.sub}
            </span>
          </div>
        </motion.div>
      ))}
    </div>
  )
}
