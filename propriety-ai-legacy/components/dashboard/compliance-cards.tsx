import { useState, useEffect, useRef } from "react"
import { motion, useInView } from "framer-motion"
import { ShieldCheck, ShieldAlert } from "lucide-react"
import { fetchGovernanceStatus, type ComplianceFramework } from "@/lib/api-client"

const STATUS_COLORS: Record<ComplianceFramework["status"], {
  badge: string
  bar: string
  icon: typeof ShieldCheck
}> = {
  compliant: {
    badge: "bg-governance/15 text-governance border-governance/25",
    bar: "bg-governance",
    icon: ShieldCheck,
  },
  partial: {
    badge: "bg-warning/15 text-warning border-warning/25",
    bar: "bg-warning",
    icon: ShieldAlert,
  },
  non_compliant: {
    badge: "bg-destructive/15 text-destructive border-destructive/25",
    bar: "bg-destructive",
    icon: ShieldAlert,
  },
}

const STATUS_LABEL: Record<ComplianceFramework["status"], string> = {
  compliant: "Compliant",
  partial: "Partial",
  non_compliant: "Non-compliant",
}

// ── Fallback data for offline / demo mode ──────────────────────────────────

const FALLBACK_FRAMEWORKS: ComplianceFramework[] = [
  { name: "GDPR", score: 94, status: "compliant", passing: 47, total: 50 },
  { name: "EU AI Act", score: 87, status: "compliant", passing: 26, total: 30 },
  { name: "NIST AI RMF", score: 91, status: "compliant", passing: 55, total: 60 },
  { name: "ISO 42001", score: 72, status: "partial", passing: 36, total: 50 },
  { name: "SOC 2 Type II", score: 88, status: "compliant", passing: 44, total: 50 },
  { name: "HIPAA", score: 65, status: "partial", passing: 26, total: 40 },
  { name: "CCPA", score: 96, status: "compliant", passing: 24, total: 25 },
  { name: "MACI Protocol", score: 100, status: "compliant", passing: 15, total: 15 },
  { name: "Constitutional Hash", score: 100, status: "compliant", passing: 8, total: 8 },
]

export function ComplianceCards() {
  const [frameworks, setFrameworks] = useState<ComplianceFramework[]>(FALLBACK_FRAMEWORKS)
  const ref = useRef<HTMLDivElement>(null)
  const isInView = useInView(ref as React.RefObject<Element>, { once: true, margin: "-40px" })

  useEffect(() => {
    let cancelled = false

    async function load() {
      try {
        const result = await fetchGovernanceStatus()
        if (!cancelled) setFrameworks(result.frameworks)
      } catch {
        // Keep fallback data
      }
    }

    load()
    return () => { cancelled = true }
  }, [])

  return (
    <div ref={ref} className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
      {frameworks.map((fw, i) => {
        const style = STATUS_COLORS[fw.status]
        const Icon = style.icon
        const pct = Math.round(fw.score)

        return (
          <motion.div
            key={fw.name}
            initial={{ opacity: 0, y: 16 }}
            animate={isInView ? { opacity: 1, y: 0 } : {}}
            transition={{ duration: 0.45, delay: i * 0.06, ease: [0.16, 1, 0.3, 1] }}
            className="rounded-xl border border-border/40 glass-edge p-4 flex flex-col gap-3"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Icon className="w-4 h-4 text-governance" />
                <span className="text-sm font-medium text-foreground">{fw.name}</span>
              </div>
              <span
                className={`text-[10px] font-mono px-2 py-0.5 rounded-full border ${style.badge}`}
              >
                {STATUS_LABEL[fw.status]}
              </span>
            </div>

            {/* Score bar */}
            <div className="flex flex-col gap-1.5">
              <div className="flex items-baseline justify-between">
                <span className="font-mono text-xl text-foreground tabular-nums">
                  {pct}
                  <span className="text-xs text-muted-foreground/50">%</span>
                </span>
                <span className="font-mono text-[10px] text-muted-foreground/50">
                  {fw.passing}/{fw.total} items
                </span>
              </div>
              <div className="h-1.5 rounded-full bg-card/60 overflow-hidden">
                <motion.div
                  className={`h-full rounded-full ${style.bar}`}
                  initial={{ width: 0 }}
                  animate={isInView ? { width: `${pct}%` } : {}}
                  transition={{ duration: 0.8, delay: 0.2 + i * 0.06, ease: [0.16, 1, 0.3, 1] }}
                />
              </div>
            </div>
          </motion.div>
        )
      })}
    </div>
  )
}
