import { clsx } from "clsx";
import type { Severity } from "@/lib/types";

const SEVERITY_STYLES: Record<Severity, string> = {
  CRITICAL: "badge-critical",
  HIGH: "badge-high",
  MEDIUM: "badge-medium",
  LOW: "badge-low",
};

export function SeverityBadge({ severity }: { severity: Severity }) {
  return <span className={clsx(SEVERITY_STYLES[severity])}>{severity}</span>;
}
