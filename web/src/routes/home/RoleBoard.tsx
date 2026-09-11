import { useState } from "react";
import { KpiCard } from "@/components/dashboard/KpiCard";
import { DashboardGrid, type DashTile } from "@/components/dashboard/DashboardGrid";
import { boardFor, boardKpis, type WidgetSpec } from "@/config/kpi/roleBoards";
import {
  BOARD_WIDGETS, COMPOSITE_WIDGETS, SOCIO_BAND_ID, hasWidget,
} from "@/routes/home/boardWidgets";
import type { ScopeType } from "@/config/roles";
import { hiddenTiles, useDashboardStore } from "@/stores/useDashboardStore";
import { useUiVisibility } from "@/hooks/useUiVisibility";
import { useKpiValues } from "@/routes/home/useKpiValues";
import { useSocio } from "@/routes/home/useDashboardData";
import { useScopeChips } from "@/routes/home/useScopeChips";
import { socioTiles } from "@/routes/home/socioTiles";
import { defaultCrimeCategory } from "@/lib/socio";

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

   TWO KINDS OF WIDGET. Most ids resolve to one component through `BOARD_WIDGETS`
   and are placed by the packer. A COMPOSITE id expands to several tiles that place
   themselves, because how many there are is only known once the service answers —
   the socio-economic band is one read-out plus one scatter per indicator. Forcing
   that into a single fixed footprint is what had reduced it to a compact narrative
   card, dropping the ranked-correlation chart and every scatter plot with it.
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
  const { resolve } = useKpiValues(scope);
  /* Admin switches. Presentation only: a hidden card's endpoint still answers, so
     this decides what is DRAWN, never what may be read. */
  const ui = useUiVisibility();

  const specs = boardKpis(scope, wingCode);

  /* Socio-economic band. One request feeds the whole band — the response carries
     the district panel and a fit per cell, so each indicator box builds its own
     series client-side instead of re-querying. `useSocio` shares its react-query
     key with `useKpiValues` (which reads suppressed_cells / districts_analysed off
     the same payload), so the band costs no extra request.

     The category chosen in the read-out is the DEFAULT for every indicator box;
     a box the user sets individually keeps its own selection. Empty means "still
     following the service's narrative category", so a default arriving after first
     render still takes effect. */
  const socio = useSocio();
  const [socioCategory, setSocioCategory] = useState("");
  const socioChips = useScopeChips();
  const socioActiveCategory =
    socioCategory || (socio.data ? defaultCrimeCategory(socio.data) : "");

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

  /* Widgets the user has not dismissed and an admin has not switched off. An id
     with no component is dropped rather than rendered as an empty frame — and
     `boardWidgets.test` fails on it, so a typo in a board spec is caught at test
     time instead of appearing as a blank panel. */
  const shown = (id: string) =>
    !hiddenKeys.includes(id) && !ui.hidden.widget.has(id);

  /* Composites are held back from the packer: they expand to several tiles and
     place themselves, so packing them as one footprint would leave the rest of the
     band overlapping them. */
  const widgetSpecs = board.widgets.filter(
    (w) => hasWidget(w.id) && !COMPOSITE_WIDGETS.has(w.id) && shown(w.id),
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

  /* The band starts below the tallest widget placed, not below the last one: the
     packer fills rows left to right, so the last widget is often on a short row
     while a taller tile beside it still occupies later rows. */
  const bandY = packed.reduce((y, { spec, y: top }) => Math.max(y, top + spec.h), bodyY);
  const xlBandY = xlPacked.reduce((y, { spec, y: top }) => Math.max(y, top + spec.h), xlBodyY);

  const socioBandTiles: DashTile[] =
    board.widgets.some((w) => w.id === SOCIO_BAND_ID) && shown(SOCIO_BAND_ID)
      ? socioTiles({
          data: socio.data,
          loading: socio.isLoading,
          error: socio.error,
          onRefresh: () => socio.refetch(),
          category: socioActiveCategory,
          onCategoryChange: setSocioCategory,
          stateWideChip: socioChips.stateWide,
          startY: bandY,
          xlStartY: xlBandY,
        })
      : [];

  const tiles = [...kpiTiles, ...widgetTiles, ...socioBandTiles];

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
