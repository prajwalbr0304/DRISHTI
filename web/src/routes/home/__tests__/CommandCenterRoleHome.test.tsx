import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RoleProvider } from "@/providers/RoleProvider";
import { TooltipProvider } from "@/components/ui/tooltip";
import type { ScopeType, UserRole } from "@/config/roles";
import { boardKpis } from "@/config/kpi/roleBoards";

/* ============================================================================
   The Command Center renders ONE registry-composed board, selected by the seat's
   SCOPE TYPE rather than its role.

   That distinction is the point of the six-role model: `senior_command` is an
   ADGP wing board when wing-scoped and a DIG range board when range-scoped, and
   `district_command` is an SP or a CP board. A role-keyed board cannot tell those
   pairs apart, so every case here fixes a scope type and asserts what appears.

   The cards are asserted against `boardKpis` rather than against a hard-coded
   list: the test should verify the board renders what the registry says, not
   duplicate the registry's contents and then drift from it.
   ========================================================================== */

const seat = vi.hoisted(() => ({
  scopeType: "unresolved" as ScopeType,
  wingId: null as number | null,
  loading: false,
}));

vi.mock("@/hooks/useMyScope", () => ({
  useSeatScopeType: () => seat.scopeType,
  useMyScope: () => ({
    districtId: null, scopeLevel: "state", source: "role-default",
    loading: seat.loading, scopeType: seat.scopeType, districtIds: null,
    wingId: seat.wingId, rangeId: null, crimeHeadIds: null,
    aggregateOnly: false, isLeadInvestigator: false,
  }),
}));

// Every KPI source is stubbed: this is about which cards a board composes, not
// about what any endpoint returns.
vi.mock("@/routes/home/useKpiValues", () => ({
  useKpiValues: () => ({
    resolve: (spec: { id: string; label: string }) => ({
      label: spec.label,
      value: 1,
      "data-testid": `kpi-${spec.id}`,
    }),
  }),
}));

const uiGrants = vi.hoisted(() => ({ items: [] as Record<string, unknown>[] }));

vi.mock("@/api", () => ({
  api: {
    org: { wings: () => Promise.resolve({ total: 0, items: [] }) },
    adminConsole: {
      uiVisibility: () => Promise.resolve({
        total: uiGrants.items.length, items: uiGrants.items,
        enforcement: "Presentation only.",
      }),
    },
  },
}));

/* Widgets are stubbed to a marker div. This suite is about board COMPOSITION —
   which cards and panels a scope type gets — and the real panels would drag
   MapLibre, deck.gl and five endpoints into jsdom to prove a point about layout.
   Each widget's own behaviour is covered where it lives; that every declared id
   resolves to a component is covered in boardWidgets.test.tsx. */
vi.mock("@/routes/home/boardWidgets", async () => {
  const { BOARDS } = await import("@/config/kpi/roleBoards");
  const ids = new Set(
    Object.values(BOARDS).flatMap((b) => b.widgets.map((w) => w.id)),
  );
  const stub = (id: string) => ({ label }: { label: string }) => (
    <div data-testid={`widget-${id}`}>{label}</div>
  );
  const map: Record<string, unknown> = {};
  for (const id of ids) map[id] = stub(id);
  return { BOARD_WIDGETS: map, hasWidget: (id: string) => ids.has(id) };
});

import { CommandCenter } from "@/routes/CommandCenter";
import { BOARDS } from "@/config/kpi/roleBoards";

