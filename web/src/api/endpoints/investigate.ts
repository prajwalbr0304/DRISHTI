import { apiClient } from "@/api/client";

/* Prompt 20 Part D — case-scoped investigation assistant (services/ml/app/investigate).
   Thin orchestration over existing case summary/similar/identity/leads/timeline;
   facts (evidence) are separated from hypotheses (suggestions). Case-scoped and
   policymaker-denied server-side. Not a second free-form chatbot. */

export interface InvestigationItem {
  type: string;
  label: string;
  detail: string;
  source_ids: string[];
  basis: "evidence" | "hypothesis";
  confidence?: number | null;
}
export interface CitableObject {
  ref_table: string;
  ref_id: string;
  label: string;
  kind: string;
}
export interface InvestigationAnswer {
  case_id: number;
  crime_no?: string | null;
  question?: string | null;
  language: string;
  intent: string;
  answer: string;
  confidence: number;
  facts: InvestigationItem[];
  hypotheses: InvestigationItem[];
  citable_objects: CitableObject[];
  citations: string[];
  reasoning_summary: string;
  limitations: string[];
  planner_source: string;
}

export const investigateApi = {
  brief: (caseId: number, k = 5, s?: AbortSignal) =>
    apiClient.get<InvestigationAnswer>(`/investigate/${caseId}/brief`, { k }, s),
  ask: (caseId: number, question: string, k = 5, s?: AbortSignal) =>
    apiClient.post<InvestigationAnswer>(`/investigate/${caseId}/ask`, { question, k }, undefined, s),
};
