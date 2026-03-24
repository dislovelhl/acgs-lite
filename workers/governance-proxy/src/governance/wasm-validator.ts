/// WASM validator lifecycle — instantiate once per isolate.

import type { GovernanceResult } from "../types.ts";

// The WASM module exposes WasmValidator via wasm-bindgen.
// In Cloudflare Workers, we import the WASM module directly.

interface WasmValidatorInstance {
  validate(inputJson: string): string;
  validate_hot(textLower: string): string;
  const_hash(): string;
  free(): void;
}

interface WasmExports {
  WasmValidator: {
    new (configJson: string): WasmValidatorInstance;
  };
}

let validatorInstance: WasmValidatorInstance | null = null;
let instanceHash: string | null = null;

/// Initialize the WASM validator with a constitution config.
/// Re-uses the existing instance if the constitution hash matches.
export async function getValidator(
  wasmModule: WebAssembly.Module,
  configJson: string,
  constitutionHash: string,
  initWasm: () => Promise<WasmExports>,
): Promise<WasmValidatorInstance> {
  if (validatorInstance !== null && instanceHash === constitutionHash) {
    return validatorInstance;
  }

  const wasm = await initWasm();
  validatorInstance = new wasm.WasmValidator(configJson);
  instanceHash = constitutionHash;

  return validatorInstance;
}

/// Run validation against the WASM validator.
export function validate(
  validator: WasmValidatorInstance,
  text: string,
  context: [string, string][],
): GovernanceResult {
  const input = JSON.stringify({ text, context });
  const resultJson = validator.validate(input);
  return JSON.parse(resultJson) as GovernanceResult;
}
