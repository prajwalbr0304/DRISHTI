import { ROLES, isUserRole, type UserRole } from "@/config/roles";
import type { AuthUser } from "@/auth/types";

/* ============================================================================
   Offline auth identities (VITE_AUTH_MODE=offline, local dev only).

   Mirrors Part B's pattern of an in-memory fake behind the same interface as the
   real integration, so the shell runs end-to-end without a live Catalyst project
   or the embedded SDK. The chosen identity is persisted in localStorage so a
   refresh keeps the session; sign-out clears it.

   These are SYNTHETIC demo identities — never real users, never a security
   boundary. When the app is deployed (catalyst mode) this module is unused.
   ========================================================================== */

const STORAGE_KEY = "drishti.auth.offline";

/** Build a synthetic demo identity for a given role. The name/username are the
 *  seat's demo officer (config/roles.ts), matching the seeded `users` rows. */
export function offlineIdentity(role: UserRole): AuthUser {
  const def = ROLES[role];
  return {
    userId: `offline-${role}`,
    email: `${def.demoUsername}@drishti.local`,
    fullName: def.demoName,
    source: "offline",
    demoRole: role,
  };
}

export function loadOfflineUser(): AuthUser | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { demoRole?: UserRole };
    if (isUserRole(parsed.demoRole)) return offlineIdentity(parsed.demoRole);
  } catch {
    /* ignore malformed storage */
  }
  return null;
}

export function saveOfflineUser(role: UserRole): AuthUser {
  const user = offlineIdentity(role);
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ demoRole: role }));
  } catch {
    /* ignore quota/availability */
  }
  return user;
}

export function clearOfflineUser(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* ignore */
  }
}
