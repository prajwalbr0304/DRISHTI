import { apiClient } from "@/api/client";
import type {
  CaseDetailResponse,
  CaseListResponse,
  CaseNetworkResponse,
  EvidenceCreateRequest,
  EvidenceCreateResponse,
  EvidenceListResponse,
  FilterOptionsResponse,
  LeadsResponse,
  SimilarResponse,
  SummaryResponse,
} from "@/api/types";

export type CaseListParams = {
  q?: string;
  district_id?: number;
  station_id?: number;
  major_head_id?: number;
  minor_head_id?: number;
  status_id?: number;
  gravity_id?: number;
  date_from?: string;
  date_to?: string;
  has_arrest?: boolean;
  has_chargesheet?: boolean;
  page?: number;
  page_size?: number;
};

/** Cases destination (services/ml/app/cases). Raw reads + AI decision-support. */
export const casesApi = {
  /** GET /cases — filterable, paginated case index. */
  list: (params: CaseListParams = {}, signal?: AbortSignal) =>
    apiClient.get<CaseListResponse>("/cases", params, signal),

  /** GET /cases/filters — reference values for the filter rail. */
  filters: (signal?: AbortSignal) =>
    apiClient.get<FilterOptionsResponse>("/cases/filters", undefined, signal),

  /** GET /cases/{id}/detail — full case (overview, people, sections, timeline). */
  detail: (caseId: number, signal?: AbortSignal) =>
    apiClient.get<CaseDetailResponse>(`/cases/${caseId}/detail`, undefined, signal),

  /** GET /cases/{id}/network — case-centric mini graph. */
  network: (caseId: number, signal?: AbortSignal) =>
    apiClient.get<CaseNetworkResponse>(`/cases/${caseId}/network`, undefined, signal),

  /** GET /cases/{id}/evidence — evidence feed. */
  evidence: (caseId: number, signal?: AbortSignal) =>
    apiClient.get<EvidenceListResponse>(`/cases/${caseId}/evidence`, undefined, signal),

  /** POST /cases/{id}/evidence — add evidence (IO only, server-gated). */
  addEvidence: (caseId: number, body: EvidenceCreateRequest, signal?: AbortSignal) =>
    apiClient.post<EvidenceCreateResponse>(`/cases/${caseId}/evidence`, body, undefined, signal),

  /** GET /cases/{id}/similar — semantic similar-case search (read-only). */
  similar: (caseId: number, k = 5, signal?: AbortSignal) =>
    apiClient.get<SimilarResponse>(`/cases/${caseId}/similar`, { k }, signal),

  /** POST /cases/{id}/summary — generate + persist a fully-cited AISummary. */
  summary: (caseId: number, signal?: AbortSignal) =>
    apiClient.post<SummaryResponse>(`/cases/${caseId}/summary`, undefined, undefined, signal),

  /** POST /cases/{id}/leads — ranked officer recommendations. */
  leads: (caseId: number, signal?: AbortSignal) =>
    apiClient.post<LeadsResponse>(`/cases/${caseId}/leads`, undefined, undefined, signal),
};
