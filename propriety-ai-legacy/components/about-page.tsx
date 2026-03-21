import { motion } from "framer-motion"
import { ArrowRight, Shield, Lock, Zap, Layers } from "lucide-react"
import { PageHero } from "@/components/page-layout"
import { WordReveal } from "@/components/word-reveal"
import { AnimateIn } from "@/components/animate-in"
import { CONSTITUTIONAL_HASH } from "@/lib/constants"

// ── Types ──────────────────────────────────────────────────────────────────────

interface Value {
  section: string
  title: string
  description: string
  icon: React.ElementType
}

const VALUES: Value[] = [
  {
    section: "§ 1",
    title: "Constitutional First",
    description:
      "Governance lives in the critical path, not a sidecar. Every agent action is evaluated against constitutional constraints before execution — not logged afterward, not sampled, not approximated.",
    icon: Shield,
  },
  {
    section: "§ 2",
    title: "MACI Architecture",
    description:
      "Mandatory access control invariants enforced at the middleware layer. Proposer, Validator, and Executor are always separate agents. No system may validate its own output — this is structurally enforced, not aspirational.",
    icon: Layers,
  },
  {
    section: "§ 3",
    title: "Cryptographic Transparency",
    description:
      "Every governance decision is anchored to an immutable constitutional hash and cryptographically signed. The audit trail is append-only. Your compliance team can verify any decision independently.",
    icon: Lock,
  },
  {
    section: "§ 4",
    title: "Zero Latency Compromise",
    description:
      "Production governance at 560ns P50. Constitutional enforcement at this latency is an engineering achievement — it is also a design requirement. If governance adds meaningful latency, we have not done our job.",
    icon: Zap,
  },
]

// ── ValueCard ──────────────────────────────────────────────────────────────────

function ValueCard({ value, index }: { value: Value; index: number }) {
  const Icon = value.icon

  return (
    <AnimateIn
      delay={index * 0.09}
      duration={0.55}
      className="glass-edge rounded-xl p-6 flex flex-col gap-4"
    >
      <div className="flex items-start justify-between">
        <div className="w-9 h-9 rounded-lg bg-governance/10 border border-governance/20 flex items-center justify-center flex-shrink-0">
          <Icon className="w-4 h-4 text-governance" />
        </div>
        <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground/40 pt-1">
          {value.section}
        </span>
      </div>
      <div>
        <h3 className="font-semibold text-sm mb-2 tracking-tight">{value.title}</h3>
        <p className="text-xs text-muted-foreground leading-relaxed">{value.description}</p>
      </div>
    </AnimateIn>
  )
}

// ── Main component ─────────────────────────────────────────────────────────────

