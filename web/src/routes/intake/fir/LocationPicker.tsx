import { useEffect, useState } from "react";
import { Marker } from "react-map-gl/maplibre";
import { useQuery } from "@tanstack/react-query";
import { MapPin, MoveRight, ShieldAlert, ShieldCheck } from "lucide-react";
import { api } from "@/api";
import { cn } from "@/lib/utils";
import { roleCan } from "@/config/roles";
import { useRole } from "@/providers/RoleProvider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { MapCanvas, type MapViewState } from "@/components/map/MapCanvas";
import { KARNATAKA_VIEW } from "@/components/map/mapConfig";


/* Click-to-pin incident location with live jurisdiction/containment (DoD §E:
   map-based location with jurisdiction display). An out-of-assigned-district
   pin is a BLOCKING mismatch: the officer either reassigns the registering
   district to the detected one, or a supervisor records an audited override. */
export function LocationPicker({
  latitude, longitude, assignedDistrictId, onChange, disabled,
  onUseDetectedDistrict, overrideReason, onOverrideReasonChange,
}: {
  latitude?: number | null;
  longitude?: number | null;
  assignedDistrictId?: number | null;
  onChange: (lat: number, lon: number) => void;
  disabled?: boolean;
  /** Reassign the registering district to the detected one (clears the mismatch). */
  onUseDetectedDistrict?: (districtId: number, districtName?: string | null) => void;
  /** Supervisory override reason (recorded + audited) that lets the mismatch through. */
  overrideReason?: string | null;
  onOverrideReasonChange?: (reason: string) => void;
}) {
  const { role } = useRole();
  const canOverride = roleCan(role, "jurisdiction_override");
  const [view, setView] = useState<MapViewState>({ ...KARNATAKA_VIEW });
  const hasPoint = latitude != null && longitude != null;

  const juris = useQuery({
    queryKey: ["intake", "geo", latitude, longitude, assignedDistrictId ?? null],
    queryFn: ({ signal }) =>
      api.intake.geoResolve(
        { latitude, longitude, assigned_district_id: assignedDistrictId ?? null }, signal),
    enabled: hasPoint,
  });

  useEffect(() => {
    if (hasPoint) setView((v) => ({ ...v, longitude: longitude!, latitude: latitude!, zoom: Math.max(v.zoom, 9) }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasPoint]);

  const j = juris.data;
  return (
    <div className="space-y-2">
      <div className="relative h-64 overflow-hidden rounded-card border border-hairline">
        <MapCanvas
          viewState={view}
          onViewStateChange={setView}
          layers={[]}
          onMapClick={disabled ? undefined : ({ lng, lat }) => onChange(lat, lng)}
        >
          {hasPoint && (
            <Marker longitude={longitude!} latitude={latitude!} anchor="bottom">
              <MapPin className="size-6 text-primary drop-shadow" fill="currentColor" />
            </Marker>
          )}
        </MapCanvas>
        {!hasPoint && (
          <div className="pointer-events-none absolute inset-x-0 bottom-2 mx-auto w-fit rounded-full bg-surface/90 px-3 py-1 text-12 text-content-dim">
            Click the map to pin the incident location
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2 text-12">
        {hasPoint ? (
          <span className="tnum text-content-dim">
            {latitude!.toFixed(5)}, {longitude!.toFixed(5)}
          </span>
        ) : (
          <span className="text-content-dim">No location set</span>
        )}
        {j && (
          <>
            <Badge variant={j.in_state ? "low" : "high"}>
              {j.in_state ? <ShieldCheck className="size-3" /> : <ShieldAlert className="size-3" />}
              {j.in_state ? "In Karnataka" : "Outside state"}
            </Badge>
            {j.resolved_district_name && (
              <Badge variant="neutral">District: {j.resolved_district_name}</Badge>
            )}
            {assignedDistrictId != null && (
              <Badge variant={j.in_assigned_district ? "low" : "medium"}>
                {j.in_assigned_district ? "Matches assigned district" : "Jurisdiction mismatch"}
              </Badge>
            )}
            {j.nearest_unit_name && (
              <span className="text-content-dim">Nearest: {j.nearest_unit_name}</span>
            )}
          </>
        )}
      </div>
      {j?.note && <p className={cn("text-12", j.in_state ? "text-severity-medium" : "text-severity-high")}>{j.note}</p>}

      {/* Out-of-assigned-district mismatch: resolve by reassigning the registering
          district to the detected one, or record a supervisory override. */}
      {!disabled && j && j.in_state !== false && assignedDistrictId != null
        && j.in_assigned_district === false && (
        <div className="space-y-2 rounded-card border border-severity-medium/40 bg-severity-medium/5 p-2.5">
          <p className="flex items-center gap-1.5 text-12 text-severity-medium">
            <ShieldAlert className="size-3.5 shrink-0" />
            The pin is outside the assigned district
            {j.resolved_district_name ? ` (detected: ${j.resolved_district_name})` : ""}. Submitting is
            blocked until this is resolved.
          </p>
          {j.resolved_district_id != null && onUseDetectedDistrict && (
            <Button size="sm" variant="secondary"
              onClick={() => onUseDetectedDistrict(j.resolved_district_id!, j.resolved_district_name)}>
              <MoveRight className="size-3.5" /> Use detected district
              {j.resolved_district_name ? ` (${j.resolved_district_name})` : ""}
            </Button>
          )}
          {onOverrideReasonChange && (
            canOverride ? (
              <div>
                <label className="mb-1 block text-11 uppercase tracking-wide text-content-dim">
                  Supervisory override reason (recorded &amp; audited)
                </label>
                <input value={overrideReason ?? ""}
                  onChange={(e) => onOverrideReasonChange(e.target.value)}
                  placeholder="e.g. cross-border case retained here by DySP order…"
                  className="h-8 w-full rounded-control border border-hairline bg-surface px-2 text-13" />
              </div>
            ) : (
              <p className="text-11 text-content-dim">
                A Supervisor demo view can record an override reason to submit despite the mismatch.
              </p>
            )
          )}
        </div>
      )}
    </div>
  );
}
