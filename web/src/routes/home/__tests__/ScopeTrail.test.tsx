import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { TooltipProvider } from "@/components/ui/tooltip";
import type { ReactNode } from "react";
import type { ScopeType } from "@/config/roles";

/* ============================================================================
   Drill-down trail.

   The property that matters is THE SEAT IS THE CEILING: the root crumb is the
   seat's own scope and offers no way above it, because the server would refuse the
   query. A DIG must not be able to click up to "Karnataka".

   The second is that the trail only appears once you are actually below your own
   grain — otherwise an SP, whose district IS their ceiling, would get a permanent
   one-crumb bar that does nothing.
   ========================================================================== */

const seat = vi.hoisted(() => ({
  scopeType: "state" as ScopeType,
  districtId: null as number | null,
}));

vi.mock("@/hooks/useMyScope", () => ({
  useMyScope: () => ({ scopeType: seat.scopeType, districtId: seat.districtId }),
}));

vi.mock("@/hooks/useDistricts", () => ({
  useDistrictNamer: () => (id?: number | null) =>
    id == null ? "Unknown district" : ({ 4: "Mysuru", 9: "Belagavi" }[id] ?? `District ${id}`),
}));

import { ScopeTrail } from "@/routes/home/ScopeTrail";
import { useScopeStore } from "@/stores/useScopeStore";

function wrap(node: ReactNode) {
  return render(<TooltipProvider>{node}</TooltipProvider>);
}

describe("ScopeTrail", () => {
  beforeEach(() => {
    seat.scopeType = "state";
    seat.districtId = null;
    useScopeStore.setState({
      districtId: null, unitId: null, unitLabel: null, chosen: false,
    });
  });

  it("renders nothing until the user drills below their own grain", () => {
    // A DGP sitting at state level has not narrowed anything.
    const { container } = wrap(<ScopeTrail />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing for a seat whose district IS its ceiling", () => {
    // An SP pinned to Mysuru, with Mysuru selected, has not drilled — that is just
    // their jurisdiction. A one-crumb bar here would be noise.
    seat.scopeType = "district";
    seat.districtId = 4;
    useScopeStore.setState({ districtId: 4, chosen: true });

    const { container } = wrap(<ScopeTrail />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the ceiling and the drilled district once a DGP narrows", () => {
    useScopeStore.getState().setDistrictId(4);
    wrap(<ScopeTrail />);

    expect(screen.getByRole("button", { name: /Karnataka/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Mysuru" })).toBeInTheDocument();
  });

  it("clicking the ceiling clears the drill-down", () => {
    useScopeStore.getState().setDistrictId(4);
    wrap(<ScopeTrail />);

    fireEvent.click(screen.getByRole("button", { name: /Karnataka/ }));
    expect(useScopeStore.getState().districtId).toBeNull();
    expect(useScopeStore.getState().unitId).toBeNull();
  });

  it("adds a station crumb when drilled to a unit, and steps back to district", () => {
    useScopeStore.getState().drillToUnit(112, 4, "Jayanagar PS-1");
    wrap(<ScopeTrail />);

    expect(screen.getByText("Jayanagar PS-1")).toBeInTheDocument();

    // The district crumb becomes the way back up one level.
    fireEvent.click(screen.getByRole("button", { name: "Mysuru" }));
    expect(useScopeStore.getState().unitId).toBeNull();
    expect(useScopeStore.getState().districtId).toBe(4);
  });

  it("names a district-pinned seat's ceiling by its district, not its rank", () => {
    // "SP / District Command" does not say WHICH district; the name does.
    seat.scopeType = "district";
    seat.districtId = 4;
    useScopeStore.getState().drillToUnit(112, 4, "Jayanagar PS-1");
    wrap(<ScopeTrail />);

    expect(screen.getByRole("button", { name: /Mysuru/ })).toBeInTheDocument();
    expect(screen.queryByText(/SP \/ District Command/)).toBeNull();
  });

  it("never offers a way above the seat's own scope", () => {
    // A DIG drilled into one district: the ceiling returns them to the RANGE
    // (districtId null for a range seat), never to a state-wide view they cannot read.
    seat.scopeType = "range";
    seat.districtId = null;
    useScopeStore.getState().setDistrictId(9);
    wrap(<ScopeTrail />);

    const crumbs = screen.getAllByRole("button");
    // Only the ceiling and the drilled district — no third, higher level.
    expect(crumbs).toHaveLength(2);
    expect(screen.queryByText("Karnataka")).toBeNull();
  });

  it("drops the station when the district changes", () => {
    // Station 112 is not in district 9, so carrying it across would build a filter
    // that matches nothing.
    useScopeStore.getState().drillToUnit(112, 4, "Jayanagar PS-1");
    useScopeStore.getState().setDistrictId(9);
    expect(useScopeStore.getState().unitId).toBeNull();
    expect(useScopeStore.getState().unitLabel).toBeNull();
  });
});
