import { create } from "zustand";
import { api } from "@/api";
import { errorMessage } from "@/api/contracts";
import type { AskResponse, ChatSessionDetail, VizSpec } from "@/api/types";
import { detectLang } from "@/lib/lang";

/** Voice queries below this confidence must be confirmed before executing
 *  (Prompt 19 §E.3). Mirrors the composer's dictation threshold. */
export const VOICE_LOW_CONFIDENCE = 0.6;

/* ============================================================================
   Ask DRISHTI conversation state (doc 01 §4.7). Holds the CURRENT thread, the
   composer language (EN/KN), and any seed handed over from the ⌘K command bar.

   send() calls the Phase-2 NL->SQL engine (POST /chat/ask): it appends the user
   turn + a "thinking" placeholder, then replaces the placeholder with the
   grounded, cited answer (or a clarifying question / honest refusal). Multi-turn
   memory rides on session_id, threaded back on every send.
   ========================================================================== */

export type AskLang = "en" | "kn";
/** Composer language mode: Auto follows the typed script; EN/KN lock it. */
export type AskLangMode = "auto" | "en" | "kn";

export interface AskVoice {
  transcript_text?: string | null;
  language?: string | null;
  confidence?: number | null;
  is_low_confidence: boolean;
}

export interface AskMessage {
  id: string;
  sender: "user" | "assistant";
  text: string;
  language?: string;
  spoken?: boolean;
  /** The continuous dialog owns TTS for this turn. */
  voiceMode?: boolean;
  /* assistant answer anatomy (grounded answers) */
  citedRecordIds?: (number | string)[];
  generatedSql?: string | null;
  confidence?: number | null;
  modelVersion?: string | null;
  voice?: AskVoice | null;
  columns?: string[];
  rowsPreview?: unknown[][];
  rowCount?: number;
  /* Prompt 19: typed visualization spec + which planner produced the answer */
  visualization?: VizSpec | null;
  plannerSource?: string;
  plannerPrimary?: string;
  plannerDegraded?: boolean;
  /* turn state */
  thinking?: boolean;          // awaiting the engine
  needsClarification?: boolean; // engine asked for clarification
  blocked?: boolean;            // refused by scope/guard (no fabricated data)
  error?: boolean;              // request failed
  createdAt: number;
}

let seq = 0;
const nextId = () => `local_${Date.now().toString(36)}_${seq++}`;

interface AskState {
  messages: AskMessage[];
  /** the EFFECTIVE language sent to the engine + used for mic/placeholder. */
  language: AskLang;
  /** how `language` is chosen: auto-detect from the text, or a manual lock. */
  languageMode: AskLangMode;
  busy: boolean;
  sourceSessionId: number | null;
  sourceTitle: string | null;
  pendingSeed: string | null;

  setLanguage: (l: AskLang) => void;
  setLanguageMode: (m: AskLangMode) => void;
  /** derive the effective language from composer text (no-op unless mode=auto). */
  syncInput: (text: string) => void;
  send: (
    text: string,
    opts?: {
      spoken?: boolean;
      voiceConfidence?: number;
      voiceLanguage?: string;
      /** explicit user confirmation for a low/unknown-confidence spoken query. */
      voiceConfirmed?: boolean;
      /** continuous Voice Mode owns playback, so ChatView must not auto-speak again. */
      voiceMode?: boolean;
    },
  ) => Promise<AskResponse | null>;
  loadSession: (detail: ChatSessionDetail) => void;
  reset: () => void;
  setPendingSeed: (seed: string) => void;
  consumePendingSeed: () => string | null;
}

function answerFromResponse(id: string, res: AskResponse): AskMessage {
  return {
    id,
    sender: "assistant",
    text: res.reply,
    language: res.language,
    citedRecordIds: res.cited_record_ids ?? [],
    generatedSql: res.sql ?? null,
    confidence: res.confidence ?? null,
    modelVersion: res.model_version ?? null,
    columns: res.columns ?? [],
    rowsPreview: res.rows_preview ?? [],
    rowCount: res.row_count ?? 0,
    visualization: res.visualization ?? null,
    plannerSource: res.planner_source,
    plannerPrimary: res.planner_primary,
    plannerDegraded: res.planner_degraded,
    needsClarification: res.needs_clarification,
    blocked: res.blocked,
    createdAt: Date.now(),
  };
}

