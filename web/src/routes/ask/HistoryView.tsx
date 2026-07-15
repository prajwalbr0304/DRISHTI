import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { History as HistoryIcon, Loader2, Mic, Search } from "lucide-react";
import { api } from "@/api";
import { errorMessage } from "@/api/contracts";
import { cn, timeAgo } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { EmptyState } from "@/components/common/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import { useLoadSession } from "@/routes/ask/useLoadSession";

/* History (doc 01 §4.7): past sessions, searchable. Opening one replays its
   real, grounded turns in the Chat column. */
export function HistoryView({ onOpened }: { onOpened: () => void }) {
  const q = useQuery({
    queryKey: ["chat", "sessions"],
    queryFn: ({ signal }) => api.chat.sessions(50, signal),
  });
  const { open, loadingId } = useLoadSession();
  const [search, setSearch] = useState("");

  const sessions = q.data?.sessions ?? [];
  const filtered = useMemo(() => {
    const s = search.trim().toLowerCase();
    if (!s) return sessions;
    return sessions.filter((x) =>
      [x.title, x.first_question, x.role, x.user_display_name]
        .filter(Boolean)
        .some((f) => (f as string).toLowerCase().includes(s)),
    );
  }, [sessions, search]);

  const handleOpen = async (id: number) => {
    await open(id);
    onOpened();
  };

  return (
    <div className="mx-auto max-w-3xl">
      <div className="relative mb-3">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-content-dim" />
        <Input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search past conversations…"
          className="pl-8"
        />
      </div>

      {q.isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      ) : q.error ? (
        <EmptyState icon={HistoryIcon} title="Couldn't load history" description={errorMessage(q.error)} />
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={HistoryIcon}
          title={search ? "No matching conversations" : "No conversations yet"}
          description={
            search
              ? "Try a different search term."
              : "Past Ask DRISHTI sessions will appear here. Start one from the Chat tab."
          }
        />
      ) : (
        <ul className="space-y-2">
          {filtered.map((s) => (
            <li key={s.session_id}>
              <button
                type="button"
                onClick={() => handleOpen(s.session_id)}
                disabled={loadingId != null}
                className="flex w-full items-start gap-3 rounded-card border border-hairline bg-surface p-3 text-left shadow-card transition-colors hover:bg-surface-2/50"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="min-w-0 truncate text-14 font-medium text-content" lang={s.language ?? "en"}>
                      {s.title || s.first_question || `Session ${s.session_id}`}
                    </span>
                    {s.language === "kn" && <Badge variant="neutral">ಕನ್ನಡ</Badge>}
                    {s.has_voice && (
                      <Badge variant="neutral">
                        <Mic className="size-3" /> voice
                      </Badge>
                    )}
                  </div>
                  {s.first_question && s.title !== s.first_question && (
                    <p className="mt-0.5 truncate text-13 text-content-dim" lang={s.language ?? "en"}>
                      {s.first_question}
                    </p>
                  )}
                  <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-12 text-content-dim">
                    <Badge variant="neutral" className="capitalize">{s.role ?? "—"}</Badge>
                    {s.user_display_name && <span>{s.user_display_name}</span>}
                    <span className="tnum">{s.message_count} messages</span>
                    {(s.last_activity || s.created_at) && (
                      <span>{timeAgo(s.last_activity ?? (s.created_at as string))}</span>
                    )}
                  </div>
                </div>
                {loadingId === s.session_id && (
                  <Loader2 className={cn("mt-1 size-4 shrink-0 animate-spin text-content-dim")} />
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
