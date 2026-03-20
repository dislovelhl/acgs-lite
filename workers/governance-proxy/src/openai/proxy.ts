/// Proxy requests to upstream OpenAI-compatible API.

const UPSTREAM_URLS: Record<string, string> = {
  "openai": "https://api.openai.com",
  "anthropic": "https://api.anthropic.com",
};

/// Forward a request to the upstream API, preserving headers.
export async function proxyToUpstream(
  request: Request,
  upstreamBase: string,
  path: string,
  body: string,
): Promise<Response> {
  const url = `${upstreamBase}${path}`;

  const headers = new Headers(request.headers);
  // Remove Cloudflare-specific headers
  headers.delete("cf-connecting-ip");
  headers.delete("cf-ray");
  headers.delete("cf-visitor");

  const upstreamResponse = await fetch(url, {
    method: request.method,
    headers,
    body,
  });

  return upstreamResponse;
}

/// Resolve the upstream URL from the request.
export function resolveUpstream(request: Request): string {
  // Check for X-Upstream-Provider header
  const provider = request.headers.get("x-upstream-provider")?.toLowerCase();
  if (provider && UPSTREAM_URLS[provider]) {
    return UPSTREAM_URLS[provider];
  }
  // Default to OpenAI
  return UPSTREAM_URLS["openai"];
}
