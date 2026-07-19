import { useLocation, useNavigate } from "react-router-dom";
import { ScanEye, ShieldAlert } from "lucide-react";
import { cn } from "@/lib/utils";
import { WORKSPACES, contextForPath, type WorkspaceContext } from "@/config/destinations";
import { SimpleTooltip } from "@/components/ui/tooltip";

/* ============================================================================
   Workspace context switcher (Prompt 17 §A) — Crime Intelligence | Emergency
   Response. The active context lives in the URL (path prefix /er), not just
   local state, so a deep link opens the right workspace. Switching navigates to
   the target workspace's home.
   ========================================================================== */

const ICONS: Record<WorkspaceContext, typeof ScanEye> = {
  crime: ScanEye,
  emergency: ShieldAlert,
};

export function WorkspaceSwitcher({ collapsed }: { collapsed: boolean }) {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const active = contextForPath(pathname);

  if (collapsed) {
    // icon-rail: a single toggle to the OTHER workspace
    const other = WORKSPACES.find((w) => w.id !== active)!;
    const Icon = ICONS[other.id];
    return (
      <SimpleTooltip label={`Switch to ${other.label}`} side="right">
        <button
          type="button"
          onClick={() => navigate(other.home)}
          aria-label={`Switch to ${other.label}`}
          className="grid size-9 place-items-center rounded-control border border-hairline bg-surface-2 text-content-dim transition-colors hover:text-content"
        >
          <Icon className="size-[18px]" />
        </button>
      </SimpleTooltip>
    );
  }

  return (
    <div
      role="tablist"
      aria-label="Workspace"
      className="flex gap-0.5 rounded-control border border-hairline bg-surface-2/60 p-0.5"
    >
      {WORKSPACES.map((w) => {
        const Icon = ICONS[w.id];
        const isActive = w.id === active;
        return (
          <button
            key={w.id}
            role="tab"
            aria-selected={isActive}
            type="button"
            onClick={() => !isActive && navigate(w.home)}
            title={w.blurb}
            className={cn(
              "flex flex-1 items-center justify-center gap-1.5 rounded-[6px] px-2 py-1.5 text-12 font-medium transition-colors",
              isActive
                ? w.id === "emergency"
                  ? "bg-severity-high/20 text-severity-high"
                  : "bg-primary/15 text-primary"
                : "text-content-dim hover:text-content",
            )}
          >
            <Icon className="size-3.5 shrink-0" />
            <span className="truncate">{w.id === "emergency" ? "Emergency" : "Crime"}</span>
          </button>
        );
      })}
    </div>
  );
}
