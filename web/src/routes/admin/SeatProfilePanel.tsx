import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Loader2, Search } from "lucide-react";
import { api } from "@/api";
import { errorMessage } from "@/api/contracts";
import type { SeatProfile, SeatProfileBody } from "@/api/endpoints/adminConsole";
import type { SeatOut } from "@/api/endpoints/org";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Field, SectionCard } from "@/routes/intake/components";
import { SCOPE_TYPE_LABELS, type ScopeType } from "@/config/roles";
import { cn } from "@/lib/utils";

/* ============================================================================
   Per-seat profile editing.

   WHAT IS EDITABLE HERE, AND WHAT IS NOT. Name, rank, designation, posting label,
   contact details, language, notes and the lead-investigator flag. Role, unit,
   district, wing, range and scope_type are deliberately absent: those are
   provisioning decisions with their own audited endpoints under Access &
   hierarchy, and accepting them on a profile form would let a display-name edit
   quietly move a seat's jurisdiction.

   `is_lead_investigator` belongs here because it is an ASSIGNMENT property — may
   this officer be recorded as the IO of record — and not a rank or a scope. A lead
   IO and an assisting constable at the same station hold identical scope, so
   nothing else on the record distinguishes them.

   Only the fields the admin actually changed are sent. The server writes only what
   it receives, so a partial edit cannot blank a rank nobody touched.
   ========================================================================== */

const LANGUAGES = [
  { value: "en", label: "English" },
  { value: "kn", label: "ಕನ್ನಡ (Kannada)" },
  { value: "hi", label: "हिन्दी (Hindi)" },
];

/** The searchable tiers, matching the seat picker: the small ones can be browsed,
 *  the 1,000 SHO and ~10,700 IO tiers must be searched. */
const TIERS: ScopeType[] = [
  "state", "wing", "range", "commissionerate", "district",
  "station", "assigned_case", "platform",
];
const BROWSABLE = new Set<ScopeType>([
  "state", "wing", "range", "commissionerate", "district", "platform",
]);

export function SeatProfilePanel() {
  const qc = useQueryClient();
  const [scope, setScope] = useState<ScopeType>("district");
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  const [selected, setSelected] = useState<number | null>(null);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(q.trim()), 250);
    return () => clearTimeout(t);
  }, [q]);

  const browsable = BROWSABLE.has(scope);
  const enabled = browsable || debounced.length >= 2;

  const seats = useQuery({
    queryKey: ["org", "seats", "admin-profile", scope, debounced],
    queryFn: ({ signal }) =>
      api.org.seats({ scope_type: scope, q: debounced || undefined, page_size: 40 }, signal),
    enabled,
    staleTime: 60_000,
  });

  return (
    <div className="space-y-4">
      <SectionCard
        title="Seat directory"
        description="Find a seat to edit. Large tiers are searchable by station, posting or officer name."
      >
        <div className="mb-3 flex flex-wrap gap-1.5">
          {TIERS.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => { setScope(t); setQ(""); }}
              aria-pressed={t === scope}
              className={cn(
                "rounded-control border px-2 py-1 text-11 transition-colors",
                t === scope
                  ? "border-primary/60 bg-primary/10 text-content"
                  : "border-hairline bg-surface text-content-dim hover:border-primary/40",
              )}
            >
              {SCOPE_TYPE_LABELS[t]}
            </button>
          ))}
        </div>

        <div className="relative mb-3">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-content-dim" />
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            aria-label="Search seats"
            placeholder={
              browsable
                ? `Filter ${SCOPE_TYPE_LABELS[scope]} seats…`
                : "Search by station, posting or officer name…"
            }
            className="pl-8"
          />
        </div>

        {!enabled ? (
          <p className="py-4 text-center text-12 text-content-dim">
            {seats.data?.scope_type_counts?.[scope]?.toLocaleString() ?? "Many"} seats.
            Type at least two characters to search.
          </p>
        ) : seats.isLoading ? (
          <p className="py-4 text-center text-12 text-content-dim">Loading seats…</p>
        ) : seats.error ? (
          <p className="text-12 text-severity-high">{errorMessage(seats.error)}</p>
        ) : (
          <SeatTable
            items={seats.data?.items ?? []}
            selected={selected}
            onSelect={setSelected}
          />
        )}
      </SectionCard>

      {selected != null && (
        <ProfileForm
          userId={selected}
          onSaved={() => {
            // The seat directory and the login picker both show these labels.
            qc.invalidateQueries({ queryKey: ["org", "seats"] });
          }}
        />
      )}
    </div>
  );
}

