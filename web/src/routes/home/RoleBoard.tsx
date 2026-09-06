import { KpiCard } from "@/components/dashboard/KpiCard";
import { DashboardGrid, type DashTile } from "@/components/dashboard/DashboardGrid";
import { boardFor, boardKpis, type WidgetSpec } from "@/config/kpi/roleBoards";
import { BOARD_WIDGETS, hasWidget } from "@/routes/home/boardWidgets";
import type { ScopeType } from "@/config/roles";
import { hiddenTiles, useDashboardStore } from "@/stores/useDashboardStore";
import { useUiVisibility } from "@/hooks/useUiVisibility";
import { useKpiValues } from "@/routes/home/useKpiValues";

/* ============================================================================
   One board, composed from the KPI registry.

   Replaces the five hand-written boards that had drifted apart: the same metric
   carried different labels and different hints depending on which file you were
   in, and adding a card meant editing whichever subset of the five you remembered.

   Keyed by SCOPE TYPE, not by role. A `senior_command` seat is an ADGP wing board
   when wing-scoped and a DIG range board when range-scoped — different jobs, one
   role — so a role-keyed board could not tell them apart.

   The card set comes from `boardKpis(scope, wing)`, which intersects three things:
   where a metric is meaningful, what the board asks for, and what the board
   explicitly omits. Nothing here decides what to show; it only renders it.
   ========================================================================== */

/** 12-column grid, four cards a row, two rows tall. */
const KPI_W = 3;
const KPI_H = 2;
const KPI_PER_ROW = 12 / KPI_W;

/** Left-to-right row packing for the widget band.
 *
 *  `roleBoards.ts` declares only a footprint (`w`/`h`), not a position, so the
 *  board places them: fill the current row, wrap when the next widget would not
 *  fit, and start the new row below the tallest tile placed so far. Declaring
 *  absolute coordinates in the spec was the alternative and it does not survive
 *  editing — removing one widget would leave a hole and every later widget would
 *  need renumbering by hand.
 *
 *  `scale` widens each footprint for the 24-column layout. */
function packRow(
  specs: WidgetSpec[],
  cols: number,
  startY: number,
  scale = 1,
): { spec: WidgetSpec; x: number; y: number }[] {
  const out: { spec: WidgetSpec; x: number; y: number }[] = [];
  let x = 0;
  let y = startY;
  let rowH = 0;
  for (const spec of specs) {
    const w = spec.w * scale;
    if (x + w > cols) {
      x = 0;
      y += rowH;
      rowH = 0;
    }
    out.push({ spec, x, y });
    x += w;
    rowH = Math.max(rowH, spec.h);
  }
  return out;
}

/** The 24-column breakpoint fits six per row at the same pixel size, so a large
 *  monitor shows more of the band above the fold rather than four wide cards. */
const XL_KPI_W = 4;
const XL_KPI_PER_ROW = 24 / XL_KPI_W;

export function RoleBoard({
  scope,
  wingCode,
}: {
  scope: ScopeType;
  wingCode?: string | null;
}) {
  const board = boardFor(scope);
  /* Grid layout is persisted per BOARD, so a DIG rearranging the range board does
     not disturb the ADGP wing board even though both are senior_command. */
  const gridId = `board:${scope}`;
  const hiddenKeys = useDashboardStore((s) => hiddenTiles(s, gridId));
  const { resolve } = useKpiValues();
  /* Admin switches. Presentation only: a hidden card's endpoint still answers, so
     this decides what is DRAWN, never what may be read. */
  const ui = useUiVisibility();

  const specs = boardKpis(scope, wingCode);

  /* Two independent ways a card can be absent, and they are not the same thing:
       - `hiddenKeys`  the USER dismissed it from their own board (local, per-grid);
       - `ui.hidden`   an ADMIN turned it off for this role (server, per-role).
     A user cannot restore something the admin disabled, and an admin enabling
     something does not undo a user's own dismissal. */
  const visible = specs.filter(
    (s) => !hiddenKeys.includes(s.id) && !ui.hidden.kpi.has(s.id),
  );

  /* Positions are computed over the VISIBLE cards. The grid drops a hidden tile on
     its own, but the band then keeps the gap where that card used to be and the
     row rhythm breaks — re-flowing here means removing a card closes the hole, at
     both 12 and 24 columns. */
  const kpiTiles: DashTile[] = visible.map((spec, i) => ({
    key: spec.id,
    handle: "self" as const,
    x: (i % KPI_PER_ROW) * KPI_W,
    y: Math.floor(i / KPI_PER_ROW) * KPI_H,
    w: KPI_W,
    h: KPI_H,
    xl: {
      x: (i % XL_KPI_PER_ROW) * XL_KPI_W,
      y: Math.floor(i / XL_KPI_PER_ROW) * KPI_H,
      w: XL_KPI_W,
      h: KPI_H,
    },
    minW: 2,
    minH: 2,
    el: <KpiCard className="h-full" {...resolve(spec)} />,
  }));

  /* Widgets sit below the KPI band, starting on the row after the last card. Both
     layouts are packed independently: at 24 columns the same widget list fits
     differently, and reusing the 12-column rows there would leave half the board
     empty. */
  const bodyY = Math.ceil(visible.length / KPI_PER_ROW) * KPI_H;
  const xlBodyY = Math.ceil(visible.length / XL_KPI_PER_ROW) * KPI_H;

  /* Only widgets the resolver knows AND the user has not dismissed. An id with no
     component is dropped rather than rendered as an empty frame — and
     `boardWidgets.test` fails on it, so a typo in a board spec is caught at test
     time instead of appearing as a blank panel. */
  const widgetSpecs = board.widgets.filter(
    (w) => hasWidget(w.id)
      && !hiddenKeys.includes(w.id)
      && !ui.hidden.widget.has(w.id),
  );

  const packed = packRow(widgetSpecs, 12, bodyY);
  const xlPacked = packRow(widgetSpecs, 24, xlBodyY, 2);

  const widgetTiles: DashTile[] = packed.map(({ spec, x, y }, i) => {
    const Component = BOARD_WIDGETS[spec.id];
    return {
      key: spec.id,
      handle: "header" as const,
      x, y, w: spec.w, h: spec.h,
      xl: { x: xlPacked[i].x, y: xlPacked[i].y, w: spec.w * 2, h: spec.h },
      minW: 3,
      minH: 4,
      el: <Component label={spec.label} />,
    };
  });

  const tiles = [...kpiTiles, ...widgetTiles];

  if (!tiles.length) {
    return (
      <div className="rounded-card border border-hairline bg-surface p-6">
        <h2 className="text-16 font-semibold text-content">{board.title}</h2>
        <p className="mt-2 max-w-[70ch] text-13 leading-relaxed text-content-dim">
          {board.subtitle}
        </p>
      </div>
    );
  }

  return <DashboardGrid id={gridId} tiles={tiles} />;
}
