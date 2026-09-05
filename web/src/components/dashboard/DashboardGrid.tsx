import { useEffect, useMemo, useRef, useState } from "react";
import { Responsive, WidthProvider, type Layout, type Layouts } from "react-grid-layout";
import { Eye, RotateCcw } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { hiddenTiles, mergeLayouts, useDashboardStore } from "@/stores/useDashboardStore";
import { DashTileContext, type DashTileHandle } from "@/components/dashboard/dashTile";
import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";

/* ============================================================================
   AWS-style dashboard: draggable + resizable card grid. Each tile declares its
   default position on a 12-column grid; users can drag it (by the six-dot grip
   in its card header) and resize it (edge / corner handles). Gutters use the
   AWS console board spacing of 20px. The arrangement is persisted per dashboard
   id and can be reset. Responsive: stacks to one column on narrow screens.
   ========================================================================== */

const Grid = WidthProvider(Responsive);

/* Wide displays get 24 columns instead of 12 so tiles REFLOW rather than just
   stretch. At 12 columns a 2300px board makes a metric card ~555px wide for a
   single number; at 24 it is ~370px, and the freed width is spent on a panel
   beside it instead of on emptiness. Tiles declare their wide position via
   `xl`; anything that does not simply doubles, which reproduces its 12-column
   proportions exactly and is therefore always safe. */
const COLS = { xl: 24, lg: 12, md: 12, sm: 6, xs: 1, xxs: 1 };
const BREAKPOINTS = { xl: 1800, lg: 1024, md: 768, sm: 640, xs: 420, xxs: 0 };

/* Row height scales with the board width. The tile geometry below was authored
   against roughly this content width, so on a wide monitor a tile would grow
   sideways only and end up letterboxed — a KPI card 550px wide and 108px tall,
   with its number stranded in a field of empty space. Growing the rows keeps
   tiles in proportion and puts the extra pixels to work.

   The growth is deliberately damped and capped: wide monitors are usually 16:9,
   so height does NOT scale with width, and matching the width ratio outright
   would push the board well below the fold. */
const LAYOUT_BASE_WIDTH = 1200;
const ROW_SCALE_DAMPING = 0.5;
const ROW_SCALE_MAX = 1.45;

function rowScale(containerWidth: number): number {
  if (!containerWidth) return 1;
  const ratio = containerWidth / LAYOUT_BASE_WIDTH;
  if (ratio <= 1) return 1;
  return Math.min(ROW_SCALE_MAX, 1 + (ratio - 1) * ROW_SCALE_DAMPING);
}

export interface DashTile {
  key: string;
  el: React.ReactNode;
  x: number;
  y: number;
  w: number;
  h: number;
  minW?: number;
  minH?: number;
  /** "header": the tile content owns a `.dash-drag` grip (the six dots in the
   *  Widget header).
   *  "self": the whole tile is the drag handle (e.g. a stat card). */
  handle?: "self" | "header";
  /** Position on the 24-column WIDE layout (viewports ≥1800px). Omit to reuse
   *  the 12-column geometry at double scale. Authoring this is what turns a
   *  wide screen from "same layout, stretched" into "more per row". */
  xl?: { x: number; y: number; w: number; h: number };
}

function buildLayouts(tiles: DashTile[]): Layouts {
  const lg: Layout[] = tiles.map((t) => ({
    i: t.key,
    x: t.x,
    y: t.y,
    w: t.w,
    h: t.h,
    minW: t.minW ?? 2,
    minH: t.minH ?? 2,
  }));
  // Wide (24-col): the declared `xl` position, else the 12-col one doubled.
  const xl: Layout[] = tiles.map((t) => {
    const g = t.xl ?? { x: t.x * 2, y: t.y, w: t.w * 2, h: t.h };
    return { i: t.key, ...g, minW: (t.minW ?? 2) * 2, minH: t.minH ?? 2 };
  });
  const stack = (cols: number): Layout[] => {
    let y = 0;
    return tiles.map((t) => {
      const item: Layout = { i: t.key, x: 0, y, w: cols, h: t.h, minW: 1, minH: t.minH ?? 2 };
      y += t.h;
      return item;
    });
  };
  return { xl, lg, md: lg, sm: stack(6), xs: stack(1), xxs: stack(1) };
}

