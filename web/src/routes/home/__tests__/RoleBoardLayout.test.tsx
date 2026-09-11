import { describe, expect, it, vi } from "vitest";
import { render } from "@testing-library/react";
import type { DashTile } from "@/components/dashboard/DashboardGrid";
import { BOARDS, boardKpis } from "@/config/kpi/roleBoards";
import type { ScopeType } from "@/config/roles";

/* ============================================================================
   BOARD ARRANGEMENT, for every seat.

   `CommandCenterRoleHome.test.tsx` covers WHICH cards and panels a scope type
   composes. This file covers WHERE they land, which is a separate failure mode
   and the one a user actually sees: a board can contain exactly the right tiles
   and still be unreadable if they overlap, spill past the grid, or interleave
   the panels with the metric cards.

   Asserted against the geometry RoleBoard hands to the grid rather than against
   rendered pixels: react-grid-layout positions tiles from that geometry, so if
   it is a clean, gap-free, non-overlapping packing then the board is arranged —
   and jsdom has no layout engine to measure anyway.

   The four properties below are what "arranged" means here, checked at BOTH
   breakpoints because the 12-column and 24-column layouts are packed by separate
   code paths and only one of them was ever eyeballed:

     1. nothing overlaps,
     2. nothing spills past the last column,
     3. the metric cards form a full, in-order grid from the top-left,
     4. every panel sits strictly BELOW every metric card.
   ========================================================================== */

/* ---------------------------------------------------------------- capture --- */
const captured = vi.hoisted(() => ({ tiles: [] as DashTile[], rendered: false }));

vi.mock("@/components/dashboard/DashboardGrid", () => ({
  DashboardGrid: ({ tiles }: { tiles: DashTile[] }) => {
    captured.tiles = tiles;
    captured.rendered = true;
    return <div data-testid="grid" />;
  },
}));

vi.mock("@/components/dashboard/KpiCard", () => ({
  KpiCard: ({ label }: { label: string }) => <div>{label}</div>,
}));

vi.mock("@/routes/home/useKpiValues", () => ({
  useKpiValues: () => ({
    resolve: (spec: { id: string; label: string }) => ({ label: spec.label, value: 1 }),
  }),
}));

/* Every widget id declared by any board resolves to a marker. Built from the
   real specs so a board gaining a panel is covered without editing this file. */
vi.mock("@/routes/home/boardWidgets", async () => {
  const { BOARDS: SPECS } = await import("@/config/kpi/roleBoards");
  const SOCIO = "socio-band";
  const ids = new Set<string>();
  for (const board of Object.values(SPECS)) {
    for (const w of board.widgets) if (w.id !== SOCIO) ids.add(w.id);
  }
  const widgets: Record<string, (p: { label: string }) => JSX.Element> = {};
  for (const id of ids) widgets[id] = ({ label }) => <div>{label}</div>;
  return {
    BOARD_WIDGETS: widgets,
    COMPOSITE_WIDGETS: new Set([SOCIO]),
    SOCIO_BAND_ID: SOCIO,
    hasWidget: (id: string) => id in widgets || id === SOCIO,
  };
});

/* The socio band expands to 1 + N tiles sized from a live response. Stubbed to a
   single full-width tile at the offsets RoleBoard passes in, which is what makes
   the `bandY` hand-off testable: if the band were given a row still occupied by
   a tall panel, this tile would overlap it and property 1 would fail. */
vi.mock("@/routes/home/socioTiles", () => ({
  socioTiles: ({ startY, xlStartY }: { startY: number; xlStartY: number }) => [
    {
      key: "socio-band",
      el: <div>socio</div>,
      x: 0, y: startY, w: 12, h: 8,
      xl: { x: 0, y: xlStartY, w: 24, h: 8 },
    },
  ],
}));

vi.mock("@/routes/home/useDashboardData", () => ({
  useSocio: () => ({ data: undefined, isLoading: false, error: null, refetch: () => {} }),
}));

vi.mock("@/routes/home/useScopeChips", () => ({
  useScopeChips: () => ({ stateWide: null }),
}));

vi.mock("@/hooks/useUiVisibility", () => ({
  useUiVisibility: () => ({
    hidden: { kpi: new Set<string>(), widget: new Set<string>() },
    isVisible: () => true,
    reasonFor: () => undefined,
  }),
}));

const { RoleBoard } = await import("@/routes/home/RoleBoard");

/* ----------------------------------------------------------------- helpers --- */
type Box = { key: string; x: number; y: number; w: number; h: number };

/** The two layouts RoleBoard produces. `xl` falls back to double the 12-column
 *  geometry, exactly as `buildLayouts` in DashboardGrid does. */
function boxesFor(tiles: DashTile[], breakpoint: Breakpoint): Box[] {
  return tiles.map((t) => {
    if (breakpoint === "lg") return { key: t.key, x: t.x, y: t.y, w: t.w, h: t.h };
    const g = t.xl ?? { x: t.x * 2, y: t.y, w: t.w * 2, h: t.h };
    return { key: t.key, ...g };
  });
}

