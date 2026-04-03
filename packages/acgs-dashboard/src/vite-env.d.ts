/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_ACGS_LITE_URL: string;
  readonly VITE_GATEWAY_URL: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
