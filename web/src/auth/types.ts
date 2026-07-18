import type { AuthMode } from "@/config/runtime";
import type { UserRole } from "@/config/roles";

export type { AuthMode };

/** Lifecycle of the authentication check. */
export type AuthStatus = "initializing" | "authenticated" | "unauthenticated" | "error";

/**
 * Normalised authenticated identity. This is IDENTITY only — the authoritative
 * role/scope is resolved SERVER-SIDE by the API Gateway (gateway_api) from the
 * Catalyst session. `catalystRole` / `demoRole` here drive UI presentation only
 * and are never sent as a trusted role.
 */
export interface AuthUser {
  userId: string;
  email: string;
  fullName: string;
  source: AuthMode;
  /** Raw Catalyst role name, when available (display only). */
  catalystRole?: string;
  /** Offline demo identity's role (offline mode only). */
  demoRole?: UserRole;
}

/** Shape(s) the Catalyst Web SDK may resolve `isUserAuthenticated()` with. */
interface RawCatalystUser {
  user_id?: string | number;
  zuid?: string | number;
  email_id?: string;
  email?: string;
  first_name?: string;
  last_name?: string;
  role_details?: { role_name?: string };
  role_name?: string;
  content?: RawCatalystUser;
  user_details?: RawCatalystUser;
}

/** Defensively normalise the various user shapes into an AuthUser. */
export function normalizeCatalystUser(raw: unknown): AuthUser | null {
  if (!raw || typeof raw !== "object") return null;
  const r = raw as RawCatalystUser;
  const u = r.content ?? r.user_details ?? r;
  const id = u.user_id ?? u.zuid;
  const email = u.email_id ?? u.email ?? "";
  if (id === undefined || id === null || String(id).length === 0) return null;
  const first = (u.first_name ?? "").trim();
  const last = (u.last_name ?? "").trim();
  const fullName = [first, last].filter(Boolean).join(" ") || email || `user ${id}`;
  const catalystRole = u.role_details?.role_name ?? u.role_name ?? undefined;
  return {
    userId: String(id),
    email,
    fullName,
    source: "catalyst",
    catalystRole,
  };
}