function overlaps(a: Box, b: Box): boolean {
  return a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
}

function findOverlaps(boxes: Box[]): string[] {
  const clashes: string[] = [];
  for (let i = 0; i < boxes.length; i++) {
    for (let j = i + 1; j < boxes.length; j++) {
      if (overlaps(boxes[i], boxes[j])) {
        const a = boxes[i];
        const b = boxes[j];
        clashes.push(
          `${a.key}(${a.x},${a.y} ${a.w}x${a.h}) overlaps ${b.key}(${b.x},${b.y} ${b.w}x${b.h})`,
        );
      }
    }
  }
  return clashes;
}

function renderBoard(scope: ScopeType, wingCode?: string): DashTile[] {
  captured.tiles = [];
  captured.rendered = false;
  render(<RoleBoard scope={scope} wingCode={wingCode ?? null} />);
  return captured.tiles;
}

/** Scope types that compose a real board. `unresolved` deliberately has none. */
const POPULATED = (Object.keys(BOARDS) as ScopeType[]).filter((s) => s !== "unresolved");

/** Cards a board renders, so the test knows where the metric band ends without
 *  hard-coding a count that would drift with the registry. */
const kpiCount = (scope: ScopeType, wingCode?: string) =>
  boardKpis(scope, wingCode ?? null).length;

type Breakpoint = "lg" | "xl";
const BREAKPOINTS: Breakpoint[] = ["lg", "xl"];

const COLS: Record<Breakpoint, number> = { lg: 12, xl: 24 };
const PER_ROW: Record<Breakpoint, number> = { lg: 4, xl: 6 };
const CARD_W: Record<Breakpoint, number> = { lg: 3, xl: 4 };
const CARD_H = 2;

describe.each(POPULATED)("board arrangement — %s scope", (scope) => {
  // A wing board's card set is wing-code dependent; CTS is the widest remit.
  const wingCode = scope === "wing" ? "CTS" : undefined;

  it.each(BREAKPOINTS)("has no overlapping tiles at %s", (bp: Breakpoint) => {
    const boxes = boxesFor(renderBoard(scope, wingCode), bp);
    expect(boxes.length).toBeGreaterThan(0);
    expect(findOverlaps(boxes)).toEqual([]);
  });

  it.each(BREAKPOINTS)("keeps every tile inside the %s grid", (bp: Breakpoint) => {
    const boxes = boxesFor(renderBoard(scope, wingCode), bp);
    const spilled = boxes.filter((b) => b.x < 0 || b.x + b.w > COLS[bp]);
    expect(spilled).toEqual([]);
  });

  it.each(BREAKPOINTS)("lays the metric cards out in order at %s", (bp: Breakpoint) => {
    const tiles = renderBoard(scope, wingCode);
    const n = kpiCount(scope, wingCode);
    const cards = boxesFor(tiles, bp).slice(0, n);

    // Row-major from the top-left, no gaps, uniform size: the property that
    // makes a dense band scannable instead of looking shuffled.
    cards.forEach((card, i) => {
      expect(card).toMatchObject({
        x: (i % PER_ROW[bp]) * CARD_W[bp],
        y: Math.floor(i / PER_ROW[bp]) * CARD_H,
        w: CARD_W[bp],
        h: CARD_H,
      });
    });
  });

  it.each(BREAKPOINTS)("puts every panel below the metric band at %s", (bp: Breakpoint) => {
    const tiles = renderBoard(scope, wingCode);
    const n = kpiCount(scope, wingCode);
    const boxes = boxesFor(tiles, bp);
    const cards = boxes.slice(0, n);
    const panels = boxes.slice(n);

    const bandBottom = Math.max(...cards.map((c) => c.y + c.h));
    const intruding = panels.filter((p) => p.y < bandBottom);
    expect(intruding).toEqual([]);
  });
});

describe("board arrangement — unposted seat", () => {
  it("renders the posting notice instead of an empty grid", () => {
    const tiles = renderBoard("unresolved");
    expect(tiles).toEqual([]);
    expect(captured.rendered).toBe(false);
  });
});

describe("board arrangement — the metric band reflows around a dismissal", () => {
  it("closes the hole rather than leaving a gap where a card was", async () => {
    const { useDashboardStore } = await import("@/stores/useDashboardStore");
    const specs = boardKpis("station", null);
    const dropped = specs[1].id;

    useDashboardStore.setState({ hidden: { "board:station": [dropped] } });
    try {
      const boxes = boxesFor(renderBoard("station"), "lg");
      const cards = boxes.slice(0, specs.length - 1);

      expect(cards.map((c) => c.key)).not.toContain(dropped);
      // Still a contiguous grid: the card that followed the dismissed one has
      // moved up into its slot.
      cards.forEach((card, i) => {
        expect(card.x).toBe((i % 4) * 3);
        expect(card.y).toBe(Math.floor(i / 4) * 2);
      });
      expect(findOverlaps(boxes)).toEqual([]);
    } finally {
      useDashboardStore.setState({ hidden: {} });
    }
  });
});
