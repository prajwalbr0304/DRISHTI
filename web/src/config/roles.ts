/* ============================================================================
   Roles and seat scope.

   SIX application roles, not ten presentation seats. A role answers exactly one
   question — which UI surface to render. How much data a seat sees is a separate
   axis, `ScopeType`, resolved server-side from the seat's posting.

   That split is why ADGP and DIG share `senior_command`: identical surface,
   different scope (a functional wing vs a geographic range). Likewise SP and CP
   share `district_command`.

   Mirrors, and must stay in step with:
     services/ml/app/roles.py                       (canonical, server-side)
     services/ml/app/gateway_context.py             (defence-in-depth revalidation)
     infra/catalyst/functions/gateway_api/index.js  (server-side role resolution)
     services/ml/sql/028_roles_six_app_roles.sql    (roles seed)

   This file is never a security boundary. The server re-derives the role and the
   seat scope on every request and ignores anything asserted here.
   ========================================================================== */

export type UserRole =
  | "dgp_state_command"
  | "senior_command"
  | "district_command"
  | "sho"
  | "investigating_officer"
  | "system_admin";

/** How much data a seat sees. Orthogonal to the role.
 *
 *  `wing` is deliberately not a rung on the geographic ladder: it is state-wide
 *  geographically and narrowed by crime head instead. `unresolved` means the seat
 *  has no posting on record and must see NOTHING — never state-wide. */
export type ScopeType =
  | "state"
  | "wing"
  | "range"
  | "district"
  | "commissionerate"
  | "station"
  | "assigned_case"
  | "platform"
  | "unresolved";

/** The dashboard surface a role renders. A custom admin-created role names one of
 *  these as its base surface, which is why new roles need no new frontend code. */
export type BoardSurface =
  | "state_command"
  | "senior_command"
  | "district_command"
  | "station"
  | "case_work"
  | "platform";

export interface RoleDef {
  id: UserRole;
  label: string;
  /** One-line description of what this role does. */
  blurb: string;
  /** Which scope types this role may be issued at. */
  scopeTypes: ScopeType[];
  /** Which dashboard surface it renders. */
  surface: BoardSurface;
  /** Where this role lands by default. */
  home: string;
  /** Reaches the Admin destination. */
  admin: boolean;
  /** Human-readable scope summary, for chips and menus where no live seat scope
   *  is available. Prefer SCOPE_TYPE_LABELS[seat.scopeType] when you have it. */
  scope: string;
  /** Seeded seat that provision_seats.sql posted for this role. Display/audit
   *  only; real seats are chosen through /org/seats. */
  demoName: string;
  demoUsername: string;
}

export const ROLES: Record<UserRole, RoleDef> = {
  dgp_state_command: {
    id: "dgp_state_command",
    label: "DGP / State Command",
    blurb: "State-wide command: priorities, escalations and outcomes. Aggregate-only.",
    scopeTypes: ["state"],
    surface: "state_command",
    home: "/command",
    admin: false,
    scope: "State · all districts",
    demoName: "DGP Vikram Shetty",
    demoUsername: "dgp.vikram",
  },
  senior_command: {
    id: "senior_command",
    label: "Senior Command",
    blurb: "ADGP over a functional wing, or DIG over a range of districts.",
    scopeTypes: ["wing", "range"],
    surface: "senior_command",
    home: "/command",
    admin: false,
    scope: "Wing (state-wide) or Range (multi-district)",
    demoName: "IGP Meenakshi Rao",
    demoUsername: "igp.meenakshi",
  },
  district_command: {
    id: "district_command",
    label: "District Command",
    blurb: "SP of a district, or CP of a city Commissionerate.",
    scopeTypes: ["district", "commissionerate"],
    surface: "district_command",
    home: "/command",
    admin: false,
    scope: "District or Commissionerate · all stations",
    demoName: "SP Anand Kumar",
    demoUsername: "sp.anand",
  },
  sho: {
    id: "sho",
    label: "SHO",
    blurb: "Station chief: registration, assignment and the station review queue.",
    scopeTypes: ["station"],
    surface: "station",
    home: "/command",
    admin: false,
    scope: "Station · all station cases",
    demoName: "SHO Suresh Patil",
    demoUsername: "sho.suresh",
  },
  investigating_officer: {
    id: "investigating_officer",
    label: "Investigating Officer",
    blurb: "Works assigned cases, people, evidence and leads.",
    scopeTypes: ["assigned_case"],
    surface: "case_work",
    home: "/cases",
    admin: false,
    scope: "Assigned cases · own station",
    demoName: "PSI Ramesh Gowda",
    demoUsername: "io.ramesh",
  },
  system_admin: {
    id: "system_admin",
    label: "System Admin",
    blurb: "Seats, roles, UI visibility, model registry and governance.",
    scopeTypes: ["platform"],
    surface: "platform",
    home: "/admin",
    admin: true,
    scope: "Platform administration",
    demoName: "Sysadmin Nikhil Jain",
    demoUsername: "admin",
  },
};

