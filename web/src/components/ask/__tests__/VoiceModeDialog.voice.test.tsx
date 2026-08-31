import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const h = vi.hoisted(() => ({
  onFinal: null as ((result: { text: string; confidence: number | null }) => void) | null,
  onEnd: null as (() => void) | null,
  onError: null as ((code: string) => void) | null,
  ttsSupported: false,
  send: vi.fn(),
  start: vi.fn(() => true),
  stop: vi.fn(),
  abort: vi.fn(),
  speakText: vi.fn(),
  stopSpeaking: vi.fn(),
}));

vi.mock("@/stores/useAskStore", () => ({
  VOICE_LOW_CONFIDENCE: 0.6,
  useAskStore: (selector: (state: { send: typeof h.send; busy: boolean; messages: unknown[] }) => unknown) =>
    selector({ send: h.send, busy: false, messages: [] }),
}));

vi.mock("@/components/ask/useSpeech", () => ({
  useSpeech: (opts: { onFinal?: typeof h.onFinal; onEnd?: typeof h.onEnd; onError?: typeof h.onError }) => {
    h.onFinal = opts.onFinal ?? null;
    h.onEnd = opts.onEnd ?? null;
    h.onError = opts.onError ?? null;
    return { supported: true, start: h.start, stop: h.stop, abort: h.abort };
  },
}));

vi.mock("@/components/ask/useTts", () => ({
  useTts: () => ({ supported: h.ttsSupported, speak: h.speakText, stop: h.stopSpeaking, voices: [] }),
  voicesForLanguage: () => [],
}));

import { VoiceModeDialog } from "@/components/ask/VoiceModeDialog";
import { TooltipProvider } from "@/components/ui/tooltip";

function renderDialog() {
  return render(
    <TooltipProvider>
    <VoiceModeDialog
      open
      onOpenChange={vi.fn()}
      language="en"
      providerLabel="Browser voice"
      plannerLabel="aws-bedrock"
      unscoredAutoSendAvailable
    />
    </TooltipProvider>,
  );
}

describe("VoiceModeDialog confidence gate", () => {
  beforeEach(() => {
    h.onFinal = null;
    h.ttsSupported = false;
    h.send.mockReset();
    h.send.mockResolvedValue({ reply: "Grounded answer", language: "en" });
    h.start.mockClear();
    h.stop.mockClear();
    h.abort.mockClear();
    h.speakText.mockClear();
    h.stopSpeaking.mockClear();
  });

  it("holds a low-confidence final transcript for explicit review", async () => {
    renderDialog();
    await waitFor(() => expect(h.start).toHaveBeenCalled());
    await screen.findByText("Listening…");

    act(() => h.onFinal?.({ text: "cases in Mysore", confidence: 0.42 }));

    expect(await screen.findByText(/low-confidence transcription \(42%\)/i)).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Your transcript" })).toHaveValue("cases in Mysore");
    expect(h.send).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: /send transcript/i }));
    await waitFor(() => expect(h.send).toHaveBeenCalledWith(
      "cases in Mysore",
      expect.objectContaining({ spoken: true, voiceMode: true, voiceConfirmed: true }),
    ));
  });

  it("automatically sends a high-confidence finalized transcript", async () => {
    renderDialog();
    await waitFor(() => expect(h.start).toHaveBeenCalled());
    await screen.findByText("Listening…");

    act(() => h.onFinal?.({ text: "cases in Mysuru", confidence: 0.91 }));

    await waitFor(() => expect(h.send).toHaveBeenCalledWith(
      "cases in Mysuru",
      expect.objectContaining({
        spoken: true,
        voiceMode: true,
        voiceConfidence: 0.91,
      }),
    ));
    expect(h.send.mock.calls[0][1].voiceConfirmed).toBeUndefined();
  });

  it("holds transcripts when the browser supplies no confidence", async () => {
    renderDialog();
    await waitFor(() => expect(h.start).toHaveBeenCalled());
    await screen.findByText("Listening…");

    act(() => h.onFinal?.({ text: "dashboard overview", confidence: null }));

    expect(await screen.findByText(/confidence is unavailable/i)).toBeInTheDocument();
    expect(h.send).not.toHaveBeenCalled();
  });

  it("supports explicit hands-free opt-in without fabricating confirmation", async () => {
    renderDialog();
    await screen.findByText("Listening…");
    fireEvent.click(screen.getByRole("checkbox", { name: /hands-free sending/i }));
    act(() => h.onFinal?.({ text: "dashboard overview", confidence: null }));
    await waitFor(() => expect(h.send).toHaveBeenCalledWith("dashboard overview",
      expect.objectContaining({ voiceAutoSend: true, voiceConfirmed: undefined })));
    await waitFor(() => expect(h.start).toHaveBeenCalledTimes(2));
    act(() => h.onFinal?.({ text: "and Mysore", confidence: 0.3 }));
    expect(await screen.findByText(/low-confidence transcription/i)).toBeInTheDocument();
    expect(h.send).toHaveBeenCalledTimes(1);
  });

  it("waits for speech to finish before listening for the next turn", async () => {
    h.ttsSupported = true;
    renderDialog();
    await screen.findByText("Listening…");
    act(() => h.onFinal?.({ text: "cases in Mysuru", confidence: 0.91 }));
    await waitFor(() => expect(h.speakText).toHaveBeenCalled());
    expect(h.start).toHaveBeenCalledTimes(1);
    act(() => h.speakText.mock.calls[0][2].onEnd());
    await waitFor(() => expect(h.start).toHaveBeenCalledTimes(2));
  });

  it("recovers from silence, but pauses on microphone denial", async () => {
    renderDialog();
    await screen.findByText("Listening…");
    act(() => h.onError?.("no-speech"));
    await waitFor(() => expect(h.start).toHaveBeenCalledTimes(2));
    act(() => h.onError?.("not-allowed"));
    expect(await screen.findByText(/microphone access was denied/i)).toBeInTheDocument();
    expect(h.send).not.toHaveBeenCalled();
  });

  it("does not restart after continuous mode is turned off", async () => {
    renderDialog();
    await screen.findByText("Listening…");
    fireEvent.click(screen.getByRole("checkbox", { name: "Continuous conversation" }));
    act(() => h.onFinal?.({ text: "cases", confidence: 0.9 }));
    await waitFor(() => expect(h.send).toHaveBeenCalled());
    expect(h.start).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("region", { name: "Conversation answers" })).toBeInTheDocument();
  });

  it("ignores an answer arriving after the dialog is closed", async () => {
    h.ttsSupported = true;
    let resolve!: (value: unknown) => void;
    h.send.mockReturnValue(new Promise((done) => { resolve = done; }));
    renderDialog();
    await screen.findByText("Listening…");
    act(() => h.onFinal?.({ text: "cases", confidence: 0.9 }));
    await waitFor(() => expect(h.send).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("button", { name: "End conversation" }));
    await act(async () => resolve({ reply: "Late answer", language: "en" }));
    expect(h.speakText).not.toHaveBeenCalled();
    expect(h.abort).toHaveBeenCalled();
  });
});
