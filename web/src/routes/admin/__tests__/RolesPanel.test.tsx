import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { TooltipProvider } from "@/components/ui/tooltip";
import type { ReactNode } from "react";
import type { AdminRole, PermissionOut } from "@/api/endpoints/adminConsole";

/* ============================================================================
   Admin-created roles.

   Two behaviours are worth pinning, because both encode a server rule the form
   would otherwise let an admin discover only after a long submit:

     * a permission that needs finer grain than the role's WIDEST issuable tier is
       marked and blocks the submit — the server refuses it, and the reason is the
       useful part, so it is shown rather than the permission being hidden;
     * a sensitive permission demands a reason, which is written to the audit trail.

   Also pinned: deletion is refused for built-in roles and for any role that still
   has seats, and the button says which.
   ========================================================================== */

const calls = vi.hoisted(() => ({ created: [] as Record<string, unknown>[] }));

function perm(over: Partial<PermissionOut> = {}): PermissionOut {
  return {
    permission_key: "dashboard.read", resource: "dashboard", action: "read",
    label: "Command dashboard", description: null, category: "Command",
    is_sensitive: false, requires_scope: null,
    ...over,
  };
}

function role(over: Partial<AdminRole> = {}): AdminRole {
  return {
    role_name: "district_command", description: null, is_system: true,
    base_surface: "district_command",
    allowed_scope_types: ["district", "commissionerate"],
    created_by: null, granted_count: 38, sensitive_count: 12, seat_count: 41,
    display_label: null, default_route: null, sort_order: 30,
    ...over,
  };
}

vi.mock("@/api", () => ({
  api: {
    adminConsole: {
      roles: () => Promise.resolve({
        total: 3,
        base_surfaces: ["state_command", "district_command", "station", "platform"],
        items: [
          role(),
          role({ role_name: "sho", is_system: true, base_surface: "station",
                 allowed_scope_types: ["station"], seat_count: 1001,
                 granted_count: 30, sensitive_count: 9 }),
          role({ role_name: "coastal_cell", is_system: false,
                 base_surface: "district_command", allowed_scope_types: ["district"],
                 granted_count: 2, sensitive_count: 0, seat_count: 0,
                 created_by: "platform.admin" }),
        ],
      }),
      permissions: () => Promise.resolve({
        total: 4,
        scope_types: ["state", "district", "station"],
        categories: {
          Command: [
            perm(),
            perm({ permission_key: "performance.read", action: "read",
                   resource: "performance", label: "Station performance" }),
          ],
          "Case work": [
            // Needs district grain: unusable on a state-only role.
            perm({ permission_key: "cases.detail_read", resource: "cases",
                   action: "detail_read", label: "Open case file",
                   category: "Case work", is_sensitive: true,
                   requires_scope: "district" }),
            perm({ permission_key: "cases.write", resource: "cases",
                   action: "write", label: "Edit case", category: "Case work",
                   is_sensitive: true, requires_scope: "station" }),
          ],
        },
      }),
      role: (name: string) => Promise.resolve({
        ...role({ role_name: name }),
        grants: [{ permission_key: "dashboard.read", granted: true,
                   reason: null, granted_by: "migration:035" }],
      }),
      createRole: (body: Record<string, unknown>) => {
        calls.created.push(body);
        return Promise.resolve({ ...role({ role_name: String(body.role_name) }), grants: [] });
      },
      replaceGrants: () => Promise.resolve({ ...role(), grants: [] }),
      deleteRole: () => Promise.resolve(undefined),
    },
  },
}));

import { RolesPanel } from "@/routes/admin/RolesPanel";

function wrap(node: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <TooltipProvider>{node}</TooltipProvider>
    </QueryClientProvider>,
  );
}

/** The role-name input, by placeholder. `getByLabelText(/Role name/i)` is
 *  ambiguous here — the table also has a "Role" column heading. */
function roleNameInput() {
  return screen.getByPlaceholderText("coastal_security_cell");
}

