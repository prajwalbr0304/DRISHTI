import { apiClient } from "@/api/client";
import type { AskResponse, Capabilities, ChatSessionDetail, ChatSessionsResponse } from "@/api/types";

export interface AskVoiceBody {
  confidence?: number;
  language?: string;
  transcript?: string;
  confirmed?: boolean;
  auto_send?: boolean;
}
export interface AskBody {
  question: string;
  session_id?: number;
  language?: string;
  voice?: AskVoiceBody;
}
export interface TranslateResult {
  text: string;
  translated?: string | null;
  target: string;
  available: boolean;
}
export interface ExplainBody {
  context: string;
  session_id?: number;
  language?: string;
}

/**
 * Ask DRISHTI (services/ml/app/chat). Phase-2 NL->SQL engine + chat history.
 * `ask` returns a grounded, cited, read-only answer scoped to the caller's role
 * (X-Role, sent by the client). History reads stored sessions/messages.
 */
export const chatApi = {
  voiceSession: (body: { voice: string; language: string; audio_consent: boolean; session_id?: number }) =>
    apiClient.post<{ url: string; ticket: string; expires_in: number; session_seconds: number; model: string }>("/chat/voice/session", body),
  /** POST /chat/ask — grounded NL->SQL answer (reply + SQL + citations + confidence). */
  ask: (body: AskBody, signal?: AbortSignal) =>
    apiClient.post<AskResponse>("/chat/ask", body, undefined, signal),

  /** POST /chat/explain — route a chart/hotspot/alert context into the engine. */
  explain: (body: ExplainBody, signal?: AbortSignal) =>
    apiClient.post<AskResponse>("/chat/explain", body, undefined, signal),

  /** POST /chat/translate — best-effort EN<->KN for the bilingual PDF export. */
  translate: (text: string, target: "en" | "kn", signal?: AbortSignal) =>
    apiClient.post<TranslateResult>("/chat/translate", { text, target }, undefined, signal),

  /** GET /chat/sessions — past conversation sessions (History). */
  sessions: (limit = 50, signal?: AbortSignal) =>
    apiClient.get<ChatSessionsResponse>("/chat/sessions", { limit }, signal),

  /** GET /chat/sessions/{id} — one session's messages + voice transcripts. */
  session: (sessionId: number, signal?: AbortSignal) =>
    apiClient.get<ChatSessionDetail>(`/chat/sessions/${sessionId}`, undefined, signal),

  /** GET /chat/capabilities — server-declared planner / voice / visualization
   *  capabilities (Prompt 19). Voice provider is "browser-web-speech" here. */
  capabilities: (signal?: AbortSignal) =>
    apiClient.get<Capabilities>("/chat/capabilities", undefined, signal),
};
