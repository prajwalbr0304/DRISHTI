import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const h = vi.hoisted(() => ({
  onFinal: null as ((result: { text: string; confidence: number | null }) => void) | null,
  send: vi.fn(),
  start: vi.fn(() => true),
  stop: vi.fn(),
  abort: vi.fn(),
  speakText: vi.fn(),
  stopSpeaking: vi.fn(),
}));

vi.mock("@/stores/useAskStore", () => ({
  VOICE_LOW_CONFIDENCE: 0.6,
  useAskStore: (selector: (state: { send: typeof h.send; busy: boolean }) => unknown) =>
    selector({ send: h.send, busy: false }),
}));

vi.mock("@/components/ask/useSpeech", () => ({
  useSpeech: (opts: { onFinal?: typeof h.onFinal }) => {
    h.onFinal = opts.onFinal ?? null;
    return { supported: true, start: h.start, stop: h.stop, abort: h.abort };
  },
}));

vi.mock("@/components/ask/useTts", () => ({
  useTts: () => ({ supported: false, speak: h.speakText, stop: h.stopSpeaking }),
}));

import { VoiceModeDialog } from "@/components/ask/VoiceModeDialog";

function renderDialog() {
  return render(
    <VoiceModeDialog
      open
      onOpenChange={vi.fn()}
      language="en"
      providerLabel="Browser voice"
      plannerLabel="aws-bedrock"
    />,
  );
}

describe("VoiceModeDialog confidence gate", () => {
  beforeEach(() => {
    h.onFinal = null;
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
    expect(screen.getByText("cases in Mysore")).toBeInTheDocument();
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
});