export const ROLE_LIST: RoleDef[] = Object.values(ROLES);
export const ROLE_IDS: UserRole[] = ROLE_LIST.map((r) => r.id);

/** Least-privilege default when no seat is asserted. */
export const DEFAULT_ROLE: UserRole = "investigating_officer";
export const DEFAULT_SCOPE_TYPE: ScopeType = "unresolved";

/** Rank-facing label for a seat. Depends on the SCOPE TYPE, not the role: a
 *  senior_command seat is an ADGP when wing-scoped and a DIG when range-scoped,
 *  so labelling by role alone would call both of them the same thing. */
export const SCOPE_TYPE_LABELS: Record<ScopeType, string> = {
  state: "DGP / State Command",
  wing: "ADGP / Functional Wing",
  range: "DIG / Range Command",
  district: "SP / District Command",
  commissionerate: "CP / City Commissionerate",
  station: "SHO / Station",
  assigned_case: "Investigating Officer",
  platform: "System Admin",
  unresolved: "Unposted seat",
};

/** Short scope description for chips and the profile menu. */
export const SCOPE_TYPE_BLURBS: Record<ScopeType, string> = {
  state: "All districts",
  wing: "State-wide, own crime heads",
  range: "Districts in the range",
  district: "One district, all stations",
  commissionerate: "One commissionerate, all stations",
  station: "One station",
  assigned_case: "Assigned cases",
  platform: "Platform administration",
  unresolved: "No posting on record",
};

/** Superseded role names -> current role. Kept so a stale localStorage value or
 *  cached header resolves to the right seat instead of the default. Mirrors
 *  LEGACY_ROLE_ALIASES in services/ml/app/roles.py and migration 028. */
const LEGACY_ROLE_ALIASES: Record<string, UserRole> = {
  adgp_igp_range: "senior_command",
  sp_district_command: "district_command",
  dysp_acp: "district_command",
  crime_analyst: "senior_command",
  cyber_cell: "senior_command",
  traffic_command: "senior_command",
  investigator: "investigating_officer",
  supervisor: "sho",
  analyst: "senior_command",
  policymaker: "senior_command",
  super_admin: "system_admin",
};

export function isUserRole(value: unknown): value is UserRole {
  return typeof value === "string" && value in ROLES;
}

export function isScopeType(value: unknown): value is ScopeType {
  return typeof value === "string" && value in SCOPE_TYPE_LABELS;
}

/** Coerce a possibly-stale role string to a current one. */
export function normalizeRole(value: unknown): UserRole {
  if (isUserRole(value)) return value;
  if (typeof value === "string" && value in LEGACY_ROLE_ALIASES) {
    return LEGACY_ROLE_ALIASES[value];
  }
  return DEFAULT_ROLE;
}

/** True when a role may be issued at this scope type (mirrors server rule 4). */
export function scopeTypeAllowed(role: UserRole, scope: ScopeType): boolean {
  return ROLES[role].scopeTypes.includes(scope);
}

