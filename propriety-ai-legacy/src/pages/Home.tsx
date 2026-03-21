import { ArrowRight, Mail } from "lucide-react"
import { CONSTITUTIONAL_HASH } from "@/lib/constants"
import { Hero } from "@/components/hero"
import { HowItWorks } from "@/components/how-it-works"
import { MetricsBar } from "@/components/metrics-bar"
import { DifferentiationGrid } from "@/components/differentiation-grid"
import { PolicyLogStream } from "@/components/policy-log-stream-client"

export default function Home() {
  return (
    <main className="min-h-screen crosshatch-bg pt-14">
      <Hero />
      <HowItWorks />
      <MetricsBar />

      {/* Live enforcement */}
      <section id="live-enforcement" className="py-24 px-6 max-w-7xl mx-auto">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-16 items-center">
          <div>
            <div className="article-notation mb-6">§ I — Live Enforcement</div>
            <h2 className="font-display font-light text-4xl sm:text-5xl tracking-[-0.02em] leading-[0.95] mb-5">
              Governance enforced
              <br />
              <em className="not-italic" style={{ color: "oklch(0.65 0.18 160)" }}>
                before every action
              </em>
            </h2>
            <p className="text-muted-foreground leading-relaxed mb-6">
              Every agent action passes through the constitutional engine. Policies evaluated in
              microseconds against{" "}
              <code className="text-governance font-mono text-sm bg-governance/10 px-1.5 py-0.5 rounded">
                {CONSTITUTIONAL_HASH}
              </code>{" "}
              — the immutable hash anchoring your governance constitution.
            </p>
            <div className="flex flex-col gap-3">
              {[
                "Sub-millisecond policy evaluation",
                "Cryptographic audit trails",
                "GDPR, EU AI Act, NIST RMF coverage",
              ].map((item) => (
                <div key={item} className="flex items-center gap-3">
                  <div className="w-1.5 h-1.5 rounded-full bg-governance flex-shrink-0" />
                  <span className="text-sm text-muted-foreground">{item}</span>
                </div>
              ))}
            </div>
          </div>
          <div>
            <PolicyLogStream />
          </div>
        </div>
      </section>

      <DifferentiationGrid />

      {/* Contact */}
      <section id="contact" className="py-24 px-6 max-w-3xl mx-auto text-center">
        <div className="article-notation justify-center mb-6">§ IV — Get in Touch</div>
        <h2 className="font-display font-light text-4xl sm:text-5xl tracking-[-0.02em] leading-[0.95] mb-5">
          Ready to govern your AI agents?
        </h2>
        <p className="text-muted-foreground leading-relaxed mb-10 max-w-xl mx-auto">
          Whether you need a governance assessment, a custom policy deployment, or just want to
          understand your risk posture — we can help.
        </p>
        <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
          <a
            href="/assessment"
            className="inline-flex items-center gap-2 px-6 py-3 rounded-lg bg-governance text-background font-medium text-sm"
            style={{ boxShadow: "0 0 28px 0 oklch(0.65 0.18 160 / 0.3)" }}
          >
            Start governance assessment
            <ArrowRight className="w-4 h-4" />
          </a>
          <a
            href="mailto:governance@propriety.ai"
            className="inline-flex items-center gap-2 px-6 py-3 rounded-lg border border-border/60 text-sm text-muted-foreground hover:text-foreground hover:border-border transition-colors"
          >
            <Mail className="w-4 h-4" />
            governance@propriety.ai
          </a>
        </div>
      </section>
    </main>
  )
}
