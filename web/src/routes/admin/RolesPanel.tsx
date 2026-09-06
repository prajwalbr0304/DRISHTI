import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Loader2, Lock, Plus, ShieldAlert, Trash2 } from "lucide-react";
import { api } from "@/api";
import { errorMessage } from "@/api/contracts";
import type { AdminRole, PermissionOut } from "@/api/endpoints/adminConsole";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Field, SectionCard } from "@/routes/intake/components";
import { SCOPE_TYPE_LABELS, type ScopeType } from "@/config/roles";
import { cn } from "@/lib/utils";

/* ============================================================================
   Admin-created roles: compose any permission onto a new role, and edit the
   grants of an existing one.

   WHY A ROLE NEEDS A base_surface. A role that renders nothing is not usable, and
   requiring new frontend code per role would defeat the point. Every role names
   one of the six built-in UI surfaces it starts from; the UI-visibility switches
   then trim or extend it. That is what makes "create a role without a deploy"
   true rather than aspirational.

   WHY SCOPE IS NOT ON THIS FORM. A role carries permissions and a surface, never
   a jurisdiction. The same custom role can be issued to a district seat and a
   state seat, and scope comes from the seat's posting. What the form does declare
   is `allowed_scope_types` — the tiers the role MAY be issued at, which is a
   different statement and is what the server checks a permission against.

   The server refuses a permission that needs finer grain than the role's widest
   allowed tier, so a state-level role cannot be handed `cases.detail_read`. The
   form surfaces that as it happens rather than pre-filtering, because the reason
   is worth reading.
   ========================================================================== */

const ALL_SCOPE_TYPES: ScopeType[] = [
  "state", "wing", "range", "district", "commissionerate",
  "station", "assigned_case", "platform",
];

/** Narrowest-to-widest ordering, matching the server's own breadth table. Used to
 *  warn about a permission the chosen tiers cannot support BEFORE submitting. */
const BREADTH: Record<string, number> = {
  state: 0, platform: 0, wing: 1, range: 2,
  district: 3, commissionerate: 3, station: 4, assigned_case: 5,
};

function widestOf(scopes: string[]): string | null {
  if (!scopes.length) return null;
  return scopes.reduce((a, b) => (BREADTH[a] <= BREADTH[b] ? a : b));
}

/** Mirrors the server rule so the form can explain the refusal in advance. */
function unusableAt(perm: PermissionOut, widest: string | null): boolean {
  if (!perm.requires_scope || !widest) return false;
  if (widest === "platform") return false;
  return (BREADTH[widest] ?? 0) < (BREADTH[perm.requires_scope] ?? 0);
}

