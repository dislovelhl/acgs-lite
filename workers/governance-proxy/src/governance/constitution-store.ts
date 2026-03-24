/// Constitution store — loads and caches constitutions from KV.

/// In-memory cache for the current isolate.
let cachedConfig: string | null = null;
let cachedHash: string | null = null;

/// Load the active constitution config JSON from KV.
/// Returns cached version if available in this isolate.
export async function loadConstitution(
  kv: KVNamespace,
): Promise<{ configJson: string; hash: string }> {
  // Check isolate-level cache first
  if (cachedConfig !== null && cachedHash !== null) {
    return { configJson: cachedConfig, hash: cachedHash };
  }

  // Load active constitution pointer
  const pointer = await kv.get("constitution:active", "json") as {
    hash: string;
  } | null;

  if (!pointer) {
    throw new Error("No active constitution found in KV");
  }

  // Load the full config
  const configJson = await kv.get(`constitution:${pointer.hash}`);
  if (!configJson) {
    throw new Error(`Constitution config not found for hash: ${pointer.hash}`);
  }

  // Cache in isolate memory
  cachedConfig = configJson;
  cachedHash = pointer.hash;

  return { configJson, hash: pointer.hash };
}

/// Invalidate the isolate-level cache (for config updates).
export function invalidateCache(): void {
  cachedConfig = null;
  cachedHash = null;
}

/// Test helper to inspect the isolate cache state.
export function getCachedConstitutionHash(): string | null {
  return cachedHash;
}
