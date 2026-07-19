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

  // The global-zoom feature was removed. Clear any leftover inline `zoom` a prior
  // session may have set on <html> (a stale zoom would break dashboard drag math).
  useEffect(() => {
    document.documentElement.style.removeProperty("zoom");
  }, []);

  return <>{children}</>;
}
