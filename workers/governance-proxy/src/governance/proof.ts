/// X-Governance-Proof header generation.

import type { GovernanceProof } from "../types.ts";

/// Build the X-Governance-Proof header value.
export function buildProofHeader(proof: GovernanceProof): string {
  return [
    `v1`,
    `req=${proof.requestId}`,
    `phase=${proof.phase}`,
    `const=${proof.constitutionalHash}`,
    `result=${proof.result}`,
    `rules=${proof.rulesChecked}`,
  ].join("; ");
}

/// Create a proof object from validation results.
export function createProof(
  requestId: string,
  phase: "request" | "response",
  constitutionalHash: string,
  valid: boolean,
  rulesChecked: number,
): GovernanceProof {
  return {
    version: "v1",
    requestId,
    phase,
    constitutionalHash,
    result: valid ? "allow" : "deny",
    rulesChecked,
  };
}
