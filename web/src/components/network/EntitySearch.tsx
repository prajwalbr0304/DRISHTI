import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search, X } from "lucide-react";
import { api } from "@/api";
import type { EntityListItem } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";

/* Reusable entity picker — full-text search over /graph/entities. */
export function EntitySearch({
  placeholder = "Search an entity…",
  selected,
  onPick,
  onClear,
}: {
  placeholder?: string;
  selected?: { id: number; label: string } | null;
  onPick: (e: EntityListItem) => void;
  onClear?: () => void;
}) {
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(q.trim()), 350);
    return () => clearTimeout(t);
  }, [q]);

  const res = useQuery({
    queryKey: ["entities", "search", debounced],
    queryFn: ({ signal }) => api.graph.entities({ q: debounced, page_size: 8 }, signal),
    enabled: debounced.length >= 2,
  });

  if (selected) {
    return (
      <div className="flex items-center gap-2 rounded-control border border-hairline bg-surface-2 px-2.5 py-1.5">
        <span className="min-w-0 flex-1 truncate text-13 text-content">{selected.label}</span>
        <button type="button" onClick={onClear} className="text-content-dim hover:text-content" aria-label="Clear">
          <X className="size-4" />
        </button>
      </div>
    );
  }

  return (
    <div className="relative">
      <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-content-dim" />
      <Input
        value={q}
        onChange={(e) => {
          setQ(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        placeholder={placeholder}
        className="h-8 pl-8"
      />
      {open && debounced.length >= 2 && (
        <div className="absolute z-20 mt-1 max-h-64 w-full overflow-auto rounded-card border border-hairline bg-surface p-1 shadow-pop">
          {res.isLoading && <div className="px-2 py-2 text-12 text-content-dim">Searching…</div>}
          {res.data && res.data.items.length === 0 && (
            <div className="px-2 py-2 text-12 text-content-dim">No matches.</div>
          )}
          {res.data?.items.map((e) => (
            <button
              key={e.entity_id}
              type="button"
              onClick={() => {
                onPick(e);
                setOpen(false);
                setQ("");
              }}
              className="flex w-full items-center gap-2 rounded-control px-2 py-1.5 text-left transition-colors hover:bg-surface-2"
            >
              <span className="min-w-0 flex-1 truncate text-13 text-content">{e.label}</span>
              <Badge variant="neutral" className="shrink-0 capitalize">
                {e.entity_type.replace(/_/g, " ")}
              </Badge>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
