import { Outlet } from "react-router-dom";
import { useDataAnchor } from "@/hooks/useDataAnchor";
import { useSeatCacheReset } from "@/hooks/useSeatCacheReset";
import { useSeatScopeAnchor } from "@/hooks/useSeatScopeAnchor";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Sidebar } from "@/components/shell/Sidebar";
import { TopBar } from "@/components/shell/TopBar";
import { Breadcrumbs } from "@/components/shell/Breadcrumbs";
import { PeekRail } from "@/components/shell/PeekRail";
import { CommandBar } from "@/components/shell/CommandBar";

/* ============================================================================
   The shell: sidebar · [top bar · breadcrumb · workspace] · peek rail.
   The ⌘K command bar mounts globally.
   ========================================================================== */

export function AppShell() {
  // Anchors the global time window to the latest data date. Must live here (not
  // in the scrubber) so it runs on every route.
  useDataAnchor();
  // Changing seat must not leave the previous seat's answers on screen. Ordered
  // BEFORE the scope anchor: the cache is dropped first, so the anchor re-derives
  // the district from a fresh /org/my-scope rather than from the outgoing seat's
  // cached one.
  useSeatCacheReset();
  // Same for the district scope: open on the seat's own region (an SP/SHO on their
  // district, a state seat on all of them) until the user picks. Must also run on
  // every route, not inside the top-bar selector.
  useSeatScopeAnchor();

  return (
    <TooltipProvider delayDuration={200} skipDelayDuration={400}>
      <div className="flex h-screen w-full overflow-hidden bg-bg text-content">
        <Sidebar />

        <div className="flex min-w-0 flex-1 flex-col">
          <TopBar />
          <Breadcrumbs />
          {/* No max-width cap: the workspace fills the display. A fixed cap left
              dead gutters on wide monitors, which is exactly the space an ops
              room wants spent on data. */}
          <main className="min-h-0 flex-1 overflow-y-auto">
            <div className="w-full p-5">
              <Outlet />
            </div>
          </main>
        </div>

        <PeekRail />
      </div>

      <CommandBar />
    </TooltipProvider>
  );
}
