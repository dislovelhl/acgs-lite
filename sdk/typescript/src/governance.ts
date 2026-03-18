/**
 * Governance API methods: status and SSE event subscription.
 */

import type { HttpClient } from "./client.js";
import type { GovernanceEvent, GovernanceStatus } from "./types.js";

export type GovernanceEventCallback = (event: GovernanceEvent) => void;
export type Unsubscribe = () => void;

export class GovernanceApi {
  constructor(private readonly http: HttpClient) {}

  /** Fetch the current governance and compliance status. */
  async getStatus(): Promise<GovernanceStatus> {
    return this.http.request<GovernanceStatus>("/api/v1/governance/status");
  }

  /**
   * Subscribe to the governance event SSE stream.
   *
   * Returns an unsubscribe function that aborts the underlying connection.
   *
   * @param callback - Invoked for each governance event received.
   * @param options.since - Optional unix timestamp to replay events from.
   * @param options.onError - Optional error handler; connection closes on error
   *   unless this callback is provided.
   */
  subscribe(
    callback: GovernanceEventCallback,
    options?: {
      readonly since?: number;
      readonly onError?: (error: unknown) => void;
    },
  ): Unsubscribe {
    const controller = new AbortController();
    const query: Record<string, string | number | undefined> = {};
    if (options?.since !== undefined) {
      query["since"] = options.since;
    }

    const url = this.http.buildUrl("/api/v1/governance/events", query);

    const consume = async () => {
      const headers = this.http.getDefaultHeaders();
      headers["Accept"] = "text/event-stream";

      const response = await fetch(url, {
        headers,
        signal: controller.signal,
      });

      if (!response.ok || response.body === null) {
        throw new Error(`SSE connection failed: ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      // eslint-disable-next-line no-constant-condition
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        // Keep the last (possibly incomplete) chunk in the buffer.
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const event = JSON.parse(line.slice(6)) as GovernanceEvent;
              callback(event);
            } catch {
              // Skip malformed events silently.
            }
          }
          // Heartbeat comments (": heartbeat ...") are ignored.
        }
      }
    };

    consume().catch((error) => {
      // AbortError means the caller unsubscribed -- not an error.
      if (error instanceof DOMException && error.name === "AbortError") {
        return;
      }
      if (options?.onError) {
        options.onError(error);
      }
    });

    return () => controller.abort();
  }
}
