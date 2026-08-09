/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Origin of the Command Center API. Empty means same origin. */
  readonly VITE_ARKALI_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
