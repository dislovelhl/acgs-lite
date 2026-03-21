import { motion, useInView } from "framer-motion"
import { useRef } from "react"

const METRICS = [
  {
    value: "560",
    unit: "ns",
    label: "P50 validation latency",
    sub: "Rust/PyO3 backend",
  },
  {
    value: "3",
    unit: "×",
    label: "MACI role separation",
    sub: "Proposer · Validator · Executor",
  },
  {
    value: "4",
    unit: "",
    label: "regulatory frameworks",
    sub: "GDPR · EU AI Act · NIST · ISO 42001",
  },
  {
    value: "∞",
    unit: "",
    label: "audit trail depth",
    sub: "cryptographically signed, append-only",
  },
]

export function MetricsBar() {
  const ref = useRef<HTMLDivElement>(null)
  const isInView = useInView(ref as React.RefObject<Element>, {
    once: true,
    margin: "-60px",
  })

  return (
    <section ref={ref} className="border-y border-border/30 py-16 px-6">
      <div className="max-w-7xl mx-auto grid grid-cols-2 lg:grid-cols-4 divide-x divide-border/20">
        {METRICS.map((m, i) => (
          <motion.div
            key={m.label}
            initial={{ opacity: 0, y: 20 }}
            animate={isInView ? { opacity: 1, y: 0 } : {}}
            transition={{ duration: 0.6, delay: i * 0.1, ease: [0.16, 1, 0.3, 1] }}
            className="flex flex-col gap-2 px-8 first:pl-0 last:pr-0 py-4"
          >
            <div
              className="font-display font-light leading-none tracking-tight"
              style={{ fontSize: "clamp(3rem, 5.5vw, 5rem)" }}
            >
              <span className="text-foreground">{m.value}</span>
              {m.unit && (
                <span style={{ color: "oklch(0.65 0.18 160)" }}>{m.unit}</span>
              )}
            </div>
            <div className="text-sm text-muted-foreground leading-snug">
              {m.label}
            </div>
            <div className="text-[10px] font-mono text-muted-foreground/40 leading-snug">
              {m.sub}
            </div>
          </motion.div>
        ))}
      </div>
    </section>
  )
}
