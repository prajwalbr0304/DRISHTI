import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  AudioLines,
  Loader2,
  Mic,
  RotateCcw,
  SendHorizonal,
  Square,
  Volume2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import { useAskStore, type AskLang } from "@/stores/useAskStore";
import { useSpeech, type SpeechFinalResult } from "@/components/ask/useSpeech";
import { useTts } from "@/components/ask/useTts";

type VoicePhase = "idle" | "listening" | "review" | "thinking" | "speaking" | "error";

const STATUS: Record<VoicePhase, string> = {
  idle: "Ready when you are",
  listening: "Listening…",
  review: "Review what I heard",
  thinking: "Checking DRISHTI…",
  speaking: "Speaking — tap to interrupt",
  error: "Voice mode paused",
};

export function VoiceModeDialog({
  open,
  onOpenChange,
  language,
  confidenceThreshold,
  providerLabel,
  plannerLabel,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  language: AskLang;
  confidenceThreshold: number;
  providerLabel: string;
  plannerLabel: string;
}) {
  const send = useAskStore((state) => state.send);
  const busy = useAskStore((state) => state.busy);
  const {
    supported: ttsSupported,
    speak: speakText,
    stop: stopSpeaking,
  } = useTts();
  const [phase, setPhase] = useState<VoicePhase>("idle");
  const [transcript, setTranscript] = useState("");
  const [assistantText, setAssistantText] = useState("");
  const [confidence, setConfidence] = useState<number | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [finalResult, setFinalResult] = useState<SpeechFinalResult | null>(null);

  const openRef = useRef(open);
  const phaseRef = useRef<VoicePhase>(phase);
  const finalReceivedRef = useRef(false);
  const submittingRef = useRef(false);
  const lifecycleRef = useRef(0);
  const restartTimerRef = useRef<number | null>(null);
  const beginListeningRef = useRef<() => void>(() => undefined);

  useEffect(() => {
    openRef.current = open;
  }, [open]);
  useEffect(() => {
    phaseRef.current = phase;
  }, [phase]);

  const clearRestartTimer = useCallback(() => {
    if (restartTimerRef.current != null) {
      window.clearTimeout(restartTimerRef.current);
      restartTimerRef.current = null;
    }
  }, []);

  const {
    start: startSpeech,
    stop: stopSpeech,
    abort: abortSpeech,
  } = useSpeech({
    lang: language,
    onTranscript: setTranscript,
    onFinal: (result) => {
      finalReceivedRef.current = true;
      setFinalResult(result);
    },
    onError: (code) => {
      if (!openRef.current || submittingRef.current) return;
      const denied = code === "not-allowed" || code === "service-not-allowed";
      setErrorMessage(
        denied
          ? "Microphone access was denied. Allow it in your browser, or use text chat."
          : "I couldn't access browser speech recognition. You can retry or use text chat.",
      );
      setPhase("error");
    },
    onEnd: () => {
      window.setTimeout(() => {
        if (
          openRef.current &&
          phaseRef.current === "listening" &&
          !finalReceivedRef.current &&
          !submittingRef.current
        ) {
          setErrorMessage("I didn't catch a complete phrase. Tap the microphone to try again.");
          setPhase("idle");
        }
      }, 0);
    },
  });

  const beginListening = useCallback(() => {
    if (!openRef.current || busy || submittingRef.current) return;
    clearRestartTimer();
    stopSpeaking();
    finalReceivedRef.current = false;
    setFinalResult(null);
    setTranscript("");
    setAssistantText("");
    setConfidence(null);
    setErrorMessage(null);
    setPhase("listening");
    if (!startSpeech()) {
      setErrorMessage("Browser speech recognition is unavailable. Continue with text chat instead.");
      setPhase("error");
    }
  }, [busy, clearRestartTimer, startSpeech, stopSpeaking]);

  useEffect(() => {
    beginListeningRef.current = beginListening;
  }, [beginListening]);

  const scheduleNextTurn = useCallback(() => {
    clearRestartTimer();
    if (!openRef.current) return;
    restartTimerRef.current = window.setTimeout(() => beginListeningRef.current(), 450);
  }, [clearRestartTimer]);

  const submitTurn = useCallback(
    async (text: string, resultConfidence: number | null, confirmed: boolean) => {
      const cleaned = text.trim();
      if (!cleaned || submittingRef.current) return;
      submittingRef.current = true;
      const lifecycle = lifecycleRef.current;
      stopSpeech();
      setConfidence(resultConfidence);
      setErrorMessage(null);
      setPhase("thinking");

      const response = await send(cleaned, {
        spoken: true,
        voiceMode: true,
        voiceConfidence: resultConfidence ?? undefined,
        voiceLanguage: language,
        voiceConfirmed: confirmed,
      });
      submittingRef.current = false;
      if (!openRef.current || lifecycle !== lifecycleRef.current) return;

      if (!response) {
        setErrorMessage("DRISHTI couldn't complete that turn. Review the chat response or try again.");
        setPhase("error");
        return;
      }

      setAssistantText(response.reply);
      if (!ttsSupported) {
        setPhase("idle");
        scheduleNextTurn();
        return;
      }

      setPhase("speaking");
      speakText(response.reply, response.language, {
        onEnd: () => {
          if (!openRef.current) return;
          setPhase("idle");
          scheduleNextTurn();
        },
      });
    },
    [language, scheduleNextTurn, send, speakText, stopSpeech, ttsSupported],
  );

  useEffect(() => {
    if (!open || !finalResult || phaseRef.current !== "listening") return;
    setTranscript(finalResult.text);
    setConfidence(finalResult.confidence);
    setFinalResult(null);

    if (finalResult.confidence != null && finalResult.confidence >= confidenceThreshold) {
      void submitTurn(finalResult.text, finalResult.confidence, false);
    } else {
      setPhase("review");
    }
  }, [confidenceThreshold, finalResult, open, submitTurn]);

  useEffect(() => {
    if (!open) return;
    const timer = window.setTimeout(() => beginListeningRef.current(), 120);
    return () => window.clearTimeout(timer);
  }, [open]);

  const stopEverything = useCallback(() => {
    openRef.current = false;
    clearRestartTimer();
    lifecycleRef.current += 1;
    abortSpeech();
    stopSpeaking();
    submittingRef.current = false;
    finalReceivedRef.current = false;
    setFinalResult(null);
    setPhase("idle");
  }, [abortSpeech, clearRestartTimer, stopSpeaking]);

  useEffect(() => () => stopEverything(), [stopEverything]);

  const changeOpen = (next: boolean) => {
    if (!next) stopEverything();
    onOpenChange(next);
  };

  const handleOrb = () => {
    if (phase === "speaking") {
      stopSpeaking();
      beginListening();
      return;
    }
    if (phase === "listening") {
      stopSpeech();
      if (transcript.trim()) setPhase("review");
      else setPhase("idle");
      return;
    }
    if (phase !== "thinking") beginListening();
  };

  const requiresReview = confidence == null || confidence < confidenceThreshold;
  const phaseIcon =
    phase === "thinking" ? (
      <Loader2 className="size-8 animate-spin" />
    ) : phase === "speaking" ? (
      <Volume2 className="size-8" />
    ) : phase === "listening" ? (
      <Square className="size-7" />
    ) : (
      <Mic className="size-8" />
    );

  return (
    <Dialog open={open} onOpenChange={changeOpen}>
      <DialogContent hideClose className="w-[calc(100vw-2rem)] max-w-xl overflow-hidden p-0">
        <div className="relative bg-gradient-to-b from-primary/10 via-surface to-surface px-6 pb-6 pt-5">
          <DialogHeader className="text-center">
            <DialogTitle className="flex items-center justify-center gap-2 text-18">
              <AudioLines className="size-5 text-primary" /> Voice mode
            </DialogTitle>
            <DialogDescription>
              {providerLabel} · grounded answers via {plannerLabel}
            </DialogDescription>
          </DialogHeader>

          <div className="mt-7 flex flex-col items-center">
            <button
              type="button"
              onClick={handleOrb}
              disabled={phase === "thinking"}
              aria-label={phase === "speaking" ? "Interrupt response" : phase === "listening" ? "Stop listening" : "Start listening"}
              className={cn(
                "relative grid size-28 place-items-center rounded-full text-white shadow-pop transition-transform focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-4 focus-visible:ring-offset-surface disabled:cursor-wait",
                phase === "error" ? "bg-severity-high" : "bg-primary",
                phase !== "thinking" && "hover:scale-[1.03] active:scale-95",
              )}
            >
              {phase === "listening" && (
                <>
                  <span className="absolute inset-0 animate-ping rounded-full bg-primary/20" />
                  <span className="absolute -inset-3 animate-pulse rounded-full border border-primary/25" />
                </>
              )}
              <span className="relative">{phaseIcon}</span>
            </button>
            <div className="mt-4 text-15 font-semibold text-content" aria-live="polite">
              {STATUS[phase]}
            </div>
            <div className="mt-1 min-h-5 text-12 text-content-dim">
              {language === "kn" ? "ಕನ್ನಡ" : "English (India)"}
              {confidence != null ? ` · ${Math.round(confidence * 100)}% heard` : ""}
            </div>
          </div>

          {(transcript || assistantText || errorMessage) && (
            <div className="mt-6 space-y-3 rounded-card border border-hairline bg-surface/90 p-4">
              {transcript && (
                <div>
                  <div className="mb-1 text-11 font-semibold uppercase tracking-wide text-content-dim">You</div>
                  <p lang={language} className="text-14 text-content">{transcript}</p>
                </div>
              )}
              {assistantText && (
                <div className="border-t border-hairline pt-3">
                  <div className="mb-1 text-11 font-semibold uppercase tracking-wide text-primary">DRISHTI</div>
                  <p lang={language} className="text-14 text-content">{assistantText}</p>
                </div>
              )}
              {errorMessage && (
                <div className="flex gap-2 text-13 text-severity-high">
                  <AlertTriangle className="mt-0.5 size-4 shrink-0" />
                  <span>{errorMessage}</span>
                </div>
              )}
            </div>
          )}

          {phase === "review" && transcript && (
            <div className="mt-4 rounded-card bg-severity-high/10 p-3">
              <div className="flex items-start gap-2 text-12 text-severity-high">
                <AlertTriangle className="mt-0.5 size-4 shrink-0" />
                <span>
                  {requiresReview
                    ? "Confidence was low or unavailable. Confirm the transcript before DRISHTI runs it."
                    : "Review the transcript before sending."}
                </span>
              </div>
              <div className="mt-3 flex justify-end gap-2">
                <Button variant="ghost" size="sm" onClick={beginListening}>
                  <RotateCcw /> Try again
                </Button>
                <Button size="sm" onClick={() => void submitTurn(transcript, confidence, true)}>
                  <SendHorizonal /> Confirm & send
                </Button>
              </div>
            </div>
          )}

          <div className="mt-5 flex items-center justify-between gap-3 border-t border-hairline pt-4">
            <p className="max-w-sm text-11 leading-relaxed text-content-dim">
              Browser speech handles audio; finalized text is sent to DRISHTI. Raw audio is not stored.
            </p>
            <Button variant="outline" size="sm" onClick={() => changeOpen(false)}>
              End
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
