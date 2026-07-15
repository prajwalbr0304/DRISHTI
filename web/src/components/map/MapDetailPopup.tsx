import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Popup } from "react-map-gl/maplibre";
import { ArrowUpRight, Building2, Loader2 } from "lucide-react";
import { api } from "@/api";
import { errorMessage } from "@/api/contracts";
import type { StationFeature } from "@/api/types";
import { formatDate, formatNumber } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

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

  return (
    <Popup longitude={lon} latitude={lat} anchor="bottom" onClose={onClose} closeOnClick={false} maxWidth="300px" offset={12}>
      <div className="w-64 p-3">
        {q.isLoading ? (
          <div className="flex items-center gap-2 py-2 text-12 text-content-dim">
            <Loader2 className="size-4 animate-spin" /> Loading case…
          </div>
        ) : q.error ? (
          <p className="text-12 text-content-dim">{errorMessage(q.error)}</p>
        ) : c ? (
          <div className="space-y-1.5">
            <div className="flex items-center gap-2">
              <span className="tnum text-13 font-semibold text-content">{c.crime_no ?? `Case ${id}`}</span>
              {c.gravity && <Badge variant="neutral" className="capitalize">{c.gravity}</Badge>}
            </div>
            <Row label="Crime" value={[c.crime_group, c.crime_subhead].filter(Boolean).join(" · ")} />
            <Row label="Status" value={c.status} />
            <Row label="Where" value={[c.station, c.district].filter(Boolean).join(" · ")} />
            <Row label="Registered" value={c.registered_date ? formatDate(c.registered_date) : null} />
            {q.data && q.data.section_labels.length > 0 && (
              <div className="flex flex-wrap gap-1 pt-0.5">
                {q.data.section_labels.slice(0, 4).map((s) => (
                  <span key={s} className="tnum rounded bg-surface-2 px-1.5 py-0.5 text-[11px] text-content-dim">{s}</span>
                ))}
              </div>
            )}
            <Button size="sm" className="mt-1 w-full justify-center" onClick={() => navigate(`/cases/${id}`)}>
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
    <Popup longitude={station.lon} latitude={station.lat} anchor="bottom" onClose={onClose} closeOnClick={false} maxWidth="280px" offset={12}>
      <div className="w-56 p-3">
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
    <div className="flex items-baseline justify-between gap-3 text-12">
      <span className="shrink-0 text-content-dim">{label}</span>
      <span className="min-w-0 truncate text-right text-content">{value}</span>
    </div>
  );
}
