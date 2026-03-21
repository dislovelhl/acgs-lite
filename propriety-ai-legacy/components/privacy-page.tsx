import { useRef } from "react"
import { motion, useInView } from "framer-motion"
import { Shield } from "lucide-react"
import { AnimateIn } from "@/components/animate-in"

const SECTIONS = [
  {
    number: "1",
    title: "Introduction",
    content: (
      <p className="text-muted-foreground leading-relaxed">
        Propriety AI (propriety.ai) is committed to protecting your privacy. This policy describes
        how we collect, use, and safeguard information when you use our governance platform.
        By accessing or using our services, you acknowledge that you have read and understood
        this Privacy Policy.
      </p>
    ),
  },
  {
    number: "2",
    title: "Information We Collect",
    content: (
      <div className="space-y-5">
        <div>
          <h3 className="text-sm font-mono uppercase tracking-[0.12em] text-governance/70 mb-2">
            Information you provide
          </h3>
          <p className="text-muted-foreground leading-relaxed">
            We collect information you voluntarily provide, including your name and email address
            when submitting governance assessments, and any information you include in contact form
            submissions. Assessment inputs you provide are processed to generate your governance
            report.
          </p>
        </div>
        <div>
          <h3 className="text-sm font-mono uppercase tracking-[0.12em] text-governance/70 mb-2">
            Information collected automatically
          </h3>
          <p className="text-muted-foreground leading-relaxed">
            When you interact with our platform, we automatically collect usage data including
            pages visited, features used, session duration, and device/browser information.
            Assessment inputs are logged for audit and model-improvement purposes, subject to the
            retention limits described in § 6.
          </p>
        </div>
      </div>
    ),
  },
  {
    number: "3",
    title: "How We Use Your Information",
    content: (
      <ul className="space-y-2 text-muted-foreground">
        {[
          "Provide and operate our governance assessment services",
          "Improve our constitutional models, policies, and evaluation methodology",
          "Communicate with you about your assessment results and platform updates",
          "Ensure legal compliance and enforce our terms of service",
          "Detect and prevent fraud, abuse, or security incidents",
        ].map((item) => (
          <li key={item} className="flex items-start gap-3">
            <span className="mt-1.5 w-1 h-1 rounded-full bg-governance/50 shrink-0" />
            <span className="leading-relaxed">{item}</span>
          </li>
        ))}
      </ul>
    ),
  },
  {
    number: "4",
    title: "Constitutional Hash and Audit Data",
    content: (
      <div className="space-y-4">
        <p className="text-muted-foreground leading-relaxed">
          All assessment data processed by our platform is anchored to our constitutional hash:
        </p>
        <div className="inline-flex items-center gap-2.5 px-4 py-2.5 rounded-lg border border-governance/25 bg-governance/5">
          <div className="w-5 h-5 rounded bg-governance/20 border border-governance/30 flex items-center justify-center">
            <Shield className="w-3 h-3 text-governance" />
          </div>
          <code className="font-mono text-sm text-governance tracking-wider">
            cdd01ef066bc6cf2
          </code>
        </div>
        <p className="text-muted-foreground leading-relaxed">
          Audit records generated during assessments are cryptographically signed and maintained in
          an append-only log. This architectural constraint means that certain assessment records
          cannot be deleted or modified after creation. This is a feature, not a limitation — it
          provides the tamper-evidence guarantees that make our governance reports trustworthy and
          defensible in compliance contexts.
        </p>
        <p className="text-muted-foreground leading-relaxed">
          If you submit a deletion request under § 7, we will remove your personal identifiers
          from assessment records where technically feasible, but the cryptographic audit trail
          itself will be retained for its full regulatory retention period.
        </p>
      </div>
    ),
  },
  {
    number: "5",
    title: "Data Sharing",
    content: (
      <div className="space-y-4 text-muted-foreground">
        <p className="leading-relaxed font-medium text-foreground/80">
          We do not sell your personal data. We do not share your data with third parties for
          advertising or marketing purposes.
        </p>
        <p className="leading-relaxed">
          We share data only in the following limited circumstances:
        </p>
        <ul className="space-y-2">
          {[
            "Infrastructure and cloud service providers necessary to operate the platform (subject to data processing agreements)",
            "Professional advisors (legal, accounting) under strict confidentiality obligations",
            "Law enforcement or regulatory bodies when required by applicable law or valid legal process",
            "Successors in the event of a merger, acquisition, or asset sale, with prior notice to you",
          ].map((item) => (
            <li key={item} className="flex items-start gap-3">
              <span className="mt-1.5 w-1 h-1 rounded-full bg-governance/50 shrink-0" />
              <span className="leading-relaxed">{item}</span>
            </li>
          ))}
        </ul>
      </div>
    ),
  },
  {
    number: "6",
    title: "Data Retention",
    content: (
      <div className="space-y-3">
        {[
          {
            label: "Assessment reports",
            period: "2 years",
            note: "from date of generation",
          },
          {
            label: "Audit trail records",
            period: "7 years",
            note: "regulatory and compliance requirement",
          },
          {
            label: "Account data",
            period: "Until deletion request",
            note: "subject to audit trail constraints in § 4",
          },
          {
            label: "Contact form submissions",
            period: "3 years",
            note: "or until you request deletion",
          },
        ].map(({ label, period, note }) => (
          <div
            key={label}
            className="flex items-start justify-between gap-6 py-3 border-b border-border/20 last:border-0"
          >
            <span className="text-muted-foreground leading-relaxed">{label}</span>
            <div className="text-right shrink-0">
              <span className="font-mono text-sm text-foreground/80">{period}</span>
              <p className="text-xs text-muted-foreground/50 mt-0.5">{note}</p>
            </div>
          </div>
        ))}
      </div>
    ),
  },
  {
    number: "7",
    title: "Your Rights",
    content: (
      <div className="space-y-4 text-muted-foreground">
        <p className="leading-relaxed">
          Depending on your jurisdiction (including under GDPR and applicable data protection law),
          you may have the following rights regarding your personal data:
        </p>
        <ul className="space-y-3">
          {[
            {
              right: "Right of access",
              desc: "Request a copy of the personal data we hold about you.",
            },
            {
              right: "Right to rectification",
              desc: "Request correction of inaccurate or incomplete personal data.",
            },
            {
              right: "Right to erasure",
              desc:
                "Request deletion of your personal data, subject to the audit-trail constraints described in § 4 and mandatory retention periods in § 6.",
            },
            {
              right: "Right to data portability",
              desc: "Receive your personal data in a structured, machine-readable format.",
            },
            {
              right: "Right to object",
              desc:
                "Object to processing of your personal data for certain purposes, including direct marketing.",
            },
            {
              right: "Right to restrict processing",
              desc: "Request that we limit the processing of your personal data in certain circumstances.",
            },
          ].map(({ right, desc }) => (
            <li key={right} className="flex items-start gap-3">
              <span className="mt-1.5 w-1 h-1 rounded-full bg-governance/50 shrink-0" />
              <span className="leading-relaxed">
                <span className="text-foreground/80 font-medium">{right}.</span> {desc}
              </span>
            </li>
          ))}
        </ul>
        <p className="leading-relaxed text-sm">
          To exercise any of these rights, contact us at{" "}
          <a
            href="mailto:governance@propriety.ai"
            className="text-governance hover:underline underline-offset-2"
          >
            governance@propriety.ai
          </a>
          . We will respond within 30 days.
        </p>
      </div>
    ),
  },
  {
    number: "8",
    title: "Contact",
    content: (
      <div className="space-y-4 text-muted-foreground">
        <p className="leading-relaxed">
          Questions, concerns, or requests regarding this Privacy Policy should be directed to:
        </p>
        <div className="glass-edge rounded-xl p-5 space-y-2">
          <p className="text-foreground/80 font-medium">Propriety AI — Privacy</p>
          <a
            href="mailto:governance@propriety.ai"
            className="text-governance hover:underline underline-offset-2 font-mono text-sm"
          >
            governance@propriety.ai
          </a>
          <p className="text-sm text-muted-foreground/60 pt-1 font-mono">
            Effective date: March 18, 2026
          </p>
        </div>
        <p className="leading-relaxed text-sm">
          We may update this Privacy Policy from time to time. Material changes will be
          communicated via email or a prominent notice on our platform. Continued use of our
          services after the effective date of any revision constitutes acceptance of the updated
          policy.
        </p>
      </div>
    ),
  },
]

