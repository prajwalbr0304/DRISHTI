import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Route as RouteIcon } from "lucide-react";
import { api } from "@/api";
import { errorMessage } from "@/api/contracts";
import type { Allocation, AllocationProposal } from "@/api/endpoints/disaster";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { PageHeader } from "@/components/common/PageHeader";
import { SendToBoard } from "@/components/board/SendToBoard";
import { districtName } from "@/stores/useDisasterStore";
import { DistrictPicker, Panel, SyntheticNote, useErCapabilities } from "@/routes/emergency/erShared";

const REQ_TYPES = ["boat", "personnel", "ambulance", "relief_material", "equipment"];
const NEXT_STATUS: Record<string, string> = {
  proposed: "approved", approved: "dispatched", dispatched: "enroute",
  enroute: "onsite", onsite: "released",
};

export function Resources() {
  const qc = useQueryClient();
  const { canWrite, activeDistrict } = useErCapabilities();
  const d = activeDistrict ?? undefined;

  const resources = useQuery({ queryKey: ["er", "resources", d], queryFn: ({ signal }) => api.disaster.resources({ district_id: d }, signal) });
  const shelters = useQuery({ queryKey: ["er", "shelters", d], queryFn: ({ signal }) => api.disaster.shelters({ district_id: d }, signal) });
  const events = useQuery({ queryKey: ["er", "events", d], queryFn: ({ signal }) => api.disaster.events({ district_id: d }, signal) });
  const allocations = useQuery({ queryKey: ["er", "allocations", d], queryFn: ({ signal }) => api.disaster.allocations({ district_id: d }, signal) });

  const [eventId, setEventId] = useState("");
  const [req, setReq] = useState<Record<string, number>>({ boat: 2, personnel: 20 });
  const [proposal, setProposal] = useState<AllocationProposal | null>(null);

  const propose = useMutation({
    mutationFn: () => api.disaster.proposeAllocation({
      hazard_event_id: Number(eventId),
      required: Object.fromEntries(Object.entries(req).filter(([, v]) => v > 0)),
      max_distance_km: 150 }),
    onSuccess: (p) => { setProposal(p); qc.invalidateQueries({ queryKey: ["er", "allocations"] }); },
  });
  const transition = useMutation({
    mutationFn: ({ id, status }: { id: number; status: string }) =>
      api.disaster.transitionAllocation(id, status),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["er"] }),
  });
  const route = useMutation({
    mutationFn: (eid: number) => api.disaster.proposeRoute({ hazard_event_id: eid }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["er", "routes"] }),
  });

  return (
    <div className="space-y-4">
      <PageHeader title="Resources"
        description={`Inventory, readiness, allocation planner and dispatch lifecycle — ${districtName(activeDistrict)}`}
        actions={<DistrictPicker />} />

      {canWrite && (
        <Panel title="Allocation planner">
          <div className="flex flex-wrap items-end gap-3">
            <label className="text-12 text-content-dim">
              Hazard event
              <NativeSelect className="mt-1 w-64" aria-label="Hazard event" value={eventId} onChange={setEventId}
                options={(events.data?.events ?? []).map((e) => ({
                  value: String(e.hazard_event_id),
                  label: `#${e.hazard_event_id} ${e.hazard_code} · ${districtName(e.district_id)}` }))}
                placeholder="Select event" />
            </label>
            {REQ_TYPES.map((t) => (
              <label key={t} className="text-12 text-content-dim">
                {t}
                <Input type="number" min={0} className="mt-1 h-8 w-20 text-13"
                  value={req[t] ?? 0}
                  onChange={(e) => setReq((s) => ({ ...s, [t]: Math.max(0, Number(e.target.value) || 0) }))} />
              </label>
            ))}
            <Button size="sm" disabled={!eventId || propose.isPending} onClick={() => propose.mutate()}>
              {propose.isPending ? <Loader2 className="animate-spin" /> : null} Propose plan
            </Button>
            {eventId && (
              <Button size="sm" variant="outline" disabled={route.isPending}
                      onClick={() => route.mutate(Number(eventId))}>
                <RouteIcon /> Propose evacuation route
              </Button>
            )}
          </div>
          {propose.isError && <p className="mt-2 text-12 text-severity-critical">{errorMessage(propose.error)}</p>}
          {route.data && (
            <p className="mt-2 text-12">
              Route: <Badge variant={route.data.status === "no_route" ? "critical" : "low"}>{route.data.status}</Badge>
              {route.data.distance_km != null && <> · {route.data.distance_km} km / {route.data.est_minutes} min</>}
              {" "}<span className="text-content-dim">{route.data.notes}</span>
            </p>
          )}
          {proposal && (
            <div className="mt-3 rounded-control border border-hairline p-2">
              <div className="mb-1 flex items-center gap-2 text-12">
                <span className="font-medium text-content">Proposal ({proposal.optimizer})</span>
                {Object.keys(proposal.unmet).length > 0
                  ? <Badge variant="high">unmet: {JSON.stringify(proposal.unmet)}</Badge>
                  : <Badge variant="low">fully covered</Badge>}
              </div>
              <ul className="space-y-1 text-12">
                {proposal.proposals.map((p) => (
                  <li key={p.resource_allocation_id} className="flex items-center gap-2">
                    <span className="text-content">{p.resource_name}</span>
                    <span className="text-content-dim">×{p.quantity_allocated}</span>
                    <Badge variant="neutral">score {p.score?.toFixed(2)}</Badge>
                    <span className="text-11 text-content-dim">
                      {String((p.reason as { distance_km?: number }).distance_km ?? "")} km
                    </span>
                  </li>
                ))}
              </ul>
              {proposal.reasons.map((r, i) => <p key={i} className="mt-1 text-11 text-content-dim">{r}</p>)}
            </div>
          )}
        </Panel>
      )}

      {/* live allocations + lifecycle */}
      <Panel title="Allocations — lifecycle">
        {transition.isError && <p className="mb-2 text-12 text-severity-critical">{errorMessage(transition.error)}</p>}
        <div className="overflow-x-auto">
          <table className="w-full text-12">
            <thead className="text-content-dim">
              <tr className="border-b border-hairline text-left">
                <th className="px-2 py-1.5">#</th><th className="px-2 py-1.5">Resource</th>
                <th className="px-2 py-1.5">Qty</th><th className="px-2 py-1.5">Status</th>
                <th className="px-2 py-1.5">Action</th>
              </tr>
            </thead>
            <tbody>
              {allocations.data?.allocations.map((a) => <AllocRow key={a.resource_allocation_id} a={a}
                canWrite={canWrite}
                onAdvance={(id, status) => transition.mutate({ id, status })}
                busy={transition.isPending} />)}
              {allocations.data && allocations.data.allocations.length === 0 && (
                <tr><td colSpan={5} className="px-2 py-3 text-content-dim">No allocations yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Panel>

      <div className="grid gap-4 lg:grid-cols-2">
        {/* inventory / readiness */}
        <Panel title="Inventory &amp; readiness">
          {resources.isLoading && <Loader2 className="size-4 animate-spin text-content-dim" />}
          <div className="overflow-x-auto">
            <table className="w-full text-12">
              <thead className="text-content-dim">
                <tr className="border-b border-hairline text-left">
                  <th className="px-2 py-1.5">Resource</th><th className="px-2 py-1.5">Type</th>
                  <th className="px-2 py-1.5">Qty</th><th className="px-2 py-1.5">Status</th><th />
                </tr>
              </thead>
              <tbody>
                {resources.data?.resources.map((r) => (
                  <tr key={r.resource_id} className="border-b border-hairline/60">
                    <td className="px-2 py-1.5 text-content">{r.name}</td>
                    <td className="px-2 py-1.5 text-content-dim">{r.resource_type}</td>
                    <td className="px-2 py-1.5 tabular-nums">{r.quantity}</td>
                    <td className="px-2 py-1.5">
                      <Badge variant={r.status === "available" ? "low" : r.status === "deployed" ? "medium" : "neutral"}>
                        {r.status}
                      </Badge>
                    </td>
                    <td className="px-2 py-1.5 text-right">
                      <SendToBoard size="icon-sm" variant="ghost"
                        target={{ refTable: "Resource", refId: r.resource_id, nodeKind: "resource", label: r.name }} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>

        {/* shelters */}
        <Panel title="Relief shelters">
          {shelters.isLoading && <Loader2 className="size-4 animate-spin text-content-dim" />}
          <div className="overflow-x-auto">
            <table className="w-full text-12">
              <thead className="text-content-dim">
                <tr className="border-b border-hairline text-left">
                  <th className="px-2 py-1.5">Shelter</th><th className="px-2 py-1.5">Occupancy</th>
                  <th className="px-2 py-1.5">Status</th><th />
                </tr>
              </thead>
              <tbody>
                {shelters.data?.shelters.map((s) => {
                  const pct = s.capacity ? Math.round((s.current_occupancy / s.capacity) * 100) : 0;
                  return (
                    <tr key={s.relief_shelter_id} className="border-b border-hairline/60">
                      <td className="px-2 py-1.5 text-content">{s.name}</td>
                      <td className="px-2 py-1.5 tabular-nums">
                        {s.current_occupancy}/{s.capacity} ({pct}%)
                      </td>
                      <td className="px-2 py-1.5">
                        <Badge variant={s.status === "full" ? "high" : s.status === "closed" ? "neutral" : "low"}>
                          {s.status}
                        </Badge>
                      </td>
                      <td className="px-2 py-1.5 text-right">
                        <SendToBoard size="icon-sm" variant="ghost"
                          target={{ refTable: "ReliefShelter", refId: s.relief_shelter_id, nodeKind: "shelter", label: s.name }} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Panel>
      </div>

      <SyntheticNote />
    </div>
  );
}

function AllocRow({ a, canWrite, onAdvance, busy }: {
  a: Allocation; canWrite: boolean;
  onAdvance: (id: number, status: string) => void; busy: boolean;
}) {
  const next = NEXT_STATUS[a.status];
  return (
    <tr className="border-b border-hairline/60">
      <td className="px-2 py-1.5 tabular-nums">{a.resource_allocation_id}</td>
      <td className="px-2 py-1.5 text-content">{a.resource_name ?? a.resource_id}</td>
      <td className="px-2 py-1.5 tabular-nums">{a.quantity_allocated}</td>
      <td className="px-2 py-1.5">
        <Badge variant={a.status === "released" ? "neutral" : a.status === "onsite" ? "low" : "medium"}>
          {a.status}
        </Badge>
      </td>
      <td className="px-2 py-1.5">
        {canWrite && next && a.resource_allocation_id != null && (
          <Button size="sm" variant="outline" disabled={busy}
                  onClick={() => onAdvance(a.resource_allocation_id!, next)}>
            → {next}
          </Button>
        )}
      </td>
    </tr>
  );
}
