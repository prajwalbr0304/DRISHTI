import { describe, expect, it, vi, beforeEach } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { useState, type ReactNode } from "react";

/* Web Speech isn't available in jsdom, so we mock the speech hook and drive its
   transcript + confidence deterministically. `vi.hoisted` shares the control
   state with the (hoisted) mock factory. */
const h = vi.hoisted(() => ({
  onTranscript: null as ((t: string) => void) | null,
  confidence: 0.3 as number | null,
  supported: true,
  listening: false,
}));

vi.mock("@/components/ask/useSpeech", () => ({
  useSpeech: (opts: { onTranscript: (t: string) => void }) => {
    h.onTranscript = opts.onTranscript;
    return {
      supported: h.supported,
      listening: h.listening,
      confidence: h.confidence,
      start: () => {},
      stop: () => {},
      toggle: () => {},
    };
  },
  speechLocale: (l: string) => (l === "kn" ? "kn-IN" : "en-IN"),
}));

import { Composer } from "@/components/ask/Composer";
import { RoleProvider } from "@/providers/RoleProvider";
import { TooltipProvider } from "@/components/ui/tooltip";
import type { AskLangMode } from "@/stores/useAskStore";

type SendOpts = {
  spoken?: boolean;
  voiceConfidence?: number;
  voiceLanguage?: string;
  voiceConfirmed?: boolean;
};

function Harness({ onSend }: { onSend: (opts?: SendOpts) => void }) {
  const [value, setValue] = useState("");
  const [mode, setMode] = useState<AskLangMode>("auto");
  return (
    <Composer
      value={value}
      onChange={setValue}
      onSend={onSend}
      language="en"
      languageMode={mode}
      onLanguageModeChange={setMode}
    />
  );
}

function renderComposer(onSend: (opts?: SendOpts) => void) {
  const ui: ReactNode = (
    <TooltipProvider>
      <RoleProvider>
        <Harness onSend={onSend} />
      </RoleProvider>
    </TooltipProvider>
  );
  return render(ui);
}

describe("Composer voice (Prompt 19 §E — browser voice + low-confidence gate)", () => {
  beforeEach(() => {
    h.confidence = 0.3;
    h.supported = true;
    h.listening = false;
    localStorage.clear();
  });

  it("does not send a low-confidence transcript on first Send; confirms then sends", () => {
    const onSend = vi.fn();
    renderComposer(onSend);

    // A low-confidence spoken transcript arrives from the recogniser.
    act(() => h.onTranscript?.("how many thefts in bengaluru"));
    expect(screen.getByText(/low-confidence/i)).toBeInTheDocument();

    // First Send click must NOT execute — it asks for confirmation instead.
    fireEvent.click(screen.getByRole("button", { name: /^send$/i }));
    expect(onSend).not.toHaveBeenCalled();

    // Explicit confirm sends, flagged as a confirmed spoken query.
    fireEvent.click(screen.getByRole("button", { name: /send anyway/i }));
    expect(onSend).toHaveBeenCalledTimes(1);
    expect(onSend).toHaveBeenCalledWith(
      expect.objectContaining({ spoken: true, voiceConfirmed: true }),
    );
  });

  it("clears the low-confidence gate when the user edits the transcript", () => {
    const onSend = vi.fn();
    renderComposer(onSend);

    act(() => h.onTranscript?.("thefts"));
    expect(screen.getByText(/low-confidence/i)).toBeInTheDocument();

    // Editing the text clears the spoken low-confidence state.
    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "thefts in bengaluru this year" },
    });
    expect(screen.queryByText(/low-confidence/i)).toBeNull();

    // Now it sends straight away, no confirm, as a normal (non-spoken) query.
    fireEvent.click(screen.getByRole("button", { name: /^send$/i }));
    expect(onSend).toHaveBeenCalledTimes(1);
    expect(onSend).toHaveBeenCalledWith(expect.objectContaining({ spoken: false }));
  });

  it("labels the mic as browser voice and never claims Zia", () => {
    renderComposer(vi.fn());
    expect(screen.getByText(/browser voice/i)).toBeInTheDocument();
    expect(screen.queryByText(/zia/i)).toBeNull();
  });
});
