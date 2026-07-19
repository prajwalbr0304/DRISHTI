import { create } from "zustand";
import { persist } from "zustand/middleware";

/* ============================================================================
   Emergency Response UI state (Prompt 17).

   - assignedDistrict: the coordinator's SEAT — sent as X-Disaster-District so the
     server-side scope check applies to writes (a coordinator may only act inside
     their assigned synthetic district). super_admin covers all districts
     server-side regardless. Fixed per demo session (not the view filter).
   - activeDistrict: the VIEW filter for reads (district_id query param). Changing
     it never widens write scope.
   ========================================================================== */

// Demo default seat: Dakshina Kannada (24) — the primary coastal-flood scenario.
export const DEFAULT_ASSIGNED_DISTRICT = 24;

// District id -> name (mirrors datagen/disaster.py DISTRICTS for the demo).
export const DISTRICT_NAMES: Record<number, string> = {
  1: "Bagalkot", 2: "Ballari", 5: "Bengaluru Urban", 9: "Chikkamagaluru",
  13: "Davanagere", 16: "Kalaburagi", 18: "Kodagu", 19: "Koppal", 21: "Mandya",
  22: "Mysuru", 23: "Raichur", 24: "Dakshina Kannada", 27: "Udupi",
  28: "Uttara Kannada", 30: "Vijayapura",
};

interface DisasterState {
  assignedDistrict: number;
  activeDistrict: number | null;
  setActiveDistrict: (d: number | null) => void;
  setAssignedDistrict: (d: number) => void;
}

export const useDisasterStore = create<DisasterState>()(
  persist(
    (set) => ({
      assignedDistrict: DEFAULT_ASSIGNED_DISTRICT,
      activeDistrict: DEFAULT_ASSIGNED_DISTRICT,
      setActiveDistrict: (d) => set({ activeDistrict: d }),
      setAssignedDistrict: (d) => set({ assignedDistrict: d }),
    }),
    { name: "drishti.disaster" },
  ),
);

export function districtName(id?: number | null): string {
  if (id == null) return "All districts";
  return DISTRICT_NAMES[id] ?? `District ${id}`;
}
