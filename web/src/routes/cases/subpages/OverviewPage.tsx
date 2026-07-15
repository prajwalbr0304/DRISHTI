import { ArrowRight, MapPin, Scale } from "lucide-react";
import type { CaseDetailResponse } from "@/api/types";
import { formatDate } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { MiniDensity } from "@/components/dashboard/MiniDensity";

/* Case Overview (doc 01 §4.2): the FIR at a glance — key facts, mini-map,
   charges and key people. */
export function OverviewPage({
  detail,
  goTo,
}: {
  detail: CaseDetailResponse;
  goTo: (tab: string) => void;
}) {
  const c = detail.core;
  const point =
    c.latitude != null && c.longitude != null
      ? [{ lon: c.longitude, lat: c.latitude, weight: 0.85 }]
      : [];

  const people = [
    ...detail.accused.map((p) => ({ ...p, role: "Accused" as const })),
    ...detail.victims.map((p) => ({ ...p, role: "Victim" as const })),
    ...detail.complainants.map((p) => ({ ...p, role: "Complainant" as const })),
  ];

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      <div className="space-y-4 lg:col-span-2">
        <div className="rounded-card border border-hairline bg-surface p-4">
          <div className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-3">
            <Fact label="Crime no." value={c.crime_no} mono />
            <Fact label="Status" value={c.status} />
            <Fact label="Gravity" value={c.gravity} />
            <Fact label="Crime head" value={c.crime_group} />
            <Fact label="Sub-head" value={c.crime_subhead} />
            <Fact label="Registered" value={c.registered_date ? formatDate(c.registered_date) : null} />
            <Fact label="District" value={c.district} />
            <Fact label="Station" value={c.station} />
            <Fact label="Investigating officer" value={c.io_name} />
          </div>

          {(c.incident_from || c.incident_to) && (
            <div className="mt-3 border-t border-hairline pt-3 text-13 text-content-dim">
              Incident window:{" "}
              <span className="tnum text-content">
                {c.incident_from ? formatDate(c.incident_from) : "?"} –{" "}
                {c.incident_to ? formatDate(c.incident_to) : "?"}
              </span>
            </div>
          )}
        </div>

        {/* Charges */}
        <div className="rounded-card border border-hairline bg-surface p-4">
          <div className="mb-2 flex items-center gap-1.5 text-12 font-semibold uppercase tracking-wide text-content-dim">
            <Scale className="size-3.5" /> Acts & sections
          </div>
          {detail.section_labels.length ? (
            <div className="flex flex-wrap gap-1.5">
              {detail.section_labels.map((s) => (
                <Badge key={s} variant="primary" className="tnum">
                  {s}
                </Badge>
              ))}
            </div>
          ) : (
            <p className="text-13 text-content-dim">No act/section charges recorded.</p>
          )}
        </div>

        {/* Brief facts */}
        <div className="rounded-card border border-hairline bg-surface p-4">
          <div className="mb-2 text-12 font-semibold uppercase tracking-wide text-content-dim">Brief facts</div>
          <p className="whitespace-pre-line text-14 leading-relaxed text-content">
            {c.brief_facts?.trim() || "No brief facts recorded."}
          </p>
        </div>
      </div>

      {/* Right column: location + people */}
      <div className="space-y-4">
        <div className="rounded-card border border-hairline bg-surface p-4">
          <div className="mb-2 flex items-center gap-1.5 text-12 font-semibold uppercase tracking-wide text-content-dim">
            <MapPin className="size-3.5" /> Location
          </div>
          {point.length ? (
            <MiniDensity points={point} />
          ) : (
            <p className="text-13 text-content-dim">No geolocation on this FIR.</p>
          )}
        </div>

        <div className="rounded-card border border-hairline bg-surface p-4">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-12 font-semibold uppercase tracking-wide text-content-dim">Key people</span>
            <Button variant="ghost" size="sm" className="h-6 gap-1 px-1.5 text-12" onClick={() => goTo("accused")}>
              View all <ArrowRight className="size-3" />
            </Button>
          </div>
          {people.length ? (
            <div className="flex flex-wrap gap-1.5">
              {people.slice(0, 12).map((p, i) => (
                <span
                  key={`${p.role}-${p.id}-${i}`}
                  className="inline-flex items-center gap-1.5 rounded-full border border-hairline bg-surface-2 py-0.5 pl-1 pr-2 text-12"
                >
                  <span className="rounded-full bg-surface px-1.5 py-0.5 text-[10px] text-content-dim">{p.role}</span>
                  <span className="text-content">{p.name ?? "—"}</span>
                </span>
              ))}
            </div>
          ) : (
            <p className="text-13 text-content-dim">No people linked yet.</p>
          )}
        </div>
      </div>
    </div>
  );
}

function Fact({ label, value, mono }: { label: string; value?: string | null; mono?: boolean }) {
  return (
    <div className="min-w-0">
      <div className="text-12 text-content-dim">{label}</div>
      <div className={`truncate text-13 text-content ${mono ? "tnum" : ""}`} title={value ?? undefined}>
        {value ?? "—"}
      </div>
    </div>
  );
}
