import { Link, useLocation } from "react-router-dom";
import { ChevronRight, Home } from "lucide-react";
import { destinationByPath } from "@/config/destinations";
import { cn } from "@/lib/utils";
import { useLanguage } from "@/providers/LanguageProvider";

/* Breadcrumb bar — reflects the active destination and any sub-path.
   Hidden on the Command Center: there the trail collapses to a single crumb
   linking to the page you are already on, so the bar is 40px of noise directly
   above the greeting. Deeper routes keep it, where it carries real navigation
   (DRISHTI › Cases › 1024). */
export function Breadcrumbs() {
  const { pathname } = useLocation();
  const { t } = useLanguage();
  const dest = destinationByPath(pathname);
  const isHome = pathname === "/command";

  if (isHome) return null;

  // extra path segments beyond the destination root (e.g. /cases/1024)
  const rest = dest ? pathname.slice(dest.path.length).split("/").filter(Boolean) : [];

  return (
    <div className="flex h-breadcrumb shrink-0 items-center gap-1.5 border-b border-hairline bg-bg px-4 text-12">
      <Link
        to="/command"
        className="inline-flex items-center gap-1 text-content-dim transition-colors hover:text-content"
      >
        <Home className="size-3.5" />
        <span>DRISHTI</span>
      </Link>

      {dest && (
        <>
          <ChevronRight className="size-3.5 text-content-dim/60" />
          <Link
            to={dest.path}
            className={cn(
              "font-medium transition-colors",
              rest.length ? "text-content-dim hover:text-content" : "text-content",
            )}
          >
            {t(dest.label)}
          </Link>
        </>
      )}

      {rest.map((seg, i) => (
        <span key={i} className="inline-flex items-center gap-1.5">
          <ChevronRight className="size-3.5 text-content-dim/60" />
          <span className={cn("tnum", i === rest.length - 1 ? "text-content" : "text-content-dim")}>{seg}</span>
        </span>
      ))}
    </div>
  );
}
