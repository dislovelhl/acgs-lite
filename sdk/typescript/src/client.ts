/**
 * Core HTTP client with fetch wrapper, timeout, and error handling.
 */

import type { ACGSClientConfig } from "./types.js";
import { ACGSError, ACGSNetworkError, ACGSTimeoutError } from "./errors.js";

const DEFAULT_TIMEOUT_MS = 30_000;

export interface RequestOptions {
  readonly method?: string;
  readonly body?: unknown;
  readonly query?: Readonly<Record<string, string | number | undefined>>;
  readonly headers?: Readonly<Record<string, string>>;
  /** Override the default timeout for this request. */
  readonly timeoutMs?: number;
}

/**
 * Low-level HTTP client that wraps `fetch` with timeout, error mapping,
 * and configurable base URL / headers.
 */
export class HttpClient {
  private readonly baseUrl: string;
  private readonly defaultHeaders: Readonly<Record<string, string>>;
  private readonly timeoutMs: number;

  constructor(config: ACGSClientConfig) {
    // Strip trailing slash so path concatenation is clean.
    this.baseUrl = config.baseUrl.replace(/\/+$/, "");
    this.defaultHeaders = {
      "Content-Type": "application/json",
      Accept: "application/json",
      ...config.headers,
    };
    this.timeoutMs = config.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  }

  /** Build a full URL with optional query parameters. */
  buildUrl(
    path: string,
    query?: Readonly<Record<string, string | number | undefined>>,
  ): string {
    const url = new URL(`${this.baseUrl}${path}`);
    if (query) {
      for (const [key, value] of Object.entries(query)) {
        if (value !== undefined) {
          url.searchParams.set(key, String(value));
        }
      }
    }
    return url.toString();
  }

  /** Return a copy of the default headers (useful for SSE connections). */
  getDefaultHeaders(): Record<string, string> {
    return { ...this.defaultHeaders };
  }

  /** Execute a JSON request and return the parsed response body. */
  async request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    const { method = "GET", body, query, headers, timeoutMs } = options;
    const url = this.buildUrl(path, query);
    const timeout = timeoutMs ?? this.timeoutMs;

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);

    try {
      const response = await fetch(url, {
        method,
        headers: { ...this.defaultHeaders, ...headers },
        body: body !== undefined ? JSON.stringify(body) : undefined,
        signal: controller.signal,
      });

      if (!response.ok) {
        const text = await response.text();
        throw new ACGSError(
          `ACGS API error ${response.status}: ${text}`,
          response.status,
          text,
        );
      }

      // 204 No Content
      if (response.status === 204) {
        return undefined as T;
      }

      return (await response.json()) as T;
    } catch (error) {
      if (error instanceof ACGSError) {
        throw error;
      }
      if (error instanceof DOMException && error.name === "AbortError") {
        throw new ACGSTimeoutError(url, timeout);
      }
      throw new ACGSNetworkError(url, error);
    } finally {
      clearTimeout(timer);
    }
  }
}
