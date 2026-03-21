import { GlareCard } from "./glare-card"
import { WordReveal } from "./word-reveal"
import { AnimateIn } from "./animate-in"

const ITEMS = [
  {
    title: "Constitutional Hash",
    description:
      "Every policy evaluation is anchored to cdd01ef066bc6cf2 — the immutable fingerprint of your governance constitution.",
    tag: "cryptographic",
  },
  {
    title: "MACI Enforcement",
    description:
      "Mandatory access control invariants enforced at middleware level. Proposer, Validator, and Executor are always separate agents.",
    tag: "architecture",
  },
  {
    title: "560ns P50 Latency",
    description:
      "Governance in the critical path without adding latency. Rust/PyO3 backend delivers sub-millisecond evaluation at production scale.",
    tag: "performance",
  },
  {
    title: "Regulatory Coverage",
    description:
      "GDPR Article 22, EU AI Act, NIST RMF, and ISO 42001 policies mapped and evaluated against every agent action.",
    tag: "compliance",
  },
  {
    title: "Audit Trail",
    description:
      "Cryptographically signed, append-only audit records. Every decision traceable and verifiable by your compliance team.",
    tag: "auditability",
  },
  {
    title: "OPA Integration",
    description:
      "Native Open Policy Agent integration. Write governance policies in Rego, deploy without any agent code changes.",
    tag: "integration",
  },
]

export function DifferentiationGrid() {
  return (
    <section id="differentiators" className="py-24 px-6 max-w-7xl mx-auto">
      <div className="mb-16">
        <div className="article-notation mb-6">§ III — Differentiators</div>
        <WordReveal
          text="Built for production AI governance"
          el="h2"
          className="font-display font-light text-4xl sm:text-5xl lg:text-6xl tracking-[-0.02em] leading-[0.95] max-w-2xl"
        />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {ITEMS.map((item, i) => (
          <AnimateIn key={item.title} delay={i * 0.07}>
            <GlareCard className="glass-edge rounded-xl p-6 h-full">
              <div className="flex items-start justify-between mb-3">
                <h3 className="font-semibold text-sm">{item.title}</h3>
                <span className="text-[10px] font-mono text-governance/60 border border-governance/20 px-1.5 py-0.5 rounded">
                  {item.tag}
                </span>
              </div>
              <p className="text-xs text-muted-foreground leading-relaxed">{item.description}</p>
            </GlareCard>
          </AnimateIn>
        ))}
      </div>
    </section>
  )
}
