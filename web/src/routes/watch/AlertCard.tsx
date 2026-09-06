import { useState } from "react";
import {
  BadgeCheck, Check, ChevronRight, Loader2, MapPin, Radio, Send, ShieldQuestion, Siren, X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/native-select";
import { ConfidenceChip, SeverityBadge } from "@/routes/emergency/erShared";
import type { CctvAlert, CctvDispatch, CctvDispatchProposal } from "@/api/endpoints/cctv";
import {
  DISMISS_REASON_OPTIONS, formatAge, formatEta, formatKm, geometrySourceLabel, humanise,
  NEXT_DISPATCH_STATUS,
} from "@/routes/watch/cctvFormat";
import { severityHex } from "@/routes/watch/cctvLayers";

/* ============================================================================
   The review surfaces for a CCTV alert.

   `AlertQueueRow`  — one line in the review queue.
   `AlertReviewCard` — the full card: what was detected, on which camera, how
                       confident, who produced it, and the two decisions.

   The design rule running through both: CONFIRM and DISMISS are presented as
   equally weighted choices. Dismissal is not a hidden secondary action, because
   an interface that makes "confirm" the only easy way to clear a queue will
   manufacture confirmations — and here a confirmation is what puts a police unit
   on the road. Confirm is also never a one-click dispatch: it produces a ranked
   PROPOSAL that has to be sent deliberately.
   ========================================================================== */

const STATUS_VARIANT: Record<string, "neutral" | "primary" | "critical" | "high" | "medium" | "low"> = {
  proposed: "high",
  confirmed: "critical",
  dispatched: "primary",
  dismissed: "neutral",
  resolved: "low",
};

function AlertStatusBadge({ status }: { status: string }) {
  const label = status === "proposed" ? "awaiting review" : humanise(status);
  return <Badge variant={STATUS_VARIANT[status] ?? "neutral"}>{label}</Badge>;
}

/** Provenance chip. A synthetic-replay detection must never read as a model run. */
export function ProvenanceChip({ kind }: { kind?: string | null }) {
  if (kind === "external_analytics") {
    return <Badge variant="outline">external analytics</Badge>;
  }
  return <Badge variant="neutral">synthetic replay</Badge>;
}

export function AlertQueueRow({
  alert,
  active,
  onSelect,
}: {
  alert: CctvAlert;
  active: boolean;
  onSelect: () => void;
}) {
  const accent = severityHex(alert.severity);
  return (
    <li>
      <button
        type="button"
        onClick={onSelect}
        aria-current={active ? "true" : undefined}
        className={cn(
          "flex w-full items-start gap-2.5 rounded-control border px-3 py-2 text-left transition-colors",
          active
            ? "border-primary/50 bg-primary/10"
            : "border-hairline hover:bg-surface-2",
        )}
      >
        <span
          className="mt-1 size-2 shrink-0 rounded-full"
          style={{ background: accent }}
          aria-hidden="true"
        />
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-1.5">
            <span className="truncate text-13 font-semibold text-content">{alert.title}</span>
            <AlertStatusBadge status={alert.status} />
          </span>
          <span className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-11 text-content-dim">
            <span className="truncate">{alert.camera_name ?? `Camera ${alert.camera_id}`}</span>
            <span aria-hidden="true">·</span>
            <span>{formatAge(alert.age_seconds)}</span>
            <span aria-hidden="true">·</span>
            <span>{Math.round(alert.confidence * 100)}% confident</span>
            {alert.quality_flag === "low_confidence" && (
              <Badge variant="high" className="ml-0.5">low confidence</Badge>
            )}
          </span>
        </span>
        <ChevronRight className="mt-1 size-4 shrink-0 text-content-dim" />
      </button>
    </li>
  );
}

/** The ranked nearest-responder proposal, with its reasoning visible. */
function DispatchProposalBlock({
  proposal,
  dispatch,
  canDispatch,
  busy,
  onAdvance,
  onPropose,
}: {
  proposal?: CctvDispatchProposal | null;
  dispatch?: CctvDispatch | null;
  canDispatch: boolean;
  busy: boolean;
  onAdvance: (d: CctvDispatch, next: string) => void;
  onPropose: () => void;
}) {
  const active = dispatch ?? proposal?.dispatch ?? null;
  const source = active?.reason?.geometry_source ?? proposal?.geometry_source;

  if (!active) {
    return (
      <div className="rounded-control border border-hairline bg-surface-2/40 p-3">
        <p className="text-12 font-semibold text-content">No responder assigned</p>
        <p className="mt-1 text-11 text-content-dim">
          {proposal?.detail
            ?? "Propose the nearest responder to see the ranked options and their distances."}
        </p>
        {canDispatch && (
          <Button size="sm" variant="outline" className="mt-2" disabled={busy}
                  onClick={onPropose}>
            {busy ? <Loader2 className="animate-spin" /> : <Radio />}
            Find nearest responder
          </Button>
        )}
      </div>
    );
  }

  const next = NEXT_DISPATCH_STATUS[active.status];
  const isProposal = active.status === "proposed";

  return (
    <div
      className={cn(
        "rounded-control border p-3",
        isProposal ? "border-hairline bg-surface-2/40" : "border-primary/40 bg-primary/5",
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        <MapPin className="size-3.5 shrink-0 text-primary" />
        <span className="text-13 font-semibold text-content">{active.unit_name}</span>
        {active.unit_kind && <Badge variant="outline">{humanise(active.unit_kind)}</Badge>}
        <Badge variant={isProposal ? "neutral" : "primary"}>{humanise(active.status)}</Badge>
      </div>

      <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-11">
        <div className="flex justify-between gap-2">
          <dt className="text-content-dim">Distance</dt>
          <dd className="font-medium tabular-nums text-content">
            {formatKm(active.distance_km)}
          </dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt className="text-content-dim">Est. travel</dt>
          <dd className="font-medium tabular-nums text-content">
            {formatEta(active.eta_minutes)}
          </dd>
        </div>
      </dl>

      {/* Why this responder — the ranking is never a black box. */}
      <p className="mt-2 text-11 leading-relaxed text-content-dim">
        Ranked from {geometrySourceLabel(source)}
        {proposal?.considered ? ` across ${proposal.considered} candidates` : ""}
        {active.reason?.avg_speed_kmh
          ? `. Travel time assumes ${active.reason.avg_speed_kmh} km/h urban average (${active.reason.eta_assumptions_version}) — it is an estimate, not a live traffic route.`
          : "."}
      </p>
      {proposal?.fallback_reason && (
        <p className="mt-1 text-11 text-severity-high">{proposal.fallback_reason}</p>
      )}

      {proposal?.alternatives?.length ? (
        <details className="mt-2">
          <summary className="cursor-pointer text-11 font-medium text-content-dim hover:text-content">
            {proposal.alternatives.length} other responder
            {proposal.alternatives.length === 1 ? "" : "s"} in range
          </summary>
          <ul className="mt-1 space-y-0.5">
            {proposal.alternatives.map((alt) => (
              <li key={`${alt.unit_name}-${alt.distance_km}`}
                  className="flex justify-between gap-2 text-11 text-content-dim">
                <span className="truncate">{alt.unit_name}</span>
                <span className="shrink-0 tabular-nums">{formatKm(alt.distance_km)}</span>
              </li>
            ))}
          </ul>
        </details>
      ) : null}

      {canDispatch && next && (
        <Button
          size="sm"
          variant={isProposal ? "primary" : "outline"}
          className="mt-2.5"
          disabled={busy}
          onClick={() => onAdvance(active, next)}
        >
          {busy ? <Loader2 className="animate-spin" /> : isProposal ? <Send /> : <Check />}
          {isProposal ? `Dispatch ${active.unit_name}` : `Mark ${humanise(next)}`}
        </Button>
      )}
      {isProposal && (
        <p className="mt-1.5 text-11 text-content-dim">
          Nothing has been sent yet. Dispatching records a second confirmation
          against your name.
        </p>
      )}
    </div>
  );
}

export function AlertReviewCard({
  alert,
  dispatches,
  proposal,
  canReview,
  canDispatch,
  confirming,
  dismissing,
  dispatching,
  errorText,
  onConfirm,
  onDismiss,
  onPropose,
  onAdvanceDispatch,
  onFocusMap,
}: {
  alert: CctvAlert;
  dispatches: CctvDispatch[];
  proposal?: CctvDispatchProposal | null;
  canReview: boolean;
  canDispatch: boolean;
  confirming: boolean;
  dismissing: boolean;
  dispatching: boolean;
  errorText?: string | null;
  onConfirm: (note?: string) => void;
  onDismiss: (reason: string, note?: string) => void;
  onPropose: () => void;
  onAdvanceDispatch: (d: CctvDispatch, next: string) => void;
  onFocusMap?: () => void;
}) {
  const [note, setNote] = useState("");
  const [reason, setReason] = useState("");
  const [mode, setMode] = useState<"idle" | "dismiss">("idle");
  const accent = severityHex(alert.severity);
  const pending = alert.status === "proposed";
  const activeDispatch = dispatches.find(
    (d) => !["closed", "cancelled"].includes(d.status),
  ) ?? dispatches[0] ?? null;

  return (
    <div className="flex flex-col gap-3">
      {/* headline */}
      <div className="flex items-start gap-2.5 border-l-4 pl-3" style={{ borderColor: accent }}>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <Siren className="size-4 shrink-0" style={{ color: accent }} />
            <h3 className="text-heading-m font-bold text-content">{alert.title}</h3>
            <AlertStatusBadge status={alert.status} />
          </div>
          <p className="mt-1 text-12 text-content-dim">
            {alert.camera_name ?? `Camera ${alert.camera_id}`}
            {alert.location_label ? ` — near ${alert.location_label}` : ""}
          </p>
          <p className="mt-0.5 text-11 text-content-dim">{formatAge(alert.age_seconds)}</p>
        </div>
        {onFocusMap && (
          <Button size="icon-sm" variant="ghost" onClick={onFocusMap}
                  aria-label="Centre the map on this alert">
            <MapPin />
          </Button>
        )}
      </div>

      {/* honesty row: how confident, produced by what, and quality */}
      <div className="flex flex-wrap items-center gap-1.5">
        <SeverityBadge severity={alert.severity} />
        <ConfidenceChip value={alert.confidence} />
        <ProvenanceChip kind={alert.detector_kind} />
        {alert.quality_flag === "low_confidence" && (
          <Badge variant="high">low confidence — judge from the feed</Badge>
        )}
        {alert.object_count != null && (
          <Badge variant="outline">{alert.object_count} tracked</Badge>
        )}
      </div>

      {alert.detector_label && (
        <p className="text-11 text-content-dim">
          Produced by <span className="font-mono">{alert.detector_label}</span>. A
          detection is a proposal about a scene, not a finding about a person.
        </p>
      )}

      {/* review outcome, once decided */}
      {!pending && alert.reviewed_by_actor && (
        <div className="rounded-control border border-hairline bg-surface-2/40 px-3 py-2">
          <p className="flex items-center gap-1.5 text-12 text-content">
            {alert.status === "dismissed"
              ? <ShieldQuestion className="size-3.5 text-content-dim" />
              : <BadgeCheck className="size-3.5 text-severity-low" />}
            <span className="font-semibold">
              {alert.status === "dismissed" ? "Dismissed" : "Confirmed"}
            </span>
            <span className="text-content-dim">by {alert.reviewed_by_actor}</span>
          </p>
          {alert.dismiss_reason && (
            <p className="mt-1 text-11 text-content-dim">
              Reason: {humanise(alert.dismiss_reason)}
            </p>
          )}
          {alert.review_note && (
            <p className="mt-1 text-11 italic text-content-dim">“{alert.review_note}”</p>
          )}
        </div>
      )}

      {/* the two decisions */}
      {pending && canReview && (
        <div className="space-y-2 rounded-control border border-hairline p-3">
          <p className="text-12 font-semibold text-content">
            Does the feed show what was detected?
          </p>
          <label className="block">
            <span className="sr-only">Reviewer note</span>
            <input
              type="text"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              maxLength={2000}
              placeholder="Optional note recorded with your decision"
              className="h-8 w-full rounded-control border border-hairline bg-surface-2 px-2.5 text-12 text-content placeholder:text-content-dim focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
            />
          </label>

          {mode === "idle" ? (
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="primary" disabled={confirming || dismissing}
                      onClick={() => onConfirm(note.trim() || undefined)}>
                {confirming ? <Loader2 className="animate-spin" /> : <Check />}
                Confirm incident
              </Button>
              <Button size="sm" variant="outline" disabled={confirming || dismissing}
                      onClick={() => setMode("dismiss")}>
                <X />
                Dismiss
              </Button>
            </div>
          ) : (
            <div className="space-y-2">
              <NativeSelect
                aria-label="Dismissal reason"
                value={reason}
                onChange={setReason}
                options={DISMISS_REASON_OPTIONS}
                placeholder="Why is this not actionable?"
              />
              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant="danger" disabled={!reason || dismissing}
                        onClick={() => onDismiss(reason, note.trim() || undefined)}>
                  {dismissing ? <Loader2 className="animate-spin" /> : <X />}
                  Record dismissal
                </Button>
                <Button size="sm" variant="ghost" disabled={dismissing}
                        onClick={() => { setMode("idle"); setReason(""); }}>
                  Back
                </Button>
              </div>
              <p className="text-11 text-content-dim">
                The reason is stored against the camera and class — it is how this
                detector's false-positive rate is measured.
              </p>
            </div>
          )}
          <p className="text-11 text-content-dim">
            Confirming records a fresh authenticated confirmation against your name.
            It does not send a unit on its own.
          </p>
        </div>
      )}

      {pending && !canReview && (
        <p className="text-12 text-content-dim">
          You have read-only access to this wall. A reviewer must confirm or dismiss
          this alert.
        </p>
      )}

      {/* dispatch */}
      {(alert.status === "confirmed" || alert.status === "dispatched"
        || alert.status === "resolved" || dispatches.length > 0) && (
        <div className="space-y-2">
          <p className="text-12 font-semibold text-content">Response</p>
          <DispatchProposalBlock
            proposal={proposal}
            dispatch={activeDispatch}
            canDispatch={canDispatch}
            busy={dispatching}
            onAdvance={onAdvanceDispatch}
            onPropose={onPropose}
          />
        </div>
      )}

      {errorText && <p className="text-12 text-severity-critical">{errorText}</p>}
    </div>
  );
}
