import { useState, useEffect, useRef, useCallback } from "react"
import { CONSTITUTIONAL_HASH } from "@/lib/constants"
import type { PipelineMetrics } from "@/lib/pipeline-types"

const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8080"
const MAX_HISTORY = 60

function jitter(value: number, pct: number = 0.15): number {
  return value * (1 + (Math.random() - 0.5) * 2 * pct)
}

function randomBetween(min: number, max: number): number {
  return min + Math.random() * (max - min)
}

function generateDemoMetrics(): PipelineMetrics {
  const baseElapsed = randomBetween(8, 42)
  const layer4P99 = jitter(12.3, 0.2)
  const layer4Status = layer4P99 > 14 ? "warning" as const : "healthy" as const

  return {
    timestamp: new Date().toISOString(),
    constitutional_hash: CONSTITUTIONAL_HASH,
    total_sla_ms: 50.0,
    total_elapsed_ms: baseElapsed,
    sla_status: baseElapsed > 45 ? "warning" : "healthy",
    stages: [
      {
        id: "layer1_validation",
        name: "MACI Enforcement",
        order: 1,
        budget_ms: 5.0,
        latency: {
          p50_ms: jitter(0.08),
          p95_ms: jitter(0.09),
          p99_ms: jitter(0.103),
          avg_ms: jitter(0.085),
          sample_count: Math.round(jitter(15423, 0.05)),
        },
        status: "healthy",
        sla_compliant: true,
        recent_violations: Math.round(jitter(37, 0.3)),
        total_processed: Math.round(jitter(15423, 0.05)),
      },
      {
        id: "layer2_deliberation",
        name: "Tenant Validation",
        order: 2,
        budget_ms: 20.0,
        latency: {
          p50_ms: jitter(1.2),
          p95_ms: jitter(2.1),
          p99_ms: jitter(3.8),
          avg_ms: jitter(1.5),
          sample_count: Math.round(jitter(15386, 0.05)),
        },
        status: "healthy",
        sla_compliant: true,
        recent_violations: 0,
        total_processed: Math.round(jitter(15386, 0.05)),
      },
      {
        id: "layer3_policy",
        name: "Impact Analysis",
        order: 3,
        budget_ms: 10.0,
        latency: {
          p50_ms: jitter(0.5),
          p95_ms: jitter(1.8),
          p99_ms: jitter(4.2),
          avg_ms: jitter(0.9),
          sample_count: Math.round(jitter(15380, 0.05)),
        },
        status: "healthy",
        sla_compliant: true,
        recent_violations: Math.round(jitter(6, 0.4)),
        total_processed: Math.round(jitter(15380, 0.05)),
      },
      {
        id: "layer4_audit",
        name: "Constitutional Check",
        order: 4,
        budget_ms: 15.0,
        latency: {
          p50_ms: jitter(3.1),
          p95_ms: jitter(8.5),
          p99_ms: layer4P99,
          avg_ms: jitter(4.2),
          sample_count: Math.round(jitter(15371, 0.05)),
        },
        status: layer4Status,
        sla_compliant: layer4P99 <= 15.0,
        recent_violations: Math.round(jitter(9, 0.3)),
        total_processed: Math.round(jitter(15371, 0.05)),
      },
    ],
    throughput: {
      current_rps: jitter(5066, 0.1),
      peak_rps: jitter(7200, 0.05),
      avg_rps: jitter(4800, 0.08),
      total_requests: Math.round(jitter(61560, 0.05)),
    },
    scaling_recommendation: {
      direction: "maintain",
      urgency: "none",
      reasons: [],
    },
  }
}

async function fetchPipelineMetrics(): Promise<PipelineMetrics> {
  const response = await fetch(`${API_BASE}/api/v1/pipeline/metrics`, {
    headers: { "Content-Type": "application/json" },
  })
  if (!response.ok) {
    throw new Error(`API error ${response.status}`)
  }
  return response.json() as Promise<PipelineMetrics>
}

export interface UsePipelineMetricsReturn {
  metrics: PipelineMetrics | null
  history: PipelineMetrics[]
  isLoading: boolean
  error: string | null
  isDemo: boolean
}

export function usePipelineMetrics(
  pollIntervalMs: number = 10_000,
): UsePipelineMetricsReturn {
  const [metrics, setMetrics] = useState<PipelineMetrics | null>(null)
  const [history, setHistory] = useState<PipelineMetrics[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [isDemo, setIsDemo] = useState(false)
  const historyRef = useRef<PipelineMetrics[]>([])

  const appendToHistory = useCallback((m: PipelineMetrics) => {
    const next = [...historyRef.current, m].slice(-MAX_HISTORY)
    historyRef.current = next
    setHistory(next)
  }, [])

  useEffect(() => {
    let cancelled = false
    let demoTimer: ReturnType<typeof setTimeout> | null = null

    async function load() {
      try {
        const result = await fetchPipelineMetrics()
        if (cancelled) return
        setMetrics(result)
        appendToHistory(result)
        setError(null)
        setIsDemo(false)
        setIsLoading(false)
      } catch {
        if (cancelled) return
        // Fall back to demo data after first failure
        setIsDemo(true)
        setError(null)
        const demo = generateDemoMetrics()
        setMetrics(demo)
        appendToHistory(demo)
        setIsLoading(false)
      }
    }

    // Try API first, fall back to demo after 2s timeout
    const raceTimeout = setTimeout(() => {
      if (cancelled || metrics) return
      setIsDemo(true)
      const demo = generateDemoMetrics()
      setMetrics(demo)
      appendToHistory(demo)
      setIsLoading(false)
    }, 2000)

    load().then(() => clearTimeout(raceTimeout))

    const interval = setInterval(() => {
      if (isDemo) {
        const demo = generateDemoMetrics()
        setMetrics(demo)
        appendToHistory(demo)
      } else {
        load()
      }
    }, pollIntervalMs)

    return () => {
      cancelled = true
      clearInterval(interval)
      if (demoTimer) clearTimeout(demoTimer)
      clearTimeout(raceTimeout)
    }
  }, [pollIntervalMs, appendToHistory])

  return { metrics, history, isLoading, error, isDemo }
}
