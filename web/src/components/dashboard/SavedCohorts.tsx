import { useState } from "react";
import { BookmarkPlus, Layers, Trash2, X } from "lucide-react";
import { formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PRESETS, useTimeStore } from "@/stores/useTimeStore";
import { useCohortsStore } from "@/stores/useCohortsStore";

/* ============================================================================
   Saved lenses / cohorts (doc 01 §8.4). A lens is a named, reusable scope.
   Here you can save the CURRENT time window and re-apply it anywhere. Richer
   filter cohorts (district + crime-type + status) arrive with the Cases /
   Analytics explorers. Real client-persisted state.
   ========================================================================== */

export function SavedCohorts() {
  const cohorts = useCohortsStore((s) => s.cohorts);
  const saveCohort = useCohortsStore((s) => s.save);
  const removeCohort = useCohortsStore((s) => s.remove);
  const { preset, start, end } = useTimeStore();
  const setPreset = useTimeStore((s) => s.setPreset);
  const setCustomRange = useTimeStore((s) => s.setCustomRange);

  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");

  const presetLabel = preset === "custom" ? "Custom" : (PRESETS.find((p) => p.id === preset)?.label ?? "");

  function apply(c: (typeof cohorts)[number]) {
    if (c.preset === "custom") setCustomRange(c.start, c.end);
    else setPreset(c.preset);
  }

  function commit() {
    const label = name.trim() || `${presetLabel} lens`;
    saveCohort({ name: label, preset, start, end });
    setName("");
    setAdding(false);
  }

  return (
    <div className="space-y-2">
      {cohorts.length === 0 && !adding && (
        <div className="flex flex-col items-center justify-center gap-2 py-6 text-center">
          <Layers className="size-5 text-content-dim" />
          <p className="text-13 text-content-dim">No saved lenses yet.</p>
        </div>
      )}

      {cohorts.map((c) => (
        <div key={c.id} className="group flex items-center gap-2 rounded-control bg-surface-2/50 px-2.5 py-1.5">
          <button type="button" onClick={() => apply(c)} className="min-w-0 flex-1 text-left">
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
            onKeyDown={(e) => e.key === "Enter" && commit()}
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
  );
}
