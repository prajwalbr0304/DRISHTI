import { ApiError, type HealthReport } from "@/api/contracts";
import { DEFAULT_ROLE, type UserRole } from "@/config/roles";
import { runtime } from "@/config/runtime";

/* ============================================================================
   Typed API client for the Wave-B services. Live only — every call hits the
   real service; there are no mocks or synthetic fallbacks.

   Base URL (src/config/runtime.ts):
     - dev      → the FastAPI service directly (http://localhost:8000)
     - deployed → the Catalyst API Gateway origin, route `/api/*` → gateway_api
                  function → signed context → AppSail. One public base URL.

   Identity/auth:
     - Real authentication is Catalyst Authentication (see src/auth/). The
       gateway derives the user + role SERVER-SIDE from the Catalyst session and
       STRIPS any client-supplied identity headers. So `X-Role` / `X-Demo-Actor`
       here are DISPLAY/AUDIT hints only (used by the local FastAPI dev server for
       UX simulation); they are never a security boundary and are dropped at the
       gateway. Never trust a client-supplied role.
     - When configured (deployed / cross-origin), requests are sent with
       credentials so the Catalyst session cookie reaches the API Gateway, and an
       optional bearer token is attached if the auth layer provides one.
   ========================================================================== */

const DEFAULT_BASE = runtime.apiBaseUrl;

export interface ApiClientConfig {
  baseUrl: string;
  /** Send credentials (cookies) with requests — required cross-origin. */
  withCredentials: boolean;
}

type RoleGetter = () => UserRole;
type ActorGetter = () => string;
type TokenGetter = () => Promise<string | undefined> | string | undefined;
type DistrictGetter = () => number | null | undefined;

export type QueryValue = string | number | boolean | undefined | null;
export type QueryParams = Record<string, QueryValue | (string | number)[]>;

/** RFC4122-ish request id; prefers crypto.randomUUID, falls back for old envs. */
function makeRequestId(): string {
  const c = (globalThis as { crypto?: Crypto }).crypto;
  if (c?.randomUUID) return c.randomUUID();
  return "req-" + Math.random().toString(16).slice(2) + Date.now().toString(16);
}

export class ApiClient {
  baseUrl: string;
  withCredentials: boolean;
  private roleGetter: RoleGetter = () => DEFAULT_ROLE;
  // Demo actor is DISPLAY/AUDIT ONLY (UX simulation), never a security boundary.
  private actorGetter: ActorGetter = () => `demo.${DEFAULT_ROLE}`;
  // Cross-domain auth token from the auth layer (Catalyst generateAuthToken).
  // Undefined in dev/offline; then the session is cookie-based (credentials).
  private tokenGetter: TokenGetter = () => undefined;
  // Prompt 17 — the disaster coordinator's assigned district (server-side scope
  // for Emergency Response writes). Display/scoping only, never authentication.
  private districtGetter: DistrictGetter = () => null;

  constructor(config?: Partial<ApiClientConfig>) {
    this.baseUrl = config?.baseUrl ?? DEFAULT_BASE;
    this.withCredentials = config?.withCredentials ?? runtime.withCredentials;
  }

  configure(config: Partial<ApiClientConfig>) {
    if (config.baseUrl !== undefined) this.baseUrl = config.baseUrl;
    if (config.withCredentials !== undefined) this.withCredentials = config.withCredentials;
  }

  /** RoleProvider wires this so every request carries the active role (display/audit). */
  setRoleGetter(getter: RoleGetter) {
    this.roleGetter = getter;
  }

  /** RoleProvider wires this so every request carries the demo actor (audit/display only). */
  setActorGetter(getter: ActorGetter) {
    this.actorGetter = getter;
  }

  /** Auth layer wires this to attach a cross-domain token when available. */
  setTokenGetter(getter: TokenGetter) {
    this.tokenGetter = getter;
  }

  /** Emergency Response wires this so the coordinator's assigned district scopes
      server-side actions (X-Disaster-District). Scoping/display only. */
  setDistrictGetter(getter: DistrictGetter) {
    this.districtGetter = getter;
  }

