import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Gavel, Landmark, Plus, Scale, ShieldCheck } from "lucide-react";
import { api } from "@/api";
import { errorMessage } from "@/api/contracts";
import type { CwCourtEventInput } from "@/api/types";
import { roleCan } from "@/config/roles";
import { useRole } from "@/providers/RoleProvider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDateTime } from "@/lib/utils";
import {
  caseworkKeys, pretty, statusBadge, dispositionBadge, toISO,
  useCanWriteCasework, useCaseworkLookups,
} from "./casework/caseworkShared";

export function CourtLifecyclePage({ caseId }: { caseId: number }) {
  const { role } = useRole();
  const canWrite = useCanWriteCasework();
  const canReview = roleCan(role, "case_write");
  const qc = useQueryClient();
  const lookups = useCaseworkLookups();
  const [addingCourt, setAddingCourt] = useState(false);

  const q = useQuery({
    queryKey: caseworkKeys.court(caseId),
    queryFn: ({ signal }) => api.casework.court(caseId, signal),
  });
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: caseworkKeys.court(caseId) });
    qc.invalidateQueries({ queryKey: caseworkKeys.timeline(caseId) });
  };

  const lifecycle = useMutation({
    mutationFn: (eventType: string) => api.casework.addLifecycleEvent(caseId, { event_type: eventType }),
    onSuccess: invalidate,
  });
  const bail = useMutation({
    mutationFn: (v: { status: string }) => api.casework.addBail(caseId, { status: v.status, bail_type: "regular" }),
    onSuccess: invalidate,
  });
  const disposition = useMutation({
    mutationFn: (v: { disposition_type: string }) => api.casework.addDisposition(caseId, v),
    onSuccess: invalidate,
  });
  const outcome = useMutation({
    mutationFn: () => api.casework.addOutcome(caseId, { observation_type: "case_outcome" }),
    onSuccess: invalidate,
  });

  if (q.isLoading) return <Skeleton className="h-40 w-full" />;
  if (q.error) return <p className="text-13 text-content-dim">{errorMessage(q.error)}</p>;
  const v = q.data!;
  const canWriteCase = canWrite && !v.read_only;
  const canReviewCase = canReview && !v.read_only;

  return (
    <div className="space-y-4">
      {/* status header */}
      <div className="flex flex-wrap items-center gap-2 rounded-card border border-hairline bg-surface p-3">
        <Scale className="size-4 text-content-dim" />
        <span className="text-13 text-content-dim">Current status</span>
        <Badge variant={statusBadge(v.current_status)}>{v.current_status_label ?? pretty(v.current_status)}</Badge>
        <span className="text-12 text-content-dim">· {v.category}</span>
        {!v.has_case_version && <span className="text-11 text-content-dim">(event-backed lifecycle starts on first action)</span>}
      </div>

      {v.read_only && (
        <p className="rounded-card border border-hairline bg-surface-2/50 px-3 py-2 text-12 leading-relaxed text-content-dim">
          {v.read_only_reason ?? "This public-source procedural record is read-only."}
        </p>
      )}

      {/* lifecycle transitions */}
      {canWriteCase && v.allowed_transitions.length > 0 && (
        <div className="rounded-card border border-hairline bg-surface p-3">
          <div className="mb-2 text-13 font-semibold text-content">Lifecycle actions</div>
          <div className="flex flex-wrap gap-2">
            {v.allowed_transitions.map((t) => (
              <Button key={`${t.event_type}-${t.to_status}`} variant="outline" size="sm"
                      disabled={lifecycle.isPending}
                      onClick={() => lifecycle.mutate(t.event_type)} title={t.description ?? ""}>
                {t.label}
              </Button>
            ))}
          </div>
          {lifecycle.error && <p className="mt-2 text-12 text-severity-critical">{errorMessage(lifecycle.error)}</p>}
        </div>
      )}

      {/* court events */}
      <div className="rounded-card border border-hairline bg-surface p-3">
        <div className="flex items-center justify-between">
          <h4 className="flex items-center gap-1.5 text-13 font-semibold text-content">
            <Landmark className="size-3.5" /> Court events ({v.court_events.length})
          </h4>
          {canWriteCase && <Button variant="ghost" size="sm" onClick={() => setAddingCourt((x) => !x)}><Plus /> Court event</Button>}
        </div>
        {addingCourt && (
          <AddCourtEvent caseId={caseId} onDone={() => { setAddingCourt(false); invalidate(); }} />
        )}
        <div className="mt-2 space-y-1">
          {v.court_events.map((ce) => (
            <div key={ce.court_event_id} className="flex flex-wrap items-center gap-2 text-13">
              <Badge variant="neutral" className="capitalize">{pretty(ce.event_type)}</Badge>
              <span className="text-content-dim">
                {ce.court_name ?? (ce.court_reference_kind === "unasserted" ? "Court not asserted in curated record" : "")}
              </span>
              {ce.outcome && <span className="text-content">· {ce.outcome}</span>}
              {ce.occurred_at && <span className="text-12 text-content-dim">· {formatDateTime(ce.occurred_at)}</span>}
            </div>
          ))}
          {v.court_events.length === 0 && <p className="text-12 text-content-dim">No court events.</p>}
        </div>
      </div>

      {/* bail */}
      <div className="rounded-card border border-hairline bg-surface p-3">
        <div className="flex items-center justify-between">
          <h4 className="flex items-center gap-1.5 text-13 font-semibold text-content"><Gavel className="size-3.5" /> Bail ({v.bail_events.length})</h4>
          {canWriteCase && (
            <div className="flex gap-1">
              <Button variant="ghost" size="sm" onClick={() => bail.mutate({ status: "granted" })} disabled={bail.isPending}>Grant</Button>
              <Button variant="ghost" size="sm" onClick={() => bail.mutate({ status: "rejected" })} disabled={bail.isPending}>Reject</Button>
            </div>
          )}
        </div>
        <div className="mt-1 space-y-1">
          {v.bail_events.map((b) => (
            <div key={b.bail_event_id} className="text-13">
              <Badge variant={b.status === "granted" ? "low" : b.status === "rejected" ? "critical" : "neutral"}>{pretty(b.status)}</Badge>
              <span className="ml-2 text-content-dim">{b.person_label ?? ""} {b.bail_type ?? ""}</span>
            </div>
          ))}
          {v.bail_events.length === 0 && <p className="text-12 text-content-dim">No bail events.</p>}
        </div>
      </div>

      {/* disposition + outcome (supervisory) */}
      <div className="rounded-card border border-hairline bg-surface p-3">
        <div className="flex items-center justify-between">
          <h4 className="flex items-center gap-1.5 text-13 font-semibold text-content"><ShieldCheck className="size-3.5" /> Disposition & outcome</h4>
          {canReviewCase && (
            <div className="flex flex-wrap gap-1">
              {(lookups.data?.disposition_types ?? []).map((d) => (
                <Button key={d.value} variant="ghost" size="sm" disabled={disposition.isPending}
                        onClick={() => disposition.mutate({ disposition_type: d.value })}>{d.label}</Button>
              ))}
            </div>
          )}
        </div>
        {disposition.error && <p className="mt-1 text-12 text-severity-critical">{errorMessage(disposition.error)}</p>}
        <div className="mt-1 space-y-1">
          {v.dispositions.map((d) => (
            <div key={d.case_disposition_id} className="text-13">
              <Badge variant={dispositionBadge(d.disposition_type)}>{pretty(d.disposition_type)}</Badge>
              {d.is_final && <span className="ml-1 text-11 text-content-dim">final</span>}
            </div>
          ))}
          {v.dispositions.length === 0 && <p className="text-12 text-content-dim">No disposition recorded.</p>}
        </div>

        <div className="mt-3 border-t border-hairline pt-2">
          <div className="flex items-center justify-between">
            <span className="text-13 text-content">Verified outcomes ({v.outcomes.length})</span>
            {canReviewCase && (
              <Button size="sm" disabled={!v.can_record_outcome || outcome.isPending} onClick={() => outcome.mutate()}>
                Record verified outcome
              </Button>
            )}
          </div>
          {!v.can_record_outcome && (
            <p className="mt-1 text-12 text-content-dim">
              An outcome can be recorded only after a verified final event (final disposition or judgment).
            </p>
          )}
          {outcome.error && <p className="mt-1 text-12 text-severity-critical">{errorMessage(outcome.error)}</p>}
          {v.outcomes.map((o) => (
            <div key={o.outcome_observation_id} className="mt-1 text-13 text-content">
              <Badge variant="low">Verified</Badge> <span className="text-content-dim">{o.observed_at ? formatDateTime(o.observed_at) : ""}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function AddCourtEvent({ caseId, onDone }: { caseId: number; onDone: () => void }) {
  const lookups = useCaseworkLookups();
  const [eventType, setEventType] = useState("chargesheet_filed");
  const [courtId, setCourtId] = useState("");
  const [outcome, setOutcome] = useState("");
  const [occurredAt, setOccurredAt] = useState("");
  const [evidenceId, setEvidenceId] = useState("");

  const mut = useMutation({
    mutationFn: () => {
      const body: CwCourtEventInput = {
        event_type: eventType, court_id: courtId ? Number(courtId) : undefined,
        outcome: outcome.trim() || undefined, occurred_at: toISO(occurredAt),
        evidence_item_id: evidenceId ? Number(evidenceId) : undefined,
      };
      return api.casework.addCourtEvent(caseId, body);
    },
    onSuccess: onDone,
  });

  return (
    <div className="mt-2 grid grid-cols-2 gap-2 rounded-control border border-hairline bg-surface-2/40 p-3">
      <NativeSelect value={eventType} onChange={setEventType} options={lookups.data?.court_event_types ?? []}
                    placeholder="chargesheet_filed" aria-label="Court event type" />
      <NativeSelect value={courtId} onChange={setCourtId}
                    options={(lookups.data?.courts ?? []).slice(0, 200).map((c) => ({ value: String(c.id), label: c.name ?? `Court ${c.id}` }))}
                    placeholder="Court (optional)" aria-label="Court" />
      <Input value={outcome} onChange={(e) => setOutcome(e.target.value)} className="h-8" placeholder="Outcome (optional)" />
      <Input type="datetime-local" value={occurredAt} onChange={(e) => setOccurredAt(e.target.value)} className="h-8" />
      <Input value={evidenceId} onChange={(e) => setEvidenceId(e.target.value)} className="h-8 col-span-2" placeholder="Linked order/document evidence id (optional)" />
      {mut.error && <p className="col-span-2 text-12 text-severity-critical">{errorMessage(mut.error)}</p>}
      <div className="col-span-2 flex justify-end">
        <Button size="sm" onClick={() => mut.mutate()} disabled={mut.isPending}>Add court event</Button>
      </div>
    </div>
  );
}
