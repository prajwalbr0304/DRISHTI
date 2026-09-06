import { describe, expect, it } from "vitest";
import { DESTINATIONS, visibleDestinations } from "@/config/destinations";
import type { UserRole } from "@/config/roles";

/* ============================================================================
   Sidebar destination filtering.

   The live filter is `requiresCaseLevel` against the seat's aggregate-only flag,
   and it exists to mirror the server: /cases and the point-level /geo routes are
   guarded by `require_case_level`, so a state or wing seat gets a 403 there. Left
   in the sidebar, those pages read as a broken product rather than as a scope
   boundary.

   It is keyed on SCOPE, not on role, and that is the point: an ADGP and a DIG are
   both `senior_command` and only the ADGP is aggregate-only, so a role-keyed
   allow-list cannot express this at all.
   ========================================================================== */

const ROLES: UserRole[] = [
  "dgp_state_command", "senior_command", "district_command",
  "sho", "investigating_officer", "system_admin",
];

const CASE_LEVEL_PATHS = [
  "/cases", "/intake", "/people", "/people/face", "/network", "/board",
];

describe("visibleDestinations", () => {
  it("hides the case-level destinations from an aggregate-only seat", () => {
    const paths = visibleDestinations("dgp_state_command", true, "crime",
                                     { aggregateOnly: true }).map((d) => d.path);
    for (const p of CASE_LEVEL_PATHS) {
      expect(paths, `${p} should be hidden from an aggregate-only seat`)
        .not.toContain(p);
    }
  });

  it("keeps the aggregate destinations for that same seat", () => {
    const paths = visibleDestinations("dgp_state_command", true, "crime",
                                     { aggregateOnly: true }).map((d) => d.path);
    // A DGP still needs the command board, the map, analytics and the assistant:
    // those answer at district and state grain, which is exactly their remit.
    for (const p of ["/command", "/map", "/analytics", "/ask"]) {
      expect(paths, `${p} should stay for an aggregate-only seat`).toContain(p);
    }
    expect(paths.length).toBeGreaterThan(3);
  });

  it("gives the SAME role the case-level destinations when not aggregate-only", () => {
    // The ADGP/DIG pair. Both are `senior_command`; only the wing seat is
    // aggregate-only, so a role-keyed filter could not tell them apart.
    const wing = visibleDestinations("senior_command", true, "crime",
                                    { aggregateOnly: true }).map((d) => d.path);
    const range = visibleDestinations("senior_command", true, "crime",
                                     { aggregateOnly: false }).map((d) => d.path);

    expect(wing).not.toContain("/cases");
    expect(range).toContain("/cases");
    expect(range.length).toBeGreaterThan(wing.length);
  });

  it("shows everything when the seat is not supplied", () => {
    // Pre-existing behaviour, kept so every existing caller is unaffected.
    const paths = visibleDestinations("sho", true).map((d) => d.path);
    for (const p of CASE_LEVEL_PATHS) expect(paths).toContain(p);
  });

  it("still separates the two workspaces", () => {
    const crime = visibleDestinations("sho", true, "crime").map((d) => d.path);
    const er = visibleDestinations("sho", true, "emergency").map((d) => d.path);
    expect(crime.some((p) => p.startsWith("/er"))).toBe(false);
    expect(er.every((p) => p.startsWith("/er"))).toBe(true);
  });

  it("keeps admin-only destinations behind the admin flag", () => {
    const withAdmin = visibleDestinations("system_admin", true, "crime").map((d) => d.path);
    const without = visibleDestinations("sho", false, "crime").map((d) => d.path);
    expect(withAdmin).toContain("/admin");
    expect(without).not.toContain("/admin");
  });

  it("leaves every role at least a usable workspace", () => {
    // A filter that empties the sidebar for some seat is worse than no filter.
    for (const role of ROLES) {
      for (const aggregateOnly of [true, false]) {
        const v = visibleDestinations(role, true, "crime", { aggregateOnly });
        expect(v.length, `${role} aggregateOnly=${aggregateOnly}`).toBeGreaterThan(2);
      }
    }
  });

  it("marks exactly the destinations that resolve to individual records", () => {
    const marked = DESTINATIONS.filter((d) => d.requiresCaseLevel).map((d) => d.path);
    expect(marked.sort()).toEqual([...CASE_LEVEL_PATHS].sort());
    // The map is deliberately NOT marked: its hotspot layer is aggregate and is a
    // state seat's primary geographic view. Point-level data is refused inside the
    // endpoint instead.
    expect(marked).not.toContain("/map");
  });
});
