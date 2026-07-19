import { apiClient } from "@/api/client";

/* Phase-15 optional approved-text RAG assistant (services/ml/app/rag). Answers
   ONLY from approved SOP/policy text, cites source/version, refuses when
   unsupported, and is gracefully disabled by default. Browser -> FastAPI only. */

export interface RagStatus {
  enabled: boolean;
  provider: string;
  knowledge_base_version: string;
  approved_sources: number;
  retention_days: number;
  reason?: string | null;
}
export interface RagCitation {
  source: string;
  version?: string | null;
  title?: string | null;
}
export interface RagAnswer {
  enabled: boolean;
  provider: string;
  answer: string;
  citations: RagCitation[];
  refused: boolean;
  knowledge_base_version: string;
  case_scope_ref_id?: string | null;
  unit_scope_ref_id?: string | null;
  latency_ms?: number | null;
}
export interface RagEvalItem {
  question: string;
  expect_answer: boolean;
  expect_source?: string | null;
  refused: boolean;
  citations: string[];
  passed: boolean;
}
export interface RagEvalResult {
  total: number;
  passed: number;
  failed: number;
  accuracy: number;
  knowledge_base_version: string;
  items: RagEvalItem[];
}

export const ragApi = {
  status: (s?: AbortSignal) => apiClient.get<RagStatus>("/rag/status", undefined, s),
  ask: (body: { question: string; case_scope_ref_id?: string; unit_scope_ref_id?: string }, s?: AbortSignal) =>
    apiClient.post<RagAnswer>("/rag/ask", body, undefined, s),
  evaluate: (s?: AbortSignal) => apiClient.get<RagEvalResult>("/rag/evaluate", undefined, s),
};
