import { useCallback, useEffect, useRef, useState } from "react";
import { speechLocale } from "@/components/ask/useSpeech";
import { useVoiceSettings } from "@/stores/useVoiceSettings";

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

// Chat and the voice dialog share the browser's single speech queue.
let activeOwner: symbol | null = null;

export function useTts() {
  const generation = useRef(0);
  const owner = useRef(Symbol("speech-owner"));
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
    generation.current += 1;
    if (activeOwner === owner.current) {
      activeOwner = null;
      synth()?.cancel();
    }
    setSpeaking(false);
  }, []);

  const speak = useCallback(
    (text: string, lang: string, opts?: { onEnd?: () => void }) => {
      const s = synth();
      const chunks = speechChunks(text);
      if (!s || !chunks.length) { opts?.onEnd?.(); return; }
      const current = ++generation.current;
      activeOwner = owner.current;
      s.cancel(); // never overlap utterances
      const settings = useVoiceSettings.getState();
      const available = voicesForLanguage(voices, lang);
      const match = available.find((v) => v.voiceURI === settings.voices[lang]) ?? available[0];
      const finish = () => {
        if (generation.current !== current || activeOwner !== owner.current) return;
        activeOwner = null;
        setSpeaking(false);
        opts?.onEnd?.();
      };
      const play = (index: number) => {
        if (generation.current !== current || activeOwner !== owner.current) return;
        if (index === chunks.length) { finish(); return; }
        const u = new SpeechSynthesisUtterance(chunks[index]);
        u.lang = match?.lang ?? speechLocale(lang);
        if (match) u.voice = match;
        u.rate = settings.rate;
        u.onend = () => play(index + 1);
        u.onerror = finish;
        try { s.speak(u); } catch { finish(); }
      };
      setSpeaking(true);
      play(0);
    },
    [voices],
  );

  // Cancel any speech if the component using this unmounts.
  useEffect(() => stop, [stop]);

  return { supported, speaking, speak, stop, voices };
}

export function voicesForLanguage(voices: SpeechSynthesisVoice[], language: string) {
  const locale = speechLocale(language).toLowerCase();
  const score = (v: SpeechSynthesisVoice) =>
    (/natural|neural|online/i.test(v.name) ? 8 : 0) +
    (!v.localService ? 4 : 0) + (v.lang.toLowerCase() === locale ? 2 : 0) + (v.default ? 1 : 0);
  return voices.filter((v) => v.lang.toLowerCase().split(/[-_]/)[0] === language)
    .sort((a, b) => score(b) - score(a) || a.name.localeCompare(b.name));
}

export function speechChunks(text: string): string[] {
  const clean = text.replace(/```[\s\S]*?```/g, " ")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/[*#`]/g, "").replace(/\s+/g, " ").trim();
  // Short sentence-sized utterances avoid long-answer stalls in browser TTS.
  return clean.split(/(?<=[.!?\u0964])\s+/u)
    .flatMap((sentence) => sentence.trim().match(/.{1,220}(?:\s|$)|\S{1,220}/gu) ?? [])
    .map((chunk) => chunk.trim()).filter(Boolean);
}
