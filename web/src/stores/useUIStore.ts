import { create } from "zustand";
import { persist } from "zustand/middleware";

/* ============================================================================
   Shell UI state (persisted): theme, sidebar collapse, information density.
   ThemeProvider reads `theme` + `density` and reflects them onto <html>.
   ========================================================================== */

export type ThemeName = "ops" | "desk";
export type Density = "comfortable" | "compact";

interface UIState {
  theme: ThemeName;
  sidebarCollapsed: boolean;
  density: Density;
  commandOpen: boolean;
  /** seed text for the ⌘K bar (e.g. from "Ask DRISHTI about this") */
  commandSeed: string;

  setTheme: (t: ThemeName) => void;
  toggleTheme: () => void;
  setSidebarCollapsed: (v: boolean) => void;
  toggleSidebar: () => void;
  setDensity: (d: Density) => void;
  setCommandOpen: (v: boolean) => void;
  /** open the command bar pre-filled with a question */
  askAbout: (seed: string) => void;
  setCommandSeed: (seed: string) => void;
}

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      theme: "desk", // Desk (light) is the default surface
      sidebarCollapsed: false,
      density: "comfortable",
      commandOpen: false,
      commandSeed: "",

      setTheme: (theme) => set({ theme }),
      toggleTheme: () => set((s) => ({ theme: s.theme === "ops" ? "desk" : "ops" })),
      setSidebarCollapsed: (sidebarCollapsed) => set({ sidebarCollapsed }),
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      setDensity: (density) => set({ density }),
      setCommandOpen: (commandOpen) => set({ commandOpen }),
      askAbout: (commandSeed) => set({ commandSeed, commandOpen: true }),
      setCommandSeed: (commandSeed) => set({ commandSeed }),
    }),
    {
      name: "drishti.ui",
      version: 2,
      partialize: (s) => ({
        theme: s.theme,
        sidebarCollapsed: s.sidebarCollapsed,
        density: s.density,
      }),
      // v1 defaulted to the dark "ops" surface. Move everyone to the new light
      // default once (users can still toggle after).
      migrate: (persisted, version) => {
        const p = (persisted ?? {}) as Partial<UIState>;
        const theme: ThemeName = version < 2 ? "desk" : p.theme ?? "desk";
        return {
          theme,
          sidebarCollapsed: p.sidebarCollapsed ?? false,
          density: p.density ?? "comfortable",
        };
      },
    },
  ),
);
