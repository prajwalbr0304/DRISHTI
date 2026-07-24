import { useQuery } from "@tanstack/react-query";
import { ChevronsUpDown, Layers, LogOut, ShieldQuestion } from "lucide-react";
import { api } from "@/api";
import { cn } from "@/lib/utils";
import { ROLE_LIST } from "@/config/roles";
import { useAuth } from "@/auth";
import { useRole } from "@/providers/RoleProvider";
import { useUIStore } from "@/stores/useUIStore";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

/* ============================================================================
   Profile + demo view. This is a UX simulation for presenting role-specific
   screens — it is NOT authentication or a security boundary (real auth is
   deferred post-hackathon). Switching the demo view re-scopes the shell and
   sets the X-Role / X-Demo-Actor headers used only for display + audit.
   Service health is live.
   ========================================================================== */

export function ProfileMenu() {
  const { role, def, setRole } = useRole();
  const { user, signOut } = useAuth();
  const density = useUIStore((s) => s.density);
  const setDensity = useUIStore((s) => s.setDensity);

  const health = useQuery({
    queryKey: ["health"],
    queryFn: ({ signal }) => api.health(signal),
    refetchInterval: 60_000,
    retry: false,
  });

  const status = health.isLoading ? "checking" : health.error ? "down" : health.data?.status ?? "down";

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" className="h-9 shrink-0 gap-2 px-1.5" aria-label="Profile and role">
          <span className="grid size-6 shrink-0 place-items-center rounded-full bg-primary/15 text-12 font-semibold uppercase text-primary">
            {def.label.charAt(0)}
          </span>
          <span className="hidden max-w-[11rem] text-left leading-tight md:block">
            <span className="block truncate text-12 font-medium text-content">{def.label}</span>
            <span className="block truncate text-[11px] text-content-dim">{def.scope}</span>
          </span>
          <ChevronsUpDown className="hidden size-3.5 shrink-0 text-content-dim md:block" />
        </Button>
      </DropdownMenuTrigger>

      <DropdownMenuContent align="end" className="w-72">
        {user && (
          <div className="px-2 pt-1.5">
            <div className="truncate text-13 font-semibold text-content">{user.fullName}</div>
            <div className="truncate text-11 text-content-dim">{user.email}</div>
          </div>
        )}

        <DropdownMenuItem onSelect={() => signOut()}>
          <LogOut className="size-3.5" /> Sign out
        </DropdownMenuItem>

        <DropdownMenuSeparator />

        <div className="px-2 py-1.5">
          <div className="text-13 font-semibold text-content">{def.label}</div>
          <div className="text-12 text-content-dim">{def.blurb}</div>
          <div className="mt-1 text-12 text-content-dim">
            Scope: <span className="text-content">{def.scope}</span>
          </div>
        </div>

        <DropdownMenuSeparator />

        <DropdownMenuLabel className="flex items-center gap-1.5">
          <ShieldQuestion className="size-3.5" /> Demo view
        </DropdownMenuLabel>
        <div className="px-2 pb-1 text-[11px] text-content-dim">
          Presentation only — switches the role-specific screens. The server re-derives the
          real role from your identity; it never trusts this choice.
        </div>
        <DropdownMenuRadioGroup value={role} onValueChange={(v) => setRole(v as typeof role)}>
          {ROLE_LIST.map((r) => (
            <DropdownMenuRadioItem key={r.id} value={r.id}>
              <span className="flex flex-col">
                <span className="text-13 text-content">{r.label}</span>
                <span className="text-12 text-content-dim">{r.scope}</span>
              </span>
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>

        <DropdownMenuSeparator />

        <DropdownMenuLabel className="flex items-center gap-1.5">
          <Layers className="size-3.5" /> Density
        </DropdownMenuLabel>
        <DropdownMenuRadioGroup value={density} onValueChange={(v) => setDensity(v as typeof density)}>
          <DropdownMenuRadioItem value="comfortable">Comfortable</DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="compact">Compact</DropdownMenuRadioItem>
        </DropdownMenuRadioGroup>

        <DropdownMenuSeparator />

        <DropdownMenuItem
          className="cursor-default focus:bg-transparent"
          onSelect={(e) => e.preventDefault()}
        >
          <span
            className={cn(
              "size-2 rounded-full",
              status === "ok" && "bg-severity-low",
              status === "degraded" && "bg-severity-medium",
              status === "checking" && "bg-content-dim animate-pulse",
              status === "down" && "bg-severity-critical",
            )}
          />
          <span className="text-12 text-content-dim">
            Service{" "}
            <span className="text-content">
              {status === "checking" ? "checking…" : status}
            </span>
            {health.data?.version && <span className="tnum"> · v{health.data.version}</span>}
          </span>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
