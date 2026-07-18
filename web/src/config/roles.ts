/* ============================================================================
   Roles drive both data scope and which destinations appear in the sidebar
   (doc 01 §4). The whole shell reads the active role from RoleProvider.
   ========================================================================== */

export type UserRole =
  | "investigator"
  | "analyst"
  | "supervisor"
  | "policymaker"
  | "super_admin";

export interface RoleDef {
  id: UserRole;
  label: string;
  /** One-line description of what this role does. */
  blurb: string;
  /** Data scope hint shown in the profile menu and sent to services. */
  scope: string;
  /** Where this role lands by default. */
  home: string;
  /** Only super_admin sees the Admin destination (8th item). */
  admin: boolean;
}

export const ROLES: Record<UserRole, RoleDef> = {
  investigator: {
    id: "investigator",
    label: "Investigator",
    blurb: "Works individual cases, people and leads.",
    scope: "Assigned cases · own station",
    home: "/cases",
    admin: false,
  },
  analyst: {
    id: "analyst",
    label: "Crime Analyst",
    blurb: "Patterns, networks, hotspots and forecasts.",
    scope: "District · read-across",
    home: "/command",
    admin: false,
  },
  supervisor: {
    id: "supervisor",
    label: "Supervisor",
    blurb: "Oversees units, workloads and outcomes.",
    scope: "Sub-division · all stations",
    home: "/command",
    admin: false,
  },
  policymaker: {
    id: "policymaker",
    label: "Policymaker",
    blurb: "Strategic trends and socio-economic signals.",
    scope: "State · aggregated",
    home: "/analytics",
    admin: false,
  },
  super_admin: {
    id: "super_admin",
    label: "Super Admin",
    blurb: "Full access, model registry and governance.",
    scope: "All data · all districts",
    home: "/command",
    admin: true,
  },
};

export const ROLE_LIST: RoleDef[] = Object.values(ROLES);

export const DEFAULT_ROLE: UserRole = "analyst";