function mountAs(role: UserRole, scope: ScopeType, wingId: number | null = null) {
  seat.scopeType = scope;
  seat.wingId = wingId;
  seat.loading = false;
  localStorage.setItem("drishti.role", role);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={["/command"]}>
      <QueryClientProvider client={qc}>
        {/* Widget's overflow menu uses a tooltip, which throws outside a provider. */}
        <TooltipProvider>
          <RoleProvider>
            <CommandCenter />
          </RoleProvider>
        </TooltipProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("CommandCenter board composition by scope type", () => {
  beforeEach(() => {
    localStorage.clear();
    seat.scopeType = "unresolved";
    seat.wingId = null;
    seat.loading = false;
    uiGrants.items = [];
  });

  it.each<[UserRole, ScopeType]>([
    ["dgp_state_command", "state"],
    ["senior_command", "range"],
    ["district_command", "district"],
    ["district_command", "commissionerate"],
    ["sho", "station"],
    ["investigating_officer", "assigned_case"],
  ])("renders the %s board at %s scope with its registry cards", (role, scope) => {
    mountAs(role, scope);
    const expected = boardKpis(scope, null);
    expect(expected.length).toBeGreaterThan(0);
    // The first card's label is enough to prove the registry drove the board;
    // the per-scope card SETS are asserted in the registry test below.
    expect(screen.getByText(expected[0].label)).toBeInTheDocument();
  });

  /* The board used to declare widgets and render only its KPI band, so every
     panel below the cards was silently missing. These two cases pin the fix. */
  it.each<[UserRole, ScopeType]>([
    ["dgp_state_command", "state"],
    ["senior_command", "wing"],
    ["senior_command", "range"],
    ["district_command", "district"],
    ["district_command", "commissionerate"],
    ["sho", "station"],
    ["investigating_officer", "assigned_case"],
    ["system_admin", "platform"],
  ])("renders every widget the %s board declares at %s scope", (role, scope) => {
    mountAs(role, scope);
    const declared = BOARDS[scope].widgets;
    expect(declared.length).toBeGreaterThan(0);
    for (const w of declared) {
      expect(
        screen.getByTestId(`widget-${w.id}`),
        `${scope} board declares ${w.id} but did not render it`,
      ).toBeInTheDocument();
    }
  });

  it("gives a range seat range-level panels and a station seat station-level ones", () => {
    // Same assertion as the card sets, one level up: the panels differ by scope
    // too, and a DIG comparing districts is a different panel from an SHO
    // looking at one station's officer load.
    //
    // Unmounted between mounts — `render` appends rather than replaces, so both
    // boards would otherwise be in the DOM at once and every negative assertion
    // here would be meaningless.
    const range = mountAs("senior_command", "range");
    expect(screen.getByTestId("widget-district-league")).toBeInTheDocument();
    expect(screen.queryByTestId("widget-officer-load")).toBeNull();
    range.unmount();

    mountAs("sho", "station");
    expect(screen.getByTestId("widget-officer-load")).toBeInTheDocument();
    expect(screen.queryByTestId("widget-district-league")).toBeNull();
  });

  it("renders no widgets for an unposted seat", () => {
    mountAs("sho", "unresolved");
    // Every widget would draw an empty frame, since the server refuses every
    // scoped query for a seat with no posting.
    expect(screen.queryAllByTestId(/^widget-/)).toHaveLength(0);
  });

  /* Admin UI-visibility switches. The board is the only place that can honour a
     board-level override, and a KPI card turned off must actually disappear —
     otherwise the console offers switches that do nothing. */
  it("says so when an administrator has turned the whole board off", async () => {
    uiGrants.items = [{
      id: 1, role_name: "district_command", scope_type: null,
      element_kind: "board", element_id: "district", enabled: false,
      reason: "under review for the new FIR workflow",
      updated_by: "platform.admin", updated_at: null,
    }];
    mountAs("district_command", "district");

    // An empty grid would read as missing data. The seat is fine; someone
    // switched the board off, and the recorded reason is the useful part.
    expect(await screen.findByText(/is turned off/i)).toBeInTheDocument();
    expect(screen.getByText(/under review for the new FIR workflow/)).toBeInTheDocument();
    expect(screen.queryAllByTestId(/^widget-/)).toHaveLength(0);
  });

  it("hides a KPI card an administrator switched off, and keeps the rest", async () => {
    const cards = boardKpis("district", null);
    const target = cards[0];

    uiGrants.items = [{
      id: 2, role_name: "district_command", scope_type: null,
      element_kind: "kpi", element_id: target.id, enabled: false,
      reason: null, updated_by: "platform.admin", updated_at: null,
    }];
    mountAs("district_command", "district");

    // Asserted by label, since KpiCard renders the label rather than forwarding
    // arbitrary DOM attributes.
    await waitFor(() => expect(screen.queryByText(target.label)).toBeNull());
    // Only that one: a single override must not blank the band.
    expect(screen.getByText(cards[1].label)).toBeInTheDocument();
  });

  it("leaves the board intact when the visibility service returns nothing", async () => {
    // A presentation-only control with no overrides — and equally, one that could
    // not be read at all — must not blank the workspace. Showing too much is the
    // right failure here; showing nothing would look like a data outage.
    uiGrants.items = [];
    mountAs("district_command", "district");
    const cards = boardKpis("district", null);
    expect(await screen.findByText(cards[0].label)).toBeInTheDocument();
  });

  // The two pairs a role-keyed board could not distinguish.
  it("gives a wing seat a different card set than a range seat", () => {
    const wing = boardKpis("wing", "TRF").map((k) => k.id);
    const range = boardKpis("range", null).map((k) => k.id);
    expect(wing).not.toEqual(range);
    // Traffic-wing cards exist for the wing and not for the range.
    expect(wing).toContain("kpi-traffic-incidents");
    expect(range).not.toContain("kpi-traffic-incidents");
  });

  it("gives a district and a commissionerate seat the same job", () => {
    expect(boardKpis("district", null).map((k) => k.id))
      .toEqual(boardKpis("commissionerate", null).map((k) => k.id));
  });

  // An unposted seat has no jurisdiction. Falling back to a state-wide board
  // would show the whole force to a seat the server refuses every scoped query
  // for, so the board must decline to render figures.
  it("refuses to render figures for an unposted seat", () => {
    mountAs("sho", "unresolved");
    expect(boardKpis("unresolved", null)).toHaveLength(0);
    expect(screen.getByText(/no posting on record/i)).toBeInTheDocument();
  });

  it("shows a skeleton while the seat scope is still resolving", () => {
    seat.loading = true;
    seat.scopeType = "unresolved";
    localStorage.setItem("drishti.role", "district_command");
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <MemoryRouter initialEntries={["/command"]}>
        <QueryClientProvider client={qc}>
          <RoleProvider>
            <CommandCenter />
          </RoleProvider>
        </QueryClientProvider>
      </MemoryRouter>,
    );
    // Neither the unposted notice nor a card band: the answer is not known yet.
    expect(screen.queryByText(/no posting on record/i)).toBeNull();
  });
});

