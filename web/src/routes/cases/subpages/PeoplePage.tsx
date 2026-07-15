import type { CaseDetailResponse, CasePerson } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { usePeekStore } from "@/stores/usePeekStore";

/* People sub-pages: Complainant, Victims, Accused (doc 01 §4.2). Each shows
   person cards from the detail payload. The accused cards are peekable. */

export function ComplainantPage({ detail }: { detail: CaseDetailResponse }) {
  return <PersonList people={detail.complainants} role="Complainant" />;
}
export function VictimsPage({ detail }: { detail: CaseDetailResponse }) {
  return <PersonList people={detail.victims} role="Victim" />;
}
export function AccusedPage({ detail }: { detail: CaseDetailResponse }) {
  return <PersonList people={detail.accused} role="Accused" peekable />;
}

function PersonList({
  people,
  role,
  peekable,
}: {
  people: CasePerson[];
  role: string;
  peekable?: boolean;
}) {
  const push = usePeekStore((s) => s.push);
  if (!people.length) {
    return <p className="py-8 text-center text-13 text-content-dim">No {role.toLowerCase()}s recorded.</p>;
  }
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {people.map((p) => (
        <button
          key={p.id}
          type="button"
          disabled={!peekable}
          onClick={() =>
            peekable && push({ kind: "person", id: p.id, label: p.name ?? `${role} ${p.id}`, sublabel: role })
          }
          className="flex flex-col rounded-card border border-hairline bg-surface p-3.5 text-left transition-colors hover:bg-surface-2 disabled:hover:bg-surface"
        >
          <span className="text-13 font-medium text-content">{p.name ?? "—"}</span>
          <span className="mt-1 flex flex-wrap items-center gap-2 text-12 text-content-dim">
            {p.age != null && <span>Age {p.age}</span>}
            {p.person_id && (
              <Badge variant="neutral" className="tnum">
                #{p.person_id}
              </Badge>
            )}
            <Badge variant="neutral" className="capitalize">
              {role}
            </Badge>
          </span>
        </button>
      ))}
    </div>
  );
}
