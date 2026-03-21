import { useState } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { PageHero } from "@/components/page-layout"
import { AnimateIn } from "@/components/animate-in"

// ── Types ──────────────────────────────────────────────────────────────────

type TabId = "gdpr" | "eu-ai-act" | "nist-rmf" | "iso-42001"

interface RequirementCard {
  article: string
  title: string
  description: string
}

interface FrameworkData {
  id: TabId
  label: string
  badge: string
  subtitle: string
  keyFocus: string
  cards: RequirementCard[]
  mappingPoints: string[]
}

type CoverageStatus = "full" | "partial" | "none"

interface CoverageRow {
  feature: string
  gdpr: CoverageStatus
  euAiAct: CoverageStatus
  nist: CoverageStatus
  iso: CoverageStatus
}

// ── Data ──────────────────────────────────────────────────────────────────

const TABS: { id: TabId; label: string }[] = [
  { id: "gdpr", label: "GDPR" },
  { id: "eu-ai-act", label: "EU AI Act" },
  { id: "nist-rmf", label: "NIST RMF" },
  { id: "iso-42001", label: "ISO 42001" },
]

const FRAMEWORKS: Record<TabId, FrameworkData> = {
  gdpr: {
    id: "gdpr",
    label: "GDPR",
    badge: "Regulation (EU) 2016/679",
    subtitle: "General Data Protection Regulation",
    keyFocus:
      "Article 22 — Automated individual decision-making, including profiling",
    cards: [
      {
        article: "Art. 22",
        title: "Automated decision-making",
        description:
          "Prohibition on solely automated decisions producing significant effects without explicit consent, legal basis, or contractual necessity.",
      },
      {
        article: "Art. 5",
        title: "Data minimization & purpose limitation",
        description:
          "Personal data must be collected for specified, explicit, and legitimate purposes and not further processed in an incompatible manner.",
      },
      {
        article: "Art. 17",
        title: "Right to erasure",
        description:
          "Data subjects may request deletion of decision records and all personal data held without undue delay under qualifying conditions.",
      },
      {
        article: "Art. 35",
        title: "Data Protection Impact Assessment",
        description:
          "DPIA mandatory prior to processing likely resulting in high risk to individuals, including systematic automated profiling.",
      },
    ],
    mappingPoints: [
      "Constitutional hash anchors every automated decision to an immutable policy version, providing the documented legal basis required by Art. 22.",
      "OPA policies enforce data minimization at agent action boundaries — agents may only access fields declared in their constitutional scope.",
      "Append-only audit trail enables full decision replay and targeted erasure of personal data records without compromising audit integrity.",
    ],
  },
  "eu-ai-act": {
    id: "eu-ai-act",
    label: "EU AI Act",
    badge: "Regulation (EU) 2024/1689",
    subtitle: "European Union Artificial Intelligence Act",
    keyFocus:
      "Articles 13–15 — Transparency, human oversight, and accuracy requirements for high-risk AI systems",
    cards: [
      {
        article: "Art. 13",
        title: "Transparency obligations",
        description:
          "High-risk AI systems must be designed to enable users and affected persons to interpret outputs and use them appropriately.",
      },
      {
        article: "Art. 14",
        title: "Human oversight measures",
        description:
          "Providers must ensure humans can effectively oversee, interrupt, override, or stop AI system operations during deployment.",
      },
      {
        article: "Art. 15",
        title: "Accuracy, robustness & cybersecurity",
        description:
          "High-risk systems must achieve appropriate levels of accuracy, withstand errors and adversarial inputs, and resist attacks.",
      },
      {
        article: "Art. 9",
        title: "Risk management system",
        description:
          "Continuous risk management throughout the lifecycle: identification, estimation, evaluation, and mitigation of known risks.",
      },
    ],
    mappingPoints: [
      "MACI enforces Art. 14 human oversight structurally — the Proposer/Validator/Executor separation means no AI agent can approve and execute its own action.",
      "Every agent decision is tagged with its constitutional policy version and OPA evaluation trace, satisfying Art. 13 transparency requirements end-to-end.",
      "Circuit breaker and chaos engineering subsystems implement Art. 15 robustness — automatic suspension on anomalous output patterns before human review.",
    ],
  },
  "nist-rmf": {
    id: "nist-rmf",
    label: "NIST RMF",
    badge: "NIST AI 100-1",
    subtitle: "AI Risk Management Framework",
    keyFocus: "GOVERN, MAP, MEASURE, MANAGE functions for AI risk",
    cards: [
      {
        article: "GOVERN",
        title: "Governance policies & culture",
        description:
          "Policies, processes, procedures, and practices across the organization for managing AI risk. Accountability and transparency structures.",
      },
      {
        article: "MAP",
        title: "Context & risk categorization",
        description:
          "Identify, categorize, and prioritize AI risks in context. Define intended uses, affected populations, and impact levels.",
      },
      {
        article: "MEASURE",
        title: "Risk analysis & assessment",
        description:
          "Analyze, assess, benchmark, and monitor AI risks and benefits using quantitative and qualitative approaches.",
      },
      {
        article: "MANAGE",
        title: "Risk treatment & response",
        description:
          "Prioritize, respond to, and communicate AI risks. Implement treatment plans and monitor effectiveness over time.",
      },
    ],
    mappingPoints: [
      "Constitutional YAML files operationalize GOVERN — policies are versioned, auditable, and enforced before any agent executes, not as post-hoc documentation.",
      "The MAP function is implemented via MACI role tagging: every action surface is categorized by risk tier at registration time, not at audit time.",
      "Structured policy log streams provide MEASURE-ready telemetry — latency, rejection rates, policy drift, and constitutional hash adherence in real-time.",
    ],
  },
  "iso-42001": {
    id: "iso-42001",
    label: "ISO 42001",
    badge: "ISO/IEC 42001:2023",
    subtitle: "Artificial Intelligence Management System",
    keyFocus:
      "Requirements for establishing, implementing, maintaining an AI management system",
    cards: [
      {
        article: "Clause 6",
        title: "Planning",
        description:
          "Risk and opportunity assessment for AI systems. Establish AI policy objectives and processes to achieve intended outcomes.",
      },
      {
        article: "Clause 8",
        title: "Operation",
        description:
          "Operational planning and control of AI systems. Implement processes for AI system development, deployment, and monitoring.",
      },
      {
        article: "Clause 9",
        title: "Performance evaluation",
        description:
          "Monitoring, measurement, analysis, and evaluation of the AI management system and AI systems in scope.",
      },
      {
        article: "Clause 10",
        title: "Improvement",
        description:
          "Nonconformity identification, corrective action, and continual improvement of the AI management system.",
      },
    ],
    mappingPoints: [
      "Constitutional amendments (Clause 6 planning) follow a mandatory deliberation layer — proposed changes are evaluated against impact criteria before ratification.",
      "The Clause 9 performance evaluation requirement maps directly to the metrics subsystem: policy evaluation latency, override rates, and constitutional drift are tracked continuously.",
      "Schema evolution tooling implements Clause 10 improvement — nonconforming policy versions are flagged, corrective patches proposed, and audit trails preserved across the transition.",
    ],
  },
}