  private buildUrl(path: string, params?: QueryParams) {
    const url = new URL(path.replace(/^\//, ""), ensureTrailingSlash(this.baseUrl));
    if (params) {
      for (const [k, v] of Object.entries(params)) {
        if (v === undefined || v === null) continue;
        if (Array.isArray(v)) v.forEach((item) => url.searchParams.append(k, String(item)));
        else url.searchParams.set(k, String(v));
      }
    }
    return url.toString();
  }

  /** Shared headers for every request. `json` is false for multipart uploads,
      where the browser must set Content-Type itself so it can add the boundary. */
  private async buildHeaders(
    extraHeaders?: Record<string, string>,
    json = true,
  ): Promise<Record<string, string>> {
    const token = await this.tokenGetter();
    return {
      ...(json ? { "Content-Type": "application/json" } : {}),
      Accept: "application/json",
      // Presentation state only (UX simulation) — the server treats these as
      // display/audit inputs, NOT authentication. The API Gateway strips them
      // and derives the real role from the Catalyst identity.
      "X-Role": this.roleGetter(),
      "X-Demo-Actor": this.actorGetter(),
      // Correlation id echoed back by the API and recorded in the audit trail.
      "X-Request-ID": makeRequestId(),
      // Emergency Response scope (assigned district). Omitted when null.
      ...(this.districtGetter() != null
        ? { "X-Disaster-District": String(this.districtGetter()) }
        : {}),
      // Catalyst cross-domain token is a RAW Authorization value (no
      // "Bearer " prefix). Absent in dev/offline (cookie-based session).
      ...(token ? { Authorization: token } : {}),
      // Per-request headers (idempotency key / If-Match version) — never
      // identity/auth headers, which the gateway controls.
      ...(extraHeaders ?? {}),
    };
  }

  private async send<T>(
    path: string,
    method: string,
    params: QueryParams | undefined,
    signal: AbortSignal | undefined,
    headers: Record<string, string>,
    body: BodyInit | undefined,
  ): Promise<T> {
    let res: Response;
    try {
      res = await fetch(this.buildUrl(path, params), {
        method,
        signal,
        // Cross-origin (Slate → API Gateway): carry the Catalyst session cookie.
        credentials: this.withCredentials ? "include" : "same-origin",
        headers,
        body,
      });
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") throw e;
      throw new ApiError(
        `Can't reach the DRISHTI service at ${this.baseUrl}. Is it running?`,
        0,
        e,
      );
    }

    if (!res.ok) {
      let detail: unknown;
      try {
        detail = await res.json();
      } catch {
        detail = await res.text().catch(() => undefined);
      }
      throw new ApiError(`${method} ${path} failed (${res.status})`, res.status, detail);
    }
    if (res.status === 204) return undefined as T;
    return (await res.json()) as T;
  }

  async request<T>(
    path: string,
    opts: {
      method?: string;
      params?: QueryParams;
      body?: unknown;
      signal?: AbortSignal;
      /** Optional per-request headers (e.g. X-Idempotency-Key, If-Match). */
      headers?: Record<string, string>;
    } = {},
  ): Promise<T> {
    const { method = "GET", params, body, signal, headers: extraHeaders } = opts;
    return this.send<T>(
      path,
      method,
      params,
      signal,
      await this.buildHeaders(extraHeaders, true),
      body !== undefined ? JSON.stringify(body) : undefined,
    );
  }

  get<T>(path: string, params?: QueryParams, signal?: AbortSignal) {
    return this.request<T>(path, { method: "GET", params, signal });
  }
  post<T>(path: string, body?: unknown, params?: QueryParams, signal?: AbortSignal) {
    return this.request<T>(path, { method: "POST", body, params, signal });
  }

  /** Multipart upload (e.g. a scanned FIR page for OCR).
   *
   *  Content-Type is deliberately NOT set: the browser must generate it so the
   *  multipart boundary matches the body. Setting it by hand produces a body the
   *  server cannot parse. All identity/correlation headers still apply.
   */
  async upload<T>(
    path: string,
    form: FormData,
    opts: { params?: QueryParams; signal?: AbortSignal; method?: string } = {},
  ): Promise<T> {
    const { params, signal, method = "POST" } = opts;
    return this.send<T>(
      path,
      method,
      params,
      signal,
      await this.buildHeaders(undefined, false),
      form,
    );
  }

  health(signal?: AbortSignal): Promise<HealthReport> {
    return this.get<HealthReport>("/health", undefined, signal);
  }
}

function ensureTrailingSlash(s: string) {
  return s.endsWith("/") ? s : s + "/";
}

/** Shared singleton used across the app. */
export const apiClient = new ApiClient();