/** The surface to render for a seat. */
export function surfaceFor(role: UserRole): BoardSurface {
  return ROLES[role].surface;
}

/** Seats that must never read individual case rows.
 *
 *  A state or wing seat is accountable for the whole force or a whole functional
 *  wing; neither has a case-level remit, and both would otherwise be able to page
 *  through every FIR in Karnataka. Enforced server-side; used here to hide the
 *  affordance rather than to offer it and fail. */
export function isAggregateOnly(scope: ScopeType): boolean {
  return scope === "state" || scope === "wing";
}

/* --------------------------------------------------------------------------
   Capabilities.

   Still permissive pending the server-side capability matrix, with one real
   exception now enforced: case-level reads are refused for aggregate-only seats.
   That one matters because it is the difference between a command dashboard and
   a state-wide PII browser.
   -------------------------------------------------------------------------- */
export type Capability =
  | "case_read"          // case LIST / aggregate case access
  | "case_detail_read"   // an individual case FILE, including parties (PII-bearing)
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
  | "cctv_review"        // confirm/dismiss a proposed CCTV video-analytics alert
  | "cctv_dispatch"      // propose + send the nearest responder for a confirmed alert
  | "cctv_admin"         // register/retire cameras and responders
  | "admin";             // admin, registry and governance console

const CASE_LEVEL: Capability[] = ["case_detail_read", "case_write", "intake_write"];

/** Capability gate.
 *
 *  `scope` is optional so the ~30 existing call sites that predate the seat model
 *  keep compiling; when it is supplied the aggregate-only rule is enforced. Call
 *  sites that guard case-level UI should pass it — without a scope this cannot
 *  know whether the caller is a DGP or an SHO, so it errs permissive and leaves
 *  the real decision to the server. */
export function roleCan(
  role: UserRole,
  capability: Capability,
  scope?: ScopeType,
): boolean {
  if (scope && isAggregateOnly(scope) && CASE_LEVEL.includes(capability)) return false;
  if (capability === "admin") return ROLES[role].admin;
  return true;
}

/* --------------------------------------------------------------------------
   Seat display compatibility.

   Real seats now live in the `users` table (~11,800 of them) and are chosen
   through /org/seats, so a role no longer carries one demo identity. These keep
   the offline dev path and the profile menu working, and name the seeded seat that
   provision_seats.sql posted for each role.
   -------------------------------------------------------------------------- */
export const ROLE_DEMO_SEAT: Record<UserRole, { username: string; name: string }> = {
  dgp_state_command: { username: "dgp.vikram", name: "DGP Vikram Shetty" },
  senior_command: { username: "igp.meenakshi", name: "IGP Meenakshi Rao" },
  district_command: { username: "sp.anand", name: "SP Anand Kumar" },
  sho: { username: "sho.suresh", name: "SHO Suresh Patil" },
  investigating_officer: { username: "io.ramesh", name: "PSI Ramesh Gowda" },
  system_admin: { username: "admin", name: "Sysadmin Nikhil Jain" },
};

/** The actor string sent as X-Demo-Actor for a seat. The server resolves it
 *  against `users` to derive the trusted scope. Display/audit only, and stripped
 *  at the API Gateway — never authentication. */
export function demoActorFor(role: UserRole): string {
  return (ROLE_DEMO_SEAT[role] ?? ROLE_DEMO_SEAT[DEFAULT_ROLE]).username;
}

export function demoNameFor(role: UserRole): string {
  return (ROLE_DEMO_SEAT[role] ?? ROLE_DEMO_SEAT[DEFAULT_ROLE]).name;
}

/** Human-readable scope summary for a role, used where no live seat scope is
 *  available yet. Prefer the seat's own scope_type label when you have it. */
export function roleScopeSummary(role: UserRole): string {
  return ROLES[role].scopeTypes
    .map((s) => SCOPE_TYPE_BLURBS[s])
    .join(" or ");
}
