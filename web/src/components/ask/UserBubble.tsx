import { AlertTriangle, Mic } from "lucide-react";
import type { AskMessage } from "@/stores/useAskStore";
import { formatPercent } from "@/lib/utils";

/* User turn. Right-aligned. Voice queries show a mic tag; a low-confidence
   transcription is flagged for read-back confirmation (doc 01 §4.7). */
export function UserBubble({ message }: { message: AskMessage }) {
  const voice = message.voice;
  const lowConf = voice?.is_low_confidence;

  return (
    <div className="flex flex-col items-end gap-1">
      <div className="max-w-[85%] rounded-card rounded-tr-sm bg-primary/12 px-3.5 py-2.5">
        <p lang={message.language} className="whitespace-pre-wrap text-14 text-content">
          {message.text}
        </p>
      </div>
      {(message.spoken || voice) && (
        <div className="flex items-center gap-2 pr-1 text-12 text-content-dim">
          <span className="inline-flex items-center gap-1">
            <Mic className="size-3" /> voice
            {voice?.confidence != null && (
              <span className="tnum">· {formatPercent(voice.confidence, 0)}</span>
            )}
          </span>
          {lowConf && (
            <span className="inline-flex items-center gap-1 text-severity-high">
              <AlertTriangle className="size-3" /> low-confidence — verify
            </span>
          )}
        </div>
      )}
    </div>
  );
}
