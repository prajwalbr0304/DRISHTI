import { DEFAULT_ROLE, type UserRole } from "@/config/roles";
import type { AuthUser } from "@/auth/types";

/* ============================================================================
   Display-role derivation. IMPORTANT: this decides UI presentation only. The
   AUTHORITATIVE role is resolved SERVER-SIDE by gateway_api (infra/catalyst/
   functions/gateway_api/index.js `resolveIdentity`) from the Catalyst identity,
   and the client role header is stripped at the gateway. Never trust this on the
   server; never send it as a trusted role.

   The catalyst-role branch mirrors the server's rank map (gateway_api RANK_MAP /
   services/ml/app/org/hierarchy.py) so the UI shows the seat the server will
   enforce: DGP/ADGP/IGP/SP/DySP-ACP/SHO/IO plus the staff cells (crime analyst,
   cyber, traffic) and the platform admin.
   ========================================================================== */

export function deriveDisplayRole(user: AuthUser | null): UserRole {
  if (!user) return DEFAULT_ROLE;
  if (user.source === "offline" && user.demoRole) return user.demoRole;

  const r = (user.catalystRole ?? "").toLowerCase();
  if (/admin|super|sysadmin/.test(r)) return "system_admin";
  if (/dgp|director general|commissioner of police/.test(r)) return "dgp_state_command";
  if (/adgp|\bigp\b|\bdig\b|range|zone/.test(r)) return "adgp_igp_range";
  if (/\bsp\b|superintendent|\bdcp\b|district/.test(r)) return "sp_district_command";
  if (/dysp|dy\.?\s?sp|\bacp\b|\basp\b|sub-?division|circle/.test(r)) return "dysp_acp";
  if (/cyber|\bcen\b|financial/.test(r)) return "cyber_cell";
  if (/traffic/.test(r)) return "traffic_command";
  if (/analyst|scrb|records|policy/.test(r)) return "crime_analyst";
  if (/sho|station|inspector/.test(r)) return "sho";
  return DEFAULT_ROLE;
}
