import { useMemo, useRef } from "react";
import { Responsive, WidthProvider, type Layout, type Layouts } from "react-grid-layout";
import { RotateCcw } from "lucide-react";
import { cn } from "@/lib/utils";
import { useDashboardStore } from "@/stores/useDashboardStore";
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

const COLS = { lg: 12, md: 12, sm: 6, xs: 1, xxs: 1 };
const BREAKPOINTS = { lg: 1024, md: 768, sm: 640, xs: 420, xxs: 0 };

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
  const stack = (cols: number): Layout[] => {
    let y = 0;
    return tiles.map((t) => {
      const item: Layout = { i: t.key, x: 0, y, w: cols, h: t.h, minW: 1, minH: t.minH ?? 2 };
      y += t.h;
      return item;
    });
  };
  return { lg, md: lg, sm: stack(6), xs: stack(1), xxs: stack(1) };
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

  // Stable signature so the default layout object doesn't churn every render
  // (which would fight RGL). Only the tile geometry matters here, not the nodes.
  const sig = tiles.map((t) => `${t.key}:${t.x},${t.y},${t.w},${t.h},${t.minW ?? ""},${t.minH ?? ""}`).join("|");
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const defaults = useMemo(() => buildLayouts(tiles), [sig]);

  const latest = useRef<Layouts | null>(null);
  const layouts = saved ?? defaults;

  return (
    <div>
      <div className="mb-1.5 flex min-h-[20px] items-center justify-end">
        {saved && (
          <button
            type="button"
            onClick={() => reset(id)}
            className="inline-flex items-center gap-1 rounded-control px-1.5 py-0.5 text-12 text-content-dim transition-colors hover:bg-surface-2 hover:text-content"
          >
            <RotateCcw className="size-3.5" /> Reset layout
          </button>
        )}
      </div>
      <Grid
        className="drishti-dashboard"
        layouts={layouts}
        breakpoints={BREAKPOINTS}
        cols={COLS}
        rowHeight={rowHeight}
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
        {tiles.map((t) => (
          <div key={t.key} className={cn("min-w-0", t.handle === "self" && "dash-drag cursor-move")}>
            {t.el}
          </div>
        ))}
      </Grid>
    </div>
  );
}
