import { Link } from "react-router-dom";
import { CircleHelp, Search } from "lucide-react";
import { useUIStore } from "@/stores/useUIStore";
import { LanguageSwitcher } from "@/components/shell/LanguageSwitcher";
import { ThemeToggle } from "@/components/shell/ThemeToggle";
import { NotificationsBell } from "@/components/shell/NotificationsBell";
import { ProfileMenu } from "@/components/shell/ProfileMenu";
import { RegionSelector } from "@/components/shell/RegionSelector";
import { Button } from "@/components/ui/button";
import { SimpleTooltip } from "@/components/ui/tooltip";
import { useLanguage } from "@/providers/LanguageProvider";

/* ============================================================================
   Global top bar, laid out like the AWS console global navigation:

     [ search ……… Ctrl K ]   [EN] │ [☾] │ [🔔] │ [?] │ [district ▾] │ [avatar]

   Search sits left and stretches. Each utility on the right is fenced by a
   hairline rule so the cluster reads as distinct tools rather than one run-on
   strip. The "?" is the entry to Support, as it is in the console.

   The time window deliberately lives with the page greeting instead: it scopes
   the content, not the chrome, so it belongs beside the content it changes.
   ========================================================================== */

const isMac =
  typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform);

/** Hairline rule between top-bar controls. Every control is fenced by one so the
 *  cluster reads as separate tools rather than one run-on strip. Purely
 *  decorative, so it is hidden from assistive tech. */
function Rule() {
  return <span className="mx-1.5 hidden h-6 w-px shrink-0 bg-hairline sm:block" aria-hidden />;
}

export function TopBar() {
  const setCommandOpen = useUIStore((s) => s.setCommandOpen);
  const { t } = useLanguage();

  return (
    <header className="flex h-topbar shrink-0 items-center gap-2 border-b border-hairline bg-surface px-3">
      {/* Search / ⌘K — a button that opens the command palette, styled as a field */}
      <button
        type="button"
        onClick={() => setCommandOpen(true)}
        className="group flex h-8 w-full min-w-0 max-w-xl items-center gap-2 rounded-control border border-hairline bg-surface-2 px-2.5 text-content-dim transition-colors hover:border-primary/50"
        aria-label={t("Ask DRISHTI")}
      >
        <Search className="size-4 shrink-0" />
        <span className="truncate text-13">{t("Ask DRISHTI…")}</span>
        <kbd className="ml-auto hidden items-center gap-0.5 rounded border border-hairline bg-surface px-1.5 py-0.5 text-11 font-medium text-content-dim tnum sm:inline-flex">
          {isMac ? "⌘" : "Ctrl"} K
        </kbd>
      </button>

      {/* Right cluster. The time window is NOT here — it sits with the page
          greeting, next to the data it scopes. */}
      <div className="ml-auto flex shrink-0 items-center gap-0.5">
        <LanguageSwitcher />
        <Rule />
        <ThemeToggle />
        <Rule />
        <NotificationsBell />
        <Rule />

        {/* Support — the console's "?" */}
        <SimpleTooltip label={t("Support")}>
          <Button variant="ghost" size="icon-sm" className="size-8" asChild>
            <Link to="/support" aria-label={t("Support")}>
              <CircleHelp />
            </Link>
          </Button>
        </SimpleTooltip>
        <Rule />

        <RegionSelector />
        <Rule />

        <ProfileMenu />
      </div>
    </header>
  );
}
