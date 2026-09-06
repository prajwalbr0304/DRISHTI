import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import type { SeatOut } from "@/api/endpoints/org";

/* ============================================================================
   The seat picker exists because a role no longer identifies a seat: there are
   ~11,825 provisioned ones. These tests pin the two behaviours that make it
   usable at that size — large tiers require a search rather than trying to render
   themselves, and small tiers list immediately — plus the property that keeps it
   honest: picking a seat selects a view, it does not assert a jurisdiction.
   ========================================================================== */

const seatsCall = vi.hoisted(() => ({ calls: [] as Record<string, unknown>[] }));

function seat(over: Partial<SeatOut> = {}): SeatOut {
  return {
    user_id: 1, username: "sp.mysuru", display_name: "SP Anand Kumar",
    role: "district_command", scope_type: "district",
    scope_label: "SP / District Command", posting_label: "Mysuru District",
    rank_label: "Superintendent of Police", designation_label: "Superintendent of Police",
    is_lead_investigator: false, is_active: true,
    wing_id: null, range_id: null, district_id: 4, unit_id: null,
    ...over,
  };
}

vi.mock("@/api", () => ({
  api: {
    org: {
      seats: (params: Record<string, unknown>) => {
        seatsCall.calls.push(params);
        // The counts probe (page_size 1) vs a real listing.
        if (params.page_size === 1) {
          return Promise.resolve({
            total: 11825, page: 1, page_size: 1, items: [],
            scope_type_counts: {
              state: 2, wing: 9, range: 8, district: 35,
              commissionerate: 6, station: 1001, assigned_case: 10761, platform: 2,
            },
          });
        }
        const scope = params.scope_type;
        let items: SeatOut[];
        if (scope === "station") {
          items = [seat({
            user_id: 2, username: "sho.101", display_name: "PSI Ramesh",
            role: "sho", scope_type: "station",
            scope_label: "SHO / Station",
            posting_label: "Jayanagar PS-1, Bengaluru City",
            rank_label: "Police Sub-Inspector", is_lead_investigator: true,
            district_id: 1, unit_id: 101,
          })];
        } else if (scope === "assigned_case") {
          // A lead IO and an assisting constable, both at assigned_case scope and
          // both posted to the same station — the pair the badge exists to tell
          // apart, since nothing else on the row differs.
          items = [
            seat({
              user_id: 3, username: "io.852", display_name: "PSI Kavya",
              role: "investigating_officer", scope_type: "assigned_case",
              scope_label: "Investigating Officer",
              posting_label: "Jayanagar PS-1, Bengaluru City",
              rank_label: "Police Sub-Inspector", is_lead_investigator: true,
              district_id: 1, unit_id: 101,
            }),
            seat({
              user_id: 4, username: "io.853", display_name: "PC Manjunath",
              role: "investigating_officer", scope_type: "assigned_case",
              scope_label: "Investigating Officer",
              posting_label: "Jayanagar PS-1, Bengaluru City",
              rank_label: "Police Constable", is_lead_investigator: false,
              district_id: 1, unit_id: 101,
            }),
          ];
        } else {
          items = [seat()];
        }
        return Promise.resolve({
          total: items.length, page: 1, page_size: 60, items,
          scope_type_counts: {},
        });
      },
    },
  },
}));

import { SeatPicker } from "@/routes/login/SeatPicker";
import { useSeatStore } from "@/stores/useSeatStore";

function wrap(node: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>);
}

describe("SeatPicker", () => {
  beforeEach(() => {
    seatsCall.calls = [];
    useSeatStore.getState().clearSeat();
    localStorage.clear();
  });

  it("lists a small tier immediately without requiring a search", async () => {
    wrap(<SeatPicker onPick={() => {}} />);
    // District command is 35 seats — browsable.
    expect(await screen.findByText("SP Anand Kumar")).toBeInTheDocument();
  });

  it("refuses to list a large tier until a search is typed", async () => {
    wrap(<SeatPicker onPick={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: /Station \(SHO\)/ }));

    // 1,001 SHO seats cannot be browsed, so nothing is fetched and the picker
    // says what to do instead of rendering a thousand rows.
    expect(await screen.findByText(/Type at least two characters/i)).toBeInTheDocument();
    await waitFor(() => {
      const listed = seatsCall.calls.filter(
        (c) => c.scope_type === "station" && c.page_size !== 1);
      expect(listed).toHaveLength(0);
    });
  });

  it("searches a large tier once enough characters are typed", async () => {
    wrap(<SeatPicker onPick={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: /Station \(SHO\)/ }));
    fireEvent.change(screen.getByLabelText(/Search seats/i), {
      target: { value: "Jayanagar" },
    });
    expect(await screen.findByText("PSI Ramesh")).toBeInTheDocument();
    // Searched by posting, which is how someone knows the seat they want.
    expect(screen.getByText(/Jayanagar PS-1, Bengaluru City/)).toBeInTheDocument();
  });

  it("distinguishes a lead IO from an assisting officer at the same posting", async () => {
    wrap(<SeatPicker onPick={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: /Investigating Officer/ }));
    fireEvent.change(screen.getByLabelText(/Search seats/i), {
      target: { value: "Jayanagar" },
    });
    await screen.findByText("PSI Kavya");
    expect(screen.getByText("PC Manjunath")).toBeInTheDocument();

    // Both hold scope_type=assigned_case at the SAME station, so scope and posting
    // are identical on both rows. Only one may be the officer of record, and the
    // badge is the sole signal — exactly one, not both.
    expect(screen.getAllByText("Lead IO")).toHaveLength(1);
  });

  it("does not badge an SHO seat as lead IO", async () => {
    // An SHO leads by definition, so the badge would be noise there. It is only
    // informative among IO seats, where it separates lead from assisting.
    wrap(<SeatPicker onPick={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: /Station \(SHO\)/ }));
    fireEvent.change(screen.getByLabelText(/Search seats/i), {
      target: { value: "Jayanagar" },
    });
    await screen.findByText("PSI Ramesh");
    expect(screen.queryByText("Lead IO")).toBeNull();
  });

  it("hands back the posting, not just the role, when a seat is picked", async () => {
    const picked: unknown[] = [];
    wrap(<SeatPicker onPick={(s) => picked.push(s)} />);
    fireEvent.click(await screen.findByText("SP Anand Kumar"));

    expect(picked).toHaveLength(1);
    expect(picked[0]).toMatchObject({
      username: "sp.mysuru",
      role: "district_command",
      scopeType: "district",
      postingLabel: "Mysuru District",
    });
  });

  it("states that choosing a seat cannot grant a jurisdiction", async () => {
    wrap(<SeatPicker onPick={() => {}} />);
    expect(
      await screen.findByText(/cannot grant\s+access to a district/i),
    ).toBeInTheDocument();
  });
});
