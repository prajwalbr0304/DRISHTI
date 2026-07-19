import { useEffect, useMemo, useState } from "react";
import { Loader2 } from "lucide-react";
import { api } from "@/api";
import type { TimelineEventT } from "@/api/endpoints/board";
import { Badge } from "@/components/ui/badge";
import { formatDateTime } from "@/lib/utils";

/**
 * Timeline: replay/scrub the board's construction history (driven by the
 * append-only BoardActivity). Dragging the scrubber dims out-of-window objects
 * on the canvas (handled by the parent via onScrub) rather than deleting them.
 */
export function BoardTimeline({
  boardId,
  scrubTime,
  onScrub,
}: {
  boardId: number;
  scrubTime: string | null;
  onScrub: (t: string | null) => void;
}) {
  const [events, setEvents] = useState<TimelineEventT[]>([]);
  const [loading, setLoading] = useState(true);
  const [idx, setIdx] = useState(0);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    api.board.timeline(boardId).then((r) => {
      if (!alive) return;
      setEvents(r.events);
      setIdx(r.events.length);
    }).finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, [boardId]);

  const cutoff = useMemo(() => (idx >= events.length ? null : events[idx]?.at ?? null), [idx, events]);
  useEffect(() => onScrub(cutoff), [cutoff, onScrub]);

  if (loading) return <div className="grid h-40 place-items-center text-content-dim"><Loader2 className="size-5 animate-spin" /></div>;
  if (events.length === 0) return <p className="text-13 text-content-dim">No construction history yet.</p>;

  return (
    <div>
      <div className="mb-3 flex items-center gap-3">
        <input
          type="range" min={0} max={events.length} value={idx}
          onChange={(e) => setIdx(Number(e.target.value))} className="flex-1"
          aria-label="Replay construction history"
        />
        <span className="tnum text-12 text-content-dim">
          {idx >= events.length ? "now" : `#${events[idx]?.board_activity_id}`}
        </span>
      </div>
      <p className="mb-3 text-11 text-content-dim">
        {scrubTime ? "Objects added after this point are dimmed on the canvas (never deleted)." : "Showing the full board."}
      </p>
      <ol className="relative space-y-2 border-l border-hairline pl-4">
        {events.map((ev, i) => (
          <li key={ev.board_activity_id} className={i <= idx - 1 || idx >= events.length ? "" : "opacity-40"}>
            <span className="absolute -left-1.5 mt-1 size-3 rounded-full border border-hairline bg-surface" />
            <div className="flex flex-wrap items-center gap-2 text-12">
              <span className="tnum text-content-dim">#{ev.board_activity_id}</span>
              <span className="font-medium text-content">{ev.actor}</span>
              <Badge variant="neutral">{ev.action}</Badge>
              {ev.target_type && <span className="text-content-dim">{ev.target_type} {ev.target_id}</span>}
              <span className="ml-auto text-content-dim">{ev.at ? formatDateTime(ev.at) : ""}</span>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
