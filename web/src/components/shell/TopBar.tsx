import { Search } from "lucide-react";
import { useUIStore } from "@/stores/useUIStore";
import { TimeScrubber } from "@/components/shell/TimeScrubber";
import { ThemeToggle } from "@/components/shell/ThemeToggle";
import { NotificationsBell } from "@/components/shell/NotificationsBell";
import { ProfileMenu } from "@/components/shell/ProfileMenu";

const isMac =
  typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform);

export function TopBar() {
  const setCommandOpen = useUIStore((s) => s.setCommandOpen);

  return (
    <header className="flex h-topbar shrink-0 items-center gap-3 border-b border-hairline bg-surface px-3">
      {/* ⌘K Ask DRISHTI */}
      <button
        type="button"
        onClick={() => setCommandOpen(true)}
        className="group flex h-8 w-full min-w-0 max-w-md items-center gap-2 rounded-control border border-hairline bg-surface-2 px-2.5 text-content-dim transition-colors hover:border-primary/50"
        aria-label="Ask DRISHTI (open command palette)"
      >
        <Search className="size-4" />
        <span className="text-13">Ask DRISHTI…</span>
        <kbd className="ml-auto hidden items-center gap-0.5 rounded border border-hairline bg-surface px-1.5 py-0.5 text-[11px] font-medium text-content-dim tnum sm:inline-flex">
          {isMac ? "⌘" : "Ctrl"} K
        </kbd>
      </button>

      {/* Global time scrubber */}
      <div className="ml-auto hidden lg:block">
        <TimeScrubber />
      </div>

      <div className="ml-auto flex shrink-0 items-center gap-1.5 lg:ml-0">
        <div className="lg:hidden">
          <TimeScrubber />
        </div>
        <ThemeToggle />
        <NotificationsBell />
        <ProfileMenu />
      </div>
    </header>
  );
}
