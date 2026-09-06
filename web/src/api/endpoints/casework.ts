import { apiClient } from "@/api/client";
import type {
  CwBailInput,
  CwCourtEventInput,
  CwCourtLifecycleView,
  CwDispositionInput,
  CwLabResult,
  CwLabResultInput,
  CwLabResultListResponse,
  CwLookups,
  CwOutcomeInput,
  CwPropertyItem,
  CwPropertyItemInput,
  CwSeizureCreate,
  CwSeizureListResponse,
  CwStatement,
  CwStatementCorrection,
  CwStatementCreate,
  CwStatementListResponse,
  CwTimelineResponse,
} from "@/api/types";

/** Casework (services/ml/app/casework): statements, property/seizure, lab
 *  results, court/bail/disposition/outcome, event-backed lifecycle + timeline.
 *  Browser -> FastAPI only; manual entry; files linked by id (never parsed). */
export const caseworkApi = {
  lookups: (signal?: AbortSignal) =>
    apiClient.get<CwLookups>("/casework/lookups", undefined, signal),
  /** Soonest scheduled hearings in the caller's scope, confined server-side. */
  nextHearings: (params: { limit?: number } = {}, signal?: AbortSignal) =>
    apiClient.get<NextHearingsResponse>("/casework/hearings/next", params, signal),

  timeline: (caseId: number, signal?: AbortSignal) =>
    apiClient.get<CwTimelineResponse>(`/casework/cases/${caseId}/timeline`, undefined, signal),

  // --- statements ---
  listStatements: (caseId: number, signal?: AbortSignal) =>
    apiClient.get<CwStatementListResponse>(`/casework/cases/${caseId}/statements`, undefined, signal),
  createStatement: (caseId: number, body: CwStatementCreate, signal?: AbortSignal) =>
    apiClient.post<CwStatement>(`/casework/cases/${caseId}/statements`, body, undefined, signal),
  getStatement: (sid: number, signal?: AbortSignal) =>
    apiClient.get<CwStatement>(`/casework/statements/${sid}`, undefined, signal),
  correctStatement: (sid: number, body: CwStatementCorrection, signal?: AbortSignal) =>
    apiClient.request<CwStatement>(`/casework/statements/${sid}`, { method: "PUT", body, signal }),
  reviewStatement: (sid: number, body: { actor?: string; note?: string } = {}, signal?: AbortSignal) =>
    apiClient.post<CwStatement>(`/casework/statements/${sid}/review`, body, undefined, signal),

  // --- property / seizure ---
  listSeizures: (caseId: number, signal?: AbortSignal) =>
    apiClient.get<CwSeizureListResponse>(`/casework/cases/${caseId}/seizures`, undefined, signal),
  createSeizure: (caseId: number, body: CwSeizureCreate, signal?: AbortSignal) =>
    apiClient.post<CwSeizureListResponse>(`/casework/cases/${caseId}/seizures`, body, undefined, signal),
  addPropertyItem: (caseId: number, body: CwPropertyItemInput, seizureId?: number, signal?: AbortSignal) =>
    apiClient.post<CwPropertyItem>(`/casework/cases/${caseId}/property-items`, body,
      seizureId ? { seizure_id: seizureId } : undefined, signal),
  changePropertyStatus: (pid: number, body: { status: string; note?: string; actor?: string }, signal?: AbortSignal) =>
    apiClient.request<CwPropertyItem>(`/casework/property-items/${pid}/status`, { method: "PUT", body, signal }),

  // --- lab results ---
  listLabs: (caseId: number, signal?: AbortSignal) =>
    apiClient.get<CwLabResultListResponse>(`/casework/cases/${caseId}/lab-results`, undefined, signal),
  createLab: (caseId: number, body: CwLabResultInput, signal?: AbortSignal) =>
    apiClient.post<CwLabResult>(`/casework/cases/${caseId}/lab-results`, body, undefined, signal),
  updateLab: (lid: number, body: Partial<CwLabResultInput> & { status?: string }, signal?: AbortSignal) =>
    apiClient.request<CwLabResult>(`/casework/lab-results/${lid}`, { method: "PUT", body, signal }),

  // --- court / bail / disposition / outcome / lifecycle ---
  court: (caseId: number, signal?: AbortSignal) =>
    apiClient.get<CwCourtLifecycleView>(`/casework/cases/${caseId}/court`, undefined, signal),
  addCourtEvent: (caseId: number, body: CwCourtEventInput, signal?: AbortSignal) =>
    apiClient.post<CwCourtLifecycleView>(`/casework/cases/${caseId}/court-events`, body, undefined, signal),
  addBail: (caseId: number, body: CwBailInput, signal?: AbortSignal) =>
    apiClient.post<CwCourtLifecycleView>(`/casework/cases/${caseId}/bail`, body, undefined, signal),
  addDisposition: (caseId: number, body: CwDispositionInput, signal?: AbortSignal) =>
    apiClient.post<CwCourtLifecycleView>(`/casework/cases/${caseId}/disposition`, body, undefined, signal),
  addOutcome: (caseId: number, body: CwOutcomeInput, signal?: AbortSignal) =>
    apiClient.post<CwCourtLifecycleView>(`/casework/cases/${caseId}/outcome`, body, undefined, signal),
  addLifecycleEvent: (
    caseId: number,
    body: { event_type: string; occurred_at?: string; actor_role?: string; payload?: Record<string, unknown> },
    signal?: AbortSignal,
  ) => apiClient.post(`/casework/cases/${caseId}/lifecycle-events`, body, undefined, signal),
};


/* ============================================================================
   Scoped "next court date".

   This card shipped in an honest `pending` state because nothing in the corpus was
   scheduled-but-not-yet-heard: CourtEvent.ScheduledAt was unset on every row and
   each event already carried an OccurredAt. Migration 036 and datagen now write the
   adjourned-to date for cases awaiting trial.
   ========================================================================== */

export interface NextHearingRow {
  court_event_id: number;
  case_id: number;
  case_number?: string | null;
  scheduled_on?: string | null;
  /** Counted from the corpus as-of date, NOT from today: the synthetic dataset
   *  ends before the current date, so counting from today would report every
   *  hearing as overdue by however long the demo has been running. */
  days_away?: number | null;
  unit_id?: number | null;
  unit_name?: string | null;
  district_name?: string | null;
  court_name?: string | null;
}

export interface NextHearingsResponse {
  scope: { district_ids?: number[] | null; unit_id?: number | null };
  /** The corpus reference point — the last court event that actually happened.
   *  Reported so "in 21 days" is anchored to something the caller can see. */
  as_of?: string | null;
  data_age_days?: number | null;
  /** null, never 0, when nothing is listed: "no hearing scheduled" and "a hearing
   *  today" are different statements and must not render identically. */
  days_to_next_hearing?: number | null;
  next_hearing_on?: string | null;
  pending_hearings: number;
  cases_awaiting_hearing: number;
  hearings: NextHearingRow[];
  empty: boolean;
  limitations: string[];
  dataset: string;
}
