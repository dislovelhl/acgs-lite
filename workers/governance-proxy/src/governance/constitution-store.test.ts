import { beforeEach, describe, expect, it } from "vitest";

import {
  getCachedConstitutionHash,
  invalidateCache,
  loadConstitution,
} from "./constitution-store.ts";

class FakeKVNamespace {
  private readonly values = new Map<string, string>();

  put(key: string, value: string): void {
    this.values.set(key, value);
  }

  async get(key: string, type?: "json"): Promise<unknown> {
    const value = this.values.get(key) ?? null;
    if (value === null) {
      return null;
    }
    if (type === "json") {
      return JSON.parse(value);
    }
    return value;
  }
}

describe("constitution-store", () => {
  beforeEach(() => {
    invalidateCache();
  });

  it("clears the isolate cache when invalidateCache is called", async () => {
    const kv = new FakeKVNamespace();
    kv.put("constitution:active", JSON.stringify({ hash: "hash-a" }));
    kv.put("constitution:hash-a", JSON.stringify({ const_hash: "hash-a" }));

    await loadConstitution(kv as unknown as KVNamespace);
    expect(getCachedConstitutionHash()).toBe("hash-a");

    invalidateCache();

    expect(getCachedConstitutionHash()).toBeNull();
  });
});
