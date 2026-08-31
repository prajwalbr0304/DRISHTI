import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, AudioLines, Loader2, Mic, Pause, Play, Send, Volume2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { SimpleTooltip } from "@/components/ui/tooltip";
import { AnswerCard } from "@/components/ask/AnswerCard";
import { cn } from "@/lib/utils";
import { VOICE_LOW_CONFIDENCE, useAskStore, type AskLang } from "@/stores/useAskStore";
import { useVoiceSettings } from "@/stores/useVoiceSettings";
import { useSpeech, type SpeechFinalResult } from "@/components/ask/useSpeech";
import { useTts, voicesForLanguage } from "@/components/ask/useTts";
import { SonicVoiceDialog } from "./SonicVoiceDialog";

type VoicePhase = "idle" | "listening" | "thinking" | "speaking" | "error";
const STATUS: Record<VoicePhase, string> = {
  idle: "Ready when you are",
  listening: "Listening…",
  thinking: "Checking DRISHTI…",
  speaking: "Speaking",
  error: "Voice mode paused",
};

export function VoiceModeDialog(props: Parameters<typeof BrowserVoiceModeDialog>[0] & { sonicAvailable?: boolean }) {
  const [browserFallback, setBrowserFallback] = useState(false);
  useEffect(() => { if (!props.open) setBrowserFallback(false); }, [props.open]);
  if (props.sonicAvailable && props.language === "en" && !browserFallback) {
    return <SonicVoiceDialog open={props.open} onOpenChange={props.onOpenChange} onBrowserVoice={() => setBrowserFallback(true)} />;
  }
  return <BrowserVoiceModeDialog {...props} providerLabel="Browser speech" />;
}

