import { apiClient } from "@/api/client";

/* Prompt 20 Part B — organizational hierarchy (police rank -> functional role +
   scope) and SUPERADMIN credential/role provisioning (services/ml/app/org).
   Reads require admin_read (supervisor + super_admin); credential mutations
   require super_admin AND the hackathon write guard, enforced server-side. The
   organizational scope is always derived server-side, never from a browser header. */

export interface RankMapping {
  rank: string;
  abbr: string;
  functional_role: string;
  scope_level: string;
  note: string;
}
export interface HierarchyResponse {
  functional_roles: string[];
  scope_levels: string[];
  mappings: RankMapping[];
  note: string;
}
export interface ScopeMatrix {
  actions: string[];
  roles: string[];
  matrix: Record<string, Record<string, boolean>>;
  note: string;
}
export interface OrgRole {
  role_id: number;
  role_name: string;
  description?: string | null;
  is_system: boolean;
  permissions: Record<string, string>;
}
export interface OrgRolesResponse {
  total: number;
  items: OrgRole[];
  functional_roles: string[];
  missing_roles: string[];
}
export interface OrgUser {
  user_id: number;
  username: string;
  display_name?: string | null;
  role: string;
  unit_id?: number | null;
  unit_name?: string | null;
  district_id?: number | null;
  district_name?: string | null;
  is_active: boolean;
  must_reset_password: boolean;
  created_at?: string | null;
  scope_level?: string | null;
}
export interface OrgUsersResponse {
  total: number;
  items: OrgUser[];
}
export interface CreateUserBody {
  username: string;
  display_name?: string;
  role: string;
  unit_id?: number;
}

/** The caller's own scope, DERIVED SERVER-SIDE from the trusted user record.
 *
 *  `district_ids`/`unit_ids` of null mean "not geographically pinned" — a state
 *  or range seat. A district/station seat carries the ids it is assigned to. Use
 *  it to pick sensible DEFAULTS (a district commander opens on their district, a
 *  state seat opens state-wide); it is not an authorisation boundary, since the
 *  server re-derives and enforces scope on every request regardless. */
export interface MyScopeResponse {
  role: string;
  scope_level: string;
  district_ids: number[] | null;
  unit_ids: number[] | null;
  assigned_case_scoped: boolean;
  user_id?: number | null;
  username?: string | null;
  rank?: string | null;
  /** provenance of the derivation, e.g. "trusted-seat-record" / "role-default" */
  source: string;
  /** false when the server had to fall back instead of reading an assignment */
  trusted: boolean;
  note?: string;
  /* --- seat model (migrations 026/027) --------------------------------- */
  /** state | wing | range | district | commissionerate | station |
   *  assigned_case | platform | unresolved. Authoritative; drives board choice. */
  scope_type?: string;
  wing_id?: number | null;
  range_id?: number | null;
  /** Crime heads a wing seat is limited to. null = every head. */
  crime_head_ids?: number[] | null;
  /** True when the seat must never read individual case rows (state / wing). */
  aggregate_only?: boolean;
  /** True when the seat may be recorded as the IO of a case. */
  is_lead_investigator?: boolean;
}

/* --- organizational reference + seat directory ------------------------- */
export interface WingOut {
  wing_id: number;
  wing_code: string;
  wing_name: string;
  description?: string | null;
  crime_head_ids: number[];
  crime_head_names: string[];
  /** True when the wing has no head filter (it covers the whole taxonomy). */
  covers_all_heads: boolean;
  seat_count: number;
}

export interface RangeDistrict {
  district_id: number;
  district_name: string;
}

export interface RangeOut {
  range_id: number;
  range_code: string;
  range_name: string;
  hq_district_id?: number | null;
  districts: RangeDistrict[];
  district_count: number;
  station_count: number;
  seat_count: number;
}

export interface SeatOut {
  user_id: number;
  username: string;
  display_name?: string | null;
  role: string;
  scope_type: string;
  /** Rank-facing label, e.g. "DIG / Range Command". Derived from scope_type. */
  scope_label: string;
  posting_label?: string | null;
  rank_label?: string | null;
  designation_label?: string | null;
  is_lead_investigator: boolean;
  is_active: boolean;
  wing_id?: number | null;
  range_id?: number | null;
  district_id?: number | null;
  unit_id?: number | null;
}

export interface SeatsResponse {
  total: number;
  page: number;
  page_size: number;
  items: SeatOut[];
  scope_type_counts: Record<string, number>;
  note?: string;
}

export interface SeatQuery {
  q?: string;
  role?: string;
  scope_type?: string;
  active_only?: boolean;
  page?: number;
  page_size?: number;
}

export const orgApi = {
  /** GET /org/my-scope — the caller's trusted, server-derived scope. Ungated. */
  myScope: (s?: AbortSignal) => apiClient.get<MyScopeResponse>("/org/my-scope", undefined, s),
  wings: (s?: AbortSignal) =>
    apiClient.get<{ total: number; items: WingOut[]; note?: string }>(
      "/org/wings", undefined, s),
  ranges: (s?: AbortSignal) =>
    apiClient.get<{
      total: number; items: RangeOut[]; commissionerates: RangeDistrict[]; note?: string;
    }>("/org/ranges", undefined, s),
  /** Searchable seat directory (~11,800 seats), for the login seat picker. */
  seats: (params: SeatQuery = {}, s?: AbortSignal) =>
    apiClient.get<SeatsResponse>("/org/seats", { ...params }, s),
  hierarchy: (s?: AbortSignal) => apiClient.get<HierarchyResponse>("/org/hierarchy", undefined, s),
  scopeMatrix: (s?: AbortSignal) => apiClient.get<ScopeMatrix>("/org/scope-matrix", undefined, s),
  roles: (s?: AbortSignal) => apiClient.get<OrgRolesResponse>("/org/roles", undefined, s),
  users: (s?: AbortSignal) => apiClient.get<OrgUsersResponse>("/org/users", undefined, s),
  createUser: (body: CreateUserBody, s?: AbortSignal) =>
    apiClient.post<OrgUser>("/org/users", body, undefined, s),
  assignRole: (userId: number, role: string, s?: AbortSignal) =>
    apiClient.request<OrgUser>(`/org/users/${userId}/role`, { method: "PUT", body: { role }, signal: s }),
  setScope: (userId: number, unitId: number | null, s?: AbortSignal) =>
    apiClient.request<OrgUser>(`/org/users/${userId}/scope`, { method: "PUT", body: { unit_id: unitId }, signal: s }),
  setActive: (userId: number, isActive: boolean, s?: AbortSignal) =>
    apiClient.post<OrgUser>(`/org/users/${userId}/active`, { is_active: isActive }, undefined, s),
  ensureRoles: (s?: AbortSignal) => apiClient.post<unknown>("/org/roles/ensure", undefined, undefined, s),
};
