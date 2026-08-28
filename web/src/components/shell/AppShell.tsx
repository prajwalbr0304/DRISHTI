import { Outlet } from "react-router-dom";
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
  return (
    <TooltipProvider delayDuration={200} skipDelayDuration={400}>
      <div className="flex h-screen w-full overflow-hidden bg-bg text-content">
        <Sidebar />

        <div className="flex min-w-0 flex-1 flex-col">
          <TopBar />
          <Breadcrumbs />
          <main className="min-h-0 flex-1 overflow-y-auto">
            <div className="mx-auto w-full max-w-[1600px] p-5">
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
