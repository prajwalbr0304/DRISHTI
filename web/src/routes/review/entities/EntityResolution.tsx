import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, GitMerge, Lock, Search, Sparkles, UserPlus, Users2, X } from "lucide-react";
import { api } from "@/api";
import { errorMessage } from "@/api/contracts";
import type { IdentityCandidate, IdentityCandidatePersonRef } from "@/api/types";
import { roleCan } from "@/config/roles";
import { useRole } from "@/providers/RoleProvider";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { PageHeader } from "@/components/common/PageHeader";
import { EmptyState } from "@/components/common/EmptyState";
import { SectionCard } from "@/routes/intake/components";

/* Entity-resolution review inbox (Phase 4). Candidates are PROPOSALS — accepting
   one performs a reviewed, reversible merge. Nothing is ever auto-merged. The
   demo view/role is UX simulation, not authentication. */


export function EntityResolution() {
  const { role } = useRole();
  const qc = useQueryClient();
  const actor = `demo.${role}`;
  const canReview = roleCan(role, "entity_review");
  const [banner, setBanner] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const candidatesQ = useQuery({
    queryKey: ["identity", "candidates", "pending"],
    queryFn: ({ signal }) => api.identity.candidates({ status: "pending", page_size: 50 }, signal),
    enabled: roleCan(role, "entity_review"),
  });
  const statsQ = useQuery({
    queryKey: ["identity", "stats"],
    queryFn: ({ signal }) => api.identity.stats(signal),
    enabled: roleCan(role, "entity_review"),
    retry: false,
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["identity", "candidates"] });
    qc.invalidateQueries({ queryKey: ["identity", "stats"] });
  };

  const reviewM = useMutation({
    mutationFn: (v: { id: number; action: "accept" | "reject" | "create_new"; winner?: number }) =>
      api.identity.reviewCandidate(v.id, { action: v.action, winner_canonical_person_id: v.winner, actor,
        reason: `resolution ${v.action} via demo review` }),
    onSuccess: (res) => {
      setErr(null);
      setBanner(res.merge
        ? `Merged #${res.merge.loser_canonical_person_id} into #${res.merge.winner_canonical_person_id} (reversible).`
        : `Candidate ${res.status}.`);
      invalidate();
    },
    onError: (e) => setErr(errorMessage(e)),
  });

  const generateM = useMutation({
    mutationFn: () => api.identity.generate({ limit: 25, min_score: 0.3, actor }),
    onSuccess: (res) => { setErr(null); setBanner(`Generated ${res.created} candidate(s) for review.`); invalidate(); },
    onError: (e) => setErr(errorMessage(e)),
  });

  if (!roleCan(role, "entity_review")) {
    return (
      <div><PageHeader title="Entity resolution" />
        <EmptyState icon={Lock} title="Not available for this role"
          description="Entity resolution handles individual identity records and is not available to this role." /></div>
    );
  }

  const candidates = candidatesQ.data?.items ?? [];

  return (
    <div>
      <PageHeader title="Entity resolution"
        description="Review proposed person matches. Accepting a match performs a reviewed, reversible merge — nothing is auto-merged." />

      {banner && <div className="mb-3 rounded-card border border-severity-low/40 bg-severity-low/5 px-3 py-2 text-13 text-content">{banner}</div>}
      {err && <div className="mb-3 flex items-center gap-1.5 rounded-card border border-severity-high/40 bg-severity-high/5 px-3 py-2 text-13 text-severity-high"><AlertTriangle className="size-4" />{err}</div>}

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2 space-y-4">
          <SectionCard
            title={`Pending candidates (${candidatesQ.data?.total ?? candidates.length})`}
            description="Same/similar name is a review signal only — distinct people stay separate until a reviewer decides.">
            <div className="mb-3 flex items-center gap-2">
              <Button size="sm" variant="secondary" disabled={!canReview || generateM.isPending}
                onClick={() => generateM.mutate()}>
                <Sparkles className="size-3.5" /> Generate candidates
              </Button>
              {!canReview && <span className="text-12 text-content-dim">Review actions need the Supervisor demo view.</span>}
            </div>
            {candidatesQ.isLoading ? (
              <p className="text-12 text-content-dim">Loading…</p>
            ) : candidatesQ.error ? (
              <p className="flex items-center gap-1 text-12 text-severity-high"><AlertTriangle className="size-3" />{errorMessage(candidatesQ.error)}</p>
            ) : candidates.length === 0 ? (
              <EmptyState icon={Users2} title="No pending candidates" description="Generate candidates or resolve new intake to populate the queue." />
            ) : (
              <ul className="space-y-3">
                {candidates.map((c) => (
                  <CandidateRow key={c.entity_resolution_candidate_id} c={c} canReview={canReview}
                    busy={reviewM.isPending}
                    onReview={(action, winner) => reviewM.mutate({ id: c.entity_resolution_candidate_id, action, winner })} />
                ))}
              </ul>
            )}
          </SectionCard>
        </div>

        <div className="space-y-4">
          {statsQ.data && (
            <SectionCard title="Canonical identity coverage" description="Live counts from the identity layer.">
              <dl className="space-y-1.5 text-12">
                <Stat label="Canonical persons" value={statsQ.data.canonical_person} />
                <Stat label="Merged (resolved)" value={statsQ.data.canonical_person_merged} />
                <Stat label="Case-party roles" value={statsQ.data.case_party_role} />
                <Stat label="Graph persons linked" value={statsQ.data.graph_person_linked} of={statsQ.data.graph_person_nodes} />
                <Stat label="Edges with provenance" value={statsQ.data.network_edges_provenanced} of={statsQ.data.network_edges} />
                <Stat label="Pending candidates" value={statsQ.data.resolution_candidates_pending} />
                <Stat label="Merge/split history" value={statsQ.data.merge_history} />
              </dl>
            </SectionCard>
          )}
          <PersonSearchPanel />
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value, of }: { label: string; value?: number; of?: number }) {
  return (
    <div className="flex items-center justify-between">
      <dt className="text-content-dim">{label}</dt>
      <dd className="tnum text-content">{value ?? "—"}{of != null && <span className="text-content-dim"> / {of}</span>}</dd>
    </div>
  );
}

