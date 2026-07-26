import {
  Building2, Cpu, KeyRound, Landmark, Layers, LineChart, Search,
  ShieldCheck, TrafficCone, Users, type LucideIcon,
} from "lucide-react";
import type { UserRole } from "@/config/roles";

const ROLE_ICONS: Record<UserRole, LucideIcon> = {
  dgp_state_command: Landmark,
  adgp_igp_range: Layers,
  sp_district_command: Building2,
  dysp_acp: Users,
  sho: ShieldCheck,
  investigating_officer: Search,
  crime_analyst: LineChart,
  cyber_cell: Cpu,
  traffic_command: TrafficCone,
  system_admin: KeyRound,
};

export function RoleIcon({ role, className }: { role: UserRole; className?: string }) {
  const Icon = ROLE_ICONS[role];
  return <Icon className={className} aria-hidden="true" />;
}
