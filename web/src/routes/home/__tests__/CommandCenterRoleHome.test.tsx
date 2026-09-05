import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { RoleProvider } from "@/providers/RoleProvider";
import type { UserRole } from "@/config/roles";

/* ============================================================================
   The DGP seat gets its OWN board (Task 2). The range and district command
   seats must stay on the shared policymaker board, so this asserts the switch
   in both directions rather than only the new case.

   The five homes are stubbed: this test is about which board RoleHome mounts,
   not about what any board renders.
   ========================================================================== */

vi.mock("@/routes/home/StateCommandHome", () => ({
  StateCommandHome: () => <div data-testid="state-command-home" />,
}));
vi.mock("@/routes/home/PolicymakerHome", () => ({
  PolicymakerHome: () => <div data-testid="policymaker-home" />,
}));
vi.mock("@/routes/home/InvestigatorHome", () => ({
  InvestigatorHome: () => <div data-testid="investigator-home" />,
}));
vi.mock("@/routes/home/SupervisorHome", () => ({
  SupervisorHome: () => <div data-testid="supervisor-home" />,
}));
vi.mock("@/routes/home/AnalystHome", () => ({
  AnalystHome: () => <div data-testid="analyst-home" />,
}));

import { CommandCenter } from "@/routes/CommandCenter";

function mountAs(role: UserRole) {
  // RoleProvider reads the stored role at init and there is no AuthProvider
  // here, so a pre-set value is honoured verbatim.
  localStorage.setItem("drishti.role", role);
  // PageHeader reads the pathname, so the header needs a router in scope.
  return render(
    <MemoryRouter initialEntries={["/command"]}>
      <RoleProvider>
        <CommandCenter />
      </RoleProvider>
    </MemoryRouter>,
  );
}

describe("CommandCenter role switch", () => {
  beforeEach(() => localStorage.clear());

  it("mounts StateCommandHome for the DGP seat", () => {
    mountAs("dgp_state_command");
    expect(screen.getByTestId("state-command-home")).toBeInTheDocument();
    expect(screen.queryByTestId("policymaker-home")).toBeNull();
  });

  it.each<UserRole>(["adgp_igp_range", "sp_district_command"])(
    "leaves %s on the shared policymaker board",
    (role) => {
      mountAs(role);
      expect(screen.getByTestId("policymaker-home")).toBeInTheDocument();
      expect(screen.queryByTestId("state-command-home")).toBeNull();
    },
  );

  it("does not reach the state board from a field or analytical seat", () => {
    mountAs("investigating_officer");
    expect(screen.getByTestId("investigator-home")).toBeInTheDocument();
    expect(screen.queryByTestId("state-command-home")).toBeNull();
  });
});
