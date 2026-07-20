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

export const orgApi = {
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
