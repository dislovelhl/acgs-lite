export type StageStatus = "healthy" | "warning" | "critical"
export type SlaStatus = "healthy" | "warning" | "critical"
export type ScalingDirection = "scale_up" | "scale_down" | "maintain"
export type ScalingUrgency = "immediate" | "soon" | "none"

export interface StageLatency {
  p50_ms: number
  p95_ms: number
  p99_ms: number
  avg_ms: number
  sample_count: number
}

export interface PipelineStage {
  id: string
  name: string
  order: number
  budget_ms: number
  latency: StageLatency
  status: StageStatus
  sla_compliant: boolean
  recent_violations: number
  total_processed: number
}

export interface PipelineMetrics {
  timestamp: string
  constitutional_hash: string
  total_sla_ms: number
  total_elapsed_ms: number
  sla_status: SlaStatus
  stages: PipelineStage[]
  throughput: {
    current_rps: number
    peak_rps: number
    avg_rps: number
    total_requests: number
  }
  scaling_recommendation: {
    direction: ScalingDirection
    urgency: ScalingUrgency
    reasons: string[]
  }
}