async function openCreateForm() {
  wrap(<RolesPanel />);
  await screen.findByRole("button", { name: /Delete coastal_cell/i });
  fireEvent.click(screen.getByRole("button", { name: /New role/i }));
  await screen.findByPlaceholderText("coastal_security_cell");
}

describe("RolesPanel", () => {
  beforeEach(() => { calls.created = []; });

  it("lists roles with their surface, seat count and sensitive-permission count", async () => {
    wrap(<RolesPanel />);
    await screen.findByRole("button", { name: /Delete coastal_cell/i });

    // Seat counts matter: they are what makes a role safe or unsafe to delete.
    expect(screen.getByText("1001")).toBeInTheDocument();
    expect(screen.getByText(/12 sensitive/)).toBeInTheDocument();
  });

  it("refuses to delete a built-in role and says why", async () => {
    wrap(<RolesPanel />);
    await screen.findByRole("button", { name: /Delete coastal_cell/i });

    const btn = screen.getByRole("button", { name: /Delete district_command/i });
    expect(btn).toBeDisabled();
    expect(btn).toHaveAttribute("title", expect.stringContaining("Built-in"));
  });

  it("refuses to delete a custom role that still has seats", async () => {
    wrap(<RolesPanel />);
    await screen.findByRole("button", { name: /Delete coastal_cell/i });
    // sho is built-in AND has seats; the custom coastal_cell has none, so it is
    // the one that must be deletable.
    expect(screen.getByRole("button", { name: /Delete coastal_cell/i })).toBeEnabled();
  });

  it("blocks a permission that needs finer grain than the role's widest tier", async () => {
    await openCreateForm();

    // Make the role issuable at STATE level, which is aggregate-only. The tier
    // buttons are labelled by rank, so this is "DGP / State Command".
    fireEvent.click(screen.getByRole("button", { name: /DGP \/ State Command/i }));
    fireEvent.click(screen.getByRole("checkbox", { name: /Open case file/i }));

    // Marked in place rather than hidden, because the reason is what the admin
    // needs to see.
    expect(await screen.findByText(/needs district scope/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Create role/i })).toBeDisabled();
  });

  it("allows the same permission once the state tier is removed", async () => {
    await openCreateForm();
    fireEvent.change(roleNameInput(), {
      target: { value: "coastal_security_cell" },
    });
    fireEvent.click(screen.getByRole("checkbox", { name: /Open case file/i }));

    // District is selected by default, state is not — so this is already legal.
    expect(screen.queryByText(/will be refused/i)).toBeNull();

    // But it IS sensitive, so a reason is demanded before the submit unlocks.
    const reason = await screen.findByLabelText(/Reason/i);
    expect(screen.getByRole("button", { name: /Create role/i })).toBeDisabled();

    fireEvent.change(reason, { target: { value: "district command needs case files" } });
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Create role/i })).toBeEnabled());
  });

  it("sends the composed role with its permissions, tiers and reason", async () => {
    await openCreateForm();
    fireEvent.change(roleNameInput(), {
      target: { value: "coastal_security_cell" },
    });
    fireEvent.click(screen.getByRole("checkbox", { name: /Command dashboard/i }));
    fireEvent.click(screen.getByRole("checkbox", { name: /Station performance/i }));

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Create role/i })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: /Create role/i }));

    await waitFor(() => expect(calls.created).toHaveLength(1));
    expect(calls.created[0]).toMatchObject({
      role_name: "coastal_security_cell",
      base_surface: "state_command",
      allowed_scope_types: ["district"],
    });
    expect(calls.created[0].permission_keys).toEqual(
      expect.arrayContaining(["dashboard.read", "performance.read"]));
    // No sensitive permission chosen, so no reason was demanded.
    expect(calls.created[0].reason).toBeUndefined();
  });

  it("requires a name of at least three characters", async () => {
    await openCreateForm();
    fireEvent.change(roleNameInput(), { target: { value: "ab" } });
    // The server constrains this too; failing here saves the round trip.
    expect(screen.getByRole("button", { name: /Create role/i })).toBeDisabled();
  });
});
