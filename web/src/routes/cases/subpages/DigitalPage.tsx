import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, PhoneCall, Smartphone } from "lucide-react";
import { api } from "@/api";
import { errorMessage } from "@/api/contracts";
import { cn, formatNumber } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/common/EmptyState";
import { SectionCard } from "@/routes/intake/components";
import { MoneyAlertsPanel } from "@/routes/imports/panels";

/* ============================================================================
   Case sub-page: digital + financial evidence for one case.
   CDR/device timeline with simple aggregate visualisation (by type / by day),
   imported devices + artifacts, and this case's money alerts. All reviewable.
   ========================================================================== */

export function DigitalPage({ caseId }: { caseId: number }) {
  const cdrQ = useQuery({
    queryKey: ["imports", "cdr", caseId],
    queryFn: ({ signal }) => api.imports.cdrTimeline({ case_id: caseId }, 500, signal),
  });
  const devQ = useQuery({
    queryKey: ["imports", "devices", caseId],
    queryFn: ({ signal }) => api.imports.devices({ case_id: caseId }, signal),
  });

  const maxDay = useMemo(() => {
    const vals = Object.values(cdrQ.data?.by_day ?? {});
    return vals.length ? Math.max(...vals) : 0;
  }, [cdrQ.data]);

  return (
    <div className="space-y-4">
      <SectionCard
        title="Communications (CDR / chat / IP)"
        description="Imported communication events for this case. Endpoints resolve to candidate entities pending review; a link never implies guilt."
      >
        {cdrQ.error ? (
          <EmptyState icon={AlertTriangle} title="Couldn't load communications" description={errorMessage(cdrQ.error)} />
        ) : (cdrQ.data?.total ?? 0) === 0 ? (
          <EmptyState icon={PhoneCall} title="No communication events"
            description="Import a CDR/chat/IP file (Digital & financial imports) linked to this case." />
        ) : (
          <>
            <div className="mb-3 flex flex-wrap gap-2">
              {Object.entries(cdrQ.data?.by_type ?? {}).map(([k, v]) => (
                <div key={k} className="rounded-control border border-hairline bg-surface-2 px-3 py-1.5">
                  <div className="text-16 font-semibold tnum text-content">{formatNumber(v)}</div>
                  <div className="text-11 capitalize text-content-dim">{k}</div>
                </div>
              ))}
            </div>

            {/* Simple by-day aggregate bar chart (no library — Calm Authority) */}
            {Object.keys(cdrQ.data?.by_day ?? {}).length > 0 && (
              <div className="mb-3">
                <div className="mb-1 text-12 font-medium text-content-dim">Events by day</div>
                <div className="flex items-end gap-1" style={{ height: 64 }}>
                  {Object.entries(cdrQ.data?.by_day ?? {}).map(([d, v]) => (
                    <div key={d} className="group relative flex-1" title={`${d}: ${v}`}>
                      <div className="w-full rounded-t bg-primary/70"
                        style={{ height: maxDay ? `${Math.max(4, (v / maxDay) * 60)}px` : "4px" }} />
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="max-h-72 overflow-auto rounded-control border border-hairline">
              <table className="w-full text-12">
                <thead className="sticky top-0 bg-surface-2 text-content-dim">
                  <tr>
                    <th className="px-2 py-1.5 text-left">Type</th>
                    <th className="px-2 py-1.5 text-left">When</th>
                    <th className="px-2 py-1.5 text-left">A</th>
                    <th className="px-2 py-1.5 text-left">B</th>
                    <th className="px-2 py-1.5 text-right">Dur (s)</th>
                    <th className="px-2 py-1.5 text-left">Review</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-hairline">
                  {cdrQ.data?.events.map((e) => (
                    <tr key={e.communication_event_id}>
                      <td className="px-2 py-1.5 capitalize text-content">{e.comm_type}</td>
                      <td className="px-2 py-1.5 tnum text-content-dim">{e.occurred_at?.slice(0, 16).replace("T", " ") ?? "—"}</td>
                      <td className="px-2 py-1.5 tnum text-content-dim">{e.endpoint_a ?? "—"}</td>
                      <td className="px-2 py-1.5 tnum text-content-dim">{e.endpoint_b ?? "—"}</td>
                      <td className="px-2 py-1.5 text-right tnum text-content-dim">{e.duration_sec ?? "—"}</td>
                      <td className="px-2 py-1.5">
                        <Badge variant={e.review_status === "reviewed" ? "low" : "medium"} className="capitalize">
                          {e.review_status ?? "candidate"}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </SectionCard>

      <SectionCard title="Devices" description="Imported devices and their artifacts for this case.">
        {devQ.error ? (
          <EmptyState icon={AlertTriangle} title="Couldn't load devices" description={errorMessage(devQ.error)} />
        ) : (devQ.data?.count ?? 0) === 0 ? (
          <EmptyState icon={Smartphone} title="No devices" description="Import device artifacts linked to this case." />
        ) : (
          <div className="space-y-2">
            {devQ.data?.devices.map((d) => (
              <div key={d.device_id} className="rounded-control border border-hairline bg-surface-2 p-3">
                <div className="flex items-center gap-2">
                  <Smartphone className="size-4 text-content-dim" />
                  <span className="text-13 font-medium text-content">{d.label ?? d.synthetic_identifier ?? `Device #${d.device_id}`}</span>
                  <span className="text-11 capitalize text-content-dim">{d.device_type}</span>
                </div>
                {d.artifacts.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {d.artifacts.map((a) => (
                      <span key={a.device_artifact_id}
                        className={cn("rounded border border-hairline px-1.5 py-0.5 text-11 text-content-dim")}>
                        {a.artifact_type}{a.synthetic_reference ? ` · ${a.synthetic_reference}` : ""}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </SectionCard>

      <MoneyAlertsPanel caseId={caseId} />
    </div>
  );
}