function PersonChip({ p, side }: { p: IdentityCandidatePersonRef; side: string }) {
  return (
    <div className="flex-1 rounded-card border border-hairline bg-surface-2 p-2.5">
      <div className="mb-1 text-[11px] uppercase tracking-wide text-content-dim">{side}</div>
      <Link to={`/people/canonical/${p.canonical_person_id}`} className="text-13 font-medium text-primary hover:underline">
        {p.display_label ?? "Unknown"}
      </Link>
      <div className="mt-1 flex flex-wrap items-center gap-1.5 text-12 text-content-dim">
        <Badge variant="neutral" className="tnum">{p.public_ref}</Badge>
        <span>{p.case_count ?? 0} case(s)</span>
      </div>
    </div>
  );
}

function CandidateRow({ c, canReview, busy, onReview }: {
  c: IdentityCandidate; canReview: boolean; busy: boolean;
  onReview: (action: "accept" | "reject" | "create_new", winner?: number) => void;
}) {
  const feat = c.match_features ?? {};
  return (
    <li className="rounded-card border border-hairline bg-surface p-3">
      <div className="mb-2 flex items-center gap-2 text-12 text-content-dim">
        <Badge variant="neutral" className="capitalize">{c.method}</Badge>
        {c.score != null && <span>score {c.score.toFixed(2)}</span>}
        {typeof feat.feature === "string" && <span>· {feat.feature}</span>}
      </div>
      <div className="flex flex-col items-stretch gap-2 sm:flex-row sm:items-center">
        <PersonChip p={c.person_a} side="Person A" />
        <span className="self-center text-11 text-content-dim">vs</span>
        <PersonChip p={c.person_b} side="Person B" />
      </div>
      <div className="mt-2 flex flex-wrap gap-2">
        <Button size="sm" variant="primary" disabled={!canReview || busy}
          onClick={() => onReview("accept", c.person_a.canonical_person_id)}>
          <GitMerge className="size-3.5" /> Same person — merge into A
        </Button>
        <Button size="sm" variant="ghost" disabled={!canReview || busy}
          onClick={() => onReview("create_new")}>Different people</Button>
        <Button size="sm" variant="ghost" disabled={!canReview || busy}
          onClick={() => onReview("reject")}><X className="size-3.5" /> Reject</Button>
      </div>
    </li>
  );
}

function PersonSearchPanel() {
  const { role } = useRole();
  const actor = `demo.${role}`;
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [term, setTerm] = useState("");
  const [newName, setNewName] = useState("");
  const [msg, setMsg] = useState<string | null>(null);

  const searchQ = useQuery({
    queryKey: ["identity", "persons", "search", term],
    queryFn: ({ signal }) => api.identity.searchPersons({ q: term, page_size: 10 }, signal),
    enabled: term.length >= 2,
  });
  const createM = useMutation({
    mutationFn: () => api.identity.createPerson({ display_label: newName.trim(), actor }),
    onSuccess: (p) => { setMsg(`Created ${p.public_ref}.`); setNewName(""); qc.invalidateQueries({ queryKey: ["identity", "stats"] }); },
    onError: (e) => setMsg(errorMessage(e)),
  });

  return (
    <SectionCard title="Find or create a person" description="Search canonical persons or register a new synthetic identity.">
      <form className="mb-2 flex gap-2" onSubmit={(e) => { e.preventDefault(); setTerm(q.trim()); }}>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name or ref…"
          className="h-8 flex-1 rounded-control border border-hairline bg-surface px-2 text-13" />
        <Button size="sm" type="submit" variant="secondary"><Search className="size-3.5" /></Button>
      </form>
      {term.length >= 2 && (
        <ul className="mb-3 divide-y divide-hairline rounded-control border border-hairline">
          {(searchQ.data?.items ?? []).length === 0 ? (
            <li className="px-2 py-2 text-12 text-content-dim">{searchQ.isLoading ? "Searching…" : "No matches."}</li>
          ) : (
            searchQ.data!.items.map((p) => (
              <li key={p.canonical_person_id} className="flex items-center justify-between px-2 py-1.5">
                <Link to={`/people/canonical/${p.canonical_person_id}`} className="text-13 text-primary hover:underline">
                  {p.display_label ?? "Unknown"}
                </Link>
                <span className="flex items-center gap-1.5 text-12 text-content-dim">
                  <Badge variant="neutral" className="tnum">{p.public_ref}</Badge>
                  {p.resolution_status !== "canonical" && <Badge variant="medium">{p.resolution_status}</Badge>}
                </span>
              </li>
            ))
          )}
        </ul>
      )}
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (newName.trim()) createM.mutate(); }}>
        <input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="New person label…"
          className="h-8 flex-1 rounded-control border border-hairline bg-surface px-2 text-13" />
        <Button size="sm" type="submit" variant="secondary" disabled={!newName.trim() || createM.isPending}>
          <UserPlus className="size-3.5" /> Create
        </Button>
      </form>
      {msg && <p className="mt-1.5 text-12 text-content-dim">{msg}</p>}
    </SectionCard>
  );
}
