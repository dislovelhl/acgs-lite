import { useState } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { ArrowRight, ChevronDown } from "lucide-react"
import { PageHero } from "@/components/page-layout"
import { GlareCard } from "@/components/glare-card"
import { AnimateIn } from "@/components/animate-in"

// ── Data ──────────────────────────────────────────────────────────────────────

type BillingCycle = "monthly" | "annual"

interface Tier {
  section: string
  name: string
  monthlyPrice: number | null
  annualPrice: number | null
  customPrice: boolean
  subtitle: string
  features: string[]
  cta: string
  ctaHref: string
  highlighted: boolean
  tag?: string
}

const TIERS: Tier[] = [
  {
    section: "§ I",
    name: "Startup",
    monthlyPrice: 0,
    annualPrice: 0,
    customPrice: false,
    subtitle: "Run a governance assessment, understand your risk posture.",
    features: [
      "1 governance assessment",
      "100K policy evaluations / month",
      "GDPR + EU AI Act templates",
      "Community support",
    ],
    cta: "Start free assessment",
    ctaHref: "/assessment",
    highlighted: false,
  },
  {
    section: "§ II",
    name: "Professional",
    monthlyPrice: 499,
    annualPrice: 399,
    customPrice: false,
    subtitle: "Full constitutional enforcement for production AI deployments.",
    features: [
      "Unlimited evaluations",
      "All 4 frameworks (GDPR · EU AI Act · NIST RMF · ISO 42001)",
      "Constitutional hash enforcement",
      "MACI separation of powers",
      "Cryptographic audit trail",
      "OPA policy integration",
      "Priority email support",
    ],
    cta: "Start free trial",
    ctaHref: "/assessment",
    highlighted: true,
    tag: "Most popular",
  },
  {
    section: "§ III",
    name: "Enterprise",
    monthlyPrice: null,
    annualPrice: null,
    customPrice: true,
    subtitle: "Bespoke governance architecture for regulated industries.",
    features: [
      "Everything in Professional",
      "Custom constitutional design",
      "On-premise deployment option",
      "560ns P50 SLA guarantee",
      "Dedicated compliance engineer",
      "Custom regulatory extensions",
      "Custom audit integrations",
    ],
    cta: "Contact us",
    ctaHref: "mailto:governance@propriety.ai",
    highlighted: false,
  },
]

const FAQS: { question: string; answer: string }[] = [
  {
    question: "What counts as a policy evaluation?",
    answer:
      "A policy evaluation is any call to the OPA policy engine to adjudicate an agent action against your constitutional rules. Each agent request — data access, tool invocation, content generation — triggers one evaluation. Evaluations are counted per calendar month and reset on the first of each month.",
  },
  {
    question: "Can I change plans later?",
    answer:
      "Yes. You can upgrade from Startup to Professional at any time from your dashboard. Upgrades are effective immediately and prorated to your billing cycle. Downgrades take effect at the end of the current billing period. Enterprise contracts require a 30-day notice period.",
  },
  {
    question: "Is there a free trial on Professional?",
    answer:
      "Yes — the Professional plan includes a 14-day free trial, no credit card required at signup. You get access to all features including constitutional hash enforcement, MACI controls, and the full framework library. Your trial automatically converts to a paid subscription unless you cancel before day 14.",
  },
  {
    question: "What's included in the governance assessment?",
    answer:
      "The governance assessment is a structured five-phase process: agent inventory, risk surface analysis, constitutional design, MACI deployment planning, and a monitoring playbook. You receive a gap report, an OPA policy blueprint mapped to your agent actions, an audit architecture specification, and a MACI implementation guide. Startup accounts receive one assessment; Professional and Enterprise accounts receive unlimited assessments.",
  },
]

// ── Billing Toggle ────────────────────────────────────────────────────────────

function BillingToggle({
  cycle,
  onChange,
}: {
  cycle: BillingCycle
  onChange: (c: BillingCycle) => void
}) {
  return (
    <div className="flex items-center justify-center gap-3 mt-10">
      <button
        onClick={() => onChange("monthly")}
        className={`text-sm transition-colors ${
          cycle === "monthly" ? "text-foreground font-medium" : "text-muted-foreground"
        }`}
      >
        Monthly
      </button>

      <button
        onClick={() => onChange(cycle === "monthly" ? "annual" : "monthly")}
        aria-label="Toggle billing cycle"
        className="relative w-11 h-6 rounded-full border border-border/60 bg-background/60 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-governance/50"
        style={
          cycle === "annual"
            ? { backgroundColor: "oklch(0.65 0.18 160 / 0.18)", borderColor: "oklch(0.65 0.18 160 / 0.4)" }
            : {}
        }
      >
        <motion.span
          className="absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-governance"
          animate={{ x: cycle === "annual" ? 20 : 0 }}
          transition={{ type: "spring", stiffness: 400, damping: 32 }}
        />
      </button>

      <button
        onClick={() => onChange("annual")}
        className={`text-sm transition-colors flex items-center gap-1.5 ${
          cycle === "annual" ? "text-foreground font-medium" : "text-muted-foreground"
        }`}
      >
        Annual
        <span className="text-[10px] font-mono uppercase tracking-wider text-governance bg-governance/10 border border-governance/25 px-1.5 py-0.5 rounded">
          save 20%
        </span>
      </button>
    </div>
  )
}