export function RolesPanel() {
  const qc = useQueryClient();

  const roles = useQuery({
    queryKey: ["admin", "roles"],
    queryFn: ({ signal }) => api.adminConsole.roles(signal),
  });
  const catalogue = useQuery({
    queryKey: ["admin", "permissions"],
    queryFn: ({ signal }) => api.adminConsole.permissions(signal),
  });

  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["admin", "roles"] });
    qc.invalidateQueries({ queryKey: ["org", "roles"] });
  };

  const remove = useMutation({
    mutationFn: (roleName: string) => api.adminConsole.deleteRole(roleName),
    onSuccess: invalidate,
  });

  return (
    <div className="space-y-4">
      <SectionCard
        title="Roles"
        description="Every role, the permissions it holds and the seats using it. Built-in roles can have their permissions edited but cannot be renamed or deleted."
      >
        {roles.isLoading ? (
          <p className="text-12 text-content-dim">Loading roles…</p>
        ) : roles.error ? (
          <p className="flex items-center gap-1 text-12 text-severity-high">
            <AlertTriangle className="size-3.5" /> {errorMessage(roles.error)}
          </p>
        ) : (
          <>
            <div className="mb-3 flex items-center justify-between gap-2">
              <span className="text-11 text-content-dim">
                {roles.data?.total ?? 0} roles
              </span>
              <Button size="sm" variant="primary" onClick={() => setCreating((v) => !v)}>
                <Plus className="size-3.5" /> {creating ? "Cancel" : "New role"}
              </Button>
            </div>

            {creating && catalogue.data && (
              <CreateRoleForm
                baseSurfaces={roles.data?.base_surfaces ?? []}
                categories={catalogue.data.categories}
                onDone={() => { setCreating(false); invalidate(); }}
              />
            )}

            <div className="overflow-x-auto">
              <table className="w-full text-12">
                <thead className="text-content-dim">
                  <tr className="border-b border-hairline text-left">
                    <th className="py-1.5 pr-3 font-medium">Role</th>
                    <th className="py-1.5 pr-3 font-medium">UI surface</th>
                    <th className="py-1.5 pr-3 font-medium">Issuable at</th>
                    <th className="py-1.5 pr-3 font-medium">Permissions</th>
                    <th className="py-1.5 pr-3 font-medium">Seats</th>
                    <th className="py-1.5 pr-3 font-medium" />
                  </tr>
                </thead>
                <tbody>
                  {roles.data?.items.map((r) => (
                    <RoleRow
                      key={r.role_name}
                      role={r}
                      expanded={editing === r.role_name}
                      onToggle={() =>
                        setEditing(editing === r.role_name ? null : r.role_name)}
                      onDelete={() => remove.mutate(r.role_name)}
                      deleting={remove.isPending}
                    />
                  ))}
                </tbody>
              </table>
            </div>

            {remove.error && (
              <p className="mt-2 flex items-start gap-1 text-11 text-severity-critical">
                <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
                {errorMessage(remove.error)}
              </p>
            )}
          </>
        )}
      </SectionCard>

      {editing && catalogue.data && (
        <GrantEditor
          roleName={editing}
          categories={catalogue.data.categories}
          onDone={invalidate}
        />
      )}
    </div>
  );
}

/* --------------------------------- row ------------------------------------ */
function RoleRow({
  role, expanded, onToggle, onDelete, deleting,
}: {
  role: AdminRole; expanded: boolean; onToggle: () => void;
  onDelete: () => void; deleting: boolean;
}) {
  /* Deletion is refused server-side for built-in roles and for any role that
     still has seats. Disabling the button here explains WHY up front instead of
     letting the click fail. */
  const undeletable = role.is_system
    ? "Built-in roles cannot be deleted."
    : role.seat_count > 0
      ? `${role.seat_count} seat(s) still hold this role. Reassign them first.`
      : null;

  return (
    <tr className={cn("border-b border-hairline/60", expanded && "bg-surface-2/40")}>
      <td className="py-1.5 pr-3">
        <span className="flex items-center gap-1.5">
          {role.is_system && <Lock className="size-3 shrink-0 text-content-dim" />}
          <span className="text-content">{role.display_label || role.role_name}</span>
        </span>
        <span className="block text-10 text-content-dim">{role.role_name}</span>
      </td>
      <td className="py-1.5 pr-3 text-content-dim">{role.base_surface ?? "—"}</td>
      <td className="py-1.5 pr-3">
        <span className="flex flex-wrap gap-1">
          {(role.allowed_scope_types ?? []).map((s) => (
            <Badge key={s} variant="neutral" className="text-10">
              {SCOPE_TYPE_LABELS[s as ScopeType] ?? s}
            </Badge>
          ))}
          {!role.allowed_scope_types?.length && (
            <span className="text-content-dim">any</span>
          )}
        </span>
      </td>
      <td className="py-1.5 pr-3">
        <span className="tnum text-content">{role.granted_count}</span>
        {role.sensitive_count > 0 && (
          <Badge variant="medium" className="ml-1.5 text-10">
            {role.sensitive_count} sensitive
          </Badge>
        )}
      </td>
      <td className="tnum py-1.5 pr-3 text-content-dim">{role.seat_count}</td>
      <td className="py-1.5 pr-3">
        <span className="flex items-center justify-end gap-1">
          <Button size="sm" variant="secondary" onClick={onToggle}>
            {expanded ? "Close" : "Permissions"}
          </Button>
          <Button
            size="icon-sm"
            variant="ghost"
            disabled={!!undeletable || deleting}
            title={undeletable ?? "Delete this role"}
            aria-label={`Delete ${role.role_name}`}
            onClick={onDelete}
          >
            <Trash2 className="size-3.5" />
          </Button>
        </span>
      </td>
    </tr>
  );
}

