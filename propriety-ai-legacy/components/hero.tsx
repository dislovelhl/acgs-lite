import { motion } from "framer-motion"
import { ArrowRight } from "lucide-react"
import { DotMatrix } from "./dot-matrix"

export function Hero() {
  return (
    <section
      className="relative min-h-screen flex items-center overflow-hidden px-6 pt-32 pb-24"
      style={{
        background:
          "radial-gradient(ellipse 80% 60% at 30% 5%, oklch(0.65 0.18 160 / 0.09), transparent 60%), radial-gradient(ellipse 60% 40% at 80% 80%, oklch(0.65 0.18 160 / 0.04), transparent 50%)",
      }}
    >
      {/* Dot matrix — right side architectural decoration */}
      <div className="absolute right-6 top-1/2 -translate-y-1/2 opacity-[0.18] hidden xl:block pointer-events-none">
        <DotMatrix cols={26} rows={22} gap={18} />
      </div>

      {/* Vertical left accent rule */}
      <div
        className="absolute left-6 top-32 bottom-24 w-px hidden lg:block pointer-events-none"
        style={{
          background:
            "linear-gradient(to bottom, transparent, oklch(0.65 0.18 160 / 0.35) 20%, oklch(0.65 0.18 160 / 0.35) 80%, transparent)",
        }}
      />

      <div className="relative z-10 max-w-7xl mx-auto w-full">
        {/* Article notation */}
        <motion.div
          initial={{ opacity: 0, x: -12 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.55 }}
          className="article-notation mb-10"
        >
          Article I — Constitutional Governance
        </motion.div>

        {/* Main headline — Cormorant Garamond at maximum impact */}
        <motion.h1
          initial={{ opacity: 0, y: 40 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 1, delay: 0.1, ease: [0.16, 1, 0.3, 1] }}
          className="font-display font-light leading-[0.9] tracking-[-0.02em] mb-10"
          style={{ fontSize: "clamp(4rem, 10vw, 9.5rem)" }}
        >
          The governed
          <br />
          <em
            className="not-italic"
            style={{ color: "oklch(0.65 0.18 160)" }}
          >
            machine.
          </em>
        </motion.h1>

        {/* Subtext */}
        <motion.p
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.65, delay: 0.38 }}
          className="text-lg text-muted-foreground max-w-lg leading-relaxed mb-12"
        >
          Constitutional constraints enforced in microseconds — before every
          agent action, not after the fact. MACI-verified policy evaluation
          with cryptographic audit trails your compliance team can trust.
        </motion.p>

        {/* CTAs */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.55 }}
          className="flex flex-col sm:flex-row items-start gap-4 mb-20"
        >
          <a
            href="/assessment"
            className="inline-flex items-center gap-2 px-6 py-3 rounded-lg bg-governance text-background font-medium text-sm transition-opacity hover:opacity-90"
            style={{ boxShadow: "0 0 36px 0 oklch(0.65 0.18 160 / 0.38)" }}
          >
            Start governance assessment
            <ArrowRight className="w-4 h-4" />
          </a>
          <a
            href="#how-it-works"
            className="inline-flex items-center gap-2 px-6 py-3 rounded-lg border border-border/60 text-sm text-muted-foreground hover:text-foreground hover:border-border transition-colors"
          >
            See how it works
          </a>
        </motion.div>

        {/* Metric strip */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.7, delay: 0.75 }}
          className="flex flex-wrap items-stretch gap-px border border-border/25 rounded-lg overflow-hidden w-fit"
        >
          {[
            { value: "560ns", label: "P50 validation" },
            { value: "MACI", label: "separation of powers" },
            { value: "cdd01ef0…", label: "constitutional hash" },
            { value: "4 frameworks", label: "GDPR · EU AI Act · NIST · ISO" },
          ].map(({ value, label }) => (
            <div
              key={label}
              className="flex flex-col gap-0.5 px-5 py-3 bg-card/40"
            >
              <span className="font-mono text-xs text-governance">{value}</span>
              <span className="text-[10px] text-muted-foreground/50">{label}</span>
            </div>
          ))}
        </motion.div>
      </div>
    </section>
  )
}
