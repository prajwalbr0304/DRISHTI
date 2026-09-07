import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { KpiCard } from "@/components/dashboard/KpiCard";
import { ApiError } from "@/api/contracts";
import { TooltipProvider } from "@/components/ui/tooltip";

/* ============================================================================
   A KPI card has FOUR ways of not showing a number, and they are four different
   facts about the world:

     loading      still in flight;
     pending      no endpoint serves this card yet;
     error        the source was asked and refused or failed;
     null value   the source answered and has no number.

   The error case used to render the same bare em-dash as a null value, which is
   the one confusion this card must not create: an unavailable source is a fault
   to chase, an empty measurement is not. On the live platform board that made
   two 503s (/geo/hotspots, /geo/alerts) and a 504 (/forecast/backtest) look
   exactly like "nothing was measured".

   `docs/production-role-dashboard-plan.md` §3.3 states the rule and its
   acceptance test 16 requires the states stay distinguishable.
   ========================================================================== */

const wrap = (ui: React.ReactElement) => render(<TooltipProvider>{ui}</TooltipProvider>);

describe("KpiCard — distinguishing an absent number from a broken source", () => {
  it("labels a failed source unavailable rather than showing a bare dash", () => {
    wrap(
      <KpiCard
        label="Hotspots"
        error={new ApiError("Service Unavailable", 503, {
          detail: "hotspots model was generated under a stale analytics policy",
        })}
        hint="Spatial clusters detected for the window."
      />,
    );

    expect(screen.getByText("unavailable")).toBeInTheDocument();
    // and it is not mistaken for the "not built yet" state
    expect(screen.queryByText("awaiting API")).not.toBeInTheDocument();
  });

  it("keeps a bare dash for a source that answered with no number", () => {
    wrap(<KpiCard label="Hotspots" value={null} hint="No clusters." />);

    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.queryByText("unavailable")).not.toBeInTheDocument();
    expect(screen.queryByText("awaiting API")).not.toBeInTheDocument();
  });

  it("still marks an unbound card as awaiting its API", () => {
    wrap(<KpiCard label="Evidence pending" pending pendingNote="No endpoint yet." />);

    expect(screen.getByText("awaiting API")).toBeInTheDocument();
    expect(screen.queryByText("unavailable")).not.toBeInTheDocument();
  });

  it("renders a real zero as a measurement, not as an absence", () => {
    wrap(<KpiCard label="Critical alerts" value={0} hint="Escalate-now queue." />);

    expect(screen.getByText("0")).toBeInTheDocument();
    expect(screen.queryByText("unavailable")).not.toBeInTheDocument();
  });

  it("does not attach a unit to a missing number", () => {
    wrap(<KpiCard label="80% interval coverage" value={null} unit="%" />);

    // "—%" would read as a percentage that was measured and came back empty.
    expect(screen.queryByText("%")).not.toBeInTheDocument();
  });

  it("carries the server's reason in the card's hint", async () => {
    wrap(
      <KpiCard
        label="Critical alerts"
        error={new ApiError("Service Unavailable", 503, {
          detail: "regenerate the artifact before serving it",
        })}
      />,
    );

    // The reason is what turns "unavailable" into something actionable rather
    // than sending the reader to the network tab.
    const hint = screen.getByRole("button", { name: /more info/i });
    expect(hint).toBeInTheDocument();
  });
});
