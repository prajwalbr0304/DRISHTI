import { useRef, useState } from "react";
import { AlertTriangle, Bookmark, BookmarkCheck, Loader2, Mic, MicOff, SendHorizonal } from "lucide-react";
import type { AskLang, AskLangMode } from "@/stores/useAskStore";
import { useRole } from "@/providers/RoleProvider";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { SimpleTooltip } from "@/components/ui/tooltip";
import { useSpeech } from "@/components/ask/useSpeech";

/* ============================================================================
   Ask DRISHTI composer (doc 01 §4.7): text input · 🎙 voice (Web Speech) ·
   language toggle (EN/KN) · scope + model chips. Enter sends, Shift+Enter
   newlines. Dictation appends to whatever is typed; low-support browsers fall
   back to text only.
   ========================================================================== */

const MODEL_CHIP = "NL→SQL · Phase 2";

export function Composer({
  value,
  onChange,
  onSend,
  language,
  languageMode,
  onLanguageModeChange,
  onSaveQuery,
  busy = false,
}: {
  value: string;
  onChange: (v: string) => void;
  onSend: (opts?: { spoken?: boolean; voiceConfidence?: number; voiceLanguage?: string }) => void;
  /** effective language (drives mic locale, placeholder, text shaping). */
  language: AskLang;
  /** auto | en | kn — how the language is chosen. */
  languageMode: AskLangMode;
  onLanguageModeChange: (m: AskLangMode) => void;
  onSaveQuery?: (text: string) => void;
  busy?: boolean;
}) {
  const { def } = useRole();
  const baseRef = useRef("");
  const spokenRef = useRef(false);
  const [justSaved, setJustSaved] = useState(false);

  const speech = useSpeech({
    lang: language,
    onTranscript: (text) => {
      const base = baseRef.current;
      onChange(base ? `${base} ${text}` : text);
    },
  });

  const canSend = value.trim().length > 0;

  const handleMic = () => {
    if (speech.listening) {
      speech.stop();
      return;
    }
    baseRef.current = value.trim();
    spokenRef.current = true;
    speech.start();
  };

  const submit = () => {
    if (!canSend || busy) return;
    if (speech.listening) speech.stop();
    onSend({
      spoken: spokenRef.current,
      voiceConfidence: spokenRef.current ? speech.confidence ?? undefined : undefined,
      voiceLanguage: language,
    });
    spokenRef.current = false;
    baseRef.current = "";
  };

  const lowConfidence =
    speech.confidence != null && speech.confidence < 0.6 && value.trim().length > 0;

  const handleSave = () => {
    if (!canSend || !onSaveQuery) return;
    onSaveQuery(value.trim());
    setJustSaved(true);
    window.setTimeout(() => setJustSaved(false), 1600);
  };

  return (
    <div className="rounded-card border border-hairline bg-surface shadow-card">
      {/* Chips row */}
      <div className="flex flex-wrap items-center gap-2 px-3 pt-2.5">
        <div className="flex overflow-hidden rounded-control border border-hairline">
          <LangButton active={languageMode === "auto"} onClick={() => onLanguageModeChange("auto")} label="Auto" />
          <LangButton active={languageMode === "en"} onClick={() => onLanguageModeChange("en")} label="EN" />
          <LangButton active={languageMode === "kn"} onClick={() => onLanguageModeChange("kn")} label="ಕನ್ನಡ" />
        </div>
        {languageMode === "auto" && (
          <span className="text-12 text-content-dim" title="Detected from what you type">
            detected: <span lang={language}>{language === "kn" ? "ಕನ್ನಡ" : "English"}</span>
          </span>
        )}
        <span className="rounded-full bg-surface-2 px-2 py-0.5 text-12 text-content-dim">{def.scope}</span>
        <span className="rounded-full bg-surface-2 px-2 py-0.5 text-12 text-content-dim">{MODEL_CHIP}</span>
        {speech.listening && (
          <span className="ml-auto inline-flex items-center gap-1.5 text-12 font-medium text-primary">
            <span className="size-2 animate-pulse rounded-full bg-primary" />
            Listening · {language === "kn" ? "ಕನ್ನಡ" : "English"}
          </span>
        )}
      </div>

      {/* Text area */}
      <textarea
        value={value}
        lang={language}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            submit();
          }
        }}
        rows={2}
        placeholder={
          language === "kn"
            ? "DRISHTI ಅನ್ನು ಕೇಳಿ — ಉದಾ. ಬೆಂಗಳೂರಿನಲ್ಲಿ ಇತ್ತೀಚಿನ ಕಳ್ಳತನ ಪ್ರಕರಣಗಳು"
            : "Ask DRISHTI — e.g. cyber-fraud FIRs in Bengaluru City this year"
        }
        className="max-h-40 min-h-[3rem] w-full resize-y bg-transparent px-3.5 py-2.5 text-14 text-content placeholder:text-content-dim focus-visible:outline-none"
      />

      {/* Low-confidence dictation warning (doc 01 §4.7 / §9) */}
      {lowConfidence && (
        <div className="mx-3 mb-1 flex items-center gap-1.5 rounded-control bg-severity-high/10 px-2 py-1 text-12 text-severity-high">
          <AlertTriangle className="size-3.5 shrink-0" />
          Low-confidence transcription ({Math.round((speech.confidence ?? 0) * 100)}%) — please check
          the text before sending.
        </div>
      )}

      {/* Controls row */}
      <div className="flex items-center gap-1.5 px-3 pb-2.5">
        {speech.supported ? (
          <SimpleTooltip label={speech.listening ? "Stop dictation" : "Dictate (voice)"}>
            <Button
              type="button"
              variant={speech.listening ? "primary" : "ghost"}
              size="icon-sm"
              onClick={handleMic}
              aria-label={speech.listening ? "Stop dictation" : "Start voice dictation"}
              aria-pressed={speech.listening}
            >
              <Mic className={cn(speech.listening && "animate-pulse")} />
            </Button>
          </SimpleTooltip>
        ) : (
          <SimpleTooltip label="Voice needs a supported browser (Chrome/Edge). Type instead.">
            <span className="grid size-7 place-items-center rounded-control text-content-dim/50">
              <MicOff className="size-4" />
            </span>
          </SimpleTooltip>
        )}

        {onSaveQuery && (
          <SimpleTooltip label={justSaved ? "Saved to Saved Queries" : "Save this prompt"}>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              onClick={handleSave}
              disabled={!canSend}
              aria-label="Save this prompt"
            >
              {justSaved ? <BookmarkCheck className="text-accent" /> : <Bookmark />}
            </Button>
          </SimpleTooltip>
        )}

        <span className="ml-auto text-12 text-content-dim">
          <kbd className="rounded bg-surface-2 px-1 py-0.5">Enter</kbd> to send ·{" "}
          <kbd className="rounded bg-surface-2 px-1 py-0.5">Shift</kbd>+
          <kbd className="rounded bg-surface-2 px-1 py-0.5">Enter</kbd> for a new line
        </span>

        <Button type="button" onClick={submit} disabled={!canSend || busy} size="sm">
          {busy ? "Asking" : "Send"} {busy ? <Loader2 className="animate-spin" /> : <SendHorizonal />}
        </Button>
      </div>
    </div>
  );
}

function LangButton({ active, onClick, label }: { active: boolean; onClick: () => void; label: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "px-2.5 py-1 text-12 font-medium transition-colors",
        active ? "bg-primary text-primary-fg" : "bg-surface-2 text-content-dim hover:text-content",
      )}
    >
      {label}
    </button>
  );
}
