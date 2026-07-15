import { useCallback, useEffect, useRef, useState } from "react";

/* ============================================================================
   Thin wrapper over the Web Speech API (doc 01 §4.7 voice; §9 graceful
   degradation). Feature-detected — when the browser lacks SpeechRecognition the
   composer simply falls back to text. Emits the cumulative transcript for the
   current utterance so the composer can append it to whatever was typed.
   ========================================================================== */

interface RecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((e: SpeechResultEventLike) => void) | null;
  onerror: (() => void) | null;
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

function recognitionCtor(): (new () => RecognitionLike) | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as {
    SpeechRecognition?: new () => RecognitionLike;
    webkitSpeechRecognition?: new () => RecognitionLike;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

/** Map the app language toggle to a BCP-47 locale for the recogniser. */
export function speechLocale(lang: string): string {
  return lang === "kn" ? "kn-IN" : "en-IN";
}

export function useSpeech({
  lang,
  onTranscript,
}: {
  lang: string;
  onTranscript: (cumulativeText: string) => void;
}) {
  const [supported] = useState(() => recognitionCtor() != null);
  const [listening, setListening] = useState(false);
  /** confidence of the last FINAL recognition result (null until one arrives). */
  const [confidence, setConfidence] = useState<number | null>(null);
  const recRef = useRef<RecognitionLike | null>(null);
  const cbRef = useRef(onTranscript);
  useEffect(() => {
    cbRef.current = onTranscript;
  }, [onTranscript]);

  const stop = useCallback(() => {
    try {
      recRef.current?.stop();
    } catch {
      /* no-op */
    }
    setListening(false);
  }, []);

  const start = useCallback(() => {
    const Ctor = recognitionCtor();
    if (!Ctor) return;
    try {
      recRef.current?.abort();
    } catch {
      /* no-op */
    }
    const rec = new Ctor();
    rec.lang = speechLocale(lang);
    rec.continuous = false;
    rec.interimResults = true;
    setConfidence(null);
    rec.onresult = (e) => {
      let full = "";
      let finalConf: number | null = null;
      for (let i = 0; i < e.results.length; i++) {
        const res = e.results[i];
        full += res[0]?.transcript ?? "";
        if (res.isFinal && typeof res[0]?.confidence === "number") finalConf = res[0].confidence;
      }
      cbRef.current(full);
      // Some engines report confidence 0 for interim; only trust final results.
      if (finalConf != null && finalConf > 0) setConfidence(finalConf);
    };
    rec.onerror = () => setListening(false);
    rec.onend = () => setListening(false);
    recRef.current = rec;
    try {
      rec.start();
      setListening(true);
    } catch {
      setListening(false);
    }
  }, [lang]);

  useEffect(
    () => () => {
      try {
        recRef.current?.abort();
      } catch {
        /* no-op */
      }
    },
    [],
  );

  return {
    supported,
    listening,
    confidence,
    start,
    stop,
    toggle: () => (listening ? stop() : start()),
  };
}
