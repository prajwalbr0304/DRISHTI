import { useEffect, useState } from "react";
import { Marker } from "react-map-gl/maplibre";
import { MapPin } from "lucide-react";
import { MapCanvas, type MapViewState } from "@/components/map/MapCanvas";

/* ============================================================================
   Compact, read-oriented location map for a SINGLE incident: the case pinned on
   the real Karnataka basemap (the app's MapLibre + deck.gl stack). This replaces
   the abstract density scatter on the case Overview, where — with just one point
   — a grid of dots reads as empty/broken. The full toolset lives in Map &
   Hotspots.
   ========================================================================== */

export function CaseLocationMap({
  latitude,
  longitude,
  label,
  zoom = 12.5,
}: {
  latitude: number;
  longitude: number;
  label?: string | null;
  zoom?: number;
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
          <Marker longitude={longitude} latitude={latitude} anchor="bottom">
            <MapPin className="size-6 text-primary drop-shadow" fill="currentColor" />
          </Marker>
        </MapCanvas>
      </div>
      <div className="mt-1.5 flex items-center justify-between gap-2 text-12 text-content-dim">
        <span className="tnum">
          {latitude.toFixed(5)}, {longitude.toFixed(5)}
        </span>
        {label ? <span className="truncate">{label}</span> : null}
      </div>
    </div>
  );
}
