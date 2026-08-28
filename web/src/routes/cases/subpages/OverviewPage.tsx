import { ArrowRight, Database, ExternalLink, MapPin, Scale } from "lucide-react";
import type { CaseDetailResponse } from "@/api/types";
import { formatDate } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CaseLocationMap } from "@/components/cases/CaseLocationMap";

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
  const hasLocation = c.latitude != null && c.longitude != null;
  const currentVersion = detail.current_version;
  const sources = detail.sources ?? [];
  const referenceMapping = currentVersion?.reference_mapping ?? {};
  const location = currentVersion?.location ?? {};
  const proxyReferences = recordString(referenceMapping, "kind") === "proxy";
  const publicStation = recordString(referenceMapping, "public_station_label");
  const locationLabel = recordString(location, "label");
  const locationPrecision = recordString(location, "precision");

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
            <Fact label="Case reference" value={c.crime_no} mono />
            <Fact label="Status" value={c.status} />
            <Fact label="Gravity" value={c.gravity} />
            <Fact label="Crime head" value={c.crime_group} />
            <Fact label="Sub-head" value={c.crime_subhead} />
            <Fact label="Registered" value={c.registered_date ? formatDate(c.registered_date) : null} />
            <Fact label="District" value={c.district} />
            <Fact
              label={proxyReferences ? "Station (public-source label)" : "Station"}
              value={publicStation ?? c.station}
            />
            <Fact
              label="Investigating officer"
              value={proxyReferences ? "Not asserted (fixture FK is a proxy)" : c.io_name}
            />
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

        {currentVersion && !currentVersion.is_synthetic && (
          <div className="rounded-card border border-hairline bg-surface p-4">
            <div className="mb-2 flex items-center gap-1.5 text-12 font-semibold uppercase tracking-wide text-content-dim">
              <Database className="size-3.5" /> Record origin & provenance
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="primary">Public-source curated</Badge>
              <Badge variant="neutral">Non-synthetic</Badge>
              {currentVersion.excluded_from_derived_analytics && (
                <Badge variant="neutral">Excluded from derived analytics</Badge>
              )}
            </div>
            <dl className="mt-3 grid grid-cols-1 gap-2 text-12 sm:grid-cols-2">
              <MetaFact label="Source cutoff" value={currentVersion.source_cutoff ?? "—"} />
              {Object.entries(currentVersion.official_references)
                .filter((entry): entry is [string, string] => typeof entry[1] === "string")
                .map(([key, value]) => (
                  <MetaFact key={key} label={key.replaceAll("_", " ")} value={value} mono />
                ))}
            </dl>
            {proxyReferences && (
              <p className="mt-3 rounded-control border border-hairline bg-surface-2/50 px-3 py-2 text-12 leading-relaxed text-content-dim">
                Station, officer and court foreign keys are deterministic fixture proxies. Public labels are shown where sourced; proxy names must not be presented as the real investigating authority or trial court.
              </p>
            )}
          </div>
        )}

        {sources.length > 0 && (
          <div className="rounded-card border border-hairline bg-surface p-4">
            <div className="mb-2 text-12 font-semibold uppercase tracking-wide text-content-dim">
              Sources ({sources.length})
            </div>
            <div className="divide-y divide-hairline">
              {sources.map((source) => (
                <div key={source.source_record_id} className="py-2 first:pt-0 last:pb-0">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="text-13 font-medium text-content">
                        {source.public_source_id && <span className="mr-1 font-mono text-11 text-content-dim">{source.public_source_id}</span>}
                        {source.title ?? source.external_ref ?? "Public source"}
                      </div>
                      <p className="mt-0.5 text-12 text-content-dim">
                        {[source.publisher, source.published_date].filter(Boolean).join(" · ")}
                      </p>
                    </div>
                    {source.source_url && (
                      <a
                        href={source.source_url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex shrink-0 items-center gap-1 text-12 font-medium text-primary hover:underline"
                      >
                        Open <ExternalLink className="size-3" />
                      </a>
                    )}
                  </div>
                  {source.authenticity && (
                    <p className="mt-1 text-11 leading-relaxed text-content-dim">{source.authenticity}</p>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Right column: location + people */}
      <div className="space-y-4">
        <div className="rounded-card border border-hairline bg-surface p-4">
          <div className="mb-2 flex items-center gap-1.5 text-12 font-semibold uppercase tracking-wide text-content-dim">
            <MapPin className="size-3.5" /> Location
          </div>
          {hasLocation ? (
            <>
              <CaseLocationMap
                latitude={c.latitude as number}
                longitude={c.longitude as number}
                label={locationLabel ?? c.location_label ?? c.station ?? c.district ?? undefined}
                approximate={c.not_exact_incident_scene || locationPrecision === "approximate_locality_reference"}
                uncertaintyRadiusM={c.location_uncertainty_radius_m ?? undefined}
              />
              {(c.not_exact_incident_scene || locationPrecision === "approximate_locality_reference") && (
                <p className="mt-2 text-11 leading-relaxed text-content-dim">
                  Approximate Pattanagere locality reference from OpenStreetMap; not the verified shed or exact alleged incident scene.
                  {c.location_attribution ? ` ${c.location_attribution}.` : ""}
                </p>
              )}
            </>
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


function recordString(record: Record<string, unknown>, key: string): string | null {
  const value = record[key];
  return typeof value === "string" && value.trim() ? value : null;
}

function MetaFact({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <dt className="capitalize text-content-dim">{label}</dt>
      <dd className={`mt-0.5 text-content ${mono ? "font-mono" : ""}`}>{value}</dd>
    </div>
  );
}
