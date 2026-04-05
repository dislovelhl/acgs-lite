/// OpenAI-compatible route dispatch.

/// Match the request path to a governance endpoint type.
export function matchEndpoint(
  pathname: string,
): "chat.completions" | "responses" | "embeddings" | null {
  if (pathname === "/v1/chat/completions") {
    return "chat.completions";
  }
  if (pathname === "/v1/responses") {
    return "responses";
  }
  if (pathname === "/v1/embeddings") {
    return "embeddings";
  }
  return null;
}

/// Health check response.
export function healthResponse(): Response {
  return new Response(
    JSON.stringify({
      status: "ok",
      service: "acgs-governance-proxy",
      constitutional_hash: "608508a9bd224290",
    }),
    {
      status: 200,
      headers: { "Content-Type": "application/json" },
    },
  );
}
