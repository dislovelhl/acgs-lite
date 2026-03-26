import { useState, useEffect } from "react"
import { motion } from "framer-motion"
import { Activity } from "lucide-react"
import { fetchHealthDashboard, type ServiceHealth, type HealthDashboard } from "@/lib/api-client"

const STATUS_DOT: Record<ServiceHealth["status"], string> = {
  healthy: "bg-governance",
  degraded: "bg-warning",
  down: "bg-destructive",
}

const STATUS_LABEL: Record<ServiceHealth["status"], string> = {
  healthy: "Healthy",
  degraded: "Degraded",
  down: "Down",
}

const POLL_INTERVAL_MS = 30_000

// ── Fallback data for offline / demo mode ──────────────────────────────────

const FALLBACK_HEALTH: HealthDashboard = {
  overall: "healthy",
  services: [
    { name: "Agent Bus", status: "healthy", port: 8000, uptime: "14d 3h" },
    { name: "API Gateway", status: "healthy", port: 8080, uptime: "14d 3h" },
    { name: "Policy Engine", status: "healthy", port: 8001, uptime: "14d 2h" },
    { name: "Audit Store", status: "healthy", port: 8002, uptime: "14d 3h" },
    { name: "OPA Sidecar", status: "degraded", port: 8181, uptime: "2d 11h" },
    { name: "Constitutional Guard", status: "healthy", port: 8003, uptime: "14d 3h" },
  ],
}

export function HealthPanel() {
  const [data, setData] = useState<HealthDashboard>(FALLBACK_HEALTH)
  const [error, setError] = useState(false)

  useEffect(() => {
    let cancelled = false

    async function load() {
      try {
        const result = await fetchHealthDashboard()
        if (!cancelled) {
          setData(result)
          setError(false)
        }
      } catch {
        if (!cancelled) setError(true)
      }
    }

    load()
    const interval = setInterval(load, POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [])

  return (
    <div className="rounded-xl border border-border/40 glass-edge overflow-hidden">
      <div className="flex items-center gap-2 px-5 py-3 border-b border-border/30">
        <Activity className="w-4 h-4 text-governance" />
        <span className="font-mono text-[10px] tracking-[0.25em] text-muted-foreground/40 uppercase">
          service health
        </span>
        {error && (
          <span className="ml-auto font-mono text-[10px] text-warning">
            using cached data
          </span>
        )}
      </div>

      <div className="flex flex-wrap gap-px p-3">
        {data.services.map((service, i) => (
          <motion.div
            key={service.name}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35, delay: i * 0.05 }}
            className="flex items-center gap-3 px-4 py-2.5 rounded-lg bg-card/40 min-w-[180px] flex-1"
          >
            <span
              className={`w-2 h-2 rounded-full flex-shrink-0 ${STATUS_DOT[service.status]}`}
              aria-label={STATUS_LABEL[service.status]}
            />
            <div className="flex flex-col gap-0.5 min-w-0">
              <span className="text-xs text-foreground truncate">
                {service.name}
              </span>
              <span className="font-mono text-[10px] text-muted-foreground/50">
                :{service.port} &middot; {service.uptime}
              </span>
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  )
}
