import { useMemo } from "react";
import type { CorrelationCell } from "@/api/types";
import { cn } from "@/lib/utils";
import { DIVERGING, sampleRamp } from "@/lib/palette";

/* ============================================================================
   Correlation-matrix heatmap (doc 03 §2.10). Crime categories × indicators,
   each cell shaded by Pearson r on a CVD-safe DIVERGING ramp centred on zero —
   and the r value is printed IN the cell, so meaning never rides on colour
   alone (§7). Click a cell to drive the scatter's focus indicator. Suppressed /
   too-small cells (r = null) render as a neutral dash, never a fake zero.
   ========================================================================== */

function cellColor(r: number | null | undefined): string | undefined {
  if (r == null) return undefined;
  // map r∈[-1,1] → t∈[0,1] for the diverging ramp (0.5 = no correlation)
  return sampleRamp(DIVERGING, (r + 1) / 2);
}

/** Dark ramp ends need light text; the pale middle needs dark text. */
function textOn(r: number | null | undefined): string {
  if (r == null) return "var(--text-dim)";
  return Math.abs(r) > 0.34 ? "#0b1020" : "var(--text)";
}

export function CorrelationMatrix({
  cells,
  focusIndicator,
  onSelect,
}: {
  cells: CorrelationCell[];
  focusIndicator?: string;
  onSelect?: (indicator: string, crimeCategory: string) => void;
}) {
  const { rows, cols, lookup } = useMemo(() => {
    const rowSet: string[] = [];
    const colSet: string[] = [];
    const map = new Map<string, CorrelationCell>();
    for (const c of cells) {
      if (!rowSet.includes(c.crime_category)) rowSet.push(c.crime_category);
      if (!colSet.includes(c.indicator)) colSet.push(c.indicator);
      map.set(`${c.crime_category}|${c.indicator}`, c);
    }
    return { rows: rowSet, cols: colSet, lookup: map };
  }, [cells]);

  if (!rows.length || !cols.length) return null;

  return (
    <div className="space-y-2">
      <div className="overflow-x-auto">
        <div
          className="grid gap-1"
          style={{ gridTemplateColumns: `minmax(9rem,1fr) repeat(${cols.length}, minmax(4.5rem,1fr))` }}
        >
          {/* header */}
          <div />
          {cols.map((ind) => (
            <button
              key={ind}
              type="button"
              onClick={() => onSelect?.(ind, rows[0])}
              title={ind}
              className={cn(
                "truncate px-1 pb-1 text-left text-12 font-medium transition-colors",
                focusIndicator === ind ? "text-primary" : "text-content-dim hover:text-content",
              )}
            >
              {ind}
            </button>
          ))}

          {/* rows */}
          {rows.map((cat) => (
            <FragmentRow
              key={cat}
              cat={cat}
              cols={cols}
              lookup={lookup}
              focusIndicator={focusIndicator}
              onSelect={onSelect}
            />
          ))}
        </div>
      </div>

      <Legend />
    </div>
  );
}

function FragmentRow({
  cat,
  cols,
  lookup,
  focusIndicator,
  onSelect,
}: {
  cat: string;
  cols: string[];
  lookup: Map<string, CorrelationCell>;
  focusIndicator?: string;
  onSelect?: (indicator: string, crimeCategory: string) => void;
}) {
  return (
    <>
      <div className="flex items-center truncate pr-1 text-13 text-content" title={cat}>
        {cat}
      </div>
      {cols.map((ind) => {
        const cell = lookup.get(`${cat}|${ind}`);
        const r = cell?.r ?? null;
        const focused = focusIndicator === ind;
        return (
          <button
            key={ind}
            type="button"
            onClick={() => onSelect?.(ind, cat)}
            title={
              cell
                ? `${cat} ↔ ${ind}\nr=${r != null ? r.toFixed(3) : "n/a"}${
                    cell.strength ? ` (${cell.strength})` : ""
                  } · n=${cell.n}`
                : `${cat} ↔ ${ind}: no data`
            }
            className={cn(
              "tnum flex h-9 items-center justify-center rounded-[6px] text-12 font-medium transition-shadow",
              focused && "ring-2 ring-primary",
            )}
            style={{ background: cellColor(r) ?? "var(--surface-2)", color: textOn(r) }}
          >
            {r != null ? r.toFixed(2) : "–"}
          </button>
        );
      })}
    </>
  );
}

function Legend() {
  return (
    <div className="flex flex-wrap items-center gap-2 px-1 text-12 text-content-dim">
      <span>−1</span>
      <span className="inline-flex h-2.5 w-32 overflow-hidden rounded-full">
        {DIVERGING.map((c) => (
          <span key={c} className="flex-1" style={{ background: c }} />
        ))}
      </span>
      <span>+1</span>
      <span className="ml-1">Pearson r · click a cell to focus the scatter</span>
    </div>
  );
}