export function DashboardGrid({
  id,
  tiles,
  rowHeight = 44,
}: {
  id: string;
  tiles: DashTile[];
  rowHeight?: number;
}) {
  const saved = useDashboardStore((s) => s.layouts[id]);
  const save = useDashboardStore((s) => s.save);
  const reset = useDashboardStore((s) => s.reset);
  const hidden = useDashboardStore((s) => hiddenTiles(s, id));
  const hideTile = useDashboardStore((s) => s.hideTile);
  const showAllTiles = useDashboardStore((s) => s.showAllTiles);

  /* Dismissed tiles never reach RGL, so they take no space and appear in no
     layout. A board may also pre-filter (the state command band re-flows its
     rows so removing a card doesn't leave a hole), in which case this is a
     harmless no-op. */
  const visible = useMemo(() => tiles.filter((t) => !hidden.includes(t.key)), [tiles, hidden]);
  /* Counted from the STORE, not by diffing `tiles`. A board that pre-filters its
     own tiles (to close the gap a removed card leaves) hands us a list that has
     already dropped them, so a diff would read zero and the way back would
     silently disappear. */
  const hiddenCount = hidden.length;

  // Stable signature so the default layout object doesn't churn every render
  // (which would fight RGL). Only the tile geometry matters here, not the nodes.
  const sig = visible
    .map((t) => {
      const xl = t.xl ? `${t.xl.x},${t.xl.y},${t.xl.w},${t.xl.h}` : "";
      return `${t.key}:${t.x},${t.y},${t.w},${t.h},${t.minW ?? ""},${t.minH ?? ""}:${xl}`;
    })
    .join("|");
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const defaults = useMemo(() => buildLayouts(visible), [sig]);

  /* One handle per tile, memoised on the visible set so a card's remove control
     keeps a stable identity between renders. */
  const handles = useMemo(() => {
    const map = new Map<string, DashTileHandle>();
    for (const t of visible) map.set(t.key, { key: t.key, remove: () => hideTile(id, t.key) });
    return map;
  }, [visible, hideTile, id]);

  /* Measure the board so rows can scale with it. RGL's WidthProvider keeps its
     measurement internal, so we take our own. Guarded for environments without
     ResizeObserver (jsdom). */
  const boardRef = useRef<HTMLDivElement>(null);
  const [boardWidth, setBoardWidth] = useState(0);
  useEffect(() => {
    const el = boardRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width ?? 0;
      if (w) setBoardWidth(w);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const scaledRowHeight = Math.round(rowHeight * rowScale(boardWidth));

  const latest = useRef<Layouts | null>(null);
  /* Additive: the user's arrangement for tiles they have seen, the declared
     geometry for tiles added since they last dragged one. Memoised so RGL is
     not handed a fresh object every render. */
  const layouts = useMemo(() => mergeLayouts(saved, defaults), [saved, defaults]);

  return (
    <div ref={boardRef}>
      {/* "Reset to default layout" — a secondary action that appears only once
          the layout has been customised. No placeholder row when it is absent:
          reserving space for a hidden control just leaves a gap under the page
          header. */}
      {(saved || hiddenCount > 0) && (
        <div className="mb-3 flex items-center justify-end gap-2">
          {/* Dismissing a card must never be one-way — this is the way back, and
              it states the count so a hidden card is never silently forgotten. */}
          {hiddenCount > 0 && (
            <Button variant="outline" size="sm" onClick={() => showAllTiles(id)}>
              <Eye /> Show {hiddenCount} hidden card{hiddenCount === 1 ? "" : "s"}
            </Button>
          )}
          {saved && (
            <Button variant="outline" size="sm" onClick={() => reset(id)}>
              <RotateCcw /> Reset to default layout
            </Button>
          )}
        </div>
      )}
      <Grid
        className="drishti-dashboard"
        layouts={layouts}
        breakpoints={BREAKPOINTS}
        cols={COLS}
        rowHeight={scaledRowHeight}
        /* AWS console board gutter (Cloudscape space-scaled-l) */
        margin={[20, 20]}
        containerPadding={[0, 0]}
        draggableHandle=".dash-drag"
        draggableCancel=".no-drag"
        resizeHandles={["se", "e", "s"]}
        onLayoutChange={(_current, all) => {
          latest.current = all;
        }}
        onDragStop={() => latest.current && save(id, latest.current)}
        onResizeStop={() => latest.current && save(id, latest.current)}
      >
        {visible.map((t) => (
          <div key={t.key} className={cn("min-w-0", t.handle === "self" && "dash-drag cursor-move")}>
            <DashTileContext.Provider value={handles.get(t.key) ?? null}>
              {t.el}
            </DashTileContext.Provider>
          </div>
        ))}
      </Grid>
    </div>
  );
}
