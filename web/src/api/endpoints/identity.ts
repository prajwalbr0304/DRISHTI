import { apiClient } from "@/api/client";
import type {
  IdentityCandidateListResponse,
  IdentityGenerateResponse,
  IdentityLinkStats,
  IdentityMergeResult,
  IdentityOrgSearchResponse,
  IdentityOrgSummary,
  IdentityPartyMutation,
  IdentityPersonDetail,
  IdentityPersonSearchResponse,
  IdentityReviewResult,
} from "@/api/types";

/** Canonical identity + entity resolution (services/ml/app/identity).
    Browser -> FastAPI only. Writes are localhost + synthetic-DB guarded. */
export const identityApi = {
  /** GET /identity/stats — canonical-identity coverage stats. */
  stats: (signal?: AbortSignal) => apiClient.get<IdentityLinkStats>("/identity/stats", undefined, signal),

  // --- persons ---
  searchPersons: (
    params: { q?: string; gender_id?: number; juvenile?: boolean; status?: string; page?: number; page_size?: number } = {},
    signal?: AbortSignal,
  ) => apiClient.get<IdentityPersonSearchResponse>("/identity/persons", params, signal),

  getPerson: (cpid: number, signal?: AbortSignal) =>
    apiClient.get<IdentityPersonDetail>(`/identity/persons/${cpid}`, undefined, signal),

  createPerson: (
    body: { display_label?: string; is_unknown?: boolean; primary_gender_id?: number;
            approx_birth_year?: number; is_juvenile?: boolean; actor?: string },
    signal?: AbortSignal,
  ) => apiClient.post<IdentityPersonDetail>("/identity/persons", body, undefined, signal),

  updatePerson: (
    cpid: number,
    body: { display_label?: string; primary_gender_id?: number; approx_birth_year?: number; is_juvenile?: boolean; actor?: string },
    signal?: AbortSignal,
  ) => apiClient.request<IdentityPersonDetail>(`/identity/persons/${cpid}`, { method: "PATCH", body, signal }),

  // --- attributes (with sensitivity) ---
  addAlias: (cpid: number, body: { alias_name: string; alias_type?: string; actor?: string }, signal?: AbortSignal) =>
    apiClient.post<IdentityPersonDetail>(`/identity/persons/${cpid}/aliases`, body, undefined, signal),
  addIdentifier: (cpid: number, body: { identifier_type: string; identifier_value: string; sensitivity?: string; actor?: string }, signal?: AbortSignal) =>
    apiClient.post<IdentityPersonDetail>(`/identity/persons/${cpid}/identifiers`, body, undefined, signal),
  addContact: (cpid: number, body: { contact_type?: string; contact_value: string; sensitivity?: string; actor?: string }, signal?: AbortSignal) =>
    apiClient.post<IdentityPersonDetail>(`/identity/persons/${cpid}/contacts`, body, undefined, signal),
  addAddress: (cpid: number, body: { district_id?: number; address_text?: string; latitude?: number; longitude?: number; sensitivity?: string; actor?: string }, signal?: AbortSignal) =>
    apiClient.post<IdentityPersonDetail>(`/identity/persons/${cpid}/addresses`, body, undefined, signal),
  deleteAlias: (cpid: number, rowId: number, signal?: AbortSignal) =>
    apiClient.request<IdentityPersonDetail>(`/identity/persons/${cpid}/aliases/${rowId}`, { method: "DELETE", signal }),

  // --- organisations ---
  searchOrgs: (params: { q?: string; page?: number; page_size?: number } = {}, signal?: AbortSignal) =>
    apiClient.get<IdentityOrgSearchResponse>("/identity/organisations", params, signal),
  createOrg: (body: { name: string; org_type?: string; actor?: string }, signal?: AbortSignal) =>
    apiClient.post<IdentityOrgSummary>("/identity/organisations", body, undefined, signal),

  // --- case-party roles ---
  addParty: (
    caseId: number,
    body: { canonical_person_id?: number; canonical_organisation_id?: number; is_unknown?: boolean; role_type: string; party_label?: string; sequence_no?: number; actor?: string },
    signal?: AbortSignal,
  ) => apiClient.post<IdentityPartyMutation>(`/identity/cases/${caseId}/parties`, body, undefined, signal),
  updateParty: (roleId: number, body: { role_type?: string; sequence_no?: number; actor?: string }, signal?: AbortSignal) =>
    apiClient.request<IdentityPartyMutation>(`/identity/parties/${roleId}`, { method: "PATCH", body, signal }),
  removeParty: (roleId: number, signal?: AbortSignal) =>
    apiClient.request<{ case_party_role_id: number; case_master_id: number; removed: boolean }>(
      `/identity/parties/${roleId}`, { method: "DELETE", signal }),

  // --- entity resolution ---
  candidates: (params: { status?: string; page?: number; page_size?: number } = {}, signal?: AbortSignal) =>
    apiClient.get<IdentityCandidateListResponse>("/identity/resolution/candidates", params, signal),
  generate: (body: { canonical_person_id?: number; limit?: number; min_score?: number; actor?: string }, signal?: AbortSignal) =>
    apiClient.post<IdentityGenerateResponse>("/identity/resolution/generate", body, undefined, signal),
  reviewCandidate: (
    candId: number,
    body: { action: "accept" | "reject" | "create_new"; winner_canonical_person_id?: number; reason?: string; actor?: string },
    signal?: AbortSignal,
  ) => apiClient.post<IdentityReviewResult>(`/identity/resolution/candidates/${candId}/review`, body, undefined, signal),

  // --- merge / unmerge ---
  merge: (cpid: number, body: { loser_canonical_person_id: number; reason?: string; actor?: string }, signal?: AbortSignal) =>
    apiClient.post<IdentityMergeResult>(`/identity/persons/${cpid}/merge`, body, undefined, signal),
  unmerge: (cpid: number, body: { loser_canonical_person_id: number; reason?: string; actor?: string }, signal?: AbortSignal) =>
    apiClient.post<IdentityMergeResult>(`/identity/persons/${cpid}/unmerge`, body, undefined, signal),
};
