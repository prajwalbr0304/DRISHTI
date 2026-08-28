import { useCallback, useEffect, useRef, useState } from "react";

interface RecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((e: SpeechResultEventLike) => void) | null;
  onerror: ((e: SpeechErrorEventLike) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
}
interface SpeechAltLike {
  transcript: string;
  confidence?: number;
}
interface SpeechResultItemLike {
  0: SpeechAltLike;
  isFinal: boolean;
  length: number;
}
interface SpeechResultEventLike {
  results: ArrayLike<SpeechResultItemLike>;
}
interface SpeechErrorEventLike {
  error?: string;
}

export interface SpeechFinalResult {
  text: string;
  /** Null means the browser did not provide a trustworthy final confidence. */
  confidence: number | null;
}

function recognitionCtor(): (new () => RecognitionLike) | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as {
    SpeechRecognition?: new () => RecognitionLike;
    webkitSpeechRecognition?: new () => RecognitionLike;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

/** Map the app language toggle to a BCP-47 locale for the recognizer. */
export function speechLocale(lang: string): string {
  return lang === "kn" ? "kn-IN" : "en-IN";
}

export function useSpeech({
  lang,
  onTranscript,
  onFinal,
  onError,
  onEnd,
}: {
  lang: string;
  onTranscript: (cumulativeText: string) => void;
  onFinal?: (result: SpeechFinalResult) => void;
  onError?: (code: string) => void;
  onEnd?: () => void;
}) {
  const [supported] = useState(() => recognitionCtor() != null);
  const [listening, setListening] = useState(false);
  const [confidence, setConfidence] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const recRef = useRef<RecognitionLike | null>(null);
  const callbacksRef = useRef({ onTranscript, onFinal, onError, onEnd });

  useEffect(() => {
    callbacksRef.current = { onTranscript, onFinal, onError, onEnd };
  }, [onEnd, onError, onFinal, onTranscript]);

  const abort = useCallback(() => {
    const rec = recRef.current;
    recRef.current = null;
    try {
      rec?.abort();
    } catch {
      // Recognition may already have ended.
    }
    setListening(false);
  }, []);

  const stop = useCallback(() => {
    try {
      recRef.current?.stop();
    } catch {
      // Recognition may already have ended.
    }
    setListening(false);
  }, []);

  const start = useCallback((): boolean => {
    const Ctor = recognitionCtor();
    if (!Ctor) return false;

    try {
      recRef.current?.abort();
    } catch {
      // Ignore an already-closed previous recognizer.
    }

    const rec = new Ctor();
    let finalDelivered = false;
    rec.lang = speechLocale(lang);
    rec.continuous = false;
    rec.interimResults = true;
    setConfidence(null);
    setError(null);

    rec.onresult = (event) => {
      let full = "";
      let finalConfidence: number | null = null;
      let lastResultFinal = false;

      for (let i = 0; i < event.results.length; i++) {
        const result = event.results[i];
        full += result[0]?.transcript ?? "";
        lastResultFinal = result.isFinal;
        const reported = result[0]?.confidence;
        if (result.isFinal && typeof reported === "number" && reported > 0) {
          finalConfidence = reported;
        }
      }

      const text = full.trim();
      callbacksRef.current.onTranscript(text);
      if (finalConfidence != null) setConfidence(finalConfidence);
      if (lastResultFinal && text && !finalDelivered) {
        finalDelivered = true;
        callbacksRef.current.onFinal?.({ text, confidence: finalConfidence });
      }
    };

    rec.onerror = (event) => {
      const code = event.error || "speech-recognition-error";
      setError(code);
      setListening(false);
      callbacksRef.current.onError?.(code);
    };
    rec.onend = () => {
      if (recRef.current === rec) recRef.current = null;
      setListening(false);
      callbacksRef.current.onEnd?.();
    };
    recRef.current = rec;

    try {
      rec.start();
      setListening(true);
      return true;
    } catch {
      recRef.current = null;
      setError("speech-recognition-start-failed");
      setListening(false);
      callbacksRef.current.onError?.("speech-recognition-start-failed");
      return false;
    }
  }, [lang]);

  useEffect(() => abort, [abort]);

  return {
    supported,
    listening,
    confidence,
    error,
    start,
    stop,
    abort,
    toggle: () => (listening ? stop() : start()),
  };
}
