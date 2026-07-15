import { Clock } from "lucide-react";
import { timeAgo } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { useRecentsStore } from "@/stores/useRecentsStore";
import { usePeekStore } from "@/stores/usePeekStore";

/* ============================================================================
   Recent activity — the objects this user opened, newest first (doc 01 §4.1,
   "resume where you left off"). Sourced from the user's own client-side history,
   not fabricated. Clicking re-opens the object in the peek rail.
   ========================================================================== */

export function RecentActivity() {
  const items = useRecentsStore((s) => s.items);
  const open = usePeekStore((s) => s.open);

  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 py-8 text-center">
        <Clock className="size-5 text-content-dim" />
        <p className="text-13 text-content-dim">Objects you open will appear here.</p>
      </div>
    );
  }

  return (
    <div className="max-h-[240px] overflow-y-auto">
      {items.map((it) => (
        <button
          key={`${it.kind}:${it.id}`}
          type="button"
          onClick={() => open(it)}
          className="flex w-full items-center gap-2.5 rounded-control px-2 py-1.5 text-left transition-colors hover:bg-surface-2"
        >
          <Badge variant="neutral" className="shrink-0 capitalize">
            {it.kind}
          </Badge>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-13 text-content">{it.label}</span>
            {it.sublabel && <span className="block truncate text-12 text-content-dim">{it.sublabel}</span>}
          </span>
          <span className="tnum shrink-0 text-12 text-content-dim">{timeAgo(it.at)}</span>
        </button>
      ))}
    </div>
  );
}
