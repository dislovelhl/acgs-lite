import { useRef, useEffect, useState } from "react"
import { motion, useInView } from "framer-motion"
import { ArrowRight, Shield, FileCheck, Users, Database, Bell } from "lucide-react"
import { TracingBeam } from "./tracing-beam"
import { GlareCard } from "./glare-card"
import { WordReveal } from "./word-reveal"
import { AnimateIn } from "./animate-in"
import { PageHero } from "./page-layout"

// ── AnimatedNumber ──────────────────────────────────────────────
function AnimatedNumber({ value, suffix = "" }: { value: number; suffix?: string }) {
  const [display, setDisplay] = useState(0)
  const ref = useRef<HTMLSpanElement>(null)
  const isInView = useInView(ref as React.RefObject<Element>, { once: true })

  useEffect(() => {
    if (!isInView) return
    let start: number | null = null
    const duration = 1000
    function step(ts: number) {
      if (!start) start = ts
      const progress = Math.min((ts - start) / duration, 1)
      const ease = 1 - Math.pow(1 - progress, 3)
      setDisplay(Math.round(ease * value))
      if (progress < 1) requestAnimationFrame(step)
    }
    requestAnimationFrame(step)
  }, [isInView, value])

  return (
    <span ref={ref}>
      {display}
      {suffix}
    </span>
  )
}

// ── Process Steps ──────────────────────────────────────────────
const PROCESS_STEPS = [
  {
    number: "01",
    title: "Governance inventory",
    description:
      "Map all active AI agents, their action surfaces, and current policy coverage. Identify the delta between what is governed and what should be.",
  },
  {
    number: "02",
    title: "Risk surface analysis",
    description:
      "Evaluate each agent action against GDPR, EU AI Act, NIST RMF, and ISO 42001 requirements. Score proximity to regulatory limits.",
  },
  {
    number: "03",
    title: "Constitutional design",
    description:
      "Translate risk findings into enforceable OPA policies anchored to an immutable constitutional hash.",
  },
  {
    number: "04",
    title: "MACI deployment",
    description:
      "Deploy the governance engine with mandatory proposer/validator/executor separation. Verify enforcement in staging before production.",
  },
  {
    number: "05",
    title: "Continuous monitoring",
    description:
      "Ongoing audit trail review, policy drift detection, and regulatory change integration with quarterly constitutional reviews.",
  },
]

// ── Deliverable Cards ──────────────────────────────────────────────
const DELIVERABLES = [
  {
    icon: FileCheck,
    title: "Governance Gap Report",
    description: "Detailed analysis of coverage gaps with risk-ranked remediation priorities.",
  },
  {
    icon: Shield,
    title: "Constitutional Blueprint",
    description: "Ready-to-deploy OPA policy set mapped to your specific agent actions.",
  },
  {
    icon: Database,
    title: "Audit Architecture",
    description: "Append-only audit trail design with cryptographic verification paths.",
  },
  {
    icon: Users,
    title: "MACI Implementation Guide",
    description: "Agent role separation specification with enforcement verification tests.",
  },
  {
    icon: Bell,
    title: "Monitoring Playbook",
    description: "Alert thresholds, escalation paths, and quarterly review templates.",
  },
]

// ── Framework Table ──────────────────────────────────────────────
const FRAMEWORKS = [
  { name: "GDPR", items: 12, covered: 11, tag: "mandatory" },
  { name: "EU AI Act", items: 18, covered: 16, tag: "mandatory" },
  { name: "NIST RMF", items: 14, covered: 12, tag: "recommended" },
  { name: "ISO 42001", items: 9, covered: 8, tag: "recommended" },
]

