/// Compute SHA-256 hash for audit chain.
export async function sha256(data: string): Promise<string> {
  const encoder = new TextEncoder();
  const buffer = await crypto.subtle.digest("SHA-256", encoder.encode(data));
  return Array.from(new Uint8Array(buffer))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/// Compute chain hash for tamper-evident audit.
export async function chainHash(
  prevHash: string,
  entry: string,
): Promise<string> {
  return sha256(`${prevHash}|${entry}`);
}
