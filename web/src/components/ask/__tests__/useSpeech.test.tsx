import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useSpeech } from "../useSpeech";

class Recognition {
  static instances: Recognition[] = [];
  lang = ""; continuous = false; interimResults = false;
  onresult: ((e: unknown) => void) | null = null;
  onerror: ((e: unknown) => void) | null = null;
  onend: (() => void) | null = null;
  start = vi.fn(); stop = vi.fn();
  abort = vi.fn(() => this.onend?.());
  constructor() { Recognition.instances.push(this); }
}

describe("recognition lifecycle", () => {
  afterEach(() => vi.unstubAllGlobals());
  it("ignores late events from replaced or aborted recognizers", () => {
    vi.stubGlobal("SpeechRecognition", Recognition);
    const onFinal = vi.fn(), onEnd = vi.fn(), onTranscript = vi.fn();
    const { result } = renderHook(() => useSpeech({ lang: "kn", onFinal, onEnd, onTranscript }));
    act(() => { result.current.start(); });
    const old = Recognition.instances.at(-1)!;
    const lateResult = old.onresult!, lateEnd = old.onend!;
    act(() => { result.current.start(); });
    expect(Recognition.instances.at(-1)!.lang).toBe("kn-IN");
    act(() => {
      lateResult({ results: [{ 0: { transcript: "old", confidence: 0.9 }, isFinal: true }] });
      lateEnd();
    });
    expect(onFinal).not.toHaveBeenCalled();
    expect(onEnd).not.toHaveBeenCalled();
    act(() => result.current.abort());
    expect(onEnd).not.toHaveBeenCalled();
  });
});