const COVERAGE_ROWS: CoverageRow[] = [
  { feature: "Audit trail", gdpr: "full", euAiAct: "full", nist: "full", iso: "full" },
  {
    feature: "Pre-action evaluation",
    gdpr: "full",
    euAiAct: "full",
    nist: "full",
    iso: "full",
  },
  {
    feature: "Human oversight enforcement",
    gdpr: "none",
    euAiAct: "full",
    nist: "full",
    iso: "full",
  },
  {
    feature: "Automated decision logging",
    gdpr: "full",
    euAiAct: "full",
    nist: "full",
    iso: "full",
  },
  {
    feature: "Constitutional hash anchoring",
    gdpr: "full",
    euAiAct: "full",
    nist: "full",
    iso: "full",
  },
]

const COVERAGE_COLUMNS: { key: keyof Omit<CoverageRow, "feature">; label: string }[] = [
  { key: "gdpr", label: "GDPR" },
  { key: "euAiAct", label: "EU AI Act" },
  { key: "nist", label: "NIST" },
  { key: "iso", label: "ISO" },
]

// ── Sub-components ─────────────────────────────────────────────────────────

function RequirementCardItem({ card, index }: { card: RequirementCard; index: number }) {
  return (
    <AnimateIn
      delay={index * 0.06}
      offset={12}
      margin="-20px"
      duration={0.45}
      className="glass-edge rounded-xl p-5 flex flex-col gap-3"
    >
      <span
        className="text-[10px] font-mono tracking-[0.18em] uppercase"
        style={{ color: "oklch(0.65 0.18 160)" }}
      >
        {card.article}
      </span>
      <h4 className="text-sm font-semibold leading-snug">{card.title}</h4>
      <p className="text-xs text-muted-foreground leading-relaxed">{card.description}</p>
    </AnimateIn>
  )
}

