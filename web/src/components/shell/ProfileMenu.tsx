import { Link } from "react-router-dom";
import { LogOut, UserRound } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/auth";
import { useRole } from "@/providers/RoleProvider";
import { useLanguage } from "@/providers/LanguageProvider";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

/* ============================================================================
   Account avatar. Two actions only — view profile, log out.

   The demo-seat switcher used to live here; seat selection now happens at
   sign-in (the login screen's operational-view picker), so a session has one
   identity throughout instead of silently changing scope mid-session. Language
   moved to its own top-bar control; density and service health moved to the
   profile page.
   ========================================================================== */

/** Initials from a display name — "IGP Meenakshi Rao" -> "MR". */
function initials(name?: string | null): string {
  const words = (name ?? "").trim().split(/\s+/).filter(Boolean);
  if (!words.length) return "?";
  // Drop a leading rank/prefix ("SHO", "Dy.SP", "Insp.") when there is more.
  const meaningful = words.length > 1 && /[.\u002F]|^[A-Z]{2,}$/.test(words[0]) ? words.slice(1) : words;
  const picked = meaningful.length ? meaningful : words;
  return (picked[0][0] + (picked.length > 1 ? picked[picked.length - 1][0] : "")).toUpperCase();
}

export function ProfileMenu() {
  const { def } = useRole();
  const { user, signOut } = useAuth();
  const { t } = useLanguage();

  const displayName = user?.fullName ?? def.demoName;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className={cn(
          "grid size-8 shrink-0 place-items-center rounded-full bg-primary/15 text-body-s font-bold text-primary",
          "transition-colors hover:bg-primary/25 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60",
        )}
        aria-label={t("Account")}
      >
        {initials(displayName)}
      </DropdownMenuTrigger>

      <DropdownMenuContent align="end" className="w-64">
        <div className="px-2.5 py-2">
          <div className="truncate text-body-m font-bold text-content">{displayName}</div>
          {user?.email && <div className="truncate text-body-s text-content-dim">{user.email}</div>}
          <div className="mt-1 truncate text-body-s text-content-dim">
            {t(def.label)} · {t(def.scope)}
          </div>
        </div>

        <DropdownMenuSeparator />

        <DropdownMenuItem asChild>
          <Link to="/profile">
            <UserRound /> {t("View profile")}
          </Link>
        </DropdownMenuItem>

        <DropdownMenuItem onSelect={() => signOut()}>
          <LogOut /> {t("Log out")}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
