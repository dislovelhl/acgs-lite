/// ACGS Governance Proxy — Cloudflare Worker entry point.
///
/// Sits between AI clients and upstream LLM APIs, validating every
/// request and response against a constitutional governance engine.
///
/// Constitutional Hash: cdd01ef066bc6cf2

import type { Env, GovernanceResult } from "./types.ts";
import { matchEndpoint, healthResponse } from "./router.ts";
import {
  extractRequestText,
  extractModel,
  extractSystemPrompt,
  isStreaming,
  extractResponseText,
} from "./openai/normalize.ts";
import { governanceDeniedResponse } from "./openai/errors.ts";
import { proxyToUpstream, resolveUpstream } from "./openai/proxy.ts";
import { loadConstitution } from "./governance/constitution-store.ts";
import { validate } from "./governance/wasm-validator.ts";
import { buildProofHeader, createProof } from "./governance/proof.ts";
import { writeAuditRecord } from "./audit/d1-audit-log.ts";
import { generateRequestId } from "./util/ids.ts";
import { handleGitLabWebhook } from "./gitlab/webhook.ts";
import wasmModule from "../wasm/acgs_validator_wasm_bg.wasm";
import initWasm, { WasmValidator } from "../wasm/acgs_validator_wasm.js";

// WASM validator — lazy-initialized per isolate
let wasmValidator: WasmValidator | null = null;
let wasmHash: string | null = null;
let wasmInitialized = false;

async function initValidator(
  configJson: string,
  hash: string,
): Promise<WasmValidator> {
  if (wasmValidator !== null && wasmHash === hash) {
    return wasmValidator;
  }

  if (!wasmInitialized) {
    await initWasm(wasmModule);
    wasmInitialized = true;
  }

  wasmValidator = new WasmValidator(configJson);
  wasmHash = hash;
  return wasmValidator;
}