function PolicySection({
  section,
  index,
}: {
  section: (typeof SECTIONS)[number]
  index: number
}) {
  return (
    <AnimateIn
      delay={index * 0.06}
      margin="-60px"
      className="pt-10 border-t border-border/25 first:border-0 first:pt-0"
    >
      <div className="grid grid-cols-1 md:grid-cols-[220px_1fr] gap-6 md:gap-12">
        {/* Section label */}
        <div className="flex flex-col gap-1">
          <span className="article-notation">§ {section.number}</span>
          <h2 className="font-display font-light text-2xl text-foreground/90 leading-snug">
            {section.title}
          </h2>
        </div>

        {/* Section body */}
        <div className="pt-0.5">{section.content}</div>
      </div>
    </AnimateIn>
  )
}

export function PrivacyPage() {
  const headerRef = useRef<HTMLDivElement>(null)
  const headerInView = useInView(headerRef, { once: true })

  return (
    <main className="crosshatch-bg pt-14">
      <div className="max-w-5xl mx-auto px-6 py-20 md:py-28">
        {/* Page header */}
        <motion.div
          ref={headerRef}
          initial={{ opacity: 0, y: 24 }}
          animate={headerInView ? { opacity: 1, y: 0 } : { opacity: 0, y: 24 }}
          transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
          className="mb-16 md:mb-20"
        >
          <div className="flex items-center gap-3 mb-6">
            <div className="article-notation">Legal document</div>
          </div>

          <h1 className="font-display font-light text-6xl md:text-7xl text-foreground/90 leading-none tracking-tight mb-6">
            Privacy Policy
          </h1>

          <div className="flex flex-wrap items-center gap-4 mt-6">
            <span className="text-sm text-muted-foreground">
              Effective date:{" "}
              <span className="text-foreground/70 font-medium">March 18, 2026</span>
            </span>

            <span className="w-px h-4 bg-border/40" />

            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-md border border-governance/25 bg-governance/5">
              <div className="w-4 h-4 rounded-sm bg-governance/20 border border-governance/30 flex items-center justify-center">
                <Shield className="w-2.5 h-2.5 text-governance" />
              </div>
              <span className="font-mono text-[11px] text-governance/80 tracking-wider">
                cdd01ef066bc6cf2
              </span>
            </div>

            <div className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-md border border-border/30 bg-card/30">
              <span className="w-1.5 h-1.5 rounded-full bg-governance/60" />
              <span className="font-mono text-[10px] text-muted-foreground/50 tracking-wider uppercase">
                Audit-anchored
              </span>
            </div>
          </div>
        </motion.div>

        {/* Policy sections */}
        <div className="space-y-10">
          {SECTIONS.map((section, index) => (
            <PolicySection key={section.number} section={section} index={index} />
          ))}
        </div>
      </div>
    </main>
  )
}
