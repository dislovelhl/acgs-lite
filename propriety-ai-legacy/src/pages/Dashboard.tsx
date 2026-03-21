import { motion } from "framer-motion"
import { Shield } from "lucide-react"
import * as Tabs from "@radix-ui/react-tabs"
import { CONSTITUTIONAL_HASH } from "@/lib/constants"
import { HealthPanel } from "@/components/dashboard/health-panel"
import { ComplianceCards } from "@/components/dashboard/compliance-cards"
import { GovernanceFeed } from "@/components/dashboard/governance-feed"
import { AuditTrail } from "@/components/dashboard/audit-trail"
import { PipelineViz } from "@/components/dashboard/pipeline-viz"

export default function Dashboard() {
  return (
    <main className="min-h-screen crosshatch-bg pt-14">
      {/* Page header */}
      <section className="py-12 px-6 border-b border-border/30">
        <div className="max-w-7xl mx-auto">
          <motion.div
            initial={{ opacity: 0, x: -12 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.55 }}
            className="article-notation mb-4"
          >
            Governance Dashboard
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.1, ease: [0.16, 1, 0.3, 1] }}
            className="flex items-center gap-4 mb-3"
          >
            <div className="w-10 h-10 rounded-lg bg-governance/15 border border-governance/25 flex items-center justify-center">
              <Shield className="w-5 h-5 text-governance" />
            </div>
            <h1 className="font-display font-light text-3xl sm:text-4xl tracking-[-0.02em] leading-[0.95]">
              System Overview
            </h1>
          </motion.div>

          <motion.p
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.2 }}
            className="text-muted-foreground text-sm leading-relaxed max-w-xl"
          >
            Real-time governance monitoring anchored to constitutional hash{" "}
            <code className="text-governance font-mono text-xs bg-governance/10 px-1.5 py-0.5 rounded">
              {CONSTITUTIONAL_HASH}
            </code>
          </motion.p>
        </div>
      </section>

      {/* Tabbed dashboard content */}
      <div className="max-w-7xl mx-auto px-6 py-8">
        <Tabs.Root defaultValue="overview">
          <Tabs.List className="flex gap-1 mb-8 p-1 rounded-lg bg-card/30 border border-border/30 w-fit">
            <Tabs.Trigger
              value="overview"
              className="px-4 py-2 rounded-md font-mono text-xs tracking-wider uppercase transition-all
                data-[state=active]:bg-governance/15 data-[state=active]:text-governance data-[state=active]:border-governance/25
                data-[state=inactive]:text-muted-foreground/60 data-[state=inactive]:hover:text-muted-foreground
                border border-transparent"
            >
              Overview
            </Tabs.Trigger>
            <Tabs.Trigger
              value="pipeline"
              className="px-4 py-2 rounded-md font-mono text-xs tracking-wider uppercase transition-all
                data-[state=active]:bg-governance/15 data-[state=active]:text-governance data-[state=active]:border-governance/25
                data-[state=inactive]:text-muted-foreground/60 data-[state=inactive]:hover:text-muted-foreground
                border border-transparent"
            >
              Pipeline
            </Tabs.Trigger>
          </Tabs.List>

          <Tabs.Content value="overview" className="flex flex-col gap-8">
            {/* Health panel — full width row */}
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 0.25 }}
            >
              <HealthPanel />
            </motion.div>

            {/* Middle: compliance cards + governance feed */}
            <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
              {/* Compliance cards — 3 columns on desktop */}
              <motion.div
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5, delay: 0.35 }}
                className="lg:col-span-3"
              >
                <div className="mb-3">
                  <span className="font-mono text-[10px] tracking-[0.25em] text-muted-foreground/40 uppercase">
                    Compliance Frameworks
                  </span>
                </div>
                <ComplianceCards />
              </motion.div>

              {/* Governance event feed — 2 columns on desktop */}
              <motion.div
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5, delay: 0.4 }}
                className="lg:col-span-2"
              >
                <GovernanceFeed />
              </motion.div>
            </div>

            {/* Bottom: audit trail — full width */}
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 0.5 }}
            >
              <div className="mb-3">
                <span className="font-mono text-[10px] tracking-[0.25em] text-muted-foreground/40 uppercase">
                  Constitutional Audit Trail
                </span>
              </div>
              <AuditTrail />
            </motion.div>
          </Tabs.Content>

          <Tabs.Content value="pipeline">
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5 }}
            >
              <PipelineViz />
            </motion.div>
          </Tabs.Content>
        </Tabs.Root>
      </div>
    </main>
  )
}
