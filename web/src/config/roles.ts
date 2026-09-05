/* ============================================================================
   Roles drive both data scope and which destinations appear in the sidebar
   (doc 01 §4). The whole shell reads the active role from RoleProvider.

   INTERIM ACCESS MODEL: the ten command roles below are presentation seats for
   the demo and every one of them currently holds EVERY capability (`admin: true`
   + `roleCan()` returning true). Per-role narrowing returns here — and in the
   server-side matrix (services/ml/app/roles.py) — when real RBAC lands. The
   server always re-derives + enforces the role; this file is never a security
   boundary.
   ========================================================================== */

export type UserRole =
  | "dgp_state_command"
  | "adgp_igp_range"
  | "sp_district_command"
  | "dysp_acp"
  | "sho"
  | "investigating_officer"
  | "crime_analyst"
  | "cyber_cell"
  | "traffic_command"
  | "system_admin";

export interface RoleDef {
  id: UserRole;
  label: string;
  /** One-line description of what this role does. */
  blurb: string;
  /** Data scope hint shown in the profile menu and sent to services. */
  scope: string;
  /** Where this role lands by default. */
  home: string;
  /** Interim: every role reaches the Admin destination. */
  admin: boolean;
  /** Synthetic demo officer holding this seat (display name). */
  demoName: string;
  /** Synthetic demo credential username (matches the seeded `users` rows). */
  demoUsername: string;
}

export const ROLES: Record<UserRole, RoleDef> = {
  dgp_state_command: {
    id: "dgp_state_command",
    label: "DGP / State Command",
    blurb: "State-wide command view: priorities, escalations and outcomes.",
    scope: "State · all districts",
    home: "/command",
    admin: true,
    demoName: "DGP Vikram Shetty",
    demoUsername: "dgp.vikram",
  },
  adgp_igp_range: {
    id: "adgp_igp_range",
    label: "ADGP / IGP Range",
    blurb: "Range command across districts: comparison and oversight.",
    scope: "Range · multiple districts",
    home: "/command",
    admin: true,
    demoName: "IGP Meenakshi Rao",
    demoUsername: "igp.meenakshi",
  },
  sp_district_command: {
    id: "sp_district_command",
    label: "SP / District Command",
    blurb: "District chief: workload, approvals and station performance.",
    scope: "District · all stations",
    home: "/command",
    admin: true,
    demoName: "SP Anand Kumar",
    demoUsername: "sp.anand",
  },
  dysp_acp: {
    id: "dysp_acp",
    label: "DySP / ACP",
    blurb: "Sub-division oversight: case review, quality and escalation.",
    scope: "Sub-division · circle stations",
    home: "/command",
    admin: true,
    demoName: "Dy.SP Kavya Hegde",
    demoUsername: "dysp.kavya",
  },
  sho: {
    id: "sho",
    label: "SHO",
    blurb: "Station chief: registration, assignment and review queue.",
    scope: "Station · all station cases",
    home: "/cases",
    admin: true,
    demoName: "SHO Suresh Patil",
    demoUsername: "sho.suresh",
  },
  investigating_officer: {
    id: "investigating_officer",
    label: "Investigating Officer",
    blurb: "Works individual cases, people, evidence and leads.",
    scope: "Assigned cases · own station",
    home: "/cases",
    admin: true,
    demoName: "PSI Ramesh Gowda",
    demoUsername: "io.ramesh",
  },
  crime_analyst: {
    id: "crime_analyst",
    label: "Crime Analyst",
    blurb: "Patterns, networks, hotspots and forecasts.",
    scope: "State · read-across",
    home: "/analytics",
    admin: true,
    demoName: "Analyst Divya Naik",
    demoUsername: "analyst.divya",
  },
  cyber_cell: {
    id: "cyber_cell",
    label: "Cyber Cell",
    blurb: "Cyber and financial crime: money trail, devices and accounts.",
    scope: "Cyber cases · state-wide",
    home: "/network",
    admin: true,
    demoName: "Insp. Arjun Bhat (CEN)",
    demoUsername: "cyber.arjun",
  },
  traffic_command: {
    id: "traffic_command",
    label: "Traffic Command",
    blurb: "Road-safety hotspots, accident patterns and enforcement load.",
    scope: "Traffic · district corridors",
    home: "/map",
    admin: true,
    demoName: "Traffic ACP Latha Prasad",
    demoUsername: "traffic.latha",
  },
  system_admin: {
    id: "system_admin",
    label: "System Admin",
    blurb: "Full access, model registry, credentials and governance.",
    scope: "All data · all districts",
    home: "/command",
    admin: true,
    demoName: "Sysadmin Nikhil Jain",
    demoUsername: "admin",
  },
};

export const ROLE_LIST: RoleDef[] = Object.values(ROLES);

/** Every role id, in display order. */
export const ROLE_IDS: UserRole[] = ROLE_LIST.map((r) => r.id);

export const DEFAULT_ROLE: UserRole = "investigating_officer";

/** True when `value` is one of the current role ids. */
export function isUserRole(value: unknown): value is UserRole {
  return typeof value === "string" && value in ROLES;
}

/** The actor string to send as X-Demo-Actor for a seat.
 *
 *  This is the SEEDED username (see `demoUsername`), not a synthesised
 *  `demo.<role>` key, because the server tries to resolve the actor against the
 *  `users` table to derive that seat's trusted organizational scope — its
 *  district and station (services/ml/app/org/service.py resolve_scope_for_user,
 *  mirrored by app/roles.py DEMO_USERS). An unresolvable actor silently collapses
 *  to a role-default scope, which is why an SP and a DGP used to look equally
 *  un-posted to endpoints that scope by seat.
 *
 *  Display/audit only, and stripped at the API Gateway — never authentication. */
export function demoActorFor(role: UserRole): string {
  return ROLES[role]?.demoUsername ?? ROLES[DEFAULT_ROLE].demoUsername;
}

/* --------------------------------------------------------------------------
   Capabilities. Every UI gate routes through `roleCan` so the interim
   "all roles have access to everything" policy lives in exactly one place.
   -------------------------------------------------------------------------- */
export type Capability =
  | "case_read"          // individual case files / PII-bearing records
  | "case_write"         // add case evidence, statements, court updates
  | "intake_write"       // create/edit an FIR intake draft
  | "intake_review"      // approve/reject/return a submitted draft
  | "board_use"          // open the Investigation Board
  | "board_share"        // share / lock / promote a board
  | "network_analysis"   // link analysis + money trail
  | "imports_review"     // commit/rollback a structured import
  | "entity_review"      // entity resolution / jurisdiction / quality queues
  | "jurisdiction_override" // audited district override at intake
  | "governance_run"     // run a governed pipeline
  | "governance_review"  // approve a governed prediction
  | "disaster_write"     // Emergency Response approvals + dispatch
  | "admin";             // admin, registry and governance console

/**
 * Interim access model: every role holds every capability. Narrow this when the
 * real per-role matrix lands; the server re-derives and enforces regardless.
 */
export function roleCan(_role: UserRole, _capability: Capability): boolean {
  return true;
}
