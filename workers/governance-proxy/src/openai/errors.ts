/// OpenAI-compatible error responses for governance denials.

import type { GovernanceViolation } from "../types.ts";

interface OpenAIError {
  error: {
    message: string;
    type: string;
    code: string;
    param: string | null;
  };
}

export function governanceDeniedError(
  violations: GovernanceViolation[],
  phase: "request" | "response",
): OpenAIError {
  const violationSummary = violations
    .map((v) => `[${v.severity.toUpperCase()}] ${v.rule_id}: ${v.rule_text}`)
    .join("; ");

  return {
    error: {
      message: `Governance violation (${phase}): ${violationSummary}`,
      type: "governance_error",
      code: "governance_denied",
      param: null,
    },
  };
}

export function governanceDeniedResponse(
  violations: GovernanceViolation[],
  phase: "request" | "response",
  headers: Record<string, string>,
): Response {
  const body = governanceDeniedError(violations, phase);
  return new Response(JSON.stringify(body), {
    status: 403,
    headers: {
      "Content-Type": "application/json",
      ...headers,
    },
  });
}
