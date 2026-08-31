import { create } from "zustand";
import { persist } from "zustand/middleware";

export const useVoiceSettings = create(persist<{
  voices: Record<string, string>;
  rate: number;
  setVoice: (language: string, uri: string) => void;
  setRate: (rate: number) => void;
}>((set) => ({
  voices: {},
  rate: 0.95,
  setVoice: (language, uri) => set((s) => ({ voices: { ...s.voices, [language]: uri } })),
  setRate: (rate) => set({ rate: Math.min(1.25, Math.max(0.75, rate)) }),
}), { name: "drishti-voice-settings" }));
