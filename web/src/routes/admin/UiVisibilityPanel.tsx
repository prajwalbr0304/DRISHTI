import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Info, Loader2, RotateCcw } from "lucide-react";
import { api } from "@/api";
import { errorMessage } from "@/api/contracts";
import type { ElementKind, UiGrant } from "@/api/endpoints/adminConsole";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/native-select";
import { SectionCard } from "@/routes/intake/components";
import { BOARDS } from "@/config/kpi/roleBoards";
import { KPI_REGISTRY } from "@/config/kpi/registry";
import {
  ROLES, ROLE_LIST, SCOPE_TYPE_LABELS, type ScopeType, type UserRole,
} from "@/config/roles";
import { DESTINATIONS } from "@/config/destinations";

/* ============================================================================
   Per-role UI visibility: the on/off switches an administrator asked for.

   The element list comes from the FRONTEND REGISTRY, not from the database. The
   database holds only overrides, so a card shipped this week appears here
   immediately instead of waiting for someone to insert a row for it. That is also
   why "on" is rendered as the absence of an override rather than a stored TRUE:
   pinning it on would stop a later default change from reaching the role.

   VISIBILITY IS NOT ACCESS. Turning a destination off stops it being drawn; the
   route still resolves if typed and the endpoint still answers. The banner uses
   the server's own wording rather than a paraphrase.
   ========================================================================== */

const KIND_LABELS: Record<ElementKind, string> = {
  destination: "Navigation",
  board: "Boards",
  kpi: "KPI cards",
  widget: "Widgets",
};

interface Element {
  id: string;
  label: string;
  hint?: string;
}

/** Everything an admin can switch, per kind, from the shipped registries. */
function elementsFor(kind: ElementKind): Element[] {
  switch (kind) {
    case "destination":
      // Keyed by PATH, not by the internal `id`: the path is what a board or a
      // nav filter matches on, and it is what an admin recognises.
      return DESTINATIONS.map((d) => ({
        id: d.path, label: d.label, hint: `${d.section} · ${d.path}`,
      }));
    case "board":
      return (Object.keys(BOARDS) as ScopeType[])
        .filter((s) => s !== "unresolved")
        .map((s) => ({ id: s, label: BOARDS[s].title, hint: SCOPE_TYPE_LABELS[s] }));
    case "kpi":
      return KPI_REGISTRY.map((k) => ({ id: k.id, label: k.label, hint: k.id }));
    case "widget": {
      // De-duplicated across boards: one switch per widget, not one per board that
      // declares it, or an admin would have to find and flip the same panel twice.
      const seen = new Map<string, Element>();
      for (const board of Object.values(BOARDS)) {
        for (const w of board.widgets) {
          if (!seen.has(w.id)) seen.set(w.id, { id: w.id, label: w.label, hint: w.id });
        }
      }
      return [...seen.values()];
    }
  }
}

/** The scope types a role can actually be issued at, so the "applies to" list
 *  offers only real choices — a station-only role has no wing seats to target. */
function scopeTypesFor(role: UserRole): ScopeType[] {
  return ROLES[role]?.scopeTypes ?? [];
}

