import { apiClient } from "@/api/client";

/* ============================================================================
   Admin console: UI visibility, admin-created roles, role settings, seat profiles.

   Three things an administrator was promised and had no way to do: turn parts of
   the interface on and off per role, create a role with any permission, and edit
   a seat's own details.

   VISIBILITY IS NOT ACCESS. While authentication and RLS are off these switches
   govern rendering only — a hidden destination is still reachable by URL and a
   hidden card's endpoint still answers. The server says so in the response and the
   console repeats it, so the grid is never mistaken for an authorization boundary.
   ========================================================================== */

/** The four kinds of thing whose visibility can be overridden. */
export type ElementKind = "destination" | "board" | "kpi" | "widget";

export interface PermissionOut {
  permission_key: string;
  resource: string;
  action: string;
  label: string;
  description: string | null;
  category: string;
  /** Exposes PII or coercive capability: the console demands a reason first. */
  is_sensitive: boolean;
  /** Narrowest scope_type at which the permission means anything, or null for
   *  any. A state seat is aggregate-only, so it cannot hold `cases.detail_read`. */
  requires_scope: string | null;
}

export interface PermissionCatalogue {
  total: number;
  categories: Record<string, PermissionOut[]>;
  scope_types: string[];
}

export interface RoleGrantOut {
  permission_key: string;
  granted: boolean;
  reason: string | null;
  granted_by: string | null;
}

export interface AdminRole {
  role_name: string;
  description: string | null;
  /** Built-in roles cannot be renamed or deleted. */
  is_system: boolean;
  /** Which built-in UI surface the role renders. This is what lets a new role
   *  work without any new frontend code. */
  base_surface: string | null;
  allowed_scope_types: string[] | null;
  created_by: string | null;
  granted_count: number;
  sensitive_count: number;
  /** Seats holding the role. A role with seats cannot be deleted. */
  seat_count: number;
  display_label: string | null;
  default_route: string | null;
  sort_order: number | null;
}

export interface AdminRoleDetail extends AdminRole {
  grants: RoleGrantOut[];
}

export interface AdminRoleList {
  total: number;
  items: AdminRole[];
  base_surfaces: string[];
}

export interface CreateRoleBody {
  role_name: string;
  description?: string;
  base_surface: string;
  allowed_scope_types: string[];
  permission_keys: string[];
  /** Required when any requested permission is flagged sensitive. */
  reason?: string;
  display_label?: string;
  default_route?: string;
}

export interface UiGrant {
  id: number;
  role_name: string;
  /** null applies the override to every scope type of the role. */
  scope_type: string | null;
  element_kind: ElementKind;
  element_id: string;
  enabled: boolean;
  reason: string | null;
  updated_by: string | null;
  updated_at: string | null;
}

export interface UiVisibilityResponse {
  total: number;
  items: UiGrant[];
  /** The server's own statement that this is presentation, not access control.
   *  Surfaced in the console rather than paraphrased. */
  enforcement: string;
}

export interface SetUiGrantBody {
  role_name: string;
  element_kind: ElementKind;
  element_id: string;
  enabled: boolean;
  scope_type?: string | null;
  reason?: string;
}

export interface RoleSettingsBody {
  display_label?: string | null;
  description?: string | null;
  default_route?: string | null;
  default_board_id?: string | null;
  icon_name?: string | null;
  sort_order?: number | null;
}

export interface SeatProfile {
  user_id: number;
  username: string;
  display_name: string | null;
  role: string;
  scope_type: string | null;
  email: string | null;
  phone: string | null;
  rank_label: string | null;
  designation_label: string | null;
  posting_label: string | null;
  preferred_language: string | null;
  notes: string | null;
  /** An assignment property, separate from rank and from scope: may this officer
   *  be recorded as the IO of record. */
  is_lead_investigator: boolean;
  is_active: boolean;
  updated_by: string | null;
}

/** Only the fields present are written, so a partial edit cannot blank a rank the
 *  admin never touched. Role, unit and scope are deliberately absent — those are
 *  provisioning decisions with their own audited endpoints. */
export type SeatProfileBody = Partial<
  Pick<SeatProfile,
    "display_name" | "email" | "phone" | "rank_label" | "designation_label" |
    "posting_label" | "preferred_language" | "notes" | "is_lead_investigator">
>;

export const adminConsoleApi = {
  /* --- catalogue + roles ------------------------------------------------- */
  permissions: (s?: AbortSignal) =>
    apiClient.get<PermissionCatalogue>("/admin/permissions", {}, s),

  roles: (s?: AbortSignal) =>
    apiClient.get<AdminRoleList>("/admin/roles", {}, s),

  role: (roleName: string, s?: AbortSignal) =>
    apiClient.get<AdminRoleDetail>(`/admin/roles/${encodeURIComponent(roleName)}`, {}, s),

  createRole: (body: CreateRoleBody, s?: AbortSignal) =>
    apiClient.post<AdminRoleDetail>("/admin/roles", body, undefined, s),

  /** Replaces the whole set, so the console posts its checkbox state rather than
   *  a diff the server would have to trust. */
  replaceGrants: (roleName: string,
                  body: { permission_keys: string[]; reason?: string },
                  s?: AbortSignal) =>
    apiClient.put<AdminRoleDetail>(
      `/admin/roles/${encodeURIComponent(roleName)}/grants`, body, undefined, s),

  toggleGrant: (roleName: string, permissionKey: string,
                body: { granted: boolean; reason?: string }, s?: AbortSignal) =>
    apiClient.patch<AdminRoleDetail>(
      `/admin/roles/${encodeURIComponent(roleName)}/grants/${encodeURIComponent(permissionKey)}`,
      body, undefined, s),

  deleteRole: (roleName: string, s?: AbortSignal) =>
    apiClient.del<void>(`/admin/roles/${encodeURIComponent(roleName)}`, undefined, s),

  updateRoleSettings: (roleName: string, body: RoleSettingsBody, s?: AbortSignal) =>
    apiClient.put<AdminRole>(
      `/admin/roles/${encodeURIComponent(roleName)}/settings`, body, undefined, s),

  /* --- UI visibility ----------------------------------------------------- */
  /** Overrides only. Absent means "use the registry default", which is why a
   *  newly shipped card appears immediately instead of waiting to be enabled for
   *  every role. */
  uiVisibility: (params: { role_name?: string; element_kind?: ElementKind } = {},
                 s?: AbortSignal) =>
    apiClient.get<UiVisibilityResponse>("/admin/ui-visibility", { ...params }, s),

  setUiVisibility: (body: SetUiGrantBody, s?: AbortSignal) =>
    apiClient.put<UiGrant>("/admin/ui-visibility", body, undefined, s),

  /** Removes the override so the element follows its default again. Distinct from
   *  switching it on, which would PIN it visible and stop later default changes
   *  from reaching the role. */
  clearUiVisibility: (grantId: number, s?: AbortSignal) =>
    apiClient.del<void>(`/admin/ui-visibility/${grantId}`, undefined, s),

  /* --- seat profile ------------------------------------------------------ */
  seatProfile: (userId: number, s?: AbortSignal) =>
    apiClient.get<SeatProfile>(`/admin/users/${userId}/profile`, {}, s),

  updateSeatProfile: (userId: number, body: SeatProfileBody, s?: AbortSignal) =>
    apiClient.put<SeatProfile>(`/admin/users/${userId}/profile`, body, undefined, s),
};