export const useAskStore = create<AskState>((set, get) => ({
  messages: [],
  language: "en",
  languageMode: "auto",
  busy: false,
  sourceSessionId: null,
  sourceTitle: null,
  pendingSeed: null,

  setLanguage: (language) => set({ language }),

  setLanguageMode: (languageMode) =>
    set((s) => ({ languageMode, language: languageMode === "auto" ? s.language : languageMode })),

  syncInput: (text) => {
    if (get().languageMode !== "auto") return;
    const detected = detectLang(text);
    if (detected !== get().language) set({ language: detected });
  },

  send: async (text, opts) => {
    const trimmed = text.trim();
    if (!trimmed || get().busy) return null;
    // Low or unknown-confidence speech must be explicitly confirmed. This
    // client guard mirrors the server boundary; it is not the security check.
    if (
      opts?.spoken &&
      (opts.voiceConfidence == null || opts.voiceConfidence < VOICE_LOW_CONFIDENCE) &&
      !opts.voiceConfirmed
    ) {
      return null;
    }
    // In auto mode the asked language is the script of the text actually sent.
    if (get().languageMode === "auto") {
      const detected = detectLang(trimmed);
      if (detected !== get().language) set({ language: detected });
    }
    const now = Date.now();
    const lang = get().language;
    // Preserve the transcript metadata for audit/read-back. Missing browser
    // confidence is deliberately treated as low confidence.
    const voice = opts?.spoken
      ? {
          transcript_text: trimmed,
          language: opts.voiceLanguage ?? lang,
          confidence: opts.voiceConfidence ?? null,
          is_low_confidence:
            opts.voiceConfidence == null || opts.voiceConfidence < VOICE_LOW_CONFIDENCE,
        }
      : null;
    const user: AskMessage = {
      id: nextId(), sender: "user", text: trimmed, language: lang,
      spoken: opts?.spoken, voiceMode: opts?.voiceMode, voice, createdAt: now,
    };
    const placeholderId = nextId();
    const thinking: AskMessage = {
      id: placeholderId, sender: "assistant", text: "", thinking: true, createdAt: now + 1,
    };
    set((s) => ({ messages: [...s.messages, user, thinking], busy: true }));

    try {
      const res = await api.chat.ask({
        question: trimmed,
        language: lang,
        session_id: get().sourceSessionId ?? undefined,
        voice:
          opts?.spoken
            ? {
                confidence: opts.voiceConfidence,
                language: opts.voiceLanguage ?? lang,
                transcript: trimmed,
                confirmed: opts.voiceConfirmed,
              }
            : undefined,
      });
      set((s) => ({
        busy: false,
        sourceSessionId: res.session_id,
        messages: s.messages.map((m) => (m.id === placeholderId ? answerFromResponse(placeholderId, res) : m)),
      }));
      return res;
    } catch (e) {
      set((s) => ({
        busy: false,
        messages: s.messages.map((m) =>
          m.id === placeholderId
            ? { ...m, thinking: false, error: true, text: errorMessage(e) }
            : m,
        ),
      }));
      return null;
    }
  },

  loadSession: (detail) =>
    set((s) => ({
      sourceSessionId: detail.session_id,
      sourceTitle: detail.title ?? null,
      // don't override an explicit EN/KN lock; in auto mode adopt the session's.
      language: s.languageMode === "auto" ? (detail.language === "kn" ? "kn" : "en") : s.language,
      messages: detail.messages.map((m) => ({
        id: `m${m.message_id}`,
        sender: m.sender === "assistant" ? "assistant" : "user",
        text: m.content ?? "",
        language: m.language ?? undefined,
        spoken: !!m.voice,
        citedRecordIds: m.cited_record_ids ?? [],
        generatedSql: m.generated_sql ?? null,
        confidence: m.confidence ?? null,
        modelVersion: m.model_version ?? null,
        voice: m.voice
          ? {
              transcript_text: m.voice.transcript_text,
              language: m.voice.language,
              confidence: m.voice.confidence,
              is_low_confidence: m.voice.is_low_confidence,
            }
          : null,
        createdAt: m.created_at ? Date.parse(m.created_at) : Date.now(),
      })),
    })),

  reset: () => set({ messages: [], sourceSessionId: null, sourceTitle: null }),

  setPendingSeed: (pendingSeed) => set({ pendingSeed }),
  consumePendingSeed: () => {
    const seed = get().pendingSeed;
    if (seed) set({ pendingSeed: null });
    return seed;
  },
}));