export function UiVisibilityPanel() {
  const qc = useQueryClient();
  const [role, setRole] = useState<UserRole>("district_command");
  const [kind, setKind] = useState<ElementKind>("kpi");
  const [scopeType, setScopeType] = useState<string>("");

  const grants = useQuery({
    queryKey: ["admin", "ui-visibility", "panel", role],
    queryFn: ({ signal }) => api.adminConsole.uiVisibility({ role_name: role }, signal),
  });

  const setGrant = useMutation({
    mutationFn: (v: { elementId: string; enabled: boolean }) =>
      api.adminConsole.setUiVisibility({
        role_name: role, element_kind: kind, element_id: v.elementId,
        enabled: v.enabled, scope_type: scopeType || null,
      }),
    onSuccess: () => {
      // Both this panel and every board reading the same overrides.
      qc.invalidateQueries({ queryKey: ["admin", "ui-visibility"] });
    },
  });

  const clearGrant = useMutation({
    mutationFn: (grantId: number) => api.adminConsole.clearUiVisibility(grantId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "ui-visibility"] }),
  });

  const elements = useMemo(() => elementsFor(kind), [kind]);

  /** The override that applies to the current role/scope selection, if any. */
  const overrideFor = (elementId: string): UiGrant | undefined => {
    const rows = (grants.data?.items ?? []).filter(
      (g) => g.element_kind === kind && g.element_id === elementId,
    );
    const wanted = scopeType || null;
    return rows.find((g) => (g.scope_type ?? null) === wanted);
  };

  const overrideCount = (grants.data?.items ?? []).filter(
    (g) => g.element_kind === kind).length;

  return (
    <SectionCard
      title="UI visibility"
      description="Turn parts of the interface on or off for a role. Defaults come from the shipped registry; only your changes are stored."
    >
      {/* The server's own statement, not a paraphrase. */}
      <p className="mb-3 flex items-start gap-2 rounded-control border border-hairline bg-surface-2/60 p-2.5 text-11 leading-relaxed text-content-dim">
        <Info className="mt-0.5 size-3.5 shrink-0" />
        <span>
          {grants.data?.enforcement ??
            "Presentation only. These switches control what is rendered, not what may be read."}
        </span>
      </p>

      <div className="mb-3 grid gap-2 sm:grid-cols-3">
        <label className="block">
          <span className="mb-1 block text-11 text-content-dim">Role</span>
          <NativeSelect
            value={role}
            onChange={(v) => setRole(v as UserRole)}
            aria-label="Role"
            options={ROLE_LIST.map((r) => ({ value: r.id, label: r.label }))}
          />
        </label>

        <label className="block">
          <span className="mb-1 block text-11 text-content-dim">Element type</span>
          <NativeSelect
            value={kind}
            onChange={(v) => setKind(v as ElementKind)}
            aria-label="Element type"
            options={(Object.keys(KIND_LABELS) as ElementKind[]).map((k) => ({
              value: k, label: KIND_LABELS[k],
            }))}
          />
        </label>

        <label className="block">
          <span className="mb-1 block text-11 text-content-dim">Applies to</span>
          {/* Role-wide is the default because it is what an admin usually means.
              The scope-specific option exists for when it is not: hiding a card
              from wing seats while range seats keep it. */}
          <NativeSelect
            value={scopeType}
            onChange={setScopeType}
            aria-label="Applies to"
            options={[
              { value: "", label: "Every seat with this role" },
              ...scopeTypesFor(role).map((s) => ({
                value: s, label: `Only ${SCOPE_TYPE_LABELS[s]} seats`,
              })),
            ]}
          />
        </label>
      </div>

      <div className="mb-2 flex items-center gap-2 text-11 text-content-dim">
        <span>{elements.length} {KIND_LABELS[kind].toLowerCase()}</span>
        {overrideCount > 0 && (
          <Badge variant="neutral">{overrideCount} override{overrideCount === 1 ? "" : "s"}</Badge>
        )}
        {(setGrant.isPending || clearGrant.isPending) && (
          <Loader2 className="size-3.5 animate-spin text-primary" />
        )}
      </div>

      {(setGrant.error || clearGrant.error) && (
        <p className="mb-2 text-11 text-severity-critical">
          {errorMessage(setGrant.error ?? clearGrant.error)}
        </p>
      )}

      {grants.isLoading ? (
        <p className="py-6 text-center text-12 text-content-dim">Loading overrides…</p>
      ) : (
        <ul className="divide-y divide-hairline">
          {elements.map((el) => {
            const override = overrideFor(el.id);
            const enabled = override?.enabled ?? true;
            return (
              <li key={el.id} className="flex items-center gap-3 py-2">
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-12 text-content">{el.label}</span>
                  {el.hint && (
                    <span className="block truncate text-10 text-content-dim">{el.hint}</span>
                  )}
                </span>

                {override && (
                  <>
                    {/* An explicit override is worth marking: the value is no
                        longer whatever the registry ships. */}
                    <Badge variant="neutral" className="shrink-0 text-10">
                      overridden
                    </Badge>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      title="Revert to the shipped default"
                      aria-label={`Revert ${el.label} to default`}
                      onClick={() => clearGrant.mutate(override.id)}
                    >
                      <RotateCcw className="size-3.5" />
                    </Button>
                  </>
                )}

                {/* Same on/off control the feature-flag panel uses, so the two
                    admin surfaces behave alike. */}
                <Button
                  size="sm"
                  variant={enabled ? "secondary" : "primary"}
                  disabled={setGrant.isPending || clearGrant.isPending}
                  aria-pressed={enabled}
                  aria-label={`${enabled ? "Hide" : "Show"} ${el.label} for this role`}
                  onClick={() => {
                    /* Turning something back ON deletes the override rather than
                       storing TRUE. An absent row follows the registry default, so
                       a later change to that default still reaches this role;
                       a stored TRUE would pin it and silently diverge. */
                    if (enabled) setGrant.mutate({ elementId: el.id, enabled: false });
                    else if (override) clearGrant.mutate(override.id);
                    else setGrant.mutate({ elementId: el.id, enabled: true });
                  }}
                >
                  {enabled ? "Hide" : "Show"}
                </Button>
              </li>
            );
          })}
        </ul>
      )}
    </SectionCard>
  );
}
