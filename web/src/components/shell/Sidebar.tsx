import { NavLink, useLocation } from "react-router-dom";
import { PanelLeftClose, PanelLeftOpen, ScanEye, ShieldAlert } from "lucide-react";
import { cn } from "@/lib/utils";
import { useUIStore } from "@/stores/useUIStore";
import { useRole } from "@/providers/RoleProvider";
import { contextForPath, visibleDestinations } from "@/config/destinations";
import { Button } from "@/components/ui/button";
import { SimpleTooltip } from "@/components/ui/tooltip";
import { WorkspaceSwitcher } from "@/components/shell/WorkspaceSwitcher";
import { useLanguage } from "@/providers/LanguageProvider";

/* ============================================================================
   Left sidebar — the eight destinations, collapsible to an icon rail. Renders
   seven for non-admins (Admin hidden). Reads the role from RoleProvider.
   ========================================================================== */

export function Sidebar() {
  const collapsed = useUIStore((s) => s.sidebarCollapsed);
  const toggle = useUIStore((s) => s.toggleSidebar);
  const { role, isAdmin } = useRole();
  const { t } = useLanguage();
  const { pathname } = useLocation();
  const context = contextForPath(pathname);
  const destinations = visibleDestinations(role, isAdmin, context);
  const emergency = context === "emergency";

  return (
    <aside
      className={cn(
        "flex h-full shrink-0 flex-col border-r border-hairline bg-surface transition-[width] duration-200",
        collapsed ? "w-rail-collapsed" : "w-rail",
      )}
    >
      {/* Brand */}
      <div className={cn("flex h-topbar items-center gap-2 border-b border-hairline px-3", collapsed && "justify-center px-0")}>
        <div className={cn("grid size-8 shrink-0 place-items-center rounded-control",
                           emergency ? "bg-severity-high/20 text-severity-high" : "bg-primary/15 text-primary")}>
          {emergency ? <ShieldAlert className="size-5" /> : <ScanEye className="size-5" />}
        </div>
        {!collapsed && (
          <div className="min-w-0 leading-tight">
            <div className="truncate text-14 font-semibold tracking-wide text-content">DRISHTI</div>
            <div className="truncate text-12 text-content-dim">
              {emergency ? t("Emergency Response") : t("Crime Intelligence")}
            </div>
          </div>
        )}
      </div>

      {/* Workspace context switcher */}
      <div className={cn("border-b border-hairline p-2", collapsed && "flex justify-center")}>
        <WorkspaceSwitcher collapsed={collapsed} />
      </div>

      {/* Nav */}
      <nav className="flex-1 space-y-0.5 overflow-y-auto p-2">
        {destinations.map((d) => {
          const Icon = d.icon;
          const link = (
            <NavLink
              key={d.id}
              to={d.path}
              end={d.path === "/"}
              className={({ isActive }) =>
                cn(
                  "group relative flex items-center gap-3 rounded-control px-2.5 py-2 text-13 font-medium transition-colors",
                  collapsed && "justify-center px-0",
                  isActive
                    ? "bg-surface-2 text-content"
                    : "text-content-dim hover:bg-surface-2/60 hover:text-content",
                )
              }
            >
              {({ isActive }) => (
                <>
                  {isActive && (
                    <span className="absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-r-full bg-primary" aria-hidden />
                  )}
                  <Icon className={cn("size-[18px] shrink-0", isActive ? "text-primary" : "")} />
                  {!collapsed && <span className="truncate">{t(d.label)}</span>}
                </>
              )}
            </NavLink>
          );
          return collapsed ? (
            <SimpleTooltip key={d.id} label={t(d.label)} side="right">
              {link}
            </SimpleTooltip>
          ) : (
            link
          );
        })}
      </nav>

      {/* Collapse control */}
      <div className={cn("border-t border-hairline p-2", collapsed && "flex justify-center")}>
        <SimpleTooltip label={collapsed ? t("Expand sidebar") : t("Collapse sidebar")} side="right">
          <Button
            variant="ghost"
            size={collapsed ? "icon-sm" : "sm"}
            onClick={toggle}
            className={cn(!collapsed && "w-full justify-start gap-3")}
            aria-label={collapsed ? t("Expand sidebar") : t("Collapse sidebar")}
          >
            {collapsed ? <PanelLeftOpen /> : <PanelLeftClose />}
            {!collapsed && <span className="text-13">{t("Collapse")}</span>}
          </Button>
        </SimpleTooltip>
      </div>
    </aside>
  );
}