describe("registry card sets per scope", () => {
  it("excludes metrics that are undefined at a scope rather than showing zero", () => {
    const station = boardKpis("station", null).map((k) => k.id);
    // Load imbalance across ONE station is not 1.0, it has no meaning.
    expect(station).not.toContain("kpi-imbalance");
    expect(station).not.toContain("kpi-stations");
    // Forecast grain is the district, so there is no station-level prediction.
    expect(station).not.toContain("kpi-predicted");
    // And the district board, which does span stations, keeps them.
    const district = boardKpis("district", null).map((k) => k.id);
    expect(district).toContain("kpi-imbalance");
    expect(district).toContain("kpi-predicted");
  });

  it("keeps individual-person cards off the aggregate-only boards", () => {
    for (const scope of ["state", "wing"] as ScopeType[]) {
      expect(boardKpis(scope, "INT").map((k) => k.id)).not.toContain("kpi-poi");
    }
    expect(boardKpis("district", null).map((k) => k.id)).toContain("kpi-poi");
  });

  it("restricts wing-only cards to the wings that own them", () => {
    expect(boardKpis("wing", "ISC").map((k) => k.id)).toContain("kpi-flagged-txn");
    expect(boardKpis("wing", "TRF").map((k) => k.id)).not.toContain("kpi-flagged-txn");
  });

  it("gives the IO board personal cards and not force-wide accountability", () => {
    const io = boardKpis("assigned_case", null).map((k) => k.id);
    expect(io).toContain("kpi-my-open");
    expect(io).not.toContain("kpi-imbalance");
    expect(io).not.toContain("kpi-stations");
  });
});
