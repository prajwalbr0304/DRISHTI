import { describe, expect, it } from "vitest";
import { BOARDS } from "@/config/kpi/roleBoards";
import { BOARD_WIDGETS, hasWidget } from "@/routes/home/boardWidgets";
import type { ScopeType } from "@/config/roles";

/* ============================================================================
   The board specs declare widgets by id; `boardWidgets.tsx` maps ids to
   components. Those two files can drift, and the failure mode is silent — a board
   simply renders one panel fewer than it declares. Before the resolver existed,
   EVERY declared widget was ignored and the boards showed only their KPI band, so
   this is a drift that really happens.

   These tests make the contract enforceable in both directions.
   ========================================================================== */

const SCOPES = Object.keys(BOARDS) as ScopeType[];

describe("board widget resolver", () => {
  it("resolves every widget id declared by every board", () => {
    const missing: string[] = [];
    for (const scope of SCOPES) {
      for (const w of BOARDS[scope].widgets) {
        if (!hasWidget(w.id)) missing.push(`${scope}:${w.id}`);
      }
    }
    // A declared-but-unresolvable id is dropped at render, so without this the
    // panel just never appears.
    expect(missing).toEqual([]);
  });

  it("has no component that no board asks for", () => {
    const declared = new Set(
      SCOPES.flatMap((s) => BOARDS[s].widgets.map((w) => w.id)),
    );
    const orphans = Object.keys(BOARD_WIDGETS).filter((id) => !declared.has(id));
    // Not a correctness bug, but an orphan is either a spec that lost its widget
    // or dead code, and both are worth seeing.
    expect(orphans).toEqual([]);
  });

  it("gives every widget a footprint that fits the 12-column grid", () => {
    for (const scope of SCOPES) {
      for (const w of BOARDS[scope].widgets) {
        expect(w.w, `${scope}:${w.id} width`).toBeGreaterThan(0);
        expect(w.w, `${scope}:${w.id} width`).toBeLessThanOrEqual(12);
        // minH is 4 in RoleBoard, so a shorter declared height would be silently
        // grown by the grid and the board would not look as specced.
        expect(w.h, `${scope}:${w.id} height`).toBeGreaterThanOrEqual(4);
      }
    }
  });

  it("declares each widget at most once per board", () => {
    for (const scope of SCOPES) {
      const ids = BOARDS[scope].widgets.map((w) => w.id);
      // Duplicate keys would collide in the grid's layout map and one tile would
      // vanish, since DashboardGrid keys tiles by id.
      expect(new Set(ids).size, `${scope} has duplicate widget ids`).toBe(ids.length);
    }
  });

  it("gives the unposted-seat board no widgets to render", () => {
    // An unresolved seat has empty scope sets server-side, so every widget would
    // render an empty frame. The board says why instead.
    expect(BOARDS.unresolved.widgets).toEqual([]);
    expect(BOARDS.unresolved.order).toEqual([]);
  });

  it("gives every posted board at least one widget", () => {
    for (const scope of SCOPES) {
      if (scope === "unresolved") continue;
      expect(BOARDS[scope].widgets.length, `${scope} has no widgets`).toBeGreaterThan(0);
    }
  });
});
