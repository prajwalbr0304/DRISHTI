import { useQuery } from "@tanstack/react-query";
import { ChevronsUpDown, Layers, LogOut, ShieldQuestion } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { api } from "@/api";
import { cn } from "@/lib/utils";
import { ROLE_LIST, ROLES } from "@/config/roles";
import { useAuth } from "@/auth";
import { useRole } from "@/providers/RoleProvider";
import { useUIStore } from "@/stores/useUIStore";
import { Button } from "@/components/ui/button";
import { RoleIcon } from "@/components/roles/RoleIcon";
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
  const navigate = useNavigate();
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
          <span className="grid size-7 shrink-0 place-items-center rounded-full bg-primary/15 text-primary">
            <RoleIcon role={role} className="size-4" />
          </span>
          <span className="hidden max-w-[11rem] text-left leading-tight md:block">
            <span className="block truncate text-12 font-medium text-content">{def.label}</span>
            <span className="block truncate text-[11px] text-content-dim">{def.scope}</span>
          </span>
          <ChevronsUpDown className="hidden size-3.5 shrink-0 text-content-dim md:block" />
        </Button>
      </DropdownMenuTrigger>

      <DropdownMenuContent
        align="end"
        className="max-h-[calc(100dvh-5rem)] w-[480px] max-w-[calc(100vw-1rem)] overflow-y-auto p-1.5"
      >
        {user && (
          <div className="px-2.5 pb-1 pt-1.5">
            <div className="truncate text-13 font-semibold text-content">{user.fullName}</div>
            <div className="truncate text-11 text-content-dim">{user.email}</div>
          </div>
        )}

        <DropdownMenuItem onSelect={() => signOut()}>
          <LogOut className="size-3.5" /> Sign out
        </DropdownMenuItem>

        <DropdownMenuSeparator />

        <DropdownMenuLabel className="flex items-center gap-1.5">
          <ShieldQuestion className="size-3.5" /> Demo view
        </DropdownMenuLabel>
        <div className="px-2 pb-2 text-11 leading-relaxed text-content-dim">
          Preview another role workspace. Your authenticated permissions remain unchanged.
        </div>
        <DropdownMenuRadioGroup
          value={role}
          className="grid grid-cols-2 gap-1.5"
          onValueChange={(v) => {
            const nextRole = v as typeof role;
            setRole(nextRole);
            navigate(ROLES[nextRole].home);
          }}
        >
          {ROLE_LIST.map((r) => (
            <DropdownMenuRadioItem
              key={r.id}
              value={r.id}
              className="min-h-[54px] items-start border border-transparent py-1.5 pl-8 pr-2 data-[state=checked]:border-primary/30 data-[state=checked]:bg-primary/10"
            >
              <span className="flex min-w-0 items-start gap-2">
                <span className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-full bg-primary/10 text-primary">
                  <RoleIcon role={r.id} className="size-4" />
                </span>
                <span className="flex min-w-0 flex-col">
                  <span className="text-12 font-medium leading-snug text-content">{r.label}</span>
                  <span className="mt-0.5 text-11 leading-snug text-content-dim">{r.scope}</span>
                </span>
              </span>
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>

        <DropdownMenuSeparator />

        <DropdownMenuLabel className="flex items-center gap-1.5">
          <Layers className="size-3.5" /> Density
        </DropdownMenuLabel>
        <DropdownMenuRadioGroup
          value={density}
          className="grid grid-cols-2 gap-1"
          onValueChange={(v) => setDensity(v as typeof density)}
        >
          <DropdownMenuRadioItem
            className="border border-transparent data-[state=checked]:border-primary/30 data-[state=checked]:bg-primary/10"
            value="comfortable"
          >
            Comfortable
          </DropdownMenuRadioItem>
          <DropdownMenuRadioItem
            className="border border-transparent data-[state=checked]:border-primary/30 data-[state=checked]:bg-primary/10"
            value="compact"
          >
            Compact
          </DropdownMenuRadioItem>
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