function SeatTable({
  items, selected, onSelect,
}: {
  items: SeatOut[]; selected: number | null; onSelect: (id: number) => void;
}) {
  if (!items.length) {
    return (
      <p className="py-4 text-center text-12 text-content-dim">
        No seats match. Postings look like “Jayanagar PS-1, Bengaluru City”.
      </p>
    );
  }
  return (
    <div className="max-h-[280px] overflow-y-auto">
      <table className="w-full text-12">
        <thead className="text-content-dim">
          <tr className="border-b border-hairline text-left">
            <th className="py-1.5 pr-3 font-medium">Officer</th>
            <th className="py-1.5 pr-3 font-medium">Rank</th>
            <th className="py-1.5 pr-3 font-medium">Posting</th>
            <th className="py-1.5 pr-3 font-medium" />
          </tr>
        </thead>
        <tbody>
          {items.map((s) => (
            <tr
              key={s.user_id}
              className={cn(
                "border-b border-hairline/60",
                selected === s.user_id && "bg-surface-2/50",
              )}
            >
              <td className="py-1.5 pr-3">
                <span className="block text-content">{s.display_name || s.username}</span>
                <span className="block text-10 text-content-dim">{s.username}</span>
              </td>
              <td className="py-1.5 pr-3 text-content-dim">{s.rank_label ?? "—"}</td>
              <td className="py-1.5 pr-3 text-content-dim">
                {s.posting_label ?? s.scope_label}
              </td>
              <td className="py-1.5 pr-3 text-right">
                <Button size="sm" variant="secondary" onClick={() => onSelect(s.user_id)}>
                  {selected === s.user_id ? "Editing" : "Edit"}
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ProfileForm({ userId, onSaved }: { userId: number; onSaved: () => void }) {
  const profile = useQuery({
    queryKey: ["admin", "seat-profile", userId],
    queryFn: ({ signal }) => api.adminConsole.seatProfile(userId, signal),
  });

  /* Only edited fields are tracked, and only those are sent. Seeding the form
     from the server and diffing it would send unchanged values back, which is
     harmless but makes the audit entry claim more was edited than was. */
  const [edits, setEdits] = useState<SeatProfileBody>({});
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setEdits({});
    setSaved(false);
  }, [userId]);

  const save = useMutation({
    mutationFn: () => api.adminConsole.updateSeatProfile(userId, edits),
    onSuccess: () => {
      setEdits({});
      setSaved(true);
      profile.refetch();
      onSaved();
    },
  });

  const d = profile.data;
  const dirty = Object.keys(edits).length > 0;

  /** Current form value: the edit if one exists, else the server value. */
  const val = <K extends keyof SeatProfile & keyof SeatProfileBody>(k: K) =>
    (edits[k] ?? d?.[k] ?? "") as string;

  const set = (k: keyof SeatProfileBody, v: string | boolean) => {
    setSaved(false);
    setEdits((prev) => ({ ...prev, [k]: v }));
  };

  const leadFlag = useMemo(
    () => edits.is_lead_investigator ?? d?.is_lead_investigator ?? false,
    [edits.is_lead_investigator, d?.is_lead_investigator],
  );

  if (profile.isLoading) {
    return (
      <SectionCard title="Seat profile">
        <p className="text-12 text-content-dim">Loading profile…</p>
      </SectionCard>
    );
  }
  if (profile.error || !d) {
    return (
      <SectionCard title="Seat profile">
        <p className="text-12 text-severity-high">{errorMessage(profile.error)}</p>
      </SectionCard>
    );
  }

  return (
    <SectionCard
      title={`Profile — ${d.display_name || d.username}`}
      description="Name, rank, contact and posting label. Role, unit and jurisdiction are set under Access & hierarchy, not here."
    >
      {/* Read-only provisioning facts, shown so the admin knows which seat this is
          without being able to change them on this form. */}
      <div className="mb-3 flex flex-wrap items-center gap-1.5 text-11">
        <Badge variant="neutral">{d.username}</Badge>
        <Badge variant="neutral">{d.role}</Badge>
        {d.scope_type && (
          <Badge variant="neutral">
            {SCOPE_TYPE_LABELS[d.scope_type as ScopeType] ?? d.scope_type}
          </Badge>
        )}
        <Badge variant={d.is_active ? "low" : "medium"}>
          {d.is_active ? "active" : "inactive"}
        </Badge>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Display name">
          <Input value={val("display_name")}
                 onChange={(e) => set("display_name", e.target.value)} />
        </Field>
        <Field label="Rank" hint="The officer's police rank. Separate from the seat's role.">
          <Input value={val("rank_label")}
                 onChange={(e) => set("rank_label", e.target.value)} />
        </Field>
        <Field label="Designation">
          <Input value={val("designation_label")}
                 onChange={(e) => set("designation_label", e.target.value)} />
        </Field>
        <Field label="Posting label" hint="Shown in the seat picker and the profile menu.">
          <Input value={val("posting_label")}
                 onChange={(e) => set("posting_label", e.target.value)} />
        </Field>
        <Field label="Email">
          <Input type="email" value={val("email")}
                 onChange={(e) => set("email", e.target.value)} />
        </Field>
        <Field label="Phone">
          <Input value={val("phone")}
                 onChange={(e) => set("phone", e.target.value)} />
        </Field>
        <Field label="Preferred language">
          <NativeSelect
            value={val("preferred_language") || "en"}
            onChange={(v) => set("preferred_language", v)}
            aria-label="Preferred language"
            options={LANGUAGES}
          />
        </Field>
      </div>

      <div className="mt-3">
        <label className="flex cursor-pointer items-start gap-2 text-12">
          <input
            type="checkbox"
            checked={leadFlag}
            onChange={(e) => set("is_lead_investigator", e.target.checked)}
            className="mt-0.5 size-3.5 shrink-0 accent-[var(--color-primary)]"
          />
          <span>
            <span className="text-content">May be the investigating officer of record</span>
            <span className="block text-11 text-content-dim">
              An assignment property, not a rank and not a scope. A lead IO and an
              assisting officer at the same station hold identical scope, so this is
              the only thing that separates them.
            </span>
          </span>
        </label>
      </div>

      <div className="mt-3">
        <Field label="Notes">
          <Input value={val("notes")} onChange={(e) => set("notes", e.target.value)} />
        </Field>
      </div>

      {save.error && (
        <p className="mt-2 flex items-start gap-1 text-11 text-severity-critical">
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
          {errorMessage(save.error)}
        </p>
      )}

      <div className="mt-3 flex items-center gap-2">
        <Button
          size="sm"
          variant="primary"
          disabled={!dirty || save.isPending}
          onClick={() => save.mutate()}
        >
          {save.isPending && <Loader2 className="size-3.5 animate-spin" />}
          Save profile
        </Button>
        {dirty && (
          <Button size="sm" variant="ghost" onClick={() => setEdits({})}>
            Discard
          </Button>
        )}
        {saved && !dirty && (
          <span className="flex items-center gap-1 text-11 text-severity-low">
            <CheckCircle2 className="size-3.5" /> Saved
          </span>
        )}
        {dirty && (
          <span className="text-10 text-content-dim">
            {Object.keys(edits).length} field(s) changed. Only these are written.
          </span>
        )}
      </div>
    </SectionCard>
  );
}
