import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle, ArrowLeft, BadgeCheck, GitMerge, ScanFace, Undo2, UserCog,
} from "lucide-react";
import { api } from "@/api";
import { errorMessage } from "@/api/contracts";
import type { IdentityPersonDetail } from "@/api/types";
import { roleCan } from "@/config/roles";
import { useRole } from "@/providers/RoleProvider";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { PageHeader } from "@/components/common/PageHeader";
import { EmptyState } from "@/components/common/EmptyState";
import { FaceEnrolDialog } from "@/components/face/FaceEnrolDialog";
import { usePersonFaces } from "@/components/face/faceShared";
import { SectionCard } from "@/routes/intake/components";

const SENS: Record<string, "neutral" | "low" | "medium" | "high"> = {
  public: "neutral", demo_normal: "low", restricted: "high",
};

export function CanonicalProfile() {
  const { cpid } = useParams();
  const id = Number(cpid);
  const { role } = useRole();
  const actor = `demo.${role}`;
  const canReview = roleCan(role, "entity_review");
  const qc = useQueryClient();
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [alias, setAlias] = useState("");
  const [mergeLoser, setMergeLoser] = useState("");
  const [faceOpen, setFaceOpen] = useState(false);
  const facesQ = usePersonFaces(Number.isFinite(id) ? id : null);
  const faceCount = (facesQ.data?.faces ?? []).filter((f) => !f.is_archived).length;

  const q = useQuery({
    queryKey: ["identity", "person", id],
    queryFn: ({ signal }) => api.identity.getPerson(id, signal),
    enabled: Number.isFinite(id) && roleCan(role, "case_read"),
    retry: false,
  });

  const refresh = () => qc.invalidateQueries({ queryKey: ["identity", "person", id] });
  const wrap = <T,>(p: Promise<T>, ok: (r: T) => string) =>
    p.then((r) => { setErr(null); setMsg(ok(r)); refresh(); }).catch((e) => setErr(errorMessage(e)));

  const addAliasM = useMutation({
    mutationFn: () => api.identity.addAlias(id, { alias_name: alias.trim(), alias_type: "aka", actor }),
    onSuccess: () => { setErr(null); setMsg("Alias added."); setAlias(""); refresh(); },
    onError: (e) => setErr(errorMessage(e)),
  });
  const mergeM = useMutation({
    mutationFn: () => api.identity.merge(id, { loser_canonical_person_id: Number(mergeLoser), actor,
      reason: "manual merge via profile" }),
    onSuccess: (r) => { setErr(null); setMsg(`Merged #${r.loser_canonical_person_id} into this person (reversible).`); setMergeLoser(""); refresh(); },
    onError: (e) => setErr(errorMessage(e)),
  });

  if (!roleCan(role, "case_read")) {
    return <div><PageHeader title="Canonical profile" /><EmptyState icon={AlertTriangle} title="Not available for this role" description="Individual identity records are not available to this role." /></div>;
  }
  if (q.isLoading) return <div><PageHeader title="Canonical profile" /><p className="text-13 text-content-dim">Loading…</p></div>;
  if (q.error || !q.data) return <div><PageHeader title="Canonical profile" /><EmptyState icon={AlertTriangle} title="Not found" description={q.error ? errorMessage(q.error) : `No canonical person ${id}.`} /></div>;

  const p: IdentityPersonDetail = q.data;
  const merges = p.merge_history.filter((h) => h.action === "merge");

  return (
    <div>
      <Link to="/review/entities" className="mb-2 inline-flex items-center gap-1 text-12 text-content-dim hover:text-content"><ArrowLeft className="size-3.5" /> Entity resolution</Link>
      <PageHeader title={p.display_label ?? "Unknown / unidentified"}
        description={`${p.public_ref} · canonical identity`}
        actions={
          // Reference photos are what a face scan is matched against, so the
          // control lives on the record itself rather than in a settings screen.
          <Button variant="outline" size="sm" onClick={() => setFaceOpen(true)}>
            <ScanFace /> Reference photos
            {faceCount > 0 && <Badge variant="primary" className="tnum">{faceCount}</Badge>}
          </Button>
        } />

      {msg && <div className="mb-3 rounded-card border border-severity-low/40 bg-severity-low/5 px-3 py-2 text-13">{msg}</div>}
      {err && <div className="mb-3 flex items-center gap-1.5 rounded-card border border-severity-high/40 bg-severity-high/5 px-3 py-2 text-13 text-severity-high"><AlertTriangle className="size-4" />{err}</div>}

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2 space-y-4">
          <SectionCard title="Identity">
            <div className="flex flex-wrap items-center gap-2 text-12">
              <Badge variant={p.resolution_status === "merged" ? "medium" : "low"} className="capitalize">
                <BadgeCheck className="mr-1 size-3" />{p.resolution_status}
              </Badge>
              {p.merged_into && <Badge variant="neutral">merged into #{p.merged_into}</Badge>}
              {p.is_juvenile && <Badge variant="high">juvenile (protected)</Badge>}
              {p.primary_gender_id != null && <Badge variant="neutral">gender {p.primary_gender_id}</Badge>}
              {p.approx_birth_year && <Badge variant="neutral">b. ~{p.approx_birth_year}</Badge>}
              {p.canonical_entity_id && <Badge variant="neutral" className="tnum">entity #{p.canonical_entity_id}</Badge>}
            </div>
          </SectionCard>

          <SectionCard title={`Case roles (${p.case_roles.length})`} description="Cases this canonical person is a party to (via CasePartyRole — no name matching).">
            {p.case_roles.length === 0 ? <p className="text-12 text-content-dim">No case roles.</p> : (
              <ul className="divide-y divide-hairline">
                {p.case_roles.map((r) => (
                  <li key={r.case_party_role_id} className="flex items-center justify-between py-1.5 text-13">
                    <Link to={`/cases/${r.case_master_id}`} className="tnum text-primary hover:underline">{r.crime_no ?? `Case ${r.case_master_id}`}</Link>
                    <Badge variant="neutral" className="capitalize">{r.role_type}</Badge>
                  </li>
                ))}
              </ul>
            )}
          </SectionCard>

          <SectionCard title="Attributes" description="Aliases, identifiers, contacts and addresses — each sensitivity-classified.">
            <AttrGroup title="Aliases" items={p.aliases.map((a) => ({ k: a.person_alias_id, main: a.alias_name, tag: a.alias_type }))} />
            <AttrGroup title="Identifiers" items={p.identifiers.map((i) => ({ k: i.person_identifier_id, main: `${i.identifier_type}: ${i.identifier_value}`, sens: i.sensitivity }))} />
            <AttrGroup title="Contacts" items={p.contacts.map((c) => ({ k: c.person_contact_id, main: `${c.contact_type}: ${c.contact_value}`, sens: c.sensitivity }))} />
            <AttrGroup title="Addresses" items={p.addresses.map((a) => ({ k: a.person_address_id, main: a.address_text ?? "—", sens: a.sensitivity }))} />
            {canReview && (
              <form className="mt-2 flex gap-2" onSubmit={(e) => { e.preventDefault(); if (alias.trim()) addAliasM.mutate(); }}>
                <input value={alias} onChange={(e) => setAlias(e.target.value)} placeholder="Add alias (aka)…"
                  className="h-8 flex-1 rounded-control border border-hairline bg-surface px-2 text-13" />
                <Button size="sm" type="submit" variant="secondary" disabled={!alias.trim() || addAliasM.isPending}>Add alias</Button>
              </form>
            )}
          </SectionCard>
        </div>

        <div className="space-y-4">
          <SectionCard title="Resolution" description="Merges are reviewed and fully reversible.">
            {!canReview ? (
              <p className="text-12 text-content-dim">Merge/unmerge needs the Supervisor demo view.</p>
            ) : (
              <>
                <form className="mb-3 space-y-1.5" onSubmit={(e) => { e.preventDefault(); if (mergeLoser) mergeM.mutate(); }}>
                  <label className="text-12 text-content-dim">Merge another person into this one</label>
                  <div className="flex gap-2">
                    <input value={mergeLoser} onChange={(e) => setMergeLoser(e.target.value)} inputMode="numeric"
                      placeholder="loser canonical id" className="h-8 flex-1 rounded-control border border-hairline bg-surface px-2 text-13 tnum" />
                    <Button size="sm" type="submit" variant="primary" disabled={!mergeLoser || mergeM.isPending}>
                      <GitMerge className="size-3.5" /> Merge
                    </Button>
                  </div>
                </form>
                <div className="text-12 font-medium text-content-dim">Merge / split history</div>
                {p.merge_history.length === 0 ? <p className="text-12 text-content-dim">No history.</p> : (
                  <ul className="mt-1 space-y-1.5">
                    {p.merge_history.map((h) => (
                      <li key={h.entity_merge_history_id} className="flex items-center justify-between gap-2 text-12">
                        <span>
                          <Badge variant={h.action === "merge" ? "primary" : "medium"} className="mr-1 capitalize">{h.action}</Badge>
                          <span className="tnum text-content-dim">#{h.loser_canonical_person_id} → #{h.winner_canonical_person_id}</span>
                        </span>
                        {h.action === "merge" && h.winner_canonical_person_id === id && h.loser_canonical_person_id != null && (
                          <Button size="sm" variant="ghost" title="Reverse this merge"
                            onClick={() => wrap(api.identity.unmerge(id, { loser_canonical_person_id: h.loser_canonical_person_id!, actor, reason: "reviewer reversed" }),
                              (r) => `Unmerged #${r.loser_canonical_person_id} (restored).`)}>
                            <Undo2 className="size-3" /> Unmerge
                          </Button>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </>
            )}
          </SectionCard>
          <div className="flex items-center gap-1.5 rounded-card border border-hairline bg-surface-2 px-3 py-2 text-12 text-content-dim">
            <UserCog className="size-3.5" /> Demo view is UX simulation, not authentication.
          </div>
        </div>
      </div>

      <FaceEnrolDialog
        open={faceOpen}
        onOpenChange={setFaceOpen}
        canonicalPersonId={id}
        personLabel={p.display_label ?? p.public_ref}
      />
    </div>
  );
}

function AttrGroup({ title, items }: { title: string; items: { k: number; main: string; tag?: string; sens?: string }[] }) {
  return (
    <div className="mb-2">
      <div className="text-11 uppercase tracking-wide text-content-dim">{title} ({items.length})</div>
      {items.length === 0 ? <p className="text-12 text-content/60">none</p> : (
        <ul className="mt-0.5 space-y-0.5">
          {items.map((it) => (
            <li key={it.k} className="flex items-center justify-between gap-2 text-13">
              <span className="text-content">{it.main}</span>
              {it.tag && <Badge variant="neutral">{it.tag}</Badge>}
              {it.sens && <Badge variant={SENS[it.sens] ?? "neutral"}>{it.sens}</Badge>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
