import { useEffect } from "react";
import { useUIStore } from "@/stores/useUIStore";

/* ============================================================================
   Reflects the persisted theme + density onto <html>:
     Ops  -> class "dark"        (default operations surface)
     Desk -> class "theme-desk"  (light briefing surface)
   The CSS-variable token sets in index.css swap accordingly.
   ========================================================================== */

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const theme = useUIStore((s) => s.theme);
  const density = useUIStore((s) => s.density);

  useEffect(() => {
    const root = document.documentElement;
    if (theme === "ops") {
      root.classList.add("dark");
      root.classList.remove("theme-desk");
    } else {
      root.classList.remove("dark");
      root.classList.add("theme-desk");
    }
  }, [theme]);

  useEffect(() => {
    document.documentElement.dataset.density = density;
  }, [density]);

  return <>{children}</>;
}
