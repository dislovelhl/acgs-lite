/// GitLab MR webhook handler — validates diffs against constitutional rules.
///
/// Triggered by GitLab merge_request events. Validates every added line
/// in the MR diff and posts a governance report as an MR comment.

import type { Env, GovernanceResult } from "../types.ts";
import { loadConstitution } from "../governance/constitution-store.ts";
import { buildProofHeader, createProof } from "../governance/proof.ts";
import { writeAuditRecord } from "../audit/d1-audit-log.ts";
import { generateRequestId } from "../util/ids.ts";

interface MergeRequestEvent {
  object_kind: string;
  object_attributes: {
    iid: number;
    title: string;
    source_branch: string;
    target_branch: string;
    action: string;
    author_id: number;
  };
  project: {
    id: number;
    web_url: string;
  };
}

interface DiffEntry {
  new_path: string;
  diff: string;
}

/// Handle a GitLab MR webhook event.
export async function handleGitLabWebhook(
  request: Request,
  env: Env,
  ctx: ExecutionContext,
  validator: { validate(input: string): string },
): Promise<Response> {
  // Verify webhook secret
  const secret = request.headers.get("x-gitlab-token");
  const expectedSecret = env.UPSTREAM_API_KEY; // reuse this env var for webhook secret
  if (expectedSecret && secret !== expectedSecret) {
    return new Response(JSON.stringify({ error: "Invalid webhook token" }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    });
  }

  const event: MergeRequestEvent = await request.json();

  // Only process MR open/update events
  if (event.object_kind !== "merge_request") {
    return new Response(JSON.stringify({ ok: true, skipped: "not a merge_request event" }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }

  const action = event.object_attributes.action;
  if (action !== "open" && action !== "update" && action !== "reopen") {
    return new Response(JSON.stringify({ ok: true, skipped: `action=${action}` }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }

  const requestId = generateRequestId();
  const startTime = performance.now();
  const projectId = event.project.id;
  const mrIid = event.object_attributes.iid;
  const mrTitle = event.object_attributes.title;

  // Fetch MR diff from GitLab API
  const gitlabToken = request.headers.get("x-gitlab-api-token") ?? "";
  const diffUrl = `https://gitlab.com/api/v4/projects/${projectId}/merge_requests/${mrIid}/diffs`;

  const diffResponse = await fetch(diffUrl, {
    headers: { "PRIVATE-TOKEN": gitlabToken },
  });

  if (!diffResponse.ok) {
    return new Response(
      JSON.stringify({ error: "Failed to fetch MR diffs", status: diffResponse.status }),
      { status: 502, headers: { "Content-Type": "application/json" } },
    );
  }

  const diffs: DiffEntry[] = await diffResponse.json();

  // Extract added lines from diffs
  const addedLines: { file: string; line: number; text: string }[] = [];
  for (const diff of diffs) {
    const lines = diff.diff.split("\n");
    let lineNum = 0;
    for (const line of lines) {
      if (line.startsWith("@@")) {
        const match = line.match(/\+(\d+)/);
        if (match) lineNum = parseInt(match[1], 10) - 1;
        continue;
      }
      if (line.startsWith("+") && !line.startsWith("+++")) {
        lineNum++;
        addedLines.push({
          file: diff.new_path,
          line: lineNum,
          text: line.substring(1),
        });
      } else if (!line.startsWith("-")) {
        lineNum++;
      }
    }
  }

  // Validate each added line
  const allViolations: Array<{
    file: string;
    line: number;
    violations: GovernanceResult["violations"];
  }> = [];

  let totalRulesChecked = 0;

  for (const added of addedLines) {
    if (added.text.trim().length === 0) continue;

    const result: GovernanceResult = JSON.parse(
      validator.validate(
        JSON.stringify({
          text: added.text,
          context: [
            ["action_detail", `MR !${mrIid}: ${added.file}:${added.line}`],
          ],
        }),
      ),
    );

    totalRulesChecked = result.rules_checked;

    if (result.violations.length > 0) {
      allViolations.push({
        file: added.file,
        line: added.line,
        violations: result.violations,
      });
    }
  }

  const { hash: constHash } = await loadConstitution(env.CONSTITUTIONS);
  const passed = allViolations.length === 0;
  const latency = performance.now() - startTime;

  // Build governance report
  const report = buildGovernanceReport(
    mrIid,
    mrTitle,
    passed,
    allViolations,
    constHash,
    totalRulesChecked,
    addedLines.length,
    latency,
  );

  // Post comment to MR (if we have a token)
  if (gitlabToken) {
    const commentUrl = `https://gitlab.com/api/v4/projects/${projectId}/merge_requests/${mrIid}/notes`;
    ctx.waitUntil(
      fetch(commentUrl, {
        method: "POST",
        headers: {
          "PRIVATE-TOKEN": gitlabToken,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ body: report }),
      }),
    );
  }

  // Audit log
  ctx.waitUntil(
    writeAuditRecord(env.AUDIT_DB, {
      request_id: requestId,
      phase: "request",
      valid: passed,
      violations_json: JSON.stringify(allViolations),
      constitutional_hash: constHash,
      timestamp: new Date().toISOString(),
      tenant_id: `gitlab:${projectId}`,
      endpoint: "webhook",
      model: "gitlab-duo",
      latency_ms: latency,
    }),
  );

  const proof = createProof(requestId, "request", constHash, passed, totalRulesChecked);

  return new Response(
    JSON.stringify({
      status: passed ? "PASSED" : "FAILED",
      mr: `!${mrIid}`,
      violations_count: allViolations.length,
      lines_scanned: addedLines.length,
      rules_checked: totalRulesChecked,
      constitutional_hash: constHash,
      latency_ms: Math.round(latency),
    }),
    {
      status: passed ? 200 : 422,
      headers: {
        "Content-Type": "application/json",
        "X-Governance-Proof": buildProofHeader(proof),
        "X-Request-Id": requestId,
      },
    },
  );
}

function buildGovernanceReport(
  mrIid: number,
  mrTitle: string,
  passed: boolean,
  violations: Array<{ file: string; line: number; violations: GovernanceResult["violations"] }>,
  constHash: string,
  rulesChecked: number,
  linesScanned: number,
  latencyMs: number,
): string {
  const status = passed ? "PASSED" : "FAILED";
  const icon = passed ? "white_check_mark" : "x";

  let report = `## Governance Report :${icon}:\n\n`;
  report += `| Field | Value |\n|-------|-------|\n`;
  report += `| Status | **${status}** |\n`;
  report += `| Lines Scanned | ${linesScanned} |\n`;
  report += `| Rules Checked | ${rulesChecked} |\n`;
  report += `| Violations | ${violations.length} |\n`;
  report += `| Latency | ${Math.round(latencyMs)}ms |\n`;
  report += `| Constitutional Hash | \`${constHash}\` |\n\n`;

  if (violations.length > 0) {
    report += `### Violations\n\n`;
    for (const v of violations) {
      for (const viol of v.violations) {
        report += `- **[${viol.severity.toUpperCase()}]** \`${viol.rule_id}\`: ${viol.rule_text} (\`${v.file}:${v.line}\`)\n`;
      }
    }
    report += `\n`;
  }

  report += `---\n*Generated by [ACGS Constitutional Sentinel](https://propriety.ai) on Cloudflare Workers*`;
  return report;
}
