import { describe, expect, it } from "vitest";
import type { Layouts } from "react-grid-layout";
import { mergeLayouts } from "@/stores/useDashboardStore";

/* ============================================================================
   Layout persistence is ADDITIVE (Task 1). A saved arrangement is a snapshot of
   the tiles that existed when the user last dragged one, so every tile added in
   code afterwards must fall back to its declared geometry instead of letting
   react-grid-layout invent a position for it.
   ========================================================================== */

/** Two declared rows: three cards the user has seen, one added later. */
const defaults: Layouts = {
  lg: [
    { i: "kpi-a", x: 0, y: 0, w: 3, h: 2, minW: 2, minH: 2 },
    { i: "kpi-b", x: 3, y: 0, w: 3, h: 2, minW: 2, minH: 2 },
    { i: "kpi-new", x: 6, y: 0, w: 3, h: 2, minW: 2, minH: 2 },
    { i: "widget", x: 0, y: 2, w: 12, h: 7, minW: 4, minH: 4 },
  ],
  sm: [
    { i: "kpi-a", x: 0, y: 0, w: 6, h: 2, minW: 1, minH: 2 },
    { i: "kpi-b", x: 0, y: 2, w: 6, h: 2, minW: 1, minH: 2 },
    { i: "kpi-new", x: 0, y: 4, w: 6, h: 2, minW: 1, minH: 2 },
    { i: "widget", x: 0, y: 6, w: 6, h: 7, minW: 1, minH: 4 },
  ],
};

const item = (layouts: Layouts, breakpoint: string, key: string) =>
  layouts[breakpoint].find((l) => l.i === key);

describe("mergeLayouts", () => {
  it("returns the declared defaults untouched when nothing is saved", () => {
    expect(mergeLayouts(undefined, defaults)).toBe(defaults);
  });

  it("keeps saved geometry for known tiles and declared geometry for new ones", () => {
    // The user swapped kpi-a and kpi-b and widened the widget. kpi-new did not
    // exist yet, so their snapshot has no entry for it.
    const saved: Layouts = {
      lg: [
        { i: "kpi-a", x: 3, y: 0, w: 3, h: 2 },
        { i: "kpi-b", x: 0, y: 0, w: 6, h: 3 },
        { i: "widget", x: 0, y: 3, w: 12, h: 9 },
      ],
    };

    const merged = mergeLayouts(saved, defaults);

    // saved positions survive
    expect(item(merged, "lg", "kpi-a")).toMatchObject({ x: 3, y: 0, w: 3, h: 2 });
    expect(item(merged, "lg", "kpi-b")).toMatchObject({ x: 0, y: 0, w: 6, h: 3 });
    expect(item(merged, "lg", "widget")).toMatchObject({ x: 0, y: 3, w: 12, h: 9 });
    // the tile added in code lands where it declares, not where RGL would guess
    expect(item(merged, "lg", "kpi-new")).toMatchObject({ x: 6, y: 0, w: 3, h: 2 });
  });

  it("carries min constraints from code, not from the saved snapshot", () => {
    const saved: Layouts = {
      // a snapshot taken while the widget could still be shrunk to 2x2
      lg: [{ i: "widget", x: 0, y: 2, w: 2, h: 2, minW: 1, minH: 1 }],
    };

    const widget = item(mergeLayouts(saved, defaults), "lg", "widget");

    expect(widget).toMatchObject({ minW: 4, minH: 4 });
    // and a stale snapshot cannot pin the tile below its current minimum
    expect(widget?.w).toBe(4);
    expect(widget?.h).toBe(4);
  });

  it("drops saved tiles that no longer exist in code", () => {
    const saved: Layouts = {
      lg: [
        { i: "kpi-a", x: 0, y: 0, w: 3, h: 2 },
        { i: "kpi-retired", x: 9, y: 0, w: 3, h: 2 },
      ],
    };

    const merged = mergeLayouts(saved, defaults);

    expect(merged.lg.map((l) => l.i)).toEqual(["kpi-a", "kpi-b", "kpi-new", "widget"]);
    expect(item(merged, "lg", "kpi-retired")).toBeUndefined();
  });

  it("falls back to defaults for breakpoints the user never arranged", () => {
    const saved: Layouts = { lg: [{ i: "kpi-a", x: 9, y: 0, w: 3, h: 2 }] };

    const merged = mergeLayouts(saved, defaults);

    expect(merged.sm).toEqual(defaults.sm);
    // and every declared breakpoint is present in the result
    expect(Object.keys(merged).sort()).toEqual(Object.keys(defaults).sort());
  });
});