function MappingSection({ points }: { points: string[] }) {
  return (
    <div
      className="rounded-xl p-6 mt-6"
      style={{
        background: "oklch(0.65 0.18 160 / 0.05)",
        border: "1px solid oklch(0.65 0.18 160 / 0.15)",
      }}
    >
      <p
        className="text-[10px] font-mono tracking-[0.18em] uppercase mb-4"
        style={{ color: "oklch(0.65 0.18 160 / 0.7)" }}
      >
        How Propriety maps it
      </p>
      <ul className="space-y-3">
        {points.map((point, i) => (
          <li key={i} className="flex items-start gap-3">
            <span
              className="mt-1 flex-shrink-0 w-1 h-1 rounded-full"
              style={{ background: "oklch(0.65 0.18 160)", marginTop: "6px" }}
            />
            <p className="text-sm text-muted-foreground leading-relaxed">{point}</p>
          </li>
        ))}
      </ul>
    </div>
  )
}

function FrameworkTabContent({ framework }: { framework: FrameworkData }) {
  return (
    <motion.div
      key={framework.id}
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
    >
      {/* Framework header */}
      <div className="mb-8">
        <div className="flex flex-wrap items-center gap-3 mb-3">
          <span
            className="inline-flex items-center px-3 py-1 rounded-full text-[11px] font-mono tracking-wider"
            style={{
              background: "oklch(0.65 0.18 160 / 0.1)",
              border: "1px solid oklch(0.65 0.18 160 / 0.25)",
              color: "oklch(0.65 0.18 160)",
            }}
          >
            {framework.badge}
          </span>
        </div>
        <h3 className="text-xl font-semibold tracking-tight mb-2">{framework.subtitle}</h3>
        <div
          className="flex items-start gap-3 glass-edge rounded-lg px-4 py-3"
          style={{ borderLeft: "3px solid oklch(0.65 0.18 160 / 0.5)" }}
        >
          <p className="text-xs text-muted-foreground leading-relaxed">
            <span className="font-medium text-foreground/80">Key focus: </span>
            {framework.keyFocus}
          </p>
        </div>
      </div>

      {/* Requirement cards 2×2 */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {framework.cards.map((card, i) => (
          <RequirementCardItem key={card.article} card={card} index={i} />
        ))}
      </div>

      {/* Mapping section */}
      <MappingSection points={framework.mappingPoints} />
    </motion.div>
  )
}

function CoverageStatusCell({ status }: { status: CoverageStatus }) {
  if (status === "full") {
    return (
      <span
        className="inline-flex items-center justify-center w-7 h-7 rounded-full text-sm"
        style={{
          background: "oklch(0.65 0.18 160 / 0.12)",
          border: "1px solid oklch(0.65 0.18 160 / 0.25)",
          color: "oklch(0.65 0.18 160)",
        }}
        aria-label="Supported"
      >
        ✓
      </span>
    )
  }
  if (status === "partial") {
    return (
      <span
        className="inline-flex items-center justify-center w-7 h-7 rounded-full text-xs"
        style={{
          background: "oklch(0.75 0.15 85 / 0.1)",
          border: "1px solid oklch(0.75 0.15 85 / 0.25)",
          color: "oklch(0.75 0.15 85)",
        }}
        aria-label="Partial"
      >
        ◐
      </span>
    )
  }
  return (
    <span
      className="inline-flex items-center justify-center w-7 h-7 text-xs text-muted-foreground/40"
      aria-label="Not applicable"
    >
      —
    </span>
  )
}

function CoverageMatrixSection() {
  return (
    <AnimateIn duration={0.55}>
      <div className="glass-edge rounded-xl overflow-hidden">
        {/* Table header */}
        <div
          className="grid gap-0 px-6 py-3 border-b"
          style={{
            gridTemplateColumns: "1fr repeat(4, 100px)",
            borderColor: "oklch(1 0 0 / 0.06)",
          }}
        >
          <span className="text-[10px] font-mono uppercase tracking-[0.18em] text-muted-foreground/50">
            Feature
          </span>
          {COVERAGE_COLUMNS.map((col) => (
            <span
              key={col.key}
              className="text-[10px] font-mono uppercase tracking-[0.18em] text-center"
              style={{ color: "oklch(0.65 0.18 160 / 0.6)" }}
            >
              {col.label}
            </span>
          ))}
        </div>

        {/* Table rows */}
        {COVERAGE_ROWS.map((row, rowIndex) => (
          <div
            key={row.feature}
            className="grid gap-0 px-6 py-4 transition-colors hover:bg-white/[0.02]"
            style={{
              gridTemplateColumns: "1fr repeat(4, 100px)",
              borderBottom:
                rowIndex < COVERAGE_ROWS.length - 1
                  ? "1px solid oklch(1 0 0 / 0.04)"
                  : undefined,
            }}
          >
            <span className="text-sm text-muted-foreground/80 self-center">{row.feature}</span>
            {COVERAGE_COLUMNS.map((col) => (
              <div key={col.key} className="flex items-center justify-center">
                <CoverageStatusCell status={row[col.key]} />
              </div>
            ))}
          </div>
        ))}
      </div>

      {/* Legend */}
      <div className="flex flex-wrap items-center gap-6 mt-4 px-1">
        <div className="flex items-center gap-2">
          <CoverageStatusCell status="full" />
          <span className="text-xs text-muted-foreground/60">Full coverage</span>
        </div>
        <div className="flex items-center gap-2">
          <CoverageStatusCell status="partial" />
          <span className="text-xs text-muted-foreground/60">Partial coverage</span>
        </div>
        <div className="flex items-center gap-2">
          <CoverageStatusCell status="none" />
          <span className="text-xs text-muted-foreground/60">Not applicable</span>
        </div>
      </div>
    </AnimateIn>
  )
}

// ── Main Component ─────────────────────────────────────────────────────────

export function CompliancePage() {
  const [activeTab, setActiveTab] = useState<TabId>("gdpr")

  return (
    <main className="min-h-screen crosshatch-bg pt-14">
      <PageHero
        label="§ VII — Regulatory Coverage"
        title="Every regulation. One engine."
        description="Propriety AI maps AI agent actions to four major regulatory frameworks — GDPR, EU AI Act, NIST RMF, and ISO 42001 — enforcing compliance before any action executes, not after."
      />

      {/* Tab navigation + content */}
      <section className="py-16 px-6 max-w-5xl mx-auto">
        {/* Tab bar */}
        <div
          className="flex items-center gap-1 p-1 rounded-xl mb-10 overflow-x-auto"
          style={{
            background: "oklch(1 0 0 / 0.03)",
            border: "1px solid oklch(1 0 0 / 0.07)",
          }}
          role="tablist"
          aria-label="Regulatory frameworks"
        >
          {TABS.map((tab) => {
            const isActive = activeTab === tab.id
            return (
              <button
                key={tab.id}
                role="tab"
                aria-selected={isActive}
                aria-controls={`panel-${tab.id}`}
                onClick={() => setActiveTab(tab.id)}
                className="relative flex-shrink-0 px-5 py-2.5 rounded-lg text-sm font-medium transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 whitespace-nowrap"
                style={{
                  color: isActive ? "oklch(0.65 0.18 160)" : "oklch(1 0 0 / 0.4)",
                  background: isActive ? "oklch(0.65 0.18 160 / 0.1)" : "transparent",
                  border: isActive
                    ? "1px solid oklch(0.65 0.18 160 / 0.25)"
                    : "1px solid transparent",
                  boxShadow: isActive
                    ? "0 0 16px oklch(0.65 0.18 160 / 0.15)"
                    : "none",
                }}
              >
                <span className="relative z-10 font-mono tracking-wider text-xs uppercase">
                  {tab.label}
                </span>
              </button>
            )
          })}
        </div>

        {/* Animated tab content */}
        <div
          role="tabpanel"
          id={`panel-${activeTab}`}
          aria-labelledby={`tab-${activeTab}`}
        >
          <AnimatePresence mode="wait">
            <FrameworkTabContent
              key={activeTab}
              framework={FRAMEWORKS[activeTab]}
            />
          </AnimatePresence>
        </div>
      </section>

      {/* Coverage matrix */}
      <section className="py-16 px-6 max-w-5xl mx-auto">
        <div className="mb-8">
          <div className="article-notation mb-4">§ — Coverage matrix</div>
          <h2 className="text-2xl font-semibold tracking-tight mb-2">
            Capability coverage across frameworks
          </h2>
          <p className="text-sm text-muted-foreground leading-relaxed max-w-2xl">
            Each core Propriety capability maps to specific regulatory requirements. Where a
            framework has no equivalent requirement, the capability is marked not applicable
            rather than inflating coverage metrics.
          </p>
        </div>

        <CoverageMatrixSection />
      </section>

      {/* CTA */}
      <section className="py-24 px-6 max-w-2xl mx-auto text-center">
        <motion.div
          initial={{ opacity: 0, scale: 0.97 }}
          whileInView={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
          viewport={{ once: true }}
          className="glass-strong rounded-2xl p-10"
          style={{ boxShadow: "0 0 60px 0 oklch(0.65 0.18 160 / 0.12)" }}
        >
          <div className="flex items-center justify-center gap-2 mb-6">
            <div
              className="w-2 h-2 rounded-full animate-pulse"
              style={{ background: "oklch(0.65 0.18 160)" }}
            />
            <span
              className="text-xs font-mono tracking-widest uppercase"
              style={{ color: "oklch(0.65 0.18 160 / 0.7)" }}
            >
              regulatory mapping
            </span>
          </div>
          <h2 className="text-2xl font-semibold tracking-tight mb-3">
            Start your regulatory mapping
          </h2>
          <p className="text-muted-foreground text-sm mb-8 leading-relaxed">
            See exactly which of your agent actions are covered, which are gaps, and what
            constitutional policies close them — before your next audit.
          </p>
          <motion.a
            href="/assessment"
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            className="inline-flex items-center gap-2 px-6 py-3 rounded-lg font-medium text-sm"
            style={{
              background: "oklch(0.65 0.18 160)",
              color: "oklch(0.1 0 0)",
              boxShadow: "0 0 32px 0 oklch(0.65 0.18 160 / 0.35)",
            }}
          >
            Request assessment
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M5 12h14M12 5l7 7-7 7" />
            </svg>
          </motion.a>
        </motion.div>
      </section>
    </main>
  )
}
