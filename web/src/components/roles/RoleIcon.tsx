import {
  Building2, Building, KeyRound, Landmark, Layers, Search,
  ShieldCheck, type LucideIcon,
} from "lucide-react";
import type { ScopeType, UserRole } from "@/config/roles";

/* Icons are keyed by SCOPE TYPE first, then by role.
 *
 * A senior_command seat is an ADGP wing or a DIG range, and a district_command
 * seat is an SP district or a CP commissionerate — visually distinct jobs sharing
 * one role, so a role-only icon map would show the same glyph for both. */
const SCOPE_ICONS: Record<ScopeType, LucideIcon> = {
  state: Landmark,
  wing: Layers,
  range: Layers,
  district: Building2,
  commissionerate: Building,
  station: ShieldCheck,
  assigned_case: Search,
  platform: KeyRound,
  unresolved: Search,
};

const ROLE_ICONS: Record<UserRole, LucideIcon> = {
  dgp_state_command: Landmark,
  senior_command: Layers,
  district_command: Building2,
  sho: ShieldCheck,
  investigating_officer: Search,
  system_admin: KeyRound,
};

export function RoleIcon({
  role,
  scope,
  className,
}: {
  role: UserRole;
  scope?: ScopeType;
  className?: string;
}) {
  const Icon = (scope && SCOPE_ICONS[scope]) || ROLE_ICONS[role] || Search;
  return <Icon className={className} aria-hidden="true" />;
}
