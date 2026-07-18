import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

// The map stack (maplibre + deck.gl) needs WebGL — stub it in jsdom.
vi.mock("@/components/map/MapCanvas", () => ({
  MapCanvas: ({ children }: { children?: ReactNode }) => <div data-testid="map">{children}</div>,
}));
vi.mock("react-map-gl/maplibre", () => ({
  Marker: ({ children }: { children?: ReactNode }) => <div data-testid="marker">{children}</div>,
}));

const geoResolve = vi.fn();
vi.mock("@/api", () => ({
  api: { intake: { geoResolve: (...a: unknown[]) => geoResolve(...a) } },
}));

import { LocationPicker } from "@/routes/intake/fir/LocationPicker";
import { RoleProvider } from "@/providers/RoleProvider";

function wrap(node: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <RoleProvider>{node}</RoleProvider>
    </QueryClientProvider>,
  );
}

const MISMATCH = {
  has_point: true, in_state: true, in_assigned_district: false,
  resolved_district_id: 9, resolved_district_name: "Mysuru",
  nearest_unit_id: 3, nearest_unit_name: "Mysuru City PS",
  note: null, latitude: 12.3, longitude: 76.6,
};

describe("LocationPicker jurisdiction mismatch", () => {
  beforeEach(() => {
    geoResolve.mockReset();
    localStorage.clear();
  });

  it("offers 'Use detected district' when the pin is outside the assigned district", async () => {
    geoResolve.mockResolvedValue(MISMATCH);
    const onUse = vi.fn();
    wrap(
      <LocationPicker latitude={12.3} longitude={76.6} assignedDistrictId={5}
        onChange={() => {}} onUseDetectedDistrict={onUse} overrideReason={null}
        onOverrideReasonChange={() => {}} />,
    );
    // the blocking mismatch affordance is shown ...
    const btn = await screen.findByRole("button", { name: /Use detected district/i });
    expect(btn).toBeInTheDocument();
    // ... and it reassigns to the detected district.
    fireEvent.click(btn);
    expect(onUse).toHaveBeenCalledWith(9, "Mysuru");
  });

  it("lets a supervisor record an override reason", async () => {
    localStorage.setItem("drishti.role", "supervisor");
    geoResolve.mockResolvedValue(MISMATCH);
    wrap(
      <LocationPicker latitude={12.3} longitude={76.6} assignedDistrictId={5}
        onChange={() => {}} onUseDetectedDistrict={() => {}} overrideReason={null}
        onOverrideReasonChange={() => {}} />,
    );
    expect(await screen.findByText(/Supervisory override reason/i)).toBeInTheDocument();
  });

  it("shows a clean match with no mismatch panel when in the assigned district", async () => {
    geoResolve.mockResolvedValue({ ...MISMATCH, in_assigned_district: true });
    wrap(
      <LocationPicker latitude={12.3} longitude={76.6} assignedDistrictId={5}
        onChange={() => {}} onUseDetectedDistrict={vi.fn()} overrideReason={null}
        onOverrideReasonChange={vi.fn()} />,
    );
    expect(await screen.findByText(/Matches assigned district/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Use detected district/i })).not.toBeInTheDocument();
  });
});
