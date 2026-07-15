import { ApiError, type HealthReport } from "@/api/contracts";
import type { UserRole } from "@/config/roles";

/* ============================================================================
   Typed API client for the Wave-B services. Live only — every call hits the
   real FastAPI service; there are no mocks or synthetic fallbacks.

   - Base URL from VITE_API_BASE_URL (default http://localhost:8000).
   - Sends the active role as `X-Role` (money-trail + scoping read it).
   - Normalises failures into ApiError so the UI can render honest states.
   ========================================================================== */

const DEFAULT_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export interface ApiClientConfig {
  baseUrl: string;
}

type RoleGetter = () => UserRole;

export type QueryValue = string | number | boolean | undefined | null;
export type QueryParams = Record<string, QueryValue | (string | number)[]>;

export class ApiClient {
  baseUrl: string;
  private roleGetter: RoleGetter = () => "investigator";

  constructor(config?: Partial<ApiClientConfig>) {
    this.baseUrl = config?.baseUrl ?? DEFAULT_BASE;
  }

  configure(config: Partial<ApiClientConfig>) {
    if (config.baseUrl !== undefined) this.baseUrl = config.baseUrl;
  }

  /** RoleProvider wires this so every request carries the active role. */
  setRoleGetter(getter: RoleGetter) {
    this.roleGetter = getter;
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

  async request<T>(
    path: string,
    opts: {
      method?: string;
      params?: QueryParams;
      body?: unknown;
      signal?: AbortSignal;
    } = {},
  ): Promise<T> {
    const { method = "GET", params, body, signal } = opts;
    let res: Response;
    try {
      res = await fetch(this.buildUrl(path, params), {
        method,
        signal,
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
          "X-Role": this.roleGetter(),
        },
        body: body !== undefined ? JSON.stringify(body) : undefined,
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

  get<T>(path: string, params?: QueryParams, signal?: AbortSignal) {
    return this.request<T>(path, { method: "GET", params, signal });
  }
  post<T>(path: string, body?: unknown, params?: QueryParams, signal?: AbortSignal) {
    return this.request<T>(path, { method: "POST", body, params, signal });
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
