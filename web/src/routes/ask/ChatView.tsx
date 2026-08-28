import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { FileDown, MessageSquarePlus, Sparkles } from "lucide-react";
import { api } from "@/api";
import { useRole } from "@/providers/RoleProvider";
import { exportSessionPdf } from "@/lib/exportSessionPdf";
import { useAskStore, VOICE_LOW_CONFIDENCE } from "@/stores/useAskStore";
import { useSavedQueriesStore } from "@/stores/useSavedQueriesStore";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Composer } from "@/components/ask/Composer";
import { VoiceModeDialog } from "@/components/ask/VoiceModeDialog";
import { AnswerCard } from "@/components/ask/AnswerCard";
import { UserBubble } from "@/components/ask/UserBubble";
import { useTts } from "@/components/ask/useTts";
import { useLoadSession } from "@/routes/ask/useLoadSession";
import type { AskMessage } from "@/stores/useAskStore";

/* ============================================================================
   Chat (doc 01 §4.7): a focused, readable column — composer + the turn thread.
   New questions get an honest Phase-2 pending answer; the seeded "grounded
   examples" replay REAL past conversations so the full answer anatomy (reply,
   inline citations, SQL, confidence) is visible immediately.
   ========================================================================== */
export function ChatView() {
  const messages = useAskStore((s) => s.messages);
  const language = useAskStore((s) => s.language);
  const languageMode = useAskStore((s) => s.languageMode);
  const setLanguageMode = useAskStore((s) => s.setLanguageMode);
  const syncInput = useAskStore((s) => s.syncInput);
  const send = useAskStore((s) => s.send);
  const busy = useAskStore((s) => s.busy);
  const reset = useAskStore((s) => s.reset);
  const sourceTitle = useAskStore((s) => s.sourceTitle);
  const pendingSeed = useAskStore((s) => s.pendingSeed);
  const consumePendingSeed = useAskStore((s) => s.consumePendingSeed);
  const saveQuery = useSavedQueriesStore((s) => s.save);
  const sourceSessionId = useAskStore((s) => s.sourceSessionId);
  const { role, def } = useRole();
  const { open } = useLoadSession();
  const [exporting, setExporting] = useState(false);
  const [voiceModeOpen, setVoiceModeOpen] = useState(false);
  const capabilities = useQuery({
    queryKey: ["chat", "capabilities"],
    queryFn: ({ signal }) => api.chat.capabilities(signal),
    staleTime: 5 * 60 * 1000,
  });
  const voiceCapability = capabilities.data?.voice;
  const continuousVoiceAvailable =
    voiceCapability?.continuous_mode_available ?? voiceCapability?.browser_fallback ?? false;
  const voiceModeAvailable =
    voiceCapability?.voice_query_enabled === true && continuousVoiceAvailable;
  const voiceThreshold = voiceCapability?.low_confidence_threshold ?? VOICE_LOW_CONFIDENCE;
  const speechProviderLabel =
    voiceCapability?.provider === "browser-web-speech"
      ? "Browser speech"
      : voiceCapability?.provider ?? "Browser speech";
  const plannerLabel = capabilities.data?.semantic_planner.provider
    ? `${capabilities.data.semantic_planner.provider} (${capabilities.data.semantic_planner.primary})`
    : "DRISHTI NL→SQL";

  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  // --- Text-to-speech: read answers back in the detected language (Phase 4) ---
  const tts = useTts();
  const [speakingId, setSpeakingId] = useState<string | null>(null);
  const autoSpokenRef = useRef<string | null>(null);

  const speak = (m: AskMessage) => {
    setSpeakingId(m.id);
    tts.speak(m.text, m.language ?? "en", { onEnd: () => setSpeakingId(null) });
  };
  const stopSpeak = () => {
    tts.stop();
    setSpeakingId(null);
  };

  // Voice-in → voice-out: auto-read a fresh answer when its question was spoken.
  useEffect(() => {
    if (!tts.supported || messages.length < 2) return;
    const last = messages[messages.length - 1];
    const prev = messages[messages.length - 2];
    if (
      last.sender === "assistant" && !last.thinking && !last.error && last.text &&
      prev?.sender === "user" && prev.spoken && !prev.voiceMode &&
      autoSpokenRef.current !== last.id
    ) {
      autoSpokenRef.current = last.id;
      speak(last);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages]);

  // Set the composer text and re-run auto-detect (EN/KN) in one place.
  const setText = (v: string) => {
    setInput(v);
    syncInput(v);
  };

  // Seed the composer from ⌘K (Ask DRISHTI everywhere) — reacts even if this
  // view is already mounted when a new question is handed over.
  useEffect(() => {
    if (pendingSeed) {
      setText(pendingSeed);
      consumePendingSeed();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingSeed, consumePendingSeed]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length]);

  const submit = (opts?: {
    spoken?: boolean;
    voiceConfidence?: number;
    voiceLanguage?: string;
    voiceConfirmed?: boolean;
  }) => {
    if (busy || !input.trim()) return;
    void send(input, opts);
    setInput("");
  };

  const empty = messages.length === 0;

  return (
    <div className="mx-auto flex h-[calc(100vh-15rem)] min-h-[26rem] max-w-3xl flex-col">
      {/* Thread header */}
      <div className="mb-2 flex h-7 items-center justify-between">
        {sourceTitle ? (
          <Badge variant="neutral">Replaying past session · {sourceTitle}</Badge>
        ) : (
          <span className="text-12 text-content-dim">Grounded, cited answers — scoped to your role</span>
        )}
        {!empty && (
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="sm"
              disabled={exporting}
              onClick={async () => {
                setExporting(true);
                try {
                  await exportSessionPdf(messages, {
                    sessionId: sourceSessionId,
                    roleLabel: def.label,
                    role,
                    scope: def.scope,
                    title: sourceTitle,
                  });
                } finally {
                  setExporting(false);
                }
              }}
            >
              <FileDown /> {exporting ? "Preparing…" : "Export PDF"}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                stopSpeak();
                reset();
              }}
            >
              <MessageSquarePlus /> New chat
            </Button>
          </div>
        )}
      </div>

      {/* Thread / empty state */}
      <div className="min-h-0 flex-1 overflow-y-auto pr-1">
        {empty ? (
          <ChatEmptyState onPick={(id) => open(id)} onPrompt={(q) => setText(q)} />
        ) : (
          <div className="space-y-4 py-2">
            {messages.map((m) =>
              m.sender === "user" ? (
                <UserBubble key={m.id} message={m} />
              ) : (
                <AnswerCard
                  key={m.id}
                  message={m}
                  tts={{
                    supported: tts.supported,
                    isSpeaking: speakingId === m.id,
                    onSpeak: speak,
                    onStop: stopSpeak,
                  }}
                />
              ),
            )}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      {/* Composer */}
      <div className="pt-3">
        <Composer
          value={input}
          onChange={setText}
          onSend={submit}
          language={language}
          languageMode={languageMode}
          onLanguageModeChange={setLanguageMode}
          onSaveQuery={(text) => saveQuery(text, language)}
          onOpenVoiceMode={() => {
            stopSpeak();
            setVoiceModeOpen(true);
          }}
          voiceModeAvailable={voiceModeAvailable}
          lowConfidenceThreshold={voiceThreshold}
          modelLabel={
            capabilities.data?.semantic_planner.primary
              ? `NL→SQL · ${capabilities.data.semantic_planner.primary}`
              : undefined
          }
          busy={busy}
        />
      </div>

      <VoiceModeDialog
        open={voiceModeOpen}
        onOpenChange={setVoiceModeOpen}
        language={language}
        providerLabel={speechProviderLabel}
        plannerLabel={plannerLabel}
      />
    </div>
  );
}

function ChatEmptyState({
  onPick,
  onPrompt,
}: {
  onPick: (sessionId: number) => void;
  onPrompt: (q: string) => void;
}) {
  const sessions = useQuery({
    queryKey: ["chat", "sessions"],
    queryFn: ({ signal }) => api.chat.sessions(50, signal),
  });
  const examples = (sessions.data?.sessions ?? []).filter((s) => s.first_question).slice(0, 5);

  return (
    <div className="flex h-full flex-col items-center justify-center px-4 text-center">
      <div className="mb-3 grid size-12 place-items-center rounded-card bg-surface-2 text-primary">
        <Sparkles className="size-6" />
      </div>
      <h2 className="text-20 font-semibold text-content">Ask DRISHTI</h2>
      <p className="mt-1 max-w-md text-13 text-content-dim">
        Ask in English or Kannada. Answers are grounded in the data with inline citations, the exact
        read-only SQL, and a confidence score — scoped to your role.
      </p>

      {examples.length > 0 && (
        <div className="mt-6 w-full max-w-lg text-left">
          <div className="mb-2 text-12 font-semibold uppercase tracking-wide text-content-dim">
            Grounded examples — replay a real answer
          </div>
          <div className="space-y-2">
            {examples.map((s) => (
              <button
                key={s.session_id}
                type="button"
                onClick={() => onPick(s.session_id)}
                className="flex w-full items-center gap-2 rounded-card border border-hairline bg-surface-2/40 px-3 py-2 text-left transition-colors hover:bg-surface-2"
              >
                <span lang={s.language ?? "en"} className="min-w-0 flex-1 truncate text-13 text-content">
                  {s.first_question}
                </span>
                {s.language === "kn" && <Badge variant="neutral">ಕನ್ನಡ</Badge>}
                {s.has_voice && <Badge variant="neutral">voice</Badge>}
                <Badge variant="neutral" className="capitalize">{s.role}</Badge>
              </button>
            ))}
          </div>
          <p className="mt-3 text-12 text-content-dim">
            Or type your own question below — the assistant translates it to a read-only SQL query,
            runs it, and answers with citations.
          </p>
        </div>
      )}
    </div>
  );
}
