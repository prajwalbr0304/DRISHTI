import { Link, useLocation } from "react-router-dom";
import { PanelLeftClose, PanelLeftOpen, ScanEye, ShieldAlert } from "lucide-react";
import { cn } from "@/lib/utils";
import { useUIStore } from "@/stores/useUIStore";
import { useRole } from "@/providers/RoleProvider";
import {
  contextForPath,
  destinationByPath,
  groupDestinations,
  visibleDestinations,
} from "@/config/destinations";
import { Button } from "@/components/ui/button";
import { SimpleTooltip } from "@/components/ui/tooltip";
import { WorkspaceSwitcher } from "@/components/shell/WorkspaceSwitcher";
import { useLanguage } from "@/providers/LanguageProvider";

/* ============================================================================
   Left side navigation, modelled on the AWS console side navigation:

     service title (+ collapse control)      ← header, then a divider
     ─────────────────────────────────
     Section heading                         ← bold group heading
       Destination                           ← 14px link; selected = bold + blue
       Destination                              on a rounded highlight
     ─────────────────────────────────        ← divider between groups
     Section heading …

   Collapsing shrinks it to an icon rail (the icons exist for that rail; the
   expanded panel keeps them as a scanning aid). The collapse control lives in
   the header, as it does in the AWS console, not in a footer row.
   ========================================================================== */

export function Sidebar() {
  const collapsed = useUIStore((s) => s.sidebarCollapsed);
  const toggle = useUIStore((s) => s.toggleSidebar);
  const { role, isAdmin } = useRole();
  const { t } = useLanguage();
  const { pathname } = useLocation();
  const context = contextForPath(pathname);
  const groups = groupDestinations(visibleDestinations(role, isAdmin, context));
  const activeDestinationId = destinationByPath(pathname)?.id;
  const emergency = context === "emergency";

  return (
    <aside
      aria-label={t("Primary")}
      className={cn(
        "flex h-full shrink-0 flex-col border-r border-hairline bg-surface transition-[width] duration-200",
        collapsed ? "w-rail-collapsed" : "w-rail",
      )}
    >
      {/* Header — service title + collapse control */}
      <div
        className={cn(
          "flex h-topbar shrink-0 items-center gap-2 border-b border-hairline",
          collapsed ? "justify-center px-0" : "pl-5 pr-2",
        )}
      >
        <div
          className={cn(
            "grid size-8 shrink-0 place-items-center rounded-control",
            emergency ? "bg-severity-high/20 text-severity-high" : "bg-primary/15 text-primary",
          )}
        >
          {emergency ? <ShieldAlert className="size-5" /> : <ScanEye className="size-5" />}
        </div>

        {!collapsed && (
          <>
            <div className="min-w-0 leading-tight">
              <div className="truncate text-heading-m font-bold text-content">DRISHTI</div>
              <div className="truncate text-body-s text-content-dim">
                {emergency ? t("Emergency Response") : t("Crime Intelligence")}
              </div>
            </div>
            <SimpleTooltip label={t("Collapse sidebar")} side="right">
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={toggle}
                className="ml-auto size-8"
                aria-label={t("Collapse sidebar")}
              >
                <PanelLeftClose />
              </Button>
            </SimpleTooltip>
          </>
        )}
      </div>

      {/* Workspace context switcher */}
      <div className={cn("shrink-0 border-b border-hairline py-3", collapsed ? "flex justify-center px-2" : "px-4")}>
        <WorkspaceSwitcher collapsed={collapsed} />
      </div>

      {/* Sectioned navigation */}
      <nav
        aria-label={t("Destinations")}
        className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto py-3"
      >
        {groups.map((group, gi) => (
          <div key={group.section}>
            {gi > 0 && <div className={cn("my-3 border-t border-hairline", collapsed ? "mx-2" : "mx-4")} />}

            {!collapsed && (
              /* Cloudscape section header: sentence case, bold, same size as the
                 links it heads — not an uppercase micro-label. */
              <h2 className="px-4 pb-1 text-body-m font-bold text-content">{t(group.section)}</h2>
            )}

            <ul className={cn("px-2", collapsed ? "space-y-1" : "space-y-0.5")}>
              {group.items.map((d) => {
                const Icon = d.icon;
                const isActive = d.id === activeDestinationId;
                const link = (
                  <Link
                    to={d.path}
                    aria-current={isActive ? "page" : undefined}
                    className={cn(
                      "flex w-full items-center gap-2.5 rounded-control text-body-m transition-colors",
                      collapsed ? "h-10 justify-center px-0" : "min-h-9 px-2.5 py-2",
                      isActive
                        ? "bg-primary/12 font-bold text-primary"
                        : "font-normal text-content-dim hover:bg-surface-2/60 hover:text-content",
                    )}
                  >
                    <Icon
                      aria-hidden="true"
                      className={cn("size-[18px] shrink-0", isActive ? "text-primary" : undefined)}
                    />
                    {!collapsed && <span className="truncate">{t(d.label)}</span>}
                  </Link>
                );
                return (
                  <li key={d.id}>
                    {collapsed ? (
                      <SimpleTooltip label={t(d.label)} side="right">
                        {link}
                      </SimpleTooltip>
                    ) : (
                      link
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      {/* Collapsed rail keeps an expand affordance */}
      {collapsed && (
        <div className="flex shrink-0 justify-center border-t border-hairline p-2">
          <SimpleTooltip label={t("Expand sidebar")} side="right">
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={toggle}
              className="size-8"
              aria-label={t("Expand sidebar")}
            >
              <PanelLeftOpen />
            </Button>
          </SimpleTooltip>
        </div>
      )}
    </aside>
  );
}
