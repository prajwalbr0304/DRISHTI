import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, ShieldCheck, UserPlus, XCircle } from "lucide-react";
import { api } from "@/api";
import { errorMessage } from "@/api/contracts";
import { useRole } from "@/providers/RoleProvider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { SectionCard } from "@/routes/intake/components";

const ROLE_CHOICES = [
  "investigator", "analyst", "supervisor", "policymaker",
  "disaster_coordinator", "super_admin",
] as const;

function Err({ e }: { e: unknown }) {
  return (
    <p className="flex items-center gap-1 text-12 text-severity-high">
      <AlertTriangle className="size-3" />
      {errorMessage(e)}
    </p>
  );
}
function Tick({ v }: { v: boolean }) {
  return v ? (
    <CheckCircle2 className="size-3.5 text-severity-low" aria-label="allowed" />
  ) : (
    <XCircle className="size-3.5 text-content-dim" aria-label="denied" />
  );
}

/* Prompt 20 Part B — Access & hierarchy. Shows the synthetic police
   rank -> functional role + scope mapping, the server-enforced allow/deny
   matrix, roles + permission grants, and (SUPERADMIN only) create-credential +
   assign-role + activate controls. Scope is derived server-side. */
export function OrgAccessPanel() {
  const { role } = useRole();
  const isSuper = role === "super_admin";
  const qc = useQueryClient();

  const hierarchyQ = useQuery({ queryKey: ["org", "hierarchy"], queryFn: ({ signal }) => api.org.hierarchy(signal) });
  const matrixQ = useQuery({ queryKey: ["org", "matrix"], queryFn: ({ signal }) => api.org.scopeMatrix(signal) });
  const rolesQ = useQuery({ queryKey: ["org", "roles"], queryFn: ({ signal }) => api.org.roles(signal) });
  const usersQ = useQuery({ queryKey: ["org", "users"], queryFn: ({ signal }) => api.org.users(signal) });

  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [newRole, setNewRole] = useState<string>("investigator");

  const createMut = useMutation({
    mutationFn: () => api.org.createUser({ username: username.trim(), display_name: displayName.trim() || undefined, role: newRole }),
    onSuccess: () => {
      setUsername("");
      setDisplayName("");
      qc.invalidateQueries({ queryKey: ["org", "users"] });
    },
  });
  const assignMut = useMutation({
    mutationFn: ({ userId, r }: { userId: number; r: string }) => api.org.assignRole(userId, r),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["org", "users"] }),
  });
  const activeMut = useMutation({
    mutationFn: ({ userId, v }: { userId: number; v: boolean }) => api.org.setActive(userId, v),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["org", "users"] }),
  });

  return (
    <div className="space-y-4">
      {/* Rank -> role/scope mapping */}
      <SectionCard
        title="Police rank → functional role + scope"
        description="Synthetic mapping of the DGP → IGP → DIG → SP → Station Chief → Officer hierarchy to DRISHTI's six functional roles and an organizational scope. Real directory/SSO sync is post-hackathon.">
        {hierarchyQ.isLoading ? <p className="text-12 text-content-dim">Loading…</p>
          : hierarchyQ.error ? <Err e={hierarchyQ.error} />
          : hierarchyQ.data ? (
            <div className="overflow-x-auto">
              <table className="w-full text-12">
                <thead className="text-content-dim">
                  <tr className="border-b border-hairline text-left">
                    <th className="py-1.5 pr-3 font-medium">Rank / assignment</th>
                    <th className="py-1.5 pr-3 font-medium">Functional role</th>
                    <th className="py-1.5 pr-3 font-medium">Scope</th>
                  </tr>
                </thead>
                <tbody>
                  {hierarchyQ.data.mappings.map((m) => (
                    <tr key={m.rank} className="border-b border-hairline/60">
                      <td className="py-1.5 pr-3 text-content">{m.rank} <span className="text-content-dim">({m.abbr})</span></td>
                      <td className="py-1.5 pr-3"><Badge variant="neutral">{m.functional_role}</Badge></td>
                      <td className="py-1.5 pr-3 text-content-dim">{m.scope_level}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
      </SectionCard>

      {/* Allow/deny matrix */}
      <SectionCard
        title="Server-enforced allow/deny matrix"
        description="Role × action decisions enforced server-side. A geographically-scoped seat is additionally confined to its assigned district/unit; a browser district header is never trusted.">
        {matrixQ.isLoading ? <p className="text-12 text-content-dim">Loading…</p>
          : matrixQ.error ? <Err e={matrixQ.error} />
          : matrixQ.data ? (
            <div className="overflow-x-auto">
              <table className="w-full text-12">
                <thead className="text-content-dim">
                  <tr className="border-b border-hairline text-left">
                    <th className="py-1.5 pr-3 font-medium">Role</th>
                    {matrixQ.data.actions.map((a) => (
                      <th key={a} className="py-1.5 pr-3 font-medium">{a.replace(/_/g, " ")}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {matrixQ.data.roles.map((r) => (
                    <tr key={r} className="border-b border-hairline/60">
                      <td className="py-1.5 pr-3 font-medium text-content">{r}</td>
                      {matrixQ.data!.actions.map((a) => (
                        <td key={a} className="py-1.5 pr-3"><Tick v={!!matrixQ.data!.matrix[r]?.[a]} /></td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
      </SectionCard>

      {/* SUPERADMIN: create credential + assign role */}
      <SectionCard
        title="Credentials & role assignment"
        description="SUPERADMIN provisions a synthetic application credential and assigns it a functional role and scope. The sign-in secret is owned by Catalyst Authentication (fresh invite → must reset).">
        {!isSuper ? (
          <div className="flex items-center gap-2 text-12 text-content-dim">
            <ShieldCheck className="size-3.5" />
            Credential provisioning is a super-admin action. Switch to the Super Admin demo view to manage users.
          </div>
        ) : (
          <form
            className="mb-3 flex flex-wrap items-end gap-2"
            onSubmit={(e) => { e.preventDefault(); if (username.trim()) createMut.mutate(); }}
          >
            <label className="flex flex-col text-11 text-content-dim">
              Username
              <input
                className="mt-0.5 rounded border border-hairline bg-surface-1 px-2 py-1 text-13 text-content"
                value={username} onChange={(e) => setUsername(e.target.value)}
                placeholder="io.new" aria-label="username" />
            </label>
            <label className="flex flex-col text-11 text-content-dim">
              Display name
              <input
                className="mt-0.5 rounded border border-hairline bg-surface-1 px-2 py-1 text-13 text-content"
                value={displayName} onChange={(e) => setDisplayName(e.target.value)}
                placeholder="PSI New Officer" aria-label="display name" />
            </label>
            <label className="flex flex-col text-11 text-content-dim">
              Role
              <select
                className="mt-0.5 rounded border border-hairline bg-surface-1 px-2 py-1 text-13 text-content"
                value={newRole} onChange={(e) => setNewRole(e.target.value)} aria-label="role">
                {ROLE_CHOICES.map((r) => <option key={r} value={r}>{r}</option>)}
              </select>
            </label>
            <Button type="submit" disabled={!username.trim() || createMut.isPending}>
              <UserPlus className="size-3.5" /> Create credential
            </Button>
            {createMut.error ? <Err e={createMut.error} /> : null}
          </form>
        )}

        {usersQ.isLoading ? <p className="text-12 text-content-dim">Loading…</p>
          : usersQ.error ? <Err e={usersQ.error} />
          : usersQ.data ? (
            <div className="overflow-x-auto">
              <table className="w-full text-12">
                <thead className="text-content-dim">
                  <tr className="border-b border-hairline text-left">
                    <th className="py-1.5 pr-3 font-medium">Credential</th>
                    <th className="py-1.5 pr-3 font-medium">Role</th>
                    <th className="py-1.5 pr-3 font-medium">Scope</th>
                    <th className="py-1.5 pr-3 font-medium">Active</th>
                    {isSuper && <th className="py-1.5 pr-3 font-medium">Manage</th>}
                  </tr>
                </thead>
                <tbody>
                  {usersQ.data.items.map((u) => (
                    <tr key={u.user_id} className="border-b border-hairline/60">
                      <td className="py-1.5 pr-3 text-content">
                        {u.username}
                        <span className="block text-11 text-content-dim">{u.display_name}</span>
                      </td>
                      <td className="py-1.5 pr-3"><Badge variant="neutral">{u.role}</Badge></td>
                      <td className="py-1.5 pr-3 text-content-dim">
                        {u.district_name ?? (u.scope_level ?? "—")}
                      </td>
                      <td className="py-1.5 pr-3"><Tick v={u.is_active} /></td>
                      {isSuper && (
                        <td className="py-1.5 pr-3">
                          <div className="flex items-center gap-1">
                            <select
                              className="rounded border border-hairline bg-surface-1 px-1 py-0.5 text-11 text-content"
                              value={u.role} aria-label={`role for ${u.username}`}
                              onChange={(e) => assignMut.mutate({ userId: u.user_id, r: e.target.value })}>
                              {ROLE_CHOICES.map((r) => <option key={r} value={r}>{r}</option>)}
                            </select>
                            <Button variant="ghost" size="sm"
                              onClick={() => activeMut.mutate({ userId: u.user_id, v: !u.is_active })}>
                              {u.is_active ? "Deactivate" : "Activate"}
                            </Button>
                          </div>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
      </SectionCard>

      {/* Roles + permission grants */}
      <SectionCard title="Roles & permission grants"
        description="Resource × action grants per functional role (drives the whitelisted-SELECT executor and the API authorization boundary).">
        {rolesQ.data ? (
          <div className="flex flex-wrap gap-2 text-11">
            {rolesQ.data.items.map((r) => (
              <div key={r.role_id} className="rounded-card border border-hairline p-2">
                <div className="mb-1 font-medium text-content">{r.role_name}</div>
                <div className="flex flex-wrap gap-1 text-content-dim">
                  {Object.entries(r.permissions).filter(([, a]) => a !== "none").map(([res, a]) => (
                    <span key={res} className="rounded bg-surface-2 px-1">{res}:{a}</span>
                  ))}
                </div>
              </div>
            ))}
            {rolesQ.data.missing_roles.length > 0 && (
              <p className="w-full text-12 text-severity-medium">
                Missing seeded roles: {rolesQ.data.missing_roles.join(", ")} (run “ensure roles”).
              </p>
            )}
          </div>
        ) : rolesQ.error ? <Err e={rolesQ.error} /> : <p className="text-12 text-content-dim">—</p>}
      </SectionCard>
    </div>
  );
}
