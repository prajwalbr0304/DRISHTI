import { useCallback, useEffect, useRef, useState } from "react";
import { chatApi } from "@/api/endpoints/chat";
import type { AskResponse } from "@/api/types";
import { useAskStore } from "@/stores/useAskStore";

export const SONIC_VOICES = {
  kiara: "Kiara (India)", arjun: "Arjun (India)", tiffany: "Tiffany (US)",
  matthew: "Matthew (US)", amy: "Amy (UK)", olivia: "Olivia (Australia)",
};
type Phase = "idle" | "connecting" | "listening" | "speaking" | "error";
type Event = { type: string; audio?: string; role?: string; text?: string;
  message?: string; question?: string; answer?: AskResponse; data?: string; last?: boolean };

export function useSonic() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState("");
  const [transcript, setTranscript] = useState("");
  const [spokenReply, setSpokenReply] = useState("");
  const generation = useRef(0);
  const cleanup = useRef<() => void>(() => undefined);
  const restart = useRef<(voice: string) => void>(() => undefined);
  const stop = useCallback(() => {
    generation.current += 1;
    cleanup.current();
    cleanup.current = () => undefined;
    setPhase("idle");
  }, []);

  const start = useCallback(async (voice: string) => {
    stop();
    const current = generation.current;
    const active = () => generation.current === current;
    setPhase("connecting");
    setError("");
    let media: MediaStream | undefined;
    let context: AudioContext | undefined;
    let capture: AudioWorkletNode | undefined;
    let socket: WebSocket | undefined;
    let source: MediaStreamAudioSourceNode | undefined;
    let ready = false;
    let fragments = "";
    let renew = false;
    let nextPlayback = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const playing = new Set<AudioBufferSourceNode>();
    const clearAudio = () => {
      for (const node of playing) { try { node.stop(); } catch { /* already ended */ } }
      playing.clear();
      nextPlayback = 0;
      clearTimeout(timer);
    };
    const dispose = () => {
      ready = false;
      clearAudio();
      if (capture) { capture.port.onmessage = null; capture.disconnect(); }
      source?.disconnect();
      media?.getTracks().forEach((track) => track.stop());
      if (socket) { socket.onclose = null; socket.close(); }
      if (context && context.state !== "closed") void context.close();
    };
    cleanup.current = dispose;
    const fail = (message: string) => {
      if (!active()) return;
      generation.current += 1;
      dispose();
      setError(message);
      setPhase("error");
    };
    try {
      context = new AudioContext({ sampleRate: 16000 });
      await context.resume();
      media = await navigator.mediaDevices.getUserMedia({ audio: {
        channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true,
      } });
      if (!active()) { dispose(); return; }
      if (context.sampleRate !== 16000) throw new Error("Unsupported audio sample rate");
      await context.audioWorklet.addModule(`${import.meta.env.BASE_URL}audio/sonic-capture.js`);
      if (!active()) { dispose(); return; }
      const session = await chatApi.voiceSession({ voice, language: "en", audio_consent: true,
        session_id: useAskStore.getState().sourceSessionId ?? undefined });
      if (!active()) { dispose(); return; }
      socket = new WebSocket(session.url);
      const connectedSocket = socket;
      const audioContext = context;
      capture = new AudioWorkletNode(context, "sonic-capture");
      source = context.createMediaStreamSource(media);
      source.connect(capture);
      capture.connect(context.destination); // Worklet emits silence, not microphone feedback.
      capture.port.onmessage = (event: MessageEvent<ArrayBuffer>) => {
        if (!active() || !ready || connectedSocket.readyState !== WebSocket.OPEN) return;
        if (connectedSocket.bufferedAmount > 64000) {
          fail("The voice connection is too slow. Reconnect or use browser voice.");
          return;
        }
        connectedSocket.send(event.data);
      };
      const connectionTimeout = window.setTimeout(() => fail("Nova voice connection timed out. Use browser voice or reconnect."), 60000);
      const previousDispose = cleanup.current;
      cleanup.current = () => { window.clearTimeout(connectionTimeout); previousDispose(); };
      socket.onopen = () => {
        if (active()) connectedSocket.send(JSON.stringify({ ticket: session.ticket }));
      };
      socket.onerror = () => fail("Cannot reach Nova voice. Use browser voice or reconnect.");
      socket.onmessage = (message) => {
        if (!active()) return;
        let event: Event;
        try { event = JSON.parse(message.data as string) as Event; } catch { fail("Invalid voice response."); return; }
        if (event.type === "chunk") {
          fragments += event.data ?? "";
          if (fragments.length > 2000000) { fail("Voice response is too large."); return; }
          if (!event.last) return;
          try { event = JSON.parse(fragments) as Event; } catch { fail("Invalid voice response."); return; }
          fragments = "";
        }
        if (event.type === "ready") {
          window.clearTimeout(connectionTimeout);
          ready = true;
          setPhase("listening");
        } else if (event.type === "audio" && event.audio) {
          const binary = atob(event.audio);
          const buffer = audioContext.createBuffer(1, binary.length / 2, 24000);
          const samples = buffer.getChannelData(0);
          for (let i = 0; i < samples.length; i++) {
            const value = binary.charCodeAt(i * 2) | (binary.charCodeAt(i * 2 + 1) << 8);
            samples[i] = (value >= 32768 ? value - 65536 : value) / 32768;
          }
          if (nextPlayback - audioContext.currentTime > 15) { fail("Audio playback fell behind. Please reconnect."); return; }
          const node = audioContext.createBufferSource();
          node.buffer = buffer;
          node.connect(audioContext.destination);
          nextPlayback = Math.max(nextPlayback, audioContext.currentTime + 0.02);
          node.start(nextPlayback);
          nextPlayback += buffer.duration;
          playing.add(node);
          node.onended = () => { playing.delete(node); node.disconnect(); };
          setPhase("speaking");
          clearTimeout(timer);
          timer = setTimeout(() => { if (active()) setPhase("listening"); }, Math.max(0, nextPlayback - audioContext.currentTime) * 1000 + 100);
        } else if (event.type === "interrupted") {
          clearAudio();
          setPhase("listening");
        } else if (event.type === "transcript") {
          if (event.role === "USER") setTranscript(event.text ?? "");
          else setSpokenReply(event.text ?? "");
        } else if (event.type === "answer" && event.answer && event.question) {
          useAskStore.getState().appendVoiceAnswer(event.question, event.answer);
        } else if (event.type === "session_end") {
          renew = true;
        } else if (event.type === "error") {
          fail(event.message ?? "Nova voice failed.");
        } else if (event.type === "tool_error") {
          setError(event.message ?? "The grounded query failed. Please try again.");
        }
      };
      socket.onclose = () => {
        if (!active()) return;
        if (renew) restart.current(voice);
        else fail("Voice connection closed. Reconnect to continue your conversation.");
      };
    } catch {
      if (!active()) { dispose(); return; }
      fail("Could not start Nova voice. Check microphone permission and the service connection, or use browser voice.");
    }
  }, [stop]);
  useEffect(() => { restart.current = (voice) => { void start(voice); }; }, [start]);
  useEffect(() => stop, [stop]);
  return { phase, error, transcript, spokenReply, start, stop };
}
