import { useSearchParams } from "react-router-dom";
import { Banknote, Compass, EyeOff, Lock, Route as RouteIcon, Users } from "lucide-react";
import { cn } from "@/lib/utils";
import { roleCan } from "@/config/roles";
import { useRole } from "@/providers/RoleProvider";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/common/PageHeader";
import { EmptyState } from "@/components/common/EmptyState";
import { ExploreMode } from "@/routes/network/modes/ExploreMode";
import { CommunitiesMode } from "@/routes/network/modes/CommunitiesMode";
import { HiddenMode } from "@/routes/network/modes/HiddenMode";
import { MoneyMode } from "@/routes/network/modes/MoneyMode";
import { PathMode } from "@/routes/network/modes/PathMode";

const MODES = [
  { key: "explore", label: "Explore", icon: Compass },
  { key: "communities", label: "Communities", icon: Users },
  { key: "hidden", label: "Hidden Associations", icon: EyeOff },
  { key: "money", label: "Money Trail", icon: Banknote },
  { key: "path", label: "Path Finder", icon: RouteIcon },
];

export function NetworkAnalysis() {
  const { role } = useRole();
  const [sp, setSp] = useSearchParams();
  const mode = sp.get("mode") ?? "explore";
  const colorMode = (sp.get("color") as "type" | "community") ?? "type";

  const setParam = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(sp);
    for (const [k, v] of Object.entries(patch)) {
      if (v == null) next.delete(k);
      else next.set(k, v);
    }
    setSp(next, { replace: true });
  };

  if (!roleCan(role, "network_analysis")) {
    return (
      <div>
        <PageHeader title="Network Analysis" />
        <EmptyState
          icon={Lock}
          title="Not available for this role"
          description="Link analysis operates on individual entities and is not accessible to this role, which sees aggregate views only."
        />
      </div>
    );
  }

  const entity = sp.get("entity") ? Number(sp.get("entity")) : null;
  const association = sp.get("association") ? Number(sp.get("association")) : null;
  const account = sp.get("account") ? Number(sp.get("account")) : null;

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-20 font-semibold tracking-tight text-content">Network Analysis</h1>
        {mode === "explore" && (
          <div className="flex overflow-hidden rounded-control border border-hairline">
            <ColorToggle active={colorMode === "type"} onClick={() => setParam({ color: "type" })} label="By type" />
            <ColorToggle active={colorMode === "community"} onClick={() => setParam({ color: "community" })} label="By community" />
          </div>
        )}
      </div>

      {/* Mode sub-nav */}
      <div className="mb-3 flex flex-wrap gap-1 border-b border-hairline">
        {MODES.map((m) => {
          const Icon = m.icon;
          const active = mode === m.key;
          return (
            <button
              key={m.key}
              type="button"
              onClick={() => setParam({ mode: m.key })}
              className={cn(
                "flex items-center gap-2 border-b-2 px-3 py-2 text-13 font-medium transition-colors",
                active
                  ? "border-primary text-content"
                  : "border-transparent text-content-dim hover:text-content",
              )}
            >
              <Icon className="size-4" />
              {m.label}
            </button>
          );
        })}
      </div>

      {mode === "explore" && <ExploreMode colorMode={colorMode} initialEntity={entity} />}
      {mode === "communities" && <CommunitiesMode />}
      {mode === "hidden" && <HiddenMode initialAssociation={association} />}
      {mode === "money" && <MoneyMode initialAccount={account} />}
      {mode === "path" && <PathMode />}
    </div>
  );
}

function ColorToggle({ active, onClick, label }: { active: boolean; onClick: () => void; label: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "px-2.5 py-1 text-12 font-medium transition-colors",
        active ? "bg-primary text-primary-fg" : "bg-surface-2 text-content-dim hover:text-content",
      )}
    >
      {label}
    </button>
  );
}
