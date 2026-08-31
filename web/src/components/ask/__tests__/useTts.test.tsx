import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { speechChunks, useTts, voicesForLanguage } from "../useTts";
import { useVoiceSettings } from "@/stores/useVoiceSettings";

function voice(name: string, lang: string, localService = true) {
  return { name, lang, localService, voiceURI: name, default: false } as SpeechSynthesisVoice;
}
const voices = [voice("Local", "en-US"), voice("Natural India", "en-IN", false), voice("Kannada", "kn-IN")];
class Utterance {
  lang = ""; rate = 1; voice: SpeechSynthesisVoice | null = null;
  onend: (() => void) | null = null; onerror: (() => void) | null = null;
  constructor(public text: string) {}
}

describe("speech playback", () => {
  const speak = vi.fn();
  const cancel = vi.fn();
  beforeEach(() => {
    speak.mockClear(); cancel.mockClear();
    vi.stubGlobal("SpeechSynthesisUtterance", Utterance);
    vi.stubGlobal("speechSynthesis", { getVoices: () => voices, speak, cancel,
      addEventListener: vi.fn(), removeEventListener: vi.fn() });
    useVoiceSettings.setState({ voices: {}, rate: 0.95 });
  });
  afterEach(() => vi.unstubAllGlobals());

  it("prefers available natural voices and keeps languages separate", () => {
    expect(voicesForLanguage(voices, "en")[0].name).toBe("Natural India");
    expect(voicesForLanguage(voices, "kn").map((v) => v.name)).toEqual(["Kannada"]);
  });
  it("cleans markdown, preserves numbers, and bounds long utterances", () => {
    const chunks = speechChunks("**Total:** 25.5 cases. [Source](https://example.com) " + "word ".repeat(150));
    expect(chunks[0]).toBe("Total: 25.5 cases.");
    expect(chunks.join(" ")).toContain("Source");
    expect(chunks.every((c) => c.length <= 221)).toBe(true);
  });
  it("uses saved voice and speed and continues only after each utterance", () => {
    useVoiceSettings.getState().setVoice("en", "Local");
    useVoiceSettings.getState().setRate(1.1);
    const { result } = renderHook(() => useTts());
    const done = vi.fn();
    act(() => result.current.speak("First answer. Next answer.", "en", { onEnd: done }));
    expect(speak.mock.calls[0][0]).toMatchObject({ voice: voices[0], rate: 1.1 });
    expect(speak).toHaveBeenCalledTimes(1);
    act(() => speak.mock.calls[0][0].onend());
    expect(speak).toHaveBeenCalledTimes(2);
    act(() => speak.mock.calls[1][0].onend());
    expect(done).toHaveBeenCalledTimes(1);
  });
  it("does not resume a cancelled answer or fire its completion callback", () => {
    const { result } = renderHook(() => useTts());
    const done = vi.fn();
    act(() => result.current.speak("First. Second.", "en", { onEnd: done }));
    act(() => result.current.stop());
    act(() => speak.mock.calls[0][0].onend());
    act(() => speak.mock.calls[0][0].onerror());
    expect(speak).toHaveBeenCalledTimes(1);
    expect(done).not.toHaveBeenCalled();
  });
  it("unmounting an idle hook does not cancel another hook's playback", () => {
    const first = renderHook(() => useTts());
    const idle = renderHook(() => useTts());
    act(() => first.result.current.speak("Current answer.", "en"));
    cancel.mockClear();
    idle.unmount();
    expect(cancel).not.toHaveBeenCalled();
  });
  it("a replaced speaker cannot cancel or resume over the new speaker", () => {
    const first = renderHook(() => useTts());
    const second = renderHook(() => useTts());
    const oldDone = vi.fn();
    act(() => first.result.current.speak("Old. More old.", "en", { onEnd: oldDone }));
    const oldUtterance = speak.mock.calls[0][0];
    act(() => second.result.current.speak("New answer.", "en"));
    cancel.mockClear();
    act(() => oldUtterance.onend());
    first.unmount();
    expect(cancel).not.toHaveBeenCalled();
    expect(speak).toHaveBeenCalledTimes(2);
    expect(oldDone).not.toHaveBeenCalled();
  });
});
