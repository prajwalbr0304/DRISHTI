import { useEffect, useRef, useState } from "react";
import { AudioLines, Loader2, Mic, Pause, X } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { AnswerCard } from "./AnswerCard";
import { SONIC_VOICES, useSonic } from "./useSonic";
import { useAskStore } from "@/stores/useAskStore";

export function SonicVoiceDialog({ open, onOpenChange, onBrowserVoice }: {
  open: boolean; onOpenChange: (open: boolean) => void; onBrowserVoice: () => void;
}) {
  const sonic = useSonic();
  const { stop } = sonic;
  const [voice, setVoice] = useState(() => {
    try { const saved = localStorage.getItem("drishti-sonic-voice"); return saved && saved in SONIC_VOICES ? saved : "kiara"; }
    catch { return "kiara"; }
  });
  const messages = useAskStore((state) => state.messages);
  const answers = useRef<HTMLElement>(null);
  useEffect(() => { if (!open) stop(); }, [open, stop]);
  useEffect(() => {
    const panel = answers.current;
    if (panel) panel.scrollTop = panel.scrollHeight;
  }, [messages, sonic.spokenReply]);
  const active = sonic.phase !== "idle" && sonic.phase !== "error";
  const close = () => { stop(); onOpenChange(false); };
  const statuses = { idle: "Ready when you are", connecting: "Connecting to Nova", listening: "Listening", speaking: "Speaking", error: "Voice paused" };
  return <Dialog open={open} onOpenChange={(next) => { if (!next) close(); }}>
    <DialogContent hideClose className="flex h-[min(850px,calc(100dvh-2rem))] w-[calc(100vw-2rem)] max-w-6xl flex-col gap-0 overflow-hidden p-0">
      <header className="flex items-center justify-between gap-3 border-b border-hairline px-5 py-4">
        <div><DialogTitle className="flex items-center gap-2"><AudioLines className="size-5 text-primary" />Voice mode</DialogTitle>
          <DialogDescription>Amazon Nova 2 Sonic</DialogDescription></div>
        <Button variant="ghost" size="icon" title="End conversation" aria-label="End conversation" onClick={close}><X className="size-5" /></Button>
      </header>
      <div className="grid min-h-0 flex-1 grid-cols-1 overflow-y-auto md:grid-cols-[minmax(280px,340px)_minmax(0,1fr)] md:overflow-hidden">
        <section aria-label="Voice controls" className="min-w-0 space-y-5 border-b border-hairline p-5 md:overflow-y-auto md:border-b-0 md:border-r">
          <div className="flex flex-col items-center gap-3 py-5">
            <Button size="icon" className="size-24 rounded-full" title={active ? "Pause conversation" : "Start Nova conversation"}
              aria-label={active ? "Pause conversation" : "Start Nova conversation"}
              onClick={() => { if (active) stop(); else void sonic.start(voice); }}>
              {sonic.phase === "connecting" ? <Loader2 className="size-8 animate-spin" /> : active ? <Pause className="size-8" /> : <Mic className="size-8" />}
            </Button>
            <p role="status" className="text-15 font-semibold">{statuses[sonic.phase]}</p>
            <p className="text-12 text-content-dim">English · Continuous conversation</p>
          </div>
          <label className="block text-13">Voice
            <select aria-label="Speaking voice" disabled={active} value={voice} onChange={(event) => {
              setVoice(event.target.value);
              try { localStorage.setItem("drishti-sonic-voice", event.target.value); } catch { /* storage optional */ }
            }} className="mt-2 w-full rounded-md border border-hairline bg-surface p-2">
              {Object.entries(SONIC_VOICES).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
            </select>
          </label>
          <p className="text-12 text-content-dim">Starting sends microphone audio to Amazon Bedrock in us-east-1. DRISHTI does not store raw audio. Transcripts and grounded answers are saved in chat history.</p>
          {sonic.error && <p role="alert" className="text-13 text-severity-high">{sonic.error}</p>}
          {sonic.transcript && <div><h3 className="text-12 font-semibold">Your transcript</h3><p className="mt-2 break-words text-14">{sonic.transcript}</p></div>}
          <Button variant="outline" onClick={() => { stop(); onBrowserVoice(); }}>Use browser voice</Button>
        </section>
        <section ref={answers} aria-label="Conversation answers" className="min-h-[280px] min-w-0 bg-surface-2/40 md:overflow-y-auto">
          <h2 className="sticky top-0 z-10 border-b border-hairline bg-surface px-5 py-3 text-14 font-semibold">Conversation</h2>
          <div className="space-y-5 p-5 [&_pre]:max-w-full [&_pre]:overflow-x-auto [&_p]:break-words">
            {!messages.length && <p className="py-12 text-center text-14 text-content-dim">No answers yet</p>}
            {messages.map((message) => message.sender === "user"
              ? <p key={message.id} className="ml-8 whitespace-pre-wrap text-right text-14">{message.text}</p>
              : <AnswerCard key={message.id} message={message} />)}
            {sonic.spokenReply && <div className="border-t border-hairline pt-4"><h3 className="text-12 font-semibold">Spoken response</h3><p className="mt-2 text-14">{sonic.spokenReply}</p></div>}
          </div>
        </section>
      </div>
    </DialogContent>
  </Dialog>;
}
