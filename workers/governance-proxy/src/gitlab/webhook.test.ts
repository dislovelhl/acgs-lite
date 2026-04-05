import { describe, expect, it, vi } from "vitest";

import type { Env } from "../types.ts";
import { handleGitLabWebhook } from "./webhook.ts";

const baseEnv: Env = {
  CONSTITUTIONS: {} as KVNamespace,
  AUDIT_DB: {} as D1Database,
  CONSTITUTIONAL_HASH: "608508a9bd224290",
};

function makeRequest(body: unknown, headers: HeadersInit = {}): Request {
  return new Request("https://example.com/webhook", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...headers,
    },
    body: JSON.stringify(body),
  });
}

const skippedEvent = {
  object_kind: "push",
  object_attributes: {
    iid: 1,
    title: "ignored",
    source_branch: "feature",
    target_branch: "main",
    action: "open",
    author_id: 1,
  },
  project: {
    id: 1,
    web_url: "https://gitlab.com/example/project",
  },
};

describe("handleGitLabWebhook", () => {
  it("fails closed when no webhook secret is configured", async () => {
    const response = await handleGitLabWebhook(
      makeRequest(skippedEvent),
      baseEnv,
      { waitUntil: vi.fn() } as unknown as ExecutionContext,
      { validate: vi.fn() },
    );

    expect(response.status).toBe(503);
    await expect(response.json()).resolves.toEqual({
      error: "GitLab webhook secret not configured",
    });
  });

  it("accepts requests signed with the dedicated webhook secret", async () => {
    const response = await handleGitLabWebhook(
      makeRequest(skippedEvent, { "x-gitlab-token": "worker-secret" }),
      {
        ...baseEnv,
        GITLAB_WEBHOOK_SECRET: "worker-secret",
      },
      { waitUntil: vi.fn() } as unknown as ExecutionContext,
      { validate: vi.fn() },
    );

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({
      ok: true,
      skipped: "not a merge_request event",
    });
  });

  it("keeps the legacy upstream secret fallback behind an explicit flag", async () => {
    const response = await handleGitLabWebhook(
      makeRequest(skippedEvent, { "x-gitlab-token": "legacy-secret" }),
      {
        ...baseEnv,
        UPSTREAM_API_KEY: "legacy-secret",
        ALLOW_LEGACY_UPSTREAM_WEBHOOK_SECRET: "true",
      },
      { waitUntil: vi.fn() } as unknown as ExecutionContext,
      { validate: vi.fn() },
    );

    expect(response.status).toBe(200);
  });

  it("rejects mismatched webhook secrets", async () => {
    const response = await handleGitLabWebhook(
      makeRequest(skippedEvent, { "x-gitlab-token": "wrong-secret" }),
      {
        ...baseEnv,
        GITLAB_WEBHOOK_SECRET: "worker-secret",
      },
      { waitUntil: vi.fn() } as unknown as ExecutionContext,
      { validate: vi.fn() },
    );

    expect(response.status).toBe(401);
    await expect(response.json()).resolves.toEqual({ error: "Invalid webhook token" });
  });
});
