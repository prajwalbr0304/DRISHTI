import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import type { UiGrant } from "@/api/endpoints/adminConsole";

/* ============================================================================
   Admin UI-visibility overrides.

   The design decision worth protecting: DEFAULTS LIVE IN CODE, only OVERRIDES
   live in the database. That means an element with no row is visible, which is
   what lets a card shipped this week appear immediately instead of waiting for
   an admin to enable it once per role.

   The second is precedence: a scope-specific override beats a role-wide one, so a
   card can be hidden from wing seats while range seats keep it. Both rows are
   allowed to exist and the narrower must win.
   ========================================================================== */

const state = vi.hoisted(() => ({
  items: [] as UiGrant[],
  fail: false,
  scopeType: "range" as string,
}));

vi.mock("@/api", () => ({
  api: {
    adminConsole: {
      uiVisibility: () =>
        state.fail
          ? Promise.reject(new Error("service down"))
          : Promise.resolve({
              total: state.items.length, items: state.items,
              enforcement: "Presentation only.",
            }),
    },
  },
}));

vi.mock("@/providers/RoleProvider", () => ({
  useRole: () => ({ role: "senior_command" }),
}));

vi.mock("@/hooks/useMyScope", () => ({
  useMyScope: () => ({ scopeType: state.scopeType }),
}));

import { useUiVisibility } from "@/hooks/useUiVisibility";

function grant(over: Partial<UiGrant> = {}): UiGrant {
  return {
    id: 1, role_name: "senior_command", scope_type: null,
    element_kind: "kpi", element_id: "kpi-hotspots", enabled: false,
    reason: null, updated_by: "platform.admin", updated_at: null,
    ...over,
  };
}

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("useUiVisibility", () => {
  beforeEach(() => {
    state.items = [];
    state.fail = false;
    state.scopeType = "range";
  });

  it("treats an element with no override as visible", async () => {
    const { result } = renderHook(() => useUiVisibility(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));

    // The registry, not the database, decides defaults. A new card must not be
    // invisible until somebody remembers to enable it six times.
    expect(result.current.isVisible("kpi", "kpi-anything-new")).toBe(true);
    expect(result.current.hidden.kpi.size).toBe(0);
  });

  it("hides an element an admin switched off", async () => {
    state.items = [grant({ enabled: false, reason: "trialling without it" })];
    const { result } = renderHook(() => useUiVisibility(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.isVisible("kpi", "kpi-hotspots")).toBe(false);
    expect(result.current.hidden.kpi.has("kpi-hotspots")).toBe(true);
    expect(result.current.reasonFor("kpi", "kpi-hotspots")).toBe("trialling without it");
  });

  it("lets a scope-specific override win over a role-wide one", async () => {
    // Hidden for the whole role, but re-enabled for range seats specifically.
    state.items = [
      grant({ id: 1, scope_type: null, enabled: false }),
      grant({ id: 2, scope_type: "range", enabled: true }),
    ];
    state.scopeType = "range";

    const { result } = renderHook(() => useUiVisibility(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.isVisible("kpi", "kpi-hotspots")).toBe(true);
    expect(result.current.hidden.kpi.has("kpi-hotspots")).toBe(false);
  });

  it("still hides it for a scope the narrow override does not name", async () => {
    // Same two rows; this seat is a WING seat, so only the role-wide row applies.
    state.items = [
      grant({ id: 1, scope_type: null, enabled: false }),
      grant({ id: 2, scope_type: "range", enabled: true }),
    ];
    state.scopeType = "wing";

    const { result } = renderHook(() => useUiVisibility(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.isVisible("kpi", "kpi-hotspots")).toBe(false);
  });

  it("ignores overrides belonging to another role", async () => {
    state.items = [grant({ role_name: "sho", enabled: false })];
    const { result } = renderHook(() => useUiVisibility(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.isVisible("kpi", "kpi-hotspots")).toBe(true);
  });

  it("keeps element kinds separate", async () => {
    // A widget and a KPI card can share an id; hiding one must not hide the other.
    state.items = [grant({ element_kind: "widget", element_id: "trend", enabled: false })];
    const { result } = renderHook(() => useUiVisibility(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.isVisible("widget", "trend")).toBe(false);
    expect(result.current.isVisible("kpi", "trend")).toBe(true);
  });

  it("falls back to showing everything when the service is unreachable", async () => {
    state.fail = true;
    const { result } = renderHook(() => useUiVisibility(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));

    // A presentation-only control that cannot be read must not blank the
    // workspace. Showing too much is the right failure here; showing nothing
    // would make a visibility outage look like a data outage.
    expect(result.current.isVisible("kpi", "kpi-hotspots")).toBe(true);
    expect(result.current.hidden.kpi.size).toBe(0);
  });
});