// ── Feature Dot List ──────────────────────────────────────────────────────────

function FeatureList({ features }: { features: string[] }) {
  return (
    <ul className="space-y-3 mt-6">
      {features.map((feature) => (
        <li key={feature} className="flex items-start gap-3">
          <span className="mt-[5px] flex-shrink-0 w-1.5 h-1.5 rounded-full bg-governance" />
          <span className="text-sm text-muted-foreground leading-snug">{feature}</span>
        </li>
      ))}
    </ul>
  )
}

// ── Price Display ─────────────────────────────────────────────────────────────

function PriceDisplay({
  tier,
  cycle,
}: {
  tier: Tier
  cycle: BillingCycle
}) {
  if (tier.customPrice) {
    return (
      <div className="mt-6 mb-1">
        <span className="font-display font-light text-5xl tracking-[-0.02em]">Custom</span>
      </div>
    )
  }

  const price = cycle === "annual" ? tier.annualPrice : tier.monthlyPrice
  const isFree = price === 0

  return (
    <div className="mt-6 mb-1 flex items-end gap-1">
      {!isFree && (
        <span className="text-xl text-muted-foreground mb-2 font-light">$</span>
      )}
      <AnimatePresence mode="wait">
        <motion.span
          key={`${tier.name}-${cycle}`}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -6 }}
          transition={{ duration: 0.2 }}
          className="font-display font-light text-5xl tracking-[-0.02em]"
        >
          {isFree ? "Free" : price}
        </motion.span>
      </AnimatePresence>
      {!isFree && (
        <span className="text-sm text-muted-foreground mb-2 ml-0.5">/ mo</span>
      )}
    </div>
  )
}

// ── Tier Card ─────────────────────────────────────────────────────────────────

function TierCard({
  tier,
  cycle,
  index,
}: {
  tier: Tier
  cycle: BillingCycle
  index: number
}) {
  return (
    <AnimateIn
      delay={index * 0.1}
      offset={24}
      duration={0.55}
      className="relative flex flex-col"
    >
      <GlareCard
        className={`glass-edge rounded-xl flex-1 ${
          tier.highlighted ? "border border-governance/50" : ""
        }`}
      >
        <div
          className="p-8 flex flex-col h-full"
          style={
            tier.highlighted
              ? { boxShadow: "0 0 40px 0 oklch(0.65 0.18 160 / 0.18)" }
              : undefined
          }
        >
          {/* Header */}
          <div>
            {tier.tag && (
              <div className="mb-3 flex">
                <span className="text-[10px] font-mono uppercase tracking-[0.2em] text-governance bg-governance/10 border border-governance/25 px-2 py-0.5 rounded">
                  {tier.tag}
                </span>
              </div>
            )}

            <div className="flex items-baseline gap-2 mb-1">
              <span className="text-[10px] font-mono text-muted-foreground/50 tracking-widest uppercase">
                {tier.section}
              </span>
              <span className="text-[10px] font-mono text-muted-foreground/30">—</span>
              <h3 className="text-sm font-semibold tracking-tight">{tier.name}</h3>
            </div>

            <PriceDisplay tier={tier} cycle={cycle} />

            {cycle === "annual" && !tier.customPrice && tier.monthlyPrice !== 0 && (
              <p className="text-[11px] font-mono text-muted-foreground/50 mt-1">
                billed annually · ${(tier.annualPrice! * 12).toLocaleString()} / yr
              </p>
            )}

            <p className="text-sm text-muted-foreground mt-3 leading-relaxed">
              {tier.subtitle}
            </p>
          </div>

          {/* Divider */}
          <div className="my-6 h-px bg-border/30" />

          {/* Features */}
          <div className="flex-1">
            <FeatureList features={tier.features} />
          </div>

          {/* CTA */}
          <div className="mt-8">
            <motion.a
              href={tier.ctaHref}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              className={`w-full inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                tier.highlighted
                  ? "bg-governance text-background"
                  : "border border-border/60 text-foreground hover:border-governance/40 hover:text-governance"
              }`}
              style={
                tier.highlighted
                  ? { boxShadow: "0 0 24px 0 oklch(0.65 0.18 160 / 0.30)" }
                  : undefined
              }
            >
              {tier.cta}
              <ArrowRight className="w-3.5 h-3.5" />
            </motion.a>
          </div>
        </div>
      </GlareCard>
    </AnimateIn>
  )
}

