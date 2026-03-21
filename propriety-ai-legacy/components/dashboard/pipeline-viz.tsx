import { useState } from "react"
import { motion } from "framer-motion"
import { Radio } from "lucide-react"
import { usePipelineMetrics } from "@/lib/use-pipeline-metrics"
import { PipelineKpiBar } from "./pipeline-kpi-bar"
import { PipelineFlow } from "./pipeline-flow"
import { StageDetailPanel } from "./stage-detail-panel"

export function PipelineViz() {
  const { metrics, history, isLoading, isDemo } = usePipelineMetrics(10_000)
  const [selectedStageId, setSelectedStageId] = useState<string | null>(null)

  const selectedStage =
    selectedStageId && metrics
      ? (metrics.stages.find((s) => s.id === selectedStageId) ?? null)
      : null

  if (isLoading || !metrics) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="flex items-center gap-3 text-muted-foreground">
          <div className="w-4 h-4 border-2 border-governance/40 border-t-governance rounded-full animate-spin" />
          <span className="font-mono text-sm">Loading pipeline metrics...</span>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6">
      {/* Demo indicator */}
      {isDemo && (
        <motion.div
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-warning/10 border border-warning/20 w-fit"
        >
          <Radio className="w-3.5 h-3.5 text-warning" />
          <span className="font-mono text-[10px] text-warning">
            Demo mode — API unreachable, showing simulated data
          </span>
        </motion.div>
      )}

      {/* KPI summary bar */}
      <PipelineKpiBar metrics={metrics} />

      {/* Pipeline flow diagram */}
      <div>
        <div className="mb-3">
          <span className="font-mono text-[10px] tracking-[0.25em] text-muted-foreground/40 uppercase">
            Governance Pipeline
          </span>
        </div>
        <PipelineFlow
          stages={metrics.stages}
          selectedStageId={selectedStageId}
          onStageSelect={setSelectedStageId}
        />
      </div>

      {/* Detail panel (shown when a stage is selected) */}
      <StageDetailPanel
        stage={selectedStage}
        history={history}
        onClose={() => setSelectedStageId(null)}
      />
    </div>
  )
}