function BrowserVoiceModeDialog({
  open, onOpenChange, language, providerLabel, plannerLabel, unscoredAutoSendAvailable = false,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  language: AskLang;
  providerLabel: string;
  plannerLabel: string;
  unscoredAutoSendAvailable?: boolean;
}) {
  const send = useAskStore((s) => s.send);
  const busy = useAskStore((s) => s.busy);
  const messages = useAskStore((s) => s.messages);
  const { supported: ttsSupported, voices, speak: speakText, stop: stopSpeaking } = useTts();
  const settings = useVoiceSettings();
  const availableVoices = voicesForLanguage(voices, language);
  const [phase, setPhaseState] = useState<VoicePhase>("idle");
  const [transcript, setTranscript] = useState("");
  const [confidence, setConfidence] = useState<number | null>(null);
  const [reviewPending, setReviewPending] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [continuous, setContinuous] = useState(true);
  const [autoSend, setAutoSend] = useState(false);
  const [finalResult, setFinalResult] = useState<SpeechFinalResult | null>(null);
  const [speakingId, setSpeakingId] = useState<string | null>(null);
  const openRef = useRef(open);
  const phaseRef = useRef<VoicePhase>("idle");
  const continuousRef = useRef(continuous);
  const finalReceivedRef = useRef(false);
  const submittingRef = useRef(false);
  const lifecycleRef = useRef(0);
  const timerRef = useRef<number | null>(null);
  const beginRef = useRef<() => void>(() => undefined);
  const answersRef = useRef<HTMLElement>(null);
  const setPhase = useCallback((next: VoicePhase) => {
    phaseRef.current = next;
    setPhaseState(next);
  }, []);
  const clearTimer = useCallback(() => {
    if (timerRef.current != null) window.clearTimeout(timerRef.current);
    timerRef.current = null;
  }, []);
  const scheduleNext = useCallback(() => {
    clearTimer();
    if (!openRef.current || !continuousRef.current) return;
    timerRef.current = window.setTimeout(() => beginRef.current(), 650);
  }, [clearTimer]);

  const { start: startSpeech, abort: abortSpeech } = useSpeech({
    lang: language,
    onTranscript: setTranscript,
    onFinal: (result) => {
      if (!openRef.current || phaseRef.current !== "listening") return;
      finalReceivedRef.current = true;
      setFinalResult(result);
    },
    onError: (code) => {
      if (!openRef.current || phaseRef.current !== "listening") return;
      if (code === "no-speech") {
        setPhase("idle");
        scheduleNext();
        return;
      }
      clearTimer();
      setErrorMessage(code === "not-allowed" || code === "service-not-allowed"
        ? "Microphone access was denied. Allow it in your browser, or use text chat."
        : "Speech recognition stopped. Retry the microphone or use text chat.");
      setPhase("error");
    },
    onEnd: () => {
      if (openRef.current && phaseRef.current === "listening" && !finalReceivedRef.current) {
        setPhase("idle");
        scheduleNext();
      }
    },
  });

  const beginListening = useCallback(() => {
    if (!openRef.current || busy || submittingRef.current) return;
    clearTimer();
    stopSpeaking();
    setSpeakingId(null);
    finalReceivedRef.current = false;
    setFinalResult(null);
    setReviewPending(false);
    setTranscript("");
    setConfidence(null);
    setErrorMessage(null);
    setPhase("listening");
    if (!startSpeech()) {
      setErrorMessage("Browser speech recognition is unavailable. Use text chat instead.");
      setPhase("error");
    }
  }, [busy, clearTimer, startSpeech, stopSpeaking, setPhase]);
  useEffect(() => { beginRef.current = beginListening; }, [beginListening]);

  const playAnswer = useCallback((text: string, lang: string, id: string | null = null) => {
    clearTimer();
    abortSpeech();
    setSpeakingId(id);
    const lifecycle = lifecycleRef.current;
    if (!ttsSupported) { setPhase("idle"); scheduleNext(); return; }
    setPhase("speaking");
    speakText(text, lang, { onEnd: () => {
      if (!openRef.current || lifecycle !== lifecycleRef.current) return;
      setSpeakingId(null);
      setPhase("idle");
      scheduleNext();
    } });
  }, [clearTimer, abortSpeech, ttsSupported, speakText, setPhase, scheduleNext]);

  const submitTurn = useCallback(async (text: string, score: number | null, confirmed = false) => {
    if (!text.trim() || submittingRef.current || busy) return;
    submittingRef.current = true;
    const lifecycle = lifecycleRef.current;
    clearTimer();
    abortSpeech();
    setReviewPending(false);
    setConfidence(score);
    setErrorMessage(null);
    setPhase("thinking");
    try {
      const response = await send(text.trim(), {
        spoken: true, voiceMode: true, voiceConfidence: score ?? undefined,
        voiceLanguage: language, voiceConfirmed: confirmed || undefined,
        voiceAutoSend: (score == null && autoSend && unscoredAutoSendAvailable) || undefined,
      });
      if (!openRef.current || lifecycle !== lifecycleRef.current) return;
      if (!response) {
        setErrorMessage("DRISHTI couldn't complete that turn. Retry or review the answer panel.");
        setPhase("error");
        return;
      }
      playAnswer(response.reply, response.language);
    } catch {
      if (openRef.current && lifecycle === lifecycleRef.current) {
        setErrorMessage("DRISHTI couldn't complete that turn. Please retry.");
        setPhase("error");
      }
    } finally { submittingRef.current = false; }
  }, [autoSend, busy, clearTimer, language, playAnswer, send, setPhase, abortSpeech, unscoredAutoSendAvailable]);

  useEffect(() => {
    if (!open || !finalResult || phaseRef.current !== "listening") return;
    setTranscript(finalResult.text);
    setConfidence(finalResult.confidence);
    setFinalResult(null);
    const mustReview = finalResult.confidence == null ? !(autoSend && unscoredAutoSendAvailable) : finalResult.confidence < VOICE_LOW_CONFIDENCE;
    if (mustReview) {
      abortSpeech();
      setReviewPending(true);
      setErrorMessage(finalResult.confidence == null
        ? "Recognition confidence is unavailable. Review this transcript or enable hands-free sending."
        : `Low-confidence transcription (${Math.round(finalResult.confidence * 100)}%). Review before sending.`);
      setPhase("idle");
    } else { void submitTurn(finalResult.text, finalResult.confidence); }
  }, [autoSend, finalResult, open, setPhase, abortSpeech, submitTurn, unscoredAutoSendAvailable]);

  const stopEverything = useCallback(() => {
    openRef.current = false;
    clearTimer();
    lifecycleRef.current += 1;
    abortSpeech();
    stopSpeaking();
    setSpeakingId(null);
    setFinalResult(null);
    setPhase("idle");
  }, [clearTimer, abortSpeech, stopSpeaking, setPhase]);
  useEffect(() => {
    openRef.current = open;
    if (!open) { stopEverything(); return; }
    setAutoSend(false);
    setReviewPending(false);
    timerRef.current = window.setTimeout(() => beginRef.current(), 120);
    return stopEverything;
  }, [open, stopEverything]);
  useEffect(() => {
    continuousRef.current = continuous;
    if (!continuous) clearTimer();
  }, [continuous, clearTimer]);
  useEffect(() => {
    const panel = answersRef.current;
    if (panel) panel.scrollTop = panel.scrollHeight;
  }, [messages]);

  const pause = () => {
    clearTimer();
    lifecycleRef.current += 1;
    abortSpeech();
    stopSpeaking();
    setSpeakingId(null);
    setFinalResult(null);
    setPhase("idle");
  };
  const close = () => { stopEverything(); onOpenChange(false); };
  const preview = () => {
    pause();
    playAnswer(language === "kn" ? "ನಮಸ್ಕಾರ. ನಾನು ದೃಷ್ಟಿ. ನಿಮ್ಮ ಪ್ರಶ್ನೆಗೆ ಉತ್ತರಿಸಲು ಸಿದ್ಧವಾಗಿದ್ದೇನೆ."
      : "Hello, I'm DRISHTI. What would you like to know about your dashboard?", language);
  };
  const micAction = phase === "listening" ? pause : beginListening;
  const selectedVoice = settings.voices[language] ?? "";

  return (
    <Dialog open={open} onOpenChange={(next) => { if (!next) close(); }}>
      <DialogContent hideClose className="flex h-[min(850px,calc(100dvh-2rem))] w-[calc(100vw-2rem)] max-w-6xl flex-col gap-0 overflow-hidden p-0">
        <header className="flex shrink-0 items-center justify-between gap-3 border-b border-hairline px-5 py-4">
          <div className="min-w-0">
            <DialogTitle className="flex items-center gap-2"><AudioLines className="size-5 text-primary" />Voice mode</DialogTitle>
            <DialogDescription className="break-words text-12">{providerLabel} · {plannerLabel}</DialogDescription>
          </div>
          <SimpleTooltip label="End conversation"><Button variant="ghost" size="icon" aria-label="End conversation" onClick={close}><X className="size-5" /></Button></SimpleTooltip>
        </header>
        <div className="grid min-h-0 flex-1 grid-cols-1 overflow-y-auto md:grid-cols-[minmax(280px,340px)_minmax(0,1fr)] md:overflow-hidden">
          <section aria-label="Voice controls" className="min-w-0 space-y-5 border-b border-hairline p-5 md:overflow-y-auto md:border-b-0 md:border-r">
            <div className="flex flex-col items-center gap-3 py-2">
              <button type="button" disabled={phase === "thinking"} onClick={phase === "speaking" ? beginListening : micAction}
                aria-label={phase === "speaking" ? "Interrupt response" : phase === "listening" ? "Pause listening" : "Start listening"}
                className={cn("grid size-24 shrink-0 place-items-center rounded-full bg-primary text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-primary disabled:opacity-60", phase === "listening" && "ring-4 ring-primary/20")}>
                {phase === "thinking" ? <Loader2 className="size-8 animate-spin" /> : phase === "speaking" ? <Volume2 className="size-8" /> : phase === "listening" ? <Pause className="size-8" /> : <Mic className="size-8" />}
              </button>
              <p role="status" className="text-15 font-semibold">{STATUS[phase]}</p>
              <span className="text-12 text-content-dim">{language === "kn" ? "ಕನ್ನಡ" : "English (India)"}</span>
            </div>
            <div className="space-y-3 border-y border-hairline py-4 text-13">
              <label className="flex items-center justify-between gap-3">Continuous conversation<input type="checkbox" checked={continuous} onChange={(e) => setContinuous(e.target.checked)} /></label>
              <label className="flex items-center justify-between gap-3" title={unscoredAutoSendAvailable ? undefined : "Backend update required"}>Hands-free sending (unscored speech)<input type="checkbox" disabled={!unscoredAutoSendAvailable} checked={autoSend} onChange={(e) => setAutoSend(e.target.checked)} /></label>
            </div>
            <div className="space-y-3">
              <label className="block text-13">Voice
                <select aria-label="Speaking voice" value={availableVoices.some((v) => v.voiceURI === selectedVoice) ? selectedVoice : ""}
                  disabled={!ttsSupported} onChange={(e) => settings.setVoice(language, e.target.value)}
                  className="mt-1 block w-full min-w-0 rounded-md border border-hairline bg-surface px-2 py-2 text-12">
                  <option value="">Automatic{availableVoices[0] ? ` · ${availableVoices[0].name}` : " · browser default"}</option>
                  {availableVoices.map((v) => <option key={v.voiceURI} value={v.voiceURI}>{v.name} · {v.lang}</option>)}
                </select>
              </label>
              {!availableVoices.length && <p className="text-12 text-content-dim">No selectable {language === "kn" ? "Kannada" : "English"} voices available on this device.</p>}
              <label className="block text-13">Speaking speed <span className="float-right tabular-nums">{settings.rate.toFixed(2)}×</span>
                <input aria-label="Speaking speed" type="range" min="0.75" max="1.25" step="0.05" value={settings.rate}
                  onChange={(e) => settings.setRate(Number(e.target.value))} className="mt-2 w-full" />
              </label>
              <Button variant="outline" size="sm" disabled={!ttsSupported || phase === "thinking"} onClick={preview}><Play className="mr-2 size-4" />Preview voice</Button>
            </div>
            {(transcript || errorMessage) && <div className="space-y-3">
              <label className="block text-12 font-semibold">Your transcript
                <textarea aria-label="Your transcript" lang={language} value={transcript} readOnly={!reviewPending}
                  onChange={(e) => setTranscript(e.target.value)} rows={3}
                  className="mt-2 block w-full resize-y rounded-md border border-hairline bg-surface p-2 text-14 font-normal" />
              </label>
              {errorMessage && <p role="alert" className="flex gap-2 text-12 text-severity-high"><AlertTriangle className="mt-0.5 size-4 shrink-0" />{errorMessage}</p>}
              {reviewPending && <div className="flex flex-wrap gap-2">
                <Button variant="outline" size="sm" onClick={beginListening}>Try again</Button>
                <Button size="sm" disabled={!transcript.trim()} onClick={() => void submitTurn(transcript, confidence, true)}><Send className="mr-2 size-4" />Send transcript</Button>
              </div>}
            </div>}
          </section>
          <section ref={answersRef} aria-label="Conversation answers" className="min-h-[280px] min-w-0 bg-surface-2/40 md:overflow-y-auto">
            <h2 className="sticky top-0 z-10 border-b border-hairline bg-surface px-5 py-3 text-14 font-semibold">Conversation</h2>
            <div className="space-y-5 p-4 sm:p-5 [&_pre]:max-w-full [&_pre]:overflow-x-auto [&_p]:break-words">
              {!messages.length && <p className="py-12 text-center text-14 text-content-dim">No answers yet</p>}
              {messages.map((message) => message.sender === "user"
                ? <p key={message.id} lang={message.language} className="ml-8 whitespace-pre-wrap text-right text-14">{message.text}</p>
                : <AnswerCard key={message.id} message={message} tts={{
                    supported: ttsSupported && phase !== "thinking",
                    isSpeaking: phase === "speaking" && speakingId === message.id,
                    onSpeak: (m) => playAnswer(m.text, m.language ?? language, m.id), onStop: pause,
                  }} />)}
            </div>
          </section>
        </div>
      </DialogContent>
    </Dialog>
  );
}
