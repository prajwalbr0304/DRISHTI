import { DEFAULT_ROLE, type UserRole } from "@/config/roles";
import type { AuthUser } from "@/auth/types";

/* ============================================================================
   Display-role derivation. IMPORTANT: this decides UI presentation only. The
   AUTHORITATIVE role is resolved SERVER-SIDE by gateway_api (infra/catalyst/
   functions/gateway_api/index.js `resolveRole`) from the Catalyst identity, and
   the client role header is stripped at the gateway. Never trust this on the
   server; never send it as a trusted role.

   The catalyst-role branch mirrors the server's mapping (admin/super →
   super_admin, supervisor/sho/inspector → supervisor, else investigator) so the
   UI matches what the server will enforce, plus analyst/policymaker for richer
   demo views.
   ========================================================================== */

export function deriveDisplayRole(user: AuthUser | null): UserRole {
  if (!user) return DEFAULT_ROLE;
  if (user.source === "offline" && user.demoRole) return user.demoRole;

  const r = (user.catalystRole ?? "").toLowerCase();
  if (/admin|super/.test(r)) return "super_admin";
  if (/supervisor|sho|inspector/.test(r)) return "supervisor";
  if (/analyst/.test(r)) return "analyst";
  if (/policy/.test(r)) return "policymaker";
  return "investigator";
}
