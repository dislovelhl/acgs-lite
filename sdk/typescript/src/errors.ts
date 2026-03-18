/**
 * Custom error classes for the ACGS SDK.
 */

export class ACGSError extends Error {
  /** HTTP status code returned by the API, or 0 for network errors. */
  readonly status: number;
  /** Raw response body (may be empty for network errors). */
  readonly body: string;

  constructor(message: string, status: number, body: string) {
    super(message);
    this.name = "ACGSError";
    this.status = status;
    this.body = body;
  }
}

export class ACGSTimeoutError extends ACGSError {
  constructor(url: string, timeoutMs: number) {
    super(
      `Request to ${url} timed out after ${timeoutMs}ms`,
      0,
      "",
    );
    this.name = "ACGSTimeoutError";
  }
}

export class ACGSNetworkError extends ACGSError {
  constructor(url: string, cause: unknown) {
    const detail = cause instanceof Error ? cause.message : String(cause);
    super(
      `Network error requesting ${url}: ${detail}`,
      0,
      "",
    );
    this.name = "ACGSNetworkError";
  }
}
