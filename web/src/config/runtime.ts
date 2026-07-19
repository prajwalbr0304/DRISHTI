/* ============================================================================
   Runtime configuration — the SINGLE place the app reads build-time env vars.

   Phase 14 Part C rule: only PUBLIC, non-secret values may live in VITE_* (they
   are inlined into the static browser bundle). No database connection string,
   signing secret, AWS URL/creds, or any credential is ever read here. Every
   field below is safe to ship to the browser:

     - VITE_API_BASE_URL      public API base (localhost in dev; the Catalyst API
                              Gateway origin in the deployed build). NEVER an AWS
                              URL and NEVER a raw AppSail/DB URL.
     - VITE_AUTH_MODE         "catalyst" (embedded Catalyst Authentication, used
                              by the deployed build) or "offline" (local dev with
                              a synthetic demo identity; no live project needed).
     - VITE_CATALYST_SDK_URL  URL of the Catalyst Web SDK script (versioned CDN).
     - VITE_DEMO_BADGE        provenance label shown on the login gate + shell.
     - VITE_API_WITH_CREDENTIALS  send cookies cross-origin (defaults to true in
                              catalyst mode so the API-Gateway session flows).
     - VITE_MAPILLARY_TOKEN   public client read token for street imagery.

   Keeping all reads here means the "no secrets in the bundle" audit is one file
   (plus scripts/check-bundle-secrets.mjs, which greps the built assets).
   ========================================================================== */

export type AuthMode = "catalyst" | "offline";

function str(v: string | undefined, fallback: string): string {
  const s = (v ?? "").trim();
  return s.length > 0 ? s : fallback;
}

function bool(v: string | undefined, fallback: boolean): boolean {
  const s = (v ?? "").trim().toLowerCase();
  if (s === "") return fallback;
  return s === "true" || s === "1" || s === "yes";
}

const authMode: AuthMode =
  str(import.meta.env.VITE_AUTH_MODE, "offline") === "catalyst" ? "catalyst" : "offline";

export const runtime = {
  /** Public API base URL. Deployed build → Catalyst API Gateway origin. */
  apiBaseUrl: str(import.meta.env.VITE_API_BASE_URL, "http://localhost:8000"),

  /** Authentication mode. "catalyst" uses the embedded Catalyst Web SDK. */
  authMode,

  /** Versioned Catalyst Web SDK script (only loaded when authMode==="catalyst").
   *  v4.6.1+ is required for generateAuthToken() (cross-domain Slate→Gateway). */
  catalystSdkUrl: str(
    import.meta.env.VITE_CATALYST_SDK_URL,
    "https://static.zohocdn.com/catalyst/sdk/js/4.6.1/catalystWebSDK.js",
  ),

  /** Synthetic-data provenance badge label. */
  demoBadge: str(import.meta.env.VITE_DEMO_BADGE, "Synthetic Hackathon Demo"),

  /** Send credentials (cookies) with API calls. Needed cross-origin (Slate →
   *  API Gateway) so the Catalyst session reaches the gateway. */
  withCredentials: bool(import.meta.env.VITE_API_WITH_CREDENTIALS, authMode === "catalyst"),

  /** Public Mapillary read token (safe client-side); "" disables street view. */
  mapillaryToken: str(import.meta.env.VITE_MAPILLARY_TOKEN, ""),
} as const;

export type Runtime = typeof runtime;