export function AboutPage() {
  return (
    <main className="min-h-screen crosshatch-bg pt-14">
      {/* ── Section 1: Hero ── */}
      <PageHero
        label="§ VI — Company"
        title="We build the constitutional layer for AI."
        description="Propriety AI exists because the governance problem for autonomous agents is structural, not procedural. It requires a different kind of architecture — one where constraints are constitutional."
      />

      {/* ── Section 2: Mission Statement ── */}
      <section className="py-28 px-6 max-w-5xl mx-auto">
        <AnimateIn margin="-60px" offset={24} duration={0.65}>
          <div className="article-notation mb-10">Our mission</div>
        </AnimateIn>

        <div className="grid grid-cols-1 lg:grid-cols-[1fr_1.15fr] gap-16 items-start">
          {/* Left: editorial quote */}
          <AnimateIn delay={0.05} margin="-60px" offset={24} duration={0.65}>
            <blockquote className="font-display font-light text-2xl leading-[1.4] tracking-[-0.01em] italic text-foreground/90">
              "Constitutional governance is not a compliance checkbox. It is the only sustainable
              architecture for AI systems that must be trusted — by regulators, by users, by the
              organizations that deploy them."
            </blockquote>
          </AnimateIn>

          {/* Right: supporting body copy */}
          <div className="space-y-5">
            <AnimateIn delay={0.12} margin="-60px" offset={24} duration={0.65}>
              <p className="text-sm text-muted-foreground leading-relaxed">
                The MACI (Mandatory Access Control Invariants) architecture separates every agent
                interaction into three structurally distinct roles: Proposer, Validator, and
                Executor. These roles can never collapse into one agent. This is not a policy
                recommendation — it is a hard constraint enforced at the middleware layer, before
                any action reaches execution.
              </p>
            </AnimateIn>
            <AnimateIn delay={0.18} margin="-60px" offset={24} duration={0.65}>
              <p className="text-sm text-muted-foreground leading-relaxed">
                Every governance constitution is fingerprinted with an immutable cryptographic
                hash. When any policy evaluation occurs, the system verifies the evaluation against
                that hash. This means governance drift is detectable at the cryptographic level, not
                discovered in a post-incident review. The audit trail is append-only and verifiable
                by any independent party — including the regulators who will eventually require it.
              </p>
            </AnimateIn>
          </div>
        </div>
      </section>

      {/* ── Section 3: Values grid ── */}
      <section className="py-24 px-6 max-w-7xl mx-auto">
        <div className="mb-14 text-center">
          <AnimateIn margin="-60px" offset={24} duration={0.65}>
            <p className="text-xs font-mono uppercase tracking-[0.2em] text-muted-foreground/50 mb-5">
              // governing principles
            </p>
          </AnimateIn>
          <WordReveal
            text="Built on four invariants."
            el="h2"
            className="font-display font-light text-4xl sm:text-5xl tracking-[-0.02em] leading-[0.95]"
          />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {VALUES.map((value, i) => (
            <ValueCard key={value.title} value={value} index={i} />
          ))}
        </div>
      </section>

      {/* ── Section 4: Constitutional Hash band ── */}
      <section className="relative py-28 px-6 overflow-hidden">
        {/* Background glow */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            background:
              "radial-gradient(ellipse 70% 80% at 50% 50%, oklch(0.65 0.18 160 / 0.07), transparent 70%)",
          }}
        />
        {/* Top / bottom rule lines */}
        <div
          className="absolute inset-x-0 top-0 h-px"
          style={{
            background:
              "linear-gradient(to right, transparent, oklch(0.65 0.18 160 / 0.2) 30%, oklch(0.65 0.18 160 / 0.2) 70%, transparent)",
          }}
        />
        <div
          className="absolute inset-x-0 bottom-0 h-px"
          style={{
            background:
              "linear-gradient(to right, transparent, oklch(0.65 0.18 160 / 0.2) 30%, oklch(0.65 0.18 160 / 0.2) 70%, transparent)",
          }}
        />

        <div className="relative z-10 max-w-3xl mx-auto text-center">
          <AnimateIn margin="-60px" offset={24} duration={0.65}>
            <div className="article-notation justify-center mb-8">Constitutional anchor</div>
          </AnimateIn>

          <AnimateIn delay={0.08} margin="-60px" offset={24} duration={0.65}>
            <h2 className="font-display font-light text-4xl sm:text-5xl tracking-[-0.02em] leading-[0.95] mb-10">
              Our governance is anchored.
            </h2>
          </AnimateIn>

          {/* Hash badge */}
          <AnimateIn delay={0.15} margin="-60px" offset={24} duration={0.65}>
            <motion.div
              className="inline-flex items-center gap-3 mb-8"
              whileHover={{ scale: 1.02 }}
              transition={{ duration: 0.2 }}
            >
              <div
                className="glass-edge rounded-xl px-7 py-4 flex items-center gap-4"
                style={{ boxShadow: "0 0 48px 0 oklch(0.65 0.18 160 / 0.15)" }}
              >
                <div className="w-2 h-2 rounded-full bg-governance animate-pulse flex-shrink-0" />
                <span
                  className="font-mono text-xl sm:text-2xl tracking-[0.12em] text-governance"
                  style={{ fontVariantNumeric: "tabular-nums" }}
                >
                  {CONSTITUTIONAL_HASH}
                </span>
              </div>
            </motion.div>
          </AnimateIn>

          <AnimateIn delay={0.2} margin="-60px" offset={24} duration={0.65}>
            <p className="text-sm text-muted-foreground leading-relaxed max-w-xl mx-auto">
              The immutable fingerprint of our governance constitution. Every policy evaluation is
              verified against this hash at runtime — drift is detected cryptographically, not
              discovered in a post-incident report.
            </p>
          </AnimateIn>

          {/* Decorative mono detail */}
          <AnimateIn delay={0.26} margin="-60px" offset={24} duration={0.65}>
            <div className="mt-10 flex items-center justify-center gap-6 text-[10px] font-mono text-muted-foreground/35 uppercase tracking-[0.18em]">
              <span>SHA-256 anchored</span>
              <span className="w-px h-3 bg-border/40" />
              <span>Append-only audit trail</span>
              <span className="w-px h-3 bg-border/40" />
              <span>Independent verification</span>
            </div>
          </AnimateIn>
        </div>
      </section>

      {/* ── Section 5: CTA ── */}
      <section className="py-28 px-6 max-w-2xl mx-auto text-center">
        <motion.div
          initial={{ opacity: 0, scale: 0.97 }}
          whileInView={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.55, ease: [0.16, 1, 0.3, 1] }}
          viewport={{ once: true }}
          className="glass-edge rounded-2xl p-10 sm:p-14"
          style={{ boxShadow: "0 0 72px 0 oklch(0.65 0.18 160 / 0.1)" }}
        >
          <div className="flex items-center justify-center gap-2 mb-7">
            <div className="w-2 h-2 rounded-full bg-governance animate-pulse" />
            <span className="text-[10px] font-mono text-governance/70 tracking-[0.2em] uppercase">
              ready to govern
            </span>
          </div>

          <h2 className="font-display font-light text-3xl sm:text-4xl tracking-[-0.02em] leading-[1.1] mb-4">
            Ready to constitutional-govern your AI?
          </h2>

          <p className="text-sm text-muted-foreground leading-relaxed mb-10 max-w-md mx-auto">
            Start with a governance assessment — a structured analysis of your agent action surface
            mapped to MACI enforcement requirements and regulatory obligations.
          </p>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <motion.a
              href="/assessment"
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              className="inline-flex items-center gap-2 px-7 py-3.5 rounded-lg bg-governance text-background font-medium text-sm"
              style={{ boxShadow: "0 0 36px 0 oklch(0.65 0.18 160 / 0.38)" }}
            >
              Start governance assessment
              <ArrowRight className="w-4 h-4" />
            </motion.a>
            <motion.a
              href="mailto:governance@propriety.ai"
              whileHover={{ scale: 1.01 }}
              whileTap={{ scale: 0.98 }}
              className="inline-flex items-center gap-2 px-7 py-3.5 rounded-lg border border-border/50 text-sm text-muted-foreground hover:text-foreground hover:border-border transition-colors"
            >
              Contact the team
            </motion.a>
          </div>
        </motion.div>
      </section>
    </main>
  )
}