// ── Main Component ──────────────────────────────────────────────
export function AssessmentPage() {
  return (
    <main className="min-h-screen crosshatch-bg pt-14">
      <PageHero
        label="// governance assessment"
        title="Understand your AI governance posture"
        description="A structured five-step assessment that maps your agent actions to regulatory requirements and produces a deployment-ready governance constitution."
      />

      {/* Process Steps with TracingBeam */}
      <section id="assessment" className="py-24 px-6 max-w-4xl mx-auto">
        <div className="mb-12">
          <WordReveal
            text="The assessment process"
            el="h2"
            className="text-2xl font-semibold tracking-tight mb-3"
          />
          <p className="text-muted-foreground text-sm">
            Five structured phases, completed in two to four weeks depending on agent surface area.
          </p>
        </div>

        <TracingBeam>
          <div className="space-y-12">
            {PROCESS_STEPS.map((step, i) => (
              <ProcessStep key={step.number} step={step} index={i} />
            ))}
          </div>
        </TracingBeam>
      </section>

      {/* Deliverables */}
      <section className="py-20 px-6 max-w-7xl mx-auto">
        <div className="mb-12 text-center">
          <p className="text-xs font-mono uppercase tracking-[0.2em] text-muted-foreground/60 mb-4">
            // deliverables
          </p>
          <WordReveal
            text="What you receive"
            el="h2"
            className="text-3xl font-semibold tracking-tight"
          />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {DELIVERABLES.map((d, i) => (
            <DeliverableCard key={d.title} deliverable={d} index={i} />
          ))}
        </div>
      </section>

      {/* Framework Coverage Table */}
      <section className="py-20 px-6 max-w-4xl mx-auto">
        <div className="mb-10">
          <p className="text-xs font-mono uppercase tracking-[0.2em] text-muted-foreground/60 mb-4">
            // coverage
          </p>
          <WordReveal
            text="Regulatory framework coverage"
            el="h2"
            className="text-2xl font-semibold tracking-tight"
          />
        </div>

        <div className="glass-edge rounded-xl overflow-hidden">
          <div className="grid grid-cols-4 gap-0 text-xs font-mono uppercase tracking-widest text-muted-foreground/50 px-6 py-3 border-b border-border/30">
            <span>Framework</span>
            <span>Requirements</span>
            <span>Covered</span>
            <span>Status</span>
          </div>
          {FRAMEWORKS.map((fw, i) => (
            <FrameworkRow key={fw.name} fw={fw} index={i} />
          ))}
        </div>

        <div className="mt-4 glass rounded-lg px-4 py-3 flex items-center gap-3">
          <div className="w-2 h-2 rounded-full bg-amber animate-pulse flex-shrink-0" />
          <p className="text-xs text-muted-foreground">
            <span className="text-amber font-medium">Critical gap:</span> 5 high-risk agent actions
            have no current policy coverage — immediate remediation required before EU AI Act enforcement.
          </p>
        </div>
      </section>

      {/* CTA */}
      <section className="py-24 px-6 max-w-2xl mx-auto text-center">
        <motion.div
          initial={{ opacity: 0, scale: 0.97 }}
          whileInView={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.5 }}
          viewport={{ once: true }}
          className="glass-strong rounded-2xl p-10"
          style={{ boxShadow: "0 0 60px 0 oklch(0.65 0.18 160 / 0.12)" }}
        >
          <div className="flex items-center justify-center gap-2 mb-6">
            <div className="w-2 h-2 rounded-full bg-governance animate-pulse" />
            <span className="text-xs font-mono text-governance/70 tracking-widest uppercase">
              ready to start
            </span>
          </div>
          <h2 className="text-2xl font-semibold tracking-tight mb-3">
            Begin your governance assessment
          </h2>
          <p className="text-muted-foreground text-sm mb-8 leading-relaxed">
            Two to four weeks. Deployment-ready output. Compliance team satisfied.
          </p>
          <motion.a
            href="mailto:governance@propriety.ai"
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            className="inline-flex items-center gap-2 px-6 py-3 rounded-lg bg-governance text-background font-medium text-sm"
            style={{ boxShadow: "0 0 32px 0 oklch(0.65 0.18 160 / 0.35)" }}
          >
            Schedule assessment
            <ArrowRight className="w-4 h-4" />
          </motion.a>
        </motion.div>
      </section>
    </main>
  )
}

// ── Sub-components ──────────────────────────────────────────────
function ProcessStep({ step, index }: { step: (typeof PROCESS_STEPS)[0]; index: number }) {
  return (
    <AnimateIn
      delay={index * 0.08}
      direction="left"
      offset={12}
      className="glass-edge rounded-xl p-6"
    >
      <div className="flex items-start gap-4">
        <div
          className="flex-shrink-0 w-8 h-8 rounded-lg bg-governance/10 border border-governance/20 flex items-center justify-center"
          style={{ boxShadow: "0 0 16px oklch(0.65 0.18 160 / 0.25)" }}
        >
          <span className="text-[10px] font-mono text-governance">{step.number}</span>
        </div>
        <div>
          <h3 className="font-semibold mb-1.5 text-sm">{step.title}</h3>
          <p className="text-xs text-muted-foreground leading-relaxed">{step.description}</p>
        </div>
      </div>
    </AnimateIn>
  )
}

function DeliverableCard({
  deliverable,
  index,
}: {
  deliverable: (typeof DELIVERABLES)[0]
  index: number
}) {
  const Icon = deliverable.icon

  return (
    <AnimateIn delay={index * 0.07} offset={16}>
      <GlareCard className="glass-edge rounded-xl h-full">
        <motion.div
          className="p-8"
          whileHover={{ y: -4 }}
          transition={{ duration: 0.2 }}
        >
          <div className="flex items-center justify-between mb-4">
            <div className="w-8 h-8 rounded-lg bg-governance/10 border border-governance/20 flex items-center justify-center">
              <Icon className="w-4 h-4 text-governance" />
            </div>
            <span className="text-xs font-mono text-muted-foreground/40">
              {String(index + 1).padStart(2, "0")}
            </span>
          </div>
          <h3 className="font-semibold mb-2 text-sm">{deliverable.title}</h3>
          <p className="text-xs text-muted-foreground leading-relaxed">{deliverable.description}</p>
        </motion.div>
      </GlareCard>
    </AnimateIn>
  )
}

function FrameworkRow({ fw, index }: { fw: (typeof FRAMEWORKS)[0]; index: number }) {
  const ref = useRef<HTMLDivElement>(null)
  const isInView = useInView(ref as React.RefObject<Element>, { once: true })
  const pct = Math.round((fw.covered / fw.items) * 100)

  return (
    <div
      ref={ref}
      className="grid grid-cols-4 gap-0 px-6 py-4 border-b border-border/20 hover:bg-governance/[0.03] transition-colors last:border-b-0"
    >
      <span className="text-sm font-medium">{fw.name}</span>
      <span className="text-sm text-muted-foreground">
        <AnimatedNumber value={fw.items} />
      </span>
      <span className="text-sm text-governance">
        <AnimatedNumber value={fw.covered} />
      </span>
      <div className="flex items-center gap-2">
        <div className="h-1.5 w-16 rounded-full bg-border/40 overflow-hidden">
          <motion.div
            className="h-full bg-governance rounded-full"
            initial={{ width: 0 }}
            animate={isInView ? { width: `${pct}%` } : {}}
            transition={{ duration: 0.8, delay: index * 0.1, ease: "easeOut" }}
          />
        </div>
        <span className="text-xs text-muted-foreground/60">{pct}%</span>
      </div>
    </div>
  )
}
