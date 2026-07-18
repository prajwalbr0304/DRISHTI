import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { BadgeCheck, HelpCircle } from "lucide-react";
import { api } from "@/api";
import type { CaseDetailResponse, CasePerson, IntakeCaseParty } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { usePeekStore } from "@/stores/usePeekStore";

/* People sub-pages (doc 01 §4.2). Phase 2: parties are shown from canonical
   CasePartyRole records (stable identity, no name joins) when available, with a
   graceful fallback to the legacy Accused/Victim/Complainant rows for cases
   registered before canonical intake. */

function useCanonicalParties(caseId?: number) {
  return useQuery({
    queryKey: ["intake", "case-parties", caseId],
    queryFn: ({ signal }) => api.intake.caseParties(caseId!, signal),
    enabled: !!caseId,
    retry: false,
    staleTime: 60_000,
  });
}

export function ComplainantPage({ detail }: { detail: CaseDetailResponse }) {
  return <RolePeople detail={detail} role="complainant" label="Complainant" legacy={detail.complainants} />;
}
export function VictimsPage({ detail }: { detail: CaseDetailResponse }) {
  return <RolePeople detail={detail} role="victim" label="Victim" legacy={detail.victims} />;
}
export function AccusedPage({ detail }: { detail: CaseDetailResponse }) {
  return <RolePeople detail={detail} role="accused" label="Accused" legacy={detail.accused} peekable />;
}

function RolePeople({
  detail, role, label, legacy, peekable,
}: {
  detail: CaseDetailResponse;
  role: string;
  label: string;
  legacy: CasePerson[];
  peekable?: boolean;
}) {
  const partiesQ = useCanonicalParties(detail.core.case_id);
  const canonical = (partiesQ.data?.parties ?? []).filter((p) => p.role_type === role);

  if (canonical.length > 0) {
    return (
      <>
        <p className="mb-2 flex items-center gap-1.5 text-12 text-content-dim">
          <BadgeCheck className="size-3.5 text-severity-low" />
          Canonical identity records ({canonical.length})
        </p>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {canonical.map((p) => <CanonicalCard key={p.case_party_role_id} party={p} label={label} />)}
        </div>
      </>
    );
  }
  return <LegacyList people={legacy} role={label} peekable={peekable} />;
}

function CanonicalCard({ party, label }: { party: IntakeCaseParty; label: string }) {
  const name = party.is_unknown
    ? "Unknown / unidentified"
    : party.person_label ?? party.org_name ?? party.party_label ?? "—";
  const ref = party.person_ref ?? party.org_ref;
  return (
    <div className="flex flex-col rounded-card border border-hairline bg-surface p-3.5">
      <span className="flex items-center gap-1.5 text-13 font-medium text-content">
        {party.is_unknown && <HelpCircle className="size-3.5 text-content-dim" />}
        {party.canonical_person_id ? (
          <Link to={`/people/canonical/${party.canonical_person_id}`} className="text-primary hover:underline">{name}</Link>
        ) : name}
      </span>
      <span className="mt-1 flex flex-wrap items-center gap-1.5 text-12 text-content-dim">
        <Badge variant="primary" className="capitalize">{label}</Badge>
        {ref && <Badge variant="neutral" className="tnum">{ref}</Badge>}
        {party.canonical_organisation_id && <Badge variant="accent">Organisation</Badge>}
      </span>
    </div>
  );
}

function LegacyList({ people, role, peekable }: { people: CasePerson[]; role: string; peekable?: boolean }) {
  const push = usePeekStore((s) => s.push);
  if (!people.length) {
    return <p className="py-8 text-center text-13 text-content-dim">No {role.toLowerCase()}s recorded.</p>;
  }
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {people.map((p) => (
        <button key={p.id} type="button" disabled={!peekable}
          onClick={() => peekable && push({ kind: "person", id: p.id, label: p.name ?? `${role} ${p.id}`, sublabel: role })}
          className="flex flex-col rounded-card border border-hairline bg-surface p-3.5 text-left transition-colors hover:bg-surface-2 disabled:hover:bg-surface">
          <span className="text-13 font-medium text-content">{p.name ?? "—"}</span>
          <span className="mt-1 flex flex-wrap items-center gap-2 text-12 text-content-dim">
            {p.age != null && <span>Age {p.age}</span>}
            {p.person_id && <Badge variant="neutral" className="tnum">#{p.person_id}</Badge>}
            <Badge variant="neutral" className="capitalize">{role}</Badge>
          </span>
        </button>
      ))}
    </div>
  );
}
