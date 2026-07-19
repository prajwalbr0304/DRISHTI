import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { BookmarkPlus, Clock, Layers, Trash2, X } from "lucide-react";
import { api } from "@/api";
import { formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PRESETS, useTimeStore, type TimePreset } from "@/stores/useTimeStore";
import { useCohortsStore } from "@/stores/useCohortsStore";

/* ============================================================================
   Saved lenses / cohorts (doc 01 §8.4). A lens is a named, reusable scope.
   Save the CURRENT time window and re-apply it anywhere; a few SUGGESTED lenses
   derived from the real data coverage are always available so the panel is
   useful out of the box. Real client-persisted state. Richer filter cohorts
   (district + crime-type + status) arrive with the Cases / Analytics explorers.
   ========================================================================== */

interface SuggestedLens {
  key: string;
  name: string;
  preset?: TimePreset; // anchor-relative
  start?: string; // or an explicit range
  end?: string;
}

export function SavedCohorts() {
  const cohorts = useCohortsStore((s) => s.cohorts);
  const saveCohort = useCohortsStore((s) => s.save);
  const removeCohort = useCohortsStore((s) => s.remove);
  const { preset, start, end, anchor } = useTimeStore();
  const setPreset = useTimeStore((s) => s.setPreset);
  const setCustomRange = useTimeStore((s) => s.setCustomRange);

  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");

  // Dataset coverage (shared, cached query — no extra request) to derive
  // suggested lenses over the actual historical range.
  const { data: coverage } = useQuery({
    queryKey: ["geo", "coverage"],
    queryFn: ({ signal }) => api.geo.coverage(signal),
    staleTime: Infinity,
    retry: false,
  });

  const presetLabel = preset === "custom" ? "Custom" : (PRESETS.find((p) => p.id === preset)?.label ?? "");

  const suggested = useMemo<SuggestedLens[]>(() => {
    const endISO = anchor;
    const year = endISO.slice(0, 4);
    const list: SuggestedLens[] = [
      { key: "90d", name: "Last 90 days", preset: "90d" },
      { key: "year", name: `Full year ${year}`, start: `${year}-01-01`, end: endISO },
    ];
    if (coverage?.min_date) {
      list.push({
        key: "all",
        name: `All history (${coverage.min_date.slice(0, 4)}–${year})`,
        start: coverage.min_date,
        end: coverage.max_date ?? endISO,
      });
    }
    return list;
  }, [anchor, coverage?.min_date, coverage?.max_date]);

  function applyCohort(c: (typeof cohorts)[number]) {
    if (c.preset === "custom") setCustomRange(c.start, c.end);
    else setPreset(c.preset);
  }

  function applySuggested(s: SuggestedLens) {
    if (s.preset) setPreset(s.preset);
    else if (s.start && s.end) setCustomRange(s.start, s.end);
  }

  function commit() {
    const label = name.trim() || `${presetLabel} lens`;
    saveCohort({ name: label, preset, start, end });
    setName("");
    setAdding(false);
  }

  return (
    <div className="space-y-3">
      {/* Suggested lenses — always available, derived from the real data range. */}
      <div className="space-y-1.5">
        <div className="text-11 font-semibold uppercase tracking-wide text-content-dim">Suggested</div>
        <div className="flex flex-wrap gap-1.5">
          {suggested.map((s) => (
            <button
              key={s.key}
              type="button"
              onClick={() => applySuggested(s)}
              className="flex items-center gap-1.5 rounded-control border border-hairline bg-surface-2/50 px-2.5 py-1 text-12 text-content transition-colors hover:border-primary/50 hover:bg-surface-2"
            >
              <Clock className="size-3.5 text-content-dim" />
              {s.name}
            </button>
          ))}
        </div>
      </div>

      {/* User-saved lenses */}
      <div className="space-y-1.5">
        <div className="flex items-center justify-between">
          <span className="text-11 font-semibold uppercase tracking-wide text-content-dim">Saved</span>
          {cohorts.length > 0 && <span className="tnum text-11 text-content-dim">{cohorts.length}</span>}
        </div>

        {cohorts.length === 0 && !adding && (
          <div className="flex flex-col items-center justify-center gap-1.5 rounded-control border border-dashed border-hairline py-5 text-center">
            <Layers className="size-5 text-content-dim" />
            <p className="text-12 text-content-dim">No saved lenses yet — save the current window to reuse it.</p>
          </div>
        )}

        {cohorts.map((c) => (
          <div key={c.id} className="group flex items-center gap-2 rounded-control bg-surface-2/50 px-2.5 py-1.5">
            <button type="button" onClick={() => applyCohort(c)} className="min-w-0 flex-1 text-left">
              <span className="block truncate text-13 font-medium text-content">{c.name}</span>
              <span className="tnum block truncate text-12 text-content-dim">
                {formatDate(c.start)} – {formatDate(c.end)}
              </span>
            </button>
            <button
              type="button"
              onClick={() => removeCohort(c.id)}
              className="shrink-0 text-content-dim opacity-0 transition-opacity hover:text-severity-critical group-hover:opacity-100"
              aria-label="Remove lens"
            >
              <Trash2 className="size-4" />
            </button>
          </div>
        ))}

        {adding ? (
          <div className="flex items-center gap-2">
            <Input
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={`${presetLabel} lens`}
              onKeyDown={(e) => {
                if (e.key === "Enter") commit();
                if (e.key === "Escape") setAdding(false);
              }}
              className="h-8"
            />
            <Button size="sm" onClick={commit}>
              Save
            </Button>
            <Button size="icon-sm" variant="ghost" onClick={() => setAdding(false)} aria-label="Cancel">
              <X />
            </Button>
          </div>
        ) : (
          <Button variant="outline" size="sm" onClick={() => setAdding(true)} className="w-full justify-center">
            <BookmarkPlus />
            Save current lens ({presetLabel})
          </Button>
        )}
      </div>
    </div>
  );
}