export default {
  async fetch(
    request: Request,
    env: Env,
    ctx: ExecutionContext,
  ): Promise<Response> {
    const url = new URL(request.url);

    // Health check
    if (url.pathname === "/health" || url.pathname === "/") {
      return healthResponse();
    }

    // Admin endpoints require ADMIN_SECRET bearer token
    if (url.pathname.startsWith("/admin/")) {
      if (!env.ADMIN_SECRET) {
        return new Response(
          JSON.stringify({ error: "Admin endpoints disabled: ADMIN_SECRET not configured" }),
          { status: 503, headers: { "Content-Type": "application/json" } },
        );
      }
      const authHeader = request.headers.get("Authorization");
      if (authHeader !== `Bearer ${env.ADMIN_SECRET}`) {
        return new Response(
          JSON.stringify({ error: "Unauthorized" }),
          { status: 401, headers: { "Content-Type": "application/json" } },
        );
      }
    }

    // Admin: upload constitution to KV
    if (url.pathname === "/admin/constitution" && request.method === "PUT") {
      try {
        const configJson = await request.text();
        const config = JSON.parse(configJson);
        const hash = config.const_hash;
        if (!hash) {
          return new Response(
            JSON.stringify({ error: "const_hash required in config" }),
            { status: 400, headers: { "Content-Type": "application/json" } },
          );
        }
        // Store constitution config
        await env.CONSTITUTIONS.put(`constitution:${hash}`, configJson);
        // Update active pointer
        await env.CONSTITUTIONS.put(
          "constitution:active",
          JSON.stringify({ hash, version: "1.0.0", updated_at: new Date().toISOString() }),
        );
        return new Response(
          JSON.stringify({ ok: true, hash, rules: config.rule_data?.length ?? 0 }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Upload failed";
        return new Response(
          JSON.stringify({ error: msg }),
          { status: 400, headers: { "Content-Type": "application/json" } },
        );
      }
    }

    // Admin: query audit log
    if (url.pathname === "/admin/audit" && request.method === "GET") {
      const limit = parseInt(url.searchParams.get("limit") ?? "20", 10);
      const result = await env.AUDIT_DB
        .prepare("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?")
        .bind(limit)
        .all();
      return new Response(JSON.stringify(result.results), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    // GitLab webhook endpoint
    if (url.pathname === "/webhook" && request.method === "POST") {
      const { configJson, hash: constHash } = await loadConstitution(env.CONSTITUTIONS);
      const validator = await initValidator(configJson, constHash);
      return handleGitLabWebhook(request, env, ctx, validator);
    }

    // Route matching
    const endpoint = matchEndpoint(url.pathname);
    if (!endpoint) {
      return new Response(
        JSON.stringify({ error: { message: "Not found", type: "invalid_request_error" } }),
        { status: 404, headers: { "Content-Type": "application/json" } },
      );
    }

    // Only support POST
    if (request.method !== "POST") {
      return new Response(
        JSON.stringify({ error: { message: "Method not allowed", type: "invalid_request_error" } }),
        { status: 405, headers: { "Content-Type": "application/json" } },
      );
    }

    const requestId = generateRequestId();
    const startTime = performance.now();

    try {
      // Parse request body
      const bodyText = await request.text();
      const body = JSON.parse(bodyText);

      // Check for streaming (not yet supported)
      if (isStreaming(body)) {
        return new Response(
          JSON.stringify({
            error: {
              message: "Streaming not yet supported through governance proxy. Set stream: false.",
              type: "invalid_request_error",
            },
          }),
          { status: 400, headers: { "Content-Type": "application/json" } },
        );
      }

      // Load constitution from KV
      const { configJson, hash: constHash } = await loadConstitution(env.CONSTITUTIONS);

      // Initialize WASM validator
      const validator = await initValidator(configJson, constHash);

      // Extract action text from request
      const actionText = extractRequestText(body);
      const model = extractModel(body);
      const systemPrompt = extractSystemPrompt(body);

      // Build context for validation
      const context: [string, string][] = [
        ["endpoint", endpoint],
        ["model", model],
      ];
      if (systemPrompt) {
        context.push(["action_description", systemPrompt]);
      }

      // === REQUEST VALIDATION ===
      const requestResult: GovernanceResult = JSON.parse(
        validator.validate(JSON.stringify({ text: actionText, context })),
      );

      const requestProof = createProof(
        requestId,
        "request",
        constHash,
        requestResult.valid,
        requestResult.rules_checked,
      );

      // Audit the request validation (async, off critical path)
      const requestLatency = performance.now() - startTime;
      ctx.waitUntil(
        writeAuditRecord(env.AUDIT_DB, {
          request_id: requestId,
          phase: "request",
          valid: requestResult.valid,
          violations_json: JSON.stringify(requestResult.violations),
          constitutional_hash: constHash,
          timestamp: new Date().toISOString(),
          tenant_id: "default",
          endpoint,
          model,
          latency_ms: requestLatency,
        }),
      );

      // If request is blocked, return 403
      if (requestResult.blocking) {
        return governanceDeniedResponse(requestResult.violations, "request", {
          "X-Governance-Proof": buildProofHeader(requestProof),
          "X-Request-Id": requestId,
        });
      }

      // === PROXY TO UPSTREAM ===
      const upstream = resolveUpstream(request);
      const upstreamResponse = await proxyToUpstream(
        request,
        upstream,
        url.pathname,
        bodyText,
      );

      // If upstream failed, pass through
      if (!upstreamResponse.ok) {
        const responseHeaders = new Headers(upstreamResponse.headers);
        responseHeaders.set("X-Governance-Proof", buildProofHeader(requestProof));
        responseHeaders.set("X-Request-Id", requestId);
        return new Response(upstreamResponse.body, {
          status: upstreamResponse.status,
          headers: responseHeaders,
        });
      }

      // === RESPONSE VALIDATION ===
      const responseBody = await upstreamResponse.text();
      let responseJson;
      try {
        responseJson = JSON.parse(responseBody);
      } catch {
        // Non-JSON response — pass through with request proof only
        const responseHeaders = new Headers(upstreamResponse.headers);
        responseHeaders.set("X-Governance-Proof", buildProofHeader(requestProof));
        responseHeaders.set("X-Request-Id", requestId);
        return new Response(responseBody, {
          status: upstreamResponse.status,
          headers: responseHeaders,
        });
      }

      const responseText = extractResponseText(responseJson);

      const responseResult: GovernanceResult = JSON.parse(
        validator.validate(JSON.stringify({ text: responseText, context: [] })),
      );

      const responseProof = createProof(
        requestId,
        "response",
        constHash,
        responseResult.valid,
        responseResult.rules_checked,
      );

      // Audit the response validation (async)
      const totalLatency = performance.now() - startTime;
      ctx.waitUntil(
        writeAuditRecord(env.AUDIT_DB, {
          request_id: requestId,
          phase: "response",
          valid: responseResult.valid,
          violations_json: JSON.stringify(responseResult.violations),
          constitutional_hash: constHash,
          timestamp: new Date().toISOString(),
          tenant_id: "default",
          endpoint,
          model,
          latency_ms: totalLatency,
        }),
      );

      // If response is blocked, return governance error
      if (responseResult.blocking) {
        return governanceDeniedResponse(responseResult.violations, "response", {
          "X-Governance-Proof": buildProofHeader(responseProof),
          "X-Request-Id": requestId,
        });
      }

      // === RETURN GOVERNED RESPONSE ===
      const responseHeaders = new Headers(upstreamResponse.headers);
      responseHeaders.set("X-Governance-Proof", buildProofHeader(responseProof));
      responseHeaders.set("X-Request-Id", requestId);

      return new Response(responseBody, {
        status: upstreamResponse.status,
        headers: responseHeaders,
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Internal governance proxy error";
      return new Response(
        JSON.stringify({
          error: {
            message: `Governance proxy error: ${message}`,
            type: "server_error",
            code: "governance_proxy_error",
          },
        }),
        {
          status: 502,
          headers: {
            "Content-Type": "application/json",
            "X-Request-Id": requestId,
          },
        },
      );
    }
  },
};
