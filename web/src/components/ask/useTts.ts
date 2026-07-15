import { useCallback, useEffect, useState } from "react";
import { speechLocale } from "@/components/ask/useSpeech";

/* ============================================================================
   Text-to-speech (doc 01 §4.7 — TTS reads answers back in the detected
   language). Thin wrapper over the Web Speech SpeechSynthesis API, feature-
   detected so it degrades to silence where the browser lacks it. The answer
   text is shown immediately by the caller; speech synthesises in parallel.
   ========================================================================== */

function synth(): SpeechSynthesis | null {
  if (typeof window === "undefined") return null;
  return window.speechSynthesis ?? null;
}

export function useTts() {
  const [supported] = useState(
    () => synth() != null && typeof window !== "undefined" && "SpeechSynthesisUtterance" in window,
  );
  const [speaking, setSpeaking] = useState(false);
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);

  // Voice list loads asynchronously in most browsers.
  useEffect(() => {
    const s = synth();
    if (!s) return;
    const load = () => setVoices(s.getVoices());
    load();
    s.addEventListener?.("voiceschanged", load);
    return () => s.removeEventListener?.("voiceschanged", load);
  }, []);

  const stop = useCallback(() => {
    synth()?.cancel();
    setSpeaking(false);
  }, []);

  const speak = useCallback(
    (text: string, lang: string, opts?: { onEnd?: () => void }) => {
      const s = synth();
      if (!s || !text.trim()) return;
      s.cancel(); // never overlap utterances
      const u = new SpeechSynthesisUtterance(text);
      u.lang = speechLocale(lang); // en-IN / kn-IN
      const want = lang === "kn" ? "kn" : "en";
      const match = voices.find((v) => v.lang?.toLowerCase().startsWith(want));
      if (match) u.voice = match;
      u.rate = 1;
      u.onend = () => {
        setSpeaking(false);
        opts?.onEnd?.();
      };
      u.onerror = () => {
        setSpeaking(false);
        opts?.onEnd?.();
      };
      setSpeaking(true);
      s.speak(u);
    },
    [voices],
  );

  // Cancel any speech if the component using this unmounts.
  useEffect(() => () => synth()?.cancel(), []);

  return { supported, speaking, speak, stop };
}
