import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { TooltipProvider } from "@/components/ui/tooltip";
import type { ReactNode } from "react";
import type { SeatProfile } from "@/api/endpoints/adminConsole";
import type { SeatOut } from "@/api/endpoints/org";

/* ============================================================================
   Per-seat profile editing.

   The behaviour worth protecting is PARTIAL WRITES. Only the fields the admin
   actually touched are sent, because the server writes only what it receives. If
   the form posted every field, editing a display name would rewrite the rank,
   designation and phone number with whatever happened to be on screen — and blank
   any of them the response had returned as null.

   Also pinned: role and scope_type are shown but not editable. They are
   provisioning decisions with their own audited endpoints, and accepting them here
   would let a name change quietly move a seat's jurisdiction.
   ========================================================================== */

const sent = vi.hoisted(() => ({ bodies: [] as Record<string, unknown>[] }));

const PROFILE: SeatProfile = {
  user_id: 42, username: "sp.mysuru", display_name: "SP Anand Kumar",
  role: "district_command", scope_type: "district",
  email: "sp.mysuru@ksp.gov.in", phone: "+91 80 1234 5678",
  rank_label: "Superintendent of Police",
  designation_label: "Superintendent of Police",
  posting_label: "Mysuru District", preferred_language: "en",
  notes: null, is_lead_investigator: false, is_active: true,
  updated_by: null,
};

function seat(over: Partial<SeatOut> = {}): SeatOut {
  return {
    user_id: 42, username: "sp.mysuru", display_name: "SP Anand Kumar",
    role: "district_command", scope_type: "district",
    scope_label: "SP / District Command", posting_label: "Mysuru District",
    rank_label: "Superintendent of Police",
    designation_label: "Superintendent of Police",
    is_lead_investigator: false, is_active: true,
    wing_id: null, range_id: null, district_id: 4, unit_id: null,
    ...over,
  };
}

vi.mock("@/api", () => ({
  api: {
    org: {
      seats: () => Promise.resolve({
        total: 1, page: 1, page_size: 40, items: [seat()],
        scope_type_counts: { district: 35, station: 1001, assigned_case: 10761 },
      }),
    },
    adminConsole: {
      seatProfile: () => Promise.resolve(PROFILE),
      updateSeatProfile: (_id: number, body: Record<string, unknown>) => {
        sent.bodies.push(body);
        return Promise.resolve({ ...PROFILE, ...body });
      },
    },
  },
}));

import { SeatProfilePanel } from "@/routes/admin/SeatProfilePanel";

function wrap(node: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <TooltipProvider>{node}</TooltipProvider>
    </QueryClientProvider>,
  );
}

async function openProfile() {
  wrap(<SeatProfilePanel />);
  fireEvent.click(await screen.findByRole("button", { name: /^Edit$/ }));
  await screen.findByText(/Profile — SP Anand Kumar/);
}

describe("SeatProfilePanel", () => {
  beforeEach(() => { sent.bodies = []; });

  it("sends only the fields that were edited", async () => {
    await openProfile();

    fireEvent.change(screen.getByLabelText("Notes"), {
      target: { value: "on deputation until March" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Save profile/i }));

    await waitFor(() => expect(sent.bodies).toHaveLength(1));
    // Exactly one key. Posting the whole form would rewrite rank, phone and
    // designation with whatever was on screen, and blank the ones that were null.
    expect(Object.keys(sent.bodies[0])).toEqual(["notes"]);
    expect(sent.bodies[0].notes).toBe("on deputation until March");
  });

  it("sends several fields when several were edited", async () => {
    await openProfile();

    fireEvent.change(screen.getByLabelText("Display name"), {
      target: { value: "SP A. Kumar" },
    });
    fireEvent.change(screen.getByLabelText("Phone"), {
      target: { value: "+91 80 9999 0000" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Save profile/i }));

    await waitFor(() => expect(sent.bodies).toHaveLength(1));
    expect(Object.keys(sent.bodies[0]).sort()).toEqual(["display_name", "phone"]);
  });

  it("keeps Save disabled until something changes", async () => {
    await openProfile();
    // Nothing edited yet, so there is nothing to write.
    expect(screen.getByRole("button", { name: /Save profile/i })).toBeDisabled();

    // Regex, not an exact string: Field folds its hint into the label's text.
    fireEvent.change(screen.getByLabelText(/^Rank/), {
      target: { value: "Deputy Inspector General" },
    });
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Save profile/i })).toBeEnabled());
  });

  it("discards edits without sending anything", async () => {
    await openProfile();
    fireEvent.change(screen.getByLabelText("Notes"), { target: { value: "typo" } });
    fireEvent.click(screen.getByRole("button", { name: /Discard/i }));

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Save profile/i })).toBeDisabled());
    expect(sent.bodies).toHaveLength(0);
  });

  it("shows role and scope but offers no way to change them", async () => {
    await openProfile();

    // Visible, so the admin knows which seat this is. (The scope label also
    // appears on the tier buttons above, hence getAllByText.)
    expect(screen.getByText("district_command")).toBeInTheDocument();
    expect(screen.getAllByText("SP / District Command").length).toBeGreaterThan(0);

    // …but not editable. Moving a seat between roles or jurisdictions is a
    // provisioning action with its own audited endpoint, and this form must not
    // become a second way in.
    expect(screen.queryByLabelText(/^Role/)).toBeNull();
    expect(screen.queryByLabelText(/^Scope/)).toBeNull();
    expect(screen.queryByLabelText(/^District/)).toBeNull();
    expect(screen.queryByLabelText(/^Unit/)).toBeNull();
  });

  it("edits the lead-investigator flag as an assignment, not a rank", async () => {
    await openProfile();

    const box = screen.getByRole("checkbox", {
      name: /investigating officer of record/i,
    });
    expect(box).not.toBeChecked();
    fireEvent.click(box);
    fireEvent.click(screen.getByRole("button", { name: /Save profile/i }));

    await waitFor(() => expect(sent.bodies).toHaveLength(1));
    expect(sent.bodies[0]).toEqual({ is_lead_investigator: true });
  });

  it("reports how many fields will be written", async () => {
    await openProfile();
    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "new@ksp.gov.in" },
    });
    expect(await screen.findByText(/1 field\(s\) changed/)).toBeInTheDocument();
  });
});