// ── FAQ Accordion ─────────────────────────────────────────────────────────────

function FaqItem({
  faq,
  index,
}: {
  faq: (typeof FAQS)[0]
  index: number
}) {
  const [open, setOpen] = useState(false)

  return (
    <AnimateIn
      delay={index * 0.07}
      offset={12}
      margin="-24px"
      duration={0.45}
      className="glass-edge rounded-xl overflow-hidden"
    >
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between gap-4 px-6 py-5 text-left group"
        aria-expanded={open}
      >
        <span className="text-sm font-medium leading-snug">{faq.question}</span>
        <motion.span
          animate={{ rotate: open ? 180 : 0 }}
          transition={{ duration: 0.25 }}
          className="flex-shrink-0 text-muted-foreground group-hover:text-governance transition-colors"
        >
          <ChevronDown className="w-4 h-4" />
        </motion.span>
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            key="content"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
            className="overflow-hidden"
          >
            <p className="px-6 pb-5 text-sm text-muted-foreground leading-relaxed">
              {faq.answer}
            </p>
          </motion.div>
        )}
      </AnimatePresence>
    </AnimateIn>
  )
}

// ── Main Component ────────────────────────────────────────────────────────────

export function PricingPage() {
  const [cycle, setCycle] = useState<BillingCycle>("monthly")

  return (
    <main className="min-h-screen crosshatch-bg pt-14">
      {/* Hero */}
      <PageHero
        label="§ V — Pricing"
        title="Governance at every scale."
        description="From a free risk assessment to full constitutional enforcement for regulated enterprise deployments — governance that grows with your AI surface area."
      >
        <BillingToggle cycle={cycle} onChange={setCycle} />
      </PageHero>

      {/* Tier Cards */}
      <section className="py-20 px-6 max-w-6xl mx-auto">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {TIERS.map((tier, i) => (
            <TierCard key={tier.name} tier={tier} cycle={cycle} index={i} />
          ))}
        </div>

        <p className="mt-8 text-center text-xs font-mono text-muted-foreground/40 tracking-wide">
          All plans include 99.9% uptime SLA · SOC 2 Type II in progress · EU data residency available
        </p>
      </section>

      {/* FAQ */}
      <section className="py-16 px-6 max-w-3xl mx-auto">
        <AnimateIn offset={16} className="mb-10 text-center">
          <div className="article-notation justify-center mb-4">§ — FAQ</div>
          <h2 className="font-display font-light text-3xl tracking-[-0.02em]">
            Common questions
          </h2>
        </AnimateIn>

        <div className="space-y-3">
          {FAQS.map((faq, i) => (
            <FaqItem key={faq.question} faq={faq} index={i} />
          ))}
        </div>
      </section>

      {/* CTA Strip */}
      <section className="py-20 px-6 max-w-2xl mx-auto text-center">
        <motion.div
          initial={{ opacity: 0, scale: 0.97 }}
          whileInView={{ opacity: 1, scale: 1 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
          className="glass-edge rounded-2xl p-10"
          style={{ boxShadow: "0 0 60px 0 oklch(0.65 0.18 160 / 0.10)" }}
        >
          <div className="flex items-center justify-center gap-2 mb-5">
            <span className="w-1.5 h-1.5 rounded-full bg-governance animate-pulse" />
            <span className="text-[10px] font-mono text-governance/70 tracking-[0.2em] uppercase">
              no commitment required
            </span>
          </div>

          <h2 className="font-display font-light text-3xl tracking-[-0.02em] mb-3">
            Not sure which plan?
          </h2>
          <p className="text-muted-foreground text-sm leading-relaxed mb-8">
            Start with the free assessment. We'll map your agent actions to regulatory requirements and
            recommend the right governance architecture — before you pay anything.
          </p>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
            <motion.a
              href="/assessment"
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              className="inline-flex items-center gap-2 px-6 py-3 rounded-lg bg-governance text-background font-medium text-sm"
              style={{ boxShadow: "0 0 32px 0 oklch(0.65 0.18 160 / 0.35)" }}
            >
              Start free assessment
              <ArrowRight className="w-4 h-4" />
            </motion.a>

            <motion.a
              href="mailto:governance@propriety.ai"
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              className="inline-flex items-center gap-2 px-6 py-3 rounded-lg border border-border/60 text-sm font-medium text-muted-foreground hover:text-foreground hover:border-governance/40 transition-colors"
            >
              Talk to sales
            </motion.a>
          </div>
        </motion.div>
      </section>
    </main>
  )
}
