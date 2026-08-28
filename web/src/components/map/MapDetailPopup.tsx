import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Popup } from "react-map-gl/maplibre";
import { AlertTriangle, ArrowUpRight, Building2, Loader2 } from "lucide-react";
import { api } from "@/api";
import { errorMessage } from "@/api/contracts";
import type { StationFeature } from "@/api/types";
import { formatDate, formatNumber } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import "@/components/map/map-detail-popup.css";

/* ============================================================================
   Click-to-inspect popups for the Live Map. A case popup pulls the real case
   record; a station popup shows the derived station summary. Both offer a
   route into the full destination.
   ========================================================================== */

export function CasePopup({
  id,
  lon,
  lat,
  onClose,
}: {
  id: number;
  lon: number;
  lat: number;
  onClose: () => void;
}) {
  const navigate = useNavigate();
  const q = useQuery({
    queryKey: ["cases", "detail", id],
    queryFn: ({ signal }) => api.cases.detail(id, signal),
  });
  const c = q.data?.core;
  const approximate = c?.not_exact_incident_scene === true
    || c?.location_precision === "approximate_locality_reference";
  const where = approximate
    ? (c?.location_label ?? "Approximate locality reference")
    : [c?.station, c?.district].filter(Boolean).join(" · ");

  return (
    <Popup
      longitude={lon}
      latitude={lat}
      onClose={onClose}
      closeOnClick={false}
      className="drishti-map-popup"
      maxWidth="360px"
      offset={14}
    >
      <div className="w-[320px] p-4 pr-8">
        {q.isLoading ? (
          <div className="flex items-center gap-2 py-2 text-12 text-content-dim">
            <Loader2 className="size-4 animate-spin" /> Loading case…
          </div>
        ) : q.error ? (
          <p className="text-12 text-content-dim">{errorMessage(q.error)}</p>
        ) : c ? (
          <div className="space-y-1.5">
            <div className="flex min-w-0 flex-wrap items-center gap-2">
              <span className="tnum break-all text-14 font-semibold text-content">{c.crime_no ?? `Case ${id}`}</span>
              {c.gravity && <Badge variant="neutral" className="capitalize">{c.gravity}</Badge>}
            </div>
            <Row label="Crime" value={[c.crime_group, c.crime_subhead].filter(Boolean).join(" · ")} />
            <Row label="Status" value={c.status} />
            <Row label="Where" value={where} />
            {approximate && (
              <p className="flex items-start gap-1.5 rounded-control border border-severity-medium/40 bg-severity-medium/5 px-2 py-1.5 text-[11px] leading-relaxed text-content-dim">
                <AlertTriangle className="mt-0.5 size-3 shrink-0 text-severity-medium" />
                Locality-level reference only; this is not the verified shed or exact alleged incident scene.
              </p>
            )}
            <Row label="Registered" value={c.registered_date ? formatDate(c.registered_date) : null} />
            {q.data && q.data.section_labels.length > 0 && (
              <div className="flex flex-wrap gap-1 pt-0.5">
                {q.data.section_labels.slice(0, 4).map((s) => (
                  <span key={s} className="tnum rounded bg-surface-2 px-1.5 py-0.5 text-[11px] text-content-dim">{s}</span>
                ))}
              </div>
            )}
            <Button size="sm" className="mt-2 w-full justify-center" onClick={() => navigate(`/cases/${id}`)}>
              Open case file <ArrowUpRight className="size-3.5" />
            </Button>
          </div>
        ) : (
          <p className="text-12 text-content-dim">Case {id} not found.</p>
        )}
      </div>
    </Popup>
  );
}

export function StationPopup({ station, onClose }: { station: StationFeature; onClose: () => void }) {
  return (
    <Popup
      longitude={station.lon}
      latitude={station.lat}
      onClose={onClose}
      closeOnClick={false}
      className="drishti-map-popup"
      maxWidth="340px"
      offset={14}
    >
      <div className="w-[300px] p-4 pr-8">
        <div className="flex items-center gap-2">
          <Building2 className="size-4 text-primary" />
          <span className="text-13 font-semibold text-content">{station.name ?? `Station ${station.station_id}`}</span>
        </div>
        <div className="mt-2 space-y-1.5">
          <Row label="District" value={station.district} />
          <Row label="Cases" value={formatNumber(station.case_count)} />
          <Row label="Top crime" value={station.top_crime} />
        </div>
        <p className="mt-2 text-[11px] text-content-dim">Location is the centroid of this station's geo-tagged incidents.</p>
      </div>
    </Popup>
  );
}

function Row({ label, value }: { label: string; value?: string | null }) {
  if (!value) return null;
  return (
    <div className="grid grid-cols-[78px_minmax(0,1fr)] items-start gap-3 text-12 leading-relaxed">
      <span className="text-content-dim">{label}</span>
      <span className="min-w-0 break-words text-left text-content">{value}</span>
    </div>
  );
}
