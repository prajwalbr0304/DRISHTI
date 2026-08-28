import { useEffect, useState } from "react";
import { Marker } from "react-map-gl/maplibre";
import { MapPin } from "lucide-react";
import { MapCanvas, type MapViewState } from "@/components/map/MapCanvas";

/* ============================================================================
   Compact, read-oriented location map for a SINGLE case. Verified coordinates
   use a pin; locality-only references use an uncertainty marker and reduced
   precision so the UI never implies an exact incident scene.
   ========================================================================== */

export function CaseLocationMap({
  latitude,
  longitude,
  label,
  zoom = 12.5,
  approximate = false,
  uncertaintyRadiusM,
}: {
  latitude: number;
  longitude: number;
  label?: string | null;
  zoom?: number;
  approximate?: boolean;
  uncertaintyRadiusM?: number | null;
}) {
  const [view, setView] = useState<MapViewState>({
    longitude,
    latitude,
    zoom,
    pitch: 0,
    bearing: 0,
  });

  // Recenter when the case (i.e. the coordinate) changes.
  useEffect(() => {
    setView({ longitude, latitude, zoom, pitch: 0, bearing: 0 });
  }, [longitude, latitude, zoom]);

  return (
    <div>
      <div className="relative h-44 overflow-hidden rounded-control border border-hairline">
        <MapCanvas viewState={view} onViewStateChange={setView} layers={[]}>
          <Marker longitude={longitude} latitude={latitude} anchor="center">
            {approximate ? (
              <span
                className="block size-12 rounded-full border-2 border-primary/70 bg-primary/20 shadow-[0_0_0_12px_rgba(59,130,246,0.08)]"
                title="Approximate locality reference"
              />
            ) : (
              <MapPin className="size-6 text-primary drop-shadow" fill="currentColor" />
            )}
          </Marker>
        </MapCanvas>
      </div>
      <div className="mt-1.5 flex items-center justify-between gap-2 text-12 text-content-dim">
        <span className="tnum">
          {approximate
            ? `${latitude.toFixed(3)}, ${longitude.toFixed(3)} (approx.)`
            : `${latitude.toFixed(5)}, ${longitude.toFixed(5)}`}
        </span>
        {label ? <span className="truncate">{label}</span> : null}
      </div>
      {approximate && uncertaintyRadiusM ? (
        <p className="mt-1 text-[11px] text-content-dim">
          Displayed as a locality buffer of about {Math.round(uncertaintyRadiusM / 100) / 10} km; not a measured scene boundary.
        </p>
      ) : null}
    </div>
  );
}
