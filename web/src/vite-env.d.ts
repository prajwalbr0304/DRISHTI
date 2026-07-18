/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Public API base URL (localhost dev; Catalyst API Gateway origin deployed). */
  readonly VITE_API_BASE_URL?: string;
  /** "catalyst" (embedded Catalyst Authentication) or "offline" (dev demo user). */
  readonly VITE_AUTH_MODE?: "catalyst" | "offline";
  /** Versioned Catalyst Web SDK script URL (CDN). */
  readonly VITE_CATALYST_SDK_URL?: string;
  /** Synthetic-data provenance badge label. */
  readonly VITE_DEMO_BADGE?: string;
  /** Send cookies with API calls ("true"/"false"); needed cross-origin. */
  readonly VITE_API_WITH_CREDENTIALS?: string;
  /** Public Mapillary client read token (safe client-side). */
  readonly VITE_MAPILLARY_TOKEN?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
