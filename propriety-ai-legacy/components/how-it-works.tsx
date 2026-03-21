import { WordReveal } from "./word-reveal"
import { AnimateIn } from "./animate-in"

const STEPS = [
  {
    number: "01",
    title: "Agent proposes action",
    description:
      "The governed agent submits an action request with full context to the constitutional engine.",
  },
  {
    number: "02",
    title: "Constitutional evaluation",
    description:
      "Policies are evaluated in microseconds against the immutable constitutional hash, with full OPA integration.",
  },
  {
    number: "03",
    title: "MACI validation",
    description:
      "A separate validator — never the proposer — independently verifies the decision before execution.",
  },
  {
    number: "04",
    title: "Execution or block",
    description:
      "Compliant actions proceed. Non-compliant actions are blocked with a cryptographically signed audit record.",
  },
]

export function HowItWorks() {
  return (
    <section id="how-it-works" className="py-24 px-6 max-w-7xl mx-auto">
      <div className="mb-16">
        <div className="article-notation mb-6">§ II — Enforcement Pipeline</div>
        <WordReveal
          text="Governance in the critical path, not a sidecar"
          el="h2"
          className="font-display font-light text-4xl sm:text-5xl lg:text-6xl tracking-[-0.02em] leading-[0.95] max-w-3xl"
        />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {STEPS.map((step, i) => (
          <AnimateIn
            key={step.number}
            delay={i * 0.1}
            offset={24}
            className="glass-edge rounded-xl p-6 border-t-2"
            style={{ borderTopColor: "oklch(0.65 0.18 160 / 0.4)" }}
          >
            <div
              className="font-display font-light text-4xl leading-none mb-5"
              style={{ color: "oklch(0.65 0.18 160 / 0.35)" }}
            >
              {step.number}
            </div>
            <h3 className="font-medium mb-2 text-sm tracking-tight">{step.title}</h3>
            <p className="text-xs text-muted-foreground leading-relaxed">{step.description}</p>
          </AnimateIn>
        ))}
      </div>
    </section>
  )
}
