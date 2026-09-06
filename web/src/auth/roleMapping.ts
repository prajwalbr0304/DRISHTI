import { DEFAULT_ROLE, normalizeRole, type ScopeType, type UserRole } from "@/config/roles";
import type { AuthUser } from "@/auth/types";

/* ============================================================================
   Display-role derivation. IMPORTANT: this decides UI presentation only. The
   AUTHORITATIVE role is resolved SERVER-SIDE by gateway_api (infra/catalyst/
   functions/gateway_api/index.js `resolveIdentity`) from the Catalyst identity,
   and the client role header is stripped at the gateway. Never trust this on the
   server; never send it as a trusted role.

   Rank now maps to TWO things, because the role alone no longer says how much a
   seat sees: the application role (which surface) and the scope type (how much
   data). An ADGP and a DIG are both `senior_command` and differ only in scope, so
   collapsing them to a role would lose the distinction the board depends on.
   ========================================================================== */

export interface DerivedSeat {
  role: UserRole;
  /** Best-effort scope type from the rank label. The server's /org/my-scope is
   *  authoritative and overrides this as soon as it resolves. */
  scopeType: ScopeType;
}

export function deriveDisplaySeat(user: AuthUser | null): DerivedSeat {
  if (!user) return { role: DEFAULT_ROLE, scopeType: "unresolved" };
  if (user.source === "offline" && user.demoRole) {
    const role = normalizeRole(user.demoRole);
    return { role, scopeType: defaultScopeFor(role) };
  }

  const r = (user.catalystRole ?? "").toLowerCase();

  if (/admin|super|sysadmin/.test(r)) {
    return { role: "system_admin", scopeType: "platform" };
  }
  if (/dgp|director general/.test(r)) {
    return { role: "dgp_state_command", scopeType: "state" };
  }
  // ADGP heads a functional wing; IGP/DIG command a geographic range. Same role,
  // different scope — which is exactly why the two are tested separately.
  if (/adgp|additional director/.test(r)) {
    return { role: "senior_command", scopeType: "wing" };
  }
  if (/\bigp\b|\bdig\b|inspector general|range|zone/.test(r)) {
    return { role: "senior_command", scopeType: "range" };
  }
  // Staff cells now sit under an ADGP wing rather than being roles of their own.
  if (/cyber|\bcen\b|financial|analyst|scrb|records|policy|traffic/.test(r)) {
    return { role: "senior_command", scopeType: "wing" };
  }
  if (/commissioner of police|\bcp\b/.test(r)) {
    return { role: "district_command", scopeType: "commissionerate" };
  }
  if (/\bsp\b|superintendent|\bdcp\b|district|dysp|dy\.?\s?sp|\bacp\b|\basp\b/.test(r)) {
    return { role: "district_command", scopeType: "district" };
  }
  if (/sho|station|inspector/.test(r)) {
    return { role: "sho", scopeType: "station" };
  }
  return { role: DEFAULT_ROLE, scopeType: defaultScopeFor(DEFAULT_ROLE) };
}

/** The scope a role opens at before /org/my-scope answers. */
export function defaultScopeFor(role: UserRole): ScopeType {
  switch (role) {
    case "dgp_state_command": return "state";
    case "system_admin": return "platform";
    // Posted seats have no safe default: guessing a district would put a
    // jurisdiction in the top bar that the officer was never posted to.
    default: return "unresolved";
  }
}

/** Back-compat: the role alone, for call sites that do not yet handle scope. */
export function deriveDisplayRole(user: AuthUser | null): UserRole {
  return deriveDisplaySeat(user).role;
}