/* ----------------------------- permission picker -------------------------- */
function PermissionPicker({
  categories, selected, onChange, widest,
}: {
  categories: Record<string, PermissionOut[]>;
  selected: Set<string>;
  onChange: (next: Set<string>) => void;
  widest: string | null;
}) {
  const toggle = (key: string) => {
    const next = new Set(selected);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    onChange(next);
  };

  return (
    <div className="max-h-[340px] space-y-3 overflow-y-auto rounded-control border border-hairline p-3">
      {Object.entries(categories).map(([category, perms]) => (
        <div key={category}>
          <p className="mb-1 text-11 font-semibold uppercase tracking-wide text-content-dim">
            {category}
          </p>
          <ul className="space-y-0.5">
            {perms.map((p) => {
              const blocked = unusableAt(p, widest);
              const on = selected.has(p.permission_key);
              return (
                <li key={p.permission_key}>
                  <label
                    className={cn(
                      "flex cursor-pointer items-start gap-2 rounded-control px-1.5 py-1 text-12 transition-colors hover:bg-surface-2/60",
                      blocked && "opacity-60",
                    )}
                  >
                    <input
                      type="checkbox"
                      checked={on}
                      onChange={() => toggle(p.permission_key)}
                      className="mt-0.5 size-3.5 shrink-0 accent-[var(--color-primary)]"
                    />
                    <span className="min-w-0 flex-1">
                      <span className="flex flex-wrap items-center gap-1.5">
                        <span className="text-content">{p.label}</span>
                        {p.is_sensitive && (
                          <Badge variant="medium" className="text-10">
                            <ShieldAlert className="size-2.5" /> sensitive
                          </Badge>
                        )}
                        {blocked && (
                          /* Not hidden: the reason is the useful part. The server
                             would refuse this, and saying so beforehand is kinder
                             than a 400 after a long form. */
                          <Badge variant="neutral" className="text-10">
                            needs {p.requires_scope} scope
                          </Badge>
                        )}
                      </span>
                      <span className="block text-10 text-content-dim">
                        {p.permission_key}
                        {p.description ? ` · ${p.description}` : ""}
                      </span>
                    </span>
                  </label>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </div>
  );
}

/* ------------------------------ create form ------------------------------- */
function CreateRoleForm({
  baseSurfaces, categories, onDone,
}: {
  baseSurfaces: string[];
  categories: Record<string, PermissionOut[]>;
  onDone: () => void;
}) {
  const [roleName, setRoleName] = useState("");
  const [displayLabel, setDisplayLabel] = useState("");
  const [description, setDescription] = useState("");
  const [baseSurface, setBaseSurface] = useState(baseSurfaces[0] ?? "district_command");
  const [scopes, setScopes] = useState<Set<string>>(new Set(["district"]));
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [reason, setReason] = useState("");

  const widest = widestOf([...scopes]);

  const allPerms = useMemo(
    () => Object.values(categories).flat(), [categories]);

  /* A reason is required by the server whenever any chosen permission is
     sensitive, and it is written to the audit trail. Computed rather than always
     shown, so the prompt keeps meaning something. */
  const needsReason = allPerms.some(
    (p) => selected.has(p.permission_key) && p.is_sensitive);

  const blocked = allPerms.filter(
    (p) => selected.has(p.permission_key) && unusableAt(p, widest));

  const create = useMutation({
    mutationFn: () =>
      api.adminConsole.createRole({
        role_name: roleName.trim(),
        display_label: displayLabel.trim() || undefined,
        description: description.trim() || undefined,
        base_surface: baseSurface,
        allowed_scope_types: [...scopes],
        permission_keys: [...selected],
        reason: reason.trim() || undefined,
      }),
    onSuccess: onDone,
  });

  const toggleScope = (s: string) => {
    const next = new Set(scopes);
    if (next.has(s)) next.delete(s);
    else next.add(s);
    setScopes(next);
  };

  const canSubmit =
    roleName.trim().length >= 3 &&
    scopes.size > 0 &&
    blocked.length === 0 &&
    (!needsReason || reason.trim().length > 0) &&
    !create.isPending;

  return (
    <div className="mb-4 space-y-3 rounded-card border border-primary/40 bg-surface-2/40 p-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field
          label="Role name"
          required
          hint="Letters, digits and underscores. Used in URLs and configuration."
        >
          <Input
            value={roleName}
            onChange={(e) => setRoleName(e.target.value)}
            placeholder="coastal_security_cell"
          />
        </Field>
        <Field label="Display label" hint="What officers see. Defaults to the role name.">
          <Input
            value={displayLabel}
            onChange={(e) => setDisplayLabel(e.target.value)}
            placeholder="Coastal Security Cell"
          />
        </Field>
      </div>

      <Field label="Description">
        <Input
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="What this role is for."
        />
      </Field>

      <Field
        label="UI surface"
        required
        hint="Which built-in workspace this role renders. UI visibility then trims or extends it, so no new frontend code is needed."
      >
        <NativeSelect
          value={baseSurface}
          onChange={setBaseSurface}
          aria-label="UI surface"
          options={baseSurfaces.map((s) => ({ value: s, label: s.replace(/_/g, " ") }))}
        />
      </Field>

      <div>
        <p className="mb-1 flex items-center gap-1 text-12 font-medium text-content-dim">
          Issuable at <span className="text-severity-high">*</span>
        </p>
        <p className="mb-1.5 text-11 text-content-dim">
          The tiers a seat holding this role may be posted at. Not the role's own
          jurisdiction — scope always comes from the seat's posting.
        </p>
        <div className="flex flex-wrap gap-1.5">
          {ALL_SCOPE_TYPES.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => toggleScope(s)}
              aria-pressed={scopes.has(s)}
              className={cn(
                "rounded-control border px-2 py-1 text-11 transition-colors",
                scopes.has(s)
                  ? "border-primary/60 bg-primary/10 text-content"
                  : "border-hairline bg-surface text-content-dim hover:border-primary/40",
              )}
            >
              {SCOPE_TYPE_LABELS[s]}
            </button>
          ))}
        </div>
      </div>

      <div>
        <p className="mb-1 text-12 font-medium text-content-dim">
          Permissions ({selected.size} selected)
        </p>
        <PermissionPicker
          categories={categories}
          selected={selected}
          onChange={setSelected}
          widest={widest}
        />
      </div>

      {blocked.length > 0 && (
        <p className="flex items-start gap-1 text-11 text-severity-high">
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
          {blocked.length} selected permission(s) need a narrower scope than{" "}
          {widest} — a seat at that tier could not use them. Remove them, or drop
          the widest tier from “Issuable at”.
        </p>
      )}

      {needsReason && (
        <Field
          label="Reason"
          required
          hint="Recorded in the audit trail. Required because a selected permission exposes personal data or coercive capability."
        >
          <Input
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Why this role needs these permissions."
          />
        </Field>
      )}

      {create.error && (
        <p className="flex items-start gap-1 text-11 text-severity-critical">
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
          {errorMessage(create.error)}
        </p>
      )}

      <div className="flex items-center gap-2">
        <Button
          size="sm"
          variant="primary"
          disabled={!canSubmit}
          onClick={() => create.mutate()}
        >
          {create.isPending && <Loader2 className="size-3.5 animate-spin" />}
          Create role
        </Button>
        <span className="text-10 text-content-dim">
          A new role starts with no seats. Assign it under Access &amp; hierarchy.
        </span>
      </div>
    </div>
  );
}

/* ------------------------------ grant editor ------------------------------ */
function GrantEditor({
  roleName, categories, onDone,
}: {
  roleName: string;
  categories: Record<string, PermissionOut[]>;
  onDone: () => void;
}) {
  const detail = useQuery({
    queryKey: ["admin", "roles", roleName],
    queryFn: ({ signal }) => api.adminConsole.role(roleName, signal),
  });

  const [draft, setDraft] = useState<Set<string> | null>(null);
  const [reason, setReason] = useState("");

  /* Server state until the admin touches something, then the draft. Without this
     the checkbox list would snap back to the server's answer mid-edit whenever
     the query refetched. */
  const granted = useMemo(() => {
    if (draft) return draft;
    return new Set(
      (detail.data?.grants ?? []).filter((g) => g.granted)
        .map((g) => g.permission_key),
    );
  }, [draft, detail.data]);

  const widest = widestOf(detail.data?.allowed_scope_types ?? []);
  const allPerms = useMemo(() => Object.values(categories).flat(), [categories]);
  const needsReason = allPerms.some(
    (p) => granted.has(p.permission_key) && p.is_sensitive);
  const blocked = allPerms.filter(
    (p) => granted.has(p.permission_key) && unusableAt(p, widest));

  const save = useMutation({
    mutationFn: () =>
      api.adminConsole.replaceGrants(roleName, {
        permission_keys: [...granted],
        reason: reason.trim() || undefined,
      }),
    onSuccess: () => { setDraft(null); detail.refetch(); onDone(); },
  });

  return (
    <SectionCard
      title={`Permissions — ${roleName}`}
      description="The whole set is replaced on save, so anything unchecked is revoked. Read/write grants are also re-projected onto the legacy permission table the query executor reads."
    >
      {detail.isLoading ? (
        <p className="text-12 text-content-dim">Loading permissions…</p>
      ) : detail.error ? (
        <p className="text-12 text-severity-high">{errorMessage(detail.error)}</p>
      ) : (
        <div className="space-y-3">
          <p className="text-11 text-content-dim">
            {granted.size} of {allPerms.length} permissions
            {detail.data?.is_system && " · built-in role"}
          </p>

          <PermissionPicker
            categories={categories}
            selected={granted}
            onChange={setDraft}
            widest={widest}
          />

          {blocked.length > 0 && (
            <p className="flex items-start gap-1 text-11 text-severity-high">
              <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
              {blocked.map((p) => p.permission_key).join(", ")} need a narrower
              scope than {widest} and will be refused.
            </p>
          )}

          {needsReason && (
            <Field
              label="Reason"
              required
              hint="Recorded in the audit trail, because a selected permission is sensitive."
            >
              <Input
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Why this role holds these permissions."
              />
            </Field>
          )}

          {save.error && (
            <p className="flex items-start gap-1 text-11 text-severity-critical">
              <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
              {errorMessage(save.error)}
            </p>
          )}

          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="primary"
              disabled={
                !draft || blocked.length > 0 ||
                (needsReason && !reason.trim()) || save.isPending
              }
              onClick={() => save.mutate()}
            >
              {save.isPending && <Loader2 className="size-3.5 animate-spin" />}
              Save permissions
            </Button>
            {draft && (
              <Button size="sm" variant="ghost" onClick={() => setDraft(null)}>
                Discard changes
              </Button>
            )}
          </div>
        </div>
      )}
    </SectionCard>
  );
}
